import Foundation
import MelixControlPlaneProtocol

public enum ControlPlaneXPCClientError: Error, Equatable {
    case requestFailed(code: String, message: String)
}

public struct ControlPlaneImageGenerationRequest: Equatable, Sendable {
    public let modelID: String
    public let prompt: String
    public let size: String
    public let steps: UInt32
    public let guidance: Float
    public let negativePrompt: String
    public let n: UInt32
    public let responseFormat: String
    public let artifactNamespace: String

    public init(
        modelID: String,
        prompt: String,
        size: String = "1024x1024",
        steps: UInt32 = 0,
        guidance: Float = 0,
        negativePrompt: String = "",
        n: UInt32 = 1,
        responseFormat: String = "png",
        artifactNamespace: String = ""
    ) {
        self.modelID = modelID
        self.prompt = prompt
        self.size = size
        self.steps = steps
        self.guidance = guidance
        self.negativePrompt = negativePrompt
        self.n = n
        self.responseFormat = responseFormat
        self.artifactNamespace = artifactNamespace
    }
}

public struct ControlPlaneImageEditRequest: Equatable, Sendable {
    public enum Mode: String, Equatable, Sendable {
        case edit
        case variation
        case iterate
    }

    public let modelID: String
    public let prompt: String
    public let imageData: Data
    public let imageURL: String
    public let maskData: Data
    public let maskURL: String
    public let sourceArtifactID: String
    public let promptDelta: String
    public let mode: Mode
    public let strength: Float
    public let size: String
    public let steps: UInt32
    public let guidance: Float
    public let negativePrompt: String
    public let n: UInt32
    public let responseFormat: String

    public init(
        modelID: String,
        prompt: String,
        imageData: Data = Data(),
        imageURL: String = "",
        maskData: Data = Data(),
        maskURL: String = "",
        sourceArtifactID: String = "",
        promptDelta: String = "",
        mode: Mode = .edit,
        strength: Float = 1,
        size: String = "1024x1024",
        steps: UInt32 = 0,
        guidance: Float = 0,
        negativePrompt: String = "",
        n: UInt32 = 1,
        responseFormat: String = "png"
    ) {
        self.modelID = modelID
        self.prompt = prompt
        self.imageData = imageData
        self.imageURL = imageURL
        self.maskData = maskData
        self.maskURL = maskURL
        self.sourceArtifactID = sourceArtifactID
        self.promptDelta = promptDelta
        self.mode = mode
        self.strength = strength
        self.size = size
        self.steps = steps
        self.guidance = guidance
        self.negativePrompt = negativePrompt
        self.n = n
        self.responseFormat = responseFormat
    }
}

public struct ControlPlaneImageDefaultsRequest: Equatable, Sendable {
    public let generateModelID: String
    public let editModelID: String
    public let size: String
    public let steps: UInt32
    public let guidance: Float
    public let strength: Float
    public let negativePrompt: String

    public init(
        generateModelID: String,
        editModelID: String,
        size: String,
        steps: UInt32,
        guidance: Float,
        strength: Float,
        negativePrompt: String
    ) {
        self.generateModelID = generateModelID
        self.editModelID = editModelID
        self.size = size
        self.steps = steps
        self.guidance = guidance
        self.strength = strength
        self.negativePrompt = negativePrompt
    }
}

public struct ControlPlaneBenchResult: Equatable, Sendable {
    public let reportPath: String
    public let evidencePath: String
    public let reportMarkdown: String
    public let metrics: [String: Double]
    public let job: Melix_Controlplane_V1_BenchmarkJobSummary?

    public init(
        reportPath: String,
        evidencePath: String = "",
        reportMarkdown: String,
        metrics: [String: Double],
        job: Melix_Controlplane_V1_BenchmarkJobSummary? = nil
    ) {
        self.reportPath = reportPath
        self.evidencePath = evidencePath
        self.reportMarkdown = reportMarkdown
        self.metrics = metrics
        self.job = job
    }
}

public struct ControlPlaneBenchRequest: Equatable, Sendable {
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
        parameters: [String: String] = [:]
    ) {
        self.modelID = modelID
        self.hfRepoID = hfRepoID
        self.suites = suites
        self.contextLengths = Self.normalizedBenchValues(contextLengths)
        self.generationLength = generationLength
        self.batchSizes = Self.normalizedBenchValues(batchSizes)
        self.repeats = repeats == 0 ? 1 : repeats
        self.cacheProfile = cacheProfile
        self.reasoningMode = reasoningMode
        self.structuredOutputMode = structuredOutputMode
        self.parameters = parameters
    }

    public static let validCacheProfiles: [String] = ["cold", "warm", "partial_prefix"]

    public static func normalizedBenchValues(_ values: [UInt32]) -> [UInt32] {
        Array(Set(values)).sorted()
    }
}

public struct ControlPlaneBenchMatrixResult: Equatable, Sendable {
    public let job: Melix_Controlplane_V1_BenchmarkMatrixJobSummary
    public let summaryRows: [Melix_Controlplane_V1_BenchmarkMatrixSummaryRow]

    public init(
        job: Melix_Controlplane_V1_BenchmarkMatrixJobSummary,
        summaryRows: [Melix_Controlplane_V1_BenchmarkMatrixSummaryRow]
    ) {
        self.job = job
        self.summaryRows = summaryRows
    }
}

