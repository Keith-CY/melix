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

    @Test("model hub search renders typed search results")
    func modelHubSearchRendersTypedSearchResults() async throws {
        let client = StubControlPlaneXPCClient()
        var result = Melix_Controlplane_V1_HubSearchResult()
        result.nextCursor = "cursor:page-2"
        var model = Melix_Controlplane_V1_HubModelSummary()
        model.repoID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        model.pipelineTag = "text-generation"
        model.mlxCompatible = true
        result.models = [model]
        await client.setHubSearchResult(result)

        let output = try await MelixCLIRunner(client: client).run(
            .modelHubSearch(.init(query: "qwen3.5", pageSize: 5, cursor: "", mlxOnly: true, json: false))
        )

        #expect(output.contains("repo_id\tpipeline_tag\tcompatibility"))
        #expect(output.contains("mlx-community/Qwen3.5-0.8B-OptiQ-4bit\ttext-generation\tmlx"))
    }

    @Test("model hub show renders typed model cards")
    func modelHubShowRendersTypedModelCards() async throws {
        let client = StubControlPlaneXPCClient()
        var card = Melix_Controlplane_V1_HubModelCard()
        card.repoID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        card.author = "mlx-community"
        card.modelName = "Qwen3.5-0.8B-OptiQ-4bit"
        card.pipelineTag = "text-generation"
        card.mlxCompatible = true
        await client.setHubModelCard(card)

        let output = try await MelixCLIRunner(client: client).run(
            .modelHubShow(.init(repoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", json: false))
        )

        #expect(output.contains("repo_id=mlx-community/Qwen3.5-0.8B-OptiQ-4bit"))
        #expect(output.contains("author=mlx-community"))
        #expect(output.contains("mlx_compatible=true"))
    }

    @Test("model download forwards the expected download operation payload")
    func modelDownloadForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/melix-downloads/melix-dev-text")
        )

        let output = try await MelixCLIRunner(client: client).run(
            .modelDownload(
                .init(
                    modelID: "melix-dev-text",
                    outputDir: "/tmp/melix-downloads/melix-dev-text"
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix-downloads/melix-dev-text\n")
        #expect(call.modelID == "melix-dev-text")
        #expect(call.operation == "download")
        #expect(call.ext.isEmpty)
    }

    @Test("doctor command renders markdown and structured json payloads")
    func doctorCommandRendersMarkdownAndStructuredJSONPayloads() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setDoctorReport(
            makeDoctorReport(
                markdown: "# Melix Doctor\n\n- worker_state: idle\n",
                healthStatus: .healthy,
                findings: [
                    ("cache_warning", .warning, "Cache pressure", "Cache usage crossed the warning threshold."),
                ]
            )
        )

        let textOutput = try await MelixCLIRunner(client: client).run(.doctor(.init()))
        let jsonOutput = try await MelixCLIRunner(client: client).run(.doctor(.init(json: true)))
        let payload = try #require(parseJSONObject(jsonOutput))
        let findings = try #require(payload["findings"] as? [[String: Any]])

        #expect(textOutput.contains("# Melix Doctor"))
        #expect(payload["markdown"] as? String == "# Melix Doctor\n\n- worker_state: idle\n")
        #expect(payload["health_status"] as? String == "healthy")
        #expect(findings.count == 1)
        #expect(findings[0]["code"] as? String == "cache_warning")
        #expect(findings[0]["severity"] as? String == "warning")
    }

    @Test("json v1 wraps command results in a stable envelope")
    func jsonV1WrapsCommandResultsInAStableEnvelope() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setDoctorReport(
            makeDoctorReport(
                markdown: "# Melix Doctor\n\n- worker_state: idle\n",
                healthStatus: .healthy
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            MelixCLIInvocation(
                command: .doctor(.init()),
                outputFormat: .jsonV1,
                traceID: "trace-json-v1"
            )
        )
        let envelope = try #require(parseJSONObject(output))
        let result = try #require(envelope["result"] as? [String: Any])
        let metrics = try #require(envelope["metrics"] as? [String: Any])

        #expect(envelope["schema_version"] as? String == "melix.cli.output.v1")
        #expect(envelope["command_id"] as? String == "doctor")
        #expect(envelope["status"] as? String == "succeeded")
        #expect(envelope["trace_id"] as? String == "trace-json-v1")
        #expect(result["health_status"] as? String == "healthy")
        #expect((metrics["melix.cli.parse_ms"] as? Double) != nil)
        #expect((metrics["melix.cli.command_ms"] as? Double) != nil)
        #expect((metrics["melix.cli.json_encode_ms"] as? Double) != nil)
    }

    @Test("json v1 error envelopes are machine readable")
    func jsonV1ErrorEnvelopesAreMachineReadable() throws {
        let output = try MelixCLIJSONEnvelope.errorEnvelopeString(
            commandID: "chat.run",
            traceID: "trace-error",
            error: MelixCLIError.missingRequired("--message is required for melix chat run."),
            metrics: ["melix.cli.parse_ms": 0.25]
        )
        let envelope = try #require(parseJSONObject(output))
        let error = try #require(envelope["error"] as? [String: Any])
        let metrics = try #require(envelope["metrics"] as? [String: Any])

        #expect(envelope["schema_version"] as? String == "melix.cli.error.v1")
        #expect(envelope["command_id"] as? String == "chat.run")
        #expect(envelope["status"] as? String == "failed")
        #expect(envelope["trace_id"] as? String == "trace-error")
        #expect(error["code"] as? String == "missing_required")
        #expect(error["message"] as? String == "--message is required for melix chat run.")
        #expect(metrics["melix.cli.parse_ms"] as? Double == 0.25)
    }

    @Test("json metric patching rejects missing placeholders")
    func jsonMetricPatchingRejectsMissingPlaceholders() throws {
        #expect(throws: MelixCLIError.runtime("Failed to encode CLI metrics placeholder.")) {
            try MelixCLIJSONMetricPatch.replacePlaceholder(in: "{}", with: 1)
        }
        #expect(throws: MelixCLIError.runtime("Failed to locate pipeline metrics placeholder.")) {
            try MelixCLIJSONMetricPatch.placeholderRange(in: Data("{}".utf8))
        }
        let duplicatePlaceholder = MelixCLIJSONMetricPatch.Placeholder(token: "__DUPLICATE__")
        #expect(throws: MelixCLIError.runtime("Found duplicate CLI metrics placeholders.")) {
            try MelixCLIJSONMetricPatch.replacePlaceholder(
                in: "\(duplicatePlaceholder.jsonLiteral) \(duplicatePlaceholder.jsonLiteral)",
                placeholder: duplicatePlaceholder,
                with: 1
            )
        }
        #expect(throws: MelixCLIError.runtime("Found duplicate pipeline metrics placeholders.")) {
            try MelixCLIJSONMetricPatch.placeholderRange(
                in: Data("\(duplicatePlaceholder.jsonLiteral) \(duplicatePlaceholder.jsonLiteral)".utf8),
                placeholder: duplicatePlaceholder
            )
        }
        #expect(throws: MelixCLIError.runtime("Pipeline metrics placeholder is too short for the encoded metric.")) {
            try MelixCLIJSONMetricPatch.paddedLiteralData(for: 1, byteCount: 1)
        }
    }

    @Test("json metric patching preserves user artifact strings that look like the old sentinel")
    func jsonMetricPatchingPreservesUserArtifactStringsThatLookLikeTheOldSentinel() throws {
        let sentinel = "9.9999999999989997e+99"
        let output = try MelixCLIJSONEnvelope.outputEnvelopeString(
            commandID: "doctor",
            traceID: "trace-sentinel",
            result: ["health_status": "healthy"],
            artifacts: [["path": sentinel]]
        )
        let envelope = try #require(parseJSONObject(output))
        let artifacts = try #require(envelope["artifacts"] as? [[String: Any]])
        let metrics = try #require(envelope["metrics"] as? [String: Any])

        #expect(artifacts.first?["path"] as? String == sentinel)
        #expect((metrics["melix.cli.json_encode_ms"] as? Double) != nil)
        #expect(metrics["melix.cli.json_encode_ms"] as? Double != 9.999999999999e99)
    }

    @Test("pipeline dry run writes planned step receipts and a summary")
    func pipelineDryRunWritesPlannedStepReceiptsAndASummary() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("phase8.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "fake-phase8",
          "inputs": {
            "model_id": "melix-dev-text",
            "model_path": "/tmp/melix-dev-text"
          },
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "${inputs.model_path}",
                "model_id": "${inputs.model_id}",
                "model_kind": "text"
              }
            },
            {
              "id": "rescan_registry",
              "command": "model.roots.rescan",
              "args": {}
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let output = try await MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: ["MELIX_HOME": root.path]
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-pipeline-dry-run",
                    dryRun: true
                )
            )
        )
        let summary = try #require(parseJSONObject(output))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let metrics = try #require(summary["metrics"] as? [String: Any])

        #expect(summary["schema_version"] as? String == "melix.pipeline.run.v1")
        #expect(summary["name"] as? String == "fake-phase8")
        #expect(summary["trace_id"] as? String == "trace-pipeline-dry-run")
        #expect(summary["status"] as? String == "planned")
        #expect(steps.count == 2)
        #expect(steps.allSatisfy { $0["status"] as? String == "planned" })
        #expect((metrics["melix.pipeline.total_ms"] as? Double) != nil)
        #expect(metrics["melix.pipeline.resume_skipped_count"] as? Int == 0)
        #expect(metrics["melix.pipeline.failed_step_count"] as? Int == 0)

        for step in steps {
            let receiptPath = try #require(step["receipt_path"] as? String)
            #expect(FileManager.default.fileExists(atPath: receiptPath))
            let receipt = try #require(try parseJSONFile(receiptPath))
            #expect(receipt["schema_version"] as? String == "melix.cli.output.v1")
            #expect(receipt["status"] as? String == "planned")
        }

        let summaryPath = try #require(summary["summary_path"] as? String)
        #expect(FileManager.default.fileExists(atPath: summaryPath))
    }

    @Test("pipeline dry run covers default receipt roots inputs and command builder variants")
    func pipelineDryRunCoversDefaultReceiptRootsInputsAndCommandBuilderVariants() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("builder-coverage.pipeline.json")
        let inputsURL = root.appendingPathComponent("builder-coverage.inputs.json")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "builder coverage",
          "inputs": {
            "model_id": "melix-dev-text",
            "hub": {
              "repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
            },
            "metadata": {
              "suite": "smoke"
            },
            "numeric_value": 7,
            "enabled": true
          },
          "steps": [
            {
              "id": "download",
              "command": "model.hub.download",
              "args": {
                "repo_id": "${inputs.hub.repo_id}",
                "revision": true
              }
            },
            {
              "id": "rescan",
              "command": "model.roots.rescan"
            },
            {
              "id": "update_session",
              "command": "server.session.update",
              "args": {
                "server_session_id": "server-session-1",
                "title": 123,
                "model_id": "${inputs.model_id}",
                "host": true,
                "port": "8080",
                "rate_limit_per_minute": 60,
                "timeout_seconds": 30
              }
            },
            {
              "id": "select_session",
              "command": "server.session.select"
            },
            {
              "id": "start_server",
              "command": "server.start"
            },
            {
              "id": "chat",
              "command": "chat.run",
              "args": {
                "model_id": "${inputs.model_id}",
                "message": "number ${inputs.numeric_value} flag ${inputs.enabled} object ${inputs.metadata}"
              }
            },
            {
              "id": "train",
              "command": "lora.train",
              "args": {
                "model_id": "${inputs.model_id}",
                "hf_dataset_path": "org/dataset",
                "adapter_name": "adapter",
                "target_repo": "melix/adapter",
                "training_mode": "qlora",
                "rank": 8,
                "response_only": true
              }
            },
            {
              "id": "activate",
              "command": "lora.activate",
              "args": {
                "model_id": "${inputs.model_id}",
                "adapter_path": "/tmp/adapter.json",
                "alias": "derived-model",
                "activation_mode": "adapter_backed_runtime"
              }
            },
            {
              "id": "bench",
              "command": "bench.run",
              "args": {
                "repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "suite": "smoke,latency",
                "context_length": "1024,2048",
                "generation_length": "128",
                "batch_size": [1, "2"],
                "repeats": 2,
                "cache_profile": "cold",
                "reasoning_mode": "disabled",
                "structured_output_mode": "disabled",
                "sample_size": 4,
                "batch_factor": 2
              }
            },
            {
              "id": "matrix",
              "command": "bench.matrix.run",
              "args": {
                "model_id": "${inputs.model_id}",
                "task_kind": "text-generation",
                "suites": ["smoke", 7],
                "context_lengths": [1024, "2048"],
                "generation_length": "128,256",
                "batch_sizes": [1],
                "cache_profile": "cold,warm",
                "reasoning_mode": "disabled",
                "structured_output_mode": "disabled",
                "concurrency": "1,2",
                "duration_seconds": 30,
                "allow_large_matrix": 1
              }
            },
            {
              "id": "export_bench",
              "command": "bench.export-csv",
              "args": {
                "job_id": "bench-1",
                "output": "/tmp/bench.csv"
              }
            },
            {
              "id": "export_matrix_summary",
              "command": "bench.matrix.export-summary-csv",
              "args": {
                "job_id": "matrix-1",
                "output": "/tmp/matrix-summary.csv"
              }
            },
            {
              "id": "export_matrix_requests",
              "command": "bench.matrix.export-requests-csv",
              "args": {
                "job_id": "matrix-1",
                "output": "/tmp/matrix-requests.csv"
              }
            },
            {
              "id": "eval_csv",
              "command": "eval.run",
              "args": {
                "model_id": "${inputs.model_id}",
                "suite": "mmlu",
                "dataset_id": "mmlu.dev.v1",
                "sample_size": 4,
                "source_csv": "/tmp/eval.csv",
                "field_system_path": "system",
                "field_input_text_path": "input",
                "field_target_path": "target",
                "field_sample_id_path": "id",
                "profile_type": "final_result",
                "result_kind": "text",
                "extraction_mode": "heuristic_final",
                "scoring_mode": "normalized_exact_match",
                "threshold": "0.75",
                "output_schema_json": "{\"type\":\"string\"}",
                "ignored_paths": "metadata.trace,metadata.debug",
                "few_shot": 2,
                "seed": 11,
                "code_exec_policy": "sandboxed"
              }
            },
            {
              "id": "eval_jsonl",
              "command": "eval.run",
              "args": {
                "repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "source_jsonl": "/tmp/eval.jsonl"
              }
            },
            {
              "id": "eval_hf",
              "command": "eval.run",
              "args": {
                "model_id": "${inputs.model_id}",
                "hf_dataset_path": "org/eval",
                "hf_dataset_name": 123,
                "hf_dataset_revision": false,
                "hf_dataset_split": "test"
              }
            },
            {
              "id": "export_eval_summary",
              "command": "eval.export-summary-csv",
              "args": {
                "job_id": "eval-1",
                "output": "/tmp/eval-summary.csv"
              }
            },
            {
              "id": "export_eval_samples_csv",
              "command": "eval.export-samples-csv",
              "args": {
                "job_id": "eval-1",
                "output": "/tmp/eval-samples.csv"
              }
            },
            {
              "id": "export_eval_samples_jsonl",
              "command": "eval.export-samples-jsonl",
              "args": {
                "job_id": "eval-1",
                "output": "/tmp/eval-samples.jsonl"
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)
        try Data(#"{"model_id":"override-model"}"#.utf8).write(to: inputsURL)

        let output = try await MelixCLIRunner(
            client: StubControlPlaneXPCClient(),
            environment: ["MELIX_HOME": root.path]
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    inputsPath: inputsURL.path,
                    traceID: "trace-default-root",
                    dryRun: true
                )
            )
        )
        let summary = try #require(parseJSONObject(output))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let expectedReceiptDir = root
            .appendingPathComponent("pipelines")
            .appendingPathComponent("builder-coverage")
            .appendingPathComponent("trace-default-root")
            .path
        let chatStep = try #require(steps.first { $0["id"] as? String == "chat" })
        let chatReceiptPath = try #require(chatStep["receipt_path"] as? String)
        let chatReceipt = try #require(try parseJSONFile(chatReceiptPath))
        let chatResult = try #require(chatReceipt["result"] as? [String: Any])
        let chatArguments = try #require(chatResult["arguments"] as? [String])
        let trainStep = try #require(steps.first { $0["id"] as? String == "train" })
        let trainReceiptPath = try #require(trainStep["receipt_path"] as? String)
        let trainReceipt = try #require(try parseJSONFile(trainReceiptPath))
        let trainResult = try #require(trainReceipt["result"] as? [String: Any])
        let trainArguments = try #require(trainResult["arguments"] as? [String])

        #expect(summary["receipt_dir"] as? String == expectedReceiptDir)
        #expect(summary["status"] as? String == "planned")
        #expect(steps.count == 19)
        #expect(steps.allSatisfy { $0["status"] as? String == "planned" })
        #expect(chatArguments.contains("override-model"))
        #expect(chatArguments.contains(#"number 7 flag true object {"suite":"smoke"}"#))
        #expect(trainArguments.contains("--response-only"))
    }

    @Test("successful fake phase 8 pipeline writes receipts summary and artifact paths")
    func successfulFakePhase8PipelineWritesReceiptsSummaryAndArtifactPaths() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("phase8-success.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        let artifactRoot = root.appendingPathComponent("artifacts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "fake-phase8-success",
          "inputs": {
            "model_id": "melix-dev-text",
            "derived_model_alias": "melix-dev-text-derived",
            "model_path": "/tmp/melix-dev-text",
            "server_session_id": "server-session-1",
            "bench_job_id": "bench-1",
            "artifact_dir": "\#(artifactRoot.path)"
          },
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "${inputs.model_path}",
                "model_id": "${inputs.model_id}",
                "model_kind": "text"
              },
              "checks": {
                "required_result_fields": ["model_id", "managed_model_path"]
              }
            },
            {
              "id": "rescan_registry",
              "command": "model.roots.rescan",
              "args": {}
            },
            {
              "id": "update_server_session",
              "command": "server.session.update",
              "args": {
                "server_session_id": "${inputs.server_session_id}",
                "title": "Fake Phase 8",
                "model_id": "${inputs.model_id}",
                "host": "127.0.0.1",
                "port": 8080
              }
            },
            {
              "id": "start_server",
              "command": "server.start",
              "args": {
                "server_session_id": "${inputs.server_session_id}"
              }
            },
            {
              "id": "base_chat",
              "command": "chat.run",
              "args": {
                "model_id": "${inputs.model_id}",
                "server_session_id": "${inputs.server_session_id}",
                "message": "Reply with BASE_OK only."
              },
              "checks": {
                "required_result_fields": ["assistant_text", "request_id"]
              }
            },
            {
              "id": "train_lora",
              "command": "lora.train",
              "args": {
                "model_id": "${inputs.model_id}",
                "dataset_uri": "/tmp/melix-dataset.jsonl",
                "adapter_name": "fake-phase8",
                "derived_model_alias": "${inputs.derived_model_alias}"
              },
              "checks": {
                "required_result_fields": ["job_id", "output_path"]
              }
            },
            {
              "id": "activate_lora",
              "command": "lora.activate",
              "args": {
                "model_id": "${inputs.model_id}",
                "adapter_path": "${steps.train_lora.result.output_path}",
                "activation_mode": "adapter_backed_runtime",
                "derived_model_alias": "${inputs.derived_model_alias}"
              },
              "checks": {
                "required_result_fields": ["job_id"]
              }
            },
            {
              "id": "derived_chat",
              "command": "chat.run",
              "args": {
                "model_id": "${inputs.derived_model_alias}",
                "server_session_id": "${inputs.server_session_id}",
                "message": "Reply with DERIVED_OK only."
              },
              "checks": {
                "required_result_fields": ["assistant_text", "request_id"]
              }
            },
            {
              "id": "run_benchmark",
              "command": "bench.run",
              "args": {
                "model_id": "${inputs.derived_model_alias}",
                "suites": ["smoke"],
                "context_lengths": [1024],
                "generation_length": 128
              },
              "checks": {
                "required_result_fields": ["report_path", "metrics"]
              }
            },
            {
              "id": "run_benchmark_matrix",
              "command": "bench.matrix.run",
              "args": {
                "model_id": "${inputs.derived_model_alias}",
                "suites": ["smoke"],
                "context_lengths": [1024],
                "generation_lengths": [128],
                "batch_sizes": [1],
                "cache_profiles": ["cold"],
                "reasoning_modes": ["disabled"],
                "structured_output_modes": ["disabled"],
                "concurrency": [1],
                "requests": 4,
                "allow_large_matrix": true
              },
              "checks": {
                "required_result_fields": ["job.job_id"]
              }
            },
            {
              "id": "run_evaluation",
              "command": "eval.run",
              "args": {
                "model_id": "${inputs.derived_model_alias}",
                "suites": ["mmlu"],
                "dataset_id": "mmlu.dev.v1",
                "sample_size": 4
              },
              "checks": {
                "required_result_fields": ["0.job.job_id"]
              }
            },
            {
              "id": "export_benchmark_csv",
              "command": "bench.export-csv",
              "args": {
                "job_id": "${inputs.bench_job_id}",
                "output": "${inputs.artifact_dir}/benchmark.csv"
              },
              "checks": {
                "artifact_path_exists": ["${steps.export_benchmark_csv.result.output_path}"]
              }
            },
            {
              "id": "export_matrix_summary_csv",
              "command": "bench.matrix.export-summary-csv",
              "args": {
                "job_id": "${steps.run_benchmark_matrix.result.job.job_id}",
                "output": "${inputs.artifact_dir}/matrix-summary.csv"
              },
              "checks": {
                "artifact_path_exists": ["${steps.export_matrix_summary_csv.result.output_path}"]
              }
            },
            {
              "id": "export_eval_summary_csv",
              "command": "eval.export-summary-csv",
              "args": {
                "job_id": "${steps.run_evaluation.result.0.job.job_id}",
                "output": "${inputs.artifact_dir}/eval-summary.csv"
              },
              "checks": {
                "artifact_path_exists": ["${steps.export_eval_summary_csv.result.output_path}"]
              }
            },
            {
              "id": "export_eval_samples_jsonl",
              "command": "eval.export-samples-jsonl",
              "args": {
                "job_id": "${steps.run_evaluation.result.0.job.job_id}",
                "output": "${inputs.artifact_dir}/eval-samples.jsonl"
              },
              "checks": {
                "artifact_path_exists": ["${steps.export_eval_samples_jsonl.result.output_path}"]
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "melix-dev-text", kind: "text"),
            makeModelSummary(id: "melix-dev-text-derived", kind: "text"),
        ]))
        await client.setChatExecution(
            requestID: "chat-phase8",
            modelID: "melix-dev-text",
            events: [
                .tokenDelta("OK"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )
        await client.setBenchResult(
            .init(
                reportPath: "/tmp/melix/bench/bench-1/report.md",
                reportMarkdown: "# Bench\n",
                metrics: ["bench.smoke.ttft_ms": 24.45]
            )
        )
        await client.setBenchMatrixResult(
            .init(
                job: makeBenchmarkMatrixJobSummary(
                    jobID: "bench-matrix-1",
                    modelID: "melix-dev-text-derived",
                    taskKind: "text-generation",
                    sourceRepo: ""
                ),
                summaryRows: []
            )
        )
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-1",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                metricName: "eval.mmlu.accuracy",
                metricValue: 0.75
            ),
        ])
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix/train_lora/fake-phase8.adapter.json",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-text",
                  "managed_model_path": "/tmp/melix-managed/melix-dev-text",
                  "source_kind": "local_path",
                  "source_locator": "/tmp/melix-dev-text",
                  "job_id": "model-op-job-1",
                  "output_path": "/tmp/melix/train_lora/fake-phase8.adapter.json",
                  "ext": {
                    "melix.source_kind": "local_path",
                    "melix.source_locator": "/tmp/melix-dev-text"
                  }
                }
                """#
            )
        )

        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": root.path])
        )
        try await store.save(
            MelixOperatorSessionState(
                selectedServerSessionID: "server-session-1",
                serverSessions: [
                    .init(id: "server-session-1", title: "Fake Phase 8", modelID: "melix-dev-text")
                ]
            )
        )

        let output = try await MelixCLIRunner(
            client: client,
            environment: ["MELIX_HOME": root.path],
            operatorSessionStore: store
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-fake-phase8-success"
                )
            )
        )
        let summary = try #require(parseJSONObject(output))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let metrics = try #require(summary["metrics"] as? [String: Any])
        let exportStep = try #require(steps.first { $0["id"] as? String == "export_eval_samples_jsonl" })
        let artifactPaths = try #require(exportStep["artifact_paths"] as? [String])

        #expect(summary["status"] as? String == "succeeded")
        #expect(steps.count == 15)
        #expect(steps.allSatisfy { $0["status"] as? String == "succeeded" })
        #expect((metrics["melix.pipeline.step_ms.export_eval_samples_jsonl"] as? Double) != nil)
        #expect(artifactPaths == [artifactRoot.appendingPathComponent("eval-samples.jsonl").path])
        #expect(FileManager.default.fileExists(atPath: artifactRoot.appendingPathComponent("benchmark.csv").path))
        #expect(FileManager.default.fileExists(atPath: artifactRoot.appendingPathComponent("matrix-summary.csv").path))
        #expect(FileManager.default.fileExists(atPath: artifactRoot.appendingPathComponent("eval-summary.csv").path))
        #expect(FileManager.default.fileExists(atPath: artifactRoot.appendingPathComponent("eval-samples.jsonl").path))
    }

    @Test("pipeline writes an error receipt and summary when a step fails")
    func pipelineWritesErrorReceiptAndSummaryWhenAStepFails() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("failing.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "failing-pipeline",
          "inputs": {},
          "steps": [
            {
              "id": "unsupported",
              "command": "unsupported.command",
              "args": {}
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        do {
            _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                .pipelineRun(
                    .init(
                        filePath: pipelineURL.path,
                        receiptDir: receiptURL.path,
                        traceID: "trace-failing-pipeline"
                    )
                )
            )
            Issue.record("Expected unsupported pipeline command to fail.")
        } catch let error as MelixCLIError {
            #expect(error.errorDescription == "Unsupported pipeline command unsupported.command.")
        }

        let summary = try #require(try parseJSONFile(receiptURL.appendingPathComponent("run.json").path))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let errorReceiptPath = try #require(steps.first?["receipt_path"] as? String)
        let errorReceipt = try #require(try parseJSONFile(errorReceiptPath))
        let receiptError = try #require(errorReceipt["error"] as? [String: Any])

        #expect(summary["status"] as? String == "failed")
        #expect(steps.first?["status"] as? String == "failed")
        #expect(errorReceipt["schema_version"] as? String == "melix.cli.error.v1")
        #expect(receiptError["code"] as? String == "usage")
    }

    @Test("pipeline writes an error receipt and summary when a step throws a non Melix error")
    func pipelineWritesErrorReceiptAndSummaryForNonMelixStepErrors() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("generic-failing.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "generic-failing-pipeline",
          "inputs": {},
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "/tmp/melix-dev-text",
                "model_id": "melix-dev-text",
                "model_kind": "text"
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationError(NonMelixPipelineTestError(message: "transport disconnected"))
        do {
            _ = try await MelixCLIRunner(client: client).run(
                .pipelineRun(
                    .init(
                        filePath: pipelineURL.path,
                        receiptDir: receiptURL.path,
                        traceID: "trace-generic-failing-pipeline"
                    )
                )
            )
            Issue.record("Expected generic pipeline step error to fail.")
        } catch {
            #expect(String(describing: error).contains("transport disconnected"))
        }

        let summary = try #require(try parseJSONFile(receiptURL.appendingPathComponent("run.json").path))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let errorReceiptPath = try #require(steps.first?["receipt_path"] as? String)
        let errorReceipt = try #require(try parseJSONFile(errorReceiptPath))
        let receiptError = try #require(errorReceipt["error"] as? [String: Any])

        #expect(summary["status"] as? String == "failed")
        #expect(steps.first?["status"] as? String == "failed")
        #expect(errorReceipt["schema_version"] as? String == "melix.cli.error.v1")
        #expect(receiptError["code"] as? String == "runtime")
        #expect((receiptError["message"] as? String)?.contains("transport disconnected") == true)
    }

    @Test("pipeline resume skips successful receipts and rejects changed hashes")
    func pipelineResumeSkipsSuccessfulReceiptsAndRejectsChangedHashes() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("resume.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "resume-pipeline",
          "inputs": {
            "model_id": "melix-dev-text",
            "model_path": "/tmp/melix-dev-text"
          },
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "${inputs.model_path}",
                "model_id": "${inputs.model_id}",
                "model_kind": "text"
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let firstClient = StubControlPlaneXPCClient()
        await firstClient.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/melix-dev-text",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-text",
                  "ext": {
                    "melix.source_kind": "local_path",
                    "melix.source_locator": "/tmp/melix-dev-text"
                  }
                }
                """#
            )
        )
        _ = try await MelixCLIRunner(client: firstClient).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-resume-pipeline"
                )
            )
        )

        let resumeClient = StubControlPlaneXPCClient()
        let resumedOutput = try await MelixCLIRunner(client: resumeClient).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-resume-pipeline",
                    resume: true
                )
            )
        )
        let resumedSummary = try #require(parseJSONObject(resumedOutput))
        let resumedMetrics = try #require(resumedSummary["metrics"] as? [String: Any])
        let resumedSteps = try #require(resumedSummary["steps"] as? [[String: Any]])

        #expect(resumedSteps.first?["status"] as? String == "skipped")
        #expect(resumedMetrics["melix.pipeline.resume_skipped_count"] as? Double == 1)
        #expect(await resumeClient.lastModelOperationCall == nil)

        try Data(pipelineJSON.replacingOccurrences(of: "melix-dev-text", with: "melix-dev-text-v2").utf8)
            .write(to: pipelineURL)
        do {
            _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                .pipelineRun(
                    .init(
                        filePath: pipelineURL.path,
                        receiptDir: receiptURL.path,
                        traceID: "trace-resume-pipeline",
                        resume: true
                    )
                )
            )
            Issue.record("Expected resume to reject changed pipeline and input hashes.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("Pipeline resume metadata does not match the current pipeline or inputs."))
        }
    }

    @Test("pipeline from step rejects unknown targets and persists a failed summary")
    func pipelineFromStepRejectsUnknownTargetsAndPersistsAFailedSummary() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("from-step-unknown.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "from-step-unknown",
          "inputs": {},
          "steps": [
            {
              "id": "rescan_registry",
              "command": "model.roots.rescan",
              "args": {}
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-from-step-unknown",
                    dryRun: true
                )
            )
        )

        do {
            _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                .pipelineRun(
                    .init(
                        filePath: pipelineURL.path,
                        receiptDir: receiptURL.path,
                        traceID: "trace-from-step-unknown",
                        fromStepID: "missing_step",
                        dryRun: true
                    )
                )
            )
            Issue.record("Expected unknown --from-step to fail.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("--from-step missing_step does not match any pipeline step."))
        }

        let summary = try #require(try parseJSONFile(receiptURL.appendingPathComponent("run.json").path))
        let metrics = try #require(summary["metrics"] as? [String: Any])
        let error = try #require(summary["error"] as? [String: Any])

        #expect(summary["status"] as? String == "failed")
        #expect(error["code"] as? String == "runtime")
        #expect(error["message"] as? String == "--from-step missing_step does not match any pipeline step.")
        #expect(metrics["melix.pipeline.failed_step_count"] as? Double == 1)
        #expect((metrics["melix.pipeline.receipt_write_ms"] as? Double ?? 0) > 0)
    }

    @Test("pipeline from step loads prior receipts and reruns from the requested step")
    func pipelineFromStepLoadsPriorReceiptsAndRerunsFromRequestedStep() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("from-step.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "from-step",
          "inputs": {
            "model_path": "/tmp/melix-dev-text"
          },
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "${inputs.model_path}",
                "model_id": "melix-dev-text",
                "model_kind": "text"
              }
            },
            {
              "id": "chat",
              "command": "chat.run",
              "args": {
                "model_id": "${steps.materialize.result.model_id}",
                "message": "Say OK."
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let firstClient = StubControlPlaneXPCClient()
        await firstClient.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/melix-dev-text",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-text",
                  "managed_model_path": "/tmp/melix-managed/melix-dev-text"
                }
                """#
            )
        )
        await firstClient.setChatExecution(
            requestID: "chat-initial",
            modelID: "melix-dev-text",
            events: [
                .tokenDelta("OK"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )
        _ = try await MelixCLIRunner(client: firstClient).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-from-step"
                )
            )
        )
        let materializeReceiptURL = receiptURL
            .appendingPathComponent("steps")
            .appendingPathComponent("001-materialize.json")
        let materializeReceiptBefore = try Data(contentsOf: materializeReceiptURL)

        let resumeClient = StubControlPlaneXPCClient()
        await resumeClient.setChatExecution(
            requestID: "chat-rerun",
            modelID: "melix-dev-text",
            events: [
                .tokenDelta("RERUN_OK"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )
        let output = try await MelixCLIRunner(client: resumeClient).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-from-step",
                    fromStepID: "chat"
                )
            )
        )
        let summary = try #require(parseJSONObject(output))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let chatRequest = try #require(await resumeClient.lastChatRequest)
        let materializeReceiptAfter = try Data(contentsOf: materializeReceiptURL)

        #expect(steps.map { $0["status"] as? String } == ["loaded", "succeeded"])
        #expect(materializeReceiptAfter == materializeReceiptBefore)
        #expect(chatRequest.modelID == "melix-dev-text")
    }

    @Test("pipeline resume rejects stale step receipts")
    func pipelineResumeRejectsStaleStepReceipts() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("resume-stale.pipeline.json")
        let receiptURL = root.appendingPathComponent("receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "resume-stale",
          "inputs": {
            "model_id": "melix-dev-text",
            "model_path": "/tmp/melix-dev-text"
          },
          "steps": [
            {
              "id": "materialize",
              "command": "model.import",
              "args": {
                "path": "${inputs.model_path}",
                "model_id": "${inputs.model_id}",
                "model_kind": "text"
              }
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let firstClient = StubControlPlaneXPCClient()
        await firstClient.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/melix-dev-text",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-text",
                  "managed_model_path": "/tmp/melix-managed/melix-dev-text"
                }
                """#
            )
        )
        _ = try await MelixCLIRunner(client: firstClient).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-resume-stale"
                )
            )
        )

        let receiptPath = receiptURL
            .appendingPathComponent("steps")
            .appendingPathComponent("001-materialize.json")
        var receipt = try #require(try parseJSONFile(receiptPath.path))
        receipt["command_id"] = "chat.run"
        try writeJSONObjectForTest(receipt, to: receiptPath)

        do {
            _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                .pipelineRun(
                    .init(
                        filePath: pipelineURL.path,
                        receiptDir: receiptURL.path,
                        traceID: "trace-resume-stale",
                        resume: true
                    )
                )
            )
            Issue.record("Expected resume to reject a stale step receipt.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("Pipeline receipt for step materialize does not match the current command model.import."))
        }
    }

    @Test("pipeline rejects invalid schema and argument value types")
    func pipelineRejectsInvalidSchemaAndArgumentValueTypes() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let cases: [(name: String, json: String, expected: String)] = [
            (
                "inputs-array",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-inputs",
                  "inputs": [],
                  "steps": [
                    {"id": "rescan", "command": "model.roots.rescan", "args": {}}
                  ]
                }
                """#,
                "Pipeline inputs must be a JSON object."
            ),
            (
                "args-array",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-args",
                  "inputs": {},
                  "steps": [
                    {"id": "rescan", "command": "model.roots.rescan", "args": []}
                  ]
                }
                """#,
                "Pipeline step rescan args must be a JSON object."
            ),
            (
                "when-array",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-when",
                  "inputs": {},
                  "steps": [
                    {"id": "rescan", "command": "model.roots.rescan", "args": {}, "when": []}
                  ]
                }
                """#,
                "Pipeline step rescan when must be a JSON object."
            ),
            (
                "checks-array",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-checks",
                  "inputs": {},
                  "steps": [
                    {"id": "rescan", "command": "model.roots.rescan", "args": {}, "checks": []}
                  ]
                }
                """#,
                "Pipeline step rescan checks must be a JSON object."
            ),
            (
                "invalid-bool",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-bool",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "matrix",
                      "command": "bench.matrix.run",
                      "args": {
                        "allow_large_matrix": "maybe"
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument allow_large_matrix must be a boolean."
            ),
            (
                "invalid-uint-array",
                #"""
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "invalid-uint-array",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "bench",
                      "command": "bench.run",
                      "args": {
                        "context_lengths": ["not-a-number"]
                      }
                    }
                  ]
                }
                """#,
                "Pipeline command argument context_lengths must be an array of unsigned integers."
            ),
        ]

        for item in cases {
            let pipelineURL = root.appendingPathComponent("\(item.name).pipeline.json")
            let receiptURL = root.appendingPathComponent("\(item.name)-receipts")
            try Data(item.json.utf8).write(to: pipelineURL)

            do {
                _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                    .pipelineRun(
                        .init(
                            filePath: pipelineURL.path,
                            receiptDir: receiptURL.path,
                            traceID: "trace-\(item.name)",
                            dryRun: true
                        )
                    )
                )
                Issue.record("Expected invalid pipeline case \(item.name) to fail.")
            } catch let error as MelixCLIError {
                #expect(error.localizedDescription == item.expected)
            }
        }
    }

    @Test("pipeline validates skipped commands without resolving skipped arguments")
    func pipelineValidatesSkippedCommandsWithoutResolvingSkippedArguments() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let validSkippedPipelineURL = root.appendingPathComponent("valid-skipped.pipeline.json")
        try Data(
            #"""
            {
              "schema_version": "melix.pipeline.v1",
              "name": "valid-skipped",
              "inputs": {
                "mode": "local"
              },
              "steps": [
                {
                  "id": "download",
                  "command": "model.hub.download",
                  "when": {
                    "input": "mode",
                    "equals": "hub"
                  },
                  "args": {
                    "repo_id": "${inputs.repo_id}"
                  }
                }
              ]
            }
            """#.utf8
        )
        .write(to: validSkippedPipelineURL)

        let summaryText = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
            .pipelineRun(
                .init(
                    filePath: validSkippedPipelineURL.path,
                    receiptDir: root.appendingPathComponent("valid-skipped-receipts").path,
                    traceID: "trace-valid-skipped",
                    dryRun: true
                )
            )
        )
        let summary = try #require(parseJSONObject(summaryText))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        #expect(steps.first?["status"] as? String == "skipped")

        let invalidSkippedPipelineURL = root.appendingPathComponent("invalid-skipped.pipeline.json")
        try Data(
            #"""
            {
              "schema_version": "melix.pipeline.v1",
              "name": "invalid-skipped",
              "inputs": {
                "mode": "local"
              },
              "steps": [
                {
                  "id": "unsupported",
                  "command": "unsupported.command",
                  "when": {
                    "input": "mode",
                    "equals": "hub"
                  },
                  "args": {
                    "ignored": "${inputs.missing}"
                  }
                }
              ]
            }
            """#.utf8
        )
        .write(to: invalidSkippedPipelineURL)

        do {
            _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                .pipelineRun(
                    .init(
                        filePath: invalidSkippedPipelineURL.path,
                        receiptDir: root.appendingPathComponent("invalid-skipped-receipts").path,
                        traceID: "trace-invalid-skipped",
                        dryRun: true
                    )
                )
            )
            Issue.record("Expected skipped unsupported commands to be rejected.")
        } catch let error as MelixCLIError {
            #expect(error == .usage("Unsupported pipeline command unsupported.command."))
        }
    }

    @Test("pipeline when equality compares nested JSON values structurally")
    func pipelineWhenEqualityComparesNestedJSONValuesStructurally() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("nested-when.pipeline.json")
        let receiptURL = root.appendingPathComponent("nested-when-receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "nested-when",
          "inputs": {
            "gate": {
              "enabled": true,
              "labels": ["base", "derived"],
              "profile": {
                "name": "acceptance",
                "limits": [1, 2, 3]
              }
            }
          },
          "steps": [
            {
              "id": "rescan",
              "command": "model.roots.rescan",
              "when": {
                "input": "gate",
                "equals": {
                  "profile": {
                    "limits": [1, 2, 3],
                    "name": "acceptance"
                  },
                  "labels": ["base", "derived"],
                  "enabled": true
                }
              },
              "args": {}
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let summaryText = try await MelixCLIRunner(
            client: StubControlPlaneXPCClient()
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-nested-when",
                    dryRun: true
                )
            )
        )
        let summary = try #require(parseJSONObject(summaryText))
        let steps = try #require(summary["steps"] as? [[String: Any]])

        #expect(steps.first?["status"] as? String == "planned")
    }

    @Test("pipeline when equality rejects structurally different JSON values")
    func pipelineWhenEqualityRejectsStructurallyDifferentJSONValues() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let pipelineURL = root.appendingPathComponent("mismatched-when.pipeline.json")
        let receiptURL = root.appendingPathComponent("mismatched-when-receipts")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let pipelineJSON = #"""
        {
          "schema_version": "melix.pipeline.v1",
          "name": "mismatched-when",
          "inputs": {
            "null_gate": null,
            "array_gate": ["base"],
            "object_gate": {"name": "acceptance", "limit": 1},
            "bool_gate": true,
            "mixed_gate": ["base"]
          },
          "steps": [
            {
              "id": "null_match",
              "command": "model.roots.rescan",
              "when": {"input": "null_gate", "equals": null},
              "args": {}
            },
            {
              "id": "array_mismatch",
              "command": "model.roots.rescan",
              "when": {"input": "array_gate", "equals": ["base", "derived"]},
              "args": {}
            },
            {
              "id": "object_count_mismatch",
              "command": "model.roots.rescan",
              "when": {"input": "object_gate", "equals": {"name": "acceptance"}},
              "args": {}
            },
            {
              "id": "object_value_mismatch",
              "command": "model.roots.rescan",
              "when": {"input": "object_gate", "equals": {"name": "acceptance", "limit": 2}},
              "args": {}
            },
            {
              "id": "bool_type_mismatch",
              "command": "model.roots.rescan",
              "when": {"input": "bool_gate", "equals": "true"},
              "args": {}
            },
            {
              "id": "mixed_type_mismatch",
              "command": "model.roots.rescan",
              "when": {"input": "mixed_gate", "equals": {"0": "base"}},
              "args": {}
            }
          ]
        }
        """#
        try Data(pipelineJSON.utf8).write(to: pipelineURL)

        let summaryText = try await MelixCLIRunner(
            client: StubControlPlaneXPCClient()
        ).run(
            .pipelineRun(
                .init(
                    filePath: pipelineURL.path,
                    receiptDir: receiptURL.path,
                    traceID: "trace-mismatched-when",
                    dryRun: true
                )
            )
        )
        let summary = try #require(parseJSONObject(summaryText))
        let steps = try #require(summary["steps"] as? [[String: Any]])
        let statuses = Dictionary(uniqueKeysWithValues: steps.compactMap { step -> (String, String)? in
            guard let id = step["id"] as? String,
                  let status = step["status"] as? String
            else {
                return nil
            }
            return (id, status)
        })

        #expect(statuses["null_match"] == "planned")
        #expect(statuses["array_mismatch"] == "skipped")
        #expect(statuses["object_count_mismatch"] == "skipped")
        #expect(statuses["object_value_mismatch"] == "skipped")
        #expect(statuses["bool_type_mismatch"] == "skipped")
        #expect(statuses["mixed_type_mismatch"] == "skipped")
    }

    @Test("pipeline rejects invalid check field types")
    func pipelineRejectsInvalidCheckFieldTypes() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let cases: [(name: String, checks: String, expected: String)] = [
            (
                "required-fields-string",
                #""required_result_fields": "model_id""#,
                "Pipeline step import checks.required_result_fields must be an array of strings."
            ),
            (
                "equals-array",
                #""equals": []"#,
                "Pipeline step import checks.equals must be a JSON object."
            ),
            (
                "artifact-path-number",
                #""artifact_path_exists": [1]"#,
                "Pipeline step import checks.artifact_path_exists must be an array of strings."
            ),
        ]

        for item in cases {
            let pipelineURL = root.appendingPathComponent("\(item.name).pipeline.json")
            try Data(
                """
                {
                  "schema_version": "melix.pipeline.v1",
                  "name": "\(item.name)",
                  "inputs": {},
                  "steps": [
                    {
                      "id": "import",
                      "command": "model.import",
                      "args": {
                        "path": "/tmp/model",
                        "model_id": "melix-dev-text"
                      },
                      "checks": {
                        \(item.checks)
                      }
                    }
                  ]
                }
                """.utf8
            )
            .write(to: pipelineURL)

            do {
                _ = try await MelixCLIRunner(client: StubControlPlaneXPCClient()).run(
                    .pipelineRun(
                        .init(
                            filePath: pipelineURL.path,
                            receiptDir: root.appendingPathComponent("\(item.name)-receipts").path,
                            traceID: "trace-\(item.name)",
                            dryRun: true
                        )
                    )
                )
                Issue.record("Expected invalid check case \(item.name) to fail.")
            } catch let error as MelixCLIError {
                #expect(error.localizedDescription == item.expected)
            }
        }
    }

    @Test("public model ops commands forward convert quantize and upload payloads")
    func publicModelOpsCommandsForwardConvertQuantizeAndUploadPayloads() async throws {
        let client = StubControlPlaneXPCClient()
        let runner = MelixCLIRunner(client: client)

        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-convert/convert.artifact",
                manifestJSON: #"{"job_id":"convert-job-1","operation":"convert","target_format":"melix_model_bundle"}"#
            )
        )
        let convertOutput = try await runner.run(
            .convert(
                .init(
                    modelID: "melix-dev-text",
                    outputDir: "/tmp/melix-convert",
                    targetFormat: "melix_model_bundle",
                    json: true
                )
            )
        )
        let convertCall = try #require(await client.lastModelOperationCall)
        let convertPayload = try #require(parseJSONObject(convertOutput))

        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-quantize/quantize.artifact",
                manifestJSON: #"{"job_id":"quantize-job-1","operation":"quantize","quant_profile_id":"q4"}"#
            )
        )
        let quantizeOutput = try await runner.run(
            .quantize(
                .init(
                    modelID: "melix-dev-text",
                    outputDir: "/tmp/melix-quantize",
                    quantProfileID: "q4",
                    weightQuant: "q4",
                    kvQuant: "q8",
                    json: true
                )
            )
        )
        let quantizeCall = try #require(await client.lastModelOperationCall)
        let quantizePayload = try #require(parseJSONObject(quantizeOutput))

        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-upload/upload.receipt.json",
                manifestJSON: #"{"job_id":"upload-job-1","operation":"upload","target_repo":"melix/models/demo"}"#
            )
        )
        let uploadOutput = try await runner.run(
            .upload(
                .init(
                    modelID: "melix-dev-text",
                    outputDir: "/tmp/melix-upload",
                    targetRepo: "melix/models/demo",
                    artifactPath: "/tmp/melix-convert/convert.artifact",
                    artifactKind: "converted_model_bundle",
                    artifactManifestPath: "/tmp/melix-convert/convert.artifact/manifest.json",
                    json: true
                )
            )
        )
        let uploadCall = try #require(await client.lastModelOperationCall)
        let uploadPayload = try #require(parseJSONObject(uploadOutput))

        #expect(convertPayload["job_id"] as? String == "convert-job-1")
        #expect(convertCall.operation == "convert")
        #expect(convertCall.outputDir == "/tmp/melix-convert")
        #expect(convertCall.ext["target_format"] == "melix_model_bundle")
        #expect(quantizePayload["job_id"] as? String == "quantize-job-1")
        #expect(quantizeCall.operation == "quantize")
        #expect(quantizeCall.outputDir == "/tmp/melix-quantize")
        #expect(quantizeCall.quantProfileID == "q4")
        #expect(quantizeCall.weightQuant == "q4")
        #expect(quantizeCall.kvQuant == "q8")
        #expect(uploadPayload["job_id"] as? String == "upload-job-1")
        #expect(uploadCall.operation == "upload")
        #expect(uploadCall.outputDir == "/tmp/melix-upload")
        #expect(uploadCall.ext["target_repo"] == "melix/models/demo")
        #expect(uploadCall.ext["artifact_path"] == "/tmp/melix-convert/convert.artifact")
        #expect(uploadCall.ext["artifact_kind"] == "converted_model_bundle")
        #expect(uploadCall.ext["artifact_manifest_path"] == "/tmp/melix-convert/convert.artifact/manifest.json")
    }

    @Test("model hub download json renders a managed model receipt")
    func modelHubDownloadJSONRendersAManagedModelReceipt() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main",
                manifestJSON: #"""
                {
                  "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                  "ext": {
                    "melix.source_kind": "hub_repo",
                    "melix.source_locator": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
                  }
                }
                """#
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .modelHubDownload(.init(repoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", revision: "main", json: true))
        )
        let payload = try #require(parseJSONObject(output))

        #expect(payload["model_id"] as? String == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(
            payload["managed_model_path"] as? String ==
                "/tmp/melix-managed/huggingface/mlx-community/Qwen3.5-0.8B-OptiQ-4bit/main"
        )
        #expect(payload["source_kind"] as? String == "hub_repo")
        #expect(payload["source_locator"] as? String == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
    }

    @Test("model import forwards a local import operation and renders a managed model receipt")
    func modelImportForwardsALocalImportOperationAndRendersAManagedModelReceipt() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/local/melix-dev-qwen-local/main",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-qwen-local",
                  "ext": {
                    "melix.source_kind": "local_path",
                    "melix.source_locator": "/tmp/qwen-local-model"
                  }
                }
                """#
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .modelImport(
                .init(
                    path: "/tmp/qwen-local-model",
                    modelID: "melix-dev-qwen-local",
                    modelKind: "text",
                    revision: "main",
                    json: true
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)
        let payload = try #require(parseJSONObject(output))

        #expect(call.modelID == "melix-dev-qwen-local")
        #expect(call.operation == "local_import")
        #expect(call.ext["source_path"] == "/tmp/qwen-local-model")
        #expect(call.ext["melix.source_kind"] == "local_path")
        #expect(call.ext["melix.model_kind"] == "text")
        #expect(call.ext["melix.revision"] == "main")
        #expect(payload["model_id"] as? String == "melix-dev-qwen-local")
        #expect(payload["managed_model_path"] as? String == "/tmp/melix-managed/local/melix-dev-qwen-local/main")
        #expect(payload["source_kind"] as? String == "local_path")
        #expect(payload["source_locator"] as? String == "/tmp/qwen-local-model")
    }

    @Test("chat run collects streamed assistant text and returns a typed json receipt")
    func chatRunCollectsStreamedAssistantTextAndReturnsATypedJSONReceipt() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setChatExecution(
            requestID: "chat-run-1",
            modelID: "melix-dev-qwen-local",
            events: [
                .tokenDelta("Echo: "),
                .tokenDelta("Reply with BASE_OK"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )

        let output = try await MelixCLIRunner(client: client).run(
            .chatRun(
                .init(
                    modelID: "melix-dev-qwen-local",
                    message: "Reply with BASE_OK",
                    systemPrompt: "Be terse.",
                    serverSessionID: "server-session-1",
                    json: true
                )
            )
        )
        let request = try #require(await client.lastChatRequest)
        let payload = try #require(parseJSONObject(output))

        #expect(
            request ==
                ControlPlaneChatRequest(
                    modelID: "melix-dev-qwen-local",
                    messages: [
                        .init(role: "system", content: "Be terse."),
                        .init(role: "user", content: "Reply with BASE_OK"),
                    ]
                )
        )
        #expect(payload["model_id"] as? String == "melix-dev-qwen-local")
        #expect(payload["server_session_id"] as? String == "server-session-1")
        #expect(payload["assistant_text"] as? String == "Echo: Reply with BASE_OK")
        #expect(payload["finish_reason"] as? String == "stop")
        #expect(payload["request_id"] as? String == "chat-run-1")
    }

    @Test("chat run surfaces stream failures as runtime errors")
    func chatRunSurfacesStreamFailuresAsRuntimeErrors() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setChatExecution(
            requestID: "chat-run-failed",
            modelID: "melix-dev-qwen-local",
            events: [
                .failed(code: "unavailable", message: "server session is not ready"),
            ]
        )

        await #expect(throws: MelixCLIError.runtime("melix chat run failed [unavailable]: server session is not ready")) {
            try await MelixCLIRunner(client: client).run(
                .chatRun(
                    .init(
                        modelID: "melix-dev-qwen-local",
                        message: "Reply with BASE_OK",
                        systemPrompt: "",
                        serverSessionID: "server-session-1",
                        json: true
                    )
                )
            )
        }
    }

    @Test("chat run returns plain text output when json is disabled")
    func chatRunReturnsPlainTextOutputWhenJSONIsDisabled() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setChatExecution(
            requestID: "chat-run-plain",
            modelID: "melix-dev-qwen-local",
            events: [
                .tokenDelta("Echo: Reply with BASE_OK"),
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )

        let output = try await MelixCLIRunner(client: client).run(
            .chatRun(
                .init(
                    modelID: "melix-dev-qwen-local",
                    message: "Reply with BASE_OK",
                    systemPrompt: "",
                    serverSessionID: "server-session-1",
                    json: false
                )
            )
        )

        #expect(output == "Echo: Reply with BASE_OK\n")
    }

    @Test("chat run tolerates non-terminal events and falls back to streamed text when completion is omitted")
    func chatRunFallsBackToStreamedTextWhenCompletionIsOmitted() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setChatExecution(
            requestID: "chat-run-fallback",
            modelID: "melix-dev-qwen-local",
            events: [
                .heartbeat,
                .tokenDelta("Echo: Reply with BASE_OK"),
            ]
        )

        let output = try await MelixCLIRunner(client: client).run(
            .chatRun(
                .init(
                    modelID: "melix-dev-qwen-local",
                    message: "Reply with BASE_OK",
                    systemPrompt: "",
                    serverSessionID: "server-session-1",
                    json: false
                )
            )
        )

        #expect(output == "Echo: Reply with BASE_OK\n")
    }

    @Test("chat run rejects completed streams without any assistant text")
    func chatRunRejectsCompletedStreamsWithoutAnyAssistantText() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setChatExecution(
            requestID: "chat-run-empty",
            modelID: "melix-dev-qwen-local",
            events: [
                .completed(finishReason: "stop", assistantText: "", reasoningText: ""),
            ]
        )

        await #expect(throws: MelixCLIError.runtime("melix chat run did not produce assistant text.")) {
            try await MelixCLIRunner(client: client).run(
                .chatRun(
                    .init(
                        modelID: "melix-dev-qwen-local",
                        message: "Reply with BASE_OK",
                        systemPrompt: "",
                        serverSessionID: "server-session-1",
                        json: true
                    )
                )
            )
        }
    }

    @Test("model import forwards the managed root override when configured")
    func modelImportForwardsTheManagedRootOverrideWhenConfigured() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/local/melix-dev-qwen-local/main",
                manifestJSON: #"""
                {
                  "model_id": "melix-dev-qwen-local",
                  "ext": {
                    "melix.source_kind": "local_path",
                    "melix.source_locator": "/tmp/qwen-local-model"
                  }
                }
                """#
            )
        )

        _ = try await MelixCLIRunner(
            client: client,
            environment: ["MELIX_MANAGED_MODEL_ROOT": "/tmp/melix-managed"]
        ).run(
            .modelImport(
                .init(
                    path: "/tmp/qwen-local-model",
                    modelID: "melix-dev-qwen-local",
                    modelKind: "text",
                    revision: "main"
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.ext["melix.managed_root"] == "/tmp/melix-managed")
    }

    @Test("model import json rejects a malformed managed model manifest")
    func modelImportJSONRejectsAMalformedManagedModelManifest() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/local/melix-dev-qwen-local/main",
                manifestJSON: "not-json"
            )
        )

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .modelImport(
                    .init(
                        path: "/tmp/qwen-local-model",
                        modelID: "melix-dev-qwen-local",
                        modelKind: "text",
                        revision: "main",
                        json: true
                    )
                )
            )
            Issue.record("Expected model import json to reject malformed managed model manifests.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("Managed model operations must return a JSON manifest."))
        }
    }

    @Test("model import json falls back to source model and source path fields")
    func modelImportJSONFallsBackToSourceModelAndSourcePathFields() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/local/melix-dev-qwen-local/main",
                manifestJSON: #"""
                {
                  "source_model": "melix-dev-qwen-local",
                  "source_path": "/tmp/qwen-local-model"
                }
                """#
            )
        )

        let output = try await MelixCLIRunner(client: client).run(
            .modelImport(
                .init(
                    path: "/tmp/qwen-local-model",
                    modelID: "melix-dev-qwen-local",
                    modelKind: "text",
                    revision: "main",
                    json: true
                )
            )
        )
        let payload = try #require(parseJSONObject(output))

        #expect(payload["model_id"] as? String == "melix-dev-qwen-local")
        #expect(payload["managed_model_path"] as? String == "/tmp/melix-managed/local/melix-dev-qwen-local/main")
        #expect(payload["source_kind"] as? String == "")
        #expect(payload["source_locator"] as? String == "/tmp/qwen-local-model")
    }

    @Test("model import json requires a model identifier in the managed manifest")
    func modelImportJSONRequiresAModelIdentifierInTheManagedManifest() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-managed/local/melix-dev-qwen-local/main",
                manifestJSON: #"{"warnings":["manifest missing model id"]}"#
            )
        )

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .modelImport(
                    .init(
                        path: "/tmp/qwen-local-model",
                        modelID: "melix-dev-qwen-local",
                        modelKind: "text",
                        revision: "main",
                        json: true
                    )
                )
            )
            Issue.record("Expected model import json to require a model identifier in the managed manifest.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("Managed model manifest did not include a model identifier and output path."))
        }
    }

    @Test("model roots rescan omits an empty registry-root override")
    func modelRootsRescanOmitsEmptyRegistryRootOverride() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(manifestJSON: #"{"model_registry":{"models":[],"roots":[]}}"#))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )

        _ = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .modelRootsRescan(.init())
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.operation == "registry_snapshot")
        #expect(call.ext["melix.registry_rescan"] == "true")
        #expect(call.ext["melix.registry_roots_json"] == nil)
    }

    @Test("model list surfaces runtime_mode as a first-class column in JSON and text output")
    func modelListSurfacesRuntimeModeColumn() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"model_registry":{"models":[],"roots":[]}}"#
        ))
        // Seed a mix of base, fused, and adapter-backed models to prove the
        // list renderer distinguishes all three via the runtime_mode column.
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "melix-base-text", kind: "text"),
            makeModelSummary(
                id: "melix-base-text-lora-fused",
                kind: "text",
                runtimeMode: "fused_derived_model",
                activationMode: "fused_derived_model"
            ),
            makeModelSummary(
                id: "melix-base-text-lora-runtime",
                kind: "text",
                runtimeMode: "adapter_backed_runtime",
                activationMode: "adapter_backed_runtime"
            ),
        ]))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        try store.save(
            MelixOperatorSessionState(
                selectedServerSessionID: "",
                serverSessions: [],
                registryRoots: []
            )
        )

        // JSON output: every entry carries runtime_mode, and adapter-backed
        // entries additionally echo activation_mode for backward compat.
        let jsonOutput = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .modelList(.init(json: true))
        )
        let jsonData = try #require(jsonOutput.data(using: .utf8))
        let entries = try #require(try JSONSerialization.jsonObject(with: jsonData) as? [[String: Any]])
        let byID = Dictionary(uniqueKeysWithValues: entries.compactMap { entry -> (String, [String: Any])? in
            guard let id = entry["model_id"] as? String else { return nil }
            return (id, entry)
        })
        #expect(byID["melix-base-text"]?["runtime_mode"] as? String == "")
        #expect(byID["melix-base-text-lora-fused"]?["runtime_mode"] as? String == "fused_derived_model")
        #expect(byID["melix-base-text-lora-runtime"]?["runtime_mode"] as? String == "adapter_backed_runtime")
        #expect(byID["melix-base-text-lora-runtime"]?["activation_mode"] as? String == "adapter_backed_runtime")
        // Base models have no activation_mode in settings.ext so the field
        // is omitted from the payload rather than blank-strung.
        #expect(byID["melix-base-text"]?["activation_mode"] == nil)

        // Text output: fixed-width table with header row and short-form
        // runtime tags. Header column names are upper-case for legibility;
        // columns are padded to max width with two-space separators.
        let textOutput = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .modelList(.init(json: false))
        )
        let lines = textOutput.split(separator: "\n").map(String.init)
        let header = try #require(lines.first)
        // Header exposes all four columns in padded fixed-width order.
        #expect(header.contains("MODEL_ID"))
        #expect(header.contains("KIND"))
        #expect(header.contains("STATE"))
        #expect(header.contains("RUNTIME"))
        // Each short-form runtime tag appears exactly once on a data row.
        // Use ``hasPrefix`` on the model_id + trailing space to unambiguously
        // pick each row even if another id were a superstring.
        let dataRows = lines.dropFirst()
        let baseRow = try #require(
            dataRows.first(where: { $0.hasPrefix("melix-base-text ") && $0.hasSuffix("-") })
        )
        let fusedRow = try #require(
            dataRows.first(where: { $0.hasPrefix("melix-base-text-lora-fused ") && $0.hasSuffix("fused") })
        )
        let adapterRow = try #require(
            dataRows.first(where: { $0.hasPrefix("melix-base-text-lora-runtime") && $0.hasSuffix("adapter") })
        )
        // The first column is padded to the widest model_id
        // ("melix-base-text-lora-runtime" = 28 chars); assert the "KIND"
        // column actually starts at the column-separator offset. A
        // regression that dropped padding would collapse the gap.
        let firstColumnWidth = "melix-base-text-lora-runtime".count
        let separator = "  "
        let kindColumnOffset = firstColumnWidth + separator.count
        for row in [baseRow, fusedRow, adapterRow] {
            let indexAtKindStart = row.index(row.startIndex, offsetBy: kindColumnOffset)
            let kindPrefix = row[indexAtKindStart...].prefix(4)
            #expect(kindPrefix == "text", "row not padded at column offset: \(row)")
        }
    }

    @Test("model list primes configured registry roots before fetching the server snapshot")
    func modelListPrimesConfiguredRegistryRootsBeforeFetchingServerSnapshot() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"model_registry":{"models":[],"roots":[]}}"#
        ))
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", kind: "text"),
        ]))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        try store.save(
            MelixOperatorSessionState(
                selectedServerSessionID: "",
                serverSessions: [],
                registryRoots: ["/tmp/model-root-a"]
            )
        )

        let output = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .modelList(.init(json: true))
        )
        let call = try #require(await client.lastModelOperationCall)
        let outputData = try #require(output.data(using: .utf8))
        let models = try #require(try JSONSerialization.jsonObject(with: outputData) as? [[String: Any]])
        let firstModel = try #require(models.first)
        let rootsJSON = try #require(call.ext["melix.registry_roots_json"])
        let rootsData = try #require(rootsJSON.data(using: .utf8))
        let roots = try #require(try JSONSerialization.jsonObject(with: rootsData) as? [String])

        #expect(call.operation == "registry_snapshot")
        #expect(call.ext["melix.registry_rescan"] == "true")
        #expect(roots == ["/tmp/model-root-a"])
        #expect(firstModel["model_id"] as? String == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
    }

    @Test("model inspect primes registry snapshot even without configured roots")
    func modelInspectPrimesRegistrySnapshotWithoutConfiguredRoots() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let importedModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"model_registry":{"models":[],"roots":[]}}"#
        ))
        await client.setModelInfo(
            modelID: importedModelID,
            info: {
                var info = Melix_Controlplane_V1_ModelInfo()
                info.ok = true
                info.modelKind = "text"
                info.supportedModalities = ["text"]
                info.supportedTasks = ["generate"]
                return info
            }()
        )
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )

        _ = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .modelInspect(.init(modelID: importedModelID, json: true))
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.modelID == "melix-dev-text")
        #expect(call.operation == "registry_snapshot")
        #expect(call.ext["melix.registry_rescan"] == "true")
        #expect(call.ext["melix.registry_roots_json"] == nil)
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

    @Test("server session commands persist shared operator state and start validates serveable bindings")
    func serverSessionCommandsPersistSharedOperatorStateAndStartValidatesServeableBindings() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "melix-dev-image", kind: "image"),
            makeModelSummary(id: "melix-dev-vlm", kind: "vlm"),
        ]))
        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        let runner = MelixCLIRunner(client: client, operatorSessionStore: store)

        _ = try await runner.run(
            .serverSessionCreate(
                .init(
                    title: "Vision Session",
                    modelID: "melix-dev-vlm",
                    host: "127.0.0.1",
                    port: 12434
                )
            )
        )
        _ = try await runner.run(
            .serverSessionSelect(.init(serverSessionID: "server-session-1"))
        )
        let listOutput = try await runner.run(.serverSessionList(.init(json: true)))

        let payload = try #require(parseJSONObject(listOutput))
        let selectedServerSessionID = try #require(payload["selected_server_session_id"] as? String)
        let sessions = try #require(payload["server_sessions"] as? [[String: Any]])

        #expect(selectedServerSessionID == "server-session-1")
        #expect(sessions.count == 1)
        #expect(sessions.first?["model_id"] as? String == "melix-dev-vlm")

        _ = try await runner.run(
            .serverStart(.init(serverSessionID: "server-session-1"))
        )

        let gatewayConfigCall = try #require(await client.lastGatewayConfigApplyRequest)
        let servingDefaultsCall = try #require(await client.lastServingDefaultsApplyRequest)

        #expect(gatewayConfigCall.serverSessionID == "server-session-1")
        #expect(gatewayConfigCall.servedModelID == "melix-dev-vlm")
        #expect(servingDefaultsCall.serverSessionID == "server-session-1")

        try await store.save(
            MelixOperatorSessionState(
                selectedSurfaceID: "server",
                selectedToolSectionID: "modelsLibrary",
                selectedServerSessionID: "server-session-1",
                serverSessions: [
                    .init(
                        id: "server-session-1",
                        title: "Broken Session",
                        modelID: "melix-dev-ocr"
                    )
                ]
            )
        )
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: "melix-dev-ocr", kind: "ocr"),
        ]))

        await #expect(throws: MelixCLIError.self) {
            _ = try await runner.run(.serverStart(.init(serverSessionID: "server-session-1")))
        }
    }

    @Test("server start falls back to model info when the snapshot omits an imported model")
    func serverStartFallsBackToModelInfoWhenSnapshotOmitsImportedModel() async throws {
        let temporaryRoot = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-cli-runner-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer {
            try? FileManager.default.removeItem(at: temporaryRoot)
        }

        let importedModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: []))
        await client.setModelInfo(
            modelID: importedModelID,
            info: {
                var info = Melix_Controlplane_V1_ModelInfo()
                info.ok = true
                info.modelKind = "text"
                info.supportedModalities = ["text"]
                info.supportedTasks = ["generate", "chat"]
                return info
            }()
        )

        let store = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        try await store.save(
            MelixOperatorSessionState(
                selectedSurfaceID: "server",
                selectedToolSectionID: "modelsLibrary",
                selectedServerSessionID: "server-session-1",
                serverSessions: [
                    .init(
                        id: "server-session-1",
                        title: "Imported Session",
                        modelID: importedModelID
                    )
                ]
            )
        )

        _ = try await MelixCLIRunner(client: client, operatorSessionStore: store).run(
            .serverStart(.init(serverSessionID: "server-session-1"))
        )

        let gatewayConfigCall = try #require(await client.lastGatewayConfigApplyRequest)
        let startedAction = try #require(await client.lastServerAction)

        #expect(gatewayConfigCall.servedModelID == importedModelID)
        #expect(startedAction == .start("server-session-1"))
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
            makeModelSummary(id: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", kind: "text"),
        ]))
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"adapters":[{"adapter_name":"demo-adapter","status":"activated","source_model":"mlx-community/Qwen3.5-0.8B-OptiQ-4bit","activation_mode":"adapter_backed_runtime","derived_model_id":"melix-qwen35-runtime"}],"derived_models":[{"model_id":"melix-qwen35-runtime","derived_model_alias":"Runtime Alias","activation_mode":"adapter_backed_runtime","activation_backend":"internal","source_model":"mlx-community/Qwen3.5-0.8B-OptiQ-4bit"}],"experiment_groups":[{"group_id":"nightly-qwen35","run_count":2,"latest_preset_title":"Balanced Adapter","best_loss":0.33,"recommended_manifest_path":"/tmp/melix/train_lora/job-2/train_lora.adapter.json"}]}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(.loraList(.init()))
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.operation == "registry_snapshot")
        #expect(output.contains("adapter\tstatus\tsource_model\tactivation_mode\tderived_model_id"))
        #expect(output.contains("demo-adapter\tactivated\tmlx-community/Qwen3.5-0.8B-OptiQ-4bit\tadapter_backed_runtime\tmelix-qwen35-runtime"))
        #expect(output.contains("derived_model_id\talias\tactivation_mode\tactivation_backend\tsource_model"))
        #expect(output.contains("melix-qwen35-runtime\tRuntime Alias\tadapter_backed_runtime\tinternal\tmlx-community/Qwen3.5-0.8B-OptiQ-4bit"))
        #expect(output.contains("experiment_group\truns\tpreset\tbest_loss\trecommended_manifest"))
        #expect(output.contains("nightly-qwen35\t2\tBalanced Adapter\t0.330\t/tmp/melix/train_lora/job-2/train_lora.adapter.json"))
    }

    @Test("lora list returns json when requested and honors an explicit preferred model id")
    func loraListReturnsJSONWhenRequested() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: #"{"adapters":[{"adapter_name":"demo-adapter"}]}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraList(.init(modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", json: true))
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        let payload = try #require(parseJSONObject(output))
        let adapters = try #require(payload["adapters"] as? [[String: Any]])
        #expect(adapters.count == 1)
        #expect(adapters.first?["adapter_name"] as? String == "demo-adapter")
        #expect(payload["experiment_groups"] as? [Any] != nil)
        #expect(payload["jobs"] == nil)
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

        #expect(output == "No adapters or derived models found.\n")
    }

    @Test("lora experiments list renders a fixed-width table")
    func loraExperimentsListRendersFixedWidthTable() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makeExperimentsRegistryManifest()
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraExperimentsList(.init(modelID: "melix-dev-text"))
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.operation == "registry_snapshot")
        #expect(output.contains("GROUP_ID"))
        #expect(output.contains("TITLE"))
        #expect(output.contains("RUNS"))
        #expect(output.contains("BEST_LOSS"))
        #expect(output.contains("RESUME_READY"))
        #expect(output.contains("nightly-qwen35"))
        #expect(output.contains("Nightly Qwen35"))
        #expect(output.contains("2 of 3"))
    }

    @Test("lora experiments list emits JSON when requested")
    func loraExperimentsListEmitsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makeExperimentsRegistryManifest()
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraExperimentsList(.init(modelID: "melix-dev-text", json: true))
        )

        let payload = try #require(parseJSONObject(output))
        let groups = try #require(payload["experiment_groups"] as? [[String: Any]])
        #expect(groups.count == 1)
        #expect(groups.first?["group_id"] as? String == "nightly-qwen35")
    }

    @Test("lora experiments show renders detail for a known group")
    func loraExperimentsShowRendersDetail() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makeExperimentsRegistryManifest()
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraExperimentsShow(.init(modelID: "melix-dev-text", groupID: "nightly-qwen35"))
        )

        #expect(output.contains("Group: nightly-qwen35"))
        #expect(output.contains("Title: Nightly Qwen35"))
        #expect(output.contains("Runs (3):"))
        #expect(output.contains("RUN_ID"))
        #expect(output.contains("CHECKPOINTS"))
        #expect(output.contains("RESUME_READY"))
        #expect(output.contains("model-ops-0012"))
        #expect(output.contains("Best known adapter:"))
        #expect(output.contains("Manifest: /tmp/melix-train-lora/model-ops-0012/train_lora.adapter.json"))
        #expect(output.contains("Resume via: melix lora resume --group-id nightly-qwen35"))
        #expect(output.contains("\t") == false)
    }

    @Test("lora experiments list renders n/a when best loss is missing")
    func loraExperimentsListRendersNotAvailableBestLoss() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makeExperimentsRegistryManifestWithoutBestLoss()
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraExperimentsList(.init(modelID: "melix-dev-text"))
        )

        #expect(output.contains("n/a"))
        #expect(output.contains("0.0000") == false)
    }

    @Test("lora experiments list surfaces a runtime error when snapshot JSON is malformed")
    func loraExperimentsListErrorsOnMalformedSnapshot() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(manifestJSON: "not-json-at-all"))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraExperimentsList(.init(modelID: "melix-dev-text"))
            )
            Issue.record("Expected experiments list to throw for malformed JSON")
        } catch let error as MelixCLIError {
            if case .runtime(let message) = error {
                #expect(message.contains("registry_snapshot payload"))
            } else {
                Issue.record("Expected runtime error, got \(error)")
            }
        }
    }

    @Test("lora resume inherits hf dataset fields from the manifest when dataset_uri is absent")
    func loraResumeInheritsHFDatasetFields() async throws {
        let client = StubControlPlaneXPCClient()
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-lora-resume-hf-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let manifestURL = tempDir.appendingPathComponent("train_lora.adapter.json")
        try writeJSONObjectForTest(
            [
                "adapter_name": "nightly-qwen35",
                "dataset_source_kind": "hf_dataset",
                "hf_dataset_path": "HuggingFaceH4/ultrachat_200k",
                "hf_dataset_name": "default",
                "hf_train_split": "train_sft",
                "preset_id": "balanced_adapter",
            ],
            to: manifestURL
        )

        await client.setModelOperationResult(
            makeModelOperationResult(manifestJSON: makeExperimentsRegistryManifest(bestManifestPath: manifestURL.path)),
            forOperation: "registry_snapshot"
        )
        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/resume-hf.adapter.json"),
            forOperation: "train_lora"
        )

        _ = try await MelixCLIRunner(client: client).run(
            .loraResume(.init(modelID: "melix-dev-text", groupID: "nightly-qwen35"))
        )

        let calls = await client.modelOperationCalls.filter { $0.ext["melix.registry_rescan"] != "true" }
        let trainCall = try #require(calls.last)
        #expect(trainCall.operation == "train_lora")
        #expect(trainCall.ext["dataset_source_kind"] == "hf_dataset")
        #expect(trainCall.ext["dataset_uri"] == "HuggingFaceH4/ultrachat_200k")
        #expect(trainCall.ext["hf_dataset_path"] == "HuggingFaceH4/ultrachat_200k")
        #expect(trainCall.ext["hf_dataset_name"] == "default")
        #expect(trainCall.ext["hf_train_split"] == "train_sft")
    }

    @Test("lora experiments show errors for an unknown group and lists known ids")
    func loraExperimentsShowErrorsForUnknownGroup() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            manifestJSON: makeExperimentsRegistryManifest()
        ))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraExperimentsShow(.init(modelID: "melix-dev-text", groupID: "missing"))
            )
            Issue.record("Expected experiments show to throw for an unknown group")
        } catch let error as MelixCLIError {
            if case .missingRequired(let message) = error {
                #expect(message.contains("missing"))
                #expect(message.contains("nightly-qwen35"))
            } else {
                Issue.record("Expected missingRequired error, got \(error)")
            }
        }
    }

    @Test("lora resume resolves the best adapter manifest and invokes train_lora")
    func loraResumeResolvesBestAdapterAndTrains() async throws {
        let client = StubControlPlaneXPCClient()
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-lora-resume-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let manifestURL = tempDir.appendingPathComponent("train_lora.adapter.json")
        try writeJSONObjectForTest(
            [
                "adapter_name": "nightly-qwen35",
                "dataset_uri": "/tmp/datasets/nightly.jsonl",
                "preset_id": "balanced_adapter",
                "experiment_group_id": "nightly-qwen35",
                "experiment_group_title": "Nightly Qwen35",
            ],
            to: manifestURL
        )

        await client.setModelOperationResult(
            makeModelOperationResult(manifestJSON: makeExperimentsRegistryManifest(bestManifestPath: manifestURL.path)),
            forOperation: "registry_snapshot"
        )
        await client.setModelOperationResult(
            makeModelOperationResult(
                outputPath: "/tmp/melix-train-lora/resume-out/train_lora.adapter.json",
                manifestJSON: #"{"operation":"train_lora","resume_manifest_path":"\#(manifestURL.path)"}"#
            ),
            forOperation: "train_lora"
        )

        let output = try await MelixCLIRunner(client: client).run(
            .loraResume(.init(modelID: "melix-dev-text", groupID: "nightly-qwen35"))
        )

        let calls = await client.modelOperationCalls.filter { $0.ext["melix.registry_rescan"] != "true" }
        #expect(calls.count == 2)
        #expect(calls.first?.operation == "registry_snapshot")
        let trainCall = try #require(calls.last)
        #expect(trainCall.operation == "train_lora")
        #expect(trainCall.ext["resume_manifest_path"] == manifestURL.path)
        #expect(trainCall.ext["dataset_uri"] == "/tmp/datasets/nightly.jsonl")
        #expect(trainCall.ext["adapter_name"] == "nightly-qwen35")
        #expect(trainCall.ext["preset_id"] == "balanced_adapter")
        #expect(trainCall.ext["experiment_group_id"] == "nightly-qwen35")
        #expect(output == "/tmp/melix-train-lora/resume-out/train_lora.adapter.json")
    }

    @Test("lora resume applies CLI overrides over manifest defaults")
    func loraResumeAppliesCLIOverrides() async throws {
        let client = StubControlPlaneXPCClient()
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-lora-resume-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let manifestURL = tempDir.appendingPathComponent("train_lora.adapter.json")
        try writeJSONObjectForTest(
            [
                "adapter_name": "nightly-qwen35",
                "dataset_uri": "/tmp/datasets/nightly.jsonl",
                "preset_id": "balanced_adapter",
            ],
            to: manifestURL
        )

        await client.setModelOperationResult(
            makeModelOperationResult(manifestJSON: makeExperimentsRegistryManifest(bestManifestPath: manifestURL.path)),
            forOperation: "registry_snapshot"
        )
        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/resume.adapter.json"),
            forOperation: "train_lora"
        )

        _ = try await MelixCLIRunner(client: client).run(
            .loraResume(.init(
                modelID: "melix-dev-text",
                groupID: "nightly-qwen35",
                presetID: "quality_adapter",
                adapterName: "resumed-adapter",
                datasetURI: "/tmp/datasets/new.jsonl"
            ))
        )

        let calls = await client.modelOperationCalls
        let trainCall = try #require(calls.last)
        #expect(trainCall.ext["dataset_uri"] == "/tmp/datasets/new.jsonl")
        #expect(trainCall.ext["adapter_name"] == "resumed-adapter")
        #expect(trainCall.ext["preset_id"] == "quality_adapter")
    }

    @Test("lora resume surfaces error when the group has no recommended adapter")
    func loraResumeErrorsWhenGroupHasNoBestAdapter() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(
            makeModelOperationResult(manifestJSON: makeExperimentsRegistryManifest(bestManifestPath: "")),
            forOperation: "registry_snapshot"
        )

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraResume(.init(modelID: "melix-dev-text", groupID: "nightly-qwen35"))
            )
            Issue.record("Expected resume to throw when no best adapter exists")
        } catch let error as MelixCLIError {
            if case .missingRequired(let message) = error {
                #expect(message.contains("no recommended adapter"))
            } else {
                Issue.record("Expected missingRequired error, got \(error)")
            }
        }
    }

    @Test("lora resume surfaces a readable error when the manifest path is missing on disk")
    func loraResumeErrorsWhenManifestMissing() async throws {
        let client = StubControlPlaneXPCClient()
        let missingPath = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-missing-\(UUID().uuidString).json")
            .path
        await client.setModelOperationResult(
            makeModelOperationResult(manifestJSON: makeExperimentsRegistryManifest(bestManifestPath: missingPath)),
            forOperation: "registry_snapshot"
        )

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .loraResume(.init(modelID: "melix-dev-text", groupID: "nightly-qwen35"))
            )
            Issue.record("Expected resume to throw for a missing manifest")
        } catch let error as MelixCLIError {
            if case .runtime(let message) = error {
                #expect(message.contains(missingPath))
            } else {
                Issue.record("Expected runtime error, got \(error)")
            }
        }
    }

    @Test("lora train forwards dataset, adapter, repo, and tuning parameters")
    func loraTrainForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/train_lora/job-1"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraTrain(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    datasetSourceKind: "local_package",
                    datasetURI: "/tmp/datasets/alpaca.jsonl",
                    adapterName: "demo-adapter",
                    targetRepo: "melix/demo-adapter",
                    parameters: [
                        "preset_id": "balanced_adapter",
                        "experiment_group_id": "nightly-qwen35",
                        "rank": "8",
                        "epochs": "3",
                    ]
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/train_lora/job-1")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.operation == "train_lora")
        #expect(call.ext["dataset_source_kind"] == "local_package")
        #expect(call.ext["dataset_uri"] == "/tmp/datasets/alpaca.jsonl")
        #expect(call.ext["adapter_name"] == "demo-adapter")
        #expect(call.ext["target_repo"] == "melix/demo-adapter")
        #expect(call.ext["preset_id"] == "balanced_adapter")
        #expect(call.ext["experiment_group_id"] == "nightly-qwen35")
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
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    datasetSourceKind: "hf_dataset",
                    datasetURI: "",
                    adapterName: "hf-demo-adapter",
                    trainingMode: "qlora",
                    parameters: [
                        "hf_dataset_path": "HuggingFaceH4/ultrachat_200k",
                        "hf_dataset_name": "default",
                        "hf_dataset_revision": "main",
                        "hf_train_split": "train_sft",
                        "hf_valid_split": "test_sft",
                        "sample_limit": "8",
                        "text_feature": "messages",
                        "response_only": "true",
                        "mask_prompt": "true",
                        "gradient_checkpointing": "true",
                        "derived_model_alias": "melix-qwen35-acceptance",
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
        #expect(call.ext["training_mode"] == "qlora")
        #expect(call.ext["sample_limit"] == "8")
        #expect(call.ext["text_feature"] == "messages")
        #expect(call.ext["response_only"] == "true")
        #expect(call.ext["mask_prompt"] == "true")
        #expect(call.ext["gradient_checkpointing"] == "true")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.ext["derived_model_alias"] == "melix-qwen35-acceptance")
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
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
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

    @Test("lora dataset inspect forwards local source options and renders a dataset summary")
    func loraDatasetInspectForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/inspect/training_dataset.inspect.json",
            manifestJSON: #"""
            {
              "schema_version": "melix.training_dataset_inspection.v1",
              "dataset_id": "melix-alpaca-demo",
              "format": "prompt_completion",
              "sample_count": 2,
              "validation_sample_count": 1,
              "quality": {
                "duplicate_count": 1,
                "dirty_count": 1
              },
              "token_stats": {
                "prompt_tokens_p95": 8
              }
            }
            """#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraDatasetInspect(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    datasetSourceKind: "local_path",
                    datasetURI: "/tmp/datasets/alpaca.jsonl",
                    parameters: [
                        "template": "alpaca",
                        "validation_ratio": "0.2",
                        "preview_count": "4",
                    ]
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.operation == "build_training_dataset")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.ext["inspect_only"] == "true")
        #expect(call.ext["dataset_source_kind"] == "local_path")
        #expect(call.ext["dataset_uri"] == "/tmp/datasets/alpaca.jsonl")
        #expect(call.ext["template"] == "alpaca")
        #expect(call.ext["validation_ratio"] == "0.2")
        #expect(call.ext["preview_count"] == "4")
        #expect(output.contains("dataset_id=melix-alpaca-demo"))
        #expect(output.contains("format=prompt_completion"))
        #expect(output.contains("sample_count=2"))
        #expect(output.contains("duplicate_count=1"))
        #expect(output.contains("prompt_tokens_p95=8"))
    }

    @Test("lora dataset build forwards Hugging Face source metadata and returns the built package path")
    func loraDatasetBuildForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/built-dataset",
            manifestJSON: #"{"dataset_id":"melix-ultrachat-built","sample_count":8}"#
        ))

        let output = try await MelixCLIRunner(client: client).run(
            .loraDatasetBuild(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    datasetSourceKind: "hf_dataset",
                    datasetURI: "",
                    outputDir: "/tmp/melix/built-dataset",
                    parameters: [
                        "hf_dataset_path": "HuggingFaceH4/ultrachat_200k",
                        "hf_dataset_name": "default",
                        "hf_train_split": "train_sft",
                        "hf_valid_split": "test_sft",
                        "template": "chat_messages",
                        "dataset_id": "melix-ultrachat-built",
                    ]
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/built-dataset")
        #expect(call.operation == "build_training_dataset")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.outputDir == "/tmp/melix/built-dataset")
        #expect(call.ext["inspect_only"] == nil)
        #expect(call.ext["dataset_source_kind"] == "hf_dataset")
        #expect(call.ext["hf_dataset_path"] == "HuggingFaceH4/ultrachat_200k")
        #expect(call.ext["hf_dataset_name"] == "default")
        #expect(call.ext["hf_train_split"] == "train_sft")
        #expect(call.ext["hf_valid_split"] == "test_sft")
        #expect(call.ext["template"] == "chat_messages")
        #expect(call.ext["dataset_id"] == "melix-ultrachat-built")
    }

    @Test("lora activate forwards adapter path and derived alias")
    func loraActivateForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/activate_adapter/job-2"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraActivate(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    adapterPath: "/tmp/melix/adapters/demo-adapter.json",
                    derivedModelAlias: "melix-qwen35-acceptance",
                    activationMode: "adapter_backed_runtime"
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/activate_adapter/job-2")
        #expect(call.operation == "activate_adapter")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.ext["artifact_path"] == "/tmp/melix/adapters/demo-adapter.json")
        #expect(call.ext["derived_model_alias"] == "melix-qwen35-acceptance")
        #expect(call.ext["activation_mode"] == "adapter_backed_runtime")
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
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    adapterPath: "/tmp/melix/adapters/demo-adapter.json",
                    json: true
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(call.ext["derived_model_alias"] == nil)
        #expect(output == #"{"job_id":"job-2","status":"completed"}"#)
    }

    @Test("lora remove-derived forwards the derived model target")
    func loraRemoveDerivedForwardsExpectedOperationPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/remove_derived_model/job-3"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraRemoveDerived(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    derivedModelID: "melix-qwen35-acceptance"
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/remove_derived_model/job-3")
        #expect(call.operation == "remove_derived_model")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.ext["derived_model_id"] == "melix-qwen35-acceptance")
        #expect(call.ext["manifest_path"] == nil)
    }

    @Test("lora remove-derived forwards the manifest path target")
    func loraRemoveDerivedForwardsManifestPathPayload() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/remove_derived_model/job-4"))

        let output = try await MelixCLIRunner(client: client).run(
            .loraRemoveDerived(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    manifestPath: "/tmp/melix/activate_adapter/job-2/activate_adapter.derived_model.json"
                )
            )
        )
        let call = try #require(await client.lastModelOperationCall)

        #expect(output == "/tmp/melix/remove_derived_model/job-4")
        #expect(call.operation == "remove_derived_model")
        #expect(call.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(call.ext["derived_model_id"] == nil)
        #expect(call.ext["manifest_path"] == "/tmp/melix/activate_adapter/job-2/activate_adapter.derived_model.json")
    }

    @Test("lora publish forwards adapter and merged export selections")
    func loraPublishForwardsExplicitExportSelections() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setModelOperationResult(makeModelOperationResult(outputPath: "/tmp/melix/upload/job-5"))

        let adapterOutput = try await MelixCLIRunner(client: client).run(
            .loraPublish(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    targetRepo: "melix/adapters/demo",
                    exportKind: .adapterExport,
                    artifactPath: "/tmp/melix/train_lora.adapter.json",
                    artifactManifestPath: "/tmp/melix/train_lora.adapter.json"
                )
            )
        )
        let adapterCall = try #require(await client.lastModelOperationCall)

        #expect(adapterOutput == "/tmp/melix/upload/job-5")
        #expect(adapterCall.operation == "upload")
        #expect(adapterCall.ext["target_repo"] == "melix/adapters/demo")
        #expect(adapterCall.ext["artifact_kind"] == "adapter_export")
        #expect(adapterCall.ext["artifact_path"] == "/tmp/melix/train_lora.adapter.json")
        #expect(adapterCall.ext["artifact_manifest_path"] == "/tmp/melix/train_lora.adapter.json")

        await client.setModelOperationResult(makeModelOperationResult(
            outputPath: "/tmp/melix/upload/job-6",
            manifestJSON: #"{"job_id":"job-6","operation":"upload"}"#
        ))
        let mergedOutput = try await MelixCLIRunner(client: client).run(
            .loraPublish(
                .init(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    targetRepo: "melix/models/demo-merged",
                    exportKind: .mergedExport,
                    artifactPath: "/tmp/melix/activate_adapter/job-2/manifest.json",
                    artifactManifestPath: "/tmp/melix/activate_adapter/job-2/manifest.json",
                    json: true
                )
            )
        )
        let mergedCall = try #require(await client.lastModelOperationCall)

        #expect(mergedOutput.contains("job-6"))
        #expect(mergedCall.ext["target_repo"] == "melix/models/demo-merged")
        #expect(mergedCall.ext["artifact_kind"] == "merged_export")
        #expect(mergedCall.ext["artifact_path"] == "/tmp/melix/activate_adapter/job-2/manifest.json")
        #expect(mergedCall.ext["artifact_manifest_path"] == "/tmp/melix/activate_adapter/job-2/manifest.json")
    }

    @Test("subprocess-backed lora operations build public melix arguments and decode manifest payloads")
    func subprocessBackedLoraOperationsBuildPublicCLIArguments() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                #"{"operation":"train_lora","job_id":"train-job-1","output_path":"/tmp/melix/train_lora/job-1","adapter_name":"demo-adapter"}"#,
                #"{"operation":"activate_adapter","job_id":"activate-job-1","output_path":"/tmp/melix/activate_adapter/job-1","derived_model_id":"melix-qwen35-acceptance"}"#,
                #"{"operation":"registry_snapshot","adapters":[{"adapter_name":"demo-adapter","status":"activated"}]}"#,
            ]
        )
        let runner = MelixCLIRunner(
            client: client,
            commandExecutor: executor.run
        )

        let trainResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "train_lora",
            outputDir: "",
            ext: [
                "dataset_source_kind": "hf_dataset",
                "adapter_name": "demo-adapter",
                "training_mode": "qlora",
                "preset_id": "debug_fast",
                "experiment_group_id": "phase8-real-small-model",
                "max_steps": "2",
                "hf_dataset_path": "HuggingFaceH4/ultrachat_200k",
                "hf_train_split": "train_sft",
                "chat_feature": "messages",
                "derived_model_alias": "melix-qwen35-acceptance",
            ]
        )
        let activateResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "activate_adapter",
            outputDir: "",
            ext: [
                "artifact_path": "/tmp/melix/train_lora/job-1/train_lora.adapter.json",
                "activation_mode": "adapter_backed_runtime",
                "derived_model_alias": "melix-qwen35-acceptance",
            ]
        )
        let registrySnapshot = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "registry_snapshot",
            outputDir: "",
            ext: [:]
        )
        let commands = await executor.commands

        #expect(await client.lastModelOperationCall == nil)
        #expect(trainResult.outputPath == "/tmp/melix/train_lora/job-1")
        #expect(activateResult.outputPath == "/tmp/melix/activate_adapter/job-1")
        #expect(parseJSONObject(registrySnapshot.manifestJson)?["operation"] as? String == "registry_snapshot")
        #expect(commands.count == 3)
        #expect(commands[0].contains("lora"))
        #expect(commands[0].contains("train"))
        #expect(commands[0].contains("--training-mode"))
        #expect(commands[0].contains("qlora"))
        #expect(commands[0].contains("--preset"))
        #expect(commands[0].contains("debug_fast"))
        #expect(commands[0].contains("--experiment-group"))
        #expect(commands[0].contains("phase8-real-small-model"))
        #expect(commands[0].contains("--max-steps"))
        #expect(commands[0].contains("2"))
        #expect(commands[0].contains("--hf-dataset-path"))
        #expect(commands[0].contains("HuggingFaceH4/ultrachat_200k"))
        #expect(commands[1].contains("activate"))
        #expect(commands[1].contains("--activation-mode"))
        #expect(commands[1].contains("adapter_backed_runtime"))
        #expect(commands[2] == ["lora", "list", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit", "--json"])
    }

    @Test("subprocess-backed lora publish builds explicit adapter and merged publish arguments")
    func subprocessBackedLoraPublishBuildsExplicitArguments() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                #"{"operation":"upload","job_id":"upload-adapter-1","output_path":"/tmp/melix/upload/adapter"}"#,
                #"{"operation":"upload","job_id":"upload-merged-1","output_path":"/tmp/melix/upload/merged"}"#,
            ]
        )
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        _ = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "upload",
            outputDir: "",
            ext: [
                "target_repo": "melix/adapters/demo",
                "artifact_path": "/tmp/melix/train_lora.adapter.json",
                "artifact_kind": "adapter_export",
                "artifact_manifest_path": "/tmp/melix/train_lora.adapter.json",
            ]
        )
        _ = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "upload",
            outputDir: "",
            ext: [
                "target_repo": "melix/models/demo-merged",
                "artifact_path": "/tmp/melix/activate_adapter/manifest.json",
                "artifact_kind": "merged_export",
                "artifact_manifest_path": "/tmp/melix/activate_adapter/manifest.json",
            ]
        )
        let commands = await executor.commands

        #expect(commands.count == 2)
        #expect(commands[0].starts(with: ["lora", "publish", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"]))
        #expect(commands[0].contains("--adapter-path"))
        #expect(commands[0].contains("/tmp/melix/train_lora.adapter.json"))
        #expect(commands[1].contains("--manifest-path"))
        #expect(commands[1].contains("/tmp/melix/activate_adapter/manifest.json"))
        #expect(commands[1].contains("melix/models/demo-merged"))
    }

    @Test("subprocess-backed evaluation compare builds public melix compare arguments")
    func subprocessBackedEvaluationCompareBuildsPublicCLIArguments() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                """
                [
                  {
                    "job_id": "eval-compare-1",
                    "model_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    "task_kind": "text-generation",
                    "source_repo": "",
                    "suite_id": "mmlu",
                    "dataset_id": "mmlu.dev.v1",
                    "sample_size": 6,
                    "scoring_mode": "multiple_choice_accuracy",
                    "status": "completed",
                    "output_dir": "/tmp/melix/evaluation/runs/eval-compare-1",
                    "created_at_unix_ms": 1712000000000,
                    "updated_at_unix_ms": 1712000001000,
                    "results": []
                  }
                ]
                """
            ]
        )
        let runner = MelixCLIRunner(
            client: client,
            commandExecutor: executor.run
        )

        let results = try await runner.runEvaluationCompare(
            EvalCompareOptions(
                modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                targetModelIDs: ["melix-qwen35-acceptance", "melix-qwen35-safety"],
                suites: ["mmlu"],
                sampleSize: 6,
                parameters: [
                    "batch_factor": "2",
                    "few_shot": "1",
                    "seed": "9",
                    "scoring_mode": "multiple_choice_accuracy",
                    "code_exec_policy": "sandboxed",
                ]
            )
        )
        let command = try #require(await executor.commands.last)

        #expect(results.count == 1)
        #expect(await client.evaluationRequests.isEmpty)
        #expect(await client.loadedModelIDs.isEmpty)
        #expect(command.starts(with: ["eval", "compare"]))
        #expect(command.contains("--target-model-id"))
        #expect(command.contains("melix-qwen35-acceptance"))
        #expect(command.contains("melix-qwen35-safety"))
        #expect(command.contains("--batch-factor"))
        #expect(command.contains("2"))
        #expect(command.contains("--few-shot"))
        #expect(command.contains("--seed"))
        #expect(command.contains("--scoring-mode"))
        #expect(command.contains("--code-exec-policy"))
        #expect(command.last == "--json")
    }

    @Test("eval compare forwards --target-adapter manifest paths to the subprocess argv")
    func evalCompareForwardsAdapterTargetsToSubprocessArgv() async throws {
        // Module 2 surface: when adapter-manifest targets are supplied via
        // --target-adapter, the subprocess argv echoes each repeatable flag
        // so the in-process worker can parse them into
        // compare_target_adapter_manifest_paths.
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                """
                [
                  {
                    "job_id": "eval-compare-adapter",
                    "model_id": "melix-dev-text",
                    "task_kind": "text-generation",
                    "source_repo": "",
                    "suite_id": "mmlu",
                    "dataset_id": "",
                    "sample_size": 2,
                    "scoring_mode": "multiple_choice_accuracy",
                    "status": "completed",
                    "output_dir": "/tmp/melix/evaluation/runs/eval-compare-adapter",
                    "created_at_unix_ms": 1712000000000,
                    "updated_at_unix_ms": 1712000001000,
                    "results": []
                  }
                ]
                """
            ]
        )
        let runner = MelixCLIRunner(
            client: client,
            commandExecutor: executor.run
        )

        let results = try await runner.runEvaluationCompare(
            EvalCompareOptions(
                modelID: "melix-dev-text",
                targetAdapterManifestPaths: [
                    "/tmp/melix-adapters/alpha.adapter.json",
                    "/tmp/melix-adapters/beta.adapter.json",
                ],
                suites: ["mmlu"],
                sampleSize: 2
            )
        )
        let command = try #require(await executor.commands.last)

        #expect(results.count == 1)
        // Ephemeral adapter targets should NOT trigger a pre-load on the
        // client — the worker materializes them during the compare run.
        #expect(await client.loadedModelIDs.isEmpty)
        // --target-adapter must appear twice, once per manifest path.
        let adapterFlagIndices = command.enumerated().compactMap { index, value in
            value == "--target-adapter" ? index : nil
        }
        #expect(adapterFlagIndices.count == 2)
        #expect(command.contains("/tmp/melix-adapters/alpha.adapter.json"))
        #expect(command.contains("/tmp/melix-adapters/beta.adapter.json"))
        // No registered-model targets were requested, so --target-model-id
        // must be absent.
        #expect(!command.contains("--target-model-id"))
    }

    @Test("process executor runs the configured subprocess with working-directory and environment overrides")
    func processExecutorRunsConfiguredSubprocess() async throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-cli-process-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let executor = MelixCLIProcessExecutor(
            baseCommand: [
                "/bin/zsh",
                "-lc",
                #"printf "%s" "$MELIX_SUBPROCESS_TEST:$PWD:$1""#,
                "melix-process",
            ],
            environment: ["MELIX_SUBPROCESS_TEST": "configured"],
            workingDirectory: root.path
        )

        let output = try await executor.run(arguments: ["runner-arg"])
        let components = output.split(separator: ":", maxSplits: 2).map(String.init)

        #expect(components.count == 3)
        #expect(components[0] == "configured")
        #expect(
            URL(fileURLWithPath: components[1]).resolvingSymlinksInPath().path ==
            root.resolvingSymlinksInPath().path
        )
        #expect(components[2] == "runner-arg")
    }

    @Test("process executor surfaces subprocess failures and rejects empty commands")
    func processExecutorSurfacesFailuresAndMisconfiguration() async throws {
        let failingExecutor = MelixCLIProcessExecutor(
            baseCommand: [
                "/bin/zsh",
                "-lc",
                #"printf "%s" "subprocess boom" >&2; exit 3"#,
                "melix-process",
            ]
        )

        do {
            _ = try await failingExecutor.run(arguments: [])
            Issue.record("Expected the configured subprocess to fail.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("subprocess boom"))
        }

        let misconfiguredExecutor = MelixCLIProcessExecutor(baseCommand: [])

        do {
            _ = try await misconfiguredExecutor.run(arguments: [])
            Issue.record("Expected an empty subprocess command to fail.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("The melix subprocess command is not configured."))
        }
    }

    @Test("subprocess-backed model operations cover local-package remove-derived and download argument branches")
    func subprocessBackedModelOperationsCoverAdditionalArgumentBranches() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                #"{"operation":"train_lora","job_id":"train-local-1","output_path":"/tmp/melix/train_lora/train-local-1"}"#,
                #"{"operation":"remove_derived_model","job_id":"remove-job-1","output_path":"/tmp/melix/remove_derived_model/remove-job-1"}"#,
                #"{"operation":"download","job_id":"download-job-1","output_path":"/tmp/melix-downloads/qwen35"}"#,
            ]
        )
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        let trainResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "train_lora",
            outputDir: "",
            ext: [
                "dataset_source_kind": "local_package",
                "dataset_uri": "/tmp/melix/datasets/alpaca",
                "adapter_name": "demo-adapter",
                "target_repo": "melix/demo-adapter",
                "response_only": "true",
                "mask_prompt": "true",
                "gradient_checkpointing": "true",
            ]
        )
        let removeResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "remove_derived_model",
            outputDir: "",
            ext: [
                "derived_model_id": "melix-qwen35-acceptance",
                "manifest_path": "/tmp/melix/activate_adapter/job-1/activate_adapter.derived_model.json",
            ]
        )
        let downloadResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "download",
            outputDir: "/tmp/melix-downloads",
            ext: [:]
        )
        let commands = await executor.commands

        #expect(trainResult.jobID == "train-local-1")
        #expect(removeResult.jobID == "remove-job-1")
        #expect(downloadResult.outputPath == "/tmp/melix-downloads/qwen35")
        #expect(commands.count == 3)
        #expect(commands[0].contains("--dataset-uri"))
        #expect(commands[0].contains("/tmp/melix/datasets/alpaca"))
        #expect(commands[0].contains("--response-only"))
        #expect(commands[0].contains("--mask-prompt"))
        #expect(commands[0].contains("--gradient-checkpointing"))
        #expect(commands[1].contains("remove-derived"))
        #expect(commands[1].contains("--derived-model-id"))
        #expect(commands[1].contains("--manifest-path"))
        #expect(commands[2].contains("download"))
        #expect(commands[2].contains("--output-dir"))
        #expect(commands[2].contains("/tmp/melix-downloads"))
    }

    @Test("subprocess-backed model operations cover convert quantize and upload argument branches")
    func subprocessBackedModelOperationsCoverPublicModelOpsBranches() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                #"{"operation":"convert","job_id":"convert-job-1","output_path":"/tmp/melix-convert/convert.artifact"}"#,
                #"{"operation":"quantize","job_id":"quantize-job-1","output_path":"/tmp/melix-quantize/quantize.artifact"}"#,
                #"{"operation":"upload","job_id":"upload-job-1","output_path":"/tmp/melix-upload/upload.receipt.json"}"#,
            ]
        )
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        let convertResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "convert",
            outputDir: "/tmp/melix-convert",
            ext: ["target_format": "melix_model_bundle"]
        )
        let quantizeResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "quantize",
            outputDir: "/tmp/melix-quantize",
            quantProfileID: "q4",
            weightQuant: "q4",
            kvQuant: "q8"
        )
        let uploadResult = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "upload",
            outputDir: "/tmp/melix-upload",
            ext: [
                "target_repo": "melix/models/demo",
                "artifact_path": "/tmp/melix-convert/convert.artifact",
                "artifact_kind": "converted_model_bundle",
                "artifact_manifest_path": "/tmp/melix-convert/convert.artifact/manifest.json",
            ]
        )
        let commands = await executor.commands

        #expect(convertResult.jobID == "convert-job-1")
        #expect(quantizeResult.jobID == "quantize-job-1")
        #expect(uploadResult.jobID == "upload-job-1")
        #expect(commands.count == 3)
        #expect(commands[0].starts(with: ["convert", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"]))
        #expect(commands[0].contains("--output-dir"))
        #expect(commands[0].contains("/tmp/melix-convert"))
        #expect(commands[0].contains("--target-format"))
        #expect(commands[1].starts(with: ["quantize", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"]))
        #expect(commands[1].contains("--quant-profile-id"))
        #expect(commands[1].contains("--weight-quant"))
        #expect(commands[1].contains("--kv-quant"))
        #expect(commands[2].starts(with: ["upload", "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"]))
        #expect(commands[2].contains("--target-repo"))
        #expect(commands[2].contains("--artifact-path"))
        #expect(commands[2].contains("--artifact-kind"))
        #expect(commands[2].contains("--artifact-manifest-path"))
    }

    @Test("subprocess-backed model operations preserve raw manifest output when JSON decoding is unavailable")
    func subprocessBackedModelOperationsPreserveRawManifestOutput() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(responses: ["plain-manifest-output"])
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        let result = try await runner.performModelOperation(
            modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            operation: "activate_adapter",
            outputDir: "",
            ext: [
                "artifact_path": "/tmp/melix/train_lora/job-1/train_lora.adapter.json",
            ]
        )

        #expect(result.operation == "activate_adapter")
        #expect(result.manifestJson == "plain-manifest-output")
        #expect(result.jobID.isEmpty)
        #expect(result.outputPath.isEmpty)
    }

    @Test("subprocess-backed eval compare supports repo ids and decodes nested result payloads")
    func subprocessBackedEvaluationCompareSupportsRepoTargetsAndNestedResults() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(
            responses: [
                """
                [
                  0,
                  {
                    "job": {
                      "job_id": "eval-compare-2",
                      "model_id": "",
                      "task_kind": "text-generation",
                      "source_repo": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                      "suite_id": "mmlu",
                      "dataset_id": "mmlu.dev.v1",
                      "sample_size": 6,
                      "scoring_mode": "multiple_choice_accuracy",
                      "parameters": {
                        "batch_factor": "2"
                      },
                      "status": "completed",
                      "output_dir": "/tmp/melix/evaluation/runs/eval-compare-2",
                      "created_at_unix_ms": 1712000000000,
                      "updated_at_unix_ms": 1712000001000
                    },
                    "results": [
                      {
                        "job_id": "eval-compare-2",
                        "suite_id": "mmlu:melix-qwen35-acceptance",
                        "dataset_id": "mmlu.dev.v1",
                        "sample_size": 6,
                        "report_path": "/tmp/melix/evaluation/runs/eval-compare-2/summary.json",
                        "metrics": [
                          {
                            "name": "eval.compare.win_rate",
                            "value": 0.625,
                            "unit": "ratio"
                          }
                        ]
                      }
                    ]
                  }
                ]
                """
            ]
        )
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        let results = try await runner.runEvaluationCompare(
            EvalCompareOptions(
                hfRepoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                targetModelIDs: ["melix-qwen35-acceptance"],
                suites: ["mmlu"],
                sampleSize: 6,
                source: .localJSONL(path: "/tmp/eval/mmlu.jsonl"),
                fieldMapping: .init(
                    inputTextPath: "prompt",
                    targetPath: "expected",
                    sampleIDPath: "sample_id"
                ),
                profile: .init(
                    profileType: "final_result",
                    resultKind: "text",
                    extractionMode: "heuristic_final",
                    scoringMode: "multiple_choice_accuracy",
                    threshold: 0.8,
                    ignoredPaths: ["metadata.trace_id"]
                ),
                parameters: [
                        "batch_factor": "2",
                    "dataset_root": "/tmp/mmlu-split-01",
                    "few_shot": "1",
                    "seed": "9",
                    "scoring_mode": "multiple_choice_accuracy",
                    "code_exec_policy": "sandboxed",
                ]
            )
        )
        let command = try #require(await executor.commands.last)
        let first = try #require(results.first)
        let firstMetric = try #require(first.results.first?.metrics.first)

        #expect(await client.evaluationRequests.isEmpty)
        #expect(command.contains("--repo-id"))
        #expect(command.contains("mlx-community/Qwen3.5-0.8B-OptiQ-4bit"))
        #expect(command.contains("--target-model-id"))
        #expect(command.contains("melix-qwen35-acceptance"))
        #expect(command.contains("--source-jsonl"))
        #expect(command.contains("/tmp/eval/mmlu.jsonl"))
        #expect(command.contains("--field-input-text-path"))
        #expect(command.contains("prompt"))
        #expect(command.contains("--field-target-path"))
        #expect(command.contains("expected"))
        #expect(command.contains("--threshold"))
        #expect(command.contains("0.8"))
        #expect(command.contains("--ignored-path"))
        #expect(command.contains("metadata.trace_id"))
        #expect(command.contains("--batch-factor"))
        #expect(command.contains("--dataset-root"))
        #expect(command.contains("--few-shot"))
        #expect(command.contains("--seed"))
        #expect(command.contains("--scoring-mode"))
        #expect(command.contains("--code-exec-policy"))
        #expect(command.last == "--json")
        #expect(results.count == 1)
        #expect(first.job.jobID == "eval-compare-2")
        #expect(first.job.sourceRepo == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(first.results.count == 1)
        #expect(first.results[0].suiteID == "mmlu:melix-qwen35-acceptance")
        #expect(firstMetric.name == "eval.compare.win_rate")
        #expect(firstMetric.value == 0.625)
        #expect(firstMetric.unit == "ratio")
    }

    @Test("subprocess-backed eval compare rejects non-array JSON payloads")
    func subprocessBackedEvaluationCompareRejectsNonArrayPayloads() async throws {
        let client = StubControlPlaneXPCClient()
        let executor = RecordingCLICommandExecutor(responses: [#"{"job_id":"eval-compare-invalid"}"#])
        let runner = MelixCLIRunner(client: client, commandExecutor: executor.run)

        do {
            _ = try await runner.runEvaluationCompare(
                EvalCompareOptions(
                    modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                    targetModelIDs: ["melix-qwen35-acceptance"],
                    suites: ["mmlu"]
                )
            )
            Issue.record("Expected subprocess-backed eval compare decoding to fail.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("The melix eval compare subprocess did not return a JSON array."))
        }
    }

    @Test("recording subprocess executor fails without a configured response")
    func recordingExecutorFailsWithoutAConfiguredResponse() async throws {
        let emptyExecutor = RecordingCLICommandExecutor(responses: [])

        do {
            _ = try await emptyExecutor.run(["lora", "train"])
            Issue.record("Expected the recording executor to fail without a configured response.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No subprocess response was configured for lora train."))
        }
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

    @Test("eval run forwards custom Hugging Face dataset source mapping and profile controls")
    func evalRunForwardsCustomHFDatasetSourceMappingAndProfileControls() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-hf-custom-1",
                suiteID: "dolly",
                datasetID: "databricks-dolly-15k.dev.v1",
                metricName: "eval.dolly.exact_match",
                metricValue: 0.5
            ),
        ])

        _ = try await MelixCLIRunner(client: client).run(
            .evalRun(
                .init(
                    hfRepoID: "unsloth/gemma-4-E4B-it-MLX-8bit",
                    suites: ["dolly"],
                    source: .huggingFaceDataset(
                        datasetPath: "databricks/databricks-dolly-15k",
                        datasetRevision: "main",
                        split: "train"
                    ),
                    fieldMapping: .init(
                        inputTextPath: "instruction",
                        targetPath: "response",
                        sampleIDPath: "sample_id"
                    ),
                    profile: .init(
                        profileType: "final_result",
                        resultKind: "text",
                        extractionMode: "heuristic_final",
                        scoringMode: "normalized_exact_match",
                        threshold: 1.0,
                        ignoredPaths: ["metadata.trace_id"]
                    ),
                    parameters: [
                        "scoring_mode": "normalized_exact_match",
                    ]
                )
            )
        )
        let request = try #require((await client.evaluationRequests).first)

        #expect(request.datasetID.isEmpty)
        #expect(request.source.kind == .huggingFaceDataset)
        #expect(request.source.datasetPath == "databricks/databricks-dolly-15k")
        #expect(request.source.datasetRevision == "main")
        #expect(request.source.split == "train")
        #expect(request.fieldMapping.inputTextPath == "instruction")
        #expect(request.fieldMapping.targetPath == "response")
        #expect(request.fieldMapping.sampleIDPath == "sample_id")
        #expect(request.profile.resultKind == "text")
        #expect(request.profile.extractionMode == "heuristic_final")
        #expect(request.profile.scoringMode == "normalized_exact_match")
        #expect(request.profile.threshold == 1.0)
        #expect(request.profile.ignoredPaths == ["metadata.trace_id"])
    }

    @Test("eval compare preloads base and target models and forwards comparison parameters")
    func evalComparePreloadsBaseAndTargetsAndReturnsJSON() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-compare-1",
                suiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                metricName: "eval.compare.win_rate",
                metricValue: 0.5
            ),
        ])

        let output = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora-a", "melix-dev-text-lora-b"],
                    suites: ["mmlu"],
                    datasetID: "mmlu.dev.v1",
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
        let requests = await client.evaluationRequests
        let payload = try #require(parseJSONArray(output))
        let firstRun = try #require(payload.first as? [String: Any])
        let firstJob = try #require(firstRun["job"] as? [String: Any])

        #expect(await client.loadedModelIDs == ["melix-dev-text", "melix-dev-text-lora-a", "melix-dev-text-lora-b"])
        #expect(requests.count == 1)
        #expect(requests[0].modelID == "melix-dev-text")
        #expect(requests[0].suiteID == "mmlu")
        #expect(requests[0].datasetID == "mmlu.dev.v1")
        #expect(requests[0].sampleSize == 8)
        #expect(requests[0].parameters["compare_mode"] == "base_vs_targets")
        #expect(requests[0].parameters["compare_target_model_ids"] == "melix-dev-text-lora-a,melix-dev-text-lora-b")
        #expect(requests[0].parameters["batch_factor"] == "2")
        #expect(requests[0].parameters["dataset_root"] == "/tmp/mmlu-split-01")
        #expect(requests[0].parameters["few_shot"] == "4")
        #expect(requests[0].parameters["seed"] == "7")
        #expect(requests[0].parameters["scoring_mode"] == "multiple_choice_accuracy")
        #expect(requests[0].parameters["code_exec_policy"] == "sandboxed")
        #expect(firstJob["job_id"] as? String == "eval-compare-1")
        #expect(firstJob["suite_id"] as? String == "mmlu")
    }

    @Test("eval compare forwards custom JSONL source mapping and profile controls")
    func evalCompareForwardsCustomJSONLSourceMappingAndProfileControls() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationRunResult(
                jobID: "eval-compare-custom-1",
                suiteID: "mmlu",
                datasetID: "mmlu-jsonl.dev.v1",
                metricName: "eval.compare.win_rate",
                metricValue: 0.5
            ),
        ])

        _ = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora"],
                    suites: ["mmlu"],
                    source: .localJSONL(path: "/tmp/eval/mmlu.jsonl"),
                    fieldMapping: .init(
                        inputTextPath: "prompt",
                        targetPath: "expected",
                        sampleIDPath: "sample_id"
                    ),
                    profile: .init(
                        profileType: "final_result",
                        resultKind: "text",
                        extractionMode: "heuristic_final",
                        scoringMode: "normalized_exact_match",
                        threshold: 0.8,
                        ignoredPaths: ["metadata.trace_id"]
                    ),
                    parameters: [
                        "scoring_mode": "normalized_exact_match",
                    ],
                    json: true
                )
            )
        )
        let request = try #require((await client.evaluationRequests).first)

        #expect(await client.loadedModelIDs == ["melix-dev-text", "melix-dev-text-lora"])
        #expect(request.datasetID.isEmpty)
        #expect(request.parameters["compare_mode"] == "base_vs_targets")
        #expect(request.parameters["compare_target_model_ids"] == "melix-dev-text-lora")
        #expect(request.source.kind == .localJSONL)
        #expect(request.source.path == "/tmp/eval/mmlu.jsonl")
        #expect(request.fieldMapping.inputTextPath == "prompt")
        #expect(request.fieldMapping.targetPath == "expected")
        #expect(request.fieldMapping.sampleIDPath == "sample_id")
        #expect(request.profile.resultKind == "text")
        #expect(request.profile.extractionMode == "heuristic_final")
        #expect(request.profile.scoringMode == "normalized_exact_match")
        #expect(request.profile.threshold == 0.8)
        #expect(request.profile.ignoredPaths == ["metadata.trace_id"])
    }

    @Test("eval compare rejects requests without target models before dispatch")
    func evalCompareRejectsMissingTargetsBeforeDispatch() async throws {
        let client = StubControlPlaneXPCClient()

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .evalCompare(
                    .init(
                        modelID: "melix-dev-text",
                        suites: ["mmlu"],
                        datasetID: "mmlu.dev.v1",
                        sampleSize: 8
                    )
                )
            )
            Issue.record("Expected eval compare to fail when no target models are provided.")
        } catch let error as MelixCLIError {
            #expect(error == .missingRequired("At least one --target-model-id or --target-adapter is required for melix eval compare."))
        }

        #expect(await client.loadedModelIDs.isEmpty)
        #expect(await client.evaluationRequests.isEmpty)
    }

    @Test("eval compare renders one text row per comparison result")
    func evalCompareRendersTextOutputRows() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationCompareResult(
                jobID: "eval-compare-2",
                baseSuiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                targets: [
                    ("melix-dev-text-lora-a", 0.625),
                    ("melix-dev-text-lora-b", 0.375),
                ]
            ),
        ])
        await client.setExportResult(.init(exportBundleJSON: makeEvaluationCompareExportBundleJSON()))
        let output = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora-a", "melix-dev-text-lora-b"],
                    suites: ["mmlu"],
                    datasetID: "mmlu.dev.v1",
                    sampleSize: 8
                )
            )
        )

        #expect(output.contains("job_id\tsuite\tdataset\tstatus\tverdict\tdelta\tbootstrap_ci\tanalytical_ci\tthreshold"))
        #expect(output.contains("eval-compare-2\tmmlu:melix-dev-text-lora-a\tmmlu.dev.v1\tcompleted\timprovement\t+0.2500\t[+0.1200, +0.4100]\t[+0.1000, +0.3800]\t0.1000"))
        #expect(output.contains("eval-compare-2\tmmlu:melix-dev-text-lora-b\tmmlu.dev.v1\tcompleted\tinconclusive\t-0.1250\t[-0.2100, +0.0200]\t[-0.1800, +0.0100]\t0.1000"))
    }

    @Test("eval compare falls back to metrics table when compare summary rows are unavailable")
    func evalCompareFallsBackToMetricsTableWithoutCompareSummaryRows() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationCompareResult(
                jobID: "eval-compare-2",
                baseSuiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                targets: [
                    ("melix-dev-text-lora-a", 0.625),
                ]
            ),
        ])
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        let output = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora-a"],
                    suites: ["mmlu"],
                    datasetID: "mmlu.dev.v1",
                    sampleSize: 8
                )
            )
        )

        #expect(output.contains("job_id\tsuite\tdataset\tstatus\tmetrics"))
        #expect(output.contains("eval-compare-2\tmmlu:melix-dev-text-lora-a\tmmlu.dev.v1\tcompleted\teval.compare.win_rate=0.625ratio"))
    }

    @Test("eval compare renders suite fallback and placeholder evidence markers")
    func evalCompareRendersSuiteFallbackAndPlaceholderEvidenceMarkers() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationCompareResult(
                jobID: "eval-compare-2",
                baseSuiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                targets: [
                    ("melix-dev-text-lora-a", 0.625),
                ]
            ),
        ])
        await client.setExportResult(.init(exportBundleJSON: makeEvaluationCompareSparseExportBundleJSON()))

        let output = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora-a"],
                    suites: ["mmlu"],
                    datasetID: "mmlu.dev.v1",
                    sampleSize: 8
                )
            )
        )

        #expect(output.contains("job_id\tsuite\tdataset\tstatus\tverdict\tdelta\tbootstrap_ci\tanalytical_ci\tthreshold"))
        #expect(output.contains("eval-compare-2\tmmlu\tmmlu.dev.v1\tcompleted\tinconclusive\t-0.1250\t-\t-\t-"))
    }

    @Test("eval compare tolerates duplicate job identifiers in status mapping")
    func evalCompareToleratesDuplicateJobIdentifiersInStatusMapping() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setEvaluationResults([
            makeEvaluationCompareResult(
                jobID: "eval-compare-2",
                baseSuiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                targets: [
                    ("melix-dev-text-lora-a", 0.625),
                ],
                status: "queued"
            ),
            makeEvaluationCompareResult(
                jobID: "eval-compare-2",
                baseSuiteID: "arc",
                datasetID: "mmlu.dev.v1",
                targets: [
                    ("melix-dev-text-lora-a", 0.625),
                ],
                status: "completed"
            ),
        ])
        await client.setExportResult(.init(exportBundleJSON: makeEvaluationCompareExportBundleJSON()))

        let output = try await MelixCLIRunner(client: client).run(
            .evalCompare(
                .init(
                    modelID: "melix-dev-text",
                    targetModelIDs: ["melix-dev-text-lora-a"],
                    suites: ["mmlu", "arc"],
                    datasetID: "mmlu.dev.v1",
                    sampleSize: 8
                )
            )
        )

        let matchingRows = output.split(separator: "\n").filter {
            $0.contains("eval-compare-2\tmmlu:melix-dev-text-lora-a\tmmlu.dev.v1\tcompleted\timprovement")
        }
        #expect(matchingRows.count == 1)
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

    @Test("eval export commands write summary csv and sample artifacts with code evidence")
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
        #expect(summaryCSV.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,primary_score_name,primary_score_value,extraction_success_count,validation_success_count,scored_sample_count,failure_count,effect_threshold,verdict,bootstrap_lower_bound,bootstrap_upper_bound,analytical_lower_bound,analytical_upper_bound,duration_seconds,created_at_unix_ms"))
        #expect(summaryCSV.contains("eval-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,mmlu,mmlu.dev.v1,8,eval.mmlu.accuracy,0.75,8,8,8,0,0.1,improvement,0.12,0.41,0.1,0.38,12.5,1712400000000"))
        #expect(samplesCSV.contains("job_id,suite_id,id,task_kind,target,extracted_result,input_text,raw_response,typed_score,time_s,extraction_status,validation_status,failure_reason,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail,category_label,subject_label"))
        #expect(samplesCSV.contains("eval-1,mmlu,sample-1,text-generation,4,4,2+2?,4,1.0,0.01,extracted,validated,,text,,python,solve,compiled,ok,ok,passed,2,2,,math,algebra"))
        #expect(samplesJSONL.contains("\"sample_id\":\"sample-1\""))
        #expect(samplesJSONL.contains("\"task_kind\":\"text-generation\""))
        #expect(samplesJSONL.contains("\"code_language\":\"python\""))
    }

    @Test("eval compare export commands write summary csv and sample artifacts")
    func evalCompareExportCommandsWriteArtifacts() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let summaryURL = root.appendingPathComponent("eval-compare-1-summary.csv")
        let samplesURL = root.appendingPathComponent("eval-compare-1-samples.csv")
        let jsonlURL = root.appendingPathComponent("eval-compare-1-samples.jsonl")

        let summaryOutput = try await MelixCLIRunner(client: client).run(
            .evalCompareExportSummaryCSV(.init(jobID: "eval-compare-1", outputPath: summaryURL.path, json: true))
        )
        _ = try await MelixCLIRunner(client: client).run(
            .evalCompareExportSamplesCSV(.init(jobID: "eval-compare-1", outputPath: samplesURL.path))
        )
        _ = try await MelixCLIRunner(client: client).run(
            .evalCompareExportSamplesJSONL(.init(jobID: "eval-compare-1", outputPath: jsonlURL.path))
        )

        let response = try #require(parseJSONObject(summaryOutput))
        let summaryCSV = try String(contentsOf: summaryURL, encoding: .utf8)
        let samplesCSV = try String(contentsOf: samplesURL, encoding: .utf8)
        let samplesJSONL = try String(contentsOf: jsonlURL, encoding: .utf8)

        #expect(response["job_id"] as? String == "eval-compare-1")
        #expect(response["row_count"] as? Int == 1)
        #expect(summaryCSV.contains("job_id,base_model_id,target_model_id,suite_id,dataset_id,sample_size,win_count,loss_count,tie_count,regression_count,base_accuracy,target_accuracy,delta_accuracy,duration_seconds"))
        #expect(summaryCSV.contains("eval-compare-1,melix-dev-text,melix-dev-text-lora-a,mbpp,mbpp.dev.v1,2,1,0,1,0,0.5,1.0,0.5,1.75"))
        #expect(samplesCSV.contains("job_id,suite_id,dataset_id,sample_id,target_model_id,input_text,target,base_extracted_result,target_extracted_result,base_raw_response,target_raw_response,base_typed_score,target_typed_score,outcome,regression_kind,base_time_s,target_time_s,base_extraction_status,target_extraction_status,base_validation_status,target_validation_status,base_failure_reason,target_failure_reason,base_parse_status,target_parse_status,code_language,code_entry_point"))
        #expect(samplesCSV.contains("eval-compare-1,mbpp,mbpp.dev.v1,sample-1,melix-dev-text-lora-a,Write solve(n) that returns n,solve,\"def solve(n):"))
        #expect(samplesCSV.contains("parsed_code_fallback,parsed_code_fallback"))
        #expect(samplesCSV.contains("python,solve,compiled,compiled,ok,ok,ok,ok,failed,passed,1,2,2,2,assertion failed,"))
        #expect(samplesJSONL.contains("\"target_model_id\":\"melix-dev-text-lora-a\""))
        #expect(samplesJSONL.contains("\"base_code_failure_detail\":\"assertion failed\""))
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

    @Test("eval compare export commands fail when the requested job has no rows")
    func evalCompareExportCommandsFailForMissingJob() async throws {
        let client = StubControlPlaneXPCClient()
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))

        do {
            _ = try await MelixCLIRunner(client: client).run(
                .evalCompareExportSummaryCSV(.init(jobID: "eval-compare-missing", outputPath: "/tmp/eval-compare-missing.csv"))
            )
            Issue.record("Expected eval compare export-summary-csv to fail when the job is missing.")
        } catch let error as MelixCLIError {
            #expect(error == .runtime("No evaluation compare summary rows were found for job eval-compare-missing."))
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
        #expect(doctor.markdown.isEmpty)
        #expect(doctor.findings.isEmpty)
        #expect(cancelled == false)
        #expect(parseJSONObject("not-json") == nil)
        #expect(parseJSONObject(#"{"ok":true}"#)?["ok"] as? Bool == true)
    }
}

@Suite("Phase 8 LoRA CLI Smoke", .serialized)
struct Phase8LoRACLISmokeTests {
    @Test("phase 8 lora cli smoke emits canonical acceptance evidence")
    func phase8LoRACLISmokeEmitsCanonicalAcceptanceEvidence() async throws {
        let baseModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let derivedModelID = "melix-qwen35-acceptance"
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-phase8-lora-cli-smoke-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        let client = StubControlPlaneXPCClient()
        await client.setServerSnapshot(makeServerSnapshot(models: [
            makeModelSummary(id: baseModelID, kind: "text"),
            makeModelSummary(id: derivedModelID, kind: "text"),
        ]))
        await client.setExportResult(.init(exportBundleJSON: makeBenchmarkExportBundleJSON()))
        let runner = MelixCLIRunner(client: client)

        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/melix/train_lora/train-job-1")
        )
        let trainOutput = try await runSmokeCLICommand(
            [
                "lora", "train",
                "--model-id", baseModelID,
                "--hf-dataset-path", "HuggingFaceH4/ultrachat_200k",
                "--hf-train-split", "train_sft",
                "--chat-feature", "messages",
                "--adapter-name", "qwen35-acceptance",
                "--training-mode", "qlora",
                "--derived-model-alias", derivedModelID,
                "--json",
            ],
            runner: runner
        )
        let trainPayload = try #require(parseJSONObject(trainOutput))
        let trainCall = try #require(await client.lastModelOperationCall)

        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/melix/activate_adapter/activate-job-1")
        )
        let activateOutput = try await runSmokeCLICommand(
            [
                "lora", "activate",
                "--model-id", baseModelID,
                "--adapter-path", "/tmp/melix/train_lora/train-job-1/train_lora.adapter.json",
                "--activation-mode", "adapter_backed_runtime",
                "--alias", derivedModelID,
                "--json",
            ],
            runner: runner
        )
        let activatePayload = try #require(parseJSONObject(activateOutput))
        let activateCall = try #require(await client.lastModelOperationCall)

        await client.setEvaluationResults([
            makeEvaluationCompareResult(
                jobID: "eval-compare-1",
                baseSuiteID: "mmlu",
                datasetID: "mmlu.dev.v1",
                targets: [(derivedModelID, 0.625)]
            ),
        ])
        let compareOutput = try await runSmokeCLICommand(
            [
                "eval", "compare",
                "--model-id", baseModelID,
                "--target-model-id", derivedModelID,
                "--suite", "mmlu",
                "--sample-size", "6",
                "--batch-factor", "2",
                "--few-shot", "1",
                "--seed", "9",
                "--scoring-mode", "multiple_choice_accuracy",
                "--code-exec-policy", "sandboxed",
                "--json",
            ],
            runner: runner
        )
        let comparePayload = try #require(parseJSONArray(compareOutput))
        let compareEntry = try #require(comparePayload.first as? [String: Any])
        let compareJob = try #require(compareEntry["job"] as? [String: Any])
        let compareRequest = try #require((await client.evaluationRequests).last)

        let summaryURL = root.appendingPathComponent("eval-1-summary.csv")
        let exportOutput = try await runSmokeCLICommand(
            [
                "eval", "export-summary-csv",
                "--job-id", "eval-1",
                "--output", summaryURL.path,
                "--json",
            ],
            runner: runner
        )
        let exportPayload = try #require(parseJSONObject(exportOutput))
        let exportCSV = try String(contentsOf: summaryURL, encoding: .utf8)

        await client.setModelOperationResult(
            makeModelOperationResult(outputPath: "/tmp/melix/remove_derived_model/remove-job-1")
        )
        let removeOutput = try await runSmokeCLICommand(
            [
                "lora", "remove-derived",
                "--model-id", baseModelID,
                "--derived-model-id", derivedModelID,
                "--json",
            ],
            runner: runner
        )
        let removePayload = try #require(parseJSONObject(removeOutput))
        let removeCall = try #require(await client.lastModelOperationCall)

        let negativePayload: [String: String] = [
            "train_missing_adapter_name": try captureSmokeCLIError(
                ["lora", "train", "--model-id", baseModelID, "--dataset-uri", "datasets/melix-dev"]
            ),
            "activate_missing_adapter_path": try captureSmokeCLIError(
                ["lora", "activate", "--model-id", baseModelID]
            ),
            "compare_missing_target": try captureSmokeCLIError(
                ["eval", "compare", "--model-id", baseModelID]
            ),
            "export_missing_job": try await captureSmokeRunnerError(
                [
                    "eval", "export-summary-csv",
                    "--job-id", "eval-missing",
                    "--output", root.appendingPathComponent("eval-missing.csv").path,
                ],
                runner: runner
            ),
            "remove_missing_target": try captureSmokeCLIError(
                ["lora", "remove-derived", "--model-id", baseModelID]
            ),
        ]

        let positiveTrain: [String: Any] = [
            "job_id": trainPayload["job_id"] as? String ?? "train-job-1",
            "output_path": trainPayload["output_path"] as? String ?? "",
            "training_mode": trainCall.ext["training_mode"] ?? "",
        ]
        let positiveActivate: [String: Any] = [
            "job_id": activatePayload["job_id"] as? String ?? "activate-job-1",
            "output_path": activatePayload["output_path"] as? String ?? "",
            "activation_mode": activateCall.ext["activation_mode"] ?? "",
        ]
        let positiveCompare: [String: Any] = [
            "job_id": compareJob["job_id"] as? String ?? "",
            "target_model_ids": [derivedModelID],
            "metric": "eval.compare.win_rate",
            "compare_mode": compareRequest.parameters["compare_mode"] ?? "",
        ]
        let positiveExport: [String: Any] = [
            "job_id": exportPayload["job_id"] as? String ?? "",
            "output_path": summaryURL.path,
            "row_count": exportPayload["row_count"] as? Int ?? 0,
        ]
        let positiveRemove: [String: Any] = [
            "job_id": removePayload["job_id"] as? String ?? "remove-job-1",
            "output_path": removePayload["output_path"] as? String ?? "",
            "derived_model_id": removeCall.ext["derived_model_id"] ?? "",
        ]
        let positivePayload: [String: Any] = [
            "train": positiveTrain,
            "activate": positiveActivate,
            "compare": positiveCompare,
            "export": positiveExport,
            "remove_derived": positiveRemove,
        ]
        let payload: [String: Any] = [
            "model_id": baseModelID,
            "positive": positivePayload,
            "negative": negativePayload,
        ]
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        print("PHASE8_LORA_CLI_SMOKE=\(String(decoding: data, as: UTF8.self))")

        #expect(trainCall.operation == "train_lora")
        #expect(trainCall.ext["training_mode"] == "qlora")
        #expect(activateCall.operation == "activate_adapter")
        #expect(activateCall.ext["activation_mode"] == "adapter_backed_runtime")
        #expect(compareRequest.parameters["compare_target_model_ids"] == derivedModelID)
        #expect(exportPayload["row_count"] as? Int == 1)
        #expect(exportCSV.contains("eval-1"))
        #expect(removeCall.operation == "remove_derived_model")
        #expect(removeCall.ext["derived_model_id"] == derivedModelID)
        #expect(negativePayload["export_missing_job"] == "No evaluation rows were found for job eval-missing.")
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

private actor RecordingCLICommandExecutor {
    private let responses: [String]
    private var responseIndex = 0
    private(set) var commands: [[String]] = []

    init(responses: [String]) {
        self.responses = responses
    }

    func run(_ arguments: [String]) async throws -> String {
        commands.append(arguments)
        guard responseIndex < responses.count else {
            throw MelixCLIError.runtime("No subprocess response was configured for \(arguments.joined(separator: " ")).")
        }
        let response = responses[responseIndex]
        responseIndex += 1
        return response
    }
}

private func runSmokeCLICommand(
    _ arguments: [String],
    runner: MelixCLIRunner
) async throws -> String {
    let command = try MelixCLIParser.parse(arguments)
    return try await runner.run(command)
}

private func captureSmokeCLIError(_ arguments: [String]) throws -> String {
    do {
        _ = try MelixCLIParser.parse(arguments)
        Issue.record("Expected parser failure for arguments: \(arguments)")
    } catch let error as MelixCLIError {
        return error.localizedDescription
    }
    return ""
}

private func captureSmokeRunnerError(
    _ arguments: [String],
    runner: MelixCLIRunner
) async throws -> String {
    do {
        _ = try await runSmokeCLICommand(arguments, runner: runner)
        Issue.record("Expected runner failure for arguments: \(arguments)")
    } catch let error as MelixCLIError {
        return error.localizedDescription
    }
    return ""
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
        let outputDir: String
        let quantProfileID: String
        let weightQuant: String
        let kvQuant: String
        let ext: [String: String]
    }

    struct GatewayConfigApplyCall: Sendable, Equatable {
        let serverSessionID: String
        let host: String
        let port: Int
        let servedModelID: String
        let rateLimitPerMinute: Int
        let timeoutSeconds: Int
    }

    struct ServingDefaultsApplyCall: Sendable, Equatable {
        let serverSessionID: String
        let temperature: Double
        let topP: Double
        let maxTokens: Int
        let streamIntervalTokens: Int
        let maxConcurrentRequests: Int
        let concurrentProcessingEnabled: Bool
        let prefillBatchSize: Int
        let completionBatchSize: Int
        let accelerationMode: Melix_Controlplane_V1_AccelerationMode
        let draftModelID: String
        let numDraftTokens: Int
    }

    private(set) var lastServerAction: ServerAction?
    private(set) var lastIdlePolicyCall: IdlePolicyCall?
    private(set) var lastModelOperationCall: ModelOperationCall?
    private(set) var lastChatRequest: ControlPlaneChatRequest?
    private(set) var lastGatewayConfigApplyRequest: GatewayConfigApplyCall?
    private(set) var lastServingDefaultsApplyRequest: ServingDefaultsApplyCall?
    private(set) var lastBenchRequest: ControlPlaneBenchRequest?
    private(set) var lastBenchMatrixRequest: ControlPlaneBenchMatrixRequest?
    private(set) var evaluationRequests: [ControlPlaneEvaluationRequest] = []
    private(set) var loadedModelIDs: [String] = []

    private var snapshot = makeServerSnapshot(models: [makeModelSummary(id: "melix-dev-text", kind: "text")])
    private var modelOperationResult = makeModelOperationResult()
    private var modelOperationResultsByOperation: [String: Melix_Controlplane_V1_ModelOperationResult] = [:]
    private(set) var modelOperationCalls: [ModelOperationCall] = []
    private var benchResult = ControlPlaneBenchResult(reportPath: "", reportMarkdown: "", metrics: [:])
    private var benchMatrixResult = ControlPlaneBenchMatrixResult(
        job: makeBenchmarkMatrixJobSummary(jobID: "", modelID: "", taskKind: "", sourceRepo: ""),
        summaryRows: []
    )
    private var hubSearchResult = Melix_Controlplane_V1_HubSearchResult()
    private var hubModelCard = Melix_Controlplane_V1_HubModelCard()
    private var doctorReport = makeDoctorReport()
    private var evaluationResultsQueue: [ControlPlaneEvaluationResult] = []
    private var exportResult = ControlPlaneExportResult(exportBundleJSON: #"{"export_schema_version":"melix.benchmark_export.v1","benchmark_jobs":[],"benchmark_results":[]}"#)
    private var modelInfoByID: [String: Melix_Controlplane_V1_ModelInfo] = [:]
    private var modelOperationError: Error?
    private var chatRequestID = "stub-chat"
    private var chatModelID = "melix-dev-text"
    private var chatEvents: [ControlPlaneChatStreamEvent] = []

    func setServerSnapshot(_ snapshot: Melix_Controlplane_V1_ServerSnapshot) {
        self.snapshot = snapshot
    }

    func setModelOperationResult(_ result: Melix_Controlplane_V1_ModelOperationResult) {
        self.modelOperationResult = result
    }

    func setModelOperationResult(
        _ result: Melix_Controlplane_V1_ModelOperationResult,
        forOperation operation: String
    ) {
        modelOperationResultsByOperation[operation] = result
    }

    func setModelOperationError(_ error: Error?) {
        self.modelOperationError = error
    }

    func setBenchResult(_ result: ControlPlaneBenchResult) {
        self.benchResult = result
    }

    func setBenchMatrixResult(_ result: ControlPlaneBenchMatrixResult) {
        self.benchMatrixResult = result
    }

    func setHubSearchResult(_ result: Melix_Controlplane_V1_HubSearchResult) {
        self.hubSearchResult = result
    }

    func setHubModelCard(_ card: Melix_Controlplane_V1_HubModelCard) {
        self.hubModelCard = card
    }

    func setDoctorReport(_ report: Melix_Controlplane_V1_DoctorReport) {
        doctorReport = report
    }

    func setEvaluationResults(_ results: [ControlPlaneEvaluationResult]) {
        self.evaluationResultsQueue = results
    }

    func setExportResult(_ result: ControlPlaneExportResult) {
        self.exportResult = result
    }

    func setModelInfo(modelID: String, info: Melix_Controlplane_V1_ModelInfo) {
        modelInfoByID[modelID] = info
    }

    func setChatExecution(
        requestID: String,
        modelID: String,
        events: [ControlPlaneChatStreamEvent]
    ) {
        self.chatRequestID = requestID
        self.chatModelID = modelID
        self.chatEvents = events
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
        lastChatRequest = request
        let events = chatEvents
        return ControlPlaneChatExecution(
            requestID: chatRequestID,
            modelID: chatModelID,
            stream: AsyncThrowingStream { continuation in
                for event in events {
                    continuation.yield(event)
                }
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
        modelInfoByID[modelID] ?? Melix_Controlplane_V1_ModelInfo()
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
        if let modelOperationError {
            throw modelOperationError
        }
        let call = ModelOperationCall(
            modelID: modelID,
            operation: operation,
            outputDir: outputDir,
            quantProfileID: quantProfileID,
            weightQuant: weightQuant,
            kvQuant: kvQuant,
            ext: ext
        )
        lastModelOperationCall = call
        modelOperationCalls.append(call)
        if let perOperation = modelOperationResultsByOperation[operation] {
            return perOperation
        }
        return modelOperationResult
    }

    func searchHubModels(
        query: String,
        pageSize: UInt32,
        cursor: String,
        mlxOnly: Bool
    ) async throws -> Melix_Controlplane_V1_HubSearchResult {
        _ = query
        _ = pageSize
        _ = cursor
        _ = mlxOnly
        return hubSearchResult
    }

    func getHubModelCard(repoID: String) async throws -> Melix_Controlplane_V1_HubModelCard {
        _ = repoID
        return hubModelCard
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

    func runDoctor() async throws -> Melix_Controlplane_V1_DoctorReport {
        doctorReport
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

    func applyServerSessionGatewayConfig(
        serverSessionID: String,
        host: String,
        port: Int,
        servedModelID: String,
        rateLimitPerMinute: Int,
        timeoutSeconds: Int
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastGatewayConfigApplyRequest = GatewayConfigApplyCall(
            serverSessionID: serverSessionID,
            host: host,
            port: port,
            servedModelID: servedModelID,
            rateLimitPerMinute: rateLimitPerMinute,
            timeoutSeconds: timeoutSeconds
        )
        return snapshot
    }

    func applyServerSessionServingDefaults(
        serverSessionID: String,
        temperature: Double,
        topP: Double,
        maxTokens: Int,
        streamIntervalTokens: Int,
        maxConcurrentRequests: Int,
        concurrentProcessingEnabled: Bool,
        prefillBatchSize: Int,
        completionBatchSize: Int,
        accelerationMode: Melix_Controlplane_V1_AccelerationMode,
        draftModelID: String,
        numDraftTokens: Int
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot {
        lastServingDefaultsApplyRequest = ServingDefaultsApplyCall(
            serverSessionID: serverSessionID,
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            streamIntervalTokens: streamIntervalTokens,
            maxConcurrentRequests: maxConcurrentRequests,
            concurrentProcessingEnabled: concurrentProcessingEnabled,
            prefillBatchSize: prefillBatchSize,
            completionBatchSize: completionBatchSize,
            accelerationMode: accelerationMode,
            draftModelID: draftModelID,
            numDraftTokens: numDraftTokens
        )
        return snapshot
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
    kind: String,
    runtimeMode: String = "",
    activationMode: String = ""
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = id
    model.kind = kind
    model.runtimeMode = runtimeMode
    if !activationMode.isEmpty {
        model.settings.ext["melix.activation_mode"] = activationMode
    }
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

private func makeDoctorReport(
    markdown: String = "",
    healthStatus: Melix_Controlplane_V1_DoctorHealthStatus = .unspecified,
    findings: [(code: String, severity: Melix_Controlplane_V1_DoctorHealthStatus, summary: String, detail: String)] = []
) -> Melix_Controlplane_V1_DoctorReport {
    var report = Melix_Controlplane_V1_DoctorReport()
    report.markdown = markdown
    report.healthStatus = healthStatus
    report.findings = findings.map { finding in
        var item = Melix_Controlplane_V1_DoctorFinding()
        item.code = finding.code
        item.severity = finding.severity
        item.summary = finding.summary
        item.detail = finding.detail
        return item
    }
    return report
}

private func makeExperimentsRegistryManifestWithoutBestLoss() -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "adapters": [],
      "derived_models": [],
      "experiment_groups": [
        {
          "group_id": "cold-start",
          "title": "Cold Start",
          "adapter_name": "cold-start-adapter",
          "source_model": "melix-dev-text",
          "run_count": 1,
          "latest_preset_title": "Debug Fast",
          "resume_ready_run_ids": [],
          "checkpoint_lineage": [
            {"run_id": "model-ops-9999", "checkpoint_count": 0, "resume_ready": false}
          ]
        }
      ]
    }
    """#
}

