import Foundation
import Testing

@testable import AppMain

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
}
