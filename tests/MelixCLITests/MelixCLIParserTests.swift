import Testing

@testable import MelixCLICore

@Suite("Melix CLI Parser")
struct MelixCLIParserTests {
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

    @Test("parses bench run with explicit model suites and tuning parameters")
    func parsesBenchRunCommand() throws {
        let command = try MelixCLIParser.parse([
            "bench",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "smoke",
            "--suite", "latency",
            "--sample-size", "8",
            "--batch-factor", "2",
            "--json",
        ])

        guard case .benchRun(let options) = command else {
            Issue.record("Expected benchRun command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.suites == ["smoke", "latency"])
        #expect(options.parameters["sample_size"] == "8")
        #expect(options.parameters["batch_factor"] == "2")
        #expect(options.json)
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
            equals: .missingRequired("--model-id is required for melix bench run.")
        )
        try assertError(for: ["bench", "oops"], equals: .usage(MelixCLIParser.usageText))
    }

    @Test("surfaces malformed option errors")
    func surfacesMalformedOptionErrors() throws {
        try assertError(for: ["bench", "run", "oops"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["bench", "run", "--model-id"], equals: .missingValue("--model-id"))
        try assertError(for: ["lora", "list", "--model-id"], equals: .missingValue("--model-id"))
        try assertError(for: ["lora", "activate", "--model-id", "melix-dev-text", "oops"], equals: .usage(MelixCLIParser.usageText))
        #expect(MelixCLIError.usage("usage").errorDescription == "usage")
        #expect(MelixCLIError.missingValue("--alpha").errorDescription == "Missing value for --alpha.")
        #expect(MelixCLIError.missingRequired("required").errorDescription == "required")
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
