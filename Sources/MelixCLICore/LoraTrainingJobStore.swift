import Foundation

public enum LoraTrainingJobStatus: String, Codable, CaseIterable, Sendable {
    case draft
    case running
    case succeeded
    case failed
    case canceled

    public var isTerminal: Bool {
        switch self {
        case .succeeded, .failed, .canceled:
            return true
        case .draft, .running:
            return false
        }
    }

    public var allowsMutation: Bool {
        self != .running
    }
}

public struct LoraTrainingJobConfig: Codable, Equatable, Sendable {
    public static let schemaVersion = "melix.desktop_lora_training_config.v1"

    public var schemaVersion: String
    public var modelID: String
    public var datasetSourceKind: String
    public var datasetURI: String
    public var hfDatasetPath: String
    public var hfDatasetName: String
    public var hfDatasetRevision: String
    public var hfTrainSplit: String
    public var hfValidSplit: String
    public var chatFeature: String
    public var promptFeature: String
    public var completionFeature: String
    public var textFeature: String
    public var adapterName: String
    public var targetRepo: String
    public var experimentGroupID: String
    public var resumeManifestPath: String
    public var trainingMode: String
    public var presetID: String
    public var activationMode: String
    public var rank: String
    public var alpha: String
    public var dropout: String
    public var targetModules: String
    public var numLayers: String
    public var batchSize: String
    public var epochs: String
    public var learningRate: String
    public var maxSeqLength: String
    public var responseOnly: Bool
    public var maskPrompt: Bool
    public var gradientCheckpointing: Bool
    public var derivedModelAlias: String

