import Testing

@testable import MelixControlPlaneCore

@Suite("Benchmark Export Bundle")
struct BenchmarkExportBundleTests {
    @Test("decodes benchmark history entries and csv rows from persisted suite metadata")
    func decodesBenchmarkHistoryEntriesAndCSVRows() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(json: benchmarkExportBundleJSON)

        let entries = bundle.benchmarkHistoryEntries()
        let rows = bundle.benchmarkCSVRows(jobID: "bench-1")
        let csv = bundle.benchmarkCSV(jobID: "bench-1")

        #expect(entries.count == 2)
        #expect(entries[0].jobID == "bench-2")
        #expect(entries[0].suiteID == "latency")
        #expect(entries[0].datasetRepo == "databricks/databricks-dolly-15k")
        #expect(entries[1].jobID == "bench-1")
        #expect(entries[1].datasetConfig == "default")
        #expect(entries[1].sampleSize == 4)
        #expect(rows.count == 2)
        #expect(rows[0].jobID == "bench-1")
        #expect(rows[0].suiteID == "smoke")
        #expect(rows[0].metricName == "bench.smoke.tokens_per_second")
        #expect(rows[0].metricValue == 47.08)
        #expect(csv.contains("job_id,model_id,suite_id,dataset_repo,dataset_config,dataset_split,sample_size,batch_factor,metric_name,metric_value,unit,created_at_unix_ms"))
        #expect(csv.contains("bench-1,melix-dev-text,smoke,HuggingFaceH4/ultrachat_200k,default,train_sft,4,2,bench.smoke.ttft_ms,24.45,ms,1712100000000"))
    }

    @Test("surfaces invalid json and emits the csv header for empty benchmark history")
    func surfacesInvalidJSONAndEmptyBenchmarkHistory() {
        do {
            _ = try ControlPlaneBenchmarkExportBundle.decode(json: "{")
            Issue.record("Expected invalid benchmark export JSON to throw.")
        } catch let error as ControlPlaneBenchmarkExportError {
            guard case .invalidJSON(let message) = error else {
                Issue.record("Expected invalidJSON error.")
                return
            }
            #expect(message.contains("Benchmark export bundle could not be decoded"))
            #expect(error.errorDescription == message)
        } catch {
            Issue.record("Expected ControlPlaneBenchmarkExportError, got \(error).")
        }

        let emptyBundle = try? ControlPlaneBenchmarkExportBundle.decode(
            json: #"{"export_schema_version":"melix.benchmark_export.v1","benchmark_jobs":[],"benchmark_results":[]}"#
        )
        #expect(emptyBundle?.benchmarkHistoryEntries() == [])
        #expect(emptyBundle?.benchmarkCSV() == "job_id,model_id,suite_id,dataset_repo,dataset_config,dataset_split,sample_size,batch_factor,metric_name,metric_value,unit,created_at_unix_ms\n")
    }

    @Test("falls back to job parameters, sorts deterministically, and quotes csv fields")
    func fallsBackToParametersSortsDeterministicallyAndQuotesCSVFields() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(json: benchmarkExportBundleFallbackJSON)

        let historyEntries = bundle.benchmarkHistoryEntries()
        let rows = bundle.benchmarkCSVRows()
        let csv = bundle.benchmarkCSV()

        #expect(historyEntries.map(\.jobID) == ["bench-b", "bench-a", "bench-c"])
        #expect(historyEntries[0].sampleSize == 5)
        #expect(historyEntries[0].batchFactor == nil)
        #expect(historyEntries[1].sampleSize == 7)
        #expect(historyEntries[1].batchFactor == 4)
        #expect(historyEntries[2].datasetConfig == #"cfg, "quoted""#)

        #expect(rows.map(\.jobID) == ["bench-c", "bench-a", "bench-b"])
        #expect(rows[1].sampleSize == 7)
        #expect(rows[1].batchFactor == 4)
        #expect(rows[2].batchFactor == nil)
        #expect(csv.contains(#""cfg, ""quoted""""#))
    }
}