private func makeExperimentsRegistryManifest(
    bestManifestPath: String = "/tmp/melix-train-lora/model-ops-0012/train_lora.adapter.json"
) -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "adapters": [],
      "derived_models": [],
      "experiment_groups": [
        {
          "group_id": "nightly-qwen35",
          "title": "Nightly Qwen35",
          "adapter_name": "nightly-qwen35",
          "source_model": "melix-dev-text",
          "run_count": 3,
          "latest_run_id": "model-ops-0012",
          "latest_status": "activated",
          "latest_dataset_uri": "/tmp/datasets/nightly.jsonl",
          "latest_preset_id": "balanced_adapter",
          "latest_preset_title": "Balanced Adapter",
          "latest_tokens_per_second": 128.5,
          "latest_peak_memory_gb": 5.25,
          "latest_checkpoint_count": 5,
          "latest_resume_ready": true,
          "resume_ready_run_ids": ["model-ops-0012", "model-ops-0009"],
          "checkpoint_lineage": [
            { "run_id": "model-ops-0012", "checkpoint_count": 5, "resume_ready": true },
            { "run_id": "model-ops-0009", "checkpoint_count": 3, "resume_ready": true },
            { "run_id": "model-ops-0007", "checkpoint_count": 1, "resume_ready": false }
          ],
          "best_run_id": "model-ops-0012",
          "best_loss": 0.3287,
          "recommended_manifest_path": "\#(bestManifestPath)",
          "best_known_adapter": {
            "run_id": "model-ops-0012",
            "manifest_path": "\#(bestManifestPath)",
            "adapter_name": "nightly-qwen35",
            "checkpoint_count": 5,
            "latest_checkpoint_path": "/tmp/melix-train-lora/model-ops-0012/checkpoint",
            "resume_ready": true,
            "loss_best": 0.3287
          }
        }
      ]
    }
    """#
}

private func parseJSONObject(_ text: String) -> [String: Any]? {
    guard let data = text.data(using: .utf8) else {
        return nil
    }
    return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
}

private func writeJSONObjectForTest(_ object: [String: Any], to url: URL) throws {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: url)
}

private func parseJSONArray(_ text: String) -> [Any]? {
    guard let data = text.data(using: .utf8) else {
        return nil
    }
    return (try? JSONSerialization.jsonObject(with: data)) as? [Any]
}

private func parseJSONFile(_ path: String) throws -> [String: Any]? {
    let data = try Data(contentsOf: URL(fileURLWithPath: path))
    return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
}

private struct NonMelixPipelineTestError: Error, CustomStringConvertible {
    let message: String

    var description: String {
        message
    }
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
          "effect_threshold": 0.1,
          "verdict": "improvement",
          "bootstrap_lower_bound": 0.12,
          "bootstrap_upper_bound": 0.41,
          "analytical_lower_bound": 0.1,
          "analytical_upper_bound": 0.38,
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
          "task_kind": "text-generation",
          "question": "2+2?",
          "expected": "4",
          "predicted": "4",
          "raw_response": "4",
          "correct": true,
          "time_s": 0.01,
          "parse_status": "parsed",
          "input_modalities": ["text"],
          "media_references": [],
          "code_language": "python",
          "code_entry_point": "solve",
          "code_compile_status": "compiled",
          "code_runtime_status": "ok",
          "code_timeout_status": "ok",
          "code_test_status": "passed",
          "code_tests_passed": 2,
          "code_tests_total": 2,
          "code_failure_detail": "",
          "category_label": "math",
          "subject_label": "algebra"
        }
      ],
      "evaluation_compare_jobs": [
        {
          "schema_version": "melix.evaluation_compare_job.v1",
          "job_id": "eval-compare-1",
          "base_model_id": "melix-dev-text",
          "target_model_ids": ["melix-dev-text-lora-a"],
          "task_kind": "text-generation",
          "source_repo": "openai_humaneval",
          "suite_id": "mbpp",
          "dataset_id": "mbpp.dev.v1",
          "sample_size": 2,
          "scoring_mode": "pass_at_1",
          "parameters": {
            "compare_mode": "base_vs_targets",
            "compare_target_model_ids": "melix-dev-text-lora-a"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/evaluation/runs/eval-compare-1",
          "created_at_unix_ms": 1712500000000,
          "updated_at_unix_ms": 1712500005000
        }
      ],
      "evaluation_compare_summary_rows": [
        {
          "schema_version": "melix.evaluation_compare_summary.v1",
          "job_id": "eval-compare-1",
          "base_model_id": "melix-dev-text",
          "target_model_id": "melix-dev-text-lora-a",
          "suite_id": "mbpp",
          "dataset_id": "mbpp.dev.v1",
          "sample_size": 2,
          "scoring_mode": "pass_at_1",
          "win_count": 1,
          "loss_count": 0,
          "tie_count": 1,
          "regression_count": 0,
          "base_accuracy": 0.5,
          "target_accuracy": 1.0,
          "delta_accuracy": 0.5,
          "duration_seconds": 1.75,
          "metrics": [
            {"name": "eval.compare.win_count", "value": 1.0, "unit": "count"},
            {"name": "eval.compare.delta_accuracy", "value": 0.5, "unit": "ratio"}
          ],
          "report_path": "/tmp/melix/evaluation/runs/eval-compare-1/evaluation-compare-report.md"
        }
      ],
      "evaluation_compare_samples": [
        {
          "schema_version": "melix.evaluation_compare_sample.v1",
          "job_id": "eval-compare-1",
          "suite_id": "mbpp",
          "dataset_id": "mbpp.dev.v1",
          "sample_id": "sample-1",
          "target_model_id": "melix-dev-text-lora-a",
          "question": "Write solve(n) that returns n",
          "expected": "solve",
          "base_predicted": "def solve(n):\\n    return 0",
          "target_predicted": "def solve(n):\\n    return n",
          "base_raw_response": "def solve(n):\\n    return 0",
          "target_raw_response": "def solve(n):\\n    return n",
          "base_correct": false,
          "target_correct": true,
          "outcome": "win",
          "regression": false,
          "base_time_s": 0.11,
          "target_time_s": 0.09,
          "base_parse_status": "parsed_code_fallback",
          "target_parse_status": "parsed_code_fallback",
          "code_language": "python",
          "code_entry_point": "solve",
          "base_code_compile_status": "compiled",
          "target_code_compile_status": "compiled",
          "base_code_runtime_status": "ok",
          "target_code_runtime_status": "ok",
          "base_code_timeout_status": "ok",
          "target_code_timeout_status": "ok",
          "base_code_test_status": "failed",
          "target_code_test_status": "passed",
          "base_code_tests_passed": 1,
          "target_code_tests_passed": 2,
          "base_code_tests_total": 2,
          "target_code_tests_total": 2,
          "base_code_failure_detail": "assertion failed",
          "target_code_failure_detail": "",
          "category_label": "math",
          "subject_label": "algebra"
        }
      ]
    }
    """
}