public struct ControlPlaneBenchMatrixRequest: Equatable, Sendable {
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
        allowLargeMatrix: Bool = false
    ) {
        self.modelID = modelID
        self.hfRepoID = hfRepoID
        self.taskKind = taskKind
        self.suites = Array(Set(suites)).sorted()
        self.contextLengths = ControlPlaneBenchRequest.normalizedBenchValues(contextLengths)
        self.generationLengths = ControlPlaneBenchRequest.normalizedBenchValues(generationLengths)
        self.batchSizes = ControlPlaneBenchRequest.normalizedBenchValues(batchSizes)
        self.cacheProfiles = Self.normalizedStringValues(cacheProfiles)
        self.reasoningModes = Self.normalizedStringValues(reasoningModes)
        self.structuredOutputModes = Self.normalizedStringValues(structuredOutputModes)
        self.concurrencyLevels = ControlPlaneBenchRequest.normalizedBenchValues(concurrencyLevels)
        self.repeats = repeats == 0 ? 1 : repeats
        self.requests = requests
        self.durationSeconds = durationSeconds
        self.allowLargeMatrix = allowLargeMatrix
    }

    public static let maxMatrixCellCount: Int = 256

    public static func normalizedStringValues(_ values: [String]) -> [String] {
        Array(Set(values.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty })).sorted()
    }

    public var matrixCellCount: Int {
        let counts = [
            suites.count,
            contextLengths.count,
            generationLengths.count,
            batchSizes.count,
            cacheProfiles.count,
            reasoningModes.count,
            structuredOutputModes.count,
            concurrencyLevels.count,
        ]
        return counts.reduce(1) { partial, count in partial * max(count, 1) }
    }
}

public struct ControlPlaneEvaluationRequest: Equatable, Sendable {
    public struct Source: Equatable, Sendable {
        public enum Kind: String, Equatable, Sendable {
            case builtinPackage
            case localCSV
            case localJSONL
            case huggingFaceDataset
        }

        public let kind: Kind
        public let path: String
        public let datasetPath: String
        public let datasetName: String
        public let datasetRevision: String
        public let split: String

        public init(
            kind: Kind = .builtinPackage,
            path: String = "",
            datasetPath: String = "",
            datasetName: String = "",
            datasetRevision: String = "main",
            split: String = "train"
        ) {
            self.kind = kind
            self.path = path
            self.datasetPath = datasetPath
            self.datasetName = datasetName
            self.datasetRevision = datasetRevision
            self.split = split
        }

        public static let builtinPackage = Source()

        public static func localCSV(path: String) -> Source {
            Source(kind: .localCSV, path: path)
        }

        public static func localJSONL(path: String) -> Source {
            Source(kind: .localJSONL, path: path)
        }

        public static func huggingFaceDataset(
            datasetPath: String,
            datasetName: String = "",
            datasetRevision: String = "main",
            split: String = "train"
        ) -> Source {
            Source(
                kind: .huggingFaceDataset,
                datasetPath: datasetPath,
                datasetName: datasetName,
                datasetRevision: datasetRevision,
                split: split
            )
        }
    }

    public struct FieldMapping: Equatable, Sendable {
        public let systemPath: String
        public let inputTextPath: String
        public let targetPath: String
        public let sampleIDPath: String

        public init(
            systemPath: String = "",
            inputTextPath: String = "",
            targetPath: String = "",
            sampleIDPath: String = ""
        ) {
            self.systemPath = systemPath
            self.inputTextPath = inputTextPath
            self.targetPath = targetPath
            self.sampleIDPath = sampleIDPath
        }
    }

    public struct Profile: Equatable, Sendable {
        public let profileType: String
        public let resultKind: String
        public let extractionMode: String
        public let scoringMode: String
        public let threshold: Double
        public let outputSchemaJSON: String
        public let ignoredPaths: [String]

        public init(
            profileType: String = "final_result",
            resultKind: String = "text",
            extractionMode: String = "heuristic_final",
            scoringMode: String = "normalized_exact_match",
            threshold: Double = 1.0,
            outputSchemaJSON: String = "",
            ignoredPaths: [String] = []
        ) {
            self.profileType = profileType
            self.resultKind = resultKind
            self.extractionMode = extractionMode
            self.scoringMode = scoringMode
            self.threshold = threshold
            self.outputSchemaJSON = outputSchemaJSON
            self.ignoredPaths = ignoredPaths
        }
    }

    public struct RemoteTarget: Equatable, Sendable {
        public let remoteServerID: String
        public let providerKind: String
        public let baseURL: String
        public let apiKey: String
        public let modelID: String
        public let timeoutSeconds: UInt32
        public let rateLimitPerMinute: UInt32

        public init(
            remoteServerID: String,
            providerKind: String,
            baseURL: String,
            apiKey: String,
            modelID: String,
            timeoutSeconds: UInt32 = 60,
            rateLimitPerMinute: UInt32 = 0
        ) {
            self.remoteServerID = remoteServerID
            self.providerKind = providerKind
            self.baseURL = baseURL
            self.apiKey = apiKey
            self.modelID = modelID
            self.timeoutSeconds = timeoutSeconds
            self.rateLimitPerMinute = rateLimitPerMinute
        }
    }

    public let modelID: String
    public let hfRepoID: String
    public let suiteID: String
    public let datasetID: String
    public let sampleSize: UInt32
    public let source: Source
    public let fieldMapping: FieldMapping
    public let profile: Profile
    public let parameters: [String: String]
    public let remoteTarget: RemoteTarget?

    public init(
        modelID: String = "",
        hfRepoID: String = "",
        suiteID: String,
        datasetID: String = "",
        sampleSize: UInt32 = 0,
        source: Source = .builtinPackage,
        fieldMapping: FieldMapping = .init(),
        profile: Profile = .init(),
        parameters: [String: String] = [:],
        remoteTarget: RemoteTarget? = nil
    ) {
        self.modelID = modelID
        self.hfRepoID = hfRepoID
        self.suiteID = suiteID
        self.datasetID = datasetID
        self.sampleSize = sampleSize
        self.source = source
        self.fieldMapping = fieldMapping
        self.profile = profile
        self.parameters = parameters
        self.remoteTarget = remoteTarget
    }
}

public struct ControlPlaneEvaluationResult: Equatable, Sendable {
    public let job: Melix_Controlplane_V1_EvaluationJobSummary
    public let results: [Melix_Controlplane_V1_EvaluationResultSummary]

