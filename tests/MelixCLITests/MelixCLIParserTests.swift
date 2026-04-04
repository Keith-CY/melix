import Testing

@testable import MelixCLICore
import MelixControlPlaneCore

@Suite("Melix CLI Parser")
struct MelixCLIParserTests {
    @Test("parses server snapshot and pause commands")
    func parsesServerSnapshotAndPauseCommands() throws {
        let snapshotCommand = try MelixCLIParser.parse([
            "server",
            "snapshot",
            "--json",
        ])
        let pauseCommand = try MelixCLIParser.parse([
            "server",
            "pause",
        ])

        guard case .serverSnapshot(let snapshotOptions) = snapshotCommand else {
            Issue.record("Expected serverSnapshot command")
            return
        }
        guard case .serverPause(let pauseOptions) = pauseCommand else {
            Issue.record("Expected serverPause command")
            return
        }

        #expect(snapshotOptions.json)
        #expect(pauseOptions.serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
        #expect(!pauseOptions.json)
    }

    @Test("parses server start resume wake and stop commands")
    func parsesServerLifecycleCommands() throws {
        let startCommand = try MelixCLIParser.parse([
            "server",
            "start",
            "--server-session-id", "server-session-2",
            "--json",
        ])
        let resumeCommand = try MelixCLIParser.parse([
            "server",
            "resume",
            "--server-session-id", "server-session-3",
        ])
        let wakeCommand = try MelixCLIParser.parse([
            "server",
            "wake",
            "--server-session-id", "server-session-4",
        ])
        let stopCommand = try MelixCLIParser.parse([
            "server",
            "stop",
            "--server-session-id", "server-session-5",
        ])

        guard case .serverStart(let startOptions) = startCommand else {
            Issue.record("Expected serverStart command")
            return
        }
        guard case .serverResume(let resumeOptions) = resumeCommand else {
            Issue.record("Expected serverResume command")
            return
        }
        guard case .serverWake(let wakeOptions) = wakeCommand else {
            Issue.record("Expected serverWake command")
            return
        }
        guard case .serverStop(let stopOptions) = stopCommand else {
            Issue.record("Expected serverStop command")
            return
        }

        #expect(startOptions.serverSessionID == "server-session-2")
        #expect(startOptions.json)
        #expect(resumeOptions.serverSessionID == "server-session-3")
        #expect(!resumeOptions.json)
        #expect(wakeOptions.serverSessionID == "server-session-4")
        #expect(stopOptions.serverSessionID == "server-session-5")
    }

    @Test("parses server idle-policy command with explicit thresholds")
    func parsesServerIdlePolicyCommand() throws {
        let command = try MelixCLIParser.parse([
            "server",
            "set-idle-policy",
            "--server-session-id", "server-session-2",
            "--auto-sleep", "true",
            "--light-sleep-after", "60",
            "--deep-sleep-after", "600",
            "--json",
        ])

        guard case .serverSetIdlePolicy(let options) = command else {
            Issue.record("Expected serverSetIdlePolicy command")
            return
        }

        #expect(options.serverSessionID == "server-session-2")
        #expect(options.autoSleepEnabled)
        #expect(options.lightSleepAfterSeconds == 60)
        #expect(options.deepSleepAfterSeconds == 600)
        #expect(options.json)
    }

    @Test("parses server idle-policy command with auto-sleep disabled")
    func parsesServerIdlePolicyCommandWithFalseFlag() throws {
        let command = try MelixCLIParser.parse([
            "server",
            "set-idle-policy",
            "--auto-sleep", "false",
            "--light-sleep-after", "30",
            "--deep-sleep-after", "300",
        ])

        guard case .serverSetIdlePolicy(let options) = command else {
            Issue.record("Expected serverSetIdlePolicy command")
            return
        }

        #expect(options.serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
        #expect(options.autoSleepEnabled == false)
        #expect(options.lightSleepAfterSeconds == 30)
        #expect(options.deepSleepAfterSeconds == 300)
    }

