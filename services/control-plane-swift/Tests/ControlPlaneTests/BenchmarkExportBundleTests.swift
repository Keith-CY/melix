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
        #expect(entries[0].taskKind == "image-text-to-text")
        #expect(entries[0].sourceRepo == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(entries[0].datasetRepo == "databricks/databricks-dolly-15k")
        #expect(entries[1].jobID == "bench-1")
        #expect(entries[1].taskKind == "text-generation")
        #expect(entries[1].sourceRepo == "HuggingFaceH4/ultrachat_200k")
        #expect(entries[1].datasetConfig == "default")
        #expect(entries[1].sampleSize == 4)
        #expect(rows.count == 2)
        #expect(rows[0].jobID == "bench-1")
        #expect(rows[0].taskKind == "text-generation")
        #expect(rows[0].sourceRepo == "HuggingFaceH4/ultrachat_200k")
        #expect(rows[0].suiteID == "smoke")
        #expect(rows[0].metricName == "bench.smoke.tokens_per_second")
        #expect(rows[0].metricValue == 47.08)
        #expect(csv.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_repo,dataset_config,dataset_split,sample_size,batch_factor,metric_name,metric_value,unit,created_at_unix_ms"))
        #expect(csv.contains("bench-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,smoke,HuggingFaceH4/ultrachat_200k,default,train_sft,4,2,bench.smoke.ttft_ms,24.45,ms,1712100000000"))
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
        #expect(emptyBundle?.benchmarkCSV() == "job_id,model_id,task_kind,source_repo,suite_id,dataset_repo,dataset_config,dataset_split,sample_size,batch_factor,metric_name,metric_value,unit,created_at_unix_ms\n")
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
        #expect(rows[0].taskKind == "image-text-to-image")
        #expect(rows[0].sourceRepo == "mlx-community/sdxl-edit")
        #expect(rows[1].sampleSize == 7)
        #expect(rows[1].batchFactor == 4)
        #expect(rows[2].batchFactor == nil)
        #expect(csv.contains(#""cfg, ""quoted""""#))
    }

    @Test("falls back to task kind parameters and metadata source repos when explicit fields are absent")
    func fallsBackToTaskKindParametersAndMetadataSourceRepos() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(json: benchmarkExportBundleImplicitTaskJSON)

        let entries = bundle.benchmarkHistoryEntries()
        let rows = bundle.benchmarkCSVRows()
        let parameterRow = try #require(rows.first(where: { $0.jobID == "bench-implicit-param" }))
        let defaultRow = try #require(rows.first(where: { $0.jobID == "bench-implicit-default" }))

        #expect(entries.count == 2)
        #expect(entries[0].jobID == "bench-implicit-param")
        #expect(entries[0].taskKind == "image-to-text")
        #expect(entries[0].sourceRepo == "huggingface/documentation-images")
        #expect(entries[1].jobID == "bench-implicit-default")
        #expect(entries[1].taskKind == "text-generation")
        #expect(entries[1].sourceRepo.isEmpty)
        #expect(parameterRow.taskKind == "image-to-text")
        #expect(parameterRow.sourceRepo == "huggingface/documentation-images")
        #expect(defaultRow.taskKind == "text-generation")
        #expect(defaultRow.sourceRepo.isEmpty)
    }

    @Test("decodes evaluation history rows summary csv and sample exports")
    func decodesEvaluationExports() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(json: benchmarkExportBundleJSON)

        let entries = bundle.evaluationHistoryEntries()
        let summaryRows = bundle.evaluationSummaryCSVRows(jobID: "eval-1")
        let samples = bundle.evaluationSampleRows(jobID: "eval-1")
        let summaryCSV = bundle.evaluationSummaryCSV(jobID: "eval-1")
        let sampleCSV = bundle.evaluationSamplesCSV(jobID: "eval-1")
        let sampleJSONL = try bundle.evaluationSamplesJSONL(jobID: "eval-1")

        #expect(entries.count == 1)
        #expect(entries[0].jobID == "eval-1")
        #expect(entries[0].suiteID == "mmlu")
        #expect(entries[0].taskKind == "text-generation")
        #expect(entries[0].sourceRepo == "HuggingFaceH4/ultrachat_200k")
        #expect(summaryRows.count == 1)
        #expect(summaryRows[0].metricName == "eval.mmlu.accuracy")
        #expect(summaryRows[0].metricValue == 0.75)
        #expect(samples.count == 1)
        #expect(samples[0].sampleID == "sample-1")
        #expect(summaryCSV.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,scoring_mode,metric_name,metric_value,unit,created_at_unix_ms"))
        #expect(summaryCSV.contains("eval-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,mmlu,mmlu.dev.v1,8,multiple_choice_accuracy,eval.mmlu.accuracy,0.75,ratio,1712400000000"))
        #expect(sampleCSV.contains("id,correct,expected,predicted,question,raw_response,time_s,parse_status"))
        #expect(sampleCSV.contains("sample-1,true,4,4,2+2?,4,0.01,parsed"))
        #expect(sampleJSONL.contains("\"sample_id\":\"sample-1\""))
    }

    @Test("evaluation exports fall back to parameters sort deterministically and emit empty headers")
    func evaluationExportsFallBackToParametersSortDeterministicallyAndEmitEmptyHeaders() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(json: evaluationExportBundleFallbackJSON)

        let entries = bundle.evaluationHistoryEntries()
        let rows = bundle.evaluationSummaryCSVRows()
        let samples = bundle.evaluationSampleRows()
        let summaryCSV = bundle.evaluationSummaryCSV()
        let sampleCSV = bundle.evaluationSamplesCSV()
        let emptyBundle = try ControlPlaneBenchmarkExportBundle.decode(json: emptyEvaluationExportBundleJSON)

        #expect(entries.map(\.jobID) == ["eval-z", "eval-b", "eval-a"])
        #expect(entries[0].taskKind == "text-generation")
        #expect(entries[1].taskKind == "text-generation")
        #expect(entries[1].sourceRepo == "fallback/repo")
        #expect(rows.map(\.jobID) == ["eval-a", "eval-b", "eval-z"])
        #expect(rows[0].taskKind == "text-generation")
        #expect(rows[1].sourceRepo == "fallback/repo")
        #expect(samples.map(\.sampleID) == ["sample-1", "sample-2"])
        #expect(summaryCSV.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,scoring_mode,metric_name,metric_value,unit,created_at_unix_ms"))
        #expect(sampleCSV.contains("id,correct,expected,predicted,question,raw_response,time_s,parse_status"))
        #expect(emptyBundle.evaluationSummaryCSV() == "job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,scoring_mode,metric_name,metric_value,unit,created_at_unix_ms\n")
        #expect(emptyBundle.evaluationSamplesCSV() == "id,correct,expected,predicted,question,raw_response,time_s,parse_status\n")
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
    },
    {
      "schema_version": "melix.serving_benchmark_job.v1",
      "job_id": "bench-2",
      "model_id": "melix-dev-text-lora",
      "task_kind": "image-text-to-text",
      "source_repo": "unsloth/gemma-4-E4B-it-MLX-8bit",
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

private let evaluationExportBundleFallbackJSON = """
{
  "export_schema_version": "melix.benchmark_export.v1",
  "benchmark_jobs": [],
  "benchmark_results": [],
  "evaluation_jobs": [
    {
      "schema_version": "melix.evaluation_job.v1",
      "job_id": "eval-a",
      "model_id": "melix-dev-text",
      "suite_id": "mmlu",
      "dataset_id": "mmlu.dev.v1",
      "sample_size": 4,
      "scoring_mode": "multiple_choice_accuracy",
      "parameters": {
        "task_kind": "text-generation",
        "source_repo": "fallback/repo"
      },
      "status": "completed",
      "created_at_unix_ms": 100,
      "updated_at_unix_ms": 110
    },
    {
      "schema_version": "melix.evaluation_job.v1",
      "job_id": "eval-b",
      "model_id": "melix-dev-text",
      "task_kind": "text-generation",
      "suite_id": "gsm8k",
      "dataset_id": "gsm8k.dev.v1",
      "sample_size": 6,
      "scoring_mode": "exact_match",
      "parameters": {
        "source_repo": "fallback/repo"
      },
      "status": "completed",
      "created_at_unix_ms": 100,
      "updated_at_unix_ms": 120
    },
    {
      "schema_version": "melix.evaluation_job.v1",
      "job_id": "eval-z",
      "model_id": "melix-dev-text",
      "task_kind": "text-generation",
      "source_repo": "explicit/repo",
      "suite_id": "mbpp",
      "dataset_id": "mbpp.dev.v1",
      "sample_size": 2,
      "scoring_mode": "pass_at_1",
      "parameters": {},
      "status": "completed",
      "created_at_unix_ms": 200,
      "updated_at_unix_ms": 210
    }
  ],
  "evaluation_results": [
    {
      "schema_version": "melix.evaluation_result.v1",
      "job_id": "eval-a",
      "suite_id": "mmlu",
      "dataset_id": "mmlu.dev.v1",
      "sample_size": 4,
      "metrics": [
        {"name": "eval.mmlu.accuracy", "value": 0.5, "unit": "ratio"}
      ]
    },
    {
      "schema_version": "melix.evaluation_result.v1",
      "job_id": "eval-b",
      "suite_id": "gsm8k",
      "dataset_id": "gsm8k.dev.v1",
      "sample_size": 6,
      "metrics": [
        {"name": "eval.gsm8k.exact_match", "value": 0.25, "unit": "ratio"}
      ]
    },
    {
      "schema_version": "melix.evaluation_result.v1",
      "job_id": "eval-z",
      "suite_id": "mbpp",
      "dataset_id": "mbpp.dev.v1",
      "sample_size": 2,
      "metrics": [
        {"name": "eval.mbpp.pass_at_1", "value": 1.0, "unit": "ratio"}
      ]
    }
  ],
  "evaluation_samples": [
    {
      "schema_version": "melix.evaluation_sample.v1",
      "job_id": "eval-a",
      "suite_id": "mmlu",
      "dataset_id": "mmlu.dev.v1",
      "sample_id": "sample-2",
      "question": "2+2?",
      "expected": "4",
      "predicted": "4",
      "raw_response": "4",
      "correct": true,
      "time_s": 0.02,
      "parse_status": "parsed"
    },
    {
      "schema_version": "melix.evaluation_sample.v1",
      "job_id": "eval-a",
      "suite_id": "mmlu",
      "dataset_id": "mmlu.dev.v1",
      "sample_id": "sample-1",
      "question": "3+3?",
      "expected": "6",
      "predicted": "6",
      "raw_response": "6",
      "correct": true,
      "time_s": 0.01,
      "parse_status": "parsed"
    }
  ]
}
"""

private let emptyEvaluationExportBundleJSON = """
{
  "export_schema_version": "melix.benchmark_export.v1",
  "benchmark_jobs": [],
  "benchmark_results": [],
  "evaluation_jobs": [],
  "evaluation_results": [],
  "evaluation_samples": []
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
      "task_kind": "text-generation",
      "source_repo": "repo/fallback-a",
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
      "task_kind": "image-to-text",
      "source_repo": "repo/fallback-b",
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
      "task_kind": "image-text-to-image",
      "source_repo": "mlx-community/sdxl-edit",
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

private let benchmarkExportBundleImplicitTaskJSON = """
{
  "export_schema_version": "melix.benchmark_export.v1",
  "exported_at_unix_ms": 1712401234567,
  "benchmark_jobs": [
    {
      "schema_version": "melix.serving_benchmark_job.v1",
      "job_id": "bench-implicit-param",
      "model_id": "melix-dev-ocr",
      "suites": ["smoke"],
      "parameters": {
        "task_kind": "image-to-text",
        "sample_size": "1"
      },
      "status": "completed",
      "output_dir": "/tmp/melix/bench/runs/bench-implicit-param",
      "created_at_unix_ms": 1712400000000,
      "updated_at_unix_ms": 1712400001000,
      "suite_metadata": {
        "smoke": {
          "title": "Docs Images OCR Smoke",
          "dataset_path": "huggingface/documentation-images",
          "dataset_name": "default",
          "dataset_split": "train",
          "sample_size": 1,
          "batch_factor": 1
        }
      }
    },
    {
      "schema_version": "melix.serving_benchmark_job.v1",
      "job_id": "bench-implicit-default",
      "model_id": "melix-dev-text",
      "suites": ["smoke"],
      "parameters": {},
      "status": "completed",
      "output_dir": "/tmp/melix/bench/runs/bench-implicit-default",
      "created_at_unix_ms": 1712390000000,
      "updated_at_unix_ms": 1712390001000,
      "suite_metadata": {}
    }
  ],
  "benchmark_results": [
    {
      "schema_version": "melix.serving_benchmark_result.v1",
      "job_id": "bench-implicit-param",
      "suite": "smoke",
      "metrics": [
        {"name": "bench.smoke.ttft_ms", "value": 42.0, "unit": "ms"}
      ],
      "report_path": "/tmp/melix/bench/runs/bench-implicit-param/bench-report.md",
      "report_markdown": "# OCR Bench\\n"
    },
    {
      "schema_version": "melix.serving_benchmark_result.v1",
      "job_id": "bench-implicit-default",
      "suite": "smoke",
      "metrics": [
        {"name": "bench.smoke.tokens_per_second", "value": 12.0, "unit": "tok/s"}
      ],
      "report_path": "/tmp/melix/bench/runs/bench-implicit-default/bench-report.md",
      "report_markdown": "# Default Bench\\n"
    }
  ]
}
"""