    public init(
        job: Melix_Controlplane_V1_EvaluationJobSummary,
        results: [Melix_Controlplane_V1_EvaluationResultSummary]
    ) {
        self.job = job
        self.results = results
    }
}

public struct ControlPlaneExportResult: Equatable, Sendable {
    public let exportBundleJSON: String

    public init(exportBundleJSON: String) {
        self.exportBundleJSON = exportBundleJSON
    }
}

public protocol ControlPlaneXPCClient: Sendable {
    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse
    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>
    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution
    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot
    func startServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot
    func pauseServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot
    func resumeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot
    func wakeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot
    func stopServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot
    func updateServerIdlePolicy(
        serverSessionID: String,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot
    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary
    func loadModel(modelID: String, memoryBudgetBytes: UInt64) async throws -> Melix_Controlplane_V1_ModelSummary
    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary
    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary
    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo
    func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult
    func generateImage(
        _ request: ControlPlaneImageGenerationRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary
    func editImage(
        _ request: ControlPlaneImageEditRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary
    func applyImageDefaults(
        _ request: ControlPlaneImageDefaultsRequest
    ) async throws -> Melix_Controlplane_V1_ImageDefaultsSummary
    func runDoctor() async throws -> Melix_Controlplane_V1_DoctorReport
    func searchHubModels(
        query: String,
        pageSize: UInt32,
        cursor: String,
        mlxOnly: Bool
    ) async throws -> Melix_Controlplane_V1_HubSearchResult
    func getHubModelCard(repoID: String) async throws -> Melix_Controlplane_V1_HubModelCard
    func runBench(_ request: ControlPlaneBenchRequest) async throws -> ControlPlaneBenchResult
    func runBenchMatrix(_ request: ControlPlaneBenchMatrixRequest) async throws -> ControlPlaneBenchMatrixResult
    func runEvaluation(_ request: ControlPlaneEvaluationRequest) async throws -> ControlPlaneEvaluationResult
    func exportResults(outputDir: String) async throws -> ControlPlaneExportResult
    func cancelRequest(requestID: String) async throws -> Bool
    func applyServerSessionGatewayAccess(
        serverSessionID: String,
        primaryKey: String,
        keyID: String,
        label: String,
        tokenHint: String
    ) async throws
    func applyServerSessionGatewayConfig(
        serverSessionID: String,
        host: String,
        port: Int,
        defaultModelID: String,
        servedModelIDs: [String],
        rateLimitPerMinute: Int,
        timeoutSeconds: Int,
        modelIdleTimeoutSeconds: Int
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot
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
        numDraftTokens: Int
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot
    func clearServerSessionGatewayAccess(serverSessionID: String) async throws
}

public extension ControlPlaneXPCClient {
    func loadModel(modelID: String, memoryBudgetBytes: UInt64) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = memoryBudgetBytes
        return try await loadModel(modelID: modelID)
    }

    func startServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server start is not implemented for this control-plane client."
        )
    }

    func pauseServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server pause is not implemented for this control-plane client."
        )
    }

    func resumeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server resume is not implemented for this control-plane client."
        )
    }

    func wakeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server wake is not implemented for this control-plane client."
        )
    }

    func stopServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server stop is not implemented for this control-plane client."
        )
    }

    func updateServerIdlePolicy(
        serverSessionID: String,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        _ = autoSleepEnabled
        _ = lightSleepAfterSeconds
        _ = deepSleepAfterSeconds
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Server idle-policy updates are not implemented for this control-plane client."
        )
    }

    func generateImage(
        _ request: ControlPlaneImageGenerationRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        _ = request
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Image generation is not implemented for this control-plane client."
        )
    }

    func editImage(
        _ request: ControlPlaneImageEditRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        _ = request
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Image editing is not implemented for this control-plane client."
        )
    }

    func applyImageDefaults(
        _ request: ControlPlaneImageDefaultsRequest
    ) async throws -> Melix_Controlplane_V1_ImageDefaultsSummary {
        _ = request
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Image defaults apply is not implemented for this control-plane client."
        )
    }

    func runDoctor() async throws -> Melix_Controlplane_V1_DoctorReport {
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Doctor is not implemented for this control-plane client."
        )
    }

    func searchHubModels(
        query: String,
        pageSize: UInt32,
        cursor: String,
        mlxOnly: Bool
    ) async throws -> Melix_Controlplane_V1_HubSearchResult {
        _ = query
        _ = pageSize
        _ = cursor
        _ = mlxOnly
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Hub model search is not implemented for this control-plane client."
        )
    }

    func getHubModelCard(repoID: String) async throws -> Melix_Controlplane_V1_HubModelCard {
        _ = repoID
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Hub model cards are not implemented for this control-plane client."
        )
    }

    func runBench() async throws -> ControlPlaneBenchResult {
        try await runBench(ControlPlaneBenchRequest())
    }

    func runBench(_ request: ControlPlaneBenchRequest) async throws -> ControlPlaneBenchResult {
        _ = request
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Bench is not implemented for this control-plane client."
        )
    }

    func runBenchMatrix(_ request: ControlPlaneBenchMatrixRequest) async throws -> ControlPlaneBenchMatrixResult {
        _ = request
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Bench matrix is not implemented for this control-plane client."
        )
    }

    func runEvaluation(_ request: ControlPlaneEvaluationRequest) async throws -> ControlPlaneEvaluationResult {
        _ = request
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Evaluation is not implemented for this control-plane client."
        )
    }

    func exportResults() async throws -> ControlPlaneExportResult {
        try await exportResults(outputDir: "")
    }

    func exportResults(outputDir: String) async throws -> ControlPlaneExportResult {
        _ = outputDir
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Export results is not implemented for this control-plane client."
        )
    }

    func cancelRequest(requestID: String) async throws -> Bool {
        _ = requestID
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Request cancellation is not implemented for this control-plane client."
        )
    }

    func applyServerSessionGatewayAccess(
        serverSessionID: String,
        primaryKey: String,
        keyID: String,
        label: String,
        tokenHint: String
    ) async throws {
        _ = serverSessionID
        _ = primaryKey
        _ = keyID
        _ = label
        _ = tokenHint
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Gateway access apply is not implemented for this control-plane client."
        )
    }

    func clearServerSessionGatewayAccess(serverSessionID: String) async throws {
        _ = serverSessionID
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Gateway access clear is not implemented for this control-plane client."
        )
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
        _ = serverSessionID
        _ = host
        _ = port
        _ = defaultModelID
        _ = servedModelIDs
        _ = rateLimitPerMinute
        _ = timeoutSeconds
        _ = modelIdleTimeoutSeconds
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Gateway config apply is not implemented for this control-plane client."
        )
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
        numDraftTokens: Int
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        _ = serverSessionID
        _ = temperature
        _ = topP
        _ = maxTokens
        _ = streamIntervalTokens
        _ = maxConcurrentRequests
        _ = concurrentProcessingEnabled
        _ = prefillBatchSize
        _ = completionBatchSize
        _ = accelerationMode
        _ = draftModelID
        _ = numDraftTokens
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Serving defaults apply is not implemented for this control-plane client."
        )
    }
}

