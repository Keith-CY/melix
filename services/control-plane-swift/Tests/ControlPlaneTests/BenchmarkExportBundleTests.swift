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
        #expect(summaryRows[0].jobID == "eval-1")
        #expect(summaryRows[0].modelID == "melix-dev-text")
        #expect(summaryRows[0].taskKind == "text-generation")
        #expect(summaryRows[0].sourceRepo == "HuggingFaceH4/ultrachat_200k")
        #expect(summaryRows[0].suiteID == "mmlu")
        #expect(summaryRows[0].datasetID == "mmlu.dev.v1")
        #expect(summaryRows[0].sampleSize == 8)
        #expect(summaryRows[0].scoreName == "eval.mmlu.accuracy")
        #expect(summaryRows[0].scoreValue == 0.75)
        #expect(summaryRows[0].correctCount == 6)
        #expect(summaryRows[0].incorrectCount == 2)
        #expect(summaryRows[0].durationSeconds == 12.5)
        #expect(summaryRows[0].createdAtUnixMS == 1712400000000)
        #expect(samples.count == 1)
        #expect(samples[0].sampleID == "sample-1")
        #expect(samples[0].taskKind == "text-generation")
        #expect(samples[0].inputModalities == ["text"])
        #expect(samples[0].mediaReferences == [])
        #expect(samples[0].codeLanguage == "python")
        #expect(samples[0].codeEntryPoint == "solve")
        #expect(summaryCSV.contains("job_id,task_kind,source_repo,model_id,suite_id,dataset_id,score_name,score_value,sample_size,correct_count,incorrect_count,duration_seconds,created_at_unix_ms"))
        #expect(summaryCSV.contains("eval-1,text-generation,HuggingFaceH4/ultrachat_200k,melix-dev-text,mmlu,mmlu.dev.v1,eval.mmlu.accuracy,0.75,8,6,2,12.5,1712400000000"))
        #expect(sampleCSV.contains("job_id,suite_id,id,task_kind,correct,expected,predicted,question,raw_response,time_s,parse_status,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail"))
        #expect(sampleCSV.contains("eval-1,mmlu,sample-1,text-generation,true,4,4,2+2?,4,0.01,parsed,text,,python,solve,compiled,ok,ok,passed,2,2,"))
        #expect(sampleJSONL.contains("\"sample_id\":\"sample-1\""))
        #expect(sampleJSONL.contains("\"task_kind\":\"text-generation\""))
        #expect(sampleJSONL.contains("\"input_modalities\":[\"text\"]"))
        #expect(sampleJSONL.contains("\"code_language\":\"python\""))
    }

    @Test("decodes evaluation compare exports and preserves executable-code evidence")
    func decodesEvaluationCompareExports() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(json: benchmarkExportBundleJSON)

        let summaryRows = bundle.evaluationCompareSummaryRows(jobID: "eval-compare-1")
        let samples = bundle.evaluationCompareSampleRows(jobID: "eval-compare-1")
        let summaryCSV = bundle.evaluationCompareSummaryCSV(jobID: "eval-compare-1")
        let samplesCSV = bundle.evaluationCompareSamplesCSV(jobID: "eval-compare-1")
        let samplesJSONL = try bundle.evaluationCompareSamplesJSONL(jobID: "eval-compare-1")

        #expect(summaryRows.count == 1)
        #expect(summaryRows[0].jobID == "eval-compare-1")
        #expect(summaryRows[0].targetModelID == "melix-dev-text-lora-a")
        #expect(summaryRows[0].deltaAccuracy == 0.5)
        #expect(samples.count == 1)
        #expect(samples[0].sampleID == "sample-1")
        #expect(samples[0].codeLanguage == "python")
        #expect(samples[0].baseCodeTestStatus == "failed")
        #expect(samples[0].targetCodeTestStatus == "passed")
        #expect(summaryCSV.contains("job_id,base_model_id,target_model_id,suite_id,dataset_id,sample_size,win_count,loss_count,tie_count,regression_count,base_accuracy,target_accuracy,delta_accuracy,duration_seconds"))
        #expect(summaryCSV.contains("eval-compare-1,melix-dev-text,melix-dev-text-lora-a,mbpp,mbpp.dev.v1,2,1,0,1,0,0.5,1.0,0.5,1.75"))
        #expect(samplesCSV.contains("job_id,suite_id,dataset_id,sample_id,target_model_id,question,expected,base_predicted,target_predicted"))
        #expect(samplesCSV.contains("python,solve,compiled,compiled,ok,ok,ok,ok,failed,passed,1,2,2,2,assertion failed,"))
        #expect(samplesJSONL.contains("\"target_model_id\":\"melix-dev-text-lora-a\""))
        #expect(samplesJSONL.contains("\"base_code_failure_detail\":\"assertion failed\""))
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
        #expect(rows[0].scoreName == "eval.mmlu.accuracy")
        #expect(rows[0].scoreValue == 0.5)
        #expect(rows[0].correctCount == 0)
        #expect(rows[0].incorrectCount == 0)
        #expect(rows[0].durationSeconds == 0)
        #expect(samples.map(\.sampleID) == ["sample-1", "sample-2"])
        #expect(summaryCSV.contains("job_id,task_kind,source_repo,model_id,suite_id,dataset_id,score_name,score_value,sample_size,correct_count,incorrect_count,duration_seconds,created_at_unix_ms"))
        #expect(sampleCSV.contains("job_id,suite_id,id,task_kind,correct,expected,predicted,question,raw_response,time_s,parse_status,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail"))
        #expect(emptyBundle.evaluationSummaryCSV() == "job_id,task_kind,source_repo,model_id,suite_id,dataset_id,score_name,score_value,sample_size,correct_count,incorrect_count,duration_seconds,created_at_unix_ms\n")
        #expect(emptyBundle.evaluationSamplesCSV() == "job_id,suite_id,id,task_kind,correct,expected,predicted,question,raw_response,time_s,parse_status,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail\n")
        #expect(emptyBundle.evaluationCompareSummaryCSV() == "job_id,base_model_id,target_model_id,suite_id,dataset_id,sample_size,win_count,loss_count,tie_count,regression_count,base_accuracy,target_accuracy,delta_accuracy,duration_seconds\n")
        #expect(emptyBundle.evaluationCompareSamplesCSV() == "job_id,suite_id,dataset_id,sample_id,target_model_id,question,expected,base_predicted,target_predicted,base_raw_response,target_raw_response,base_correct,target_correct,outcome,regression,base_time_s,target_time_s,base_parse_status,target_parse_status,code_language,code_entry_point,base_code_compile_status,target_code_compile_status,base_code_runtime_status,target_code_runtime_status,base_code_timeout_status,target_code_timeout_status,base_code_test_status,target_code_test_status,base_code_tests_passed,target_code_tests_passed,base_code_tests_total,target_code_tests_total,base_code_failure_detail,target_code_failure_detail\n")
    }

    @Test("canonical evaluation summary rows are sorted deterministically")
    func canonicalEvaluationSummaryRowsAreSortedDeterministically() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(
            json: canonicalEvaluationSummaryRowsJSON
        )

        let rows = bundle.evaluationSummaryCSVRows()
        let csv = bundle.evaluationSummaryCSV()

        #expect(rows.map(\.jobID) == ["eval-a", "eval-b"])
        #expect(rows[0].createdAtUnixMS == 1712400000000)
        #expect(rows[1].createdAtUnixMS == 1712400000000)
        #expect(csv.contains("job_id,task_kind,source_repo,model_id,suite_id,dataset_id,score_name,score_value,sample_size,correct_count,incorrect_count,duration_seconds,created_at_unix_ms"))
        #expect(csv.contains("eval-a,text-generation,HuggingFaceH4/ultrachat_200k,melix-dev-text,mmlu,mmlu.dev.v1,eval.mmlu.accuracy,0.75,8,6,2,12.5,1712400000000"))
        #expect(csv.contains("eval-b,text-generation,HuggingFaceH4/ultrachat_200k,melix-dev-text,gsm8k,gsm8k.dev.v1,eval.gsm8k.exact_match,0.5,8,5,3,9.75,1712400000000"))
    }

    @Test("canonical evaluation summary rows sort by timestamp before job id")
    func canonicalEvaluationSummaryRowsSortByTimestampBeforeJobID() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(
            json: canonicalEvaluationSummaryTimestampJSON
        )

        let rows = bundle.evaluationSummaryCSVRows()

        #expect(rows.map(\.jobID) == ["eval-a", "eval-b"])
        #expect(rows[0].createdAtUnixMS == 1712400000000)
        #expect(rows[1].createdAtUnixMS == 1712400001000)
    }

    @Test("canonical evaluation compare rows sort by job target and sample identifiers")
    func canonicalEvaluationCompareRowsSortDeterministically() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(
            json: canonicalEvaluationCompareRowsJSON
        )

        let summaryRows = bundle.evaluationCompareSummaryRows()
        let sampleRows = bundle.evaluationCompareSampleRows()

        #expect(summaryRows.map { "\($0.jobID):\($0.targetModelID)" } == [
            "eval-compare-a:target-a",
            "eval-compare-a:target-b",
            "eval-compare-b:target-a",
        ])
        #expect(sampleRows.map { "\($0.jobID):\($0.targetModelID):\($0.sampleID)" } == [
            "eval-compare-a:target-a:sample-1",
            "eval-compare-a:target-a:sample-2",
            "eval-compare-a:target-b:sample-1",
            "eval-compare-b:target-a:sample-1",
        ])
    }

    @Test("decodes benchmark matrix history rows and csv exports")
    func decodesBenchmarkMatrixHistoryRowsAndCSVExports() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(json: benchmarkMatrixExportBundleJSON)

        let history = bundle.benchmarkMatrixHistoryEntries()
        let summaryRows = bundle.benchmarkMatrixSummaryCSVRows()
        let requestRows = bundle.benchmarkMatrixRequestRows()
        let summaryCSV = bundle.benchmarkMatrixSummaryCSV()
        let requestsCSV = bundle.benchmarkMatrixRequestsCSV()

        #expect(history.map(\.jobID) == ["matrix-a", "matrix-b", "matrix-c"])
        #expect(history[0].benchmarkMode == "matrix")
        #expect(history[1].benchmarkMode == "matrix")
        #expect(history[2].benchmarkMode == "matrix")
        #expect(history[0].status == "completed")
        #expect(history[0].requests == 24)
        #expect(history[2].durationSeconds == 60)

        #expect(summaryRows.map(\.jobID) == ["matrix-c", "matrix-a", "matrix-b"])
        #expect(summaryRows[0].taskKind == "text-generation")
        #expect(summaryRows[1].contextLength == 1024)
        #expect(summaryRows[2].batchSize == 4)

        #expect(requestRows.map(\.cellID) == ["cell-0", "cell-1", "cell-2"])
        #expect(requestRows[0].requestIndex == 0)
        #expect(requestRows[1].repeatIndex == 0)
        #expect(requestRows[2].status == "completed")

        #expect(summaryCSV.contains("job_id,task_kind,source_repo,model_id,suite_id,context_length,generation_length,batch_size,cache_profile,reasoning_mode,structured_output_mode,concurrency_level,repeats,requests,duration_seconds,ttft_mean_ms"))
        #expect(summaryCSV.contains("matrix-a,text-generation,HuggingFaceH4/ultrachat_200k,melix-dev-text,smoke,1024,128,2,cold,enabled,plain_text,1,3,24,0,24.45"))
        #expect(requestsCSV.contains("job_id,cell_id,task_kind,suite_id,context_length,generation_length,batch_size,cache_profile,reasoning_mode,structured_output_mode,concurrency_level,repeat_index,request_index,ttft_ms"))
        #expect(requestsCSV.contains("matrix-a,cell-1,text-generation,smoke,1024,128,2,cold,enabled,plain_text,1,0,1,25.0"))
    }

    @Test("benchmark matrix exports emit empty csv headers when there is no matrix history")
    func benchmarkMatrixExportsEmitEmptyCSVHeadersWhenThereIsNoMatrixHistory() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(json: emptyBenchmarkMatrixExportBundleJSON)

        #expect(bundle.benchmarkMatrixHistoryEntries() == [])
        #expect(bundle.benchmarkMatrixSummaryCSV() == "job_id,task_kind,source_repo,model_id,suite_id,context_length,generation_length,batch_size,cache_profile,reasoning_mode,structured_output_mode,concurrency_level,repeats,requests,duration_seconds,ttft_mean_ms,ttft_std_ms,request_latency_mean_ms,request_latency_std_ms,prefill_tokens_per_second_mean,decode_tokens_per_second_mean,throughput_requests_per_second,throughput_tokens_per_second,success_rate,peak_memory_bytes_max,queue_wait_mean_ms,queue_wait_p95_ms,created_at_unix_ms\n")
        #expect(bundle.benchmarkMatrixRequestsCSV() == "job_id,cell_id,task_kind,suite_id,context_length,generation_length,batch_size,cache_profile,reasoning_mode,structured_output_mode,concurrency_level,repeat_index,request_index,ttft_ms,request_latency_ms,prefill_tokens_per_second,decode_tokens_per_second,queue_wait_ms,peak_memory_bytes,status,error_code,created_at_unix_ms\n")
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
      "code_failure_detail": ""
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
      "target_code_failure_detail": ""
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

