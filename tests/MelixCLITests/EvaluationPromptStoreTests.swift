import Foundation
import Testing

@testable import MelixCLICore

@Suite("Evaluation Prompt Store")
struct EvaluationPromptStoreTests {
    @Test("built-in baseline prompt is frozen read only and deterministic")
    func builtInBaselinePromptIsFrozenReadOnlyAndDeterministic() throws {
        let store = EvaluationPromptStore(melixHome: temporaryMelixHome())

        let prompts = try store.list()
        let baseline = try #require(prompts.first)
        let revision = try #require(baseline.latestRevision)

        #expect(baseline.id == EvaluationPromptStore.builtInBaselinePromptID)
        #expect(baseline.readOnly)
        #expect(baseline.latestRevisionID == "baseline.v2")
        #expect(baseline.revisions.map(\.revisionID) == ["baseline.v1", "baseline.v2"])
        #expect(revision.status == .frozen)
        #expect(revision.systemPrompt == EvaluationPromptStore.builtInBaselineSystemPrompt)
        #expect(revision.systemPrompt.contains("# Segment Metadata Candidates"))
        #expect(revision.systemPrompt.contains("\"event_candidates\""))
        #expect(revision.contentHash == EvaluationPromptStore.contentHash(systemPrompt: revision.systemPrompt))
        #expect(revision.contentHash.hasPrefix("sha256:"))

        let resolved = try store.resolveForRun()
        #expect(resolved.promptID == baseline.id)
        #expect(resolved.revisionID == EvaluationPromptStore.builtInBaselineRevisionID)

        #expect(throws: MelixCLIError.self) {
            try store.create(
                promptID: EvaluationPromptStore.builtInBaselinePromptID,
                title: "Override",
                systemPrompt: "no"
            )
        }
        #expect(throws: MelixCLIError.self) {
            try store.update(promptID: EvaluationPromptStore.builtInBaselinePromptID, systemPrompt: "no")
        }
        #expect(throws: MelixCLIError.self) {
            try store.archive(promptID: EvaluationPromptStore.builtInBaselinePromptID)
        }
    }

    @Test("custom prompt draft update freeze archive and immutable revision lifecycle")
    func customPromptRevisionLifecycle() throws {
        let home = temporaryMelixHome()
        let store = EvaluationPromptStore(melixHome: home)

        let created = try store.create(
            promptID: "event-prod",
            title: "Event Prod",
            systemPrompt: "Extract events as JSON."
        )
        #expect(created.latestRevisionID == "rev-1")
        #expect(created.latestRevision?.status == .draft)
        #expect(try store.list().map(\.id) == [
            EvaluationPromptStore.builtInBaselinePromptID,
            "event-prod",
        ])

        #expect(throws: MelixCLIError.self) {
            try store.resolveForRun(promptID: "event-prod")
        }

        let updatedDraft = try store.update(
            promptID: "event-prod",
            systemPrompt: "Extract established events and plans."
        )
        #expect(updatedDraft.revisions.count == 1)
        #expect(updatedDraft.latestRevision?.systemPrompt == "Extract established events and plans.")

        let frozen = try store.freeze(promptID: "event-prod")
        let frozenRevision = try #require(frozen.latestRevision)
        #expect(frozenRevision.status == .frozen)
        #expect(try store.resolveForRun(promptID: "event-prod").contentHash == frozenRevision.contentHash)

        let nextDraft = try store.update(
            promptID: "event-prod",
            systemPrompt: "Extract events and keep original wording."
        )
        #expect(nextDraft.revisions.count == 2)
        #expect(nextDraft.latestRevisionID == "rev-2")
        #expect(nextDraft.revisions.first?.revisionID == "rev-1")
        #expect(nextDraft.revisions.first?.status == .frozen)
        #expect(nextDraft.latestRevision?.status == .draft)

        let visibleState = try String(contentsOf: home.evaluationPromptsFileURL, encoding: .utf8)
        #expect(visibleState.contains("event-prod"))
        #expect(visibleState.contains("Extract events and keep original wording."))

        let archived = try store.archive(promptID: "event-prod")
        #expect(archived.archived)
        #expect(try store.list().map(\.id) == [EvaluationPromptStore.builtInBaselinePromptID])
        #expect(throws: MelixCLIError.self) {
            try store.resolveForRun(promptID: "event-prod")
        }
    }

    private func temporaryMelixHome() -> MelixHome {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-eval-prompts-\(UUID().uuidString)", isDirectory: true)
        return MelixHome(environment: ["MELIX_HOME": root.path])
    }
}