public protocol ControlPlaneExecuting: Sendable {
    func handshake(_ request: Melix_Controlplane_V1_HandshakeRequest) async throws -> Melix_Controlplane_V1_HandshakeResponse
    func subscribe(_ request: Melix_Controlplane_V1_SubscribeRequest) async -> ControlPlaneSubscription
    func unsubscribe(_ subscriptionID: String) async
    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution
    func execute(_ request: Melix_Controlplane_V1_ControlPlaneRequest) async throws -> Melix_Controlplane_V1_ControlPlaneResponse
}

extension ControlPlaneService: ControlPlaneExecuting {}

public actor LocalControlPlaneXPCClient: ControlPlaneXPCClient {
    private let service: any ControlPlaneExecuting

    public init(service: any ControlPlaneExecuting = ControlPlaneService()) {
        self.service = service
    }

    public func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = UUID().uuidString
        return try await service.handshake(request)
    }

    public func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        var request = Melix_Controlplane_V1_SubscribeRequest()
        request.lastSeenSeq = lastSeenSeq
        let subscription = await service.subscribe(request)

        return AsyncStream { continuation in
            let forwardTask = Task {
                for await event in subscription.stream {
                    continuation.yield(event)
                }
                continuation.finish()
            }

            continuation.onTermination = { _ in
                forwardTask.cancel()
                Task {
                    await self.service.unsubscribe(subscription.subscriptionID)
                }
            }
        }
    }

    public func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        try await service.startChat(request)
    }

    public func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await loadModel(modelID: modelID, memoryBudgetBytes: 0)
    }

    public func loadModel(
        modelID: String,
        memoryBudgetBytes: UInt64
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await execute(makeLoadRequest(modelID: modelID, memoryBudgetBytes: memoryBudgetBytes)) { response in
            response.model.model
        }
    }

    public func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await execute(makeServerSnapshotRequest()) { response in
            response.server.snapshot
        }
    }

    public func startServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await execute(makeStartServerRequest(serverSessionID: serverSessionID)) { response in
            response.server.snapshot
        }
    }

    public func pauseServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await execute(makePauseServerRequest(serverSessionID: serverSessionID)) { response in
            response.server.snapshot
        }
    }

    public func resumeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await execute(makeResumeServerRequest(serverSessionID: serverSessionID)) { response in
            response.server.snapshot
        }
    }

    public func wakeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await execute(makeWakeServerRequest(serverSessionID: serverSessionID)) { response in
            response.server.snapshot
        }
    }

    public func stopServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await execute(makeStopServerRequest(serverSessionID: serverSessionID)) { response in
            response.server.snapshot
        }
    }

    public func updateServerIdlePolicy(
        serverSessionID: String,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await execute(
            makeSetServerIdlePolicyRequest(
                serverSessionID: serverSessionID,
                autoSleepEnabled: autoSleepEnabled,
                lightSleepAfterSeconds: lightSleepAfterSeconds,
                deepSleepAfterSeconds: deepSleepAfterSeconds
            )
        ) { response in
            response.server.snapshot
        }
    }

    public func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await execute(makeUnloadRequest(modelID: modelID)) { response in
            response.model.model
        }
    }

    public func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await execute(makeSetModelPolicyRequest(modelID: modelID, values: values)) { response in
            response.model.model
        }
    }

    public func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        try await execute(makeGetModelInfoRequest(modelID: modelID)) { response in
            response.model.info
        }
    }

    public func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String = "",
        weightQuant: String,
        kvQuant: String,
        ext: [String: String] = [:]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        try await execute(
            makeRunModelOperationRequest(
                modelID: modelID,
                operation: operation,
                outputDir: outputDir,
                quantProfileID: quantProfileID,
                weightQuant: weightQuant,
                kvQuant: kvQuant,
                ext: ext
            )
        ) { response in
            response.model.operation
        }
    }

    public func generateImage(
        _ request: ControlPlaneImageGenerationRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        try await execute(makeImageGenerateRequest(request)) { response in
            response.image.job
        }
    }

    public func editImage(
        _ request: ControlPlaneImageEditRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        try await execute(makeImageEditRequest(request)) { response in
            response.image.job
        }
    }

    public func applyImageDefaults(
        _ request: ControlPlaneImageDefaultsRequest
    ) async throws -> Melix_Controlplane_V1_ImageDefaultsSummary {
        try await execute(makeApplyImageDefaultsRequest(request)) { response in
            response.image.imageDefaults
        }
    }

    public func runDoctor() async throws -> Melix_Controlplane_V1_DoctorReport {
        try await execute(makeRunDoctorRequest()) { response in
            response.ops.doctor
        }
    }

    public func searchHubModels(
        query: String,
        pageSize: UInt32,
        cursor: String,
        mlxOnly: Bool
    ) async throws -> Melix_Controlplane_V1_HubSearchResult {
        try await execute(
            makeSearchHubModelsRequest(
                query: query,
                pageSize: pageSize,
                cursor: cursor,
                mlxOnly: mlxOnly
            )
        ) { response in
            response.ops.hubSearch
        }
    }

    public func getHubModelCard(repoID: String) async throws -> Melix_Controlplane_V1_HubModelCard {
        try await execute(makeGetHubModelCardRequest(repoID: repoID)) { response in
            response.ops.hubModelCard
        }
    }

    public func runBench(_ request: ControlPlaneBenchRequest) async throws -> ControlPlaneBenchResult {
        try await execute(makeRunBenchRequest(request)) { response in
            ControlPlaneBenchResult(
                reportPath: response.ops.reportPath,
                evidencePath: response.ops.evidencePath,
                reportMarkdown: response.ops.reportMarkdown,
                metrics: response.ops.metrics.values,
                job: response.ops.hasBenchmarkJob ? response.ops.benchmarkJob : nil
            )
        }
    }

    public func runBenchMatrix(_ request: ControlPlaneBenchMatrixRequest) async throws -> ControlPlaneBenchMatrixResult {
        try await execute(makeRunBenchMatrixRequest(request)) { response in
            ControlPlaneBenchMatrixResult(
                job: response.ops.benchmarkMatrixJob,
                summaryRows: Array(response.ops.benchmarkMatrixSummaryRows)
            )
        }
    }

    public func runEvaluation(_ request: ControlPlaneEvaluationRequest) async throws -> ControlPlaneEvaluationResult {
        try await execute(makeRunEvaluationRequest(request)) { response in
            ControlPlaneEvaluationResult(
                job: response.ops.evaluationJob,
                results: Array(response.ops.evaluationResults)
            )
        }
    }

    public func exportResults(outputDir: String = "") async throws -> ControlPlaneExportResult {
        try await execute(makeExportResultsRequest(outputDir: outputDir)) { response in
            ControlPlaneExportResult(exportBundleJSON: response.ops.exportBundleJson)
        }
    }

    public func cancelRequest(requestID: String) async throws -> Bool {
        try await execute(makeCancelRequest(requestID: requestID)) { _ in
            true
        }
    }

    public func applyServerSessionGatewayAccess(
        serverSessionID: String,
        primaryKey: String,
        keyID: String = "primary",
        label: String = "primary",
        tokenHint: String = "primary"
    ) async throws {
        _ = try await execute(
            makeApplyServerSessionGatewayAccessRequest(
                serverSessionID: serverSessionID,
                primaryKey: primaryKey,
                keyID: keyID,
                label: label,
                tokenHint: tokenHint
            )
        ) { _ in true }
    }

    public func clearServerSessionGatewayAccess(serverSessionID: String) async throws {
        _ = try await execute(
            makeClearServerSessionGatewayAccessRequest(serverSessionID: serverSessionID)
        ) { _ in true }
    }

    public func applyServerSessionGatewayConfig(
        serverSessionID: String,
        host: String,
        port: Int,
        defaultModelID: String,
        servedModelIDs: [String],
        rateLimitPerMinute: Int,
        timeoutSeconds: Int,
        modelIdleTimeoutSeconds: Int
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await execute(
            makeApplyServerSessionGatewayConfigRequest(
                serverSessionID: serverSessionID,
                host: host,
                port: port,
                defaultModelID: defaultModelID,
                servedModelIDs: servedModelIDs,
                rateLimitPerMinute: rateLimitPerMinute,
                timeoutSeconds: timeoutSeconds,
                modelIdleTimeoutSeconds: modelIdleTimeoutSeconds
            )
        ) { response in
            response.server.snapshot
        }
    }

    public func applyServerSessionServingDefaults(
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
        numDraftTokens: Int
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await execute(
            makeApplyServerSessionServingDefaultsRequest(
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
                numDraftTokens: numDraftTokens
            )
        ) { response in
            response.server.snapshot
        }
    }

    private func execute<T>(
        _ request: Melix_Controlplane_V1_ControlPlaneRequest,
        transform: (Melix_Controlplane_V1_ControlPlaneResponse) -> T
    ) async throws -> T {
        let response = try await service.execute(request)
        guard response.ok else {
            throw ControlPlaneXPCClientError.requestFailed(
                code: response.error.code,
                message: response.error.message
            )
        }
        return transform(response)
    }

    private func makeLoadRequest(
        modelID: String,
        memoryBudgetBytes: UInt64
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-load-\(modelID)"
        request.commandType = "model.load"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.load = Melix_Controlplane_V1_LoadModel()
        request.model.load.modelID = modelID
        request.model.load.memoryBudgetBytes = memoryBudgetBytes
        return request
    }

    private func makeServerSnapshotRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-server-snapshot"
        request.commandType = "server.get_snapshot"
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.getSnapshot = Melix_Controlplane_V1_GetServerSnapshot()
        return request
    }

    private func makeStartServerRequest(serverSessionID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-server-start-\(serverSessionID)"
        request.commandType = "server.start"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.start = Melix_Controlplane_V1_StartServer()
        request.server.start.serverSessionID = serverSessionID
        return request
    }

    private func makePauseServerRequest(serverSessionID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-server-pause-\(serverSessionID)"
        request.commandType = "server.pause"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.pause = Melix_Controlplane_V1_PauseServer()
        request.server.pause.serverSessionID = serverSessionID
        return request
    }

    private func makeResumeServerRequest(serverSessionID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-server-resume-\(serverSessionID)"
        request.commandType = "server.resume"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.resume = Melix_Controlplane_V1_ResumeServer()
        request.server.resume.serverSessionID = serverSessionID
        return request
    }

    private func makeWakeServerRequest(serverSessionID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-server-wake-\(serverSessionID)"
        request.commandType = "server.wake"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.wake = Melix_Controlplane_V1_WakeServer()
        request.server.wake.serverSessionID = serverSessionID
        return request
    }

    private func makeStopServerRequest(serverSessionID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-server-stop-\(serverSessionID)"
        request.commandType = "server.stop"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.stop = Melix_Controlplane_V1_StopServer()
        request.server.stop.serverSessionID = serverSessionID
        return request
    }

    private func makeSetServerIdlePolicyRequest(
        serverSessionID: String,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-server-idle-policy-\(serverSessionID)"
        request.commandType = "server.set_idle_policy"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.setIdlePolicy = Melix_Controlplane_V1_SetServerIdlePolicy()
        request.server.setIdlePolicy.serverSessionID = serverSessionID
        request.server.setIdlePolicy.autoSleepEnabled = autoSleepEnabled
        request.server.setIdlePolicy.lightSleepAfterSeconds = lightSleepAfterSeconds
        request.server.setIdlePolicy.deepSleepAfterSeconds = deepSleepAfterSeconds
        return request
    }

    private func makeUnloadRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-unload-\(modelID)"
        request.commandType = "model.unload"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.unload = Melix_Controlplane_V1_UnloadModel()
        request.model.unload.modelID = modelID
        return request
    }

    private func makeSetModelPolicyRequest(
        modelID: String,
        values: [String: String]
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-set-policy-\(modelID)"
        request.commandType = "model.set_policy"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.setPolicy = Melix_Controlplane_V1_SetModelPolicy()
        request.model.setPolicy.modelID = modelID
        request.model.setPolicy.values = values
        return request
    }

    private func makeGetModelInfoRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-model-info-\(modelID)"
        request.commandType = "model.get_info"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.getInfo = Melix_Controlplane_V1_GetModelInfo()
        request.model.getInfo.modelID = modelID
        return request
    }

    private func makeRunModelOperationRequest(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-model-op-\(modelID)-\(operation)"
        request.commandType = "model.run_operation"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.runOperation = Melix_Controlplane_V1_RunModelOperation()
        request.model.runOperation.modelID = modelID
        request.model.runOperation.operation = operation
        request.model.runOperation.outputDir = outputDir
        request.model.runOperation.weightQuant = weightQuant
        request.model.runOperation.kvQuant = kvQuant
        request.model.runOperation.generateManifest = true
        request.model.runOperation.runSmokeTest = true
        request.model.runOperation.ext = ext
        if operation == "quantize" || !quantProfileID.isEmpty || !weightQuant.isEmpty || !kvQuant.isEmpty {
            request.model.runOperation.quantProfile = Melix_Controlplane_V1_QuantizationProfile()
            request.model.runOperation.quantProfile.algorithm = "oq"
            request.model.runOperation.quantProfile.schemaVersion = "melix.quant_profile.v1"
            let resolvedProfileID = quantProfileID.isEmpty ? (weightQuant.isEmpty ? "q4" : weightQuant) : quantProfileID
            request.model.runOperation.quantProfile.quantProfileID = resolvedProfileID
            request.model.runOperation.quantProfile.weightQuant = weightQuant.isEmpty ? resolvedProfileID : weightQuant
            request.model.runOperation.quantProfile.kvQuant = kvQuant
        }
        return request
    }

    private func makeImageGenerateRequest(
        _ generation: ControlPlaneImageGenerationRequest
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-image-generate-\(UUID().uuidString)"
        request.commandType = "image.generate"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.generate = Melix_Controlplane_V1_GenerateImage()
        request.image.generate.modelID = generation.modelID
        request.image.generate.prompt = generation.prompt
        request.image.generate.size = generation.size
        request.image.generate.steps = generation.steps
        request.image.generate.guidance = generation.guidance
        request.image.generate.negativePrompt = generation.negativePrompt
        request.image.generate.n = generation.n
        request.image.generate.responseFormat = generation.responseFormat
        request.image.generate.artifactNamespace = generation.artifactNamespace
        return request
    }

    private func makeImageEditRequest(
        _ edit: ControlPlaneImageEditRequest
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-image-edit-\(UUID().uuidString)"
        request.commandType = "image.edit"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.edit = Melix_Controlplane_V1_EditImage()
        request.image.edit.modelID = edit.modelID
        request.image.edit.prompt = edit.prompt
        request.image.edit.image = edit.imageData
        request.image.edit.imageUri = edit.imageURL
        request.image.edit.mask = edit.maskData
        request.image.edit.maskUri = edit.maskURL
        request.image.edit.sourceArtifactID = edit.sourceArtifactID
        request.image.edit.promptDelta = edit.promptDelta
        request.image.edit.editMode = imageEditModeProto(edit.mode)
        request.image.edit.strength = edit.strength
        request.image.edit.size = edit.size
        request.image.edit.steps = edit.steps
        request.image.edit.guidance = edit.guidance
        request.image.edit.negativePrompt = edit.negativePrompt
        request.image.edit.n = edit.n
        request.image.edit.responseFormat = edit.responseFormat
        return request
    }

    private func makeApplyImageDefaultsRequest(
        _ defaults: ControlPlaneImageDefaultsRequest
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-image-defaults-\(UUID().uuidString)"
        request.commandType = "image.apply_defaults"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.applyDefaults = Melix_Controlplane_V1_ApplyImageDefaults()
        request.image.applyDefaults.generateModelID = defaults.generateModelID
        request.image.applyDefaults.editModelID = defaults.editModelID
        request.image.applyDefaults.size = defaults.size
        request.image.applyDefaults.steps = defaults.steps
        request.image.applyDefaults.guidance = defaults.guidance
        request.image.applyDefaults.strength = defaults.strength
        request.image.applyDefaults.negativePrompt = defaults.negativePrompt
        return request
    }

    private func makeCancelRequest(
        requestID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-cancel-\(requestID)"
        request.commandType = "ops.cancel_request"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.cancelRequest = Melix_Controlplane_V1_CancelRequest()
        request.ops.cancelRequest.requestID = requestID
        return request
    }

    private func makeRunDoctorRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-run-doctor"
        request.commandType = "ops.run_doctor"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.runDoctor = Melix_Controlplane_V1_RunDoctor()
        return request
    }

    private func makeSearchHubModelsRequest(
        query: String,
        pageSize: UInt32,
        cursor: String,
        mlxOnly: Bool
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-search-hub-models"
        request.commandType = "ops.search_hub_models"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.searchHubModels = Melix_Controlplane_V1_SearchHubModels()
        request.ops.searchHubModels.query = query
        request.ops.searchHubModels.pageSize = pageSize
        request.ops.searchHubModels.cursor = cursor
        request.ops.searchHubModels.mlxOnly = mlxOnly
        return request
    }

    private func makeGetHubModelCardRequest(
        repoID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-get-hub-model-card"
        request.commandType = "ops.get_hub_model_card"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.getHubModelCard = Melix_Controlplane_V1_GetHubModelCard()
        request.ops.getHubModelCard.repoID = repoID
        return request
    }

    private func makeRunBenchRequest(
        _ bench: ControlPlaneBenchRequest
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-run-bench"
        request.commandType = "ops.run_bench"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.runBench = Melix_Controlplane_V1_RunBench()
        request.ops.runBench.modelID = bench.modelID
        request.ops.runBench.hfRepoID = bench.hfRepoID
        request.ops.runBench.suites = bench.suites
        request.ops.runBench.contextLengths = bench.contextLengths
        request.ops.runBench.generationLength = bench.generationLength
        request.ops.runBench.batchSizes = bench.batchSizes
        request.ops.runBench.repeats = bench.repeats
        request.ops.runBench.cacheProfile = bench.cacheProfile
        request.ops.runBench.reasoningMode = bench.reasoningMode
        request.ops.runBench.structuredOutputMode = bench.structuredOutputMode
        request.ops.runBench.parameters = bench.parameters
        return request
    }

    private func makeRunBenchMatrixRequest(
        _ bench: ControlPlaneBenchMatrixRequest
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-run-bench-matrix"
        request.commandType = "ops.run_bench_matrix"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.runBenchMatrix = Melix_Controlplane_V1_RunBenchMatrix()
        request.ops.runBenchMatrix.modelID = bench.modelID
        request.ops.runBenchMatrix.hfRepoID = bench.hfRepoID
        request.ops.runBenchMatrix.taskKind = bench.taskKind
        request.ops.runBenchMatrix.suiteIds = bench.suites
        request.ops.runBenchMatrix.contextLengths = bench.contextLengths
        request.ops.runBenchMatrix.generationLengths = bench.generationLengths
        request.ops.runBenchMatrix.batchSizes = bench.batchSizes
        request.ops.runBenchMatrix.cacheProfiles = bench.cacheProfiles
        request.ops.runBenchMatrix.reasoningModes = bench.reasoningModes
        request.ops.runBenchMatrix.structuredOutputModes = bench.structuredOutputModes
        request.ops.runBenchMatrix.concurrencyLevels = bench.concurrencyLevels
        request.ops.runBenchMatrix.repeats = bench.repeats
        request.ops.runBenchMatrix.requests = bench.requests
        request.ops.runBenchMatrix.durationSeconds = bench.durationSeconds
        request.ops.runBenchMatrix.allowLargeMatrix = bench.allowLargeMatrix
        return request
    }

    private func makeRunEvaluationRequest(
        _ evaluation: ControlPlaneEvaluationRequest
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-run-eval-\(evaluation.suiteID)"
        request.commandType = "ops.run_evaluation"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.runEvaluation = Melix_Controlplane_V1_RunEvaluation()
        request.ops.runEvaluation.modelID = evaluation.modelID
        request.ops.runEvaluation.hfRepoID = evaluation.hfRepoID
        request.ops.runEvaluation.suiteID = evaluation.suiteID
        request.ops.runEvaluation.datasetID = evaluation.datasetID
        request.ops.runEvaluation.sampleSize = evaluation.sampleSize
        request.ops.runEvaluation.fewShot = UInt32(evaluation.parameters["few_shot"] ?? "") ?? 0
        request.ops.runEvaluation.seed = UInt64(evaluation.parameters["seed"] ?? "") ?? 0
        request.ops.runEvaluation.scoringMode = evaluation.parameters["scoring_mode"] ?? evaluation.profile.scoringMode
        request.ops.runEvaluation.codeExecPolicy = evaluation.parameters["code_exec_policy"] ?? ""
        switch evaluation.source.kind {
        case .builtinPackage:
            break
        case .localCSV:
            request.ops.runEvaluation.source.localCsv.path = evaluation.source.path
        case .localJSONL:
            request.ops.runEvaluation.source.localJsonl.path = evaluation.source.path
        case .huggingFaceDataset:
            request.ops.runEvaluation.source.hfDataset.datasetPath = evaluation.source.datasetPath
            request.ops.runEvaluation.source.hfDataset.datasetName = evaluation.source.datasetName
            request.ops.runEvaluation.source.hfDataset.datasetRevision = evaluation.source.datasetRevision
            request.ops.runEvaluation.source.hfDataset.split = evaluation.source.split
        }
        request.ops.runEvaluation.fieldMapping.systemPath = evaluation.fieldMapping.systemPath
        request.ops.runEvaluation.fieldMapping.inputTextPath = evaluation.fieldMapping.inputTextPath
        request.ops.runEvaluation.fieldMapping.targetPath = evaluation.fieldMapping.targetPath
        request.ops.runEvaluation.fieldMapping.sampleIDPath = evaluation.fieldMapping.sampleIDPath
        request.ops.runEvaluation.profile.profileType = evaluation.profile.profileType
        request.ops.runEvaluation.profile.resultKind = evaluation.profile.resultKind
        request.ops.runEvaluation.profile.extractionMode = evaluation.profile.extractionMode
        request.ops.runEvaluation.profile.scoringMode = evaluation.profile.scoringMode
        request.ops.runEvaluation.profile.threshold = evaluation.profile.threshold
        request.ops.runEvaluation.profile.outputSchemaJson = evaluation.profile.outputSchemaJSON
        request.ops.runEvaluation.profile.ignoredPaths = evaluation.profile.ignoredPaths
        request.ops.runEvaluation.parameters = evaluation.parameters
        if let remoteTarget = evaluation.remoteTarget {
            request.ops.runEvaluation.remoteTarget.remoteServerID = remoteTarget.remoteServerID
            request.ops.runEvaluation.remoteTarget.providerKind = remoteTarget.providerKind
            request.ops.runEvaluation.remoteTarget.baseURL = remoteTarget.baseURL
            request.ops.runEvaluation.remoteTarget.apiKey = remoteTarget.apiKey
            request.ops.runEvaluation.remoteTarget.modelID = remoteTarget.modelID
            request.ops.runEvaluation.remoteTarget.timeoutSeconds = remoteTarget.timeoutSeconds
            request.ops.runEvaluation.remoteTarget.rateLimitPerMinute = remoteTarget.rateLimitPerMinute
        }
        return request
    }

    private func makeExportResultsRequest(outputDir: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-export-results"
        request.commandType = "ops.export_results"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.exportResults = Melix_Controlplane_V1_ExportResults()
        request.ops.exportResults.outputDir = outputDir
        return request
    }

    private func makeApplyServerSessionGatewayAccessRequest(
        serverSessionID: String,
        primaryKey: String,
        keyID: String,
        label: String,
        tokenHint: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-apply-gateway-access-\(serverSessionID)"
        request.commandType = "server.apply_gateway_access"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.applyGatewayAccess = Melix_Controlplane_V1_ApplyGatewayAccess()
        request.server.applyGatewayAccess.serverSessionID = serverSessionID
        request.server.applyGatewayAccess.mode = .apiKeys
        request.server.applyGatewayAccess.sharedAccessEnabled = true
        request.server.applyGatewayAccess.primaryKey = Melix_Controlplane_V1_GatewayAccessKeyRecord()
        request.server.applyGatewayAccess.primaryKey.keyID = keyID
        request.server.applyGatewayAccess.primaryKey.label = label
        request.server.applyGatewayAccess.primaryKey.tokenHint = tokenHint
        request.server.applyGatewayAccess.primaryKey.token = primaryKey
        return request
    }

    private func makeClearServerSessionGatewayAccessRequest(
        serverSessionID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-clear-gateway-access-\(serverSessionID)"
        request.commandType = "server.apply_gateway_access"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.applyGatewayAccess = Melix_Controlplane_V1_ApplyGatewayAccess()
        request.server.applyGatewayAccess.serverSessionID = serverSessionID
        request.server.applyGatewayAccess.mode = .none
        request.server.applyGatewayAccess.sharedAccessEnabled = false
        return request
    }

    private func makeApplyServerSessionGatewayConfigRequest(
        serverSessionID: String,
        host: String,
        port: Int,
        defaultModelID: String,
        servedModelIDs: [String],
        rateLimitPerMinute: Int,
        timeoutSeconds: Int,
        modelIdleTimeoutSeconds: Int
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-apply-gateway-config-\(serverSessionID)"
        request.commandType = "server.apply_gateway_config"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.applyGatewayConfig = Melix_Controlplane_V1_ApplyGatewayConfig()
        request.server.applyGatewayConfig.serverSessionID = serverSessionID
        request.server.applyGatewayConfig.host = host
        request.server.applyGatewayConfig.port = UInt32(max(0, min(port, Int(UInt16.max))))
        request.server.applyGatewayConfig.defaultModelID = defaultModelID
        request.server.applyGatewayConfig.servedModelIds = servedModelIDs
        request.server.applyGatewayConfig.rateLimitPerMinute = UInt32(max(0, rateLimitPerMinute))
        request.server.applyGatewayConfig.timeoutSeconds = UInt32(max(0, timeoutSeconds))
        request.server.applyGatewayConfig.modelIdleTimeoutSeconds = UInt32(max(0, modelIdleTimeoutSeconds))
        return request
    }

    private func makeApplyServerSessionServingDefaultsRequest(
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
        numDraftTokens: Int
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-apply-serving-defaults-\(serverSessionID)"
        request.commandType = "server.apply_serving_defaults"
        request.targetID = serverSessionID
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.applyServingDefaults = Melix_Controlplane_V1_ApplyServingDefaults()
        request.server.applyServingDefaults.serverSessionID = serverSessionID
        request.server.applyServingDefaults.temperature = temperature
        request.server.applyServingDefaults.topP = topP
        request.server.applyServingDefaults.maxTokens = UInt32(max(0, maxTokens))
        request.server.applyServingDefaults.streamIntervalTokens = UInt32(max(0, streamIntervalTokens))
        request.server.applyServingDefaults.maxConcurrentRequests = UInt32(max(0, maxConcurrentRequests))
        request.server.applyServingDefaults.concurrentProcessingEnabled = concurrentProcessingEnabled
        request.server.applyServingDefaults.prefillBatchSize = UInt32(max(0, prefillBatchSize))
        request.server.applyServingDefaults.completionBatchSize = UInt32(max(0, completionBatchSize))
        request.server.applyServingDefaults.accelerationMode = accelerationMode
        request.server.applyServingDefaults.draftModelID = draftModelID
        request.server.applyServingDefaults.numDraftTokens = UInt32(max(0, numDraftTokens))
        return request
    }
}

private func imageEditModeProto(
    _ mode: ControlPlaneImageEditRequest.Mode
) -> Melix_Controlplane_V1_ImageEditMode {
    switch mode {
    case .edit:
        return .edit
    case .variation:
        return .variation
    case .iterate:
        return .iterate
    }
}
