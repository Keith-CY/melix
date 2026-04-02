import Foundation
import Testing

@testable import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Melix CLI Runner")
struct MelixCLIRunnerTests {
    @Test("lora list resolves the first text model and renders registry output")
    func loraListResolvesTextModelAndRendersRegistryOutput() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "melix-dev-image", kind: "image"),
            makeModelSummary(id: "melix-dev-text", kind: "text"),
        ]))
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"adapters":[{"adapter_name":"demo-adapter","status":"ready","source_model":"melix-dev-text"}]}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(.loraList(.init()))
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.modelID == "melix-dev-text")
        #expect(call.operation == "registry_snapshot")
        #expect(output.contains("adapter\tstatus\tsource_model"))
        #expect(output.contains("demo-adapter\tready\tmelix-dev-text"))
    }

    @Test("lora list returns json when requested and honors an explicit preferred model id")
    func loraListReturnsJSONWhenRequested() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"adapters":[{"adapter_name":"demo-adapter"}]}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraList(.init(modelID: "melix-dev-text", json: true))
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.modelID == "melix-dev-text")
        #expect(output == #"{"adapters":[{"adapter_name":"demo-adapter"}]}"#)
    }

    @Test("lora list falls back to raw manifest text when the registry payload is not tabular")
    func loraListFallsBackToRawManifestText() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(manifestJSON: "not-json"))

        let output = try await MelixCLIRunner(client: client).run(.loraList(.init()))

        #expect(output == "not-json")
    }

    @Test("lora list renders the empty adapter state when no adapters are present")
    func loraListRendersEmptyRegistryState() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(manifestJSON: #"{"adapters":[]}"#))

        let output = try await MelixCLIRunner(client: client).run(.loraList(.init()))

        #expect(output == "No adapters found.\n")
    }

    @Test("lora train forwards dataset, adapter, repo, and tuning parameters")
    func loraTrainForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/train_lora/job-1"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraTrain(
                .init(
                    modelID: "melix-dev-text",
                    datasetSourceKind: "local_package",
                    datasetURI: "/tmp/datasets/alpaca.jsonl",
                    adapterName: "demo-adapter",
                    targetRepo: "melix/demo-adapter",
                    parameters: [
                        "rank": "8",
                        "epochs": "3",
                    ]
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/train_lora/job-1")
        #expect(call.modelID == "melix-dev-text")
        #expect(call.operation == "train_lora")
        #expect(call.ext["dataset_source_kind"] == "local_package")
        #expect(call.ext["dataset_uri"] == "/tmp/datasets/alpaca.jsonl")
        #expect(call.ext["adapter_name"] == "demo-adapter")
        #expect(call.ext["target_repo"] == "melix/demo-adapter")
        #expect(call.ext["rank"] == "8")
        #expect(call.ext["epochs"] == "3")
    }

    @Test("lora train forwards Hugging Face dataset metadata and boolean flags")
    func loraTrainForwardsHFDatasetPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/train_lora/job-hf"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraTrain(
                .init(
                    modelID: "melix-dev-text",
                    datasetSourceKind: "hf_dataset",
                    datasetURI: "",
                    adapterName: "hf-demo-adapter",
                    parameters: [
                        "hf_dataset_path": "HuggingFaceH4/ultrachat_200k",
                        "hf_dataset_name": "default",
                        "hf_dataset_revision": "main",
                        "hf_train_split": "train_sft",
                        "hf_valid_split": "test_sft",
                        "text_feature": "messages",
                        "response_only": "true",
                        "mask_prompt": "true",
                        "gradient_checkpointing": "true",
                        "derived_model_alias": "melix-dev-text-ultrachat",
                    ]
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/train_lora/job-hf")
        #expect(call.ext["dataset_source_kind"] == "hf_dataset")
        #expect(call.ext["dataset_uri"] == nil)
        #expect(call.ext["hf_dataset_path"] == "HuggingFaceH4/ultrachat_200k")
        #expect(call.ext["hf_dataset_name"] == "default")
        #expect(call.ext["hf_dataset_revision"] == "main")
        #expect(call.ext["hf_train_split"] == "train_sft")
        #expect(call.ext["hf_valid_split"] == "test_sft")
        #expect(call.ext["text_feature"] == "messages")
        #expect(call.ext["response_only"] == "true")
        #expect(call.ext["mask_prompt"] == "true")
        #expect(call.ext["gradient_checkpointing"] == "true")
        #expect(call.ext["derived_model_alias"] == "melix-dev-text-ultrachat")
    }

    @Test("lora train returns manifest json when requested")
    func loraTrainReturnsManifestJSONWhenRequested() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/train_lora/job-1",
            manifestJSON: #"{"job_id":"job-1","status":"completed"}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraTrain(
                .init(
                    modelID: "melix-dev-text",
                    datasetSourceKind: "local_package",
                    datasetURI: "/tmp/datasets/alpaca.jsonl",
                    adapterName: "demo-adapter",
                    json: true
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.ext["target_repo"] == nil)
        #expect(output == #"{"job_id":"job-1","status":"completed"}"#)
    }

    @Test("lora activate forwards adapter path and derived alias")
    func loraActivateForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/activate_adapter/job-2"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraActivate(
                .init(
                    modelID: "melix-dev-text",
                    adapterPath: "/tmp/melix/adapters/demo-adapter.json",
                    derivedModelAlias: "melix-dev-text-demo"
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/activate_adapter/job-2")
        #expect(call.operation == "activate_adapter")
        #expect(call.ext["artifact_path"] == "/tmp/melix/adapters/demo-adapter.json")
        #expect(call.ext["derived_model_alias"] == "melix-dev-text-demo")
    }

    @Test("lora activate returns manifest json when requested without an alias")
    func loraActivateReturnsManifestJSONWhenRequested() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/activate_adapter/job-2",
            manifestJSON: #"{"job_id":"job-2","status":"completed"}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraActivate(
                .init(
                    modelID: "melix-dev-text",
                    adapterPath: "/tmp/melix/adapters/demo-adapter.json",
                    json: true
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.ext["derived_model_alias"] == nil)
        #expect(output == #"{"job_id":"job-2","status":"completed"}"#)
    }

    @Test("bench run loads the explicit model and returns JSON output")
    func benchRunLoadsExplicitModelAndReturnsJSONOutput() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-3/report.md",
                reportMarkdown: "# Melix Bench\n",
                metrics: ["bench.smoke.ttft_ms": 24.45]
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .benchRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["smoke", "latency"],
                    parameters: [
                        "sample_size": "8",
                        "batch_factor": "2",
                    ],
                    json: true
                )
            )
        )
        let benchRequest = try #require(await client.lastBenchRequest)
        let payload = try #require(parseJSONObject(output))
        let metrics = try #require(payload["metrics"] as? [String: Double])

        #expect(await client.loadedModelIDs == ["melix-dev-text"])
        #expect(benchRequest.modelID == "melix-dev-text")
        #expect(benchRequest.suites == ["smoke", "latency"])
        #expect(benchRequest.parameters["sample_size"] == "8")
        #expect(benchRequest.parameters["batch_factor"] == "2")
        #expect(payload["report_path"] as? String == "/tmp/melix/bench/job-3/report.md")
        #expect(payload["report_markdown"] as? String == "# Melix Bench\n")
        #expect(metrics["bench.smoke.ttft_ms"] == 24.45)
    }

    @Test("bench run returns plain markdown or the report path depending on the response")
    func benchRunReturnsPlainOutput() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-4/report.md",
                reportMarkdown: "# Bench Summary\n",
                metrics: [:]
            )
        )

        let markdown = try await MelixCLIRunner(client: client).run(
            .benchRun(.init(modelID: "melix-dev-text"))
        )
        #expect(markdown == "# Bench Summary\n")

        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-5/report.md",
                reportMarkdown: "",
                metrics: [:]
            )
        )

        let path = try await MelixCLIRunner(client: client).run(
            .benchRun(.init(modelID: "melix-dev-text"))
        )
        #expect(path == "/tmp/melix/bench/job-5/report.md")
    }

    @Test("bench list renders history rows and returns JSON when requested")
    func benchListRendersHistoryRowsAndJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        let textOutput = try await MelixCLIRunner(client: client).run(.benchList(.init()))
        let jsonOutput = try await MelixCLIRunner(client: client).run(.benchList(.init(json: true)))
        let entries = try #require(parseJSONArray(jsonOutput))
        let benchOneEntry = try #require(entries.first(where: {
            ($0 as? [String: Any])?["job_id"] as? String == "bench-1"
        }) as? [String: Any])

        #expect(textOutput.contains("job_id\tmodel_id\tsuite\tdataset"))
        #expect(textOutput.contains("bench-1\tmelix-dev-text\tsmoke\tHuggingFaceH4/ultrachat_200k/default:train_sft\t4\t2\tcompleted\t1712100000000"))
        #expect(benchOneEntry["job_id"] as? String == "bench-1")
        #expect(benchOneEntry["suite_id"] as? String == "smoke")
        #expect(benchOneEntry["dataset_repo"] as? String == "HuggingFaceH4/ultrachat_200k")
    }

    @Test("bench export-csv writes filtered benchmark metric rows and returns JSON metadata")
    func benchExportCSVWritesFilteredRows() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let outputURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("bench-1.csv")

        let jsonOutput = try await MelixCLIRunner(client: client).run(
            .benchExportCSV(.init(jobID: "bench-1", outputPath: outputURL.path, json: true))
        )
        let response = try #require(parseJSONObject(jsonOutput))
        let csv = try String(contentsOf: outputURL, encoding: .utf8)

        #expect(response["job_id"] as? String == "bench-1")
        #expect(response["output_path"] as? String == outputURL.path)
        #expect(response["row_count"] as? Int == 2)
        #expect(csv.contains("job_id,model_id,suite_id,dataset_repo,dataset_config,dataset_split,sample_size,batch_factor,metric_name,metric_value,unit,created_at_unix_ms"))
        #expect(csv.contains("bench-1,melix-dev-text,smoke,HuggingFaceH4/ultrachat_200k,default,train_sft,4,2,bench.smoke.tokens_per_second,47.08,tok/s,1712100000000"))
        #expect(csv.contains("bench-1,melix-dev-text,smoke,HuggingFaceH4/ultrachat_200k,default,train_sft,4,2,bench.smoke.ttft_ms,24.45,ms,1712100000000"))
    }

    @Test("bench export-csv fails when the requested job is not present")
    func benchExportCSVFailsForMissingJob() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .benchExportCSV(.init(jobID: "bench-missing", outputPath: "/tmp/missing.csv"))
            )
            Issue.record("Expected bench export-csv to fail when the job is missing.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No benchmark metrics were found for job bench-missing."))
        }
    }

    @Test("lora list fails when the server snapshot has no models")
    func loraListFailsWhenServerSnapshotIsEmpty() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: []))

        do {
            _ = try await MelixCLIRunner(client: client).run(.loraList(.init()))
            Issue.record("Expected lora list to fail without an available model.")
        } catch let error as MelixCLIError {
            #expect(
                error == .missingRequired("No model is available in the current server snapshot.")
            )
        }
    }

    @Test("stub control-plane client covers auxiliary protocol helpers used by the CLI tests")
    func stubControlPlaneClientCoversAuxiliaryHelpers() async throws {
        let client = StubControlPlaneXPCClient()

        let handshake = try await client.handshake()
        let subscription = await client.subscribe(lastSeenSeq: 7)
        var iterator = subscription.makeAsyncIterator()
        let chat = try await client.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )
        let unloaded = try await client.unloadModel(modelID: "melix-dev-text")
        let updated = try await client.updateModelSettings(modelID: "melix-dev-text", values: ["alias": "Demo"])
        let info = try await client.modelInfo(modelID: "melix-dev-text")
        let generated = try await client.generateImage(
            .init(modelID: "melix-dev-image", prompt: "render")
        )
        let edited = try await client.editImage(
            .init(modelID: "melix-dev-image", prompt: "edit")
        )
        let doctor = try await client.runDoctor()
        let cancelled = try await client.cancelRequest(requestID: "request-1")
        try await client.applyServerSessionGatewayAccess(
            serverSessionID: "session-1",
            primaryKey: "pk",
            keyID: "key",
            label: "demo",
            tokenHint: "***"
        )
        try await client.clearServerSessionGatewayAccess(serverSessionID: "session-1")

        #expect(handshake.protocolVersion.isEmpty)
        #expect(await iterator.next() == nil)
        #expect(chat.requestID == "stub-chat")
        #expect(unloaded.modelID == "melix-dev-text")
        #expect(updated.modelID == "melix-dev-text")
        #expect(info.ok == false)
        #expect(generated.jobID.isEmpty)
        #expect(edited.jobID.isEmpty)
        #expect(doctor.isEmpty)
        #expect(cancelled == false)
        #expect(parseJSONObject("not-json") == nil)
        #expect(parseJSONObject(#"{"ok":true}"#)?["ok"] as? Bool == true)
    }
}

