import Foundation
import Testing

@testable import MelixCLICore

@Suite("LoRA Training Job Store")
struct LoraTrainingJobStoreTests {
    @Test("status helpers distinguish terminal and mutable jobs")
    func statusHelpersDistinguishTerminalAndMutableJobs() {
        #expect(LoraTrainingJobStatus.succeeded.isTerminal)
        #expect(LoraTrainingJobStatus.failed.isTerminal)
        #expect(LoraTrainingJobStatus.canceled.isTerminal)
        #expect(!LoraTrainingJobStatus.draft.isTerminal)
        #expect(!LoraTrainingJobStatus.running.isTerminal)
        #expect(LoraTrainingJobStatus.draft.allowsMutation)
        #expect(!LoraTrainingJobStatus.running.allowsMutation)
    }

    @Test("persists desktop LoRA jobs under MELIX_HOME state")
    func persistsDesktopLoraJobsUnderMelixHomeState() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LoraTrainingJobStore(melixHome: home)
        let config = sampleConfig()

        let created = try store.createDraft(title: "Nightly Qwen", config: config)
        var running = created
        running.status = .running
        running.lastRunJobID = "model-ops-0001"
        running.outputPath = "/tmp/melix/train_lora.adapter.json"
        running.followUpArtifacts.adapterManifestPath = running.outputPath
        let saved = try store.save(running)

        #expect(saved.title == "Nightly Qwen")
        #expect(saved.status == .running)
        #expect(try store.get(id: saved.id)?.config == config)

