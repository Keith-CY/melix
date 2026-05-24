import AppKit
import Foundation

@testable import AppMain
import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

enum MenuBarTestEnvironment {
    static var isHeadlessCI: Bool {
        let environment = ProcessInfo.processInfo.environment
        return environment["GITHUB_ACTIONS"] == "true" || environment["CI"] == "true"
    }

    static var bootstrapConditionTimeout: Duration {
        .seconds(10)
    }
}

final class RecordingPasteboard: RuntimePasteboardWriting {
    private(set) var string: String?
    private(set) var clearCount = 0

    @discardableResult
    func clearContents() -> Int {
        clearCount += 1
        string = nil
        return clearCount
    }

    func setString(_ string: String, forType dataType: NSPasteboard.PasteboardType) -> Bool {
        guard dataType == .string else {
            return false
        }
        self.string = string
        return true
    }
}

final class FakeRemoteServerStore: RemoteServerStoring, @unchecked Sendable {
    enum StoreError: Error, Equatable {
        case list
        case save
        case remove
    }

    private(set) var savedMutations: [RemoteServerMutation] = []
    private(set) var removedIDs: [String] = []
    var servers: [RemoteServer]
    var listError: StoreError?
    var saveError: StoreError?
    var removeError: StoreError?
    var apiKeys: [String: String]

    init(servers: [RemoteServer] = [], apiKeys: [String: String] = [:]) {
        self.servers = servers
        self.apiKeys = apiKeys
    }

    func list() throws -> [RemoteServer] {
        if let listError {
            throw listError
        }
        return servers.sorted { $0.id < $1.id }
    }

    func loadAPIKey(remoteServerID: String) throws -> RemoteServerAPIKeyRecord? {
        guard let apiKey = apiKeys[remoteServerID] else {
            return nil
        }
        return RemoteServerAPIKeyRecord(remoteServerID: remoteServerID, apiKey: apiKey)
    }

    @discardableResult
    func save(_ mutation: RemoteServerMutation) throws -> RemoteServer {
        if let saveError {
            throw saveError
        }
        savedMutations.append(mutation)
        let now = Date()
        let existing = servers.first { $0.id == mutation.id }
        let server = RemoteServer(
            id: mutation.id,
            title: mutation.title,
            providerPreset: mutation.providerPreset,
            providerKind: mutation.providerPreset.providerKind,
            baseURL: mutation.providerPreset.fixedBaseURL ?? mutation.baseURL,
            defaultModelID: mutation.defaultModelID,
            timeoutSeconds: mutation.timeoutSeconds,
            rateLimitPerMinute: mutation.rateLimitPerMinute,
            credentialRef: RemoteServerStore.credentialRef(for: mutation.id),
            apiKeyHint: mutation.apiKey.isEmpty
                ? (existing?.apiKeyHint ?? "")
                : RemoteServerAPIKeyStore.maskedHint(for: mutation.apiKey),
            healthStatus: existing?.healthStatus ?? "unknown",
            createdAt: existing?.createdAt ?? now,
            updatedAt: now
        )
        if mutation.apiKey.isEmpty == false {
            apiKeys[mutation.id] = mutation.apiKey
        }
        servers.removeAll { $0.id == mutation.id }
        servers.append(server)
        return server
    }

    func remove(id: String) throws {
        if let removeError {
            throw removeError
        }
        removedIDs.append(id)
        apiKeys.removeValue(forKey: id)
        servers.removeAll { $0.id == id }
    }
}

final class FakeEvaluationPromptStore: EvaluationPromptStoring, @unchecked Sendable {
    enum StoreError: Error, Equatable {
        case list
        case create
        case update
        case freeze
        case archive
        case resolve
    }

    private(set) var createdPrompts: [(id: String, title: String, systemPrompt: String)] = []
    private(set) var updatedPrompts: [(id: String, systemPrompt: String)] = []
    private(set) var frozenPrompts: [(id: String, revisionID: String)] = []
    private(set) var archivedPromptIDs: [String] = []
    var prompts: [EvaluationPrompt]
    var listError: StoreError?
    var createError: StoreError?
    var updateError: StoreError?
    var freezeError: StoreError?
    var archiveError: StoreError?
    var resolveError: StoreError?

    init(prompts: [EvaluationPrompt] = [EvaluationPromptStore.builtInBaselinePrompt]) {
        self.prompts = prompts
    }

    func list(includeArchived: Bool) throws -> [EvaluationPrompt] {
        if let listError {
            throw listError
        }
        return prompts
            .filter { includeArchived || $0.archived == false }
            .sorted { $0.id < $1.id }
    }

    @discardableResult
    func create(promptID: String, title: String, systemPrompt: String) throws -> EvaluationPrompt {
        if let createError {
            throw createError
        }
        createdPrompts.append((id: promptID, title: title, systemPrompt: systemPrompt))
        let prompt = Self.makePrompt(
            id: promptID,
            title: title,
            revisionID: "rev-1",
            status: .draft,
            systemPrompt: systemPrompt
        )
        prompts.removeAll { $0.id == promptID }
        prompts.append(prompt)
        return prompt
    }

    @discardableResult
    func update(promptID: String, systemPrompt: String) throws -> EvaluationPrompt {
        if let updateError {
            throw updateError
        }
        updatedPrompts.append((id: promptID, systemPrompt: systemPrompt))
        let existing = prompts.first { $0.id == promptID }
        let nextRevisionID: String
        let nextStatus: EvaluationPromptRevisionStatus
        if existing?.latestRevision?.status == .draft {
            nextRevisionID = existing?.latestRevisionID ?? "rev-1"
            nextStatus = .draft
        } else {
            nextRevisionID = "rev-\((existing?.revisions.count ?? 0) + 1)"
            nextStatus = .draft
        }
        let prompt = Self.makePrompt(
            id: promptID,
            title: existing?.title ?? promptID,
            revisionID: nextRevisionID,
            status: nextStatus,
            systemPrompt: systemPrompt,
            existingRevisions: existing?.revisions ?? []
        )
        prompts.removeAll { $0.id == promptID }
        prompts.append(prompt)
        return prompt
    }

    @discardableResult
    func freeze(promptID: String, revisionID: String) throws -> EvaluationPrompt {
        if let freezeError {
            throw freezeError
        }
        frozenPrompts.append((id: promptID, revisionID: revisionID))
        let existing = prompts.first { $0.id == promptID } ?? EvaluationPromptStore.builtInBaselinePrompt
        let selectedRevisionID = revisionID.isEmpty ? existing.latestRevisionID : revisionID
        let systemPrompt = existing.latestRevision?.systemPrompt ?? EvaluationPromptStore.builtInBaselineSystemPrompt
        let prompt = Self.makePrompt(
            id: existing.id,
            title: existing.title,
            revisionID: selectedRevisionID,
            status: .frozen,
            systemPrompt: systemPrompt,
            existingRevisions: existing.revisions
        )
        prompts.removeAll { $0.id == promptID }
        prompts.append(prompt)
        return prompt
    }

    @discardableResult
    func archive(promptID: String) throws -> EvaluationPrompt {
        if let archiveError {
            throw archiveError
        }
        archivedPromptIDs.append(promptID)
        let existing = prompts.first { $0.id == promptID } ?? EvaluationPromptStore.builtInBaselinePrompt
        let archived = EvaluationPrompt(
            id: existing.id,
            title: existing.title,
            taskKind: existing.taskKind,
            scoringMode: existing.scoringMode,
            latestRevisionID: existing.latestRevisionID,
            archived: true,
            readOnly: existing.readOnly,
            revisions: existing.revisions,
            createdAt: existing.createdAt,
            updatedAt: Date()
        )
        prompts.removeAll { $0.id == promptID }
        prompts.append(archived)
        return archived
    }

    func resolveForRun(promptID: String, revisionID: String) throws -> EvaluationPromptSnapshot {
        if let resolveError {
            throw resolveError
        }
        let requestedID = promptID.isEmpty ? EvaluationPromptStore.builtInBaselinePromptID : promptID
        let prompt = prompts.first { $0.id == requestedID } ?? EvaluationPromptStore.builtInBaselinePrompt
        let revision = revisionID.isEmpty
            ? prompt.latestRevision
            : prompt.revisions.first { $0.revisionID == revisionID }
        guard let revision else {
            throw StoreError.resolve
        }
        guard prompt.archived == false, revision.status == .frozen else {
            throw StoreError.resolve
        }
        return EvaluationPromptSnapshot(prompt: prompt, revision: revision)
    }

    private static func makePrompt(
        id: String,
        title: String,
        revisionID: String,
        status: EvaluationPromptRevisionStatus,
        systemPrompt: String,
        existingRevisions: [EvaluationPromptRevision] = []
    ) -> EvaluationPrompt {
        let now = Date()
        let revision = EvaluationPromptRevision(
            revisionID: revisionID,
            status: status,
            systemPrompt: systemPrompt,
            contentHash: try! EvaluationPromptStore.contentHash(systemPrompt: systemPrompt),
            createdAt: now,
            updatedAt: now
        )
        var revisions = existingRevisions
        revisions.removeAll { $0.revisionID == revisionID }
        revisions.append(revision)
        return EvaluationPrompt(
            id: id,
            title: title,
            latestRevisionID: revisionID,
            revisions: revisions,
            createdAt: now,
            updatedAt: now
        )
    }
}

final class FakeLoraTrainingJobStore: LoraTrainingJobStoring, @unchecked Sendable {
    enum StoreError: Error, Equatable {
        case list
        case save
        case duplicate
        case delete
        case importConfig
        case exportConfig
    }

    private(set) var savedRecords: [LoraTrainingJobRecord] = []
    private(set) var deletedIDs: [String] = []
    private(set) var exportedConfigs: [(config: LoraTrainingJobConfig, path: String)] = []
    var importedConfig: LoraTrainingJobConfig?
    var jobs: [LoraTrainingJobRecord]
    var listError: StoreError?
    var saveError: StoreError?
    var duplicateError: StoreError?
    var deleteError: StoreError?
    var importError: StoreError?
    var exportError: StoreError?

    init(jobs: [LoraTrainingJobRecord] = []) {
        self.jobs = jobs
    }

    func list() throws -> [LoraTrainingJobRecord] {
        if let listError {
            throw listError
        }
        return jobs.sorted { $0.updatedAt > $1.updatedAt }
    }

    func get(id: String) throws -> LoraTrainingJobRecord? {
        jobs.first { $0.id == id }
    }

    @discardableResult
    func save(_ record: LoraTrainingJobRecord) throws -> LoraTrainingJobRecord {
        if let saveError {
            throw saveError
        }
        var saved = record
        saved.updatedAt = Date()
        savedRecords.append(saved)
        jobs.removeAll { $0.id == saved.id }
        jobs.append(saved)
        return saved
    }

    @discardableResult
    func createDraft(title: String, config: LoraTrainingJobConfig) throws -> LoraTrainingJobRecord {
        if let saveError {
            throw saveError
        }
        let now = Date()
        let record = LoraTrainingJobRecord(
            id: "desktop-\(jobs.count + 1)",
            title: title,
            config: config,
            status: .draft,
            createdAt: now,
            updatedAt: now
        )
        savedRecords.append(record)
        jobs.append(record)
        return record
    }

    @discardableResult
    func duplicate(id: String) throws -> LoraTrainingJobRecord {
        if let duplicateError {
            throw duplicateError
        }
        guard let source = jobs.first(where: { $0.id == id }) else {
            throw StoreError.duplicate
        }
        let now = Date()
        let copy = LoraTrainingJobRecord(
            id: "\(source.id)-copy",
            title: "\(source.title) Copy",
            config: source.config,
            status: .draft,
            createdAt: now,
            updatedAt: now
        )
        jobs.append(copy)
        return copy
    }

    func delete(id: String) throws {
        if let deleteError {
            throw deleteError
        }
        deletedIDs.append(id)
        jobs.removeAll { $0.id == id }
    }

    func importConfig(from fileURL: URL) throws -> LoraTrainingJobConfig {
        if let importError {
            throw importError
        }
        if let importedConfig {
            return importedConfig
        }
        let data = try Data(contentsOf: fileURL)
        return try JSONDecoder().decode(LoraTrainingJobConfig.self, from: data)
    }

    func exportConfig(_ config: LoraTrainingJobConfig, to fileURL: URL) throws {
        if let exportError {
            throw exportError
        }
        exportedConfigs.append((config: config, path: fileURL.path))
    }
}