private actor StubControlPlaneXPCClient: ControlPlaneXPCClient {
    struct ModelOperationCall: Sendable, Equatable {
        let modelID: String
        let operation: String
        let ext: [String: String]
    }

    private(set) var lastModelOperationCall: ModelOperationCall?
    private(set) var lastBenchRequest: ControlPlaneBenchRequest?
    private(set) var loadedModelIDs: [String] = []

    private var snapshot = makeServerSnapshot(models: [makeModelSummary(id: "melix-dev-text", kind: "text")])
    private var modelOperationResult = makeModelOperationResult()
    private var benchResult = ControlPlaneBenchResult(reportPath: "", reportMarkdown: "", metrics: [:])
    private var exportResult = ControlPlaneExportResult(exportBundleJSON: #"{"export_schema_version":"melix.benchmark_export.v1","benchmark_jobs":[],"benchmark_results":[]}"#)

    func setServerSnapshot(_ snapshot: Melix_Controlplane_V1_ServerSnapshot) {
        self.snapshot = snapshot
    }

    func setModelOperationResult(_ result: Melix_Controlplane_V1_ModelOperationResult) {
        self.modelOperationResult = result
    }

    func setBenchResult(_ result: ControlPlaneBenchResult) {
        self.benchResult = result
    }

    func setExportResult(_ result: ControlPlaneExportResult) {
        self.exportResult = result
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        Melix_Controlplane_V1_HandshakeResponse()
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        _ = lastSeenSeq
        return AsyncStream { continuation in
            continuation.finish()
        }
    }

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        _ = request
        return ControlPlaneChatExecution(
            requestID: "stub-chat",
            modelID: "melix-dev-text",
            stream: AsyncThrowingStream { continuation in
                continuation.finish()
            }
        )
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        snapshot
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        loadedModelIDs.append(modelID)
        return makeModelSummary(id: modelID, kind: "text")
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        makeModelSummary(id: modelID, kind: "text")
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = values
        return makeModelSummary(id: modelID, kind: "text")
    }

    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        _ = modelID
        return Melix_Controlplane_V1_ModelInfo()
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
        _ = outputDir
        _ = quantProfileID
        _ = weightQuant
        _ = kvQuant
        lastModelOperationCall = ModelOperationCall(modelID: modelID, operation: operation, ext: ext)
        return modelOperationResult
    }

    func generateImage(
        _ request: ControlPlaneImageGenerationRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        _ = request
        return Melix_Controlplane_V1_ImageJobSummary()
    }

    func editImage(
        _ request: ControlPlaneImageEditRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        _ = request
        return Melix_Controlplane_V1_ImageJobSummary()
    }

    func runDoctor() async throws -> String {
        ""
    }

    func runBench(_ request: ControlPlaneBenchRequest) async throws -> ControlPlaneBenchResult {
        lastBenchRequest = request
        return benchResult
    }

    func exportResults(outputDir: String) async throws -> ControlPlaneExportResult {
        _ = outputDir
        return exportResult
    }

    func cancelRequest(requestID: String) async throws -> Bool {
        _ = requestID
        return false
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
    }

    func clearServerSessionGatewayAccess(serverSessionID: String) async throws {
        _ = serverSessionID
    }
}