    public init(
        schemaVersion: String = Self.schemaVersion,
        modelID: String,
        datasetSourceKind: String,
        datasetURI: String = "",
        hfDatasetPath: String = "",
        hfDatasetName: String = "",
        hfDatasetRevision: String = "",
        hfTrainSplit: String = "",
        hfValidSplit: String = "",
        chatFeature: String = "",
        promptFeature: String = "",
        completionFeature: String = "",
        textFeature: String = "",
        adapterName: String,
        targetRepo: String = "",
        experimentGroupID: String = "",
        resumeManifestPath: String = "",
        trainingMode: String,
        presetID: String = "",
        activationMode: String,
        rank: String = "",
        alpha: String = "",
        dropout: String = "",
        targetModules: String = "",
        numLayers: String = "",
        batchSize: String = "",
        epochs: String = "",
        learningRate: String = "",
        maxSeqLength: String = "",
        responseOnly: Bool = true,
        maskPrompt: Bool = false,
        gradientCheckpointing: Bool = false,
        derivedModelAlias: String = ""
    ) {
        self.schemaVersion = schemaVersion
        self.modelID = modelID
        self.datasetSourceKind = datasetSourceKind
        self.datasetURI = datasetURI
        self.hfDatasetPath = hfDatasetPath
        self.hfDatasetName = hfDatasetName
        self.hfDatasetRevision = hfDatasetRevision
        self.hfTrainSplit = hfTrainSplit
        self.hfValidSplit = hfValidSplit
        self.chatFeature = chatFeature
        self.promptFeature = promptFeature
        self.completionFeature = completionFeature
        self.textFeature = textFeature
        self.adapterName = adapterName
        self.targetRepo = targetRepo
        self.experimentGroupID = experimentGroupID
        self.resumeManifestPath = resumeManifestPath
        self.trainingMode = trainingMode
        self.presetID = presetID
        self.activationMode = activationMode
        self.rank = rank
        self.alpha = alpha
        self.dropout = dropout
        self.targetModules = targetModules
        self.numLayers = numLayers
        self.batchSize = batchSize
        self.epochs = epochs
        self.learningRate = learningRate
        self.maxSeqLength = maxSeqLength
        self.responseOnly = responseOnly
        self.maskPrompt = maskPrompt
        self.gradientCheckpointing = gradientCheckpointing
        self.derivedModelAlias = derivedModelAlias
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case modelID = "model_id"
        case datasetSourceKind = "dataset_source_kind"
        case datasetURI = "dataset_uri"
        case hfDatasetPath = "hf_dataset_path"
        case hfDatasetName = "hf_dataset_name"
        case hfDatasetRevision = "hf_dataset_revision"
        case hfTrainSplit = "hf_train_split"
        case hfValidSplit = "hf_valid_split"
        case chatFeature = "chat_feature"
        case promptFeature = "prompt_feature"
        case completionFeature = "completion_feature"
        case textFeature = "text_feature"
        case adapterName = "adapter_name"
        case targetRepo = "target_repo"
        case experimentGroupID = "experiment_group_id"
        case resumeManifestPath = "resume_manifest_path"
        case trainingMode = "training_mode"
        case presetID = "preset_id"
        case activationMode = "activation_mode"
        case rank
        case alpha
        case dropout
        case targetModules = "target_modules"
        case numLayers = "num_layers"
        case batchSize = "batch_size"
        case epochs
        case learningRate = "learning_rate"
        case maxSeqLength = "max_seq_length"
        case responseOnly = "response_only"
        case maskPrompt = "mask_prompt"
        case gradientCheckpointing = "gradient_checkpointing"
        case derivedModelAlias = "derived_model_alias"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? Self.schemaVersion
        guard schemaVersion == Self.schemaVersion else {
            throw MelixCLIError.runtime("Unsupported LoRA training config schema: \(schemaVersion)")
        }
        self.init(
            schemaVersion: schemaVersion,
            modelID: try container.decodeIfPresent(String.self, forKey: .modelID) ?? "",
            datasetSourceKind: try container.decodeIfPresent(String.self, forKey: .datasetSourceKind) ?? "local_package",
            datasetURI: try container.decodeIfPresent(String.self, forKey: .datasetURI) ?? "",
            hfDatasetPath: try container.decodeIfPresent(String.self, forKey: .hfDatasetPath) ?? "",
            hfDatasetName: try container.decodeIfPresent(String.self, forKey: .hfDatasetName) ?? "",
            hfDatasetRevision: try container.decodeIfPresent(String.self, forKey: .hfDatasetRevision) ?? "",
            hfTrainSplit: try container.decodeIfPresent(String.self, forKey: .hfTrainSplit) ?? "",
            hfValidSplit: try container.decodeIfPresent(String.self, forKey: .hfValidSplit) ?? "",
            chatFeature: try container.decodeIfPresent(String.self, forKey: .chatFeature) ?? "",
            promptFeature: try container.decodeIfPresent(String.self, forKey: .promptFeature) ?? "",
            completionFeature: try container.decodeIfPresent(String.self, forKey: .completionFeature) ?? "",
            textFeature: try container.decodeIfPresent(String.self, forKey: .textFeature) ?? "",
            adapterName: try container.decodeIfPresent(String.self, forKey: .adapterName) ?? "",
            targetRepo: try container.decodeIfPresent(String.self, forKey: .targetRepo) ?? "",
            experimentGroupID: try container.decodeIfPresent(String.self, forKey: .experimentGroupID) ?? "",
            resumeManifestPath: try container.decodeIfPresent(String.self, forKey: .resumeManifestPath) ?? "",
            trainingMode: try container.decodeIfPresent(String.self, forKey: .trainingMode) ?? "lora",
            presetID: try container.decodeIfPresent(String.self, forKey: .presetID) ?? "",
            activationMode: try container.decodeIfPresent(String.self, forKey: .activationMode) ?? "fused_derived_model",
            rank: try container.decodeIfPresent(String.self, forKey: .rank) ?? "",
            alpha: try container.decodeIfPresent(String.self, forKey: .alpha) ?? "",
            dropout: try container.decodeIfPresent(String.self, forKey: .dropout) ?? "",
            targetModules: try container.decodeIfPresent(String.self, forKey: .targetModules) ?? "",
            numLayers: try container.decodeIfPresent(String.self, forKey: .numLayers) ?? "",
            batchSize: try container.decodeIfPresent(String.self, forKey: .batchSize) ?? "",
            epochs: try container.decodeIfPresent(String.self, forKey: .epochs) ?? "",
            learningRate: try container.decodeIfPresent(String.self, forKey: .learningRate) ?? "",
            maxSeqLength: try container.decodeIfPresent(String.self, forKey: .maxSeqLength) ?? "",
            responseOnly: try container.decodeIfPresent(Bool.self, forKey: .responseOnly) ?? true,
            maskPrompt: try container.decodeIfPresent(Bool.self, forKey: .maskPrompt) ?? false,
            gradientCheckpointing: try container.decodeIfPresent(Bool.self, forKey: .gradientCheckpointing) ?? false,
            derivedModelAlias: try container.decodeIfPresent(String.self, forKey: .derivedModelAlias) ?? ""
        )
    }
}