actor FakeControlPlaneXPCClient: ControlPlaneXPCClient {
    struct ScheduledChatEvent: Equatable, Sendable {
        let delay: Duration
        let event: ControlPlaneChatStreamEvent

        init(delay: Duration = .zero, event: ControlPlaneChatStreamEvent) {
            self.delay = delay
            self.event = event
        }
    }

    struct RecordedModelOperationRequest: Equatable, Sendable {
        let modelID: String
        let operation: String
        let outputDir: String
        let quantProfileID: String
        let weightQuant: String
        let kvQuant: String
        let ext: [String: String]
    }

    struct RecordedGatewayAccessApplyRequest: Equatable, Sendable {
        let serverSessionID: String
        let primaryKey: String
        let keyID: String
        let label: String
        let tokenHint: String
    }

    struct RecordedGatewayConfigApplyRequest: Equatable, Sendable {
        let serverSessionID: String
        let host: String
        let port: Int
        let defaultModelID: String
        let servedModelIDs: [String]
        let rateLimitPerMinute: Int
        let timeoutSeconds: Int
        let modelIdleTimeoutSeconds: Int
    }

    struct RecordedServingDefaultsApplyRequest: Equatable, Sendable {
        let serverSessionID: String
        let temperature: Double
        let topP: Double
        let maxTokens: Int
        let streamIntervalTokens: Int
        let maxConcurrentRequests: Int
        let concurrentProcessingEnabled: Bool
        let prefillBatchSize: Int
        let completionBatchSize: Int
        let accelerationMode: Melix_Controlplane_V1_AccelerationMode
        let draftModelID: String
        let numDraftTokens: Int
        let accelerationProfile: String
    }

    struct RecordedImageDefaultsApplyRequest: Equatable, Sendable {
        let generateModelID: String
        let editModelID: String
        let size: String
        let steps: UInt32
        let guidance: Float
        let strength: Float
        let negativePrompt: String
    }

    struct RecordedImageGenerateRequest: Equatable, Sendable {
        let modelID: String
        let prompt: String
        let size: String
        let steps: UInt32
        let guidance: Float
        let negativePrompt: String
        let n: UInt32
        let responseFormat: String
        let artifactNamespace: String
    }

    struct RecordedImageEditRequest: Equatable, Sendable {
        let modelID: String
        let prompt: String
        let imageURL: String
        let maskURL: String
        let sourceArtifactID: String
        let promptDelta: String
        let mode: ControlPlaneImageEditRequest.Mode
        let strength: Float
        let size: String
        let steps: UInt32
        let guidance: Float
        let negativePrompt: String
        let n: UInt32
        let responseFormat: String
    }

    struct RecordedServerIdlePolicyRequest: Equatable, Sendable {
        let serverSessionID: String
        let autoSleepEnabled: Bool
        let lightSleepAfterSeconds: UInt32
        let deepSleepAfterSeconds: UInt32
    }

    struct RecordedHubSearchRequest: Equatable, Sendable {
        let query: String
        let pageSize: UInt32
        let cursor: String
        let mlxOnly: Bool
    }

    struct RecordedHubModelCardRequest: Equatable, Sendable {
        let repoID: String
    }

    struct RecordedModelSettingsUpdate: Equatable, Sendable {
        let modelID: String
        let values: [String: String]
    }

    private var streamContinuations: [AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>.Continuation] = []
    private var nextEventSequence: UInt64 = 1

    private(set) var recordedActions: [String] = []
    private(set) var recordedModelSettingsUpdates: [RecordedModelSettingsUpdate] = []
    private(set) var recordedModelOperationRequests: [RecordedModelOperationRequest] = []
    private(set) var recordedBenchRequests: [ControlPlaneBenchRequest] = []
    private(set) var recordedBenchMatrixRequests: [ControlPlaneBenchMatrixRequest] = []
    private(set) var recordedEvaluationRequests: [ControlPlaneEvaluationRequest] = []
    private(set) var recordedExportOutputDirs: [String] = []
    private(set) var recordedGatewayAccessApplyRequests: [RecordedGatewayAccessApplyRequest] = []
    private(set) var recordedGatewayConfigApplyRequests: [RecordedGatewayConfigApplyRequest] = []
    private(set) var recordedServingDefaultsApplyRequests: [RecordedServingDefaultsApplyRequest] = []
    private(set) var recordedImageDefaultsApplyRequests: [RecordedImageDefaultsApplyRequest] = []
    private(set) var recordedImageGenerateRequests: [RecordedImageGenerateRequest] = []
    private(set) var recordedImageEditRequests: [RecordedImageEditRequest] = []
    private(set) var recordedGatewayAccessClearRequests: [String] = []
    private(set) var recordedServerIdlePolicyRequests: [RecordedServerIdlePolicyRequest] = []
    private(set) var recordedHubSearchRequests: [RecordedHubSearchRequest] = []
    private(set) var recordedHubModelCardRequests: [RecordedHubModelCardRequest] = []
    private(set) var lastLoadMemoryBudgetBytes: UInt64 = 0
    private(set) var handshakeCount = 0
    private(set) var subscriptionRequests: [UInt64] = []
    private var modelState: Melix_Controlplane_V1_ModelState = .modelDiscovered
    private var handshakeError: Error?
    private var loadError: Error?
    private var unloadError: Error?
    private var snapshotError: Error?
    private var modelSettingsError: Error?
    private var modelInfoError: Error?
    private var modelOperationError: Error?
    private var modelOperationDelay: Duration = .zero
    private var doctorError: Error?
    private var benchError: Error?
    private var benchMatrixError: Error?
    private var evaluationError: Error?
    private var exportError: Error?
    private var chatError: Error?
    private var imageGenerateError: Error?
    private var imageEditError: Error?
    private var cancelError: Error?
    private var applyGatewayAccessError: Error?
    private var applyGatewayConfigError: Error?
    private var applyServingDefaultsError: Error?
    private var applyImageDefaultsError: Error?
    private var clearGatewayAccessError: Error?
    private var startServerError: Error?
    private var pauseServerError: Error?
    private var resumeServerError: Error?
    private var wakeServerError: Error?
    private var stopServerError: Error?
    private var updateServerIdlePolicyError: Error?
    private var snapshotOverride: Melix_Controlplane_V1_ServerSnapshot?
    private var responseFeatures: [String] = ["chat"]
    private var modelSettings = FakeControlPlaneXPCClient.defaultModelSettings()
    private var modelInfoResponse = FakeControlPlaneXPCClient.defaultModelInfo()
    private var modelOperationResponse = FakeControlPlaneXPCClient.defaultModelOperation()
    private var modelOperationResponsesByName: [String: Melix_Controlplane_V1_ModelOperationResult] = [:]
    private var modelOperationErrorsByName: [String: Error] = [:]
    private var doctorResponse = FakeControlPlaneXPCClient.defaultDoctorReport()
    private var hubSearchResult = Melix_Controlplane_V1_HubSearchResult()
    private var hubModelCard = Melix_Controlplane_V1_HubModelCard()
    private var benchResponse = ControlPlaneBenchResult(
        reportPath: "/tmp/melix-fake/bench-report.md",
        reportMarkdown: "# Melix Bench\n\n- bench.smoke.ttft_ms: 24.45 ms\n",
        metrics: ["bench.smoke.ttft_ms": 24.45]
    )
    private var benchMatrixResponse = ControlPlaneBenchMatrixResult(
        job: {
            var job = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
            job.jobID = "matrix-fake"
            job.modelID = "melix-dev-text"
            job.taskKind = "text-generation"
            job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
            job.suiteIds = ["smoke"]
            job.benchmarkMode = "matrix"
            job.status = "completed"
            job.outputDir = "/tmp/melix-fake/bench/matrix-runs/matrix-fake"
            job.createdAtUnixMs = 1_712_000_000_000
            job.updatedAtUnixMs = 1_712_000_001_000
            return job
        }(),
        summaryRows: {
            var row = Melix_Controlplane_V1_BenchmarkMatrixSummaryRow()
            row.jobID = "matrix-fake"
            row.taskKind = "text-generation"
            row.sourceRepo = "HuggingFaceH4/ultrachat_200k"
            row.modelID = "melix-dev-text"
            row.suiteID = "smoke"
            row.contextLength = 1024
            row.generationLength = 128
            row.batchSize = 2
            row.cacheProfile = "cold"
            row.reasoningMode = "enabled"
            row.structuredOutputMode = "json_schema"
            row.concurrencyLevel = 1
            row.repeats = 3
            row.requests = 8
            row.ttftMeanMs = 24.4
            row.ttftStdMs = 1.2
            row.requestLatencyMeanMs = 33.8
            row.requestLatencyStdMs = 1.1
            row.prefillTokensPerSecondMean = 310.0
            row.decodeTokensPerSecondMean = 62.0
            row.throughputRequestsPerSecond = 4.8
            row.throughputTokensPerSecond = 256.0
            row.successRate = 1
            row.peakMemoryBytesMax = 2_048_000_000
            row.queueWaitMeanMs = 2.3
            row.queueWaitP95Ms = 3.1
            row.createdAtUnixMs = 1_712_000_000_000
            return [row]
        }()
    )
    private var evaluationResponse = ControlPlaneEvaluationResult(
        job: {
            var job = Melix_Controlplane_V1_EvaluationJobSummary()
            job.jobID = "eval-fake"
            job.modelID = "melix-dev-text"
            job.taskKind = "text-generation"
            job.sourceRepo = "cais/mmlu"
            job.suiteID = "mmlu"
            job.datasetID = "mmlu.dev.v1"
            job.sampleSize = 8
            job.scoringMode = "multiple_choice_accuracy"
            job.status = "completed"
            job.outputDir = "/tmp/melix-fake/evaluation/runs/eval-fake"
            job.createdAtUnixMs = 1_712_000_000_000
            job.updatedAtUnixMs = 1_712_000_001_000
            return job
        }(),
        results: []
    )
    private var exportResult = ControlPlaneExportResult(
        exportBundleJSON: #"{"export_schema_version":"melix.benchmark_export.v1","benchmark_jobs":[],"benchmark_results":[]}"#
    )
    private var chatEvents = FakeControlPlaneXPCClient.defaultChatEvents()
    private var scheduledChatEvents: [ScheduledChatEvent]?
    private var imageGenerateResponse = makeMenuBarImageJobSummary(
        jobID: "image-generate-1::image-generate",
        requestID: "image-generate-1",
        modelID: "melix-dev-image",
        operation: "image_generate"
    )
    private var imageEditResponse = makeMenuBarImageJobSummary(
        jobID: "image-edit-1::image-edit",
        requestID: "image-edit-1",
        modelID: "melix-dev-image",
        operation: "image_edit"
    )

    init() {}

    func configureErrors(
        handshake: Error? = nil,
        load: Error? = nil,
        unload: Error? = nil,
        snapshot: Error? = nil,
        modelSettings: Error? = nil,
        modelInfo: Error? = nil,
        modelOperation: Error? = nil,
        doctor: Error? = nil,
        bench: Error? = nil,
        benchMatrix: Error? = nil,
        evaluation: Error? = nil,
        exportResults: Error? = nil,
        chat: Error? = nil,
        imageGenerate: Error? = nil,
        imageEdit: Error? = nil,
        cancel: Error? = nil,
        applyGatewayAccess: Error? = nil,
        applyGatewayConfig: Error? = nil,
        applyServingDefaults: Error? = nil,
        startServer: Error? = nil,
        pauseServer: Error? = nil,
        resumeServer: Error? = nil,
        wakeServer: Error? = nil,
        stopServer: Error? = nil,
        updateServerIdlePolicy: Error? = nil
    ) {
        handshakeError = handshake
        loadError = load
        unloadError = unload
        snapshotError = snapshot
        modelSettingsError = modelSettings
        modelInfoError = modelInfo
        modelOperationError = modelOperation
        doctorError = doctor
        benchError = bench
        benchMatrixError = benchMatrix
        evaluationError = evaluation
        exportError = exportResults
        chatError = chat
        imageGenerateError = imageGenerate
        imageEditError = imageEdit
        cancelError = cancel
        applyGatewayAccessError = applyGatewayAccess
        applyGatewayConfigError = applyGatewayConfig
        applyServingDefaultsError = applyServingDefaults
        startServerError = startServer
        pauseServerError = pauseServer
        resumeServerError = resumeServer
        wakeServerError = wakeServer
        stopServerError = stopServer
        updateServerIdlePolicyError = updateServerIdlePolicy
    }

    func configureModelResponseFeatures(_ features: [String]) {
        responseFeatures = features
    }

    func configureModelInfo(_ info: Melix_Controlplane_V1_ModelInfo) {
        modelInfoResponse = info
    }

    func configureModelOperation(_ operation: Melix_Controlplane_V1_ModelOperationResult) {
        modelOperationResponse = operation
    }

    func configureModelOperationError(_ error: Error?) {
        modelOperationError = error
    }

    func configureModelOperationError(
        _ error: Error?,
        forNamedOperation operationName: String
    ) {
        if let error {
            modelOperationErrorsByName[operationName] = error
        } else {
            modelOperationErrorsByName.removeValue(forKey: operationName)
        }
    }

    func configureModelOperationDelay(_ delay: Duration) {
        modelOperationDelay = delay
    }

    func configureModelOperation(
        _ operation: Melix_Controlplane_V1_ModelOperationResult,
        forNamedOperation operationName: String
    ) {
        modelOperationResponsesByName[operationName] = operation
    }

    static func defaultDoctorReport() -> Melix_Controlplane_V1_DoctorReport {
        var report = Melix_Controlplane_V1_DoctorReport()
        report.markdown = "# Melix Doctor\n\n- worker_state: idle\n"
        report.healthStatus = .healthy
        return report
    }

    func configureDoctorResponse(
        _ markdown: String,
        healthStatus: Melix_Controlplane_V1_DoctorHealthStatus = .healthy,
        findings: [Melix_Controlplane_V1_DoctorFinding] = []
    ) {
        doctorResponse.markdown = markdown
        doctorResponse.healthStatus = healthStatus
        doctorResponse.findings = findings
    }

    func configureHubSearchResult(_ result: Melix_Controlplane_V1_HubSearchResult) {
        hubSearchResult = result
    }

    func configureHubModelCard(_ card: Melix_Controlplane_V1_HubModelCard) {
        hubModelCard = card
    }

    func configureBenchResponse(_ result: ControlPlaneBenchResult) {
        benchResponse = result
    }

    func configureBenchMatrixResponse(_ result: ControlPlaneBenchMatrixResult) {
        benchMatrixResponse = result
    }

    func configureEvaluationResponse(_ result: ControlPlaneEvaluationResult) {
        evaluationResponse = result
    }

    func configureExportResult(_ result: ControlPlaneExportResult) {
        exportResult = result
    }

    func configureChatEvents(_ events: [ControlPlaneChatStreamEvent]) {
        chatEvents = events
        scheduledChatEvents = nil
    }

    func configureScheduledChatEvents(_ events: [ScheduledChatEvent]) {
        scheduledChatEvents = events
    }

    func configureImageResponses(
        generation: Melix_Controlplane_V1_ImageJobSummary? = nil,
        edit: Melix_Controlplane_V1_ImageJobSummary? = nil
    ) {
        if let generation {
            imageGenerateResponse = generation
        }
        if let edit {
            imageEditResponse = edit
        }
    }

    func configureGatewayAccessClearError(_ error: Error?) {
        clearGatewayAccessError = error
    }

    func configureGatewayConfigApplyError(_ error: Error?) {
        applyGatewayConfigError = error
    }

    func configureServingDefaultsApplyError(_ error: Error?) {
        applyServingDefaultsError = error
    }

    func configureImageDefaultsApplyError(_ error: Error?) {
        applyImageDefaultsError = error
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        handshakeCount += 1
        if let handshakeError {
            throw handshakeError
        }

        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "daemon-1"
        response.features = ["xpc", "models", "metrics", "cache-metadata", "session-graph", "image-jobs"]
        response.snapshot = makeSnapshot(state: modelState)
        return response
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        subscriptionRequests.append(lastSeenSeq)
        return AsyncStream { continuation in
            streamContinuations.append(continuation)
        }
    }

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        recordedActions.append("chat:\(request.modelID)")
        if let chatError {
            throw chatError
        }
        let events = chatEvents
        let scheduledEvents = scheduledChatEvents
        return ControlPlaneChatExecution(
            requestID: "chat-request-1",
            modelID: request.modelID,
            stream: AsyncThrowingStream { continuation in
                Task {
                    if let scheduledEvents {
                        for scheduled in scheduledEvents {
                            if scheduled.delay > .zero {
                                try? await Task.sleep(for: scheduled.delay)
                            }
                            continuation.yield(scheduled.event)
                        }
                    } else {
                        for event in events {
                            continuation.yield(event)
                        }
                    }
                    continuation.finish()
                }
            }
        )
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        recordedActions.append("snapshot")
        if let snapshotError {
            throw snapshotError
        }
        return makeSnapshot(state: modelState)
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await loadModel(modelID: modelID, memoryBudgetBytes: 0)
    }

    func loadModel(
        modelID: String,
        memoryBudgetBytes: UInt64
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("load:\(modelID)")
        lastLoadMemoryBudgetBytes = memoryBudgetBytes
        if let loadError {
            throw loadError
        }

        modelState = .modelWarm
        return makeModelSummary(state: modelState)
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("unload:\(modelID)")
        if let unloadError {
            throw unloadError
        }

        modelState = .modelUnloaded
        return makeModelSummary(state: modelState)
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("settings:\(modelID)")
        recordedModelSettingsUpdates.append(
            RecordedModelSettingsUpdate(modelID: modelID, values: values)
        )
        if let modelSettingsError {
            throw modelSettingsError
        }
        if let alias = values["alias"] {
            modelSettings.alias = alias
        }
        if let typeOverride = values["type_override"] {
            modelSettings.typeOverride = typeOverride
        }
        if let ttl = values["ttl_seconds"] {
            if ttl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                modelSettings.ttlSeconds = 0
            } else if let ttlSeconds = UInt32(ttl) {
                modelSettings.ttlSeconds = ttlSeconds
            }
        }
        if let pinOnLoad = values["pin_on_load"] {
            modelSettings.pinOnLoad = ["1", "true", "yes", "on"].contains(pinOnLoad.lowercased())
        }
        if let memoryPolicy = values["memory_policy"] {
            modelSettings.memoryPolicy = switch memoryPolicy.lowercased() {
            case "pinned": .memoryResidencyPinned
            case "ttl": .memoryResidencyTtl
            default: .memoryResidencyEvictable
            }
        }
        if let memoryBudgetBytes = values["memory_budget_bytes"] {
            if memoryBudgetBytes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                modelSettings.memoryBudgetBytes = 0
            } else {
                modelSettings.memoryBudgetBytes = UInt64(memoryBudgetBytes) ?? 0
            }
        }
        if let diskStreamingMode = values["disk_streaming_mode"] {
            modelSettings.diskStreamingMode = switch diskStreamingMode.lowercased() {
            case "prefer_disk": .diskStreamingPreferDisk
            case "require_disk": .diskStreamingRequireDisk
            default: .diskStreamingDisabled
            }
        }
        if let cacheMode = values["cache_mode"] {
            modelSettings.cacheMode = switch cacheMode.lowercased() {
            case "rotating":
                .rotating
            case "hybrid":
                .hybrid
            case "tiered", "default":
                .tiered
            default:
                .unspecified
            }
        }
        if let cacheMemoryBudgetBytes = values["cache_memory_budget_bytes"] {
            if cacheMemoryBudgetBytes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                modelSettings.cacheMemoryBudgetBytes = 0
            } else {
                modelSettings.cacheMemoryBudgetBytes = UInt64(cacheMemoryBudgetBytes) ?? 0
            }
        }
        if let cacheMemoryBudgetPct = values["cache_memory_budget_pct"] {
            if cacheMemoryBudgetPct.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                modelSettings.cacheMemoryBudgetPct = 0
            } else {
                modelSettings.cacheMemoryBudgetPct = UInt32(cacheMemoryBudgetPct) ?? 0
            }
        }
        if let cacheBlockSizeTokens = values["cache_block_size_tokens"] {
            if cacheBlockSizeTokens.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                modelSettings.cacheBlockSizeTokens = 0
            } else {
                modelSettings.cacheBlockSizeTokens = UInt32(cacheBlockSizeTokens) ?? 0
            }
        }
        if let cacheDirectory = values["cache_directory"] {
            modelSettings.cacheDirectory = cacheDirectory
        }
        if let multimodalCacheBudgetBytes = values["multimodal_cache_budget_bytes"] {
            if multimodalCacheBudgetBytes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                modelSettings.multimodalCacheBudgetBytes = 0
            } else {
                modelSettings.multimodalCacheBudgetBytes = UInt64(multimodalCacheBudgetBytes) ?? 0
            }
        }
        if let accelerationMode = values["default_acceleration_mode"] {
            modelSettings.defaultAccelerationMode = switch accelerationMode.lowercased() {
            case "speculative_decode": .speculativeDecode
            case "accelerated_prefill": .acceleratedPrefill
            case "sparse_prefill": .sparsePrefill
            case "active_kv_quantized": .activeKvQuantized
            default: .baseline
            }
        }
        if let profileID = values["acceleration_profile_id"] {
            modelSettings.accelerationProfileID = profileID
        }
        if let adaptiveThinkingMode = values["adaptive_thinking_mode"] {
            modelSettings.adaptiveThinking.mode = adaptiveThinkingMode
        }
        if let budget = values["adaptive_thinking_budget_tokens"] {
            modelSettings.adaptiveThinking.budgetTokens = UInt32(budget) ?? 0
        }
        if let toolParserXMLFallback = values["tool_parser_xml_fallback"] {
            modelSettings.ext["tool_parser_xml_fallback"] = toolParserXMLFallback
        }
        if let loadTrustMode = values["load_trust_mode"] ?? values["model_load_trust_mode"] {
            let normalizedLoadTrustMode = loadTrustMode
                .trimmingCharacters(in: .whitespacesAndNewlines)
                .lowercased()
                .replacingOccurrences(of: "-", with: "_")
                .replacingOccurrences(of: " ", with: "_")
            modelSettings.loadTrustMode = switch normalizedLoadTrustMode {
            case "", "clear", "unset", "unspecified", "default":
                .unspecified
            case "safe", "default_safe", "false", "0", "no", "off":
                .modelLoadTrustDefaultSafe
            case "trust_remote_code", "remote_code", "trusted", "true", "1", "yes", "on":
                .modelLoadTrustTrustRemoteCode
            case "not_applicable", "n/a", "na":
                .modelLoadTrustNotApplicable
            default:
                .unspecified
            }
        }
        if let ocrSamplingProfileID = values["ocr_sampling_profile_id"] {
            modelSettings.ext["ocr_sampling_profile_id"] = ocrSamplingProfileID
        }
        if let ocrDefaultTemperature = values["ocr_default_temperature"] {
            modelSettings.ext["ocr_default_temperature"] = ocrDefaultTemperature
        }
        if let ocrDefaultTopP = values["ocr_default_top_p"] {
            modelSettings.ext["ocr_default_top_p"] = ocrDefaultTopP
        }
        if let ocrDefaultMaxTokens = values["ocr_default_max_tokens"] {
            modelSettings.ext["ocr_default_max_tokens"] = ocrDefaultMaxTokens
        }
        if var snapshot = snapshotOverride,
           let modelIndex = snapshot.models.firstIndex(where: { $0.modelID == modelID }) {
            snapshot.models[modelIndex].settings = modelSettings
            snapshot.models[modelIndex].cachePolicy.requestedMode = modelSettings.cacheMode
            snapshot.models[modelIndex].cachePolicy.requestedDirectory = modelSettings.cacheDirectory
            snapshot.models[modelIndex].cachePolicy.requestedBlockSizeTokens = modelSettings.cacheBlockSizeTokens
            snapshot.models[modelIndex].cachePolicy.requestedCacheMemoryBudgetBytes = modelSettings.cacheMemoryBudgetBytes
            snapshot.models[modelIndex].cachePolicy.requestedCacheMemoryBudgetPct = modelSettings.cacheMemoryBudgetPct
            snapshot.models[modelIndex].cachePolicy.requestedMultimodalCacheBudgetBytes = modelSettings.multimodalCacheBudgetBytes
            if snapshot.models[modelIndex].cachePolicy.effectiveMode == .unspecified {
                snapshot.models[modelIndex].cachePolicy.effectiveMode = modelSettings.cacheMode == .unspecified
                    ? .tiered
                    : modelSettings.cacheMode
            }
            if snapshot.models[modelIndex].cachePolicy.effectiveDirectory.isEmpty {
                snapshot.models[modelIndex].cachePolicy.effectiveDirectory = modelSettings.cacheDirectory
            }
            if snapshot.models[modelIndex].cachePolicy.effectiveBlockSizeTokens == 0 {
                snapshot.models[modelIndex].cachePolicy.effectiveBlockSizeTokens = modelSettings.cacheBlockSizeTokens
            }
            if snapshot.models[modelIndex].cachePolicy.effectiveCacheMemoryBudgetBytes == 0 {
                snapshot.models[modelIndex].cachePolicy.effectiveCacheMemoryBudgetBytes = modelSettings.cacheMemoryBudgetBytes
            }
            if snapshot.models[modelIndex].cachePolicy.effectiveCacheMemoryBudgetPct == 0 {
                snapshot.models[modelIndex].cachePolicy.effectiveCacheMemoryBudgetPct = modelSettings.cacheMemoryBudgetPct
            }
            if snapshot.models[modelIndex].cachePolicy.effectiveMultimodalCacheBudgetBytes == 0 {
                snapshot.models[modelIndex].cachePolicy.effectiveMultimodalCacheBudgetBytes = modelSettings.multimodalCacheBudgetBytes
            }
            snapshotOverride = snapshot
            return snapshot.models[modelIndex]
        }
        return makeModelSummary(state: modelState)
    }

    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        recordedActions.append("info:\(modelID)")
        if let modelInfoError {
            throw modelInfoError
        }
        return modelInfoResponse
    }

    func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        recordedActions.append("operation:\(operation):\(modelID)")
        recordedModelOperationRequests.append(
            RecordedModelOperationRequest(
                modelID: modelID,
                operation: operation,
                outputDir: outputDir,
                quantProfileID: quantProfileID,
                weightQuant: weightQuant,
                kvQuant: kvQuant,
                ext: ext
            )
        )
        if modelOperationDelay > .zero {
            try? await Task.sleep(for: modelOperationDelay)
        }
        if let namedError = modelOperationErrorsByName[operation] {
            throw namedError
        }
        if let modelOperationError {
            throw modelOperationError
        }
        let hasNamedOverride = modelOperationResponsesByName[operation] != nil
        var response = modelOperationResponsesByName[operation] ?? modelOperationResponse
        response.operation = operation
        if !hasNamedOverride, !outputDir.isEmpty {
            response.outputPath = outputDir + "/" + operation + ".artifact"
        }
        if !quantProfileID.isEmpty, !response.hasQuantProfile {
            response.quantProfile = Melix_Controlplane_V1_QuantizationProfile()
            response.quantProfile.algorithm = "oq"
            response.quantProfile.schemaVersion = "melix.quant_profile.v1"
            response.quantProfile.quantProfileID = quantProfileID
            response.quantProfile.weightQuant = quantProfileID
            response.quantProfile.kvQuant = kvQuant
        }
        if !weightQuant.isEmpty || !kvQuant.isEmpty || !ext.isEmpty || !quantProfileID.isEmpty {
            response.stage = response.stage.isEmpty ? "write_artifact" : response.stage
        }
        return response
    }

    func generateImage(
        _ request: ControlPlaneImageGenerationRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        recordedActions.append("image.generate:\(request.modelID)")
        if let imageGenerateError {
            throw imageGenerateError
        }
        recordedImageGenerateRequests.append(
            RecordedImageGenerateRequest(
                modelID: request.modelID,
                prompt: request.prompt,
                size: request.size,
                steps: request.steps,
                guidance: request.guidance,
                negativePrompt: request.negativePrompt,
                n: request.n,
                responseFormat: request.responseFormat,
                artifactNamespace: request.artifactNamespace
            )
        )
        var response = imageGenerateResponse
        response.modelID = request.modelID
        if response.requestID.isEmpty {
            response.requestID = "image-generate-1"
        }
        return response
    }

    func editImage(
        _ request: ControlPlaneImageEditRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        recordedActions.append("image.edit:\(request.modelID)")
        if let imageEditError {
            throw imageEditError
        }
        recordedImageEditRequests.append(
            RecordedImageEditRequest(
                modelID: request.modelID,
                prompt: request.prompt,
                imageURL: request.imageURL,
                maskURL: request.maskURL,
                sourceArtifactID: request.sourceArtifactID,
                promptDelta: request.promptDelta,
                mode: request.mode,
                strength: request.strength,
                size: request.size,
                steps: request.steps,
                guidance: request.guidance,
                negativePrompt: request.negativePrompt,
                n: request.n,
                responseFormat: request.responseFormat
            )
        )
        var response = imageEditResponse
        response.modelID = request.modelID
        if response.requestID.isEmpty {
            response.requestID = "image-edit-1"
        }
        return response
    }

    func applyImageDefaults(
        _ request: ControlPlaneImageDefaultsRequest
    ) async throws -> Melix_Controlplane_V1_ImageDefaultsSummary {
        recordedActions.append("image.defaults.apply")
        if let applyImageDefaultsError {
            throw applyImageDefaultsError
        }
        recordedImageDefaultsApplyRequests.append(
            RecordedImageDefaultsApplyRequest(
                generateModelID: request.generateModelID,
                editModelID: request.editModelID,
                size: request.size,
                steps: request.steps,
                guidance: request.guidance,
                strength: request.strength,
                negativePrompt: request.negativePrompt
            )
        )

        var summary = Melix_Controlplane_V1_ImageDefaultsSummary()
        summary.requestedGenerateModelID = request.generateModelID
        summary.requestedEditModelID = request.editModelID
        summary.requestedSize = request.size
        summary.requestedSteps = request.steps
        summary.requestedGuidance = request.guidance
        summary.requestedStrength = request.strength
        summary.requestedNegativePrompt = request.negativePrompt
        summary.effectiveGenerateModelID = request.generateModelID
        summary.effectiveEditModelID = request.editModelID
        summary.effectiveSize = request.size
        summary.effectiveSteps = request.steps
        summary.effectiveGuidance = request.guidance
        summary.effectiveStrength = request.strength
        summary.effectiveNegativePrompt = request.negativePrompt
        summary.source = .operatorOverride
        summary.updatedAtUnixMs = 1_717_171_717_000

        var snapshot = snapshotOverride ?? makeSnapshot(state: modelState)
        snapshot.imageDefaults = summary
        snapshotOverride = snapshot
        return summary
    }

    func cancelRequest(requestID: String) async throws -> Bool {
        recordedActions.append("cancel:\(requestID)")
        if let cancelError {
            throw cancelError
        }
        return true
    }

    func applyServerSessionGatewayAccess(
        serverSessionID: String,
        primaryKey: String,
        keyID: String,
        label: String,
        tokenHint: String
    ) async throws {
        recordedActions.append("gateway.apply:\(serverSessionID)")
        if let applyGatewayAccessError {
            throw applyGatewayAccessError
        }
        recordedGatewayAccessApplyRequests.append(
            RecordedGatewayAccessApplyRequest(
                serverSessionID: serverSessionID,
                primaryKey: primaryKey,
                keyID: keyID,
                label: label,
                tokenHint: tokenHint
            )
        )
    }

    func clearServerSessionGatewayAccess(serverSessionID: String) async throws {
        recordedActions.append("gateway.clear:\(serverSessionID)")
        if let clearGatewayAccessError {
            throw clearGatewayAccessError
        }
        recordedGatewayAccessClearRequests.append(serverSessionID)
    }

    func applyServerSessionGatewayConfig(
        serverSessionID: String,
        host: String,
        port: Int,
        defaultModelID: String,
        servedModelIDs: [String],
        rateLimitPerMinute: Int,
        timeoutSeconds: Int,
        modelIdleTimeoutSeconds: Int
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        recordedActions.append("gateway.config:\(serverSessionID)")
        if let applyGatewayConfigError {
            throw applyGatewayConfigError
        }
        let normalizedServedModelIDs = servedModelIDs.isEmpty ? [defaultModelID] : servedModelIDs
        recordedGatewayConfigApplyRequests.append(
            RecordedGatewayConfigApplyRequest(
                serverSessionID: serverSessionID,
                host: host,
                port: port,
                defaultModelID: defaultModelID,
                servedModelIDs: normalizedServedModelIDs,
                rateLimitPerMinute: rateLimitPerMinute,
                timeoutSeconds: timeoutSeconds,
                modelIdleTimeoutSeconds: modelIdleTimeoutSeconds
            )
        )

        var snapshot = makeSnapshot(state: modelState)
        var config = snapshot.gatewayConfig
        if let existingIndex = config.listeners.firstIndex(where: { $0.serverSessionID == serverSessionID }) {
            config.listeners[existingIndex].requestedHost = host
            config.listeners[existingIndex].requestedPort = UInt32(max(1, port))
            config.listeners[existingIndex].effectiveHost = host
            config.listeners[existingIndex].effectivePort = UInt32(max(1, port))
            config.listeners[existingIndex].defaultModelID = defaultModelID
            config.listeners[existingIndex].servedModelIds = normalizedServedModelIDs
            config.listeners[existingIndex].rateLimitPerMinute = UInt32(max(1, rateLimitPerMinute))
            config.listeners[existingIndex].timeoutSeconds = UInt32(max(1, timeoutSeconds))
            config.listeners[existingIndex].modelIdleTimeoutSeconds = UInt32(max(0, modelIdleTimeoutSeconds))
            config.listeners[existingIndex].source = .operatorOverride
            config.listeners[existingIndex].activeBinding = true
            config.listeners[existingIndex].requiresRestart = false
        } else {
            var listener = Melix_Controlplane_V1_GatewayListenerConfigSummary()
            listener.serverSessionID = serverSessionID
            listener.requestedHost = host
            listener.requestedPort = UInt32(max(1, port))
            listener.effectiveHost = host
            listener.effectivePort = UInt32(max(1, port))
            listener.defaultModelID = defaultModelID
            listener.servedModelIds = normalizedServedModelIDs
            listener.rateLimitPerMinute = UInt32(max(1, rateLimitPerMinute))
            listener.timeoutSeconds = UInt32(max(1, timeoutSeconds))
            listener.modelIdleTimeoutSeconds = UInt32(max(0, modelIdleTimeoutSeconds))
            listener.source = .operatorOverride
            listener.activeBinding = true
            listener.requiresRestart = false
            config.listeners.append(listener)
        }
        snapshot.gatewayConfig = config
        snapshotOverride = snapshot
        return snapshot
    }

    func applyServerSessionServingDefaults(
        serverSessionID: String,
        temperature: Double,
        topP: Double,
        maxTokens: Int,
        streamIntervalTokens: Int,
        maxConcurrentRequests: Int,
        concurrentProcessingEnabled: Bool,
        prefillBatchSize: Int,
        completionBatchSize: Int,
        accelerationMode: Melix_Controlplane_V1_AccelerationMode,
        draftModelID: String,
        numDraftTokens: Int,
        accelerationProfile: String
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        recordedActions.append("serving-defaults.apply:\(serverSessionID)")
        if let applyServingDefaultsError {
            throw applyServingDefaultsError
        }
        recordedServingDefaultsApplyRequests.append(
            RecordedServingDefaultsApplyRequest(
                serverSessionID: serverSessionID,
                temperature: temperature,
                topP: topP,
                maxTokens: maxTokens,
                streamIntervalTokens: streamIntervalTokens,
                maxConcurrentRequests: maxConcurrentRequests,
                concurrentProcessingEnabled: concurrentProcessingEnabled,
                prefillBatchSize: prefillBatchSize,
                completionBatchSize: completionBatchSize,
                accelerationMode: accelerationMode,
                draftModelID: draftModelID,
                numDraftTokens: numDraftTokens,
                accelerationProfile: accelerationProfile
            )
        )

        let normalizedMaxConcurrentRequests = UInt32(max(1, maxConcurrentRequests))
        let normalizedPrefillBatchSize = UInt32(max(1, prefillBatchSize))
        let normalizedCompletionBatchSize = UInt32(max(1, completionBatchSize))
        let effectiveBatchCapacity: UInt32 = concurrentProcessingEnabled
            ? min(normalizedMaxConcurrentRequests, normalizedPrefillBatchSize, normalizedCompletionBatchSize)
            : 1
        let effectiveConcurrentProcessingEnabled = concurrentProcessingEnabled && effectiveBatchCapacity > 1

        var snapshot = snapshotOverride ?? makeSnapshot(state: modelState)
        var summary = snapshot.servingDefaults
        if let existingIndex = summary.sessions.firstIndex(where: { $0.serverSessionID == serverSessionID }) {
            summary.sessions[existingIndex].requestedTemperature = temperature
            summary.sessions[existingIndex].requestedTopP = topP
            summary.sessions[existingIndex].requestedMaxTokens = UInt32(max(1, maxTokens))
            summary.sessions[existingIndex].requestedStreamIntervalTokens = UInt32(max(1, streamIntervalTokens))
            summary.sessions[existingIndex].requestedMaxConcurrentRequests = UInt32(max(1, maxConcurrentRequests))
            summary.sessions[existingIndex].requestedConcurrentProcessingEnabled = concurrentProcessingEnabled
            summary.sessions[existingIndex].requestedPrefillBatchSize = UInt32(max(1, prefillBatchSize))
            summary.sessions[existingIndex].requestedCompletionBatchSize = UInt32(max(1, completionBatchSize))
            summary.sessions[existingIndex].requestedAccelerationMode = accelerationMode
            summary.sessions[existingIndex].requestedDraftModelID = draftModelID
            summary.sessions[existingIndex].requestedNumDraftTokens = UInt32(max(0, numDraftTokens))
            summary.sessions[existingIndex].effectiveTemperature = temperature
            summary.sessions[existingIndex].effectiveTopP = topP
            summary.sessions[existingIndex].effectiveMaxTokens = UInt32(max(1, maxTokens))
            summary.sessions[existingIndex].effectiveStreamIntervalTokens = UInt32(max(1, streamIntervalTokens))
            summary.sessions[existingIndex].effectiveMaxConcurrentRequests = effectiveConcurrentProcessingEnabled ? effectiveBatchCapacity : 1
            summary.sessions[existingIndex].effectiveConcurrentProcessingEnabled = effectiveConcurrentProcessingEnabled
            summary.sessions[existingIndex].effectivePrefillBatchSize = effectiveConcurrentProcessingEnabled ? effectiveBatchCapacity : 1
            summary.sessions[existingIndex].effectiveCompletionBatchSize = effectiveConcurrentProcessingEnabled ? effectiveBatchCapacity : 1
            summary.sessions[existingIndex].effectiveAccelerationMode = accelerationMode
            summary.sessions[existingIndex].effectiveDraftModelID = accelerationMode == .speculativeDecode ? draftModelID : ""
            summary.sessions[existingIndex].effectiveNumDraftTokens = accelerationMode == .speculativeDecode ? UInt32(max(0, numDraftTokens)) : 0
            summary.sessions[existingIndex].source = .operatorOverride
            summary.sessions[existingIndex].modelOverrideApplied = false
        } else {
            var session = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
            session.serverSessionID = serverSessionID
            session.defaultModelID = snapshot.gatewayConfig.listeners.first(where: { $0.serverSessionID == serverSessionID })?.defaultModelID ?? "melix-dev-text"
            session.requestedTemperature = temperature
            session.requestedTopP = topP
            session.requestedMaxTokens = UInt32(max(1, maxTokens))
            session.requestedStreamIntervalTokens = UInt32(max(1, streamIntervalTokens))
            session.requestedMaxConcurrentRequests = UInt32(max(1, maxConcurrentRequests))
            session.requestedConcurrentProcessingEnabled = concurrentProcessingEnabled
            session.requestedPrefillBatchSize = UInt32(max(1, prefillBatchSize))
            session.requestedCompletionBatchSize = UInt32(max(1, completionBatchSize))
            session.requestedAccelerationMode = accelerationMode
            session.requestedDraftModelID = draftModelID
            session.requestedNumDraftTokens = UInt32(max(0, numDraftTokens))
            session.effectiveTemperature = temperature
            session.effectiveTopP = topP
            session.effectiveMaxTokens = UInt32(max(1, maxTokens))
            session.effectiveStreamIntervalTokens = UInt32(max(1, streamIntervalTokens))
            session.effectiveMaxConcurrentRequests = effectiveConcurrentProcessingEnabled ? effectiveBatchCapacity : 1
            session.effectiveConcurrentProcessingEnabled = effectiveConcurrentProcessingEnabled
            session.effectivePrefillBatchSize = effectiveConcurrentProcessingEnabled ? effectiveBatchCapacity : 1
            session.effectiveCompletionBatchSize = effectiveConcurrentProcessingEnabled ? effectiveBatchCapacity : 1
            session.effectiveAccelerationMode = accelerationMode
            session.effectiveDraftModelID = accelerationMode == .speculativeDecode ? draftModelID : ""
            session.effectiveNumDraftTokens = accelerationMode == .speculativeDecode ? UInt32(max(0, numDraftTokens)) : 0
            session.source = .operatorOverride
            summary.sessions.append(session)
        }
        snapshot.servingDefaults = summary
        snapshotOverride = snapshot
        return snapshot
    }

    func startServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        recordedActions.append("server.start:\(serverSessionID)")
        if let startServerError {
            throw startServerError
        }
        return mutateRuntimeSession(serverSessionID: serverSessionID) { runtimeSession in
            runtimeSession.lifecycleState = .ready
            runtimeSession.powerState = .active
            runtimeSession.wakeReason = .initialBoot
        }
    }

    func pauseServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        recordedActions.append("server.pause:\(serverSessionID)")
        if let pauseServerError {
            throw pauseServerError
        }
        return mutateRuntimeSession(serverSessionID: serverSessionID) { runtimeSession in
            runtimeSession.lifecycleState = .paused
            runtimeSession.powerState = .active
            runtimeSession.wakeReason = .policyApply
        }
    }

    func resumeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        recordedActions.append("server.resume:\(serverSessionID)")
        if let resumeServerError {
            throw resumeServerError
        }
        return mutateRuntimeSession(serverSessionID: serverSessionID) { runtimeSession in
            runtimeSession.lifecycleState = .ready
            runtimeSession.powerState = .active
            runtimeSession.wakeReason = .operatorResume
        }
    }

    func wakeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        recordedActions.append("server.wake:\(serverSessionID)")
        if let wakeServerError {
            throw wakeServerError
        }
        return mutateRuntimeSession(serverSessionID: serverSessionID) { runtimeSession in
            runtimeSession.lifecycleState = .ready
            runtimeSession.powerState = .active
            runtimeSession.wakeReason = .operatorResume
        }
    }

    func stopServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        recordedActions.append("server.stop:\(serverSessionID)")
        if let stopServerError {
            throw stopServerError
        }
        return mutateRuntimeSession(serverSessionID: serverSessionID) { runtimeSession in
            runtimeSession.lifecycleState = .stopped
            runtimeSession.powerState = .stopped
            runtimeSession.wakeReason = .policyApply
        }
    }

    func updateServerIdlePolicy(
        serverSessionID: String,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        recordedActions.append("server.idle_policy:\(serverSessionID)")
        if let updateServerIdlePolicyError {
            throw updateServerIdlePolicyError
        }
        recordedServerIdlePolicyRequests.append(
            RecordedServerIdlePolicyRequest(
                serverSessionID: serverSessionID,
                autoSleepEnabled: autoSleepEnabled,
                lightSleepAfterSeconds: lightSleepAfterSeconds,
                deepSleepAfterSeconds: deepSleepAfterSeconds
            )
        )
        return mutateRuntimeSession(serverSessionID: serverSessionID) { runtimeSession in
            runtimeSession.autoSleepEnabled = autoSleepEnabled
            runtimeSession.lightSleepAfterSeconds = lightSleepAfterSeconds
            runtimeSession.deepSleepAfterSeconds = deepSleepAfterSeconds
        }
    }

    func runDoctor() async throws -> Melix_Controlplane_V1_DoctorReport {
        recordedActions.append("doctor")
        if let doctorError {
            throw doctorError
        }
        return doctorResponse
    }

    func searchHubModels(
        query: String,
        pageSize: UInt32,
        cursor: String,
        mlxOnly: Bool
    ) async throws -> Melix_Controlplane_V1_HubSearchResult {
        recordedActions.append("hub.search:\(query)")
        recordedHubSearchRequests.append(
            RecordedHubSearchRequest(
                query: query,
                pageSize: pageSize,
                cursor: cursor,
                mlxOnly: mlxOnly
            )
        )
        return hubSearchResult
    }

    func getHubModelCard(repoID: String) async throws -> Melix_Controlplane_V1_HubModelCard {
        recordedActions.append("hub.card:\(repoID)")
        recordedHubModelCardRequests.append(.init(repoID: repoID))
        return hubModelCard
    }

    func runBench(_ request: ControlPlaneBenchRequest) async throws -> ControlPlaneBenchResult {
        recordedBenchRequests.append(request)
        recordedActions.append("bench")
        if let benchError {
            throw benchError
        }
        return benchResponse
    }

    func runBenchMatrix(_ request: ControlPlaneBenchMatrixRequest) async throws -> ControlPlaneBenchMatrixResult {
        recordedBenchMatrixRequests.append(request)
        recordedActions.append("bench.matrix")
        if let benchMatrixError {
            throw benchMatrixError
        }
        return benchMatrixResponse
    }

    func runEvaluation(_ request: ControlPlaneEvaluationRequest) async throws -> ControlPlaneEvaluationResult {
        recordedEvaluationRequests.append(request)
        recordedActions.append("eval")
        if let evaluationError {
            throw evaluationError
        }
        return evaluationResponse
    }

    func exportResults(outputDir: String) async throws -> ControlPlaneExportResult {
        recordedExportOutputDirs.append(outputDir)
        recordedActions.append("bench.export")
        if let exportError {
            throw exportError
        }
        return exportResult
    }

    func sendModelStateChanged(state: Melix_Controlplane_V1_ModelState) {
        modelState = state
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "model.state_changed"
        event.modelState = Melix_Controlplane_V1_ModelStateChanged()
        event.modelState.modelID = "melix-dev-text"
        event.modelState.state = state
        emit(event)
    }

    func sendLog(level: String, message: String) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "log"
        event.log = Melix_Controlplane_V1_LogEvent()
        event.log.level = level
        event.log.message = message
        emit(event)
    }

    func sendServerStateChanged(
        state: Melix_Controlplane_V1_ServerState,
        runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState] = []
    ) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "server.state_changed"
        event.serverState = Melix_Controlplane_V1_ServerStateChanged()
        event.serverState.state = state
        event.serverState.runtimeSessions = runtimeSessions
        emit(event)
    }

    func sendSessionStateChanged(
        sessionID: String,
        branchCount: Int = 1,
        latestRequestID: String = "request-1",
        latestSnapshotID: String = "snapshot-1"
    ) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "session.state_changed"
        event.sessionState = Melix_Controlplane_V1_SessionStateChanged()
        event.sessionState.state.sessionID = sessionID
        event.sessionState.state.activeBranchID = "branch-main"
        event.sessionState.state.latestRequestID = latestRequestID
        event.sessionState.state.latestSnapshotID = latestSnapshotID
        event.sessionState.state.branches = (0..<branchCount).map { index in
            var branch = Melix_Controlplane_V1_BranchState()
            branch.branchID = "branch-\(index)"
            return branch
        }
        emit(event)
    }

    func sendCacheStats(l1Bytes: UInt64, l2Bytes: UInt64) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "cache.stats"
        event.cacheStats = Melix_Controlplane_V1_CacheStatsEvent()
        event.cacheStats.summary.l1Bytes = l1Bytes
        event.cacheStats.summary.l2Bytes = l2Bytes
        emit(event)
    }

    func sendResourcePressure(scope: String, usedBytes: UInt64, totalBytes: UInt64) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "resource.pressure"
        event.resourcePressure = Melix_Controlplane_V1_ResourcePressureEvent()
        event.resourcePressure.scope = scope
        event.resourcePressure.resources.memoryUsedBytes = usedBytes
        event.resourcePressure.resources.memoryTotalBytes = totalBytes
        emit(event)
    }

    func sendRequestProgress(
        requestID: String,
        phase: Melix_Controlplane_V1_RequestPhase,
        prefillProcessedTokens: UInt32 = 0,
        prefillTotalTokens: UInt32 = 0,
        activeRequests: UInt32 = 0,
        waitingRequests: UInt32 = 0,
        restoreStage: String = "",
        cachePressure: Double = 0
    ) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "request.progress"
        event.requestProgress = Melix_Controlplane_V1_RequestProgressEvent()
        event.requestProgress.requestID = requestID
        event.requestProgress.phase = phase
        event.requestProgress.prefillProcessedTokens = prefillProcessedTokens
        event.requestProgress.prefillTotalTokens = prefillTotalTokens
        event.requestProgress.prefillProgressPct = prefillTotalTokens == 0
            ? 0
            : Double(prefillProcessedTokens) / Double(prefillTotalTokens) * 100
        event.requestProgress.activeRequests = activeRequests
        event.requestProgress.waitingRequests = waitingRequests
        event.requestProgress.restoreStage = restoreStage
        event.requestProgress.cachePressure = cachePressure
        emit(event)
    }

    func sendBenchmarkProgress(
        jobID: String,
        suite: String,
        pct: Double
    ) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "benchmark.progress"
        event.benchProgress = Melix_Controlplane_V1_BenchmarkProgressEvent()
        event.benchProgress.jobID = jobID
        event.benchProgress.suite = suite
        event.benchProgress.pct = pct
        emit(event)
    }

    func sendHeartbeat() {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "heartbeat"
        event.heartbeat = Melix_Controlplane_V1_Heartbeat()
        emit(event)
    }

    func sendImageJobStateChanged(_ job: Melix_Controlplane_V1_ImageJobSummary) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "image.job.state_changed"
        event.imageJob = Melix_Controlplane_V1_ImageJobStateChanged()
        event.imageJob.job = job
        emit(event)
    }

    func finishLatestSubscription() {
        guard let continuation = streamContinuations.last else {
            return
        }
        continuation.finish()
        streamContinuations.removeLast()
    }

    func configureSnapshot(_ snapshot: Melix_Controlplane_V1_ServerSnapshot?) {
        snapshotOverride = snapshot
        if let model = snapshot?.models.first(where: { $0.modelID == "melix-dev-text" }) ?? snapshot?.models.first {
            modelSettings = model.settings
            responseFeatures = model.features
        }
    }

    func makeSnapshot(state: Melix_Controlplane_V1_ModelState) -> Melix_Controlplane_V1_ServerSnapshot {
        if var snapshotOverride {
            if snapshotOverride.models.isEmpty {
                snapshotOverride.models = [makeModelSummary(state: state)]
            }
            return snapshotOverride
        }

        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeModelSummary(state: state)]
        snapshot.queues = makeQueueSummary()
        snapshot.cache = makeCacheSummary()
        snapshot.metrics = makeMetricsSummary()
        return snapshot
    }

    private func makeModelSummary(
        state: Melix_Controlplane_V1_ModelState
    ) -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-text"
        model.kind = "text"
        model.state = state
        model.features = responseFeatures
        model.maxContext = 8192
        model.settings = modelSettings
        return model
    }

    private func makeQueueSummary() -> Melix_Controlplane_V1_QueueSummary {
        var queue = Melix_Controlplane_V1_QueueSummary()
        queue.queuedRequests = 1
        queue.activeRequests = 1
        queue.backpressure = 0.12

        var decode = Melix_Controlplane_V1_QueueLaneSummary()
        decode.laneID = "text.decode.interactive"
        decode.laneClass = "interactive-decode"
        decode.activeRequests = 1
        decode.priorityScore = 100

        var prefill = Melix_Controlplane_V1_QueueLaneSummary()
        prefill.laneID = "text.prefill.hot"
        prefill.laneClass = "hot-prefill"
        prefill.queuedRequests = 1
        prefill.priorityScore = 120

        queue.lanes = [decode, prefill]
        return queue
    }

    private static func defaultChatEvents() -> [ControlPlaneChatStreamEvent] {
        [
            .queued(lane: "text.decode.interactive", queuePosition: 0, backpressure: 0),
            .admitted(lane: "text.decode.interactive", workerID: "swift-text-worker", queueDelayMs: 0.5),
            .tokenDelta("Assistant response"),
            .reasoningDelta("Reasoning trace"),
            .toolCallDelta(callID: "tool-1", toolName: "search", argumentsFragment: #"{"q":"melix"}"#),
            .usage(promptTokens: 12, completionTokens: 24),
            .completed(finishReason: "stop", assistantText: "Assistant response", reasoningText: "Reasoning trace"),
        ]
    }

    private func makeCacheSummary() -> Melix_Controlplane_V1_CacheSummary {
        var cache = Melix_Controlplane_V1_CacheSummary()
        cache.l1Bytes = 16 * 1024 * 1024
        cache.l2Bytes = 64 * 1024 * 1024
        cache.l1HitRate = 0.72
        cache.l2HitRate = 0.35
        cache.activeMode = .tiered
        cache.cacheRoot = "/tmp/melix-cache"
        cache.initialCacheBlocks = 4
        cache.supportedModes = [.tiered, .rotating, .hybrid]
        cache.experimentalModes = [.rotating, .hybrid]
        cache.supportsPrefixCache = true
        cache.supportsPagedCache = true
        cache.supportsDiskCache = true
        cache.supportsBoundarySnapshots = true
        return cache
    }

    private func makeMetricsSummary() -> Melix_Controlplane_V1_MetricsSummary {
        var metrics = Melix_Controlplane_V1_MetricsSummary()
        metrics.values = [
            "http.translation_ms": 2.4,
            "http.stream_first_event_ms": 18.8,
            "requests.inflight": 1,
        ]
        return metrics
    }

    private func mutateRuntimeSession(
        serverSessionID: String,
        _ update: (inout Melix_Controlplane_V1_ServerSessionRuntimeState) -> Void
    ) -> Melix_Controlplane_V1_ServerSnapshot {
        var snapshot = makeSnapshot(state: modelState)
        let existingIndex = snapshot.runtimeSessions.firstIndex(where: { $0.serverSessionID == serverSessionID })
        if let existingIndex {
            update(&snapshot.runtimeSessions[existingIndex])
        } else {
            var runtimeSession = Melix_Controlplane_V1_ServerSessionRuntimeState()
            runtimeSession.serverSessionID = serverSessionID
            runtimeSession.lifecycleState = .ready
            runtimeSession.powerState = .active
            runtimeSession.wakeReason = .initialBoot
            update(&runtimeSession)
            snapshot.runtimeSessions.append(runtimeSession)
        }
        snapshotOverride = snapshot
        return snapshot
    }

    private static func defaultModelSettings() -> Melix_Controlplane_V1_ModelSettings {
        var settings = Melix_Controlplane_V1_ModelSettings()
        settings.alias = "Melix Text"
        settings.memoryPolicy = .memoryResidencyEvictable
        settings.defaultAccelerationMode = .baseline
        return settings
    }

    private static func defaultModelInfo() -> Melix_Controlplane_V1_ModelInfo {
        var info = Melix_Controlplane_V1_ModelInfo()
        info.ok = true
        info.modelKind = "text"
        info.maxContext = 8192
        info.supportedParsers = ["text", "json"]
        info.supportedModalities = ["text"]
        return info
    }

    private static func defaultModelOperation() -> Melix_Controlplane_V1_ModelOperationResult {
        var result = Melix_Controlplane_V1_ModelOperationResult()
        result.ok = true
        result.jobID = "job-fake"
        result.stage = "write_artifact"
        result.pct = 0.75
        result.manifestJson = #"{"operation":"quantize"}"#
        result.outputPath = "/tmp/melix-fake/quantize.artifact"
        return result
    }

    private func emit(_ event: Melix_Controlplane_V1_ControlPlaneEvent) {
        guard streamContinuations.isEmpty == false else {
            return
        }
        var sequenced = event
        sequenced.seq = nextEventSequence
        nextEventSequence += 1
        streamContinuations[streamContinuations.count - 1].yield(sequenced)
    }
}