private func makeEvaluationCompareExportBundleJSON() -> String {
    """
    {
      "export_schema_version": "melix.benchmark_export.v1",
      "evaluation_jobs": [
        {
          "schema_version": "melix.evaluation_job.v1",
          "job_id": "eval-compare-2",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "scoring_mode": "multiple_choice_accuracy",
          "parameters": {
            "compare_mode": "base_vs_targets",
            "compare_target_model_ids": "melix-dev-text-lora-a,melix-dev-text-lora-b"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/evaluation/runs/eval-compare-2",
          "created_at_unix_ms": 1712400000000,
          "updated_at_unix_ms": 1712400005000
        }
      ],
      "evaluation_summary_rows": [
        {
          "job_id": "eval-compare-2",
          "model_id": "melix-dev-text-lora-a",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "score_name": "eval.compare.delta_accuracy",
          "score_value": 0.25,
          "correct_count": 7,
          "incorrect_count": 1,
          "effect_threshold": 0.1,
          "verdict": "improvement",
          "bootstrap_lower_bound": 0.12,
          "bootstrap_upper_bound": 0.41,
          "analytical_lower_bound": 0.1,
          "analytical_upper_bound": 0.38,
          "duration_seconds": 12.5,
          "created_at_unix_ms": 1712400000000
        },
        {
          "job_id": "eval-compare-2",
          "model_id": "melix-dev-text-lora-b",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "score_name": "eval.compare.delta_accuracy",
          "score_value": -0.125,
          "correct_count": 3,
          "incorrect_count": 5,
          "effect_threshold": 0.1,
          "verdict": "inconclusive",
          "bootstrap_lower_bound": -0.21,
          "bootstrap_upper_bound": 0.02,
          "analytical_lower_bound": -0.18,
          "analytical_upper_bound": 0.01,
          "duration_seconds": 12.5,
          "created_at_unix_ms": 1712400000000
        }
      ]
    }
    """
}