private let benchmarkExportBundleJSON = """
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
    },
    {
      "schema_version": "melix.serving_benchmark_job.v1",
      "job_id": "bench-2",
      "model_id": "melix-dev-text-lora",
      "suites": [],
      "parameters": {},
      "status": "completed",
      "output_dir": "/tmp/melix/bench/runs/bench-2",
      "created_at_unix_ms": 1712200000000,
      "updated_at_unix_ms": 1712200005000,
      "suite_metadata": {
        "latency": {
          "title": "Dolly Latency",
          "dataset_path": "databricks/databricks-dolly-15k",
          "dataset_name": "default",
          "dataset_split": "train",
          "sample_size": 5,
          "batch_factor": 1
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
    },
    {
      "schema_version": "melix.serving_benchmark_result.v1",
      "job_id": "bench-2",
      "suite": "latency",
      "metrics": [
        {"name": "bench.latency.p95_ms", "value": 44.72, "unit": "ms"}
      ],
      "report_path": "/tmp/melix/bench/runs/bench-2/bench-report.md",
      "report_markdown": "# Melix Bench\\n"
    }
  ]
}
"""

private let benchmarkExportBundleFallbackJSON = """
{
  "export_schema_version": "melix.benchmark_export.v1",
  "exported_at_unix_ms": 1712301234567,
  "benchmark_jobs": [
    {
      "schema_version": "melix.serving_benchmark_job.v1",
      "job_id": "bench-a",
      "model_id": "melix-dev-text-a",
      "suites": [],
      "parameters": {
        "sample_size": "7",
        "batch_factor": "4"
      },
      "status": "completed",
      "output_dir": "/tmp/melix/bench/runs/bench-a",
      "created_at_unix_ms": 1712300000000,
      "updated_at_unix_ms": 1712300005000,
      "suite_metadata": {}
    },
    {
      "schema_version": "melix.serving_benchmark_job.v1",
      "job_id": "bench-b",
      "model_id": "melix-dev-text-b",
      "suites": [],
      "parameters": {
        "sample_size": "5"
      },
      "status": "completed",
      "output_dir": "/tmp/melix/bench/runs/bench-b",
      "created_at_unix_ms": 1712300000000,
      "updated_at_unix_ms": 1712300007000,
      "suite_metadata": {}
    },
    {
      "schema_version": "melix.serving_benchmark_job.v1",
      "job_id": "bench-c",
      "model_id": "melix-dev-text-c",
      "suites": ["quoted"],
      "parameters": {},
      "status": "completed",
      "output_dir": "/tmp/melix/bench/runs/bench-c",
      "created_at_unix_ms": 1712290000000,
      "updated_at_unix_ms": 1712290005000,
      "suite_metadata": {
        "quoted": {
          "title": "Quoted Suite",
          "dataset_path": "repo/quoted",
          "dataset_name": "cfg, \\"quoted\\"",
          "dataset_split": "eval",
          "sample_size": 2,
          "batch_factor": 3
        }
      }
    }
  ],
  "benchmark_results": [
    {
      "schema_version": "melix.serving_benchmark_result.v1",
      "job_id": "bench-a",
      "suite": "fallback-a",
      "metrics": [
        {"name": "bench.smoke.ttft_ms", "value": 30.0, "unit": "ms"}
      ],
      "report_path": "/tmp/melix/bench/runs/bench-a/bench-report.md",
      "report_markdown": "# Bench A\\n"
    },
    {
      "schema_version": "melix.serving_benchmark_result.v1",
      "job_id": "bench-b",
      "suite": "fallback-b",
      "metrics": [
        {"name": "bench.latency.p95_ms", "value": 40.0, "unit": "ms"}
      ],
      "report_path": "/tmp/melix/bench/runs/bench-b/bench-report.md",
      "report_markdown": "# Bench B\\n"
    },
    {
      "schema_version": "melix.serving_benchmark_result.v1",
      "job_id": "bench-c",
      "suite": "quoted",
      "metrics": [
        {"name": "bench.quote.tokens_per_second", "value": 55.5, "unit": "tok/s"}
      ],
      "report_path": "/tmp/melix/bench/runs/bench-c/bench-report.md",
      "report_markdown": "# Bench C\\n"
    }
  ]
}
"""
