import Foundation
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Runtime Jobs State")
struct RuntimeJobsStateTests {
    @Test("jobs list JSON decodes into desktop job summaries")
    func jobsListJSONDecodesIntoDesktopJobSummaries() throws {
        let data = Data("""
        [
          {
            "schema_version": "melix.job_summary.v1",
            "job_id": "bench-20260516-1027",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "started_at_unix_ms": 1778908032000,
            "updated_at_unix_ms": 1778908099000,
            "duration_ms": 67000,
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "suite_ids": ["smoke", "latency"],
            "dataset_id": "",
            "artifact_root": "/tmp/melix/bench/bench-20260516-1027",
            "record_path": "/tmp/melix/bench/bench-20260516-1027/run-record.json",
            "cancelable": true,
            "cancellation_requested": false
          },
          {
            "schema_version": "melix.job_summary.v1",
            "job_id": "model-ops-20260516-0941",
            "run_kind": "training",
            "operation": "train_lora",
            "status": "completed",
            "phase": "write_manifest",
            "started_at_unix_ms": "1778905261000",
            "updated_at_unix_ms": "1778905321000",
            "duration_ms": "60000",
            "model_id": "melix-dev-text",
            "task_kind": "train_lora",
            "suite_ids": [],
            "dataset_id": "synthetic/math",
            "artifact_root": "/tmp/melix/jobs/model-ops/train_lora/model-ops-20260516-0941",
            "record_path": "/tmp/melix/jobs/model-ops/train_lora/model-ops-20260516-0941/train_lora.adapter.json",
            "cancelable": false,
            "cancellation_requested": true
          }
        ]
        """.utf8)

        let jobs = try RuntimeJobsPayloadDecoder.decodeList(data)

        #expect(jobs.map(\.id) == ["bench-20260516-1027", "model-ops-20260516-0941"])
        #expect(jobs.first?.schemaVersion == "melix.job_summary.v1")
        #expect(jobs.first?.runKind == "benchmark")
        #expect(jobs.first?.status == "running")
        #expect(jobs.first?.phase == "sampling")
        #expect(jobs.first?.startedAtUnixMS == 1_778_908_032_000)
        #expect(jobs.first?.updatedAtUnixMS == 1_778_908_099_000)
        #expect(jobs.first?.durationMS == 67_000)
        #expect(jobs.first?.modelID == "mlx-community/Qwen3-8B")
        #expect(jobs.first?.taskKind == "text-generation")
        #expect(jobs.first?.suiteIDs == ["smoke", "latency"])
        #expect(jobs.first?.artifactRoot == "/tmp/melix/bench/bench-20260516-1027")
        #expect(jobs.first?.isActive == true)
        #expect(jobs.first?.isTerminal == false)

        let training = try #require(jobs.last)
        #expect(training.operation == "train_lora")
        #expect(training.startedAtUnixMS == 1_778_905_261_000)
        #expect(training.updatedAtUnixMS == 1_778_905_321_000)
        #expect(training.durationMS == 60_000)
        #expect(training.cancelable == false)
        #expect(training.cancellationRequested == true)
        #expect(training.isActive == false)
        #expect(training.isTerminal == true)
    }

