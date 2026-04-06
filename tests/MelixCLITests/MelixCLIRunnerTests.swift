import Foundation
import Testing

@testable import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Melix CLI Runner")
struct MelixCLIRunnerTests {
    @Test("server snapshot renders runtime session metadata")
    func serverSnapshotRendersRuntimeSessionMetadata() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(runtimeSessions: [makeRuntimeSession()]))

        let output = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init()))

        #expect(output.contains("server_state\tserver_session_id\tlifecycle_state"))
        #expect(output.contains("server_ready\tserver-session-1\tready\tactive\tinitial_boot"))
    }

    @Test("server lifecycle commands forward session ids and render updated snapshots")
    func serverLifecycleCommandsForwardSessionIDsAndRenderUpdatedSnapshots() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot())

        let startOutput = try await MelixCLIRunner(client: client).run(
            .serverStart(.init(serverSessionID: "server-session-2"))
        )
        let resumeOutput = try await MelixCLIRunner(client: client).run(
            .serverResume(.init(serverSessionID: "server-session-2", json: true))
        )
        let wakeOutput = try await MelixCLIRunner(client: client).run(
            .serverWake(.init(serverSessionID: "server-session-2", json: true))
        )
        let stopOutput = try await MelixCLIRunner(client: client).run(
            .serverStop(.init(serverSessionID: "server-session-2"))
        )

        let wakePayload = try #require(parseJSONObject(wakeOutput))
        let wakeSessions = try #require(wakePayload["runtime_sessions"] as? [[String: Any]])
        let wakeSession = try #require(wakeSessions.first)

        #expect(startOutput.contains("server_ready\tserver-session-2\tready\tactive\toperator_resume"))
        #expect(resumeOutput.contains(#""wake_reason" : "operator_resume""#))
        #expect(wakeSession["wake_reason"] as? String == "request_activity")
        #expect(stopOutput.contains("server_stopped\tserver-session-2\tstopped\tstopped\trequest_activity"))
        #expect(await client.lastServerAction == .stop("server-session-2"))
    }

    @Test("server pause forwards the target session and returns json output")
    func serverPauseForwardsTargetSessionAndReturnsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(runtimeSessions: [makeRuntimeSession()]))

        let output = try await MelixCLIRunner(client: client).run(
            .serverPause(.init(serverSessionID: "server-session-1", json: true))
        )
        let action = try #require(await client.lastServerAction)
        let payload = try #require(parseJSONObject(output))
        let runtimeSessions = try #require(payload["runtime_sessions"] as? [[String: Any]])
        let firstSession = try #require(runtimeSessions.first)

        #expect(action == .pause("server-session-1"))
        #expect(payload["server_state"] as? String == "server_degraded")
        #expect(firstSession["server_session_id"] as? String == "server-session-1")
        #expect(firstSession["lifecycle_state"] as? String == "paused")
        #expect(firstSession["power_state"] as? String == "active")
    }

    @Test("server idle policy forwards thresholds and returns updated runtime metadata")
    func serverIdlePolicyForwardsThresholdsAndReturnsUpdatedRuntimeMetadata() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(runtimeSessions: [makeRuntimeSession()]))

        let output = try await MelixCLIRunner(client: client).run(
            .serverSetIdlePolicy(
                .init(
                    serverSessionID: "server-session-1",
                    autoSleepEnabled: true,
                    lightSleepAfterSeconds: 60,
                    deepSleepAfterSeconds: 600,
                    json: true
                )
            )
        )
        let call = try #require(await client.lastIdlePolicyCall)
        let payload = try #require(parseJSONObject(output))
        let runtimeSessions = try #require(payload["runtime_sessions"] as? [[String: Any]])
        let firstSession = try #require(runtimeSessions.first)

        #expect(call.serverSessionID == "server-session-1")
        #expect(call.autoSleepEnabled)
        #expect(call.lightSleepAfterSeconds == 60)
        #expect(call.deepSleepAfterSeconds == 600)
        #expect(firstSession["auto_sleep_enabled"] as? Bool == true)
        #expect(firstSession["light_sleep_after_seconds"] as? Int == 60)
        #expect(firstSession["deep_sleep_after_seconds"] as? Int == 600)
    }

    @Test("server snapshot renders empty sessions and fallback labels")
    func serverSnapshotRendersEmptySessionsAndFallbackLabels() async throws {
        let client = StubControlPlaneXPCClient()

        var emptySnapshot = Melix_Controlplane_V1_ServerSnapshot()
        emptySnapshot.serverState = .serverBooting
        await client.setServerSnapshot(emptySnapshot)
        let emptyOutput = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init()))

        var loadingSession = makeRuntimeSession(serverSessionID: "server-session-loading")
        loadingSession.lifecycleState = .loading
        loadingSession.powerState = .lightSleep
        loadingSession.wakeReason = .toolActivity
        var stoppedSession = makeRuntimeSession(serverSessionID: "server-session-stopped")
        stoppedSession.lifecycleState = .stopped
        stoppedSession.powerState = .stopped
        stoppedSession.wakeReason = .policyApply
        var failedSession = makeRuntimeSession(serverSessionID: "server-session-failed")
        failedSession.lifecycleState = .error
        failedSession.powerState = .deepSleep
        failedSession.wakeReason = .operatorResume
        var unknownSession = makeRuntimeSession(serverSessionID: "server-session-unknown")
        unknownSession.lifecycleState = .UNRECOGNIZED(999)
        unknownSession.powerState = .UNRECOGNIZED(999)
        unknownSession.wakeReason = .UNRECOGNIZED(999)

        var richSnapshot = Melix_Controlplane_V1_ServerSnapshot()
        richSnapshot.serverState = .serverDraining
        richSnapshot.runtimeSessions = [loadingSession]
        await client.setServerSnapshot(richSnapshot)
        let loadingOutput = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init()))

        richSnapshot.serverState = .serverStopped
        richSnapshot.runtimeSessions = [stoppedSession]
        await client.setServerSnapshot(richSnapshot)
        let stoppedOutput = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init()))

        richSnapshot.serverState = .serverFailed
        richSnapshot.runtimeSessions = [failedSession]
        await client.setServerSnapshot(richSnapshot)
        let failedOutput = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init()))

        richSnapshot.serverState = .UNRECOGNIZED(999)
        richSnapshot.runtimeSessions = [unknownSession]
        await client.setServerSnapshot(richSnapshot)
        let unknownOutput = try await MelixCLIRunner(client: client).run(.serverSnapshot(.init(json: true)))

        #expect(emptyOutput == "server_state=server_booting\nNo runtime sessions found.\n")
        #expect(loadingOutput.contains("server_draining\tserver-session-loading\tloading\tlight_sleep\ttool_activity"))
        #expect(stoppedOutput.contains("server_stopped\tserver-session-stopped\tstopped\tstopped\tpolicy_apply"))
        #expect(failedOutput.contains("server_failed\tserver-session-failed\terror\tdeep_sleep\toperator_resume"))
        #expect(unknownOutput.contains(#""server_state" : "server_state_unspecified""#))
        #expect(unknownOutput.contains(#""lifecycle_state" : "lifecycle_unspecified""#))
        #expect(unknownOutput.contains(#""power_state" : "power_unspecified""#))
        #expect(unknownOutput.contains(#""wake_reason" : "wake_unspecified""#))
    }

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
                    contextLengths: [2048],
                    generationLength: 256,
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
        #expect(benchRequest.contextLengths == [2048])
        #expect(benchRequest.generationLength == 256)
        #expect(benchRequest.batchSizes.isEmpty)
        #expect(benchRequest.repeats == 1)
        #expect(benchRequest.parameters["sample_size"] == "8")
        #expect(benchRequest.parameters["batch_factor"] == "2")
        #expect(payload["report_path"] as? String == "/tmp/melix/bench/job-3/report.md")
        #expect(payload["report_markdown"] as? String == "# Melix Bench\n")
        #expect(metrics["bench.smoke.ttft_ms"] == 24.45)
    }

    @Test("bench run forwards canonical normalized request values")
    func benchRunForwardsCanonicalNormalizedRequestValues() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/job-canonical/report.md",
                reportMarkdown: "# Melix Bench\n",
                metrics: [:]
            )
        )

        _ = try await MelixCLIRunner(client: client).run(
            .benchRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["smoke"],
                    contextLengths: [4096, 1024],
                    generationLength: 128,
                    batchSizes: [4, 2],
                    repeats: 0,
                    cacheProfile: "partial_prefix",
                    reasoningMode: "enabled",
                    structuredOutputMode: "json_schema"
                )
            )
        )
        let benchRequest = try #require(await client.lastBenchRequest)

        #expect(benchRequest.contextLengths == [1024, 4096])
        #expect(benchRequest.generationLength == 128)
        #expect(benchRequest.batchSizes == [2, 4])
        #expect(benchRequest.repeats == 1)
        #expect(benchRequest.cacheProfile == "partial_prefix")
        #expect(benchRequest.reasoningMode == "enabled")
        #expect(benchRequest.structuredOutputMode == "json_schema")
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

    @Test("bench matrix run forwards normalized matrix inputs and returns JSON output")
    func benchMatrixRunForwardsNormalizedInputsAndReturnsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchMatrixResult(
            .init(
                job: makeBenchmarkMatrixJobSummary(
                    jobID: "bench-matrix-1",
                    modelID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                    taskKind: "image-text-to-text",
                    sourceRepo: "unsloth/gemma-4-E4B-it-MLX-8bit"
                ),
                summaryRows: [
                    makeBenchmarkMatrixSummaryRow(
                        jobID: "bench-matrix-1",
                        taskKind: "image-text-to-text",
                        sourceRepo: "unsloth/gemma-4-E4B-it-MLX-8bit",
                        modelID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                        suiteID: "smoke",
                        contextLength: 1024,
                        generationLength: 128,
                        batchSize: 2,
                        cacheProfile: "cold",
                        reasoningMode: "enabled",
                        structuredOutputMode: "plain_text",
                        concurrencyLevel: 1,
                        repeats: 3,
                        requests: 24,
                        durationSeconds: 0,
                        ttftMeanMS: 44.5
                    ),
                ]
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .benchMatrixRun(
                .init(
                    hfRepoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                    suites: ["latency", "smoke"],
                    contextLengths: [4096, 1024],
                    generationLengths: [256, 128],
                    batchSizes: [4, 2],
                    cacheProfiles: ["warm", "cold"],
                    reasoningModes: ["enabled", "disabled"],
                    structuredOutputModes: ["json_schema", "plain_text"],
                    concurrencyLevels: [8, 1],
                    repeats: 3,
                    requests: 24,
                    json: true
                )
            )
        )
        let request = try #require(await client.lastBenchMatrixRequest)
        let payload = try #require(parseJSONObject(output))
        let rows = try #require(payload["summary_rows"] as? [[String: Any]])
        let job = try #require(payload["job"] as? [String: Any])

        #expect(await client.loadedModelIDs.isEmpty)
        #expect(request.modelID.isEmpty)
        #expect(request.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(request.suites == ["latency", "smoke"])
        #expect(request.contextLengths == [1024, 4096])
        #expect(request.generationLengths == [128, 256])
        #expect(request.batchSizes == [2, 4])
        #expect(request.cacheProfiles == ["cold", "warm"])
        #expect(request.reasoningModes == ["disabled", "enabled"])
        #expect(request.structuredOutputModes == ["json_schema", "plain_text"])
        #expect(request.concurrencyLevels == [1, 8])
        #expect(request.repeats == 3)
        #expect(request.requests == 24)
        #expect(request.durationSeconds == 0)
        #expect(job["job_id"] as? String == "bench-matrix-1")
        #expect(rows.count == 1)
        #expect(rows[0]["ttft_mean_ms"] as? Double == 44.5)
    }

    @Test("bench matrix run loads explicit models and renders tabular text output")
    func benchMatrixRunLoadsExplicitModelsAndRendersTabularTextOutput() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchMatrixResult(
            .init(
                job: makeBenchmarkMatrixJobSummary(
                    jobID: "bench-matrix-2",
                    modelID: "melix-dev-text",
                    taskKind: "text-generation",
                    sourceRepo: "melix-dev-text"
                ),
                summaryRows: [
                    makeBenchmarkMatrixSummaryRow(
                        jobID: "bench-matrix-2",
                        taskKind: "text-generation",
                        sourceRepo: "melix-dev-text",
                        modelID: "melix-dev-text",
                        suiteID: "latency",
                        contextLength: 2048,
                        generationLength: 256,
                        batchSize: 4,
                        cacheProfile: "warm",
                        reasoningMode: "disabled",
                        structuredOutputMode: "json_schema",
                        concurrencyLevel: 2,
                        repeats: 2,
                        requests: 0,
                        durationSeconds: 45,
                        ttftMeanMS: 51.2
                    ),
                ]
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .benchMatrixRun(
                .init(
                    modelID: "melix-dev-text",
                    suites: ["latency"],
                    contextLengths: [2048],
                    generationLengths: [256],
                    batchSizes: [4],
                    cacheProfiles: ["warm"],
                    reasoningModes: ["disabled"],
                    structuredOutputModes: ["json_schema"],
                    concurrencyLevels: [2],
                    repeats: 2,
                    durationSeconds: 45
                )
            )
        )

        #expect(await client.loadedModelIDs == ["melix-dev-text"])
        #expect(output.contains("job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tcontext_length"))
        #expect(output.contains("bench-matrix-2\tmelix-dev-text\ttext-generation\tmelix-dev-text\tlatency\t2048\t256\t4\twarm\tdisabled\tjson_schema\t2\t2\tduration_seconds=45\t51.2"))
    }

    @Test("bench matrix run renders the empty state when no matrix rows are returned")
    func benchMatrixRunRendersEmptyState() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setBenchMatrixResult(
            .init(
                job: makeBenchmarkMatrixJobSummary(
                    jobID: "bench-matrix-empty",
                    modelID: "melix-dev-text",
                    taskKind: "text-generation",
                    sourceRepo: "melix-dev-text"
                ),
                summaryRows: []
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .benchMatrixRun(
                .init(
                    hfRepoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                    suites: ["smoke"],
                    contextLengths: [1024],
                    generationLengths: [128],
                    batchSizes: [2],
                    cacheProfiles: ["cold"],
                    reasoningModes: ["enabled"],
                    structuredOutputModes: ["plain_text"],
                    concurrencyLevels: [1],
                    requests: 8
                )
            )
        )

        #expect(output == "No benchmark matrix rows were returned.\n")
    }

    @Test("bench matrix list renders matrix history and returns JSON when requested")
    func benchMatrixListRendersHistoryAndReturnsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        let textOutput = try await MelixCLIRunner(client: client).run(.benchMatrixList(.init()))
        let jsonOutput = try await MelixCLIRunner(client: client).run(.benchMatrixList(.init(json: true)))
        let entries = try #require(parseJSONArray(jsonOutput))
        let first = try #require(entries.first as? [String: Any])

        #expect(textOutput.contains("job_id\tmodel_id\ttask_kind\tsource_repo\tsuite\tcontext_length\tgeneration_length\tbatch_size\tcache_profile\treasoning_mode\tstructured_output_mode\tconcurrency_level\trepeats\tload_budget\tstatus\tcreated_at_unix_ms"))
        #expect(textOutput.contains("bench-matrix-1\tmelix-dev-text\ttext-generation\tHuggingFaceH4/ultrachat_200k\tsmoke\t1024\t128\t2\tcold\tenabled\tplain_text\t1\t3\trequests=24\tcompleted\t1712200000000"))
        #expect(first["job_id"] as? String == "bench-matrix-1")
        #expect(first["benchmark_mode"] as? String == "matrix")
    }

    @Test("bench matrix list renders an empty state when there is no matrix history")
    func benchMatrixListRendersEmptyState() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(
            .init(exportBundleJSON: #"{"export_schema_version":"melix.benchmark_export.v1","benchmark_matrix_jobs":[],"benchmark_matrix_summary_rows":[],"benchmark_matrix_request_rows":[]}"#)
        )

        let output = try await MelixCLIRunner(client: client).run(.benchMatrixList(.init()))

        #expect(output == "No benchmark matrix runs found.\n")
    }

    @Test("bench matrix export-summary-csv writes filtered rows")
    func benchMatrixExportSummaryCSVWritesFilteredRows() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let outputURL = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("bench-matrix-summary.csv")

        let jsonOutput = try await MelixCLIRunner(client: client).run(
            .benchMatrixExportSummaryCSV(
                .init(jobID: "bench-matrix-1", outputPath: outputURL.path, json: true)
            )
        )
        let response = try #require(parseJSONObject(jsonOutput))
        let csv = try String(contentsOf: outputURL, encoding: .utf8)

        #expect(response["job_id"] as? String == "bench-matrix-1")
        #expect(response["row_count"] as? Int == 1)
        #expect(csv.contains("job_id,task_kind,source_repo,model_id,suite_id,context_length,generation_length,batch_size,cache_profile,reasoning_mode,structured_output_mode,concurrency_level,repeats,requests,duration_seconds,ttft_mean_ms,ttft_std_ms,request_latency_mean_ms,request_latency_std_ms,prefill_tokens_per_second_mean,decode_tokens_per_second_mean,throughput_requests_per_second,throughput_tokens_per_second,success_rate,peak_memory_bytes_max,queue_wait_mean_ms,queue_wait_p95_ms,created_at_unix_ms"))
        #expect(csv.contains("bench-matrix-1,text-generation,HuggingFaceH4/ultrachat_200k,melix-dev-text,smoke,1024,128,2,cold,enabled,plain_text,1,3,24,0,24.45,1.2,88.4,3.1,1400.0,58.2,3.8,221.5,1.0,2147483648,5.1,9.2,1712200000000"))
    }

    @Test("bench matrix export-summary-csv returns the written path in plain text")
    func benchMatrixExportSummaryCSVReturnsTheWrittenPathInPlainText() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let outputURL = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("bench-matrix-summary.txt")

        let output = try await MelixCLIRunner(client: client).run(
            .benchMatrixExportSummaryCSV(.init(jobID: "bench-matrix-1", outputPath: outputURL.path))
        )

        #expect(output == outputURL.path + "\n")
    }

    @Test("bench matrix export-summary-csv fails when the requested job is missing")
    func benchMatrixExportSummaryCSVFailsForMissingJob() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .benchMatrixExportSummaryCSV(.init(jobID: "bench-matrix-missing", outputPath: "/tmp/missing.csv"))
            )
            Issue.record("Expected bench matrix export-summary-csv to fail when the job is missing.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No benchmark matrix summary rows were found for job bench-matrix-missing."))
        }
    }

    @Test("bench matrix export-requests-csv writes filtered rows")
    func benchMatrixExportRequestsCSVWritesFilteredRows() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let outputURL = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("bench-matrix-requests.csv")

        let jsonOutput = try await MelixCLIRunner(client: client).run(
            .benchMatrixExportRequestsCSV(
                .init(jobID: "bench-matrix-1", outputPath: outputURL.path, json: true)
            )
        )
        let response = try #require(parseJSONObject(jsonOutput))
        let csv = try String(contentsOf: outputURL, encoding: .utf8)

        #expect(response["job_id"] as? String == "bench-matrix-1")
        #expect(response["row_count"] as? Int == 1)
        #expect(csv.contains("job_id,cell_id,task_kind,suite_id,context_length,generation_length,batch_size,cache_profile,reasoning_mode,structured_output_mode,concurrency_level,repeat_index,request_index,ttft_ms,request_latency_ms,prefill_tokens_per_second,decode_tokens_per_second,queue_wait_ms,peak_memory_bytes,status,error_code,created_at_unix_ms"))
        #expect(csv.contains("bench-matrix-1,cell-1,text-generation,smoke,1024,128,2,cold,enabled,plain_text,1,0,0,24.45,88.4,1400.0,58.2,5.1,2147483648,completed,,1712200000000"))
    }

    @Test("bench matrix export-requests-csv returns the written path in plain text")
    func benchMatrixExportRequestsCSVReturnsTheWrittenPathInPlainText() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let outputURL = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent(UUID().uuidString)
            .appendingPathComponent("bench-matrix-requests.txt")

        let output = try await MelixCLIRunner(client: client).run(
            .benchMatrixExportRequestsCSV(.init(jobID: "bench-matrix-1", outputPath: outputURL.path))
        )

        #expect(output == outputURL.path + "\n")
    }

    @Test("bench matrix export-requests-csv fails when the requested job is missing")
    func benchMatrixExportRequestsCSVFailsForMissingJob() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .benchMatrixExportRequestsCSV(.init(jobID: "bench-matrix-missing", outputPath: "/tmp/missing.csv"))
            )
            Issue.record("Expected bench matrix export-requests-csv to fail when the job is missing.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No benchmark matrix request rows were found for job bench-matrix-missing."))
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
                    parameters: [
                        "batch_factor": "2",
                        "dataset_root": "/tmp/mmlu-split-01",
                        "few_shot": "4",
                        "seed": "7",
                        "scoring_mode": "multiple_choice_accuracy",
                        "code_exec_policy": "sandboxed",
                    ],
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
        #expect(requests[0].parameters["dataset_root"] == "/tmp/mmlu-split-01")
        #expect(requests[0].parameters["few_shot"] == "4")
        #expect(requests[0].parameters["seed"] == "7")
        #expect(requests[0].parameters["scoring_mode"] == "multiple_choice_accuracy")
        #expect(requests[0].parameters["code_exec_policy"] == "sandboxed")
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
        #expect(summaryCSV.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,score_name,score_value,correct_count,incorrect_count,duration_seconds,created_at_unix_ms"))
        #expect(summaryCSV.contains("eval-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,mmlu,mmlu.dev.v1,8,eval.mmlu.accuracy,0.75,6,2,12.5,1712400000000"))
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
    enum ServerAction: Sendable, Equatable {
        case start(String)
        case pause(String)
        case resume(String)
        case wake(String)
        case stop(String)
    }

    struct IdlePolicyCall: Sendable, Equatable {
        let serverSessionID: String
        let autoSleepEnabled: Bool
        let lightSleepAfterSeconds: UInt32
        let deepSleepAfterSeconds: UInt32
    }

    struct ModelOperationCall: Sendable, Equatable {
        let modelID: String
        let operation: String
        let ext: [String: String]
    }

    private(set) var lastServerAction: ServerAction?
    private(set) var lastIdlePolicyCall: IdlePolicyCall?
    private(set) var lastModelOperationCall: ModelOperationCall?
    private(set) var lastBenchRequest: ControlPlaneBenchRequest?
    private(set) var lastBenchMatrixRequest: ControlPlaneBenchMatrixRequest?
    private(set) var evaluationRequests: [ControlPlaneEvaluationRequest] = []
    private(set) var loadedModelIDs: [String] = []

    private var snapshot = makeServerSnapshot(models: [makeModelSummary(id: "melix-dev-text", kind: "text")])
    private var modelOperationResult = makeModelOperationResult()
    private var benchResult = ControlPlaneBenchResult(reportPath: "", reportMarkdown: "", metrics: [:])
    private var benchMatrixResult = ControlPlaneBenchMatrixResult(
        job: makeBenchmarkMatrixJobSummary(jobID: "", modelID: "", taskKind: "", sourceRepo: ""),
        summaryRows: []
    )
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

    func setBenchMatrixResult(_ result: ControlPlaneBenchMatrixResult) {
        self.benchMatrixResult = result
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

    func startServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServerAction = .start(serverSessionID)
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.lifecycleState = .ready
            session.powerState = .active
            session.wakeReason = .operatorResume
        }
        snapshot.serverState = .serverReady
        return snapshot
    }

    func pauseServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServerAction = .pause(serverSessionID)
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.lifecycleState = .paused
            session.powerState = .active
        }
        snapshot.serverState = .serverDegraded
        return snapshot
    }

    func resumeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServerAction = .resume(serverSessionID)
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.lifecycleState = .ready
            session.powerState = .active
            session.wakeReason = .operatorResume
        }
        snapshot.serverState = .serverReady
        return snapshot
    }

    func wakeServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServerAction = .wake(serverSessionID)
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.lifecycleState = .ready
            session.powerState = .active
            session.wakeReason = .requestActivity
        }
        snapshot.serverState = .serverReady
        return snapshot
    }

    func stopServerSession(serverSessionID: String) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServerAction = .stop(serverSessionID)
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.lifecycleState = .stopped
            session.powerState = .stopped
        }
        snapshot.serverState = .serverStopped
        return snapshot
    }

    func updateServerIdlePolicy(
        serverSessionID: String,
        autoSleepEnabled: Bool,
        lightSleepAfterSeconds: UInt32,
        deepSleepAfterSeconds: UInt32
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastIdlePolicyCall = IdlePolicyCall(
            serverSessionID: serverSessionID,
            autoSleepEnabled: autoSleepEnabled,
            lightSleepAfterSeconds: lightSleepAfterSeconds,
            deepSleepAfterSeconds: deepSleepAfterSeconds
        )
        mutateRuntimeSession(serverSessionID: serverSessionID) { session in
            session.autoSleepEnabled = autoSleepEnabled
            session.lightSleepAfterSeconds = lightSleepAfterSeconds
            session.deepSleepAfterSeconds = deepSleepAfterSeconds
        }
        return snapshot
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

    func runBenchMatrix(_ request: ControlPlaneBenchMatrixRequest) async throws -> ControlPlaneBenchMatrixResult {
        lastBenchMatrixRequest = request
        return benchMatrixResult
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

    private func mutateRuntimeSession(
        serverSessionID: String,
        update: (inout Melix_Controlplane_V1_ServerSessionRuntimeState) -> Void
    ) {
        if let index = snapshot.runtimeSessions.firstIndex(where: { $0.serverSessionID == serverSessionID }) {
            update(&snapshot.runtimeSessions[index])
            return
        }

        var session = makeRuntimeSession(serverSessionID: serverSessionID)
        update(&session)
        snapshot.runtimeSessions.append(session)
    }
}

private func makeServerSnapshot(
    models: [Melix_Controlplane_V1_ModelSummary] = [],
    runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState] = []
) -> Melix_Controlplane_V1_ServerSnapshot {
    var snapshot = Melix_Controlplane_V1_ServerSnapshot()
    snapshot.serverState = runtimeSessions.contains(where: { $0.lifecycleState == .paused || $0.lifecycleState == .sleeping })
        ? .serverDegraded
        : (runtimeSessions.allSatisfy { $0.lifecycleState == .stopped } && !runtimeSessions.isEmpty ? .serverStopped : .serverReady)
    snapshot.models = models
    snapshot.runtimeSessions = runtimeSessions
    return snapshot
}