struct MenuBarTestError: Error, CustomStringConvertible {
    let description: String
}

func makeMenuBarImageModelSummary(
    modelID: String = "melix-dev-image",
    state: Melix_Controlplane_V1_ModelState = .modelWarm,
    familyID: String = "deterministic-v1",
    supportsGeneration: Bool = true,
    supportsEdit: Bool = true
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = "image"
    model.state = state
    model.features = (supportsGeneration ? ["image_generate"] : [])
        + (supportsEdit ? ["image_edit"] : [])
        + ["artifact_jobs"]
    model.supportedTasks = (supportsGeneration ? ["image_generate"] : [])
        + (supportsEdit ? ["image_edit"] : [])
    model.supportedModalities = ["text", "image"]
    model.maxContext = 0
    model.settings.alias = "Melix Image"
    model.settings.ext["melix.image.family_id"] = familyID
    model.settings.ext["melix.image.supports_generation"] = supportsGeneration ? "true" : "false"
    model.settings.ext["melix.image.supports_edit"] = supportsEdit ? "true" : "false"
    model.settings.ext["melix.image.task_kind"] = supportsEdit && !supportsGeneration
        ? "image-text-to-image"
        : "text-to-image"
    return model
}

func makeMenuBarImageArtifact(
    jobID: String,
    role: Melix_Controlplane_V1_ImageArtifactRole = .imageArtifactGenerated,
    storageURI: String = "/tmp/output.png"
) -> Melix_Controlplane_V1_ImageArtifactRef {
    var artifact = Melix_Controlplane_V1_ImageArtifactRef()
    artifact.artifactID = "\(jobID)::artifact"
    artifact.jobID = jobID
    artifact.role = role
    artifact.mimeType = "image/png"
    artifact.format = "png"
    artifact.width = 512
    artifact.height = 512
    artifact.byteLength = 128
    artifact.storageUri = storageURI
    artifact.sha256 = "sha256-artifact"
    artifact.variantIndex = 0
    return artifact
}