public struct LoraTrainingFollowUpArtifacts: Codable, Equatable, Sendable {
    public var adapterManifestPath: String
    public var derivedModelID: String
    public var derivedModelPath: String
    public var quantizedArtifactPath: String
    public var convertedArtifactPath: String
    public var benchmarkJobID: String
    public var evaluationJobID: String
    public var publishedRepo: String

    public init(
        adapterManifestPath: String = "",
        derivedModelID: String = "",
        derivedModelPath: String = "",
        quantizedArtifactPath: String = "",
        convertedArtifactPath: String = "",
        benchmarkJobID: String = "",
        evaluationJobID: String = "",
        publishedRepo: String = ""
    ) {
        self.adapterManifestPath = adapterManifestPath
        self.derivedModelID = derivedModelID
        self.derivedModelPath = derivedModelPath
        self.quantizedArtifactPath = quantizedArtifactPath
        self.convertedArtifactPath = convertedArtifactPath
        self.benchmarkJobID = benchmarkJobID
        self.evaluationJobID = evaluationJobID
        self.publishedRepo = publishedRepo
    }

    enum CodingKeys: String, CodingKey {
        case adapterManifestPath = "adapter_manifest_path"
        case derivedModelID = "derived_model_id"
        case derivedModelPath = "derived_model_path"
        case quantizedArtifactPath = "quantized_artifact_path"
        case convertedArtifactPath = "converted_artifact_path"
        case benchmarkJobID = "benchmark_job_id"
        case evaluationJobID = "evaluation_job_id"
        case publishedRepo = "published_repo"
    }
}

public struct LoraTrainingJobRecord: Codable, Identifiable, Equatable, Sendable {
    public var id: String
    public var title: String
    public var config: LoraTrainingJobConfig
    public var status: LoraTrainingJobStatus
    public var createdAt: Date
    public var updatedAt: Date
    public var startedAt: Date?
    public var completedAt: Date?
    public var lastRunJobID: String
    public var outputPath: String
    public var manifestPath: String
    public var latestOutputText: String
    public var terminalMessage: String
    public var followUpArtifacts: LoraTrainingFollowUpArtifacts

    public init(
        id: String,
        title: String,
        config: LoraTrainingJobConfig,
        status: LoraTrainingJobStatus = .draft,
        createdAt: Date = Date(),
        updatedAt: Date = Date(),
        startedAt: Date? = nil,
        completedAt: Date? = nil,
        lastRunJobID: String = "",
        outputPath: String = "",
        manifestPath: String = "",
        latestOutputText: String = "",
        terminalMessage: String = "",
        followUpArtifacts: LoraTrainingFollowUpArtifacts = .init()
    ) {
        self.id = id
        self.title = title
        self.config = config
        self.status = status
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.startedAt = startedAt
        self.completedAt = completedAt
        self.lastRunJobID = lastRunJobID
        self.outputPath = outputPath
        self.manifestPath = manifestPath
        self.latestOutputText = latestOutputText
        self.terminalMessage = terminalMessage
        self.followUpArtifacts = followUpArtifacts
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case config
        case status
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case startedAt = "started_at"
        case completedAt = "completed_at"
        case lastRunJobID = "last_run_job_id"
        case outputPath = "output_path"
        case manifestPath = "manifest_path"
        case latestOutputText = "latest_output_text"
        case terminalMessage = "terminal_message"
        case followUpArtifacts = "follow_up_artifacts"
    }
}

private struct LoraTrainingJobsDocument: Codable {
    static let schemaVersion = "melix.desktop_lora_training_jobs.v1"

    var schemaVersion: String
    var jobs: [LoraTrainingJobRecord]

    init(schemaVersion: String = Self.schemaVersion, jobs: [LoraTrainingJobRecord] = []) {
        self.schemaVersion = schemaVersion
        self.jobs = jobs
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobs
    }

    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? Self.schemaVersion
        guard schemaVersion == Self.schemaVersion else {
            throw MelixCLIError.runtime("Unsupported LoRA training jobs schema: \(schemaVersion)")
        }
        self.init(
            schemaVersion: schemaVersion,
            jobs: try container.decodeIfPresent([LoraTrainingJobRecord].self, forKey: .jobs) ?? []
        )
    }
}

public struct LoraTrainingJobStore: Sendable {
    private let melixHome: MelixHome

    public init(melixHome: MelixHome) {
        self.melixHome = melixHome
    }

