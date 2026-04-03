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
        #expect(benchRequest.hfRepoID.isEmpty)
        #expect(benchRequest.suites == ["smoke", "latency"])
        #expect(benchRequest.parameters["sample_size"] == "8")
        #expect(benchRequest.parameters["batch_factor"] == "2")
        #expect(payload["report_path"] as? String == "/tmp/melix/bench/job-3/report.md")
        #expect(payload["report_markdown"] as? String == "# Melix Bench\n")
        #expect(metrics["bench.smoke.ttft_ms"] == 24.45)
    }

    @Test("bench run forwards a direct Hugging Face repo target without preloading a catalog model")
    func benchRunForDirectHFRepoSkipsModelPreload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-vlm/report.md",
                reportMarkdown: "# Melix Bench\n",
                metrics: ["bench.smoke.first_token_ms": 88.2]
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .benchRun(
                .init(
                    hfRepoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                    suites: ["smoke"],
                    json: true
                )
            )
        )
        let benchRequest = try #require(await client.lastBenchRequest)
        let payload = try #require(parseJSONObject(output))

        #expect(await client.loadedModelIDs.isEmpty)
        #expect(benchRequest.modelID.isEmpty)
        #expect(benchRequest.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(payload["report_path"] as? String == "/tmp/melix/bench/job-vlm/report.md")
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

        #expect(textOutput.contains("job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tdataset"))
        #expect(textOutput.contains("bench-1\tmelix-dev-text\ttext-generation\tHuggingFaceH4/ultrachat_200k\tsmoke\tHuggingFaceH4/ultrachat_200k/default:train_sft\t4\t2\tcompleted\t1712100000000"))
        #expect(benchOneEntry["job_id"] as? String == "bench-1")
        #expect(benchOneEntry["suite_id"] as? String == "smoke")
        #expect(benchOneEntry["dataset_repo"] as? String == "HuggingFaceH4/ultrachat_200k")
        #expect(benchOneEntry["task_kind"] as? String == "text-generation")
        #expect(benchOneEntry["source_repo"] as? String == "HuggingFaceH4/ultrachat_200k")
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
        #expect(csv.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_repo,dataset_config,dataset_split,sample_size,batch_factor,metric_name,metric_value,unit,created_at_unix_ms"))
        #expect(csv.contains("bench-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,smoke,HuggingFaceH4/ultrachat_200k,default,train_sft,4,2,bench.smoke.tokens_per_second,47.08,tok/s,1712100000000"))
        #expect(csv.contains("bench-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,smoke,HuggingFaceH4/ultrachat_200k,default,train_sft,4,2,bench.smoke.ttft_ms,24.45,ms,1712100000000"))
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

    @Test("eval run forwards sequential suite requests and returns JSON output")
    func evalRunForwardsSuiteRequestsAndReturnsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-1",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                metricName: "eval.mmlu.accuracy",
                metricValue: 0.75
            ),
            makeEvaluationRunResult(
                jobID: "eval-2",
                suiteID: "gsm8k",
                datasetID: "gsm8k.dev.v1",
                metricName: "eval.gsm8k.exact_match",
                metricValue: 0.5
            ),
        ])

        let output = try await MelixCLIRunner(client: client).run(
            .evalRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["mmlu", "gsm8k"],
                    sampleSize: 8,
                    parameters: ["batch_factor": "2", "few_shot": "4"],
                    json: true
                )
            )
        )
        let payload = try #require(parseJSONArray(output))
        let requests = await client.evaluationRequests

        #expect(requests.count == 2)
        #expect(requests[0].suiteID == "mmlu")
        #expect(requests[0].datasetID == "mmlu.dev.v1")
        #expect(requests[0].sampleSize == 8)
        #expect(requests[0].parameters["batch_factor"] == "2")
        #expect(requests[1].suiteID == "gsm8k")
        #expect(requests[1].datasetID == "gsm8k.dev.v1")
        let firstRun = try #require(payload.first as? [String: Any])
        let firstJob = try #require(firstRun["job"] as? [String: Any])
        #expect(firstJob["job_id"] as? String == "eval-1")
        #expect(firstJob["suite_id"] as? String == "mmlu")
    }

    @Test("eval run renders tabular text output for completed suites")
    func evalRunRendersTextOutput() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-1",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                metricName: "eval.mmlu.accuracy",
                metricValue: 0.75
            ),
        ])

        let output = try await MelixCLIRunner(client: client).run(
            .evalRun(
                .init(
                    modelID: "melix-dev-text",
                    sampleSize: 8
                )
            )
        )
        let request = try #require((await client.evaluationRequests).first)

        #expect(request.suiteID == "mmlu")
        #expect(request.datasetID == "mmlu.dev.v1")
        #expect(output.contains("job_id\tsuite\tdataset\tstatus\tmetrics"))
        #expect(output.contains("eval-1\tmmlu\tmmlu.dev.v1\tcompleted\teval.mmlu.accuracy=0.75ratio"))
    }

    @Test("eval list renders history rows and returns JSON when requested")
    func evalListRendersHistoryRowsAndJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        let textOutput = try await MelixCLIRunner(client: client).run(.evalList(.init()))
        let jsonOutput = try await MelixCLIRunner(client: client).run(.evalList(.init(json: true)))
        let entries = try #require(parseJSONArray(jsonOutput))
        let evalEntry = try #require(entries.first as? [String: Any])

        #expect(textOutput.contains("job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tdataset\tsample_size\tscoring_mode\tstatus\tcreated_at_unix_ms"))
        #expect(textOutput.contains("eval-1\tmelix-dev-text\ttext-generation\tHuggingFaceH4/ultrachat_200k\tmmlu\tmmlu.dev.v1\t8\tmultiple_choice_accuracy\tcompleted\t1712400000000"))
        #expect(evalEntry["job_id"] as? String == "eval-1")
        #expect(evalEntry["suite_id"] as? String == "mmlu")
        #expect(evalEntry["task_kind"] as? String == "text-generation")
    }

    @Test("eval list renders the empty history state when no evaluation jobs are present")
    func evalListRendersEmptyState() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeEmptyBenchmarkExportBundleJSON()))

        let output = try await MelixCLIRunner(client: client).run(.evalList(.init()))

        #expect(output == "No evaluation runs found.\n")
    }

    @Test("eval export commands write summary csv and sample artifacts")
    func evalExportCommandsWriteArtifacts() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let summaryURL = root.appendingPathComponent("eval-1-summary.csv")
        let samplesURL = root.appendingPathComponent("eval-1-samples.csv")
        let jsonlURL = root.appendingPathComponent("eval-1-samples.jsonl")

        let summaryOutput = try await MelixCLIRunner(client: client).run(
            .evalExportSummaryCSV(.init(jobID: "eval-1", outputPath: summaryURL.path, json: true))
        )
        _ = try await MelixCLIRunner(client: client).run(
            .evalExportSamplesCSV(.init(jobID: "eval-1", outputPath: samplesURL.path))
        )
        _ = try await MelixCLIRunner(client: client).run(
            .evalExportSamplesJSONL(.init(jobID: "eval-1", outputPath: jsonlURL.path))
        )

        let response = try #require(parseJSONObject(summaryOutput))
        let summaryCSV = try String(contentsOf: summaryURL, encoding: .utf8)
        let samplesCSV = try String(contentsOf: samplesURL, encoding: .utf8)
        let samplesJSONL = try String(contentsOf: jsonlURL, encoding: .utf8)

        #expect(response["job_id"] as? String == "eval-1")
        #expect(response["row_count"] as? Int == 1)
        #expect(summaryCSV.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,scoring_mode,metric_name,metric_value,unit,created_at_unix_ms"))
        #expect(summaryCSV.contains("eval-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,mmlu,mmlu.dev.v1,8,multiple_choice_accuracy,eval.mmlu.accuracy,0.75,ratio,1712400000000"))
        #expect(samplesCSV.contains("id,correct,expected,predicted,question,raw_response,time_s,parse_status"))
        #expect(samplesCSV.contains("sample-1,true,4,4,2+2?,4,0.01,parsed"))
        #expect(samplesJSONL.contains("\"sample_id\":\"sample-1\""))
    }

    @Test("eval export commands fail when the requested job has no rows")
    func evalExportCommandsFailForMissingJob() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .evalExportSummaryCSV(.init(jobID: "eval-missing", outputPath: "/tmp/eval-missing.csv"))
            )
            Issue.record("Expected eval export-summary-csv to fail when the job is missing.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No evaluation rows were found for job eval-missing."))
        }
    }

    @Test("runner default live client path uses the supplied environment-backed service builder")
    func runnerDefaultLiveClientPathUsesServiceBuilder() async throws {
        let recorder = EnvironmentRecorder()
        let runner = MelixCLIRunner(
            environment: [
                "MELIX_REPO_ROOT": "/tmp/melix-repo",
                "MELIX_WORKER_SOCKET_PATH": "/tmp/melix-python.sock",
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift.sock",
            ],
            serviceBuilder: { environment in
                recorder.record(environment)
                return ExportResultsOnlyControlPlaneService(exportBundleJSON: makeBenchmarkExportBundleJSON())
            }
        )

        let output = try await runner.run(.benchList(.init()))
        let environment = try #require(recorder.environment)

        #expect(environment["MELIX_REPO_ROOT"] == "/tmp/melix-repo")
        #expect(environment["MELIX_WORKER_SOCKET_PATH"] == "/tmp/melix-python.sock")
        #expect(environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] == "/tmp/melix-swift.sock")
        #expect(output.contains("bench-1\tmelix-dev-text\ttext-generation\tHuggingFaceH4/ultrachat_200k\tsmoke"))
    }

    @Test("default runner instantiates the built-in local runtime with an explicit repo root")
    func defaultRunnerInstantiatesLocalRuntimeWithExplicitRepoRoot() {
        let repoRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .path

        _ = MelixCLIRunner(
            environment: [
                "MELIX_REPO_ROOT": repoRoot,
                "MELIX_WORKER_SOCKET_PATH": "/tmp/melix-python.sock",
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift.sock",
            ]
        )

        #expect(Bool(true))
    }

    @Test("default runner falls back to the repository path when MELIX_REPO_ROOT is absent")
    func defaultRunnerInstantiatesLocalRuntimeWithFallbackRepoRoot() {
        _ = MelixCLIRunner(
            environment: [
                "MELIX_WORKER_SOCKET_PATH": "/tmp/melix-python.sock",
                "MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH": "/tmp/melix-swift.sock",
            ]
        )

        #expect(Bool(true))
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

private final class EnvironmentRecorder: @unchecked Sendable {
    private(set) var environment: [String: String]?

    func record(_ environment: [String: String]) {
        self.environment = environment
    }
}

private actor ExportResultsOnlyControlPlaneService: ControlPlaneExecuting {
    private let exportBundleJSON: String

    init(exportBundleJSON: String) {
        self.exportBundleJSON = exportBundleJSON
    }

    func handshake(
        _ request: Melix_Controlplane_V1_HandshakeRequest
    ) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        _ = request
        return Melix_Controlplane_V1_HandshakeResponse()
    }

    func subscribe(
        _ request: Melix_Controlplane_V1_SubscribeRequest
    ) async -> ControlPlaneSubscription {
        _ = request
        return ControlPlaneSubscription(
            subscriptionID: "sub-export-only",
            stream: AsyncStream { continuation in
                continuation.finish()
            }
        )
    }

    func unsubscribe(_ subscriptionID: String) async {
        _ = subscriptionID
    }

    func startChat(
        _ request: ControlPlaneChatRequest
    ) async throws -> ControlPlaneChatExecution {
        _ = request
        return ControlPlaneChatExecution(
            requestID: "export-only-chat",
            modelID: "melix-dev-text",
            stream: AsyncThrowingStream { continuation in
                continuation.finish()
            }
        )
    }

    func execute(
        _ request: Melix_Controlplane_V1_ControlPlaneRequest
    ) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        guard case .ops(let command) = request.command,
              case .exportResults = command.kind
        else {
            Issue.record("Unexpected control-plane command for export-only CLI service.")
            return Melix_Controlplane_V1_ControlPlaneResponse()
        }

        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.requestID = request.requestID
        response.commandType = request.commandType
        response.ok = true
        response.ops.exportBundleJson = exportBundleJSON
        return response
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
    private(set) var evaluationRequests: [ControlPlaneEvaluationRequest] = []
    private(set) var loadedModelIDs: [String] = []

    private var snapshot = makeServerSnapshot(models: [makeModelSummary(id: "melix-dev-text", kind: "text")])
    private var modelOperationResult = makeModelOperationResult()
    private var benchResult = ControlPlaneBenchResult(reportPath: "", reportMarkdown: "", metrics: [:])
    private var evaluationResultsQueue: [ControlPlaneEvaluationResult] = []
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

    func setEvaluationResults(_ results: [ControlPlaneEvaluationResult]) {
        self.evaluationResultsQueue = results
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

    func runEvaluation(_ request: ControlPlaneEvaluationRequest) async throws -> ControlPlaneEvaluationResult {
        evaluationRequests.append(request)
        guard evaluationResultsQueue.isEmpty == false else {
            throw MelixCLIError.runtime("No stub evaluation result is configured.")
        }
        return evaluationResultsQueue.removeFirst()
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
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
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
      ,
      "evaluation_jobs": [
        {
          "schema_version": "melix.evaluation_job.v1",
          "job_id": "eval-1",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "scoring_mode": "multiple_choice_accuracy",
          "parameters": {
            "few_shot": "4"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/evaluation/runs/eval-1",
          "created_at_unix_ms": 1712400000000,
          "updated_at_unix_ms": 1712400005000
        }
      ],
      "evaluation_results": [
        {
          "schema_version": "melix.evaluation_result.v1",
          "job_id": "eval-1",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "metrics": [
            {"name": "eval.mmlu.accuracy", "value": 0.75, "unit": "ratio"}
          ],
          "report_path": "/tmp/melix/evaluation/runs/eval-1/evaluation-result.json"
        }
      ],
      "evaluation_samples": [
        {
          "schema_version": "melix.evaluation_sample.v1",
          "job_id": "eval-1",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_id": "sample-1",
          "question": "2+2?",
          "expected": "4",
          "predicted": "4",
          "raw_response": "4",
          "correct": true,
          "time_s": 0.01,
          "parse_status": "parsed"
        }
      ]
    }
    """
}

private func makeEmptyBenchmarkExportBundleJSON() -> String {
    """
    {
      "export_schema_version": "melix.benchmark_export.v1",
      "benchmark_jobs": [],
      "benchmark_results": [],
      "evaluation_jobs": [],
      "evaluation_results": [],
      "evaluation_samples": []
    }
    """
}

private func makeEvaluationRunResult(
    jobID: String,
    suiteID: String,
    datasetID: String,
    metricName: String,
    metricValue: Double
) -> ControlPlaneEvaluationResult {
    var job = Melix_Controlplane_V1_EvaluationJobSummary()
    job.schemaVersion = "melix.evaluation_job.v1"
    job.jobID = jobID
    job.modelID = "melix-dev-text"
    job.taskKind = "text-generation"
    job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
    job.suiteID = suiteID
    job.datasetID = datasetID
    job.sampleSize = 8
    job.scoringMode = "multiple_choice_accuracy"
    job.status = "completed"
    job.outputDir = "/tmp/melix/evaluation/runs/\(jobID)"
    job.createdAtUnixMs = 1712400000000
    job.updatedAtUnixMs = 1712400005000

    var metric = Melix_Controlplane_V1_BenchmarkMetricValue()
    metric.name = metricName
    metric.value = metricValue
    metric.unit = "ratio"

    var result = Melix_Controlplane_V1_EvaluationResultSummary()
    result.schemaVersion = "melix.evaluation_result.v1"
    result.jobID = jobID
    result.suiteID = suiteID
    result.datasetID = datasetID
    result.sampleSize = 8
    result.metrics = [metric]
    result.reportPath = "/tmp/melix/evaluation/runs/\(jobID)/evaluation-result.json"
    return ControlPlaneEvaluationResult(job: job, results: [result])
}
