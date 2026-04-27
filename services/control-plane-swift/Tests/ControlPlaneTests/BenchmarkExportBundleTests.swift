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
        #expect(summaryRows[0].primaryScoreName == "typed_score_mean")
        #expect(summaryRows[0].primaryScoreValue == 0.75)
        #expect(summaryRows[0].extractionSuccessCount == 8)
        #expect(summaryRows[0].validationSuccessCount == 8)
        #expect(summaryRows[0].scoredSampleCount == 8)
        #expect(summaryRows[0].failureCount == 0)
        #expect(summaryRows[0].effectThreshold == 0.1)
        #expect(summaryRows[0].verdict == "improvement")
        #expect(summaryRows[0].bootstrapLowerBound == 0.12)
        #expect(summaryRows[0].bootstrapUpperBound == 0.41)
        #expect(summaryRows[0].analyticalLowerBound == 0.1)
        #expect(summaryRows[0].analyticalUpperBound == 0.38)
        #expect(summaryRows[0].durationSeconds == 12.5)
        #expect(summaryRows[0].createdAtUnixMS == 1712400000000)
        #expect(samples.count == 1)
        #expect(samples[0].sampleID == "sample-1")
        #expect(samples[0].taskKind == "text-generation")
        #expect(samples[0].inputModalities == ["text"])
        #expect(samples[0].mediaReferences == [])
        #expect(samples[0].codeLanguage == "python")
        #expect(samples[0].codeEntryPoint == "solve")
        #expect(samples[0].categoryLabel == "math")
        #expect(samples[0].subjectLabel == "algebra")
        #expect(summaryCSV.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,primary_score_name,primary_score_value,extraction_success_count,validation_success_count,scored_sample_count,failure_count,effect_threshold,verdict,bootstrap_lower_bound,bootstrap_upper_bound,analytical_lower_bound,analytical_upper_bound,duration_seconds,created_at_unix_ms"))
        #expect(summaryCSV.contains("eval-1,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,mmlu,mmlu.dev.v1,8,typed_score_mean,0.75,8,8,8,0,0.1,improvement,0.12,0.41,0.1,0.38,12.5,1712400000000"))
        #expect(sampleCSV.contains("job_id,suite_id,id,task_kind,target,extracted_result,input_text,raw_response,typed_score,time_s,extraction_status,validation_status,failure_reason,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail,category_label,subject_label"))
        #expect(sampleCSV.contains("eval-1,mmlu,sample-1,text-generation,4,4,2+2?,4,1.0,0.01,extracted,validated,,text,,python,solve,compiled,ok,ok,passed,2,2,,math,algebra"))
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
        #expect(samples[0].categoryLabel == "math")
        #expect(samples[0].subjectLabel == "algebra")
        #expect(summaryCSV.contains("job_id,base_model_id,target_model_id,suite_id,dataset_id,sample_size,win_count,loss_count,tie_count,regression_count,base_accuracy,target_accuracy,delta_accuracy,duration_seconds"))
        #expect(summaryCSV.contains("eval-compare-1,melix-dev-text,melix-dev-text-lora-a,mbpp,mbpp.dev.v1,2,1,0,1,0,0.5,1.0,0.5,1.75"))
        #expect(samplesCSV.contains("job_id,suite_id,dataset_id,sample_id,target_model_id,input_text,target,base_extracted_result,target_extracted_result"))
        #expect(samplesCSV.contains("python,solve,compiled,compiled,ok,ok,ok,ok,failed,passed,1,2,2,2,assertion failed,,math,algebra"))
        #expect(samplesJSONL.contains("\"target_model_id\":\"melix-dev-text-lora-a\""))
        #expect(samplesJSONL.contains("\"base_code_failure_detail\":\"assertion failed\""))
    }

    @Test("decodes flexible string-backed evaluation summary doubles")
    func decodesFlexibleStringBackedEvaluationSummaryDoubles() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(
            json: flexibleEvaluationSummaryDoublesJSON
        )

        let row = try #require(bundle.evaluationSummaryCSVRows().first)

        #expect(row.effectThreshold == 0.1)
        #expect(row.bootstrapLowerBound == nil)
        #expect(row.bootstrapUpperBound == 0.41)
        #expect(row.analyticalLowerBound == nil)
        #expect(row.analyticalUpperBound == 0.38)
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
        #expect(rows[0].primaryScoreName == "eval.mmlu.accuracy")
        #expect(rows[0].primaryScoreValue == 0.5)
        #expect(rows[0].extractionSuccessCount == 0)
        #expect(rows[0].validationSuccessCount == 0)
        #expect(rows[0].durationSeconds == 0)
        #expect(samples.map(\.sampleID) == ["sample-1", "sample-2"])
        #expect(summaryCSV.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,primary_score_name,primary_score_value,extraction_success_count,validation_success_count,scored_sample_count,failure_count,effect_threshold,verdict,bootstrap_lower_bound,bootstrap_upper_bound,analytical_lower_bound,analytical_upper_bound,duration_seconds,created_at_unix_ms"))
        #expect(sampleCSV.contains("job_id,suite_id,id,task_kind,target,extracted_result,input_text,raw_response,typed_score,time_s,extraction_status,validation_status,failure_reason,input_modalities,media_references,code_language,code_entry_point,code_compile_status,code_runtime_status,code_timeout_status,code_test_status,code_tests_passed,code_tests_total,code_failure_detail,category_label,subject_label"))
        #expect(emptyBundle.evaluationSummaryCSV() == "job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,primary_score_name,primary_score_value,extraction_success_count,validation_success_count,scored_sample_count,failure_count,effect_threshold,verdict,bootstrap_lower_bound,bootstrap_upper_bound,analytical_lower_bound,analytical_upper_bound,duration_seconds,created_at_unix_ms\n")
        #expect(emptyBundle.evaluationSamplesCSV().contains("sample_render_ms,inference_ms,extraction_ms,validation_ms,scoring_ms,raw_response_chars,extracted_result_chars,failure_stage"))
        #expect(emptyBundle.evaluationCompareSummaryCSV() == "job_id,base_model_id,target_model_id,suite_id,dataset_id,sample_size,win_count,loss_count,tie_count,regression_count,base_accuracy,target_accuracy,delta_accuracy,duration_seconds\n")
        #expect(emptyBundle.evaluationCompareSamplesCSV() == "job_id,suite_id,dataset_id,sample_id,target_model_id,input_text,target,base_extracted_result,target_extracted_result,base_raw_response,target_raw_response,base_typed_score,target_typed_score,outcome,regression_kind,base_time_s,target_time_s,base_extraction_status,target_extraction_status,base_validation_status,target_validation_status,base_failure_reason,target_failure_reason,base_parse_status,target_parse_status,code_language,code_entry_point,base_code_compile_status,target_code_compile_status,base_code_runtime_status,target_code_runtime_status,base_code_timeout_status,target_code_timeout_status,base_code_test_status,target_code_test_status,base_code_tests_passed,target_code_tests_passed,base_code_tests_total,target_code_tests_total,base_code_failure_detail,target_code_failure_detail,category_label,subject_label\n")
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
        #expect(csv.contains("job_id,model_id,task_kind,source_repo,suite_id,dataset_id,sample_size,primary_score_name,primary_score_value,extraction_success_count,validation_success_count,scored_sample_count,failure_count,effect_threshold,verdict,bootstrap_lower_bound,bootstrap_upper_bound,analytical_lower_bound,analytical_upper_bound,duration_seconds,created_at_unix_ms"))
        #expect(csv.contains("eval-a,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,mmlu,mmlu.dev.v1,8,typed_score_mean,0.75,8,8,8,0,0.1,improvement,0.12,0.41,0.1,0.38,12.5,1712400000000"))
        #expect(csv.contains("eval-b,melix-dev-text,text-generation,HuggingFaceH4/ultrachat_200k,gsm8k,gsm8k.dev.v1,8,typed_score_mean,0.5,8,8,8,0,0.05,inconclusive,-0.04,0.16,-0.02,0.14,9.75,1712400000000"))
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
        #expect(bundle.benchmarkMatrixSummaryCSV().contains("cell_wall_ms,completed_count,failed_count,ttft_p50_ms,ttft_p95_ms,request_latency_p50_ms,request_latency_p95_ms"))
        #expect(bundle.benchmarkMatrixRequestsCSV().contains("dataset_materialize_ms,prompt_render_ms,warmup_ms,prefill_ms,decode_ms,tokens_in,tokens_out,first_token_index,cache_hit,runtime_kind,error_stage,speculative_acceptance_rate"))
    }

    @Test("decodes additive probe fields in benchmark matrix and evaluation exports")
    func decodesAdditiveProbeFieldsInBenchmarkMatrixAndEvaluationExports() throws {
        let bundle = try ControlPlaneBenchmarkExportBundle.decode(json: benchmarkEvaluationProbeBundleJSON)

        let summary = try #require(bundle.benchmarkMatrixSummaryCSVRows().first)
        let request = try #require(bundle.benchmarkMatrixRequestRows().first)
        let sample = try #require(bundle.evaluationSampleRows().first)
        let matrixJob = try #require(bundle.benchmarkMatrixJobs.first)

        #expect(matrixJob.parameters["runtime_kind"] == "swift-text")
        #expect(matrixJob.parameters["runtime_model_id"] == "target/live")
        #expect(summary.cellWallMS == 456.7)
        #expect(summary.completedCount == 3)
        #expect(summary.failedCount == 1)
        #expect(summary.ttftP50MS == 21.0)
        #expect(summary.requestLatencyP95MS == 91.0)
        #expect(request.datasetMaterializeMS == 1.1)
        #expect(request.promptRenderMS == 2.2)
        #expect(request.prefillMS == 4.4)
        #expect(request.decodeMS == 5.5)
        #expect(request.tokensIn == 128)
        #expect(request.tokensOut == 32)
        #expect(request.firstTokenIndex == 7)
        #expect(request.cacheHit)
        #expect(request.runtimeKind == "swift-text")
        #expect(request.errorStage == "decode")
        #expect(request.speculativeAcceptanceRate == 0.8)
        #expect(request.speculativeRollbackRate == 0.2)
        #expect(request.speculativeAcceptedTokens == 24)
        #expect(request.speculativeRejectedTokens == 6)
        #expect(request.speculativeFallbackCount == 1)
        #expect(request.speculativeNumDraftTokens == 4)
        #expect(request.speculativeDraftModelConfigured)
        #expect(request.speculativeDraftProposeMS == 8.8)
        #expect(request.speculativeTargetVerifyMS == 9.9)
        #expect(request.dflashEnabled)
        #expect(request.dflashBlockSize == 16)
        #expect(request.dflashRollbackCount == 2)
        #expect(request.dflashTargetHiddenLayers == 12)
        #expect(sample.sampleRenderMS == 10.1)
        #expect(sample.inferenceMS == 20.2)
        #expect(sample.extractionMS == 30.3)
        #expect(sample.validationMS == 40.4)
        #expect(sample.scoringMS == 50.5)
        #expect(sample.rawResponseChars == 11)
        #expect(sample.extractedResultChars == 3)
        #expect(sample.failureStage == "scoring")
        #expect(bundle.benchmarkMatrixSummaryCSV().contains("456.7,3,1,21.0,29.0,80.0,91.0"))
        #expect(bundle.benchmarkMatrixRequestsCSV().contains("1.1,2.2,3.3,4.4,5.5,128,32,7,true,swift-text,decode,0.8,0.2,24,6,1,4,true,8.8,9.9,true,16,2,12"))
        #expect(bundle.evaluationSamplesCSV().contains("10.1,20.2,30.3,40.4,50.5,11,3,scoring"))
        let sampleJSONL = try bundle.evaluationSamplesJSONL()
        #expect(sampleJSONL.contains(#""failure_stage":"scoring""#))
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
      "primary_score_name": "typed_score_mean",
      "primary_score_value": 0.75,
      "extraction_success_count": 8,
      "validation_success_count": 8,
      "scored_sample_count": 8,
      "failure_count": 0,
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
      "schema_version": "melix.evaluation_sample.v2",
      "job_id": "eval-1",
      "suite_id": "mmlu",
      "dataset_id": "mmlu.dev.v1",
      "sample_id": "sample-1",
      "system": "",
      "input_text": "2+2?",
      "target": "4",
      "raw_response": "4",
      "extracted_result": "4",
      "typed_score": 1.0,
      "time_s": 0.01,
      "extraction_status": "extracted",
      "validation_status": "validated",
      "failure_reason": "",
      "task_kind": "text-generation",
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
      "schema_version": "melix.evaluation_compare_job.v2",
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
      "schema_version": "melix.evaluation_compare_summary.v2",
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
      "schema_version": "melix.evaluation_compare_sample.v2",
      "job_id": "eval-compare-1",
      "suite_id": "mbpp",
      "dataset_id": "mbpp.dev.v1",
      "sample_id": "sample-1",
      "target_model_id": "melix-dev-text-lora-a",
      "input_text": "Write solve(n) that returns n",
      "target": "solve",
      "base_extracted_result": "def solve(n):\\n    return 0",
      "target_extracted_result": "def solve(n):\\n    return n",
      "base_raw_response": "def solve(n):\\n    return 0",
      "target_raw_response": "def solve(n):\\n    return n",
      "base_typed_score": 0.0,
      "target_typed_score": 1.0,
      "outcome": "win",
      "regression_kind": "",
      "base_time_s": 0.11,
      "target_time_s": 0.09,
      "base_extraction_status": "extracted",
      "target_extraction_status": "extracted",
      "base_validation_status": "validated",
      "target_validation_status": "validated",
      "base_failure_reason": "",
      "target_failure_reason": "",
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
      "schema_version": "melix.evaluation_sample.v2",
      "job_id": "eval-a",
      "suite_id": "mmlu",
      "dataset_id": "mmlu.dev.v1",
      "sample_id": "sample-2",
      "system": "",
      "input_text": "2+2?",
      "target": "4",
      "raw_response": "4",
      "extracted_result": "4",
      "typed_score": 1.0,
      "time_s": 0.02,
      "extraction_status": "extracted",
      "validation_status": "validated",
      "failure_reason": ""
    },
    {
      "schema_version": "melix.evaluation_sample.v2",
      "job_id": "eval-a",
      "suite_id": "mmlu",
      "dataset_id": "mmlu.dev.v1",
      "sample_id": "sample-1",
      "system": "",
      "input_text": "3+3?",
      "target": "6",
      "raw_response": "6",
      "extracted_result": "6",
      "typed_score": 1.0,
      "time_s": 0.01,
      "extraction_status": "extracted",
      "validation_status": "validated",
      "failure_reason": ""
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

private let flexibleEvaluationSummaryDoublesJSON = """
{
  "export_schema_version": "melix.benchmark_export.v1",
  "evaluation_summary_rows": [
    {
      "job_id": "eval-flex",
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
      "effect_threshold": "0.1",
      "verdict": "improvement",
      "bootstrap_lower_bound": "",
      "bootstrap_upper_bound": "0.41",
      "analytical_upper_bound": "0.38",
      "duration_seconds": 12.5,
      "created_at_unix_ms": 1712400000000
    }
  ]
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
      "primary_score_name": "typed_score_mean",
      "primary_score_value": 0.5,
      "extraction_success_count": 8,
      "validation_success_count": 8,
      "scored_sample_count": 8,
      "failure_count": 0,
      "effect_threshold": 0.05,
      "verdict": "inconclusive",
      "bootstrap_lower_bound": -0.04,
      "bootstrap_upper_bound": 0.16,
      "analytical_lower_bound": -0.02,
      "analytical_upper_bound": 0.14,
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
      "primary_score_name": "typed_score_mean",
      "primary_score_value": 0.75,
      "extraction_success_count": 8,
      "validation_success_count": 8,
      "scored_sample_count": 8,
      "failure_count": 0,
      "effect_threshold": 0.1,
      "verdict": "improvement",
      "bootstrap_lower_bound": 0.12,
      "bootstrap_upper_bound": 0.41,
      "analytical_lower_bound": 0.1,
      "analytical_upper_bound": 0.38,
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
      "primary_score_name": "typed_score_mean",
      "primary_score_value": 0.5,
      "extraction_success_count": 8,
      "validation_success_count": 8,
      "scored_sample_count": 8,
      "failure_count": 0,
      "effect_threshold": 0.05,
      "verdict": "inconclusive",
      "bootstrap_lower_bound": -0.04,
      "bootstrap_upper_bound": 0.16,
      "analytical_lower_bound": -0.02,
      "analytical_upper_bound": 0.14,
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
      "primary_score_name": "typed_score_mean",
      "primary_score_value": 0.75,
      "extraction_success_count": 8,
      "validation_success_count": 8,
      "scored_sample_count": 8,
      "failure_count": 0,
      "effect_threshold": 0.1,
      "verdict": "improvement",
      "bootstrap_lower_bound": 0.12,
      "bootstrap_upper_bound": 0.41,
      "analytical_lower_bound": 0.1,
      "analytical_upper_bound": 0.38,
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

private let benchmarkEvaluationProbeBundleJSON = """
{
  "export_schema_version": "melix.benchmark_export.v1",
  "benchmark_matrix_jobs": [
    {
      "schema_version": "melix.benchmark_matrix_job.v1",
      "job_id": "matrix-probe",
      "model_id": "melix-dev-text",
      "task_kind": "text-generation",
      "source_repo": "fixture/repo",
      "suite_ids": ["smoke"],
      "benchmark_mode": "matrix",
      "status": "completed",
      "output_dir": "/tmp/melix/bench/matrix-runs/matrix-probe",
      "created_at_unix_ms": 1712600000000,
      "updated_at_unix_ms": 1712600001000,
      "parameters": {
        "runtime_kind": "swift-text",
        "runtime_model_id": "target/live"
      }
    }
  ],
  "benchmark_matrix_summary_rows": [
    {
      "job_id": "matrix-probe",
      "task_kind": "text-generation",
      "source_repo": "fixture/repo",
      "model_id": "melix-dev-text",
      "suite_id": "smoke",
      "context_length": 1024,
      "generation_length": 128,
      "batch_size": 1,
      "cache_profile": "warm",
      "reasoning_mode": "enabled",
      "structured_output_mode": "plain_text",
      "concurrency_level": 1,
      "repeats": 1,
      "requests": 4,
      "duration_seconds": 1,
      "ttft_mean_ms": 25.0,
      "request_latency_mean_ms": 85.0,
      "cell_wall_ms": 456.7,
      "completed_count": 3,
      "failed_count": 1,
      "ttft_p50_ms": 21.0,
      "ttft_p95_ms": 29.0,
      "request_latency_p50_ms": 80.0,
      "request_latency_p95_ms": 91.0,
      "created_at_unix_ms": 1712600000000
    }
  ],
  "benchmark_matrix_request_rows": [
    {
      "job_id": "matrix-probe",
      "cell_id": "cell-0",
      "task_kind": "text-generation",
      "suite_id": "smoke",
      "context_length": 1024,
      "generation_length": 128,
      "batch_size": 1,
      "cache_profile": "warm",
      "reasoning_mode": "enabled",
      "structured_output_mode": "plain_text",
      "concurrency_level": 1,
      "repeat_index": 0,
      "request_index": 0,
      "ttft_ms": 21.0,
      "request_latency_ms": 80.0,
      "prefill_tokens_per_second": 1200.0,
      "decode_tokens_per_second": 50.0,
      "queue_wait_ms": 0.0,
      "peak_memory_bytes": 4096,
      "status": "failed",
      "error_code": "decode_error",
      "dataset_materialize_ms": 1.1,
      "prompt_render_ms": 2.2,
      "warmup_ms": 3.3,
      "prefill_ms": 4.4,
      "decode_ms": 5.5,
      "tokens_in": 128,
      "tokens_out": 32,
      "first_token_index": 7,
      "cache_hit": true,
      "runtime_kind": "swift-text",
      "error_stage": "decode",
      "speculative_acceptance_rate": 0.8,
      "speculative_rollback_rate": 0.2,
      "speculative_accepted_tokens": 24,
      "speculative_rejected_tokens": 6,
      "speculative_fallback_count": 1,
      "speculative_num_draft_tokens": 4,
      "speculative_draft_model_configured": true,
      "speculative_draft_propose_ms": 8.8,
      "speculative_target_verify_ms": 9.9,
      "dflash_enabled": true,
      "dflash_block_size": 16,
      "dflash_rollback_count": 2,
      "dflash_target_hidden_layers": 12,
      "created_at_unix_ms": 1712600000000
    }
  ],
  "evaluation_samples": [
    {
      "schema_version": "melix.evaluation_sample.v2",
      "job_id": "eval-probe",
      "suite_id": "mmlu",
      "dataset_id": "mmlu.dev.v1",
      "sample_id": "sample-1",
      "input_text": "2+2?",
      "target": "4",
      "raw_response": "wrong answer",
      "extracted_result": "bad",
      "typed_score": 0.0,
      "time_s": 0.2,
      "extraction_status": "extracted",
      "validation_status": "validated",
      "failure_reason": "wrong answer",
      "sample_render_ms": 10.1,
      "inference_ms": 20.2,
      "extraction_ms": 30.3,
      "validation_ms": 40.4,
      "scoring_ms": 50.5,
      "raw_response_chars": 11,
      "extracted_result_chars": 3,
      "failure_stage": "scoring"
    }
  ]
}
"""
