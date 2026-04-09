import Foundation

public enum MelixOperatorServerSessionLifecycle: String, Codable, Sendable {
    case draft = "Draft"
    case starting = "Starting"
    case running = "Running"
    case paused = "Paused"
    case sleeping = "Sleeping"
    case stopping = "Stopping"
    case stopped = "Stopped"
    case error = "Error"
    case unavailable = "Unavailable"
}

public struct MelixOperatorServerServingDefaultsState: Codable, Equatable, Sendable {
    public var temperature: Double
    public var topP: Double
    public var maxTokens: Int
    public var streamIntervalTokens: Int
    public var maxConcurrentRequests: Int
    public var concurrentProcessingEnabled: Bool
    public var prefillBatchSize: Int
    public var completionBatchSize: Int
    public var accelerationMode: String
    public var draftModelID: String
    public var numDraftTokens: Int

    public init(
        temperature: Double = 0.7,
        topP: Double = 1.0,
        maxTokens: Int = 256,
        streamIntervalTokens: Int = 1,
        maxConcurrentRequests: Int = 4,
        concurrentProcessingEnabled: Bool = true,
        prefillBatchSize: Int = 2,
        completionBatchSize: Int = 2,
        accelerationMode: String = "baseline",
        draftModelID: String = "",
        numDraftTokens: Int = 0
    ) {
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.streamIntervalTokens = streamIntervalTokens
        self.maxConcurrentRequests = maxConcurrentRequests
        self.concurrentProcessingEnabled = concurrentProcessingEnabled
        self.prefillBatchSize = prefillBatchSize
        self.completionBatchSize = completionBatchSize
        self.accelerationMode = accelerationMode
        self.draftModelID = draftModelID
        self.numDraftTokens = numDraftTokens
    }

    enum CodingKeys: String, CodingKey {
        case temperature
        case topP = "top_p"
        case maxTokens = "max_tokens"
        case streamIntervalTokens = "stream_interval_tokens"
        case maxConcurrentRequests = "max_concurrent_requests"
        case concurrentProcessingEnabled = "concurrent_processing_enabled"
        case prefillBatchSize = "prefill_batch_size"
        case completionBatchSize = "completion_batch_size"
        case accelerationMode = "acceleration_mode"
        case draftModelID = "draft_model_id"
        case numDraftTokens = "num_draft_tokens"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            temperature: try container.decodeIfPresent(Double.self, forKey: .temperature) ?? 0.7,
            topP: try container.decodeIfPresent(Double.self, forKey: .topP) ?? 1.0,
            maxTokens: try container.decodeIfPresent(Int.self, forKey: .maxTokens) ?? 256,
            streamIntervalTokens: try container.decodeIfPresent(Int.self, forKey: .streamIntervalTokens) ?? 1,
            maxConcurrentRequests: try container.decodeIfPresent(Int.self, forKey: .maxConcurrentRequests) ?? 4,
            concurrentProcessingEnabled: try container.decodeIfPresent(Bool.self, forKey: .concurrentProcessingEnabled) ?? true,
            prefillBatchSize: try container.decodeIfPresent(Int.self, forKey: .prefillBatchSize) ?? 2,
            completionBatchSize: try container.decodeIfPresent(Int.self, forKey: .completionBatchSize) ?? 2,
            accelerationMode: try container.decodeIfPresent(String.self, forKey: .accelerationMode) ?? "baseline",
            draftModelID: try container.decodeIfPresent(String.self, forKey: .draftModelID) ?? "",
            numDraftTokens: try container.decodeIfPresent(Int.self, forKey: .numDraftTokens) ?? 0
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(temperature, forKey: .temperature)
        try container.encode(topP, forKey: .topP)
        try container.encode(maxTokens, forKey: .maxTokens)
        try container.encode(streamIntervalTokens, forKey: .streamIntervalTokens)
        try container.encode(maxConcurrentRequests, forKey: .maxConcurrentRequests)
        try container.encode(concurrentProcessingEnabled, forKey: .concurrentProcessingEnabled)
        try container.encode(prefillBatchSize, forKey: .prefillBatchSize)
        try container.encode(completionBatchSize, forKey: .completionBatchSize)
        try container.encode(accelerationMode, forKey: .accelerationMode)
        try container.encode(draftModelID, forKey: .draftModelID)
        try container.encode(numDraftTokens, forKey: .numDraftTokens)
    }
}

public struct MelixOperatorServerSessionState: Codable, Equatable, Sendable {
    public let id: String
    public var title: String
    public var modelID: String
    public var host: String
    public var port: Int
    public var rateLimitPerMinute: Int
    public var timeoutSeconds: Int
    public var servingDefaults: MelixOperatorServerServingDefaultsState
    public var autoSleepEnabled: Bool
    public var lightSleepAfterSeconds: Int
    public var deepSleepAfterSeconds: Int
    public var lifecycle: MelixOperatorServerSessionLifecycle
    public var lastError: String
    public var lastKnownModelStateText: String
    public var createdAt: Date
    public var updatedAt: Date