func makeMenuBarImageJobSummary(
    jobID: String,
    requestID: String,
    modelID: String = "melix-dev-image",
    operation: String,
    state: Melix_Controlplane_V1_ImageJobState = .imageJobCompleted,
    artifacts: [Melix_Controlplane_V1_ImageArtifactRef] = [],
    recipe: Melix_Controlplane_V1_ImageJobRecipeSummary = Melix_Controlplane_V1_ImageJobRecipeSummary(),
    timeoutSeconds: UInt32 = 0,
    sourceArtifactID: String = "",
    sourceJobID: String = "",
    promptDelta: String = "",
    editMode: Melix_Controlplane_V1_ImageEditMode = .unspecified,
    error: Melix_Controlplane_V1_ErrorStatus = Melix_Controlplane_V1_ErrorStatus()
) -> Melix_Controlplane_V1_ImageJobSummary {
    var job = Melix_Controlplane_V1_ImageJobSummary()
    job.jobID = jobID
    job.requestID = requestID
    job.modelID = modelID
    job.operation = operation
    job.state = state
    job.lane = operation == "image_edit" ? "image.edit.background" : "image.generate.background"
    job.workerID = "python-image-worker"
    job.progress.stage = state == .imageJobCompleted ? "completed" : "running"
    job.progress.pct = state == .imageJobCompleted ? 1 : 0.5
    job.artifacts = artifacts
    job.recipe = recipe
    job.timeoutSeconds = timeoutSeconds
    job.sourceArtifactID = sourceArtifactID
    job.sourceJobID = sourceJobID
    job.promptDelta = promptDelta
    job.editMode = editMode
    job.error = error
    job.cancelable = state == .imageJobRunning || state == .imageJobQueued
    job.createdAtUnixMs = 1_710_000_000_000
    job.updatedAtUnixMs = 1_710_000_000_500
    return job
}

