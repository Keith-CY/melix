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
        #expect(baseline.latestRevisionID == "baseline.v6")
        #expect(baseline.revisions.map(\.revisionID) == ["baseline.v1", "baseline.v2", "baseline.v3", "baseline.v4", "baseline.v5", "baseline.v6"])
        #expect(revision.status == .frozen)
        #expect(revision.systemPrompt == EvaluationPromptStore.builtInBaselineSystemPrompt)
        #expect(revision.systemPrompt.contains("你是中文对话事件抽取器"))
        #expect(revision.systemPrompt.contains("\"source_order\""))
        #expect(revision.systemPrompt.contains("不要使用元动作"))
        #expect(revision.systemPrompt.contains("连续时间区间"))
        #expect(revision.systemPrompt.contains("可用时间"))
        #expect(revision.systemPrompt.contains("模糊第三方关系词"))
        #expect(revision.systemPrompt.contains("反馈案例约束"))
        #expect(revision.systemPrompt.contains("召回强化"))
        #expect(revision.systemPrompt.contains("同地点同时吃饭"))
        #expect(revision.systemPrompt.contains("不要抽取为独立事件"))
        #expect(revision.systemPrompt.contains("周日新买裙子"))
        #expect(revision.systemPrompt.contains("明天打给你"))
        #expect(revision.systemPrompt.contains("周一晚上11点下飞机"))
        #expect(revision.systemPrompt.contains("周二晚上7点上飞机"))
        #expect(revision.systemPrompt.contains("同事/朋友/表姐"))
        let expectedContentHash = try EvaluationPromptStore.contentHash(systemPrompt: revision.systemPrompt)
        #expect(revision.contentHash == expectedContentHash)
        #expect(revision.contentHash.hasPrefix("sha256:"))

        let resolved = try store.resolveForRun()
        #expect(resolved.promptID == baseline.id)
        #expect(resolved.revisionID == EvaluationPromptStore.builtInBaselineRevisionID)
        #expect(resolved.revisionID == "baseline.v6")

        let v3Resolved = try store.resolveForRun(
            promptID: EvaluationPromptStore.builtInBaselinePromptID,
            revisionID: "baseline.v3"
        )
        #expect(v3Resolved.revisionID == "baseline.v3")
        #expect(v3Resolved.systemPrompt.contains("不要使用元动作"))
        #expect(v3Resolved.systemPrompt.contains("连续时间区间") == false)

        let v4Resolved = try store.resolveForRun(
            promptID: EvaluationPromptStore.builtInBaselinePromptID,
            revisionID: "baseline.v4"
        )
        #expect(v4Resolved.revisionID == "baseline.v4")
        #expect(v4Resolved.systemPrompt.contains("连续时间区间"))
        #expect(v4Resolved.systemPrompt.contains("反馈案例约束") == false)

        let v5Resolved = try store.resolveForRun(
            promptID: EvaluationPromptStore.builtInBaselinePromptID,
            revisionID: "baseline.v5"
        )
        #expect(v5Resolved.revisionID == "baseline.v5")
        #expect(v5Resolved.systemPrompt.contains("反馈案例约束"))
        #expect(v5Resolved.systemPrompt.contains("召回强化") == false)

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