    public func list() throws -> [LoraTrainingJobRecord] {
        try loadDocument().jobs.sorted { lhs, rhs in
            if lhs.updatedAt == rhs.updatedAt {
                return lhs.title < rhs.title
            }
            return lhs.updatedAt > rhs.updatedAt
        }
    }

    public func get(id: String) throws -> LoraTrainingJobRecord? {
        let normalizedID = try Self.normalizedRequired(id, fieldName: "job_id")
        return try list().first { $0.id == normalizedID }
    }

    @discardableResult
    public func save(_ record: LoraTrainingJobRecord) throws -> LoraTrainingJobRecord {
        let normalizedID = try Self.normalizedRequired(record.id, fieldName: "job_id")
        let normalizedTitle = Self.normalizedTitle(record.title, config: record.config)
        var updated = record
        updated.id = normalizedID
        updated.title = normalizedTitle
        updated.updatedAt = Date()

        var document = try loadDocument()
        document.jobs.removeAll { $0.id == normalizedID }
        document.jobs.append(updated)
        document.jobs.sort { $0.updatedAt > $1.updatedAt }
        try saveDocument(document)
        return updated
    }

    @discardableResult
    public func createDraft(title: String, config: LoraTrainingJobConfig) throws -> LoraTrainingJobRecord {
        let now = Date()
        let record = LoraTrainingJobRecord(
            id: Self.makeJobID(title: title, config: config),
            title: Self.normalizedTitle(title, config: config),
            config: config,
            status: .draft,
            createdAt: now,
            updatedAt: now
        )
        return try save(record)
    }

    @discardableResult
    public func duplicate(id: String) throws -> LoraTrainingJobRecord {
        guard let source = try get(id: id) else {
            throw MelixCLIError.missingRequired("LoRA training job \(id) was not found.")
        }
        let now = Date()
        let copy = LoraTrainingJobRecord(
            id: Self.makeJobID(title: "\(source.title) Copy", config: source.config),
            title: "\(source.title) Copy",
            config: source.config,
            status: .draft,
            createdAt: now,
            updatedAt: now
        )
        return try save(copy)
    }

    public func delete(id: String) throws {
        let normalizedID = try Self.normalizedRequired(id, fieldName: "job_id")
        var document = try loadDocument()
        document.jobs.removeAll { $0.id == normalizedID }
        try saveDocument(document)
    }

    @discardableResult
    public func importConfig(from fileURL: URL) throws -> LoraTrainingJobConfig {
        let data = try Data(contentsOf: fileURL)
        return try Self.decoder.decode(LoraTrainingJobConfig.self, from: data)
    }

    public func exportConfig(_ config: LoraTrainingJobConfig, to fileURL: URL) throws {
        let data = try Self.encoder.encode(config)
        try melixHome.writeAtomically(data, to: fileURL)
    }

    private func loadDocument() throws -> LoraTrainingJobsDocument {
        guard FileManager.default.fileExists(atPath: melixHome.loraTrainingJobsFileURL.path) else {
            return LoraTrainingJobsDocument()
        }
        let data = try Data(contentsOf: melixHome.loraTrainingJobsFileURL)
        return try Self.decoder.decode(LoraTrainingJobsDocument.self, from: data)
    }

    private func saveDocument(_ document: LoraTrainingJobsDocument) throws {
        let data = try Self.encoder.encode(document)
        try melixHome.writeAtomically(data, to: melixHome.loraTrainingJobsFileURL)
    }

    private static func normalizedRequired(_ value: String, fieldName: String) throws -> String {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalized.isEmpty == false else {
            throw MelixCLIError.missingRequired("\(fieldName) must not be empty.")
        }
        return normalized
    }

    private static func normalizedTitle(_ title: String, config: LoraTrainingJobConfig) -> String {
        let trimmedTitle = title.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmedTitle.isEmpty == false {
            return trimmedTitle
        }
        let adapterName = config.adapterName.trimmingCharacters(in: .whitespacesAndNewlines)
        if adapterName.isEmpty == false {
            return adapterName
        }
        return "LoRA Training Job"
    }

    private static func makeJobID(title: String, config: LoraTrainingJobConfig) -> String {
        let base = normalizedTitle(title, config: config)
            .lowercased()
            .map { character -> Character in
                character.isLetter || character.isNumber ? character : "-"
            }
        let slug = String(base)
            .split(separator: "-")
            .joined(separator: "-")
        let prefix = slug.isEmpty ? "lora-job" : slug
        return "\(prefix)-\(UUID().uuidString.prefix(8).lowercased())"
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()
}