private func makeServerSnapshot(
    models: [Melix_Controlplane_V1_ModelSummary]
) -> Melix_Controlplane_V1_ServerSnapshot {
    var snapshot = Melix_Controlplane_V1_ServerSnapshot()
    snapshot.models = models
    return snapshot
}

private func makeModelSummary(
    id: String,
    kind: String
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = id
    model.kind = kind
    return model
}

private func makeModelOperationResult(
    outputPath: String = "",
    manifestJSON: String = #"{"adapters":[]}"#
) -> Melix_Controlplane_V1_ModelOperationResult {
    var result = Melix_Controlplane_V1_ModelOperationResult()
    result.outputPath = outputPath
    result.manifestJson = manifestJSON
    return result
}

private func parseJSONObject(_ text: String) -> [String: Any]? {
    guard let data = text.data(using: .utf8) else {
        return nil
    }
    return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
}

private func parseJSONArray(_ text: String) -> [Any]? {
    guard let data = text.data(using: .utf8) else {
        return nil
    }
    return (try? JSONSerialization.jsonObject(with: data)) as? [Any]
}

private func makeBenchmarkExportBundleJSON() -> String {
    """
    {
      "export_schema_version": "melix.benchmark_export.v1",
      "exported_at_unix_ms": 1712101234567,
      "benchmark_jobs": [
        {
          "schema_version": "melix.serving_benchmark_job.v1",
          "job_id": "bench-1",
          "model_id": "melix-dev-text",
          "suites": ["smoke"],
          "parameters": {
            "sample_size": "4",
            "batch_factor": "2"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/bench/runs/bench-1",
          "created_at_unix_ms": 1712100000000,
          "updated_at_unix_ms": 1712100005000,
          "suite_metadata": {
            "smoke": {
              "title": "UltraChat Smoke",
              "dataset_path": "HuggingFaceH4/ultrachat_200k",
              "dataset_name": "default",
              "dataset_split": "train_sft",
              "sample_size": 4,
              "batch_factor": 2
            }
          }
        }
      ],
      "benchmark_results": [
        {
          "schema_version": "melix.serving_benchmark_result.v1",
          "job_id": "bench-1",
          "suite": "smoke",
          "metrics": [
            {"name": "bench.smoke.ttft_ms", "value": 24.45, "unit": "ms"},
            {"name": "bench.smoke.tokens_per_second", "value": 47.08, "unit": "tok/s"}
          ],
          "report_path": "/tmp/melix/bench/runs/bench-1/bench-report.md",
          "report_markdown": "# Melix Bench\\n"
        }
      ]
    }
    """
}