func makeBenchmarkExportBundleJSON() -> String {
    """
    {
      "export_schema_version": "melix.benchmark_export.v1",
      "exported_at_unix_ms": 1712201234567,
      "benchmark_jobs": [
        {
          "schema_version": "melix.serving_benchmark_job.v1",
          "job_id": "bench-older",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suites": ["smoke"],
          "parameters": {
            "sample_size": "2",
            "batch_factor": "1",
            "acceleration_profile": "balanced"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/bench/runs/bench-older",
          "created_at_unix_ms": 1712100000000,
          "updated_at_unix_ms": 1712100004000,
          "suite_metadata": {
            "smoke": {
              "title": "UltraChat Smoke",
              "dataset_path": "HuggingFaceH4/ultrachat_200k",
              "dataset_name": "default",
              "dataset_split": "train_sft",
              "sample_size": 2,
              "batch_factor": 1
            }
          }
        },
        {
          "schema_version": "melix.serving_benchmark_job.v1",
          "job_id": "bench-newer",
          "model_id": "melix-dev-text-lora",
          "task_kind": "text-generation",
          "source_repo": "databricks/databricks-dolly-15k",
          "suites": ["smoke", "latency"],
          "parameters": {
            "sample_size": "6",
            "batch_factor": "2",
            "acceleration_profile": "throughput"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/bench/runs/bench-newer",
          "created_at_unix_ms": 1712200000000,
          "updated_at_unix_ms": 1712200005000,
          "suite_metadata": {
            "smoke": {
              "title": "UltraChat Smoke",
              "dataset_path": "HuggingFaceH4/ultrachat_200k",
              "dataset_name": "default",
              "dataset_split": "train_sft",
              "sample_size": 6,
              "batch_factor": 2
            },
            "latency": {
              "title": "Dolly Latency",
              "dataset_path": "databricks/databricks-dolly-15k",
              "dataset_name": "default",
              "dataset_split": "train",
              "sample_size": 6,
              "batch_factor": 2
            }
          }
        }
      ],
      "benchmark_results": [
        {
          "schema_version": "melix.serving_benchmark_result.v1",
          "job_id": "bench-older",
          "suite": "smoke",
          "metrics": [
            {"name": "bench.smoke.ttft_ms", "value": 24.45, "unit": "ms"},
            {"name": "bench.smoke.tokens_per_second", "value": 47.08, "unit": "tok/s"}
          ],
          "report_path": "/tmp/melix/bench/runs/bench-older/bench-report.md",
          "report_markdown": "# Bench Older\\n"
        },
        {
          "schema_version": "melix.serving_benchmark_result.v1",
          "job_id": "bench-newer",
          "suite": "smoke",
          "metrics": [
            {"name": "bench.smoke.ttft_ms", "value": 21.10, "unit": "ms"},
            {"name": "bench.smoke.tokens_per_second", "value": 61.20, "unit": "tok/s"}
          ],
          "report_path": "/tmp/melix/bench/runs/bench-newer/bench-report.md",
          "report_markdown": "# Bench Newer\\n"
        },
        {
          "schema_version": "melix.serving_benchmark_result.v1",
          "job_id": "bench-newer",
          "suite": "latency",
          "metrics": [
            {"name": "bench.latency.p95_ms", "value": 39.70, "unit": "ms"}
          ],
          "report_path": "/tmp/melix/bench/runs/bench-newer/bench-report.md",
          "report_markdown": "# Bench Newer\\n"
        }
      ],
      "benchmark_matrix_jobs": [
        {
          "schema_version": "melix.benchmark_matrix_job.v1",
          "job_id": "matrix-older",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_ids": ["smoke"],
          "benchmark_mode": "matrix",
          "status": "completed",
          "output_dir": "/tmp/melix/bench/matrix-runs/matrix-older",
          "created_at_unix_ms": 1712150000000,
          "updated_at_unix_ms": 1712150005000,
          "parameters": {
            "acceleration_profile": "balanced"
          }
        },
        {
          "schema_version": "melix.benchmark_matrix_job.v1",
          "job_id": "matrix-newer",
          "model_id": "melix-dev-text-lora",
          "task_kind": "text-generation",
          "source_repo": "databricks/databricks-dolly-15k",
          "suite_ids": ["smoke", "latency"],
          "benchmark_mode": "matrix",
          "status": "completed",
          "output_dir": "/tmp/melix/bench/matrix-runs/matrix-newer",
          "created_at_unix_ms": 1712250000000,
          "updated_at_unix_ms": 1712250005000,
          "parameters": {
            "acceleration_profile": "low-memory"
          }
        }
      ],
      "benchmark_matrix_summary_rows": [
        {
          "job_id": "matrix-older",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "model_id": "melix-dev-text",
          "suite_id": "smoke",
          "context_length": 1024,
          "generation_length": 128,
          "batch_size": 2,
          "cache_profile": "cold",
          "reasoning_mode": "enabled",
          "structured_output_mode": "json_schema",
          "concurrency_level": 1,
          "repeats": 3,
          "requests": 8,
          "duration_seconds": 0,
          "ttft_mean_ms": 24.4,
          "ttft_std_ms": 1.2,
          "request_latency_mean_ms": 33.8,
          "request_latency_std_ms": 1.1,
          "prefill_tokens_per_second_mean": 310.0,
          "decode_tokens_per_second_mean": 62.0,
          "throughput_requests_per_second": 4.8,
          "throughput_tokens_per_second": 256.0,
          "success_rate": 1.0,
          "peak_memory_bytes_max": 2048000000,
          "queue_wait_mean_ms": 2.3,
          "queue_wait_p95_ms": 3.1,
          "created_at_unix_ms": 1712150000000
        },
        {
          "job_id": "matrix-newer",
          "task_kind": "text-generation",
          "source_repo": "databricks/databricks-dolly-15k",
          "model_id": "melix-dev-text-lora",
          "suite_id": "smoke",
          "context_length": 1024,
          "generation_length": 128,
          "batch_size": 2,
          "cache_profile": "warm",
          "reasoning_mode": "enabled",
          "structured_output_mode": "json_schema",
          "concurrency_level": 1,
          "repeats": 4,
          "requests": 12,
          "duration_seconds": 0,
          "ttft_mean_ms": 21.4,
          "ttft_std_ms": 0.9,
          "request_latency_mean_ms": 29.1,
          "request_latency_std_ms": 0.8,
          "prefill_tokens_per_second_mean": 340.0,
          "decode_tokens_per_second_mean": 66.0,
          "throughput_requests_per_second": 5.4,
          "throughput_tokens_per_second": 284.0,
          "success_rate": 1.0,
          "peak_memory_bytes_max": 1984000000,
          "queue_wait_mean_ms": 1.8,
          "queue_wait_p95_ms": 2.4,
          "created_at_unix_ms": 1712250000000
        },
        {
          "job_id": "matrix-newer",
          "task_kind": "text-generation",
          "source_repo": "databricks/databricks-dolly-15k",
          "model_id": "melix-dev-text-lora",
          "suite_id": "latency",
          "context_length": 4096,
          "generation_length": 256,
          "batch_size": 4,
          "cache_profile": "warm",
          "reasoning_mode": "enabled",
          "structured_output_mode": "json_schema",
          "concurrency_level": 2,
          "repeats": 4,
          "requests": 12,
          "duration_seconds": 0,
          "ttft_mean_ms": 31.8,
          "ttft_std_ms": 1.6,
          "request_latency_mean_ms": 44.7,
          "request_latency_std_ms": 1.2,
          "prefill_tokens_per_second_mean": 420.0,
          "decode_tokens_per_second_mean": 74.0,
          "throughput_requests_per_second": 7.6,
          "throughput_tokens_per_second": 512.0,
          "success_rate": 0.98,
          "peak_memory_bytes_max": 2368000000,
          "queue_wait_mean_ms": 3.4,
          "queue_wait_p95_ms": 4.9,
          "created_at_unix_ms": 1712250000000
        }
      ],
      "benchmark_matrix_request_rows": [
        {
          "job_id": "matrix-newer",
          "cell_id": "matrix-newer:smoke:1024:128:2:1",
          "task_kind": "text-generation",
          "suite_id": "smoke",
          "context_length": 1024,
          "generation_length": 128,
          "batch_size": 2,
          "cache_profile": "warm",
          "acceleration_profile": "low-memory",
          "reasoning_mode": "enabled",
          "structured_output_mode": "json_schema",
          "concurrency_level": 1,
          "repeat_index": 0,
          "request_index": 0,
          "ttft_ms": 21.1,
          "request_latency_ms": 28.7,
          "prefill_tokens_per_second": 336.0,
          "decode_tokens_per_second": 65.0,
          "queue_wait_ms": 1.7,
          "peak_memory_bytes": 1983000000,
          "status": "completed",
          "error_code": "",
          "created_at_unix_ms": 1712250000000
        },
        {
          "job_id": "matrix-newer",
          "cell_id": "matrix-newer:latency:4096:256:4:2",
          "task_kind": "text-generation",
          "suite_id": "latency",
          "context_length": 4096,
          "generation_length": 256,
          "batch_size": 4,
          "cache_profile": "warm",
          "acceleration_profile": "low-memory",
          "reasoning_mode": "enabled",
          "structured_output_mode": "json_schema",
          "concurrency_level": 2,
          "repeat_index": 0,
          "request_index": 0,
          "ttft_ms": 31.4,
          "request_latency_ms": 44.2,
          "prefill_tokens_per_second": 416.0,
          "decode_tokens_per_second": 73.0,
          "queue_wait_ms": 3.1,
          "peak_memory_bytes": 2367000000,
          "status": "completed",
          "error_code": "",
          "created_at_unix_ms": 1712250000000
        }
      ],
      "evaluation_jobs": [
        {
          "schema_version": "melix.evaluation_job.v1",
          "job_id": "eval-newer",
          "model_id": "melix-dev-text-lora",
          "task_kind": "text-generation",
          "source_repo": "cais/mmlu",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "scoring_mode": "multiple_choice_accuracy",
          "parameters": {
            "batch_factor": "2",
            "few_shot": "3"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/evaluation/runs/eval-newer",
          "created_at_unix_ms": 1712300000000,
          "updated_at_unix_ms": 1712300005000
        }
      ],
      "evaluation_results": [
        {
          "schema_version": "melix.evaluation_result.v2",
          "job_id": "eval-newer",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "primary_score_name": "typed_score_mean",
          "primary_score_value": 0.75,
          "extraction_success_count": 8,
          "validation_success_count": 8,
          "scored_sample_count": 8,
          "failure_count": 0,
          "duration_seconds": 12.5,
          "metrics": [
            {"name": "eval.mmlu.typed_score_mean", "value": 0.75, "unit": "ratio"},
            {"name": "eval.mmlu.threshold_pass_rate", "value": 0.75, "unit": "ratio"}
          ],
          "report_path": "/tmp/melix/evaluation/runs/eval-newer/evaluation-report.md"
        }
      ],
      "evaluation_summary_rows": [
        {
          "job_id": "eval-newer",
          "model_id": "melix-dev-text-lora",
          "task_kind": "text-generation",
          "source_repo": "cais/mmlu",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "score_name": "eval.compare.delta_accuracy",
          "score_value": 0.25,
          "correct_count": 6,
          "incorrect_count": 2,
          "effect_threshold": 0.1,
          "verdict": "improvement",
          "bootstrap_lower_bound": 0.12,
          "bootstrap_upper_bound": 0.41,
          "analytical_lower_bound": 0.1,
          "analytical_upper_bound": 0.38,
          "duration_seconds": 12.5,
          "created_at_unix_ms": 1712300000000
        }
      ],
      "evaluation_samples": [
        {
          "schema_version": "melix.evaluation_sample.v2",
          "job_id": "eval-newer",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_id": "mmlu-0001",
          "system": "",
          "input_text": "What is 2 + 2?",
          "target": "4",
          "raw_response": "4",
          "extracted_result": "4",
          "typed_score": 1.0,
          "time_s": 0.42,
          "extraction_status": "extracted",
          "validation_status": "validated",
          "failure_reason": "",
          "category_label": "math",
          "subject_label": "arithmetic"
        },
        {
          "schema_version": "melix.evaluation_sample.v2",
          "job_id": "eval-newer",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_id": "mmlu-0002",
          "system": "",
          "input_text": "Capital of France?",
          "target": "Paris",
          "raw_response": "Lyon",
          "extracted_result": "Lyon",
          "typed_score": 0.0,
          "time_s": 0.51,
          "extraction_status": "extracted",
          "validation_status": "validated",
          "failure_reason": "",
          "category_label": "geography",
          "subject_label": "europe"
        }
      ]
    }
    """
}

