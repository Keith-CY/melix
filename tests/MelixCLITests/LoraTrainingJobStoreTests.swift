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

    @Test("local training queue persists admission running cancellation and metrics")
    func localTrainingQueuePersistsAdmissionRunningCancellationAndMetrics() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LocalTrainingQueueStore(melixHome: home)

        let admitted = try store.admit(
            LocalTrainingQueueAdmissionRequest(
                modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                datasetURI: "/tmp/datasets/alpaca.jsonl",
                adapterName: "demo-adapter",
                trainingMode: "qlora",
                parameters: [
                    "dataset_version_id": "dataset-v2",
                    "workspace_manifest_path": "/tmp/workspace/manifest.json",
                    "project_id": "workspace-a",
                ]
            )
        )
        let running = try store.markRunning(jobID: admitted.jobID)
        let restored = try LocalTrainingQueueStore(melixHome: home).get(jobID: admitted.jobID)

        #expect(admitted.jobID == "training-queue-0001")
        #expect(running.status == .running)
        #expect(restored?.projectID == "workspace-a")
        #expect(restored?.datasetVersionID == "dataset-v2")
        #expect(restored?.status == .running)

        do {
            _ = try store.admit(
                LocalTrainingQueueAdmissionRequest(
                    modelID: "melix-dev-text",
                    datasetURI: "/tmp/other.jsonl",
                    adapterName: "other-adapter"
                )
            )
            Issue.record("Expected exclusive local training queue admission to reject overlap.")
        } catch let error as MelixCLIError {
            #expect(error == .requestFailed(
                code: "training_queue_busy",
                message: "Local training queue is busy with training-queue-0001."
            ))
        }

        let cancelled = try store.requestCancel(jobID: admitted.jobID)
        let snapshot = try store.snapshot()
        let metrics = try #require(snapshot["metrics"] as? [String: Any])

        #expect(cancelled.status == .cancelRequested)
        #expect(FileManager.default.fileExists(atPath: cancelled.cancellationRequestPath))
        #expect(metrics["running_job_count"] as? Int == 1)
        #expect(metrics["admission_refusal_count"] as? Int == 1)
    }

    @Test("local training queue rejects malformed queue schema with typed restore error")
    func localTrainingQueueRejectsMalformedQueueSchemaWithTypedRestoreError() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        try FileManager.default.createDirectory(at: home.stateDirectoryURL, withIntermediateDirectories: true)
        try #"{"schema_version":"melix.local_training_queue.v0","jobs":[]}"#
            .write(to: home.localTrainingQueueFileURL, atomically: true, encoding: .utf8)

        #expect(throws: MelixCLIError.requestFailed(
            code: "training_queue_restore_failed",
            message: "Unsupported local training queue schema: melix.local_training_queue.v0."
        )) {
            _ = try LocalTrainingQueueStore(melixHome: home).list()
        }
    }

    @Test("local training queue records nonexclusive defaults failures and terminal cancel errors")
    func localTrainingQueueRecordsNonexclusiveDefaultsFailuresAndTerminalCancelErrors() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LocalTrainingQueueStore(melixHome: home)

        #expect(throws: MelixCLIError.missingRequired("job_id must not be empty.")) {
            _ = try store.get(jobID: "  ")
        }

        let first = try store.admit(
            LocalTrainingQueueAdmissionRequest(
                modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                datasetURI: "",
                adapterName: "background-adapter",
                trainingMode: "qlora",
                resourceClass: "background_training",
                parameters: [
                    "dataset_id": "explicit-dataset",
                    "hf_dataset_path": "ignored/hf-dataset",
                    "preflight_receipt_path": "/tmp/preflight-receipt.json",
                    "recovery_policy": "custom_policy",
                ]
            )
        )
        let second = try store.admit(
            LocalTrainingQueueAdmissionRequest(
                modelID: "mlx-community/TinyLlama-1.1B-4bit",
                datasetURI: "/tmp/second.jsonl",
                adapterName: "second-adapter",
                resourceClass: "background_training"
            )
        )
        let failed = try store.markFailed(
            jobID: first.jobID,
            code: "worker_failed",
            message: "worker crashed",
            retriable: true,
            remediation: "Rerun after freeing memory."
        )

        #expect(first.id == first.jobID)
        #expect(first.datasetID == "explicit-dataset")
        #expect(first.recoveryPolicy == "custom_policy")
        #expect(first.preflightReceiptPath == "/tmp/preflight-receipt.json")
        #expect(first.runDirectory.hasSuffix("/jobs/model-ops/train_lora/training-queue-0001"))
        #expect(second.jobID == "training-queue-0002")
        #expect(failed.status == .failed)
        #expect(failed.operatorErrors == [
            LocalTrainingQueueOperatorError(
                code: "worker_failed",
                message: "worker crashed",
                retriable: true,
                remediation: "Rerun after freeing memory."
            ),
        ])

        let guardrailFailed = try store.markFailed(
            jobID: second.jobID,
            code: "insufficient_training_samples",
            message: "LoRA training requires at least one training sample."
        )
        #expect(guardrailFailed.operatorErrors == [
            LocalTrainingQueueOperatorError(
                code: "insufficient_training_samples",
                message: "LoRA training requires at least one training sample.",
                retriable: false,
                remediation: "Add more accepted training samples before starting training."
            ),
        ])

        #expect(throws: MelixCLIError.requestFailed(
            code: "training_queue_state_invalid",
            message: "Local training queue job \(first.jobID) is already terminal."
        )) {
            _ = try store.markSucceeded(jobID: first.jobID)
        }
        #expect(throws: MelixCLIError.requestFailed(
            code: "training_queue_job_not_found",
            message: "No local training queue job was found for missing-job."
        )) {
            _ = try store.markRunning(jobID: "missing-job")
        }
        #expect(throws: MelixCLIError.requestFailed(
            code: "training_queue_job_not_found",
            message: "No local training queue job was found for missing-job."
        )) {
            _ = try store.requestCancel(jobID: "missing-job")
        }
        #expect(throws: MelixCLIError.requestFailed(
            code: "training_queue_state_invalid",
            message: "Local training queue job \(first.jobID) is already terminal."
        )) {
            _ = try store.requestCancel(jobID: first.jobID)
        }
    }

    @Test("local training queue restores legacy operator errors without remediation")
    func localTrainingQueueRestoresLegacyOperatorErrorsWithoutRemediation() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        try FileManager.default.createDirectory(at: home.stateDirectoryURL, withIntermediateDirectories: true)

        try """
        {
          "schema_version": "melix.local_training_queue.v1",
          "queue_id": "local-training",
          "updated_at_unix_ms": 1234,
          "jobs": [
            {
              "schema_version": "melix.local_training_queue_job.v1",
              "job_id": "training-queue-0001",
              "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
              "adapter_name": "legacy-adapter",
              "status": "failed",
              "created_at_unix_ms": 1000,
              "updated_at_unix_ms": 1234,
              "operator_errors": [
                {
                  "code": "worker_failed",
                  "message": "worker crashed",
                  "retriable": true
                }
              ]
            }
          ]
        }
        """
        .write(to: home.localTrainingQueueFileURL, atomically: true, encoding: .utf8)

        let restored = try #require(try LocalTrainingQueueStore(melixHome: home).get(jobID: "training-queue-0001"))

        #expect(restored.operatorErrors == [
            LocalTrainingQueueOperatorError(
                code: "worker_failed",
                message: "worker crashed",
                retriable: true,
                remediation: ""
            ),
        ])
    }

    @Test("local training queue keeps status unchanged when cancel request cannot be written")
    func localTrainingQueueKeepsStatusUnchangedWhenCancelRequestCannotBeWritten() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LocalTrainingQueueStore(melixHome: home)
        try FileManager.default.createDirectory(at: home.rootURL, withIntermediateDirectories: true)
        let blockedRunDirectory = home.rootURL.appendingPathComponent("blocked-run-directory")
        try Data("not a directory".utf8).write(to: blockedRunDirectory)
        let admitted = try store.admit(
            LocalTrainingQueueAdmissionRequest(
                modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                datasetURI: "/tmp/datasets/alpaca.jsonl",
                adapterName: "blocked-adapter",
                runDirectory: blockedRunDirectory.path
            )
        )
        _ = try store.markRunning(jobID: admitted.jobID)

        do {
            _ = try store.requestCancel(jobID: admitted.jobID)
            Issue.record("Expected cancellation to fail before queue status changes.")
        } catch let error as MelixCLIError {
            guard case .requestFailed(let code, let message) = error else {
                Issue.record("Unexpected cancellation error: \(error).")
                return
            }
            #expect(code == "training_queue_cancel_failed")
            #expect(message.contains("Failed to persist cancellation request for \(admitted.jobID):"))
        }

        let restored = try store.get(jobID: admitted.jobID)

        #expect(restored?.status == .running)
        #expect(!FileManager.default.fileExists(atPath: admitted.cancellationRequestPath))
    }

    @Test("local training queue removes cancellation request when queue save fails")
    func localTrainingQueueRemovesCancellationRequestWhenQueueSaveFails() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        let store = LocalTrainingQueueStore(melixHome: home)
        let admitted = try store.admit(
            LocalTrainingQueueAdmissionRequest(
                modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                datasetURI: "/tmp/datasets/alpaca.jsonl",
                adapterName: "rollback-adapter"
            )
        )
        _ = try store.markRunning(jobID: admitted.jobID)
        try FileManager.default.setAttributes([.immutable: true], ofItemAtPath: home.localTrainingQueueFileURL.path)
        defer {
            try? FileManager.default.setAttributes([.immutable: false], ofItemAtPath: home.localTrainingQueueFileURL.path)
        }

        do {
            _ = try store.requestCancel(jobID: admitted.jobID)
            Issue.record("Expected cancellation to roll back when queue save fails.")
        } catch let error as MelixCLIError {
            guard case .requestFailed(let code, let message) = error else {
                Issue.record("Unexpected cancellation error: \(error).")
                return
            }
            #expect(code == "training_queue_admission_failed")
            #expect(message.contains("Failed to persist local training queue:"))
        }

        try FileManager.default.setAttributes([.immutable: false], ofItemAtPath: home.localTrainingQueueFileURL.path)
        let restored = try store.get(jobID: admitted.jobID)

        #expect(restored?.status == .running)
        #expect(!FileManager.default.fileExists(atPath: admitted.cancellationRequestPath))
    }

    @Test("local training queue restores flexible timestamps and rejects corrupted records")
    func localTrainingQueueRestoresFlexibleTimestampsAndRejectsCorruptedRecords() throws {
        let home = temporaryMelixHome()
        defer { try? FileManager.default.removeItem(at: home.rootURL) }
        try FileManager.default.createDirectory(at: home.stateDirectoryURL, withIntermediateDirectories: true)

        try """
        {
          "schema_version": "melix.local_training_queue.v1",
          "updated_at_unix_ms": "1234",
          "jobs": [
            {
              "schema_version": "melix.local_training_queue_job.v0",
              "job_id": "bad-job",
              "created_at_unix_ms": 1,
              "updated_at_unix_ms": 1
            }
          ]
        }
        """
        .write(to: home.localTrainingQueueFileURL, atomically: true, encoding: .utf8)

        #expect(throws: MelixCLIError.requestFailed(
            code: "training_queue_restore_failed",
            message: "Unsupported local training queue job schema: melix.local_training_queue_job.v0."
        )) {
            _ = try LocalTrainingQueueStore(melixHome: home).list()
        }

        try "not-json"
            .write(to: home.localTrainingQueueFileURL, atomically: true, encoding: .utf8)
        do {
            _ = try LocalTrainingQueueStore(melixHome: home).list()
            Issue.record("Expected malformed queue JSON to raise a typed restore failure.")
        } catch let error as MelixCLIError {
            guard case .requestFailed(let code, let message) = error else {
                Issue.record("Unexpected local training queue error: \(error).")
                return
            }
            #expect(code == "training_queue_restore_failed")
            #expect(message.hasPrefix("Failed to restore local training queue:"))
        }

        try """
        {
          "schema_version": "melix.local_training_queue.v1",
          "updated_at_unix_ms": "1234",
          "jobs": [
            {
              "job_id": "legacy",
              "model_id": "model-legacy",
              "adapter_name": "legacy-adapter",
              "resource_class": "background_training",
              "created_at_unix_ms": 123,
              "updated_at_unix_ms": "999"
            },
            {
              "job_id": "training-queue-0009",
              "model_id": "model-number",
              "adapter_name": "number-adapter",
              "resource_class": "background_training",
              "created_at_unix_ms": 124.8,
              "updated_at_unix_ms": 999.8
            },
            {
              "job_id": "alpha",
              "model_id": "model-alpha",
              "adapter_name": "alpha-adapter",
              "resource_class": "background_training",
              "created_at_unix_ms": "125",
              "updated_at_unix_ms": "999"
            }
          ]
        }
        """
        .write(to: home.localTrainingQueueFileURL, atomically: true, encoding: .utf8)

        let store = LocalTrainingQueueStore(melixHome: home)
        let restored = try store.list()
        let admitted = try store.admit(
            LocalTrainingQueueAdmissionRequest(
                modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                datasetURI: "",
                adapterName: "next-adapter",
                resourceClass: "background_training",
                parameters: ["hf_dataset_path": "org/hf-dataset"]
            )
        )

        #expect(restored.map(\.jobID) == ["alpha", "legacy", "training-queue-0009"])
        #expect(restored.first { $0.jobID == "training-queue-0009" }?.createdAtUnixMS == 124)
        #expect(admitted.jobID == "training-queue-0010")
        #expect(admitted.datasetID == "org/hf-dataset")
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