    public init(
        id: String,
        title: String,
        modelID: String,
        host: String = "127.0.0.1",
        port: Int = 8080,
        rateLimitPerMinute: Int = 120,
        timeoutSeconds: Int = 120,
        servingDefaults: MelixOperatorServerServingDefaultsState = .init(),
        autoSleepEnabled: Bool = false,
        lightSleepAfterSeconds: Int = 0,
        deepSleepAfterSeconds: Int = 0,
        lifecycle: MelixOperatorServerSessionLifecycle = .draft,
        lastError: String = "",
        lastKnownModelStateText: String = "",
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.modelID = modelID
        self.host = host
        self.port = port
        self.rateLimitPerMinute = rateLimitPerMinute
        self.timeoutSeconds = timeoutSeconds
        self.servingDefaults = servingDefaults
        self.autoSleepEnabled = autoSleepEnabled
        self.lightSleepAfterSeconds = lightSleepAfterSeconds
        self.deepSleepAfterSeconds = deepSleepAfterSeconds
        self.lifecycle = lifecycle
        self.lastError = lastError
        self.lastKnownModelStateText = lastKnownModelStateText
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case modelID = "model_id"
        case host
        case port
        case rateLimitPerMinute = "rate_limit_per_minute"
        case timeoutSeconds = "timeout_seconds"
        case servingDefaults = "serving_defaults"
        case autoSleepEnabled = "auto_sleep_enabled"
        case lightSleepAfterSeconds = "light_sleep_after_seconds"
        case deepSleepAfterSeconds = "deep_sleep_after_seconds"
        case lifecycle
        case lastError = "last_error"
        case lastKnownModelStateText = "last_known_model_state_text"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            id: try container.decode(String.self, forKey: .id),
            title: try container.decodeIfPresent(String.self, forKey: .title) ?? "",
            modelID: try container.decodeIfPresent(String.self, forKey: .modelID) ?? "",
            host: try container.decodeIfPresent(String.self, forKey: .host) ?? "127.0.0.1",
            port: try container.decodeIfPresent(Int.self, forKey: .port) ?? 8080,
            rateLimitPerMinute: try container.decodeIfPresent(Int.self, forKey: .rateLimitPerMinute) ?? 120,
            timeoutSeconds: try container.decodeIfPresent(Int.self, forKey: .timeoutSeconds) ?? 120,
            servingDefaults: try container.decodeIfPresent(
                MelixOperatorServerServingDefaultsState.self,
                forKey: .servingDefaults
            ) ?? .init(),
            autoSleepEnabled: try container.decodeIfPresent(Bool.self, forKey: .autoSleepEnabled) ?? false,
            lightSleepAfterSeconds: try container.decodeIfPresent(Int.self, forKey: .lightSleepAfterSeconds) ?? 0,
            deepSleepAfterSeconds: try container.decodeIfPresent(Int.self, forKey: .deepSleepAfterSeconds) ?? 0,
            lifecycle: try container.decodeIfPresent(MelixOperatorServerSessionLifecycle.self, forKey: .lifecycle) ?? .draft,
            lastError: try container.decodeIfPresent(String.self, forKey: .lastError) ?? "",
            lastKnownModelStateText: try container.decodeIfPresent(String.self, forKey: .lastKnownModelStateText) ?? "",
            createdAt: try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date(),
            updatedAt: try container.decodeIfPresent(Date.self, forKey: .updatedAt) ?? Date()
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(title, forKey: .title)
        try container.encode(modelID, forKey: .modelID)
        try container.encode(host, forKey: .host)
        try container.encode(port, forKey: .port)
        try container.encode(rateLimitPerMinute, forKey: .rateLimitPerMinute)
        try container.encode(timeoutSeconds, forKey: .timeoutSeconds)
        try container.encode(servingDefaults, forKey: .servingDefaults)
        try container.encode(autoSleepEnabled, forKey: .autoSleepEnabled)
        try container.encode(lightSleepAfterSeconds, forKey: .lightSleepAfterSeconds)
        try container.encode(deepSleepAfterSeconds, forKey: .deepSleepAfterSeconds)
        try container.encode(lifecycle, forKey: .lifecycle)
        try container.encode(lastError, forKey: .lastError)
        try container.encode(lastKnownModelStateText, forKey: .lastKnownModelStateText)
        try container.encode(createdAt, forKey: .createdAt)
        try container.encode(updatedAt, forKey: .updatedAt)
    }
}