func makeBenchmarkExportBundleJSONWithSparseEvaluationCompareEvidence() -> String {
    makeBenchmarkExportBundleJSON()
        .replacingOccurrences(of: #""effect_threshold": 0.1,"#, with: "")
        .replacingOccurrences(of: #""verdict": "improvement""#, with: #""verdict": "inconclusive""#)
        .replacingOccurrences(of: #""bootstrap_lower_bound": 0.12,"#, with: "")
        .replacingOccurrences(of: #""bootstrap_upper_bound": 0.41,"#, with: "")
        .replacingOccurrences(of: #""analytical_lower_bound": 0.1,"#, with: "")
        .replacingOccurrences(of: #""analytical_upper_bound": 0.38,"#, with: "")
}

func makeBenchmarkExportBundleJSONWithoutResults() -> String {
    """
    {
      "export_schema_version": "melix.benchmark_export.v1",
      "exported_at_unix_ms": 1712201234567,
      "benchmark_jobs": [
        {
          "schema_version": "melix.serving_benchmark_job.v1",
          "job_id": "bench-empty",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suites": ["smoke"],
          "parameters": {
            "sample_size": "1",
            "batch_factor": "1"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/bench/runs/bench-empty",
          "created_at_unix_ms": 1712200000000,
          "updated_at_unix_ms": 1712200005000,
          "suite_metadata": {
            "smoke": {
              "title": "UltraChat Smoke",
              "dataset_path": "HuggingFaceH4/ultrachat_200k",
              "dataset_name": "default",
              "dataset_split": "train_sft",
              "sample_size": 1,
              "batch_factor": 1
            }
          }
        }
      ],
      "benchmark_results": [],
      "benchmark_matrix_jobs": [],
      "benchmark_matrix_summary_rows": [],
      "benchmark_matrix_request_rows": [],
      "evaluation_jobs": [],
      "evaluation_results": [],
      "evaluation_samples": []
    }
    """
}

struct MenuBarRegistryRootFixture: Sendable {
    let id: String
    let path: String
    let order: Int
    let accessible: Bool
    let errorCode: String
    let errorMessage: String
    let discoveredModelIDs: [String]

    init(
        id: String,
        path: String,
        order: Int,
        accessible: Bool = true,
        errorCode: String = "",
        errorMessage: String = "",
        discoveredModelIDs: [String] = []
    ) {
        self.id = id
        self.path = path
        self.order = order
        self.accessible = accessible
        self.errorCode = errorCode
        self.errorMessage = errorMessage
        self.discoveredModelIDs = discoveredModelIDs
    }
}

struct MenuBarDownloadFixture: Sendable {
    let jobID: String
    let sourceModel: String
    let status: String
    let stage: String
    let pct: Double
    let outputDir: String
    let outputPath: String
    let partialPath: String
    let statePath: String
    let selectedMirror: String
    let downloadedBytes: Int
    let totalBytes: Int
    let resumeUsed: Bool
    let resumeFromBytes: Int
    let retryCount: Int
    let stallDetectionCount: Int
    let stallReason: String
    let resumeReady: Bool

    init(
        jobID: String,
        sourceModel: String,
        status: String,
        stage: String,
        pct: Double,
        outputDir: String,
        outputPath: String,
        partialPath: String,
        statePath: String,
        selectedMirror: String,
        downloadedBytes: Int,
        totalBytes: Int,
        resumeUsed: Bool = false,
        resumeFromBytes: Int = 0,
        retryCount: Int = 0,
        stallDetectionCount: Int = 0,
        stallReason: String = "",
        resumeReady: Bool
    ) {
        self.jobID = jobID
        self.sourceModel = sourceModel
        self.status = status
        self.stage = stage
        self.pct = pct
        self.outputDir = outputDir
        self.outputPath = outputPath
        self.partialPath = partialPath
        self.statePath = statePath
        self.selectedMirror = selectedMirror
        self.downloadedBytes = downloadedBytes
        self.totalBytes = totalBytes
        self.resumeUsed = resumeUsed
        self.resumeFromBytes = resumeFromBytes
        self.retryCount = retryCount
        self.stallDetectionCount = stallDetectionCount
        self.stallReason = stallReason
        self.resumeReady = resumeReady
    }
}

func makeModelOpsRegistrySnapshotManifestJSON(
    roots: [MenuBarRegistryRootFixture],
    downloads: [MenuBarDownloadFixture] = [],
    scannedAtUnixMS: Int64 = 1_712_300_000_000
) -> String {
    let rootsJSON = roots.map { root in
        let discoveredModelsJSON = root.discoveredModelIDs
            .map { "\"\($0)\"" }
            .joined(separator: ", ")
        return """
        {
          "root_id": "\(root.id)",
          "root_path": "\(root.path)",
          "root_order": \(root.order),
          "accessible": \(root.accessible ? "true" : "false"),
          "error_code": "\(root.errorCode)",
          "error_message": "\(root.errorMessage)",
          "discovered_model_ids": [\(discoveredModelsJSON)]
        }
        """
    }
    .joined(separator: ",\n")
    let downloadsJSON = downloads.map { download in
        """
        {
          "job_id": "\(download.jobID)",
          "source_model": "\(download.sourceModel)",
          "status": "\(download.status)",
          "stage": "\(download.stage)",
          "pct": \(download.pct),
          "output_dir": "\(download.outputDir)",
          "output_path": "\(download.outputPath)",
          "partial_path": "\(download.partialPath)",
          "state_path": "\(download.statePath)",
          "selected_mirror": "\(download.selectedMirror)",
          "downloaded_bytes": \(download.downloadedBytes),
          "total_bytes": \(download.totalBytes),
          "resume_used": \(download.resumeUsed ? "true" : "false"),
          "resume_from_bytes": \(download.resumeFromBytes),
          "retry_count": \(download.retryCount),
          "stall_detection_count": \(download.stallDetectionCount),
          "stall_reason": "\(download.stallReason)",
          "resume_ready": \(download.resumeReady ? "true" : "false")
        }
        """
    }
    .joined(separator: ",\n")

    return """
    {
      "operation": "registry_snapshot",
      "jobs": [],
      "adapters": [],
      "derived_models": [],
      "downloads": [
        \(downloadsJSON)
      ],
      "model_registry": {
        "scanned_at_unix_ms": \(scannedAtUnixMS),
        "roots": [
          \(rootsJSON)
        ],
        "models": []
      }
    }
    """
}


struct StubProductInstallStateProvider: ProductInstallStateProviding {
    var updateStatusResponse: ProductUpdateStatus?
    var startupDiagnosticResponse: ProductStartupFailureDiagnostic?

    func updateStatus() -> ProductUpdateStatus? {
        updateStatusResponse
    }

    func startupFailureDiagnostic(for error: any Error) -> ProductStartupFailureDiagnostic? {
        startupDiagnosticResponse
    }
}

actor RecordingCLIWorkflowRunner: MelixCLIWorkflowRunning {
    private var outputs: [(command: MelixCLICommand, output: String)] = []
    private var failures: [(command: MelixCLICommand, error: MelixCLIWorkflowError)] = []
    private var commandHandler: (@Sendable (MelixCLICommand) -> Result<String, MelixCLIWorkflowError>)?
    private(set) var recordedCommands: [MelixCLICommand] = []

    let surface: MelixCLIWorkflowSurface

    init(surface: MelixCLIWorkflowSurface = .subprocess) {
        self.surface = surface
    }

    func configureOutput(_ output: String, for command: MelixCLICommand) {
        outputs.append((command: command, output: output))
    }

    func configureFailure(_ error: MelixCLIWorkflowError, for command: MelixCLICommand) {
        failures.append((command: command, error: error))
    }

    func configureHandler(
        _ handler: @escaping @Sendable (MelixCLICommand) -> Result<String, MelixCLIWorkflowError>
    ) {
        commandHandler = handler
    }

    func run(_ command: MelixCLICommand) async throws -> String {
        recordedCommands.append(command)
        if let commandHandler {
            return try commandHandler(command).get()
        }
        if let failure = failures.last(where: { $0.command == command }) {
            throw failure.error
        }
        return outputs.last(where: { $0.command == command })?.output ?? "{}\n"
    }

    func snapshotRecordedCommands() -> [MelixCLICommand] {
        recordedCommands
    }
}

actor RecordingCLIProcessExecutor: MelixCLIProcessExecuting {
    struct Invocation: Equatable, Sendable {
        let executablePath: String
        let arguments: [String]
        let environment: [String: String]
    }

    private var queuedResults: [Result<String, MelixCLIProcessExecutionError>] = []
    private(set) var recordedInvocations: [Invocation] = []

    func enqueueOutput(_ output: String) {
        queuedResults.append(.success(output))
    }

    func enqueueFailure(_ error: MelixCLIProcessExecutionError) {
        queuedResults.append(.failure(error))
    }

    func run(executablePath: String, arguments: [String], environment: [String: String]) async throws -> String {
        recordedInvocations.append(
            Invocation(
                executablePath: executablePath,
                arguments: arguments,
                environment: environment
            )
        )
        guard queuedResults.isEmpty == false else {
            return "{}\n"
        }
        let next = queuedResults.removeFirst()
        return try next.get()
    }
}

func makeManagedModelReceiptJSON(
    modelID: String,
    managedModelPath: String,
    sourceKind: String,
    sourceLocator: String
) -> String {
    """
    {
      "model_id": "\(modelID)",
      "managed_model_path": "\(managedModelPath)",
      "source_kind": "\(sourceKind)",
      "source_locator": "\(sourceLocator)",
      "warnings": []
    }
    """
}

func makeCLIServerSnapshotJSON(
    serverSessionID: String,
    lifecycleState: String = "ready",
    powerState: String = "active",
    serverState: String = "server_ready"
) -> String {
    """
    {
      "server_state": "\(serverState)",
      "runtime_sessions": [
        {
          "server_session_id": "\(serverSessionID)",
          "lifecycle_state": "\(lifecycleState)",
          "power_state": "\(powerState)",
          "wake_reason": "operator_resume",
          "idle_timer_seconds": 0,
          "auto_sleep_enabled": false,
          "light_sleep_after_seconds": 300,
          "deep_sleep_after_seconds": 900,
          "updated_at_unix_ms": 1712300000000
        }
      ]
    }
    """
}

func makeCLIBenchRunJSON(
    reportPath: String = "/tmp/melix/bench/runs/bench-newer/bench-report.md"
) -> String {
    """
    {
      "report_path": "\(reportPath)",
      "report_markdown": "# Melix Bench\\n\\n- bench.smoke.ttft_ms: 21.10 ms\\n",
      "metrics": {
        "bench.smoke.tokens_per_second": 61.2,
        "bench.smoke.ttft_ms": 21.1
      }
    }
    """
}

func makeDiagnosticsDebugBundleJSON(
    bundleID: String = "bench-1",
    bundlePath: String = "/tmp/melix-debug/bench-1",
    servingDiagnosticsEventCount: Int? = nil,
    servingDiagnosticsDroppedEventCount: Int? = nil,
    servingDiagnosticsMode: String = "debug"
) -> String {
    let servingDiagnosticsJSON: String
    if let servingDiagnosticsEventCount, let servingDiagnosticsDroppedEventCount {
        servingDiagnosticsJSON = """
          ,
          "serving_diagnostics": {
            "schema_version": "melix.serving_diagnostics.manifest.v1",
            "diagnostics_mode": "\(servingDiagnosticsMode)",
            "event_count": \(servingDiagnosticsEventCount),
            "dropped_event_count": \(servingDiagnosticsDroppedEventCount)
          }
        """
    } else {
        servingDiagnosticsJSON = ""
    }
    return """
    {
      "schema_version": "melix.diagnostics.bundle.v1",
      "bundle_id": "\(bundleID)",
      "bundle_path": "\(bundlePath)",
      "diagnostics_consent_state": "local_only",
      "debug_artifact_policy": "explicit_cli_command",
      "debug_jsonl_enabled": true,
      "debug_jsonl_event_limit": 256,
      "redaction_schema_version": "melix.diagnostics.redaction.v1",
      "redacted_field_count": 3,
      "source_run_record_path": "/tmp/melix/jobs/\(bundleID)/run-record.json",
      "artifacts": {
        "command": "command.txt",
        "redacted_env": "redacted-env.json",
        "effective_config": "effective-config.json",
        "system": "system.json",
        "capability_receipts": "capability-receipts.json",
        "memory_estimate": "memory-estimate.json",
        "logs": "logs.txt",
        "metrics": "metrics.json",
        "error": "error.json"
      }
      \(servingDiagnosticsJSON)
    }
    """
}

func makeCLIBenchmarkMatrixRunJSON(
    jobID: String = "matrix-newer",
    outputDir: String = "/tmp/melix/bench/matrix-runs/matrix-newer"
) -> String {
    """
    {
      "job": {
        "schema_version": "melix.benchmark_matrix_job.v1",
        "job_id": "\(jobID)",
        "model_id": "melix-dev-text-lora",
        "task_kind": "text-generation",
        "source_repo": "",
        "suite_ids": ["smoke"],
        "benchmark_mode": "matrix",
        "status": "completed",
        "output_dir": "\(outputDir)",
        "created_at_unix_ms": 1712300000000,
        "updated_at_unix_ms": 1712300001000
      },
      "summary_rows": []
    }
    """
}

func makeCLIEvaluationRunJSON(
    jobID: String = "eval-newer",
    outputDir: String = "/tmp/melix/evaluation/runs/eval-newer"
) -> String {
    """
    [
      {
        "job": {
          "schema_version": "melix.evaluation_job.v1",
          "job_id": "\(jobID)",
          "model_id": "melix-dev-text-lora",
          "task_kind": "text-generation",
          "source_repo": "",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "scoring_mode": "multiple_choice_accuracy",
          "parameters": {},
          "status": "completed",
          "output_dir": "\(outputDir)",
          "created_at_unix_ms": 1712300000000,
          "updated_at_unix_ms": 1712300001000
        },
        "results": [
          {
            "schema_version": "melix.evaluation_result.v1",
            "job_id": "\(jobID)",
            "suite_id": "mmlu",
            "dataset_id": "mmlu.dev.v1",
            "sample_size": 8,
            "report_path": "\(outputDir)/evaluation-report.md",
            "metrics": [
              {
                "name": "mmlu.accuracy",
                "value": 0.5,
                "unit": ""
              }
            ]
          }
        ]
      }
    ]
    """
}

func makeCLIExportResponseJSON(
    jobID: String,
    outputPath: String,
    rowCount: Int
) -> String {
    """
    {
      "job_id": "\(jobID)",
      "output_path": "\(outputPath)",
      "row_count": \(rowCount)
    }
    """
}
