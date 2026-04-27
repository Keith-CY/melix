import Foundation
import MelixCLICore

public protocol EvaluationPromptStoring: Sendable {
    func list(includeArchived: Bool) throws -> [EvaluationPrompt]
    func create(promptID: String, title: String, systemPrompt: String) throws -> EvaluationPrompt
    func update(promptID: String, systemPrompt: String) throws -> EvaluationPrompt
    func freeze(promptID: String, revisionID: String) throws -> EvaluationPrompt
    func archive(promptID: String) throws -> EvaluationPrompt
    func resolveForRun(promptID: String, revisionID: String) throws -> EvaluationPromptSnapshot
}

extension EvaluationPromptStore: EvaluationPromptStoring {}

public struct NullEvaluationPromptStore: EvaluationPromptStoring {
    public init() {}

    public func list(includeArchived: Bool) throws -> [EvaluationPrompt] {
        [EvaluationPromptStore.builtInBaselinePrompt]
    }

    public func create(promptID: String, title: String, systemPrompt: String) throws -> EvaluationPrompt {
        let now = Date()
        let revision = EvaluationPromptRevision(
            revisionID: "rev-1",
            status: .draft,
            systemPrompt: systemPrompt,
            contentHash: EvaluationPromptStore.contentHash(systemPrompt: systemPrompt),
            createdAt: now,
            updatedAt: now
        )
        return EvaluationPrompt(
            id: promptID,
            title: title,
            latestRevisionID: revision.revisionID,
            revisions: [revision],
            createdAt: now,
            updatedAt: now
        )
    }

    public func update(promptID: String, systemPrompt: String) throws -> EvaluationPrompt {
        try create(promptID: promptID, title: promptID, systemPrompt: systemPrompt)
    }

    public func freeze(promptID: String, revisionID: String) throws -> EvaluationPrompt {
        if promptID == EvaluationPromptStore.builtInBaselinePromptID {
            return EvaluationPromptStore.builtInBaselinePrompt
        }
        let now = Date()
        let resolvedRevisionID = revisionID.isEmpty ? "rev-1" : revisionID
        let revision = EvaluationPromptRevision(
            revisionID: resolvedRevisionID,
            status: .frozen,
            systemPrompt: EvaluationPromptStore.builtInBaselineSystemPrompt,
            contentHash: EvaluationPromptStore.contentHash(systemPrompt: EvaluationPromptStore.builtInBaselineSystemPrompt),
            createdAt: now,
            updatedAt: now
        )
        return EvaluationPrompt(
            id: promptID,
            title: promptID,
            latestRevisionID: resolvedRevisionID,
            revisions: [revision],
            createdAt: now,
            updatedAt: now
        )
    }

    public func archive(promptID: String) throws -> EvaluationPrompt {
        EvaluationPrompt(
            id: promptID,
            title: promptID,
            latestRevisionID: "rev-1",
            archived: true,
            revisions: []
        )
    }

    public func resolveForRun(promptID: String, revisionID: String) throws -> EvaluationPromptSnapshot {
        guard let revision = EvaluationPromptStore.builtInBaselinePrompt.latestRevision else {
            throw MelixCLIError.runtime("Built-in evaluation prompt revision was not found.")
        }
        return EvaluationPromptSnapshot(
            prompt: EvaluationPromptStore.builtInBaselinePrompt,
            revision: revision
        )
    }
}