public struct MelixOperatorDownloadQueueEntryState: Codable, Equatable, Sendable {
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

    public init(
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
        resumeUsed: Bool,
        resumeFromBytes: Int,
        retryCount: Int,
        stallDetectionCount: Int,
        stallReason: String,
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

public struct MelixOperatorSessionState: Codable, Equatable, Sendable {
    public var schemaVersion: Int
    public var selectedSurfaceID: String
    public var selectedToolSectionID: String
    public var selectedServerSessionID: String
    public var serverSessions: [MelixOperatorServerSessionState]
    public var dismissedBannerIDs: [String]
    public var downloadQueue: [MelixOperatorDownloadQueueEntryState]
    public var registryRoots: [String]

    public init(
        schemaVersion: Int = 4,
        selectedSurfaceID: String = "chat",
        selectedToolSectionID: String = "modelsLibrary",
        selectedServerSessionID: String,
        serverSessions: [MelixOperatorServerSessionState],
        dismissedBannerIDs: [String] = [],
        downloadQueue: [MelixOperatorDownloadQueueEntryState] = [],
        registryRoots: [String] = []
    ) {
        self.schemaVersion = schemaVersion
        self.selectedSurfaceID = selectedSurfaceID
        self.selectedToolSectionID = selectedToolSectionID
        self.selectedServerSessionID = selectedServerSessionID
        self.serverSessions = serverSessions
        self.dismissedBannerIDs = dismissedBannerIDs
        self.downloadQueue = downloadQueue
        self.registryRoots = registryRoots
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case selectedSurfaceID = "selected_surface"
        case selectedToolSectionID = "selected_tool_section"
        case selectedServerSessionID = "selected_server_session_id"
        case serverSessions = "server_sessions"
        case dismissedBannerIDs = "dismissed_banner_ids"
        case downloadQueue = "download_queue"
        case registryRoots = "registry_roots"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            schemaVersion: try container.decodeIfPresent(Int.self, forKey: .schemaVersion) ?? 4,
            selectedSurfaceID: try container.decodeIfPresent(String.self, forKey: .selectedSurfaceID) ?? "chat",
            selectedToolSectionID: try container.decodeIfPresent(String.self, forKey: .selectedToolSectionID) ?? "modelsLibrary",
            selectedServerSessionID: try container.decodeIfPresent(String.self, forKey: .selectedServerSessionID) ?? "",
            serverSessions: try container.decodeIfPresent([MelixOperatorServerSessionState].self, forKey: .serverSessions) ?? [],
            dismissedBannerIDs: try container.decodeIfPresent([String].self, forKey: .dismissedBannerIDs) ?? [],
            downloadQueue: try container.decodeIfPresent([MelixOperatorDownloadQueueEntryState].self, forKey: .downloadQueue) ?? [],
            registryRoots: try container.decodeIfPresent([String].self, forKey: .registryRoots) ?? []
        )
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(schemaVersion, forKey: .schemaVersion)
        try container.encode(selectedSurfaceID, forKey: .selectedSurfaceID)
        try container.encode(selectedToolSectionID, forKey: .selectedToolSectionID)
        try container.encode(selectedServerSessionID, forKey: .selectedServerSessionID)
        try container.encode(serverSessions, forKey: .serverSessions)
        try container.encode(dismissedBannerIDs, forKey: .dismissedBannerIDs)
        try container.encode(downloadQueue, forKey: .downloadQueue)
        try container.encode(registryRoots, forKey: .registryRoots)
    }
}

public protocol MelixOperatorSessionStoring: Sendable {
    func load() throws -> MelixOperatorSessionState?
    func save(_ state: MelixOperatorSessionState) throws
}

public struct NullMelixOperatorSessionStore: MelixOperatorSessionStoring {
    public init() {}

    public func load() throws -> MelixOperatorSessionState? {
        nil
    }

    public func save(_ state: MelixOperatorSessionState) throws {
        _ = state
    }
}

public struct MelixOperatorSessionStore: MelixOperatorSessionStoring {
    private let melixHome: MelixHome

    public init(melixHome: MelixHome) {
        self.melixHome = melixHome
    }

    public func load() throws -> MelixOperatorSessionState? {
        let fileManager = FileManager.default
        let fileURL = melixHome.operatorSessionFileURL
        guard fileManager.fileExists(atPath: fileURL.path) else {
            return nil
        }
        let data = try Data(contentsOf: fileURL)
        return try Self.decoder.decode(MelixOperatorSessionState.self, from: data)
    }

    public func save(_ state: MelixOperatorSessionState) throws {
        let data = try Self.encoder.encode(state)
        try melixHome.writeAtomically(data, to: melixHome.operatorSessionFileURL)
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}
