import CryptoKit
import Foundation

public enum EvaluationPromptRevisionStatus: String, Codable, Equatable, Sendable {
    case draft
    case frozen
}

public struct EvaluationPromptExampleEvent: Codable, Equatable, Sendable {
    public let actor: [String]?
    public let time: [String]?
    public let location: [String]?
    public let action: [String]?

    public init(
        actor: [String]? = nil,
        time: [String]? = nil,
        location: [String]? = nil,
        action: [String]? = nil
    ) {
        self.actor = actor
        self.time = time
        self.location = location
        self.action = action
    }
}

public struct EvaluationPromptExample: Codable, Equatable, Sendable {
    public let dialogueID: String
    public let dialogue: [String]
    public let events: [EvaluationPromptExampleEvent]

    public init(dialogueID: String, dialogue: [String], events: [EvaluationPromptExampleEvent]) {
        self.dialogueID = dialogueID
        self.dialogue = dialogue
        self.events = events
    }

    enum CodingKeys: String, CodingKey {
        case dialogueID = "dialogue_id"
        case dialogue
        case events
    }
}

public struct EvaluationPromptRevision: Codable, Equatable, Sendable, Identifiable {
    public let revisionID: String
    public let status: EvaluationPromptRevisionStatus
    public let systemPrompt: String
    public let examples: [EvaluationPromptExample]
    public let contentHash: String
    public let createdAt: Date
    public let updatedAt: Date

    public var id: String { revisionID }