private let canonicalEvaluationSummaryRowsJSON = """
{
  "export_schema_version": "melix.benchmark_export.v1",
  "evaluation_summary_rows": [
    {
      "job_id": "eval-b",
      "model_id": "melix-dev-text",
      "task_kind": "text-generation",
      "source_repo": "HuggingFaceH4/ultrachat_200k",
      "suite_id": "gsm8k",
      "dataset_id": "gsm8k.dev.v1",
      "sample_size": 8,
      "score_name": "eval.gsm8k.exact_match",
      "score_value": 0.5,
      "correct_count": 5,
      "incorrect_count": 3,
      "duration_seconds": 9.75,
      "created_at_unix_ms": 1712400000000
    },
    {
      "job_id": "eval-a",
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
  ]
}
"""

private let canonicalEvaluationSummaryTimestampJSON = """
{
  "export_schema_version": "melix.benchmark_export.v1",
  "evaluation_summary_rows": [
    {
      "job_id": "eval-b",
      "model_id": "melix-dev-text",
      "task_kind": "text-generation",
      "source_repo": "HuggingFaceH4/ultrachat_200k",
      "suite_id": "gsm8k",
      "dataset_id": "gsm8k.dev.v1",
      "sample_size": 8,
      "score_name": "eval.gsm8k.exact_match",
      "score_value": 0.5,
      "correct_count": 5,
      "incorrect_count": 3,
      "duration_seconds": 9.75,
      "created_at_unix_ms": 1712400001000
    },
    {
      "job_id": "eval-a",
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
  ]
}
"""