    @Test("parses lora list with an explicit model id")
    func parsesLoraListCommand() throws {
        let command = try MelixCLIParser.parse([
            "lora",
            "list",
            "--model-id", "melix-dev-text",
            "--json",
        ])

        guard case .loraList(let options) = command else {
            Issue.record("Expected loraList command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.json)
    }

    @Test("parses lora train with all supported tuning parameters")
    func parsesLoraTrainCommand() throws {
        let command = try MelixCLIParser.parse([
            "lora",
            "train",
            "--model-id", "melix-dev-text",
            "--dataset-uri", "/tmp/data/alpaca.jsonl",
            "--adapter-name", "demo-adapter",
            "--target-repo", "melix/demo-adapter",
            "--rank", "8",
            "--alpha", "16",
            "--dropout", "0.05",
            "--target-modules", "q_proj,k_proj,v_proj",
            "--num-layers", "12",
            "--batch-size", "2",
            "--epochs", "3",
            "--learning-rate", "0.0001",
            "--max-seq-length", "4096",
            "--response-only",
            "--gradient-checkpointing",
            "--json",
        ])

        guard case .loraTrain(let options) = command else {
            Issue.record("Expected loraTrain command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.datasetSourceKind == "local_package")
        #expect(options.datasetURI == "/tmp/data/alpaca.jsonl")
        #expect(options.adapterName == "demo-adapter")
        #expect(options.targetRepo == "melix/demo-adapter")
        #expect(options.parameters["rank"] == "8")
        #expect(options.parameters["alpha"] == "16")
        #expect(options.parameters["dropout"] == "0.05")
        #expect(options.parameters["target_modules"] == "q_proj,k_proj,v_proj")
        #expect(options.parameters["num_layers"] == "12")
        #expect(options.parameters["batch_size"] == "2")
        #expect(options.parameters["epochs"] == "3")
        #expect(options.parameters["learning_rate"] == "0.0001")
        #expect(options.parameters["max_seq_length"] == "4096")
        #expect(options.parameters["response_only"] == "true")
        #expect(options.parameters["gradient_checkpointing"] == "true")
        #expect(options.json)
    }

    @Test("parses lora train with a Hugging Face dataset source and feature mapping")
    func parsesLoraTrainCommandForHFDataset() throws {
        let command = try MelixCLIParser.parse([
            "lora",
            "train",
            "--model-id", "melix-dev-text",
            "--hf-dataset-path", "HuggingFaceH4/ultrachat_200k",
            "--hf-dataset-name", "default",
            "--hf-dataset-revision", "main",
            "--hf-train-split", "train_sft",
            "--hf-valid-split", "test_sft",
            "--text-feature", "messages",
            "--prompt-feature", "prompt",
            "--completion-feature", "completion",
            "--chat-feature", "messages",
            "--adapter-name", "hf-demo-adapter",
            "--mask-prompt",
            "--derived-model-alias", "melix-dev-text-ultrachat",
        ])

        guard case .loraTrain(let options) = command else {
            Issue.record("Expected loraTrain command")
            return
        }

        #expect(options.datasetSourceKind == "hf_dataset")
        #expect(options.datasetURI.isEmpty)
        #expect(options.adapterName == "hf-demo-adapter")
        #expect(options.parameters["hf_dataset_path"] == "HuggingFaceH4/ultrachat_200k")
        #expect(options.parameters["hf_dataset_name"] == "default")
        #expect(options.parameters["hf_dataset_revision"] == "main")
        #expect(options.parameters["hf_train_split"] == "train_sft")
        #expect(options.parameters["hf_valid_split"] == "test_sft")
        #expect(options.parameters["text_feature"] == "messages")
        #expect(options.parameters["prompt_feature"] == "prompt")
        #expect(options.parameters["completion_feature"] == "completion")
        #expect(options.parameters["chat_feature"] == "messages")
        #expect(options.parameters["mask_prompt"] == "true")
        #expect(options.parameters["derived_model_alias"] == "melix-dev-text-ultrachat")
    }

    @Test("parses bench run with an explicit model target suites and tuning parameters")
    func parsesBenchRunCommand() throws {
        let command = try MelixCLIParser.parse([
            "bench",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "smoke",
            "--suite", "latency",
            "--context-length", "2048",
            "--generation-length", "256",
            "--sample-size", "8",
            "--batch-factor", "2",
            "--json",
        ])

        guard case .benchRun(let options) = command else {
            Issue.record("Expected benchRun command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.hfRepoID.isEmpty)
        #expect(options.suites == ["smoke", "latency"])
        #expect(options.contextLengths == [2048])
        #expect(options.generationLength == 256)
        #expect(options.batchSizes.isEmpty)
        #expect(options.repeats == 1)
        #expect(options.cacheProfile.isEmpty)
        #expect(options.reasoningMode.isEmpty)
        #expect(options.structuredOutputMode.isEmpty)
        #expect(options.parameters["sample_size"] == "8")
        #expect(options.parameters["batch_factor"] == "2")
        #expect(options.json)
    }

    @Test("parses bench run with canonical sweep and tuning inputs")
    func parsesBenchRunWithCanonicalSweepAndTuningInputs() throws {
        let command = try MelixCLIParser.parse([
            "bench",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "smoke",
            "--context-length", "4096",
            "--context-length", "1024",
            "--generation-length", "128",
            "--batch-size", "4",
            "--batch-size", "2",
            "--repeats", "3",
            "--cache-profile", "partial_prefix",
            "--reasoning-mode", "enabled",
            "--structured-output-mode", "json_schema",
        ])

        guard case .benchRun(let options) = command else {
            Issue.record("Expected benchRun command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.suites == ["smoke"])
        #expect(options.contextLengths == [1024, 4096])
        #expect(options.generationLength == 128)
        #expect(options.batchSizes == [2, 4])
        #expect(options.repeats == 3)
        #expect(options.cacheProfile == "partial_prefix")
        #expect(options.reasoningMode == "enabled")
        #expect(options.structuredOutputMode == "json_schema")
    }

    @Test("rejects invalid bench cache profiles")
    func rejectsInvalidBenchCacheProfiles() throws {
        try assertError(
            for: [
                "bench",
                "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--context-length", "1024",
                "--generation-length", "128",
                "--cache-profile", "hot",
            ],
            equals: .usage("Invalid value for --cache-profile. Expected one of: cold, warm, partial_prefix.")
        )
    }

    @Test("parses bench run with a direct Hugging Face repo target")
    func parsesBenchRunCommandForDirectHFRepo() throws {
        let command = try MelixCLIParser.parse([
            "bench",
            "run",
            "--repo-id", "unsloth/gemma-4-E4B-it-MLX-8bit",
            "--suite", "smoke",
            "--json",
        ])

        guard case .benchRun(let options) = command else {
            Issue.record("Expected benchRun command")
            return
        }

        #expect(options.modelID.isEmpty)
        #expect(options.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(options.suites == ["smoke"])
        #expect(options.json)
    }

    @Test("parses bench list and export-csv commands")
    func parsesBenchListAndExportCSVCommands() throws {
        let listCommand = try MelixCLIParser.parse([
            "bench",
            "list",
            "--json",
        ])
        let exportCommand = try MelixCLIParser.parse([
            "bench",
            "export-csv",
            "--job-id", "bench-1",
            "--output", "/tmp/melix/bench-1.csv",
            "--json",
        ])

        guard case .benchList(let listOptions) = listCommand else {
            Issue.record("Expected benchList command")
            return
        }
        guard case .benchExportCSV(let exportOptions) = exportCommand else {
            Issue.record("Expected benchExportCSV command")
            return
        }

        #expect(listOptions.json)
        #expect(exportOptions.jobID == "bench-1")
        #expect(exportOptions.outputPath == "/tmp/melix/bench-1.csv")
        #expect(exportOptions.json)
    }

    @Test("parses bench matrix run with canonical sweep and load-budget inputs")
    func parsesBenchMatrixRunCommand() throws {
        let command = try MelixCLIParser.parse([
            "bench",
            "matrix",
            "run",
            "--repo-id", "unsloth/gemma-4-E4B-it-MLX-8bit",
            "--suite", "smoke",
            "--suite", "latency",
            "--context-length", "4096",
            "--context-length", "1024",
            "--generation-length", "256",
            "--generation-length", "128",
            "--batch-size", "4",
            "--batch-size", "2",
            "--cache-profile", "warm",
            "--cache-profile", "cold",
            "--reasoning-mode", "enabled",
            "--reasoning-mode", "disabled",
            "--structured-output-mode", "json_schema",
            "--structured-output-mode", "plain_text",
            "--concurrency", "8",
            "--concurrency", "1",
            "--repeats", "3",
            "--requests", "24",
            "--json",
        ])

        guard case .benchMatrixRun(let options) = command else {
            Issue.record("Expected benchMatrixRun command")
            return
        }

        #expect(options.modelID.isEmpty)
        #expect(options.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(options.suites == ["latency", "smoke"])
        #expect(options.contextLengths == [1024, 4096])
        #expect(options.generationLengths == [128, 256])
        #expect(options.batchSizes == [2, 4])
        #expect(options.cacheProfiles == ["cold", "warm"])
        #expect(options.reasoningModes == ["disabled", "enabled"])
        #expect(options.structuredOutputModes == ["json_schema", "plain_text"])
        #expect(options.concurrencyLevels == [1, 8])
        #expect(options.repeats == 3)
        #expect(options.requests == 24)
        #expect(options.durationSeconds == 0)
        #expect(options.allowLargeMatrix == false)
        #expect(options.json)
    }

    @Test("parses bench matrix list and export commands")
    func parsesBenchMatrixListAndExportCommands() throws {
        let listCommand = try MelixCLIParser.parse([
            "bench",
            "matrix",
            "list",
            "--json",
        ])
        let summaryCommand = try MelixCLIParser.parse([
            "bench",
            "matrix",
            "export-summary-csv",
            "--job-id", "bench-matrix-1",
            "--output", "/tmp/melix/bench-matrix-summary.csv",
            "--json",
        ])
        let requestsCommand = try MelixCLIParser.parse([
            "bench",
            "matrix",
            "export-requests-csv",
            "--job-id", "bench-matrix-1",
            "--output", "/tmp/melix/bench-matrix-requests.csv",
        ])

        guard case .benchMatrixList(let listOptions) = listCommand else {
            Issue.record("Expected benchMatrixList command")
            return
        }
        guard case .benchMatrixExportSummaryCSV(let summaryOptions) = summaryCommand else {
            Issue.record("Expected benchMatrixExportSummaryCSV command")
            return
        }
        guard case .benchMatrixExportRequestsCSV(let requestsOptions) = requestsCommand else {
            Issue.record("Expected benchMatrixExportRequestsCSV command")
            return
        }

        #expect(listOptions.json)
        #expect(summaryOptions.jobID == "bench-matrix-1")
        #expect(summaryOptions.outputPath == "/tmp/melix/bench-matrix-summary.csv")
        #expect(summaryOptions.json)
        #expect(requestsOptions.jobID == "bench-matrix-1")
        #expect(requestsOptions.outputPath == "/tmp/melix/bench-matrix-requests.csv")
        #expect(requestsOptions.json == false)
    }

    @Test("bench matrix parser rejects missing targets required dimensions and malformed exports")
    func benchMatrixParserRejectsMissingTargetsRequiredDimensionsAndMalformedExports() throws {
        try assertError(for: ["bench", "matrix"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["bench", "matrix", "oops"], equals: .usage(MelixCLIParser.usageText))
        try assertError(
            for: [
                "bench", "matrix", "run",
                "--suite", "smoke",
                "--context-length", "1024",
                "--generation-length", "128",
                "--batch-size", "2",
                "--cache-profile", "warm",
                "--reasoning-mode", "enabled",
                "--structured-output-mode", "plain_text",
                "--concurrency", "1",
                "--requests", "8",
            ],
            equals: .missingRequired("Exactly one of --model-id or --repo-id is required for melix bench matrix run.")
        )
        try assertError(
            for: [
                "bench", "matrix", "run",
                "--model-id", "melix-dev-text",
                "--context-length", "1024",
                "--generation-length", "128",
                "--batch-size", "2",
                "--cache-profile", "warm",
                "--reasoning-mode", "enabled",
                "--structured-output-mode", "plain_text",
                "--concurrency", "1",
                "--requests", "8",
            ],
            equals: .missingRequired("At least one --suite is required for melix bench matrix run.")
        )
        try assertError(
            for: [
                "bench", "matrix", "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--generation-length", "128",
                "--batch-size", "2",
                "--cache-profile", "warm",
                "--reasoning-mode", "enabled",
                "--structured-output-mode", "plain_text",
                "--concurrency", "1",
                "--requests", "8",
            ],
            equals: .missingRequired("At least one --context-length is required for melix bench matrix run.")
        )
        try assertError(
            for: [
                "bench", "matrix", "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--context-length", "1024",
                "--batch-size", "2",
                "--cache-profile", "warm",
                "--reasoning-mode", "enabled",
                "--structured-output-mode", "plain_text",
                "--concurrency", "1",
                "--requests", "8",
            ],
            equals: .missingRequired("At least one --generation-length is required for melix bench matrix run.")
        )
        try assertError(
            for: [
                "bench", "matrix", "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--context-length", "1024",
                "--generation-length", "128",
                "--cache-profile", "warm",
                "--reasoning-mode", "enabled",
                "--structured-output-mode", "plain_text",
                "--concurrency", "1",
                "--requests", "8",
            ],
            equals: .missingRequired("At least one --batch-size is required for melix bench matrix run.")
        )
        try assertError(
            for: [
                "bench", "matrix", "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--context-length", "1024",
                "--generation-length", "128",
                "--batch-size", "2",
                "--reasoning-mode", "enabled",
                "--structured-output-mode", "plain_text",
                "--concurrency", "1",
                "--requests", "8",
            ],
            equals: .missingRequired("At least one --cache-profile is required for melix bench matrix run.")
        )
        try assertError(
            for: [
                "bench", "matrix", "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--context-length", "1024",
                "--generation-length", "128",
                "--batch-size", "2",
                "--cache-profile", "warm",
                "--structured-output-mode", "plain_text",
                "--concurrency", "1",
                "--requests", "8",
            ],
            equals: .missingRequired("At least one --reasoning-mode is required for melix bench matrix run.")
        )
        try assertError(
            for: [
                "bench", "matrix", "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--context-length", "1024",
                "--generation-length", "128",
                "--batch-size", "2",
                "--cache-profile", "warm",
                "--reasoning-mode", "enabled",
                "--concurrency", "1",
                "--requests", "8",
            ],
            equals: .missingRequired("At least one --structured-output-mode is required for melix bench matrix run.")
        )
        try assertError(
            for: [
                "bench", "matrix", "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--context-length", "1024",
                "--generation-length", "128",
                "--batch-size", "2",
                "--cache-profile", "warm",
                "--reasoning-mode", "enabled",
                "--structured-output-mode", "plain_text",
                "--requests", "8",
            ],
            equals: .missingRequired("At least one --concurrency is required for melix bench matrix run.")
        )
        try assertError(
            for: [
                "bench", "matrix", "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--context-length", "1024",
                "--generation-length", "128",
                "--batch-size", "2",
                "--cache-profile", "ancient",
                "--reasoning-mode", "enabled",
                "--structured-output-mode", "plain_text",
                "--concurrency", "1",
                "--requests", "8",
            ],
            equals: .usage("Invalid value for --cache-profile. Expected one of: cold, warm, partial_prefix.")
        )
        try assertError(
            for: ["bench", "matrix", "export-summary-csv", "--job-id", "bench-matrix-1"],
            equals: .missingRequired("--output is required for melix bench matrix export-summary-csv.")
        )
        try assertError(
            for: ["bench", "matrix", "export-requests-csv", "--output", "/tmp/out.csv"],
            equals: .missingRequired("--job-id is required for melix bench matrix export-requests-csv.")
        )
    }

    @Test("parses eval run with direct repo target and sampling controls")
    func parsesEvalRunCommand() throws {
        let command = try MelixCLIParser.parse([
            "eval",
            "run",
            "--repo-id", "unsloth/gemma-4-E4B-it-MLX-8bit",
            "--suite", "mmlu",
            "--suite", "gsm8k",
            "--dataset-id", "mmlu.dev.v1",
            "--sample-size", "8",
            "--batch-factor", "2",
            "--seed", "7",
            "--few-shot", "4",
            "--json",
        ])

        guard case .evalRun(let options) = command else {
            Issue.record("Expected evalRun command")
            return
        }

        #expect(options.modelID.isEmpty)
        #expect(options.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(options.suites == ["mmlu", "gsm8k"])
        #expect(options.datasetID == "mmlu.dev.v1")
        #expect(options.sampleSize == 8)
        #expect(options.parameters["batch_factor"] == "2")
        #expect(options.parameters["seed"] == "7")
        #expect(options.parameters["few_shot"] == "4")
        #expect(options.json)
    }

    @Test("parses eval run with canonical few-shot scoring and execution inputs")
    func parsesEvalRunWithCanonicalFewShotScoringAndExecutionInputs() throws {
        let command = try MelixCLIParser.parse([
            "eval",
            "run",
            "--repo-id", "unsloth/gemma-4-E4B-it-MLX-8bit",
            "--suite", "qa_smoke",
            "--dataset-id", "qa_smoke.dev.v1",
            "--few-shot", "4",
            "--seed", "7",
            "--scoring-mode", "multiple_choice_accuracy",
            "--code-exec-policy", "sandboxed",
        ])

        guard case .evalRun(let options) = command else {
            Issue.record("Expected evalRun command")
            return
        }

        #expect(options.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(options.suites == ["qa_smoke"])
        #expect(options.datasetID == "qa_smoke.dev.v1")
        #expect(options.sampleSize == 0)
        #expect(options.parameters["few_shot"] == "4")
        #expect(options.parameters["seed"] == "7")
        #expect(options.parameters["scoring_mode"] == "multiple_choice_accuracy")
        #expect(options.parameters["code_exec_policy"] == "sandboxed")
    }

    @Test("parses eval list and export commands")
    func parsesEvalListAndExportCommands() throws {
        let listCommand = try MelixCLIParser.parse([
            "eval",
            "list",
            "--json",
        ])
        let summaryCommand = try MelixCLIParser.parse([
            "eval",
            "export-summary-csv",
            "--job-id", "eval-1",
            "--output", "/tmp/melix/eval-1-summary.csv",
            "--json",
        ])
        let samplesCommand = try MelixCLIParser.parse([
            "eval",
            "export-samples-jsonl",
            "--job-id", "eval-1",
            "--output", "/tmp/melix/eval-1-samples.jsonl",
        ])

        guard case .evalList(let listOptions) = listCommand else {
            Issue.record("Expected evalList command")
            return
        }
        guard case .evalExportSummaryCSV(let summaryOptions) = summaryCommand else {
            Issue.record("Expected evalExportSummaryCSV command")
            return
        }
        guard case .evalExportSamplesJSONL(let samplesOptions) = samplesCommand else {
            Issue.record("Expected evalExportSamplesJSONL command")
            return
        }

        #expect(listOptions.json)
        #expect(summaryOptions.jobID == "eval-1")
        #expect(summaryOptions.outputPath == "/tmp/melix/eval-1-summary.csv")
        #expect(summaryOptions.json)
        #expect(samplesOptions.jobID == "eval-1")
        #expect(samplesOptions.outputPath == "/tmp/melix/eval-1-samples.jsonl")
        #expect(samplesOptions.json == false)
    }

    @Test("parses lora activate with explicit alias and adapter path")
    func parsesLoraActivateCommand() throws {
        let command = try MelixCLIParser.parse([
            "lora",
            "activate",
            "--model-id", "melix-dev-text",
            "--adapter-path", "/tmp/melix/adapter/train_lora.adapter.json",
            "--alias", "melix-dev-text-lora",
        ])

        guard case .loraActivate(let options) = command else {
            Issue.record("Expected loraActivate command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.adapterPath == "/tmp/melix/adapter/train_lora.adapter.json")
        #expect(options.derivedModelAlias == "melix-dev-text-lora")
    }

    @Test("surfaces usage and missing required parser errors")
    func surfacesUsageAndMissingRequiredErrors() throws {
        try assertError(for: [], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["unknown"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["lora"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["lora", "oops"], equals: .usage(MelixCLIParser.usageText))
        try assertError(
            for: ["lora", "train", "--dataset-uri", "/tmp/data.jsonl", "--adapter-name", "demo"],
            equals: .missingRequired("--model-id is required for melix lora train.")
        )
        try assertError(
            for: ["lora", "train", "--model-id", "melix-dev-text", "--adapter-name", "demo"],
            equals: .missingRequired("Either --dataset-uri or --hf-dataset-path is required for melix lora train.")
        )
        try assertError(
            for: ["lora", "train", "--model-id", "melix-dev-text", "--dataset-uri", "/tmp/data.jsonl"],
            equals: .missingRequired("--adapter-name is required for melix lora train.")
        )
        try assertError(
            for: ["lora", "activate", "--model-id", "melix-dev-text"],
            equals: .missingRequired("--adapter-path is required for melix lora activate.")
        )
        try assertError(
            for: ["bench", "run"],
            equals: .missingRequired("Exactly one of --model-id or --repo-id is required for melix bench run.")
        )
        try assertError(
            for: ["bench", "run", "--model-id", "melix-dev-text", "--repo-id", "unsloth/gemma-4-E4B-it-MLX-8bit"],
            equals: .missingRequired("Exactly one of --model-id or --repo-id is required for melix bench run.")
        )
        try assertError(
            for: ["bench", "export-csv", "--output", "/tmp/out.csv"],
            equals: .missingRequired("--job-id is required for melix bench export-csv.")
        )
        try assertError(
            for: ["bench", "export-csv", "--job-id", "bench-1"],
            equals: .missingRequired("--output is required for melix bench export-csv.")
        )
        try assertError(
            for: ["bench", "matrix", "run", "--model-id", "melix-dev-text", "--suite", "smoke"],
            equals: .missingRequired("Exactly one of --requests or --duration-seconds is required for melix bench matrix run.")
        )
        try assertError(
            for: [
                "bench", "matrix", "run",
                "--model-id", "melix-dev-text",
                "--suite", "smoke",
                "--context-length", "1024",
                "--generation-length", "128",
                "--batch-size", "2",
                "--cache-profile", "warm",
                "--reasoning-mode", "enabled",
                "--structured-output-mode", "plain_text",
                "--concurrency", "1",
                "--requests", "8",
                "--duration-seconds", "30",
            ],
            equals: .missingRequired("Exactly one of --requests or --duration-seconds is required for melix bench matrix run.")
        )
        try assertError(
            for: ["bench", "matrix", "export-summary-csv", "--output", "/tmp/out.csv"],
            equals: .missingRequired("--job-id is required for melix bench matrix export-summary-csv.")
        )
        try assertError(
            for: ["bench", "matrix", "export-requests-csv", "--job-id", "bench-matrix-1"],
            equals: .missingRequired("--output is required for melix bench matrix export-requests-csv.")
        )
        try assertError(for: ["bench", "oops"], equals: .usage(MelixCLIParser.usageText))
        try assertError(
            for: ["eval", "run"],
            equals: .missingRequired("Exactly one of --model-id or --repo-id is required for melix eval run.")
        )
        try assertError(
            for: ["eval", "run", "--model-id", "melix-dev-text", "--repo-id", "repo"],
            equals: .missingRequired("Exactly one of --model-id or --repo-id is required for melix eval run.")
        )
        try assertError(for: ["eval"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["eval", "oops"], equals: .usage(MelixCLIParser.usageText))
        try assertError(
            for: ["eval", "export-summary-csv", "--output", "/tmp/out.csv"],
            equals: .missingRequired("--job-id is required for melix eval export-summary-csv.")
        )
        try assertError(
            for: ["eval", "export-samples-csv", "--job-id", "eval-1"],
            equals: .missingRequired("--output is required for melix eval export-samples-csv.")
        )
    }

    @Test("surfaces malformed option errors")
    func surfacesMalformedOptionErrors() throws {
        try assertError(for: ["server"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["server", "hibernate"], equals: .usage(MelixCLIParser.usageText))
        try assertError(
            for: ["server", "set-idle-policy", "--light-sleep-after", "60", "--deep-sleep-after", "600"],
            equals: .missingRequired("--auto-sleep is required for melix server set-idle-policy.")
        )
        try assertError(
            for: ["server", "set-idle-policy", "--auto-sleep", "maybe", "--light-sleep-after", "60", "--deep-sleep-after", "600"],
            equals: .usage("Invalid value for --auto-sleep. Expected true or false.")
        )
        try assertError(
            for: ["server", "set-idle-policy", "--auto-sleep", "true", "--deep-sleep-after", "600"],
            equals: .missingRequired("--light-sleep-after is required for melix server set-idle-policy.")
        )
        try assertError(
            for: ["server", "set-idle-policy", "--auto-sleep", "true", "--light-sleep-after", "60"],
            equals: .missingRequired("--deep-sleep-after is required for melix server set-idle-policy.")
        )
        try assertError(for: ["bench", "run", "oops"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["bench", "run", "--model-id"], equals: .missingValue("--model-id"))
        try assertError(for: ["eval", "run", "--repo-id"], equals: .missingValue("--repo-id"))
        try assertError(for: ["lora", "list", "--model-id"], equals: .missingValue("--model-id"))
        try assertError(for: ["lora", "activate", "--model-id", "melix-dev-text", "oops"], equals: .usage(MelixCLIParser.usageText))
        #expect(MelixCLIError.usage("usage").errorDescription == "usage")
        #expect(MelixCLIError.missingValue("--alpha").errorDescription == "Missing value for --alpha.")
        #expect(MelixCLIError.missingRequired("required").errorDescription == "required")
        #expect(MelixCLIError.runtime("runtime").errorDescription == "runtime")
    }
}

private func assertError(
    for arguments: [String],
    equals expected: MelixCLIError
) throws {
    do {
        _ = try MelixCLIParser.parse(arguments)
        Issue.record("Expected parser to throw for arguments: \(arguments)")
    } catch let error as MelixCLIError {
        #expect(error == expected)
    }
}