    @Test("jobs show JSON decodes nested detail state")
    func jobsShowJSONDecodesNestedDetailState() throws {
        let data = Data("""
        {
          "schema_version": "melix.job_status.v1",
          "job_id": "bench-20260516-1027",
          "run_kind": "benchmark",
          "status": "failed",
          "phase": "collect_artifacts",
          "started_at_unix_ms": 1778908032000,
          "updated_at_unix_ms": 1778908099000,
          "duration_ms": 67000,
          "model_id": "mlx-community/Qwen3-8B",
          "task_kind": "text-generation",
          "suite_ids": ["smoke"],
          "dataset_id": "",
          "artifact_root": "/tmp/melix/bench/bench-20260516-1027",
          "record_path": "/tmp/melix/bench/bench-20260516-1027/run-record.json",
          "cancelable": false,
          "cancellation_requested": true,
          "command": {
            "display": "melix bench run --model-id mlx-community/Qwen3-8B"
          },
          "timestamps": {
            "started_at_unix_ms": 1778908032000,
            "updated_at_unix_ms": 1778908099000,
            "ended_at_unix_ms": 1778908099000,
            "duration_ms": 67000
          },
          "progress": {
            "phase": "collect_artifacts",
            "status": "failed",
            "duration_ms": 1200,
            "pct": 0.8
          },
          "throughput_metrics": [
            {
              "name": "tokens_per_second",
              "value": 42.5,
              "unit": "tokens_per_second"
            }
          ],
          "error": {
            "code": "artifact_write_failed",
            "message": "Output path is read-only."
          },
          "logs": {
            "schema_version": "melix.job_logs_ref.v1",
            "available": true,
            "path": "/tmp/melix/bench/bench-20260516-1027/run.log",
            "command": "melix jobs logs bench-20260516-1027 --follow"
          },
          "artifacts": [
            {
              "kind": "artifact_root",
              "path": "/tmp/melix/bench/bench-20260516-1027",
              "relative_path": "",
              "exists": true
            },
            {
              "kind": "cancel_request",
              "path": "/tmp/melix/bench/bench-20260516-1027/cancel-request.json",
              "relative_path": "cancel-request.json",
              "exists": false
            }
          ],
          "cancellation": {
            "schema_version": "melix.job_cancellation_state.v1",
            "cancelable": false,
            "requested": true,
            "request_path": "/tmp/melix/bench/bench-20260516-1027/cancel-request.json"
          }
        }
        """.utf8)

        let detail = try RuntimeJobsPayloadDecoder.decodeDetail(data)

        #expect(detail.summary.id == "bench-20260516-1027")
        #expect(detail.summary.status == "failed")
        #expect(detail.summary.isTerminal == true)
        #expect(detail.commandDisplay == "melix bench run --model-id mlx-community/Qwen3-8B")
        #expect(detail.timestamps.endedAtUnixMS == 1_778_908_099_000)
        #expect(detail.progress?.pct == 0.8)
        #expect(detail.progress?.durationMS == 1_200)
        #expect(detail.throughputMetrics.first?.name == "tokens_per_second")
        #expect(detail.throughputMetrics.first?.value == 42.5)
        #expect(detail.error?.code == "artifact_write_failed")
        #expect(detail.error?.message == "Output path is read-only.")
        #expect(detail.logs.available == true)
        #expect(detail.logs.path.hasSuffix("run.log"))
        #expect(detail.artifacts.map(\.kind) == ["artifact_root", "cancel_request"])
        #expect(detail.artifacts.first?.exists == true)
        #expect(detail.cancellation.cancelable == false)
        #expect(detail.cancellation.requested == true)
    }