private let canonicalEvaluationCompareRowsJSON = """
{
  "export_schema_version": "melix.benchmark_export.v1",
  "evaluation_compare_summary_rows": [
    {
      "schema_version": "melix.evaluation_compare_summary.v1",
      "job_id": "eval-compare-b",
      "base_model_id": "base-b",
      "target_model_id": "target-a",
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
      "duration_seconds": 2.0,
      "metrics": [],
      "report_path": "/tmp/eval-compare-b.md"
    },
    {
      "schema_version": "melix.evaluation_compare_summary.v1",
      "job_id": "eval-compare-a",
      "base_model_id": "base-a",
      "target_model_id": "target-b",
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
      "duration_seconds": 1.0,
      "metrics": [],
      "report_path": "/tmp/eval-compare-a-target-b.md"
    },
    {
      "schema_version": "melix.evaluation_compare_summary.v1",
      "job_id": "eval-compare-a",
      "base_model_id": "base-a",
      "target_model_id": "target-a",
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
      "duration_seconds": 1.0,
      "metrics": [],
      "report_path": "/tmp/eval-compare-a-target-a.md"
    }
  ],
  "evaluation_compare_samples": [
    {
      "schema_version": "melix.evaluation_compare_sample.v1",
      "job_id": "eval-compare-b",
      "suite_id": "mbpp",
      "dataset_id": "mbpp.dev.v1",
      "sample_id": "sample-1",
      "target_model_id": "target-a",
      "question": "Question B",
      "expected": "solve",
      "base_predicted": "base-b",
      "target_predicted": "target-b",
      "base_raw_response": "base-b",
      "target_raw_response": "target-b",
      "base_correct": false,
      "target_correct": true,
      "outcome": "win",
      "regression": false,
      "base_time_s": 0.2,
      "target_time_s": 0.1,
      "base_parse_status": "parsed",
      "target_parse_status": "parsed",
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
      "target_code_failure_detail": ""
    },
    {
      "schema_version": "melix.evaluation_compare_sample.v1",
      "job_id": "eval-compare-a",
      "suite_id": "mbpp",
      "dataset_id": "mbpp.dev.v1",
      "sample_id": "sample-2",
      "target_model_id": "target-a",
      "question": "Question A2",
      "expected": "solve",
      "base_predicted": "base-a2",
      "target_predicted": "target-a2",
      "base_raw_response": "base-a2",
      "target_raw_response": "target-a2",
      "base_correct": false,
      "target_correct": true,
      "outcome": "win",
      "regression": false,
      "base_time_s": 0.2,
      "target_time_s": 0.1,
      "base_parse_status": "parsed",
      "target_parse_status": "parsed",
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
      "target_code_failure_detail": ""
    },
    {
      "schema_version": "melix.evaluation_compare_sample.v1",
      "job_id": "eval-compare-a",
      "suite_id": "mbpp",
      "dataset_id": "mbpp.dev.v1",
      "sample_id": "sample-1",
      "target_model_id": "target-b",
      "question": "Question A target B",
      "expected": "solve",
      "base_predicted": "base-ab",
      "target_predicted": "target-ab",
      "base_raw_response": "base-ab",
      "target_raw_response": "target-ab",
      "base_correct": false,
      "target_correct": true,
      "outcome": "win",
      "regression": false,
      "base_time_s": 0.2,
      "target_time_s": 0.1,
      "base_parse_status": "parsed",
      "target_parse_status": "parsed",
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
      "target_code_failure_detail": ""
    },
    {
      "schema_version": "melix.evaluation_compare_sample.v1",
      "job_id": "eval-compare-a",
      "suite_id": "mbpp",
      "dataset_id": "mbpp.dev.v1",
      "sample_id": "sample-1",
      "target_model_id": "target-a",
      "question": "Question A1",
      "expected": "solve",
      "base_predicted": "base-a1",
      "target_predicted": "target-a1",
      "base_raw_response": "base-a1",
      "target_raw_response": "target-a1",
      "base_correct": false,
      "target_correct": true,
      "outcome": "win",
      "regression": false,
      "base_time_s": 0.2,
      "target_time_s": 0.1,
      "base_parse_status": "parsed",
      "target_parse_status": "parsed",
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
      "target_code_failure_detail": ""
    }
  ]
}
"""