private func makeRuntimeSession(
    serverSessionID: String = "server-session-1"
) -> Melix_Controlplane_V1_ServerSessionRuntimeState {
    var session = Melix_Controlplane_V1_ServerSessionRuntimeState()
    session.serverSessionID = serverSessionID
    session.lifecycleState = .ready
    session.powerState = .active
    session.wakeReason = .initialBoot
    session.updatedAtUnixMs = 1_234
    return session
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
      ],
      "benchmark_matrix_jobs": [
        {
          "schema_version": "melix.benchmark_matrix_job.v1",
          "job_id": "bench-matrix-1",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_ids": ["smoke"],
          "benchmark_mode": "matrix",
          "status": "completed",
          "output_dir": "/tmp/melix/bench/matrix-runs/bench-matrix-1",
          "created_at_unix_ms": 1712200000000,
          "updated_at_unix_ms": 1712200005000
        }
      ],
      "benchmark_matrix_summary_rows": [
        {
          "job_id": "bench-matrix-1",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "model_id": "melix-dev-text",
          "suite_id": "smoke",
          "context_length": 1024,
          "generation_length": 128,
          "batch_size": 2,
          "cache_profile": "cold",
          "reasoning_mode": "enabled",
          "structured_output_mode": "plain_text",
          "concurrency_level": 1,
          "repeats": 3,
          "requests": 24,
          "duration_seconds": 0,
          "ttft_mean_ms": 24.45,
          "ttft_std_ms": 1.2,
          "request_latency_mean_ms": 88.4,
          "request_latency_std_ms": 3.1,
          "prefill_tokens_per_second_mean": 1400.0,
          "decode_tokens_per_second_mean": 58.2,
          "throughput_requests_per_second": 3.8,
          "throughput_tokens_per_second": 221.5,
          "success_rate": 1.0,
          "peak_memory_bytes_max": 2147483648,
          "queue_wait_mean_ms": 5.1,
          "queue_wait_p95_ms": 9.2,
          "created_at_unix_ms": 1712200000000
        }
      ],
      "benchmark_matrix_request_rows": [
        {
          "job_id": "bench-matrix-1",
          "cell_id": "cell-1",
          "task_kind": "text-generation",
          "suite_id": "smoke",
          "context_length": 1024,
          "generation_length": 128,
          "batch_size": 2,
          "cache_profile": "cold",
          "reasoning_mode": "enabled",
          "structured_output_mode": "plain_text",
          "concurrency_level": 1,
          "repeat_index": 0,
          "request_index": 0,
          "ttft_ms": 24.45,
          "request_latency_ms": 88.4,
          "prefill_tokens_per_second": 1400.0,
          "decode_tokens_per_second": 58.2,
          "queue_wait_ms": 5.1,
          "peak_memory_bytes": 2147483648,
          "status": "completed",
          "error_code": "",
          "created_at_unix_ms": 1712200000000
        }
      ],
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
      "evaluation_summary_rows": [
        {
          "job_id": "eval-1",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "score_name": "eval.mmlu.accuracy",
          "score_value": 0.75,
          "correct_count": 6,
          "incorrect_count": 2,
          "duration_seconds": 12.5,
          "created_at_unix_ms": 1712400000000
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

private func makeBenchmarkMatrixJobSummary(
    jobID: String,
    modelID: String,
    taskKind: String,
    sourceRepo: String
) -> Melix_Controlplane_V1_BenchmarkMatrixJobSummary {
    var job = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
    job.schemaVersion = "melix.benchmark_matrix_job.v1"
    job.jobID = jobID
    job.modelID = modelID
    job.taskKind = taskKind
    job.sourceRepo = sourceRepo
    job.benchmarkMode = "matrix"
    job.status = "completed"
    job.outputDir = "/tmp/melix/bench/matrix-runs/\(jobID)"
    job.createdAtUnixMs = 1712200000000
    job.updatedAtUnixMs = 1712200005000
    return job
}

private func makeBenchmarkMatrixSummaryRow(
    jobID: String,
    taskKind: String,
    sourceRepo: String,
    modelID: String,
    suiteID: String,
    contextLength: UInt32,
    generationLength: UInt32,
    batchSize: UInt32,
    cacheProfile: String,
    reasoningMode: String,
    structuredOutputMode: String,
    concurrencyLevel: UInt32,
    repeats: UInt32,
    requests: UInt32,
    durationSeconds: UInt32,
    ttftMeanMS: Double
) -> Melix_Controlplane_V1_BenchmarkMatrixSummaryRow {
    var row = Melix_Controlplane_V1_BenchmarkMatrixSummaryRow()
    row.jobID = jobID
    row.taskKind = taskKind
    row.sourceRepo = sourceRepo
    row.modelID = modelID
    row.suiteID = suiteID
    row.contextLength = contextLength
    row.generationLength = generationLength
    row.batchSize = batchSize
    row.cacheProfile = cacheProfile
    row.reasoningMode = reasoningMode
    row.structuredOutputMode = structuredOutputMode
    row.concurrencyLevel = concurrencyLevel
    row.repeats = repeats
    row.requests = requests
    row.durationSeconds = durationSeconds
    row.ttftMeanMs = ttftMeanMS
    row.createdAtUnixMs = 1712200000000
    return row
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