    @Test("jobs detail decoder tolerates sparse and mixed scalar payloads")
    func jobsDetailDecoderToleratesSparseAndMixedScalarPayloads() throws {
        let data = Data("""
        {
          "schema_version": 7,
          "job_id": "sparse-job",
          "run_kind": true,
          "status": "queued",
          "phase": "preflight",
          "started_at_unix_ms": "1778908032000",
          "updated_at_unix_ms": 1778908032123.9,
          "duration_ms": 12.75,
          "model_id": 42.5,
          "task_kind": false,
          "suite_ids": [101, 202],
          "dataset_id": "dataset-a",
          "artifact_root": "/tmp/melix/sparse-job",
          "record_path": "/tmp/melix/sparse-job/run-record.json",
          "cancelable": 1,
          "cancellation_requested": "yes",
          "progress": {
            "phase": "preflight",
            "status": "queued",
            "duration_ms": "25",
            "pct": "0.25"
          },
          "throughput_metrics": [
            {
              "name": 25,
              "value": "3.5",
              "unit": true
            }
          ],
          "logs": {
            "available": "no"
          },
          "artifacts": [
            {
              "kind": "run_record",
              "path": "/tmp/melix/sparse-job/run-record.json",
              "exists": "true"
            }
          ]
        }
        """.utf8)

        let detail = try RuntimeJobsPayloadDecoder.decodeDetail(data)

        #expect(detail.summary.schemaVersion == "7")
        #expect(detail.summary.runKind == "true")
        #expect(detail.summary.isActive == true)
        #expect(detail.summary.modelID == "42.5")
        #expect(detail.summary.taskKind == "false")
        #expect(detail.summary.suiteIDs == ["101", "202"])
        #expect(detail.summary.startedAtUnixMS == 1_778_908_032_000)
        #expect(detail.summary.updatedAtUnixMS == 1_778_908_032_123)
        #expect(detail.summary.durationMS == 12)
        #expect(detail.summary.cancelable == true)
        #expect(detail.summary.cancellationRequested == true)
        #expect(detail.commandDisplay.isEmpty)
        #expect(detail.timestamps.startedAtUnixMS == detail.summary.startedAtUnixMS)
        #expect(detail.timestamps.endedAtUnixMS == 0)
        #expect(detail.progress?.pct == 0.25)
        #expect(detail.throughputMetrics.first?.name == "25")
        #expect(detail.throughputMetrics.first?.value == 3.5)
        #expect(detail.throughputMetrics.first?.unit == "true")
        #expect(detail.logs.available == false)
        #expect(detail.logs.path.isEmpty)
        #expect(detail.artifacts.first?.relativePath.isEmpty == true)
        #expect(detail.artifacts.first?.exists == true)
        #expect(detail.artifacts.first?.id == "run_record|/tmp/melix/sparse-job/run-record.json")
        #expect(detail.cancellation.cancelable == true)
        #expect(detail.cancellation.requested == true)
        #expect(detail.cancellation.requestPath.isEmpty)

        let stringSuiteData = Data("""
        [
          {
            "job_id": "single-suite",
            "status": "unknown",
            "suite_ids": "solo"
          }
        ]
        """.utf8)
        let singleSuite = try #require(RuntimeJobsPayloadDecoder.decodeList(stringSuiteData).first)
        #expect(singleSuite.suiteIDs == ["solo"])
        #expect(singleSuite.isActive == false)
        #expect(singleSuite.isTerminal == false)

        let minimalDetailData = Data("""
        {
          "job_id": "minimal-job",
          "status": "started",
          "progress": {
            "phase": "queued",
            "status": "started"
          }
        }
        """.utf8)
        let minimal = try RuntimeJobsPayloadDecoder.decodeDetail(minimalDetailData)
        #expect(minimal.summary.suiteIDs.isEmpty)
        #expect(minimal.summary.isActive == true)
        #expect(minimal.progress?.pct == nil)
        #expect(minimal.logs == RuntimeJobLogReferenceState())
        #expect(minimal.cancellation == RuntimeJobCancellationState())
    }