    public init(
        revisionID: String,
        status: EvaluationPromptRevisionStatus,
        systemPrompt: String,
        examples: [EvaluationPromptExample] = [],
        contentHash: String,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.revisionID = revisionID
        self.status = status
        self.systemPrompt = systemPrompt
        self.examples = examples
        self.contentHash = contentHash
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    enum CodingKeys: String, CodingKey {
        case revisionID = "revision_id"
        case status
        case systemPrompt = "system_prompt"
        case examples
        case contentHash = "content_hash"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

public struct EvaluationPrompt: Codable, Equatable, Sendable, Identifiable {
    public let id: String
    public let title: String
    public let taskKind: String
    public let scoringMode: String
    public let latestRevisionID: String
    public let archived: Bool
    public let readOnly: Bool
    public let revisions: [EvaluationPromptRevision]
    public let createdAt: Date
    public let updatedAt: Date

    public init(
        id: String,
        title: String,
        taskKind: String = EvaluationPromptStore.eventExtractionTaskKind,
        scoringMode: String = EvaluationPromptStore.eventExtractionScoringMode,
        latestRevisionID: String,
        archived: Bool = false,
        readOnly: Bool = false,
        revisions: [EvaluationPromptRevision],
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.taskKind = taskKind
        self.scoringMode = scoringMode
        self.latestRevisionID = latestRevisionID
        self.archived = archived
        self.readOnly = readOnly
        self.revisions = revisions
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    public var latestRevision: EvaluationPromptRevision? {
        revisions.first { $0.revisionID == latestRevisionID } ?? revisions.last
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case taskKind = "task_kind"
        case scoringMode = "scoring_mode"
        case latestRevisionID = "latest_revision_id"
        case archived
        case readOnly = "read_only"
        case revisions
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

public struct EvaluationPromptSnapshot: Codable, Equatable, Sendable {
    public let promptID: String
    public let title: String
    public let taskKind: String
    public let scoringMode: String
    public let revisionID: String
    public let status: EvaluationPromptRevisionStatus
    public let systemPrompt: String
    public let examples: [EvaluationPromptExample]
    public let contentHash: String
    public let readOnly: Bool

    public init(prompt: EvaluationPrompt, revision: EvaluationPromptRevision) {
        self.promptID = prompt.id
        self.title = prompt.title
        self.taskKind = prompt.taskKind
        self.scoringMode = prompt.scoringMode
        self.revisionID = revision.revisionID
        self.status = revision.status
        self.systemPrompt = revision.systemPrompt
        self.examples = revision.examples
        self.contentHash = revision.contentHash
        self.readOnly = prompt.readOnly
    }

    enum CodingKeys: String, CodingKey {
        case promptID = "prompt_id"
        case title
        case taskKind = "task_kind"
        case scoringMode = "scoring_mode"
        case revisionID = "revision_id"
        case status
        case systemPrompt = "system_prompt"
        case examples
        case contentHash = "content_hash"
        case readOnly = "read_only"
    }
}

public struct EvaluationPromptStore: Sendable {
    public static let eventExtractionTaskKind = "event_extraction"
    public static let eventExtractionScoringMode = "event_extraction_weighted_f1"
    public static let builtInBaselinePromptID = "builtin.event-extraction.baseline"
    public static let builtInBaselineRevisionID = "baseline.v1"
    public static let builtInBaselineSystemPrompt = """
    Extract established events and future plans from a dialogue.

    Return only one JSON object. Do not wrap it in markdown.

    Required shape:
    {"events":[{"actor":null|["..."],"time":null|["..."],"location":null|["..."],"action":null|["..."]}]}

    Rules:
    - Extract only events or plans stated in the dialogue.
    - Split each event into actor, time, location, and action arrays.
    - Use null when a field is absent.
    - Keep original wording as much as possible.
    - Do not include digest; Melix derives it locally.
    """

    private let melixHome: MelixHome

    public init(melixHome: MelixHome) {
        self.melixHome = melixHome
    }

    public func list(includeArchived: Bool = false) throws -> [EvaluationPrompt] {
        let customPrompts = try loadDocument().prompts
            .filter { includeArchived || $0.archived == false }
            .sorted { $0.id < $1.id }
        return [Self.builtInBaselinePrompt] + customPrompts
    }

    public func get(id: String) throws -> EvaluationPrompt? {
        let normalizedID = try Self.normalizedRequired(id, fieldName: "prompt_id")
        if normalizedID == Self.builtInBaselinePromptID {
            return Self.builtInBaselinePrompt
        }
        return try loadDocument().prompts.first { $0.id == normalizedID }
    }

    public func resolveForRun(promptID: String = "", revisionID: String = "") throws -> EvaluationPromptSnapshot {
        let normalizedPromptID = promptID.trimmingCharacters(in: .whitespacesAndNewlines)
        let prompt = try get(id: normalizedPromptID.isEmpty ? Self.builtInBaselinePromptID : normalizedPromptID)
        guard let prompt else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedPromptID) was not found.")
        }
        guard prompt.archived == false else {
            throw MelixCLIError.runtime("Evaluation prompt \(prompt.id) is archived.")
        }
        let revision = try Self.revision(
            in: prompt,
            revisionID: revisionID,
            fallbackToLatest: true
        )
        guard revision.status == .frozen else {
            throw MelixCLIError.runtime("Evaluation prompt \(prompt.id) revision \(revision.revisionID) is not frozen.")
        }
        return EvaluationPromptSnapshot(prompt: prompt, revision: revision)
    }

    @discardableResult
    public func create(promptID: String, title: String, systemPrompt: String) throws -> EvaluationPrompt {
        let normalizedID = try Self.normalizedRequired(promptID, fieldName: "prompt_id")
        let normalizedTitle = try Self.normalizedRequired(title, fieldName: "title")
        let normalizedPrompt = try Self.normalizedRequired(systemPrompt, fieldName: "system_prompt")
        guard normalizedID != Self.builtInBaselinePromptID else {
            throw MelixCLIError.runtime("The built-in evaluation prompt is read-only.")
        }
        var document = try loadDocument()
        guard document.prompts.contains(where: { $0.id == normalizedID }) == false else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) already exists.")
        }
        let now = Date()
        let revision = Self.makeRevision(
            revisionID: "rev-1",
            status: .draft,
            systemPrompt: normalizedPrompt,
            examples: [],
            createdAt: now,
            updatedAt: now
        )
        let prompt = EvaluationPrompt(
            id: normalizedID,
            title: normalizedTitle,
            latestRevisionID: revision.revisionID,
            revisions: [revision],
            createdAt: now,
            updatedAt: now
        )
        document.prompts.append(prompt)
        document.prompts.sort { $0.id < $1.id }
        try saveDocument(document)
        return prompt
    }

    @discardableResult
    public func update(promptID: String, systemPrompt: String) throws -> EvaluationPrompt {
        let normalizedID = try Self.normalizedRequired(promptID, fieldName: "prompt_id")
        let normalizedPrompt = try Self.normalizedRequired(systemPrompt, fieldName: "system_prompt")
        guard normalizedID != Self.builtInBaselinePromptID else {
            throw MelixCLIError.runtime("The built-in evaluation prompt is read-only.")
        }
        var document = try loadDocument()
        guard let promptIndex = document.prompts.firstIndex(where: { $0.id == normalizedID }) else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) was not found.")
        }
        let prompt = document.prompts[promptIndex]
        guard prompt.archived == false else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) is archived.")
        }
        let now = Date()
        var revisions = prompt.revisions
        var latestRevisionID = prompt.latestRevisionID
        if let latestIndex = revisions.firstIndex(where: { $0.revisionID == prompt.latestRevisionID }),
           revisions[latestIndex].status == .draft
        {
            let existing = revisions[latestIndex]
            revisions[latestIndex] = Self.makeRevision(
                revisionID: existing.revisionID,
                status: .draft,
                systemPrompt: normalizedPrompt,
                examples: existing.examples,
                createdAt: existing.createdAt,
                updatedAt: now
            )
        } else {
            let baseExamples = prompt.latestRevision?.examples ?? []
            let revisionID = "rev-\(revisions.count + 1)"
            let revision = Self.makeRevision(
                revisionID: revisionID,
                status: .draft,
                systemPrompt: normalizedPrompt,
                examples: baseExamples,
                createdAt: now,
                updatedAt: now
            )
            revisions.append(revision)
            latestRevisionID = revisionID
        }
        document.prompts[promptIndex] = EvaluationPrompt(
            id: prompt.id,
            title: prompt.title,
            taskKind: prompt.taskKind,
            scoringMode: prompt.scoringMode,
            latestRevisionID: latestRevisionID,
            archived: false,
            readOnly: false,
            revisions: revisions,
            createdAt: prompt.createdAt,
            updatedAt: now
        )
        try saveDocument(document)
        return document.prompts[promptIndex]
    }

    @discardableResult
    public func freeze(promptID: String, revisionID: String = "") throws -> EvaluationPrompt {
        let normalizedID = try Self.normalizedRequired(promptID, fieldName: "prompt_id")
        guard normalizedID != Self.builtInBaselinePromptID else {
            return Self.builtInBaselinePrompt
        }
        var document = try loadDocument()
        guard let promptIndex = document.prompts.firstIndex(where: { $0.id == normalizedID }) else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) was not found.")
        }
        let prompt = document.prompts[promptIndex]
        guard prompt.archived == false else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) is archived.")
        }
        let revision = try Self.revision(in: prompt, revisionID: revisionID, fallbackToLatest: true)
        guard revision.status == .draft else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) revision \(revision.revisionID) is already frozen.")
        }
        var revisions = prompt.revisions
        let now = Date()
        guard let revisionIndex = revisions.firstIndex(where: { $0.revisionID == revision.revisionID }) else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) revision \(revision.revisionID) was not found.")
        }
        revisions[revisionIndex] = Self.makeRevision(
            revisionID: revision.revisionID,
            status: .frozen,
            systemPrompt: revision.systemPrompt,
            examples: revision.examples,
            createdAt: revision.createdAt,
            updatedAt: now
        )
        document.prompts[promptIndex] = EvaluationPrompt(
            id: prompt.id,
            title: prompt.title,
            taskKind: prompt.taskKind,
            scoringMode: prompt.scoringMode,
            latestRevisionID: revision.revisionID,
            archived: false,
            readOnly: false,
            revisions: revisions,
            createdAt: prompt.createdAt,
            updatedAt: now
        )
        try saveDocument(document)
        return document.prompts[promptIndex]
    }

    @discardableResult
    public func archive(promptID: String) throws -> EvaluationPrompt {
        let normalizedID = try Self.normalizedRequired(promptID, fieldName: "prompt_id")
        guard normalizedID != Self.builtInBaselinePromptID else {
            throw MelixCLIError.runtime("The built-in evaluation prompt is read-only.")
        }
        var document = try loadDocument()
        guard let promptIndex = document.prompts.firstIndex(where: { $0.id == normalizedID }) else {
            throw MelixCLIError.runtime("Evaluation prompt \(normalizedID) was not found.")
        }
        let prompt = document.prompts[promptIndex]
        let now = Date()
        document.prompts[promptIndex] = EvaluationPrompt(
            id: prompt.id,
            title: prompt.title,
            taskKind: prompt.taskKind,
            scoringMode: prompt.scoringMode,
            latestRevisionID: prompt.latestRevisionID,
            archived: true,
            readOnly: false,
            revisions: prompt.revisions,
            createdAt: prompt.createdAt,
            updatedAt: now
        )
        try saveDocument(document)
        return document.prompts[promptIndex]
    }

    public static func contentHash(
        taskKind: String = eventExtractionTaskKind,
        scoringMode: String = eventExtractionScoringMode,
        systemPrompt: String,
        examples: [EvaluationPromptExample] = []
    ) -> String {
        let payload = EvaluationPromptHashPayload(
            taskKind: taskKind,
            scoringMode: scoringMode,
            systemPrompt: systemPrompt,
            examples: examples
        )
        let data = (try? hashEncoder.encode(payload)) ?? Data()
        let digest = SHA256.hash(data: data)
        return "sha256:" + digest.map { String(format: "%02x", $0) }.joined()
    }

    public static func examplesJSONString(_ examples: [EvaluationPromptExample]) throws -> String {
        guard examples.isEmpty == false else {
            return "[]"
        }
        let data = try hashEncoder.encode(examples)
        return String(decoding: data, as: UTF8.self)
    }

    public static var builtInBaselinePrompt: EvaluationPrompt {
        let revision = makeRevision(
            revisionID: builtInBaselineRevisionID,
            status: .frozen,
            systemPrompt: builtInBaselineSystemPrompt,
            examples: [],
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
        return EvaluationPrompt(
            id: builtInBaselinePromptID,
            title: "Built-in Event Extraction Baseline",
            latestRevisionID: revision.revisionID,
            archived: false,
            readOnly: true,
            revisions: [revision],
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
    }

    private func loadDocument() throws -> EvaluationPromptDocument {
        guard FileManager.default.fileExists(atPath: melixHome.evaluationPromptsFileURL.path) else {
            return EvaluationPromptDocument()
        }
        let data = try Data(contentsOf: melixHome.evaluationPromptsFileURL)
        return try Self.decoder.decode(EvaluationPromptDocument.self, from: data)
    }

    private func saveDocument(_ document: EvaluationPromptDocument) throws {
        let data = try Self.encoder.encode(document)
        try melixHome.writeAtomically(data, to: melixHome.evaluationPromptsFileURL)
    }

    private static func makeRevision(
        revisionID: String,
        status: EvaluationPromptRevisionStatus,
        systemPrompt: String,
        examples: [EvaluationPromptExample],
        createdAt: Date,
        updatedAt: Date
    ) -> EvaluationPromptRevision {
        EvaluationPromptRevision(
            revisionID: revisionID,
            status: status,
            systemPrompt: systemPrompt,
            examples: examples,
            contentHash: contentHash(systemPrompt: systemPrompt, examples: examples),
            createdAt: createdAt,
            updatedAt: updatedAt
        )
    }

    private static func revision(
        in prompt: EvaluationPrompt,
        revisionID: String,
        fallbackToLatest: Bool
    ) throws -> EvaluationPromptRevision {
        let normalizedRevisionID = revisionID.trimmingCharacters(in: .whitespacesAndNewlines)
        if normalizedRevisionID.isEmpty, fallbackToLatest, let latest = prompt.latestRevision {
            return latest
        }
        guard let revision = prompt.revisions.first(where: { $0.revisionID == normalizedRevisionID }) else {
            throw MelixCLIError.runtime("Evaluation prompt \(prompt.id) revision \(normalizedRevisionID) was not found.")
        }
        return revision
    }

    private static func normalizedRequired(_ value: String, fieldName: String) throws -> String {
        let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalized.isEmpty == false else {
            throw MelixCLIError.missingRequired("\(fieldName) must not be empty.")
        }
        return normalized
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()

    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }()

    private static let hashEncoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        return encoder
    }()
}

private struct EvaluationPromptHashPayload: Codable {
    let taskKind: String
    let scoringMode: String
    let systemPrompt: String
    let examples: [EvaluationPromptExample]

    enum CodingKeys: String, CodingKey {
        case taskKind = "task_kind"
        case scoringMode = "scoring_mode"
        case systemPrompt = "system_prompt"
        case examples
    }
}

private struct EvaluationPromptDocument: Codable {
    var schemaVersion: Int
    var prompts: [EvaluationPrompt]

    init(schemaVersion: Int = 1, prompts: [EvaluationPrompt] = []) {
        self.schemaVersion = max(schemaVersion, 1)
        self.prompts = prompts
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case prompts
    }
}
