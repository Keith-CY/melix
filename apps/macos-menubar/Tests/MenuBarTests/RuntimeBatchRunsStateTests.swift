import Foundation
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Runtime Batch Runs State")
struct RuntimeBatchRunsStateTests {
    @Test("batch run setup input state parses models and config validation messages")
    @MainActor
    func batchRunSetupInputStateParsesModelsAndConfigValidationMessages() {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())

        #expect(viewModel.batchRunSetupCanRequestPreflight == false)
        #expect(viewModel.batchRunSetupValidationMessages.contains { $0.message == "Add at least one model repository." })

        viewModel.updateBatchRunModelListText(
            """
            # smoke targets
            01 | mlx-community/Qwen3-8B
            mlx-community/Mistral-7B
            """
        )
        viewModel.updateBatchRunConfigText(
            """
            run_id: smoke-batch
            bench_batch_size: 2
            api_token: plain-secret
            unknown_key: value
            broken line
            """
        )

        #expect(viewModel.batchRunModelInputs.map(\.repoID) == [
            "mlx-community/Qwen3-8B",
            "mlx-community/Mistral-7B",
        ])
        #expect(viewModel.batchRunModelInputs.map(\.index) == ["01", "02"])
        #expect(viewModel.batchRunConfigEntries.map(\.key).prefix(2) == ["run_id", "bench_batch_size"])
        #expect(viewModel.batchRunSetupCanRequestPreflight == false)
        #expect(viewModel.batchRunSetupValidationMessages.contains { $0.message.contains("api_token") })
        #expect(viewModel.batchRunSetupValidationMessages.contains { $0.message.contains("unknown_key") })
        #expect(viewModel.batchRunSetupValidationMessages.contains { $0.message.contains("line 5") })

        viewModel.updateBatchRunConfigText(
            """
            run_id: smoke-batch
            bench_batch_size: 2
            preflight: true
            """
        )

        #expect(viewModel.batchRunSetupCanRequestPreflight == true)
        #expect(viewModel.batchRunSetupValidationMessages.allSatisfy { $0.severity != .error })
        #expect(viewModel.batchRunSetupSummaryText == "2 models • 3 config values")
    }

    @Test("batch run preflight action writes inputs dispatches dry-run command and selects report")
    @MainActor
    func batchRunPreflightActionWritesInputsDispatchesDryRunCommandAndSelectsReport() async throws {
        let runner = RecordingCLIWorkflowRunner()
        let preflightOutput = Self.batchPreflightOutput(modelListPath: "", configPath: "")
        await runner.configureHandler { command in
            guard case .batchRun(let options) = command else {
                return .failure(.unsupportedCommand(commandID: "unexpected", surface: .subprocess))
            }
            return .success(preflightOutput(options.modelListPath, options.configPath))
        }
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateBatchRunModelListText("01 | mlx-community/Qwen3-8B")
        viewModel.updateBatchRunConfigText(
            """
            run_id: smoke-batch
            bench_suite: latency
            """
        )

        await viewModel.requestBatchRunPreflight()

        let recordedCommands = await runner.snapshotRecordedCommands()
        let command = try #require(recordedCommands.first)
        guard case .batchRun(let options) = command else {
            Issue.record("expected batch.run command")
            return
        }
        #expect(options.preflight)
        #expect(options.dryRun)
        #expect(options.json)
        #expect(try String(contentsOfFile: options.modelListPath, encoding: .utf8) == "01 | mlx-community/Qwen3-8B\n")
        #expect(try String(contentsOfFile: options.configPath, encoding: .utf8).contains("bench_suite: latency"))
        #expect(viewModel.batchRunPreflightInProgress == false)
        #expect(viewModel.batchRunPreflightErrorMessage.isEmpty)
        #expect(viewModel.batchRunReports.count == 1)
        #expect(viewModel.selectedBatchRunReportID == viewModel.batchRunReports.first?.id)
        #expect(viewModel.selectedBatchRunReport?.runID == "smoke-batch")
        #expect(viewModel.selectedBatchRunReport?.preflightStatus == "ready")
        #expect(viewModel.selectedBatchRunReport?.checks.first?.name == "output_root")
        #expect(viewModel.selectedBatchRunReport?.effectiveConfigRows.contains {
            $0.title == "Output Root" && $0.detail == "/tmp/melix-batch-output"
        } == true)
        #expect(viewModel.selectedBatchRunReport?.effectiveConfigRows.contains {
            $0.title == "Benchmark" && $0.detail.contains("latency")
        } == true)
        #expect(viewModel.selectedBatchRunReport?.isolationSummaryRows.contains {
            $0.title == "Restart Stack Per Model" && $0.detail == "enabled"
        } == true)
        #expect(viewModel.selectedBatchRunReport?.isolationSummaryRows.contains {
            $0.title == "Force Clean After Runtime Failure" && $0.detail == "enabled"
        } == true)

        await viewModel.requestBatchRunPreflight()
        #expect(viewModel.batchRunReports.count == 1)
    }

    @Test("batch run preflight action blocks invalid input before CLI dispatch")
    @MainActor
    func batchRunPreflightActionBlocksInvalidInputBeforeCLIDispatch() async {
        let runner = RecordingCLIWorkflowRunner()
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateBatchRunModelListText("")
        viewModel.updateBatchRunConfigText("unknown_key: value")

        await viewModel.requestBatchRunPreflight()

        #expect(await runner.snapshotRecordedCommands().isEmpty)
        #expect(viewModel.batchRunPreflightInProgress == false)
        #expect(viewModel.batchRunPreflightErrorMessage == "Resolve batch input validation errors before running preflight.")
    }

    @Test("batch run preflight action surfaces missing runner and CLI failures")
    @MainActor
    func batchRunPreflightActionSurfacesMissingRunnerAndCLIFailures() async {
        let missingRunner = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        missingRunner.updateBatchRunModelListText("mlx-community/Qwen3-8B")

        await missingRunner.requestBatchRunPreflight()

        #expect(missingRunner.batchRunPreflightErrorMessage == "Batch Runs CLI runner is unavailable.")

        let failingRunner = RecordingCLIWorkflowRunner()
        await failingRunner.configureHandler { _ in
            .failure(
                .processFailed(
                    commandID: "batch.run",
                    surface: .subprocess,
                    exitCode: 2,
                    stderr: "preflight failed"
                )
            )
        }
        let failing = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: failingRunner)
        failing.updateBatchRunModelListText("mlx-community/Qwen3-8B")

        await failing.requestBatchRunPreflight()

        #expect(failing.batchRunPreflightInProgress == false)
        #expect(failing.batchRunPreflightErrorMessage.contains("preflight failed"))
    }

    @Test("batch run status action decodes manifest rows with partial failure attribution")
    @MainActor
    func batchRunStatusActionDecodesManifestRowsWithPartialFailureAttribution() async throws {
        let runner = RecordingCLIWorkflowRunner()
        let preflightOutput = Self.batchPreflightOutput(modelListPath: "", configPath: "")
        let statusOutput = Self.batchStatusOutput()
        await runner.configureHandler { command in
            switch command {
            case .batchRun(let options):
                return .success(preflightOutput(options.modelListPath, options.configPath))
            case .batchStatus:
                return .success(statusOutput)
            default:
                return .failure(.unsupportedCommand(commandID: "unexpected", surface: .subprocess))
            }
        }
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateBatchRunModelListText("01 | mlx-community/Qwen3-8B")
        viewModel.updateBatchRunConfigText("run_id: smoke-batch")

        await viewModel.requestBatchRunPreflight()
        await viewModel.requestBatchRunStatus()

        let recordedCommands = await runner.snapshotRecordedCommands()
        #expect(recordedCommands.count == 2)
        let statusCommand = try #require(recordedCommands.last)
        guard case .batchStatus(let options) = statusCommand else {
            Issue.record("expected batch.status command")
            return
        }
        #expect(options.json)
        #expect(options.runID == "smoke-batch")
        #expect(options.outputRoot == "/tmp/melix-batch-output")
        #expect(options.tempRoot == "/tmp/melix-batch-temp")
        #expect(viewModel.batchRunStatusInProgress == false)
        #expect(viewModel.batchRunStatusErrorMessage.isEmpty)

        let report = try #require(viewModel.selectedBatchRunReport)
        #expect(report.statusSummary?.status == "partial_success")
        #expect(report.statusSummary?.countsText == "2 succeeded, 1 partial, 1 failed, 0 running, 0 planned / 4 total")
        #expect(report.statusSummary?.manifestPath == "/tmp/melix-batch-temp/manifest.jsonl")
        #expect(report.manifestStatusRows.map(\.status) == [
            "succeeded",
            "partial_success",
            "failed",
            "succeeded",
        ])
        let partial = try #require(report.manifestStatusRows.first { $0.modelIndex == "02" })
        #expect(partial.repoID == "mlx-community/Mistral-7B")
        #expect(partial.failureAttribution == "artifact_export • retry_same_model")
        let failed = try #require(report.manifestStatusRows.first { $0.modelIndex == "03" })
        #expect(failed.failureAttribution == "model_load • operator_action_required")
    }

    @Test("batch run status action surfaces missing selection and CLI failures")
    @MainActor
    func batchRunStatusActionSurfacesMissingSelectionAndCLIFailures() async {
        let missingSelection = RuntimeViewModel(client: FakeControlPlaneXPCClient())

        await missingSelection.requestBatchRunStatus()

        #expect(missingSelection.batchRunStatusInProgress == false)
        #expect(missingSelection.batchRunStatusErrorMessage == "Run or select a batch report before refreshing status.")

        let runner = RecordingCLIWorkflowRunner()
        let preflightOutput = Self.batchPreflightOutput(modelListPath: "", configPath: "")
        await runner.configureHandler { command in
            switch command {
            case .batchRun(let options):
                return .success(preflightOutput(options.modelListPath, options.configPath))
            case .batchStatus:
                return .failure(
                    .processFailed(
                        commandID: "batch.status",
                        surface: .subprocess,
                        exitCode: 2,
                        stderr: "status manifest missing"
                    )
                )
            default:
                return .failure(.unsupportedCommand(commandID: "unexpected", surface: .subprocess))
            }
        }
        let failing = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        failing.updateBatchRunModelListText("01 | mlx-community/Qwen3-8B")
        failing.updateBatchRunConfigText("run_id: smoke-batch")

        await failing.requestBatchRunPreflight()
        await failing.requestBatchRunStatus()

        #expect(failing.batchRunStatusInProgress == false)
        #expect(failing.batchRunStatusErrorMessage.contains("status manifest missing"))
    }

    @Test("batch run report decoder renders effective config fallback rows")
    func batchRunReportDecoderRendersEffectiveConfigFallbackRows() throws {
        let intPortReport = try Self.decodedBatchReport { payload in
            payload["http_port"] = 12435
            payload.removeValue(forKey: "melix_home")
            payload.removeValue(forKey: "runtime_dir")
            payload.removeValue(forKey: "service_instance_name")
            payload.removeValue(forKey: "continue_on_failure")
            payload.removeValue(forKey: "isolation_policy")
            payload["restart_stack_per_model"] = false
        }

        #expect(intPortReport.effectiveConfigRows.contains {
            $0.title == "HTTP Port" && $0.detail == "12435"
        })
        #expect(intPortReport.effectiveConfigRows.contains { $0.title == "MELIX_HOME" } == false)
        #expect(intPortReport.effectiveConfigRows.contains { $0.title == "Continue On Failure" } == false)
        #expect(intPortReport.isolationSummaryRows.contains {
            $0.title == "Restart Stack Per Model" && $0.detail == "disabled"
        })
        #expect(intPortReport.isolationSummaryRows.contains {
            $0.title == "Force Clean After Runtime Failure"
        } == false)

        let boolPortReport = try Self.decodedBatchReport { payload in
            payload["http_port"] = true
        }
        #expect(boolPortReport.effectiveConfigRows.contains {
            $0.title == "HTTP Port" && $0.detail == "true"
        })

        let unsupportedPortReport = try Self.decodedBatchReport { payload in
            payload["http_port"] = ["unexpected": "object"]
        }
        #expect(unsupportedPortReport.effectiveConfigRows.contains { $0.title == "HTTP Port" } == false)
    }

    private static func batchPreflightPayload(modelListPath: String, configPath: String) -> [String: Any] {
        [
            "schema_version": "melix.batch.effective_config.v1",
            "run_id": "smoke-batch",
            "model_list": modelListPath,
            "config_path": configPath,
            "output_root": "/tmp/melix-batch-output",
            "temp_root": "/tmp/melix-batch-temp",
            "melix_home": "/tmp/melix-home",
            "runtime_dir": "/tmp/melix-runtime",
            "http_port": "12434",
            "service_instance_name": "window-ui",
            "selected_model_count": 1,
            "total_model_count": 1,
            "dry_run": true,
            "preflight": true,
            "continue_on_failure": true,
            "restart_stack_per_model": true,
            "preflight_report": "/tmp/melix-batch-output/preflight-report.json",
            "isolation_policy": [
                "schema_version": "melix.batch.isolation_policy.v1",
                "best_effort_unload_previous_model": true,
                "best_effort_unload_after_model": true,
                "restart_stack_per_model": true,
                "force_clean_stack_after_runtime_failure": true,
                "cleanup_failures_preserve_artifacts": true,
            ],
            "judge": [
                "remote_server_id": "judge-local",
                "model": "judge-model",
            ],
            "benchmark": [
                "suite": "latency",
                "context_length": 2048,
                "generation_length": 128,
                "batch_size": 2,
                "repeats": 1,
                "sample_size": 8,
                "batch_factor": 1,
            ],
            "evaluation": [
                "suite": "mt-bench",
                "dataset_id": "smoke",
                "scoring_mode": "exact",
                "sample_size": 8,
                "batch_factor": 1,
            ],
            "models": [
                [
                    "index": "01",
                    "repo_id": "mlx-community/Qwen3-8B",
                    "source_line": 1,
                    "slug": "01-mlx-community-qwen3-8b",
                ],
            ],
            "preflight_result": [
                "schema_version": "melix.batch.preflight_report.v1",
                "run_id": "smoke-batch",
                "status": "ready",
                "blocker_count": 0,
                "model_count": 1,
                "runtime": [
                    "repo_root": "/tmp/melix",
                    "melix_home": "/tmp/melix-home",
                    "runtime_dir": "/tmp/melix-runtime",
                    "http_port": "12434",
                    "service_instance_name": "window-ui",
                    "melix_cli": "/tmp/melix",
                ],
                "judge": [
                    "remote_server_id": "judge-local",
                    "model": "judge-model",
                ],
                "checks": [
                    [
                        "name": "output_root",
                        "status": "ready",
                        "detail": "output root writable",
                        "actionable": "",
                        "category": "filesystem",
                        "metadata": ["path": "/tmp/melix-batch-output"],
                    ],
                ],
            ],
        ]
    }

    private static func decodedBatchReport(
        customizing customize: (inout [String: Any]) -> Void
    ) throws -> RuntimeBatchRunReportState {
        var payload = batchPreflightPayload(modelListPath: "/tmp/models.txt", configPath: "/tmp/config.txt")
        customize(&payload)
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        return try RuntimeBatchRunReportDecoder.decodePreflightOutput(String(decoding: data, as: UTF8.self))
    }

    private static func batchPreflightOutput(
        modelListPath: String,
        configPath: String
    ) -> @Sendable (String, String) -> String {
        { runtimeModelListPath, runtimeConfigPath in
            let payload = batchPreflightPayload(
                modelListPath: runtimeModelListPath.isEmpty ? modelListPath : runtimeModelListPath,
                configPath: runtimeConfigPath.isEmpty ? configPath : runtimeConfigPath
            )
            let data = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
            return String(decoding: data, as: UTF8.self) + "\n"
        }
    }

    private static func batchStatusOutput() -> String {
        let data = try! JSONSerialization.data(withJSONObject: batchStatusPayload(), options: [.sortedKeys])
        return String(decoding: data, as: UTF8.self) + "\n"
    }

    private static func batchStatusPayload() -> [String: Any] {
        [
            "schema_version": "melix.batch.run_summary.v1",
            "run_id": "smoke-batch",
            "status": "partial_success",
            "total_models": 4,
            "succeeded_models": 2,
            "partial_success_models": 1,
            "failed_models": 1,
            "running_models": 0,
            "planned_models": 0,
            "temp_root": "/tmp/melix-batch-temp",
            "output_root": "/tmp/melix-batch-output",
            "manifest_path": "/tmp/melix-batch-temp/manifest.jsonl",
            "models": [
                [
                    "model_index": "01",
                    "repo_id": "mlx-community/Qwen3-8B",
                    "status": "succeeded",
                    "benchmark_job_id": "bench-01",
                    "evaluation_job_id": "eval-01",
                    "failure_category": "",
                    "recoverability": "",
                    "duration_seconds": 12.5,
                    "metric_fields": ["latency_ms": 42.0],
                ],
                [
                    "model_index": "02",
                    "repo_id": "mlx-community/Mistral-7B",
                    "status": "partial_success",
                    "benchmark_job_id": "bench-02",
                    "evaluation_job_id": "",
                    "failure_category": "artifact_export",
                    "recoverability": "retry_same_model",
                    "duration_seconds": 21.0,
                    "metric_fields": [:],
                ],
                [
                    "model_index": "03",
                    "repo_id": "mlx-community/Llama-3.2-3B",
                    "status": "failed",
                    "benchmark_job_id": "",
                    "evaluation_job_id": "",
                    "failure_category": "model_load",
                    "recoverability": "operator_action_required",
                    "duration_seconds": 3.25,
                    "metric_fields": [:],
                ],
                [
                    "model_index": "04",
                    "repo_id": "mlx-community/Phi-3.5",
                    "status": "succeeded",
                    "benchmark_job_id": "bench-04",
                    "evaluation_job_id": "eval-04",
                    "failure_category": "",
                    "recoverability": "",
                    "duration_seconds": 9.75,
                    "metric_fields": ["accuracy": 0.88],
                ],
            ],
        ]
    }
}