    @Test("runtime view model tracks jobs list selection and empty state")
    @MainActor
    func runtimeViewModelTracksJobsListSelectionAndEmptyState() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())

        #expect(viewModel.runtimeJobs.isEmpty)
        #expect(viewModel.selectedRuntimeJob == nil)
        #expect(viewModel.runtimeJobsEmptyStateTitle == "No Jobs Yet")
        #expect(viewModel.runtimeJobsEmptyStateDetail == "Run a benchmark, evaluation, training, or synthetic workflow to populate Jobs.")

        let jobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-20260516-1027",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "started_at_unix_ms": 1778908032000,
            "updated_at_unix_ms": 1778908099000,
            "artifact_root": "/tmp/melix/bench/bench-20260516-1027",
            "cancelable": true
          },
          {
            "job_id": "eval-20260516-1044",
            "run_kind": "evaluation",
            "status": "completed",
            "phase": "complete",
            "model_id": "melix-dev-text",
            "task_kind": "mmlu",
            "started_at_unix_ms": 1778909044000,
            "updated_at_unix_ms": 1778909101000,
            "artifact_root": "/tmp/melix/eval/eval-20260516-1044"
          }
        ]
        """.utf8))

        viewModel.applyRuntimeJobs(jobs)

        #expect(viewModel.runtimeJobs.map(\.id) == ["bench-20260516-1027", "eval-20260516-1044"])
        #expect(viewModel.selectedRuntimeJobID == "bench-20260516-1027")
        #expect(viewModel.selectedRuntimeJob?.id == "bench-20260516-1027")

        viewModel.selectRuntimeJob(id: "eval-20260516-1044")
        #expect(viewModel.selectedRuntimeJob?.id == "eval-20260516-1044")

        viewModel.selectRuntimeJob(id: "missing-job")
        #expect(viewModel.selectedRuntimeJob?.id == "eval-20260516-1044")

        viewModel.applyRuntimeJobs([jobs[0]])
        #expect(viewModel.selectedRuntimeJobID == "bench-20260516-1027")
        #expect(viewModel.selectedRuntimeJob?.id == "bench-20260516-1027")

        viewModel.applyRuntimeJobs([])
        #expect(viewModel.selectedRuntimeJobID.isEmpty)
        #expect(viewModel.selectedRuntimeJob == nil)

        viewModel.selectToolSection(.jobs)
        #expect(viewModel.selectedSurface == .workflows)
        #expect(viewModel.selectedToolSection == .jobs)
    }

    @Test("runtime view model tracks selected job detail")
    @MainActor
    func runtimeViewModelTracksSelectedJobDetail() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        let detail = try RuntimeJobsPayloadDecoder.decodeDetail(Data("""
        {
          "job_id": "bench-20260516-1120",
          "run_kind": "benchmark",
          "operation": "bench run",
          "status": "failed",
          "phase": "export",
          "model_id": "mlx-community/Qwen3-8B",
          "task_kind": "text-generation",
          "artifact_root": "/tmp/melix/jobs/bench-20260516-1120",
          "timestamps": {
            "started_at_unix_ms": 1778911200000,
            "updated_at_unix_ms": 1778911210000,
            "ended_at_unix_ms": 1778911215000,
            "duration_ms": 15000
          },
          "error": {
            "code": "E_MLX",
            "message": "out of memory"
          },
          "logs": {
            "available": true,
            "path": "/tmp/melix/jobs/bench-20260516-1120/job.log",
            "command": "melix jobs logs bench-20260516-1120"
          },
          "artifacts": [
            {
              "kind": "manifest",
              "path": "/tmp/melix/jobs/bench-20260516-1120/manifest.json",
              "relative_path": "manifest.json",
              "exists": true
            }
          ]
        }
        """.utf8))

        viewModel.applyRuntimeJobDetail(detail)

        #expect(viewModel.runtimeJobs.map(\.id) == ["bench-20260516-1120"])
        #expect(viewModel.selectedRuntimeJobID == "bench-20260516-1120")
        #expect(viewModel.selectedRuntimeJobDetail?.summary.status == "failed")
        #expect(viewModel.selectedRuntimeJobDetail?.timestamps.durationMS == 15000)
        #expect(viewModel.selectedRuntimeJobDetail?.error?.code == "E_MLX")
        #expect(viewModel.selectedRuntimeJobDetail?.logs.path.hasSuffix("job.log") == true)
        #expect(viewModel.selectedRuntimeJobDetail?.artifacts.first?.kind == "manifest")

        viewModel.applyRuntimeJobDetail(detail)
        #expect(viewModel.runtimeJobs.count == 1)
        #expect(viewModel.selectedRuntimeJobDetail?.summary.id == "bench-20260516-1120")
    }

    @Test("runtime view model refreshes jobs through CLI workflow runner")
    @MainActor
    func runtimeViewModelRefreshesJobsThroughCLIWorkflowRunner() async throws {
        let runner = RecordingCLIWorkflowRunner()
        let listCommand = MelixCLICommand.jobsList(.init(json: true))
        await runner.configureOutput(
            """
            [
              {
                "job_id": "bench-cli-1",
                "run_kind": "benchmark",
                "status": "running",
                "phase": "sampling",
                "model_id": "mlx-community/Qwen3-8B",
                "task_kind": "text-generation",
                "updated_at_unix_ms": 1778912044000,
                "cancelable": true
              }
            ]
            """,
            for: listCommand
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)

        await viewModel.refreshRuntimeJobs()

        #expect(viewModel.runtimeJobs.map(\.id) == ["bench-cli-1"])
        #expect(viewModel.selectedRuntimeJobID == "bench-cli-1")
        #expect(viewModel.lastCLIWorkflowFailure == nil)
        #expect(await runner.snapshotRecordedCommands() == [listCommand])
    }

    @Test("runtime view model refreshes selected job detail logs and artifacts through CLI workflow runner")
    @MainActor
    func runtimeViewModelRefreshesSelectedJobDetailLogsAndArtifactsThroughCLIWorkflowRunner() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureHandler { command in
            switch command {
            case .jobsList:
                return .success(
                    """
                    [
                      {
                        "job_id": "bench-cli-1",
                        "run_kind": "benchmark",
                        "status": "running",
                        "phase": "sampling",
                        "model_id": "mlx-community/Qwen3-8B",
                        "task_kind": "text-generation",
                        "updated_at_unix_ms": 1778912044000,
                        "cancelable": true
                      }
                    ]
                    """
                )
            case .jobsShow(let options):
                guard options.jobID == "bench-cli-1", options.json else {
                    return .failure(.unsupportedCommand(commandID: command.workflowCommandID, surface: .subprocess))
                }
                return .success(
                    """
                    {
                      "job_id": "bench-cli-1",
                      "run_kind": "benchmark",
                      "status": "running",
                      "phase": "export",
                      "model_id": "mlx-community/Qwen3-8B",
                      "task_kind": "text-generation",
                      "artifact_root": "/tmp/melix/jobs/bench-cli-1",
                      "timestamps": {
                        "started_at_unix_ms": 1778912000000,
                        "updated_at_unix_ms": 1778912044000,
                        "duration_ms": 44000
                      },
                      "logs": {
                        "available": true,
                        "path": "/tmp/melix/jobs/bench-cli-1/job.log",
                        "command": "melix jobs logs bench-cli-1"
                      },
                      "artifacts": []
                    }
                    """
                )
            case .jobsLogs(let options):
                guard options.jobID == "bench-cli-1", options.json else {
                    return .failure(.unsupportedCommand(commandID: command.workflowCommandID, surface: .subprocess))
                }
                return .success(
                    """
                    {
                      "schema_version": "melix.logs.v1",
                      "run_id": "bench-cli-1",
                      "source_path": "/tmp/melix/jobs/bench-cli-1/run-record.json",
                      "log_path": "/tmp/melix/jobs/bench-cli-1/job.log",
                      "follow_requested": false,
                      "active_follow_supported": false,
                      "content": "sampling complete\\nexport started",
                      "redaction_schema_version": "melix.diagnostics.redaction.v1",
                      "redacted_field_count": 0
                    }
                    """
                )
            case .jobsArtifacts(let options):
                guard options.jobID == "bench-cli-1", options.json else {
                    return .failure(.unsupportedCommand(commandID: command.workflowCommandID, surface: .subprocess))
                }
                return .success(
                    """
                    {
                      "schema_version": "melix.job_artifacts.v1",
                      "job_id": "bench-cli-1",
                      "artifact_count": 1,
                      "artifacts": [
                        {
                          "kind": "manifest",
                          "path": "/tmp/melix/jobs/bench-cli-1/manifest.json",
                          "relative_path": "manifest.json",
                          "exists": true
                        }
                      ]
                    }
                    """
                )
            default:
                return .failure(.unsupportedCommand(commandID: command.workflowCommandID, surface: .subprocess))
            }
        }
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)

        await viewModel.refreshRuntimeJobs()
        await viewModel.refreshSelectedRuntimeJobDetail()
        await viewModel.refreshSelectedRuntimeJobLogs()
        await viewModel.refreshSelectedRuntimeJobArtifacts()

        #expect(viewModel.selectedRuntimeJobDetail?.summary.phase == "export")
        #expect(viewModel.selectedRuntimeJobLogSnapshot?.content.contains("export started") == true)
        #expect(viewModel.selectedRuntimeJobArtifactSnapshot?.artifacts.first?.kind == "manifest")
        #expect(
            await runner.snapshotRecordedCommands() == [
                .jobsList(.init(json: true)),
                .jobsShow(.init(jobID: "bench-cli-1", json: true)),
                .jobsLogs(.init(jobID: "bench-cli-1", json: true)),
                .jobsArtifacts(.init(jobID: "bench-cli-1", json: true)),
            ]
        )
    }

    @Test("runtime view model surfaces missing jobs runner and selection errors")
    @MainActor
    func runtimeViewModelSurfacesMissingJobsRunnerAndSelectionErrors() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())

        await viewModel.refreshRuntimeJobs()
        #expect(viewModel.lastError == "Jobs CLI runner is unavailable.")

        await viewModel.refreshSelectedRuntimeJobDetail()
        #expect(viewModel.lastError == "Select a job before refreshing job detail.")

        let jobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-cli-1",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation"
          }
        ]
        """.utf8))
        viewModel.applyRuntimeJobs(jobs)

        await viewModel.refreshSelectedRuntimeJobDetail()
        #expect(viewModel.lastError == "Jobs CLI runner is unavailable.")
        await viewModel.refreshSelectedRuntimeJobLogs()
        #expect(viewModel.lastError == "Jobs CLI runner is unavailable.")
        await viewModel.refreshSelectedRuntimeJobArtifacts()
        #expect(viewModel.lastError == "Jobs CLI runner is unavailable.")
    }

    @Test("runtime view model records jobs CLI failures per operation")
    @MainActor
    func runtimeViewModelRecordsJobsCLIFailuresPerOperation() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureHandler { command in
            .failure(.processFailed(commandID: command.workflowCommandID, surface: .subprocess, exitCode: 2, stderr: "failed"))
        }
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)

        await viewModel.refreshRuntimeJobs()
        #expect(viewModel.runtimeJobsRefreshInProgress == false)
        #expect(viewModel.lastCLIWorkflowFailure?.commandID == "jobs.list")

        let jobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-cli-1",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation"
          }
        ]
        """.utf8))
        viewModel.applyRuntimeJobs(jobs)

        await viewModel.refreshSelectedRuntimeJobDetail()
        #expect(viewModel.selectedRuntimeJobDetailRefreshInProgress == false)
        #expect(viewModel.lastCLIWorkflowFailure?.commandID == "jobs.show")

        await viewModel.refreshSelectedRuntimeJobLogs()
        #expect(viewModel.selectedRuntimeJobLogsRefreshInProgress == false)
        #expect(viewModel.lastCLIWorkflowFailure?.commandID == "jobs.logs")

        await viewModel.refreshSelectedRuntimeJobArtifacts()
        #expect(viewModel.selectedRuntimeJobArtifactsRefreshInProgress == false)
        #expect(viewModel.lastCLIWorkflowFailure?.commandID == "jobs.artifacts")
    }

    @Test("runtime jobs CLI decoder maps malformed JSON to workflow failure")
    @MainActor
    func runtimeJobsCLIDecoderMapsMalformedJSONToWorkflowFailure() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureOutput("{", for: .jobsList(.init(json: true)))
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)

        await viewModel.refreshRuntimeJobs()

        #expect(viewModel.runtimeJobsRefreshInProgress == false)
        #expect(viewModel.lastCLIWorkflowFailure?.commandID == "jobs.list")
        #expect(viewModel.lastCLIWorkflowFailure?.failureKind == .invalidJSON)
    }

    @Test("runtime jobs cancel result decodes active and terminal receipts")
    func runtimeJobsCancelResultDecodesActiveAndTerminalReceipts() throws {
        let active = try RuntimeJobsPayloadDecoder.decodeCancelResult(Data("""
        {
          "schema_version": "melix.job_cancel_result.v1",
          "job_id": "bench-cli-1",
          "cancel_requested": true,
          "status": "running",
          "phase": "sampling",
          "request_path": "/tmp/melix/jobs/bench-cli-1/cancel-request.json",
          "request": {
            "requested_at_unix_ms": 1778913000000,
            "process_signal": {
              "pid": null,
              "sent": false,
              "reason": "direct_process_signal_disabled"
            }
          }
        }
        """.utf8))
        let terminal = try RuntimeJobsPayloadDecoder.decodeCancelResult(Data("""
        {
          "schema_version": "melix.job_cancel_result.v1",
          "job_id": "bench-cli-2",
          "cancel_requested": false,
          "status": "completed",
          "phase": "completed",
          "reason": "job_terminal_or_not_active",
          "request_path": "/tmp/melix/jobs/bench-cli-2/cancel-request.json"
        }
        """.utf8))
        let legacyProcessSignal = try RuntimeJobsPayloadDecoder.decodeCancelResult(Data("""
        {
          "schema_version": "melix.job_cancel_result.v1",
          "job_id": "bench-cli-3",
          "cancel_requested": true,
          "status": "running",
          "phase": "sampling",
          "request_path": "/tmp/melix/jobs/bench-cli-3/cancel-request.json",
          "request": {
            "requested_at_unix_ms": 1778913000001,
            "process_signal": "disabled"
          }
        }
        """.utf8))

        #expect(active.cancelRequested)
        #expect(active.jobID == "bench-cli-1")
        #expect(active.requestPath.hasSuffix("cancel-request.json"))
        #expect(active.requestedAtUnixMS == 1_778_913_000_000)
        #expect(active.processSignal == "direct_process_signal_disabled")
        #expect(terminal.cancelRequested == false)
        #expect(terminal.reason == "job_terminal_or_not_active")
        #expect(terminal.isTerminalNotActive)
        #expect(legacyProcessSignal.processSignal == "disabled")
    }

    @Test("runtime view model requests selected active job cancellation through CLI workflow runner")
    @MainActor
    func runtimeViewModelRequestsSelectedActiveJobCancellationThroughCLIWorkflowRunner() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureOutput(
            """
            {
              "schema_version": "melix.job_cancel_result.v1",
              "job_id": "bench-cli-1",
              "cancel_requested": true,
              "status": "running",
              "phase": "sampling",
              "request_path": "/tmp/melix/jobs/bench-cli-1/cancel-request.json",
              "request": {
                "requested_at_unix_ms": 1778913000000,
                "process_signal": {
                  "pid": null,
                  "sent": false,
                  "reason": "direct_process_signal_disabled"
                }
              }
            }
            """,
            for: .jobsCancel(.init(jobID: "bench-cli-1", json: true))
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        let jobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-cli-1",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "cancelable": true,
            "cancellation_requested": false
          }
        ]
        """.utf8))
        viewModel.applyRuntimeJobs(jobs)

        #expect(viewModel.selectedRuntimeJobCanRequestCancellation)
        await viewModel.requestSelectedRuntimeJobCancellation()

        #expect(viewModel.selectedRuntimeJobCancelInProgress == false)
        #expect(viewModel.selectedRuntimeJobCancelResult?.cancelRequested == true)
        #expect(viewModel.selectedRuntimeJobCancellationStatusText == "Cancellation requested")
        #expect(viewModel.selectedRuntimeJobCanRequestCancellation == false)
        #expect(await runner.snapshotRecordedCommands() == [.jobsCancel(.init(jobID: "bench-cli-1", json: true))])
    }

    @Test("runtime view model avoids CLI cancellation for terminal jobs")
    @MainActor
    func runtimeViewModelAvoidsCLICancellationForTerminalJobs() async throws {
        let runner = RecordingCLIWorkflowRunner()
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        let jobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-cli-2",
            "run_kind": "benchmark",
            "status": "completed",
            "phase": "completed",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "cancelable": false,
            "cancellation_requested": false
          }
        ]
        """.utf8))
        viewModel.applyRuntimeJobs(jobs)

        #expect(viewModel.selectedRuntimeJobCanRequestCancellation == false)
        #expect(viewModel.selectedRuntimeJobCancellationStatusText == "Terminal job cannot be canceled")
        await viewModel.requestSelectedRuntimeJobCancellation()

        #expect(await runner.snapshotRecordedCommands().isEmpty)
        #expect(viewModel.lastError == "Selected job is terminal or already has a cancel request.")
    }

    @Test("runtime view model renders stale terminal cancel receipts")
    @MainActor
    func runtimeViewModelRendersStaleTerminalCancelReceipts() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureOutput(
            """
            {
              "schema_version": "melix.job_cancel_result.v1",
              "job_id": "bench-cli-1",
              "cancel_requested": false,
              "status": "completed",
              "phase": "completed",
              "reason": "job_terminal_or_not_active",
              "request_path": "/tmp/melix/jobs/bench-cli-1/cancel-request.json"
            }
            """,
            for: .jobsCancel(.init(jobID: "bench-cli-1", json: true))
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        let jobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-cli-1",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "cancelable": true,
            "cancellation_requested": false
          }
        ]
        """.utf8))
        viewModel.applyRuntimeJobs(jobs)

        await viewModel.requestSelectedRuntimeJobCancellation()

        #expect(viewModel.selectedRuntimeJobCancelResult?.cancelRequested == false)
        #expect(viewModel.selectedRuntimeJobCancelResult?.reason == "job_terminal_or_not_active")
        #expect(viewModel.selectedRuntimeJobCancellationStatusText == "Cancellation not requested: job_terminal_or_not_active")
        #expect(viewModel.selectedRuntimeJobCanRequestCancellation == false)
    }

    @Test("runtime view model surfaces cancel guard and CLI failure states")
    @MainActor
    func runtimeViewModelSurfacesCancelGuardAndCLIFailureStates() async throws {
        let noSelection = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        #expect(noSelection.selectedRuntimeJobCancellationStatusText == "Select a job to request cancellation")
        await noSelection.requestSelectedRuntimeJobCancellation()
        #expect(noSelection.lastError == "Select a job before requesting job cancellation.")

        let requested = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        let requestedJobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-requested",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "cancelable": true,
            "cancellation_requested": true
          }
        ]
        """.utf8))
        requested.applyRuntimeJobs(requestedJobs)
        #expect(requested.selectedRuntimeJobCanRequestCancellation == false)
        #expect(requested.selectedRuntimeJobCancellationStatusText == "Cancellation already requested")
        await requested.requestSelectedRuntimeJobCancellation()
        #expect(requested.lastError == "Selected job is terminal or already has a cancel request.")

        let missingRunner = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        let activeJobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-active",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "cancelable": true,
            "cancellation_requested": false
          }
        ]
        """.utf8))
        missingRunner.applyRuntimeJobs(activeJobs)
        #expect(missingRunner.selectedRuntimeJobCanRequestCancellation)
        await missingRunner.requestSelectedRuntimeJobCancellation()
        #expect(missingRunner.lastError == "Jobs CLI runner is unavailable.")

        let failingRunner = RecordingCLIWorkflowRunner()
        await failingRunner.configureHandler { command in
            .failure(.processFailed(commandID: command.workflowCommandID, surface: .subprocess, exitCode: 2, stderr: "failed"))
        }
        let failing = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: failingRunner)
        failing.applyRuntimeJobs(activeJobs)

        await failing.requestSelectedRuntimeJobCancellation()

        #expect(failing.selectedRuntimeJobCancelInProgress == false)
        #expect(failing.lastCLIWorkflowFailure?.commandID == "jobs.cancel")
        #expect(failing.selectedRuntimeJobCancelResult == nil)
    }

    @Test("runtime view model persists selected runtime job and restores across restart")
    @MainActor
    func runtimeViewModelPersistsSelectedRuntimeJobAndRestoresAcrossRestart() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-jobs-selected-session-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let jobs = try RuntimeJobsPayloadDecoder.decodeList(Data("""
        [
          {
            "job_id": "bench-cli-1",
            "run_kind": "benchmark",
            "status": "running",
            "phase": "sampling",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "text-generation",
            "cancelable": true
          },
          {
            "job_id": "eval-cli-2",
            "run_kind": "evaluation",
            "status": "completed",
            "phase": "completed",
            "model_id": "mlx-community/Qwen3-8B",
            "task_kind": "evaluation",
            "cancelable": false
          }
        ]
        """.utf8))
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            operatorSessionStore: operatorSessionStore
        )

        await viewModel.start()
        viewModel.selectToolSection(.jobs)
        viewModel.applyRuntimeJobs(jobs)
        viewModel.selectRuntimeJob(id: "eval-cli-2")

        let persistedPayload = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: melixHome.operatorSessionFileURL)) as? [String: Any]
        )
        #expect(persistedPayload["selected_tool_section"] as? String == "jobs")
        #expect(persistedPayload["selected_runtime_job_id"] as? String == "eval-cli-2")

        let restored = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            operatorSessionStore: operatorSessionStore
        )
        await restored.start()

        #expect(restored.selectedToolSection == .jobs)
        #expect(restored.selectedRuntimeJobID == "eval-cli-2")
        restored.applyRuntimeJobs(jobs)
        #expect(restored.selectedRuntimeJob?.id == "eval-cli-2")
    }
}