        let visibleState = try String(contentsOf: home.loraTrainingJobsFileURL, encoding: .utf8)
        #expect(visibleState.contains(#""schema_version" : "melix.desktop_lora_training_jobs.v1""#))
        #expect(visibleState.contains(#""schema_version" : "melix.desktop_lora_training_config.v1""#))
        #expect(visibleState.contains("HuggingFaceH4/ultrachat_200k"))
        #expect(visibleState.contains("model-ops-0001"))
    }

    @Test("duplicate and delete keep original job immutable")
    func duplicateAndDeleteKeepOriginalJobImmutable() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LoraTrainingJobStore(melixHome: home)
        let original = try store.createDraft(title: "Adapter", config: sampleConfig(adapterName: "adapter-a"))

        let copy = try store.duplicate(id: original.id)

        #expect(copy.id != original.id)
        #expect(copy.title == "Adapter Copy")
        #expect(copy.config == original.config)
        #expect(copy.status == .draft)

        try store.delete(id: original.id)
        #expect(try store.get(id: original.id) == nil)
        #expect(try store.get(id: copy.id)?.title == "Adapter Copy")
    }

    @Test("normalizes blank titles and rejects blank identifiers")
    func normalizesBlankTitlesAndRejectsBlankIdentifiers() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LoraTrainingJobStore(melixHome: home)

        let adapterTitle = try store.createDraft(title: "   ", config: sampleConfig(adapterName: "adapter-fallback"))
        #expect(adapterTitle.title == "adapter-fallback")

        let genericTitle = try store.createDraft(title: "", config: sampleConfig(adapterName: ""))
        #expect(genericTitle.title == "LoRA Training Job")

        #expect(throws: MelixCLIError.self) {
            _ = try store.get(id: "  ")
        }
        #expect(throws: MelixCLIError.self) {
            _ = try store.duplicate(id: "missing-job")
        }
    }

    @Test("list sorts by updated time then title")
    func listSortsByUpdatedTimeThenTitle() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LoraTrainingJobStore(melixHome: home)
        let oldDate = try #require(ISO8601DateFormatter().date(from: "2026-05-04T00:00:00Z"))
        let newDate = try #require(ISO8601DateFormatter().date(from: "2026-05-04T01:00:00Z"))
        let document = TestLoraTrainingJobsDocument(jobs: [
            LoraTrainingJobRecord(
                id: "beta",
                title: "Beta",
                config: sampleConfig(adapterName: "beta"),
                updatedAt: oldDate
            ),
            LoraTrainingJobRecord(
                id: "alpha",
                title: "Alpha",
                config: sampleConfig(adapterName: "alpha"),
                updatedAt: oldDate
            ),
            LoraTrainingJobRecord(
                id: "newest",
                title: "Newest",
                config: sampleConfig(adapterName: "newest"),
                updatedAt: newDate
            ),
        ])
        try write(document, to: home.loraTrainingJobsFileURL)

        let jobs = try store.list()

        #expect(jobs.map(\.id) == ["newest", "alpha", "beta"])
    }

    @Test("rejects unsupported jobs schema")
    func rejectsUnsupportedJobsSchema() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LoraTrainingJobStore(melixHome: home)
        try FileManager.default.createDirectory(at: home.stateDirectoryURL, withIntermediateDirectories: true)
        try #"{"schema_version":"melix.desktop_lora_training_jobs.v0","jobs":[]}"#
            .write(to: home.loraTrainingJobsFileURL, atomically: true, encoding: .utf8)

        #expect(throws: MelixCLIError.self) {
            _ = try store.list()
        }
    }

    @Test("skips job records with unsupported config schema")
    func skipsJobRecordsWithUnsupportedConfigSchema() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LoraTrainingJobStore(melixHome: home)
        let valid = LoraTrainingJobRecord(
            id: "valid-job",
            title: "Valid Job",
            config: sampleConfig(adapterName: "valid-adapter")
        )
        var unsupported = LoraTrainingJobRecord(
            id: "unsupported-job",
            title: "Unsupported Job",
            config: sampleConfig(adapterName: "unsupported-adapter")
        )
        unsupported.config.schemaVersion = "melix.desktop_lora_training_config.v0"
        try write(TestLoraTrainingJobsDocument(jobs: [unsupported, valid]), to: home.loraTrainingJobsFileURL)

        let jobs = try store.list()

        #expect(jobs.map(\.id) == ["valid-job"])
        #expect(jobs.first?.config.adapterName == "valid-adapter")
    }

    @Test("serializes concurrent draft mutations")
    func serializesConcurrentDraftMutations() async throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LoraTrainingJobStore(melixHome: home)
        let inputs = (0..<40).map { index in
            (
                title: "Concurrent \(index)",
                config: sampleConfig(adapterName: "adapter-\(index)")
            )
        }

        let savedIDs = try await withThrowingTaskGroup(of: String.self) { group in
            for input in inputs {
                group.addTask {
                    try store.createDraft(title: input.title, config: input.config).id
                }
            }
            var ids: [String] = []
            for try await id in group {
                ids.append(id)
            }
            return ids
        }

        let jobs = try store.list()

        #expect(Set(savedIDs).count == inputs.count)
        #expect(jobs.count == inputs.count)
        #expect(Set(jobs.map(\.id)) == Set(savedIDs))
        #expect(Set(jobs.map(\.config.adapterName)) == Set(inputs.map(\.config.adapterName)))
    }

    @Test("config import export round trip preserves every supported field")
    func configImportExportRoundTripPreservesEverySupportedField() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LoraTrainingJobStore(melixHome: home)
        let config = sampleConfig(trainingMode: "dora", adapterName: "adapter-roundtrip")
        let exportURL = home.rootURL
            .appendingPathComponent("exports", isDirectory: true)
            .appendingPathComponent("adapter-roundtrip.lora-config.json")

        try store.exportConfig(config, to: exportURL)
        let imported = try store.importConfig(from: exportURL)

        #expect(imported == config)
        let exportedText = try String(contentsOf: exportURL, encoding: .utf8)
        #expect(exportedText.contains(#""training_mode" : "dora""#))
        #expect(exportedText.contains(#""gradient_checkpointing" : true"#))
        #expect(exportedText.contains(#""activation_mode" : "adapter_backed_runtime""#))
    }

    @Test("rejects unsupported config schema")
    func rejectsUnsupportedConfigSchema() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LoraTrainingJobStore(melixHome: home)
        let path = home.rootURL.appendingPathComponent("bad-config.json")
        try FileManager.default.createDirectory(at: home.rootURL, withIntermediateDirectories: true)
        try #"{"schema_version":"melix.desktop_lora_training_config.v0"}"#
            .write(to: path, atomically: true, encoding: .utf8)

        #expect(throws: MelixCLIError.self) {
            _ = try store.importConfig(from: path)
        }
    }

    private func temporaryMelixHome() -> MelixHome {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-lora-jobs-\(UUID().uuidString)", isDirectory: true)
        return MelixHome(environment: ["MELIX_HOME": root.path])
    }

    private func write(_ document: TestLoraTrainingJobsDocument, to url: URL) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(document)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try data.write(to: url)
    }

    private func sampleConfig(
        trainingMode: String = "qlora",
        adapterName: String = "qwen35-acceptance"
    ) -> LoraTrainingJobConfig {
        LoraTrainingJobConfig(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            datasetSourceKind: "hf_dataset",
            datasetURI: "/tmp/local-package",
            hfDatasetPath: "HuggingFaceH4/ultrachat_200k",
            hfDatasetName: "default",
            hfDatasetRevision: "main",
            hfTrainSplit: "train_sft",
            hfValidSplit: "test_sft",
            chatFeature: "messages",
            promptFeature: "prompt",
            completionFeature: "completion",
            textFeature: "text",
            adapterName: adapterName,
            targetRepo: "melix/adapters/\(adapterName)",
            experimentGroupID: "nightly-qwen35",
            resumeManifestPath: "/tmp/prior/train_lora.adapter.json",
            trainingMode: trainingMode,
            presetID: "balanced_adapter",
            activationMode: "adapter_backed_runtime",
            rank: "32",
            alpha: "64",
            dropout: "0.1",
            targetModules: "q_proj,k_proj,v_proj",
            numLayers: "24",
            batchSize: "4",
            epochs: "3",
            learningRate: "2e-4",
            maxSeqLength: "8192",
            responseOnly: true,
            maskPrompt: true,
            gradientCheckpointing: true,
            derivedModelAlias: "melix-dev-text-ultrachat"
        )
    }
}

private struct TestLoraTrainingJobsDocument: Encodable {
    var schemaVersion = "melix.desktop_lora_training_jobs.v1"
    var jobs: [LoraTrainingJobRecord]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobs
    }
}