private func makeEvaluationCompareSparseExportBundleJSON() -> String {
    """
    {
      "export_schema_version": "melix.benchmark_export.v1",
      "evaluation_jobs": [
        {
          "schema_version": "melix.evaluation_job.v1",
          "job_id": "eval-compare-2",
          "model_id": "melix-dev-text",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "scoring_mode": "multiple_choice_accuracy",
          "parameters": {
            "compare_mode": "base_vs_targets",
            "compare_target_model_ids": "melix-dev-text-lora-a"
          },
          "status": "completed",
          "output_dir": "/tmp/melix/evaluation/runs/eval-compare-2",
          "created_at_unix_ms": 1712400000000,
          "updated_at_unix_ms": 1712400005000
        }
      ],
      "evaluation_summary_rows": [
        {
          "job_id": "eval-compare-2",
          "model_id": "",
          "task_kind": "text-generation",
          "source_repo": "HuggingFaceH4/ultrachat_200k",
          "suite_id": "mmlu",
          "dataset_id": "mmlu.dev.v1",
          "sample_size": 8,
          "score_name": "eval.compare.delta_accuracy",
          "score_value": -0.125,
          "correct_count": 3,
          "incorrect_count": 5,
          "verdict": "inconclusive",
          "duration_seconds": 12.5,
          "created_at_unix_ms": 1712400000000
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

private func makeEvaluationCompareResult(
    jobID: String,
    baseSuiteID: String,
    datasetID: String,
    targets: [(modelID: String, metricValue: Double)],
    status: String = "completed"
) -> ControlPlaneEvaluationResult {
    var job = Melix_Controlplane_V1_EvaluationJobSummary()
    job.schemaVersion = "melix.evaluation_job.v1"
    job.jobID = jobID
    job.modelID = "melix-dev-text"
    job.taskKind = "text-generation"
    job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
    job.suiteID = baseSuiteID
    job.datasetID = datasetID
    job.sampleSize = 8
    job.scoringMode = "multiple_choice_accuracy"
    job.status = status
    job.outputDir = "/tmp/melix/evaluation/runs/\(jobID)"
    job.createdAtUnixMs = 1712400000000
    job.updatedAtUnixMs = 1712400005000

    let results = targets.map { target in
        var metric = Melix_Controlplane_V1_BenchmarkMetricValue()
        metric.name = "eval.compare.win_rate"
        metric.value = target.metricValue
        metric.unit = "ratio"

        var result = Melix_Controlplane_V1_EvaluationResultSummary()
        result.schemaVersion = "melix.evaluation_result.v1"
        result.jobID = jobID
        result.suiteID = "\(baseSuiteID):\(target.modelID)"
        result.datasetID = datasetID
        result.sampleSize = 8
        result.metrics = [metric]
        result.reportPath = "/tmp/melix/evaluation/runs/\(jobID)/\(target.modelID)-result.json"
        return result
    }

    return ControlPlaneEvaluationResult(job: job, results: results)
}