private let benchmarkMatrixExportBundleJSON = """
{
  "export_schema_version": "melix.benchmark_export.v1",
  "benchmark_matrix_jobs": [
    {
      "schema_version": "melix.benchmark_matrix_job.v1",
      "job_id": "matrix-a",
      "model_id": "melix-dev-text",
      "task_kind": "text-generation",
      "source_repo": "HuggingFaceH4/ultrachat_200k",
      "suite_ids": ["smoke"],
      "benchmark_mode": "matrix",
      "status": "completed",
      "output_dir": "/tmp/melix/bench/matrix-runs/matrix-a",
      "created_at_unix_ms": 1712200000000,
      "updated_at_unix_ms": 1712200005000
    },
    {
      "schema_version": "melix.benchmark_matrix_job.v1",
      "job_id": "matrix-b",
      "model_id": "melix-dev-text",
      "task_kind": "text-generation",
      "source_repo": "HuggingFaceH4/ultrachat_200k",
      "suite_ids": ["latency"],
      "benchmark_mode": "",
      "status": "completed",
      "output_dir": "/tmp/melix/bench/matrix-runs/matrix-b",
      "created_at_unix_ms": 1712200000000,
      "updated_at_unix_ms": 1712200007000
    },
    {
      "schema_version": "melix.benchmark_matrix_job.v1",
      "job_id": "matrix-c",
      "model_id": "melix-dev-text",
      "task_kind": "text-generation",
      "source_repo": "HuggingFaceH4/ultrachat_200k",
      "suite_ids": ["smoke"],
      "benchmark_mode": "matrix",
      "status": "completed",
      "output_dir": "/tmp/melix/bench/matrix-runs/matrix-c",
      "created_at_unix_ms": 1712199999000,
      "updated_at_unix_ms": 1712199999500
    }
  ],
  "benchmark_matrix_summary_rows": [
    {
      "job_id": "matrix-a",
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
    },
    {
      "job_id": "matrix-b",
      "task_kind": "text-generation",
      "source_repo": "HuggingFaceH4/ultrachat_200k",
      "model_id": "melix-dev-text",
      "suite_id": "latency",
      "context_length": 2048,
      "generation_length": 256,
      "batch_size": 4,
      "cache_profile": "warm",
      "reasoning_mode": "disabled",
      "structured_output_mode": "json_schema",
      "concurrency_level": 2,
      "repeats": 2,
      "requests": 48,
      "duration_seconds": 0,
      "ttft_mean_ms": 33.0,
      "ttft_std_ms": 0.8,
      "request_latency_mean_ms": 92.1,
      "request_latency_std_ms": 4.6,
      "prefill_tokens_per_second_mean": 1500.0,
      "decode_tokens_per_second_mean": 61.1,
      "throughput_requests_per_second": 4.1,
      "throughput_tokens_per_second": 244.0,
      "success_rate": 1.0,
      "peak_memory_bytes_max": 3221225472,
      "queue_wait_mean_ms": 2.0,
      "queue_wait_p95_ms": 5.5,
      "created_at_unix_ms": 1712200000000
    },
    {
      "job_id": "matrix-c",
      "task_kind": "text-generation",
      "source_repo": "HuggingFaceH4/ultrachat_200k",
      "model_id": "melix-dev-text",
      "suite_id": "smoke",
      "context_length": 512,
      "generation_length": 64,
      "batch_size": 1,
      "cache_profile": "cold",
      "reasoning_mode": "enabled",
      "structured_output_mode": "plain_text",
      "concurrency_level": 1,
      "repeats": 1,
      "requests": 0,
      "duration_seconds": 60,
      "ttft_mean_ms": 19.2,
      "ttft_std_ms": 0.5,
      "request_latency_mean_ms": 48.0,
      "request_latency_std_ms": 1.1,
      "prefill_tokens_per_second_mean": 1700.0,
      "decode_tokens_per_second_mean": 66.0,
      "throughput_requests_per_second": 2.2,
      "throughput_tokens_per_second": 145.0,
      "success_rate": 1.0,
      "peak_memory_bytes_max": 1073741824,
      "queue_wait_mean_ms": 1.0,
      "queue_wait_p95_ms": 2.0,
      "created_at_unix_ms": 1712199999000
    }
  ],
  "benchmark_matrix_request_rows": [
    {
      "job_id": "matrix-c",
      "cell_id": "cell-0",
      "task_kind": "text-generation",
      "suite_id": "smoke",
      "context_length": 512,
      "generation_length": 64,
      "batch_size": 1,
      "cache_profile": "cold",
      "reasoning_mode": "enabled",
      "structured_output_mode": "plain_text",
      "concurrency_level": 1,
      "repeat_index": 0,
      "request_index": 0,
      "ttft_ms": 19.0,
      "request_latency_ms": 47.0,
      "prefill_tokens_per_second": 1710.0,
      "decode_tokens_per_second": 66.2,
      "queue_wait_ms": 1.0,
      "peak_memory_bytes": 1073741824,
      "status": "completed",
      "error_code": "",
      "created_at_unix_ms": 1712199999000
    },
    {
      "job_id": "matrix-a",
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
      "request_index": 1,
      "ttft_ms": 25.0,
      "request_latency_ms": 87.0,
      "prefill_tokens_per_second": 1390.0,
      "decode_tokens_per_second": 57.0,
      "queue_wait_ms": 5.0,
      "peak_memory_bytes": 2147483648,
      "status": "completed",
      "error_code": "",
      "created_at_unix_ms": 1712200000000
    },
    {
      "job_id": "matrix-a",
      "cell_id": "cell-2",
      "task_kind": "text-generation",
      "suite_id": "smoke",
      "context_length": 1024,
      "generation_length": 128,
      "batch_size": 2,
      "cache_profile": "cold",
      "reasoning_mode": "enabled",
      "structured_output_mode": "plain_text",
      "concurrency_level": 1,
      "repeat_index": 1,
      "request_index": 0,
      "ttft_ms": 24.4,
      "request_latency_ms": 88.0,
      "prefill_tokens_per_second": 1401.0,
      "decode_tokens_per_second": 58.0,
      "queue_wait_ms": 5.1,
      "peak_memory_bytes": 2147483648,
      "status": "completed",
      "error_code": "",
      "created_at_unix_ms": 1712200000000
    }
  ]
}
"""

private let emptyBenchmarkMatrixExportBundleJSON = """
{
  "export_schema_version": "melix.benchmark_export.v1",
  "benchmark_matrix_jobs": [],
  "benchmark_matrix_summary_rows": [],
  "benchmark_matrix_request_rows": []
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
