import CryptoKit
import Foundation
import Testing

@testable import MelixCLICore
import MelixControlPlaneCore

@Suite("Melix CLI Parser")
struct MelixCLIParserTests {
    @Test("documents eval dataset root in usage text")
    func documentsEvalDatasetRootInUsageText() {
        #expect(MelixCLIParser.usageText.contains("[--dataset-root PATH]"))
        #expect(MelixCLIParser.usageText.contains("[--schema PATH | --output-schema-json JSON] [--hints PATH]"))
        #expect(MelixCLIParser.usageText.contains("--hf-token passed to model or dataset hub download is saved"))
        #expect(MelixCLIParser.usageText.contains("--hf-dataset-revision overrides a revision embedded in --dataset-ref"))
        #expect(MelixCLIParser.usageText.contains("melix runs list [--from PATH] [--json]"))
        #expect(MelixCLIParser.usageText.contains("melix bench report --from PATH [--format markdown|json]"))
        #expect(MelixCLIParser.usageText.contains("melix settings show --json [--override KEY=VALUE ...]"))
        #expect(MelixCLIParser.usageText.contains("melix info --json"))
        #expect(MelixCLIParser.usageText.contains("melix capabilities --json [--model-query MODEL]"))
        #expect(MelixCLIParser.usageText.contains("melix config metadata --json"))
        #expect(MelixCLIParser.usageText.contains("melix uri inspect URI [--json]"))
        #expect(MelixCLIParser.usageText.contains("melix recipes plan RECIPE_ID"))
    }

    @Test("parses runtime settings and machine readable discovery commands")
    func parsesRuntimeSettingsAndDiscoveryCommands() throws {
        let cases: [([String], String)] = [
            (["settings", "show", "--json"], "settings.show"),
            (["settings", "show", "--json", "--override", "max_concurrent_jobs=8"], "settings.show"),
            (["settings", "set", "max_concurrent_jobs", "6"], "settings.set"),
            (["settings", "validate"], "settings.validate"),
            (["settings", "reset", "max_concurrent_jobs"], "settings.reset"),
            (["info", "--json"], "info"),
            (["capabilities", "--json"], "capabilities"),
            (["capabilities", "--json", "--model-query", "qwen35_9b_mlx_4bit"], "capabilities"),
            (["instructions", "--json"], "instructions"),
            (["schema", "--json"], "schema"),
            (["config", "metadata", "--json"], "config.metadata"),
        ]

        for (arguments, expectedID) in cases {
            let command = try MelixCLIParser.parse(arguments)
            #expect(MelixCLICommandCodec.commandID(for: command) == expectedID)
            #expect(try MelixCLIParser.parse(MelixCLICommandCodec.arguments(for: command)) == command)
        }

        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["settings", "show"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["settings", "set", "max_concurrent_jobs"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["settings", "reset"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["info"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["config", "unknown", "--json"])
        }
    }

    @Test("rejects malformed runtime settings and discovery commands")
    func rejectsMalformedRuntimeSettingsAndDiscoveryCommands() {
        #expect(throws: MelixCLIError.usage(MelixCLIParser.usageText)) {
            _ = try MelixCLIParser.parse(["settings"])
        }
        #expect(throws: MelixCLIError.missingValue("--override")) {
            _ = try MelixCLIParser.parse(["settings", "show", "--json", "--override"])
        }
        #expect(throws: MelixCLIError.usage("--override must use KEY=VALUE.")) {
            _ = try MelixCLIParser.parse(["settings", "show", "--json", "--override", "=8"])
        }
        #expect(throws: MelixCLIError.usage(MelixCLIParser.usageText)) {
            _ = try MelixCLIParser.parse(["settings", "set", "max_concurrent_jobs", "--bad"])
        }
        #expect(throws: MelixCLIError.usage(MelixCLIParser.usageText)) {
            _ = try MelixCLIParser.parse(["settings", "set", "max_concurrent_jobs", "--jsno", "6"])
        }
        #expect(throws: MelixCLIError.usage(MelixCLIParser.usageText)) {
            _ = try MelixCLIParser.parse(["settings", "reset", "eval_sample_size", "--bad"])
        }
        #expect(throws: MelixCLIError.usage("melix capabilities requires --json.")) {
            _ = try MelixCLIParser.parse(["capabilities"])
        }
        #expect(throws: MelixCLIError.usage("melix instructions requires --json.")) {
            _ = try MelixCLIParser.parse(["instructions"])
        }
        #expect(throws: MelixCLIError.usage("melix schema requires --json.")) {
            _ = try MelixCLIParser.parse(["schema"])
        }
        #expect(throws: MelixCLIError.usage("melix config metadata requires --json.")) {
            _ = try MelixCLIParser.parse(["config", "metadata"])
        }
    }

    @Test("documents and parses remote server direct target commands")
    func documentsAndParsesRemoteServerDirectTargetCommands() throws {
        #expect(MelixCLIParser.usageText.contains("melix remote-server add"))
        #expect(MelixCLIParser.usageText.contains("melix remote-server test"))
        #expect(MelixCLIParser.usageText.contains("melix chat run (--model-id MODEL_ID | --remote-server-id ID --model MODEL)"))
        #expect(MelixCLIParser.usageText.contains("melix eval run (--model-id MODEL_ID | --repo-id HF_REPO | --remote-server-id ID [--remote-model MODEL] ...)"))
        #expect(MelixCLIParser.usageText.contains("melix eval prompt create"))

        let add = try MelixCLIParser.parse([
            "remote-server", "add",
            "--remote-server-id", "sub2api",
            "--title", "sub2api",
            "--provider", "custom",
            "--base-url", "https://sub2api.example/v1/",
            "--model", "gemini-2.5-flash",
            "--api-key", "sk-secret",
            "--timeout-seconds", "90",
            "--rate-limit-per-minute", "30",
            "--json",
        ])
        let test = try MelixCLIParser.parse([
            "remote-server", "test",
            "--remote-server-id", "sub2api",
            "--model", "gemini-2.5-flash",
            "--json",
        ])
        let list = try MelixCLIParser.parse([
            "remote-server", "list",
            "--json",
        ])
        let update = try MelixCLIParser.parse([
            "remote-server", "update",
            "--remote-server-id", "sub2api",
            "--title", "sub2api updated",
            "--provider", "custom",
            "--base-url", "https://sub2api.example/updated/v1",
            "--model", "deepseek-v4",
            "--api-key", "sk-updated",
            "--timeout-seconds", "91",
            "--rate-limit-per-minute", "31",
            "--json",
        ])
        let remove = try MelixCLIParser.parse([
            "remote-server", "remove",
            "--remote-server-id", "sub2api",
            "--json",
        ])
        let chat = try MelixCLIParser.parse([
            "chat", "run",
            "--remote-server-id", "sub2api",
            "--model", "gemini-2.5-flash",
            "--message", "hello",
            "--json",
        ])
        let eval = try MelixCLIParser.parse([
            "eval", "run",
            "--remote-server-id", "sub2api",
            "--remote-model", "gemini-2.5-flash",
            "--semantic-judge-remote-server-id", "judge-server",
            "--semantic-judge-model", "judge-model",
            "--remote-extra-body-json", "{\"max_tokens\":1024,\"chat_template_kwargs\":{\"enable_thinking\":false}}",
            "--source-jsonl", "/Users/ChenYu/Downloads/top200_final.jsonl",
            "--scoring-mode", "event_extraction_weighted_f1",
            "--eval-prompt-id", "event-prod",
            "--eval-prompt-revision", "rev-1",
            "--sample-size", "3",
            "--json",
        ])
        let promptCreate = try MelixCLIParser.parse([
            "eval", "prompt", "create",
            "--prompt-id", "event-prod",
            "--title", "Event Prod",
            "--system-prompt-file", "/tmp/event-prompt.txt",
            "--json",
        ])
        let promptFreeze = try MelixCLIParser.parse([
            "eval", "prompt", "freeze",
            "--prompt-id", "event-prod",
            "--revision-id", "rev-1",
        ])

        guard case .remoteServerAdd(let addOptions) = add else {
            Issue.record("Expected remoteServerAdd command")
            return
        }
        guard case .remoteServerTest(let testOptions) = test else {
            Issue.record("Expected remoteServerTest command")
            return
        }
        guard case .remoteServerList(let listOptions) = list else {
            Issue.record("Expected remoteServerList command")
            return
        }
        guard case .remoteServerUpdate(let updateOptions) = update else {
            Issue.record("Expected remoteServerUpdate command")
            return
        }
        guard case .remoteServerRemove(let removeOptions) = remove else {
            Issue.record("Expected remoteServerRemove command")
            return
        }
        guard case .chatRun(let chatOptions) = chat else {
            Issue.record("Expected remote chat command")
            return
        }
        guard case .evalRun(let evalOptions) = eval else {
            Issue.record("Expected remote eval command")
            return
        }
        guard case .evalPromptCreate(let promptCreateOptions) = promptCreate else {
            Issue.record("Expected prompt create command")
            return
        }
        guard case .evalPromptFreeze(let promptFreezeOptions) = promptFreeze else {
            Issue.record("Expected prompt freeze command")
            return
        }

        #expect(addOptions.remoteServerID == "sub2api")
        #expect(addOptions.title == "sub2api")
        #expect(addOptions.providerPreset == .custom)
        #expect(addOptions.providerKind == "openai-compatible")
        #expect(addOptions.baseURL == "https://sub2api.example/v1/")
        #expect(addOptions.defaultModelID == "gemini-2.5-flash")
        #expect(addOptions.apiKey == "sk-secret")
        #expect(addOptions.timeoutSeconds == 90)
        #expect(addOptions.rateLimitPerMinute == 30)
        #expect(addOptions.json)

        #expect(testOptions.remoteServerID == "sub2api")
        #expect(testOptions.remoteModelID == "gemini-2.5-flash")
        #expect(testOptions.json)

        #expect(listOptions.json)
        #expect(updateOptions.remoteServerID == "sub2api")
        #expect(updateOptions.title == "sub2api updated")
        #expect(updateOptions.providerPreset == .custom)
        #expect(updateOptions.providerKind == "openai-compatible")
        #expect(updateOptions.baseURL == "https://sub2api.example/updated/v1")
        #expect(updateOptions.defaultModelID == "deepseek-v4")
        #expect(updateOptions.apiKey == "sk-updated")
        #expect(updateOptions.timeoutSeconds == 91)
        #expect(updateOptions.rateLimitPerMinute == 31)
        #expect(updateOptions.json)
        #expect(removeOptions.remoteServerID == "sub2api")
        #expect(removeOptions.json)

        #expect(chatOptions.modelID == "")
        #expect(chatOptions.remoteServerID == "sub2api")
        #expect(chatOptions.remoteModelID == "gemini-2.5-flash")
        #expect(chatOptions.message == "hello")
        #expect(chatOptions.json)

        #expect(evalOptions.modelID == "")
        #expect(evalOptions.hfRepoID == "")
        #expect(evalOptions.remoteServerID == "sub2api")
        #expect(evalOptions.remoteModelID == "gemini-2.5-flash")
        #expect(evalOptions.remoteTargets == [
            EvalRemoteTargetOptions(remoteServerID: "sub2api", remoteModelID: "gemini-2.5-flash"),
        ])
        #expect(evalOptions.semanticJudgeRemoteServerID == "judge-server")
        #expect(evalOptions.semanticJudgeModelID == "judge-model")
        #expect(evalOptions.suites == ["event_extraction"])
        #expect(evalOptions.source == .localJSONL(path: "/Users/ChenYu/Downloads/top200_final.jsonl"))
        #expect(evalOptions.profile.scoringMode == "event_extraction_weighted_f1")
        #expect(evalOptions.parameters["remote_provider_extra_body_json"] == "{\"max_tokens\":1024,\"chat_template_kwargs\":{\"enable_thinking\":false}}")
        #expect(evalOptions.evalPromptID == "event-prod")
        #expect(evalOptions.evalPromptRevisionID == "rev-1")
        #expect(evalOptions.sampleSize == 3)
        #expect(evalOptions.json)

        #expect(promptCreateOptions.promptID == "event-prod")
        #expect(promptCreateOptions.title == "Event Prod")
        #expect(promptCreateOptions.systemPromptFile == "/tmp/event-prompt.txt")
        #expect(promptCreateOptions.json)
        #expect(promptFreezeOptions.promptID == "event-prod")
        #expect(promptFreezeOptions.revisionID == "rev-1")

        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse([
                "chat", "run",
                "--remote-server-id", "sub2api",
                "--message", "hello",
            ])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["remote-server"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["remote-server", "unknown"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["eval", "prompt", "create", "--prompt-id", "missing-title"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["eval", "prompt"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["eval", "prompt", "show"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse([
                "eval", "prompt", "create",
                "--title", "Missing ID",
                "--system-prompt-file", "/tmp/prompt.txt",
            ])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse([
                "eval", "prompt", "create",
                "--prompt-id", "missing-file",
                "--title", "Missing File",
            ])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["eval", "prompt", "update"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse([
                "eval", "prompt", "update",
                "--prompt-id", "missing-file",
            ])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["eval", "prompt", "freeze"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["eval", "prompt", "archive"])
        }
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["eval", "prompt", "unknown"])
        }
    }

    @Test("parses eval run with multiple remote provider targets")
    func parsesEvalRunWithMultipleRemoteProviderTargets() throws {
        let command = try MelixCLIParser.parse([
            "eval", "run",
            "--remote-server-id", "DeepSeek",
            "--remote-model", "deepseek-v4-pro",
            "--remote-server-id", "Gemini",
            "--remote-model", "gemini-2.5-flash",
            "--remote-server-id", "GML",
            "--remote-model", "glm-5.1",
            "--remote-parallelism", "3",
            "--source-jsonl", "/tmp/top200.jsonl",
            "--scoring-mode", "event_extraction_weighted_f1",
            "--sample-size", "200",
            "--json",
        ])

        guard case .evalRun(let options) = command else {
            Issue.record("Expected eval run command")
            return
        }

        #expect(options.remoteServerID == "DeepSeek")
        #expect(options.remoteModelID == "deepseek-v4-pro")
        #expect(options.remoteTargets == [
            EvalRemoteTargetOptions(remoteServerID: "DeepSeek", remoteModelID: "deepseek-v4-pro"),
            EvalRemoteTargetOptions(remoteServerID: "Gemini", remoteModelID: "gemini-2.5-flash"),
            EvalRemoteTargetOptions(remoteServerID: "GML", remoteModelID: "glm-5.1"),
        ])
        #expect(options.remoteParallelism == 3)
        #expect(options.suites == ["event_extraction"])
    }

    @Test("remote server parser supports provider presets and rejects base URL overrides")
    func remoteServerParserSupportsProviderPresetsAndRejectsBaseURLOverrides() throws {
        let gemini = try MelixCLIParser.parse([
            "remote-server", "add",
            "--remote-server-id", "gemini",
            "--title", "Gemini",
            "--provider", "gemini",
            "--model", "gemini-2.5-flash",
            "--api-key", "AIza-secret",
        ])

        guard case .remoteServerAdd(let addOptions) = gemini else {
            Issue.record("Expected remoteServerAdd command")
            return
        }

        #expect(addOptions.providerPreset == .gemini)
        #expect(addOptions.providerKind == "gemini-generative-language")
        #expect(addOptions.baseURL == "https://generativelanguage.googleapis.com/v1beta")

        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse([
                "remote-server", "add",
                "--remote-server-id", "kimi",
                "--title", "Kimi",
                "--provider", "kimi",
                "--base-url", "https://override.example/v1",
                "--model", "kimi-2.6",
            ])
        }

        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse([
                "remote-server", "add",
                "--remote-server-id", "custom",
                "--title", "Custom",
                "--provider", "custom",
                "--model", "kimi-2.6",
            ])
        }

        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse([
                "remote-server", "add",
                "--remote-server-id", "unknown",
                "--title", "Unknown",
                "--provider", "unknown-provider",
                "--model", "remote-model",
            ])
        }
    }

    @Test("documents and parses public model ops commands")
    func documentsAndParsesPublicModelOpsCommands() throws {
        #expect(MelixCLIParser.usageText.contains("melix doctor [--json]"))
        #expect(MelixCLIParser.usageText.contains("melix system --json"))
        #expect(MelixCLIParser.usageText.contains("melix monitor [--from PATH] [--json]"))
        #expect(MelixCLIParser.usageText.contains("melix logs JOB_ID"))
        #expect(MelixCLIParser.usageText.contains("melix debug bundle RUN_OR_JOB_ID"))
        #expect(MelixCLIParser.usageText.contains("melix convert --model-id MODEL_ID"))
        #expect(MelixCLIParser.usageText.contains("melix quantize --model-id MODEL_ID"))
        #expect(MelixCLIParser.usageText.contains("melix upload --model-id MODEL_ID"))

        let doctorCommand = try MelixCLIParser.parse([
            "doctor",
            "--json",
        ])
        let systemCommand = try MelixCLIParser.parse([
            "system",
            "--json",
        ])
        let monitorCommand = try MelixCLIParser.parse([
            "monitor",
            "--from", "/tmp/melix/jobs",
            "--json",
        ])
        let logsCommand = try MelixCLIParser.parse([
            "logs",
            "bench-1",
            "--from", "/tmp/melix/jobs",
            "--follow",
            "--json",
        ])
        let debugBundleCommand = try MelixCLIParser.parse([
            "debug",
            "bundle",
            "bench-1",
            "--from", "/tmp/melix/jobs",
            "--output", "/tmp/melix-debug/bench-1",
            "--json",
        ])
        let convertCommand = try MelixCLIParser.parse([
            "convert",
            "--model-id", "melix-dev-text",
            "--output-dir", "/tmp/melix-convert",
            "--target-format", "melix_model_bundle",
            "--json",
        ])
        let quantizeCommand = try MelixCLIParser.parse([
            "quantize",
            "--model-id", "melix-dev-text",
            "--output-dir", "/tmp/melix-quantize",
            "--quant-profile-id", "q4",
            "--weight-quant", "q4",
            "--kv-quant", "q8",
            "--quantization-mode", " QAT ",
            "--source-artifact-kind", " Merged_Adapter ",
            "--source-artifact-path", "/tmp/melix-export/merged",
            "--quantization-backend", " MLX_LM_CONVERT ",
            "--mlx-lm-q-bits", " 4 ",
            "--mlx-lm-q-group-size", " 128 ",
            "--mlx-lm-q-mode", " Affine ",
            "--calibration-dataset-uri", "/tmp/melix-datasets/calibration",
            "--quality-delta", "-0.01",
            "--latency-delta", "-0.15",
            "--local-inference-smoke-mode", " Runtime_Generate ",
            "--local-inference-smoke-prompt", "Reply with ISSUE365_OK",
            "--json",
        ])
        let uploadCommand = try MelixCLIParser.parse([
            "upload",
            "--model-id", "melix-dev-text",
            "--output-dir", "/tmp/melix-upload",
            "--target-repo", "melix/models/demo",
            "--artifact-path", "/tmp/melix-convert/convert.artifact",
            "--artifact-kind", "converted_model_bundle",
            "--artifact-manifest-path", "/tmp/melix-convert/convert.artifact/manifest.json",
            "--json",
        ])

        guard case .doctor(let doctorOptions) = doctorCommand else {
            Issue.record("Expected doctor command")
            return
        }
        guard case .system(let systemOptions) = systemCommand else {
            Issue.record("Expected system command")
            return
        }
        guard case .monitor(let monitorOptions) = monitorCommand else {
            Issue.record("Expected monitor command")
            return
        }
        guard case .logs(let logsOptions) = logsCommand else {
            Issue.record("Expected logs command")
            return
        }
        guard case .debugBundle(let debugBundleOptions) = debugBundleCommand else {
            Issue.record("Expected debugBundle command")
            return
        }
        guard case .convert(let convertOptions) = convertCommand else {
            Issue.record("Expected convert command")
            return
        }
        guard case .quantize(let quantizeOptions) = quantizeCommand else {
            Issue.record("Expected quantize command")
            return
        }
        guard case .upload(let uploadOptions) = uploadCommand else {
            Issue.record("Expected upload command")
            return
        }

        #expect(doctorOptions.json)
        #expect(systemOptions.json)
        #expect(monitorOptions.sourcePath == "/tmp/melix/jobs")
        #expect(monitorOptions.json)
        #expect(logsOptions.jobID == "bench-1")
        #expect(logsOptions.sourcePath == "/tmp/melix/jobs")
        #expect(logsOptions.follow)
        #expect(logsOptions.json)
        #expect(debugBundleOptions.runID == "bench-1")
        #expect(debugBundleOptions.sourcePath == "/tmp/melix/jobs")
        #expect(debugBundleOptions.outputPath == "/tmp/melix-debug/bench-1")
        #expect(debugBundleOptions.json)
        #expect(convertOptions.modelID == "melix-dev-text")
        #expect(convertOptions.outputDir == "/tmp/melix-convert")
        #expect(convertOptions.targetFormat == "melix_model_bundle")
        #expect(convertOptions.json)
        #expect(quantizeOptions.modelID == "melix-dev-text")
        #expect(quantizeOptions.outputDir == "/tmp/melix-quantize")
        #expect(quantizeOptions.quantProfileID == "q4")
        #expect(quantizeOptions.weightQuant == "q4")
        #expect(quantizeOptions.kvQuant == "q8")
        #expect(quantizeOptions.quantizationMode == "qat")
        #expect(quantizeOptions.sourceArtifactKind == "merged_adapter")
        #expect(quantizeOptions.sourceArtifactPath == "/tmp/melix-export/merged")
        #expect(quantizeOptions.quantizationBackend == "mlx_lm_convert")
        #expect(quantizeOptions.mlxLMQBits == "4")
        #expect(quantizeOptions.mlxLMQGroupSize == "128")
        #expect(quantizeOptions.mlxLMQMode == "affine")
        #expect(quantizeOptions.calibrationDatasetURI == "/tmp/melix-datasets/calibration")
        #expect(quantizeOptions.qualityDelta == "-0.01")
        #expect(quantizeOptions.latencyDelta == "-0.15")
        #expect(quantizeOptions.localInferenceSmokeMode == "runtime_generate")
        #expect(quantizeOptions.localInferenceSmokePrompt == "Reply with ISSUE365_OK")
        #expect(quantizeOptions.json)
        #expect(uploadOptions.modelID == "melix-dev-text")
        #expect(uploadOptions.outputDir == "/tmp/melix-upload")
        #expect(uploadOptions.targetRepo == "melix/models/demo")
        #expect(uploadOptions.artifactPath == "/tmp/melix-convert/convert.artifact")
        #expect(uploadOptions.artifactKind == "converted_model_bundle")
        #expect(uploadOptions.artifactManifestPath == "/tmp/melix-convert/convert.artifact/manifest.json")
        #expect(uploadOptions.json)
    }

    @Test("parses json v1 output format and pipeline run options")
    func parsesJSONV1OutputFormatAndPipelineRunOptions() throws {
        #expect(MelixCLIParser.usageText.contains("melix pipeline run --file PIPELINE.json"))

        let doctorInvocation = try MelixCLIParser.parseInvocation([
            "doctor",
            "--format", "json-v1",
        ])

        #expect(doctorInvocation.outputFormat == .jsonV1)
        #expect(doctorInvocation.command == .doctor(.init(json: false)))

        let pipelineInvocation = try MelixCLIParser.parseInvocation([
            "pipeline",
            "run",
            "--file", "/tmp/phase8.pipeline.json",
            "--inputs", "/tmp/phase8.inputs.json",
            "--receipt-dir", "/tmp/melix-pipeline-receipts",
            "--trace-id", "trace-pipeline-1",
            "--resume",
            "--from-step", "derived_chat",
            "--dry-run",
            "--format", "json-v1",
        ])

        #expect(pipelineInvocation.outputFormat == .jsonV1)
        guard case .pipelineRun(let options) = pipelineInvocation.command else {
            Issue.record("Expected pipelineRun command")
            return
        }
        #expect(options.filePath == "/tmp/phase8.pipeline.json")
        #expect(options.inputsPath == "/tmp/phase8.inputs.json")
        #expect(options.receiptDir == "/tmp/melix-pipeline-receipts")
        #expect(options.traceID == "trace-pipeline-1")
        #expect(options.resume)
        #expect(options.fromStepID == "derived_chat")
        #expect(options.dryRun)
    }

    @Test("invalid format requests still route parse failures to json v1 error handling")
    func invalidFormatRequestsStillRouteParseFailuresToJSONV1ErrorHandling() {
        #expect(MelixCLIParser.requestedOutputFormat([
            "doctor",
            "--format", "not-json-v1",
        ]) == .jsonV1)
        #expect(MelixCLIParser.requestedOutputFormat([
            "doctor",
            "--format", "json-v1",
        ]) == .jsonV1)
        #expect(MelixCLIParser.requestedOutputFormat([
            "bench",
            "report",
            "--from", "/tmp/bench",
            "--format", "json",
        ]) == .legacy)
        #expect(MelixCLIParser.requestedOutputFormat(["doctor"]) == .legacy)
    }

    @Test("parse invocation lets report commands own their local format option")
    func parseInvocationLetsReportCommandsOwnTheirLocalFormatOption() throws {
        let invocation = try MelixCLIParser.parseInvocation([
            "bench",
            "report",
            "--from", "/tmp/bench",
            "--format", "json",
        ])

        #expect(invocation.outputFormat == .legacy)
        #expect(invocation.command == .benchReport(.init(sourcePath: "/tmp/bench", format: "json")))

        #expect(throws: MelixCLIError.missingValue("--format")) {
            _ = try MelixCLIParser.parseInvocation(["bench", "report", "--format"])
        }
    }

    @Test("command codec round trips typed command arguments")
    func commandCodecRoundTripsTypedCommandArguments() throws {
        let command = MelixCLICommand.chatRun(
            .init(
                modelID: "melix-dev-text",
                message: "Reply with OK",
                systemPrompt: "Be concise.",
                serverSessionID: "server-session-1",
                json: true
            )
        )

        let arguments = try MelixCLICommandCodec.arguments(for: command)

        #expect(arguments == [
            "chat",
            "run",
            "--model-id", "melix-dev-text",
            "--message", "Reply with OK",
            "--system", "Be concise.",
            "--server-session-id", "server-session-1",
            "--json",
        ])
        #expect(try MelixCLIParser.parse(arguments) == command)

        let mergedManifestArguments = try MelixCLICommandCodec.arguments(
            for: .loraPublish(
                .init(
                    modelID: "model",
                    targetRepo: "melix/model-merged",
                    exportKind: .mergedExport,
                    artifactPath: "/tmp/merged/manifest.json",
                    artifactManifestPath: "/tmp/merged/manifest.json",
                    json: true
                )
            )
        )
        #expect(mergedManifestArguments.contains("--manifest-path"))
        #expect(try MelixCLIParser.parse(mergedManifestArguments) == .loraPublish(
            .init(
                modelID: "model",
                targetRepo: "melix/model-merged",
                exportKind: .mergedExport,
                artifactPath: "/tmp/merged/manifest.json",
                artifactManifestPath: "/tmp/merged/manifest.json",
                json: true
            )
        ))

        let mergedModelArguments = try MelixCLICommandCodec.arguments(
            for: .loraPublish(
                .init(
                    modelID: "model",
                    targetRepo: "melix/model-merged",
                    exportKind: .mergedExport,
                    artifactPath: "/tmp/merged-model",
                    json: true
                )
            )
        )
        #expect(mergedModelArguments.contains("--merged-model-path"))
        #expect(try MelixCLIParser.parse(mergedModelArguments) == .loraPublish(
            .init(
                modelID: "model",
                targetRepo: "melix/model-merged",
                exportKind: .mergedExport,
                artifactPath: "/tmp/merged-model",
                json: true
            )
        ))

        let alignmentCommand = MelixCLICommand.alignmentTrain(
            .init(
                modelID: "model",
                datasetSourceKind: "hf_dataset",
                datasetURI: "",
                adapterName: "aligned",
                algorithm: "grpo",
                parameters: [
                    "hf_dataset_path": "org/preference",
                    "grpo_candidate_count": "4",
                    "candidate_generation_mode": "runtime_generate",
                    "candidate_scoring_mode": "reward_model",
                    "candidate_generation_max_tokens": "16",
                    "kl_penalty": "0.02",
                ],
                json: true
            )
        )
        let alignmentArguments = try MelixCLICommandCodec.arguments(for: alignmentCommand)
        #expect(alignmentArguments.contains("--hf-dataset-path"))
        #expect(alignmentArguments.contains("org/preference"))
        #expect(alignmentArguments.contains("--candidate-generation-mode"))
        #expect(alignmentArguments.contains("runtime_generate"))
        #expect(alignmentArguments.contains("--candidate-scoring-mode"))
        #expect(alignmentArguments.contains("reward_model"))
        #expect(alignmentArguments.contains("--candidate-generation-max-tokens"))
        #expect(alignmentArguments.contains("16"))
        #expect(try MelixCLIParser.parse(alignmentArguments) == alignmentCommand)

        let preflightBenchCommand = MelixCLICommand.benchRun(
            .init(
                hfRepoID: "mlx-community/Qwen3.6-35B-A3B-4bit",
                suites: ["smoke"],
                preflightFitCheck: true,
                allowMemoryRisk: true,
                json: true
            )
        )
        let preflightBenchArguments = try MelixCLICommandCodec.arguments(for: preflightBenchCommand)
        #expect(preflightBenchArguments.contains("--preflight-fit-check"))
        #expect(preflightBenchArguments.contains("--allow-memory-risk"))
        #expect(try MelixCLIParser.parse(preflightBenchArguments) == preflightBenchCommand)

        let titledServerStartCommand = MelixCLICommand.serverStart(
            .init(
                serverTitle: "Gemma 31B",
                servedModelIDs: ["mlx-community/gemma-4-31b-it-4bit"],
                host: "127.0.0.1",
                port: 12434,
                rateLimitPerMinute: 60,
                timeoutSeconds: 240,
                json: true
            )
        )
        let titledServerStartArguments = try MelixCLICommandCodec.arguments(for: titledServerStartCommand)
        #expect(titledServerStartArguments == [
            "server",
            "start",
            "Gemma 31B",
            "--model", "mlx-community/gemma-4-31b-it-4bit",
            "--host", "127.0.0.1",
            "--port", "12434",
            "--rate-limit-per-minute", "60",
            "--timeout-seconds", "240",
            "--json",
        ])
        #expect(try MelixCLIParser.parse(titledServerStartArguments) == titledServerStartCommand)

        let multiModelServerStartCommand = MelixCLICommand.serverStart(
            .init(
                serverTitle: "Mixed Server",
                defaultModelID: "melix-secondary",
                servedModelIDs: ["melix-primary", "melix-secondary"],
                host: "127.0.0.1",
                port: 12435,
                modelIdleTimeoutSeconds: 300,
                json: true
            )
        )
        let multiModelServerStartArguments = try MelixCLICommandCodec.arguments(
            for: multiModelServerStartCommand
        )
        #expect(multiModelServerStartArguments == [
            "server",
            "start",
            "Mixed Server",
            "--model", "melix-primary",
            "--model", "melix-secondary",
            "--default-model", "melix-secondary",
            "--host", "127.0.0.1",
            "--port", "12435",
            "--model-idle-timeout-seconds", "300",
            "--json",
        ])
        #expect(try MelixCLIParser.parse(multiModelServerStartArguments) == multiModelServerStartCommand)

        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let schemaPath = root.appendingPathComponent("result.schema.json")
        let hintsPath = root.appendingPathComponent("math-hints.txt")
        try #"{"type":"object","required":["answer"]}"#.write(to: schemaPath, atomically: true, encoding: .utf8)
        try "Return the normalized answer.\n".write(to: hintsPath, atomically: true, encoding: .utf8)
        let evalCommand = MelixCLICommand.evalRun(
            .init(
                modelID: "melix-dev-text",
                suites: ["math"],
                profile: .init(
                    resultKind: "json",
                    outputSchemaJSON: #"{"required":["answer"],"type":"object"}"#
                ),
                parameters: [
                    "schema_path": schemaPath.path,
                    "hints_path": hintsPath.path,
                ],
                evalPromptFile: "/tmp/eval-prompt.txt",
                json: true
            )
        )
        let evalArguments = try MelixCLICommandCodec.arguments(for: evalCommand)
        #expect(evalArguments.contains("--schema"))
        #expect(evalArguments.contains(schemaPath.path))
        #expect(evalArguments.contains("--hints"))
        #expect(evalArguments.contains(hintsPath.path))
        #expect(evalArguments.contains("--eval-prompt-file"))
        #expect(evalArguments.contains("/tmp/eval-prompt.txt"))
        #expect(evalArguments.contains("--output-schema-json") == false)
        guard case .evalRun(let parsedEvalOptions) = try MelixCLIParser.parse(evalArguments) else {
            Issue.record("Expected evalRun command from codec arguments")
            return
        }
        #expect(parsedEvalOptions.modelID == "melix-dev-text")
        #expect(parsedEvalOptions.suites == ["math"])
        #expect(parsedEvalOptions.profile.resultKind == "json")
        #expect(parsedEvalOptions.profile.outputSchemaJSON == #"{"required":["answer"],"type":"object"}"#)
        #expect(parsedEvalOptions.parameters["schema_path"] == schemaPath.path)
        #expect(parsedEvalOptions.parameters["schema_sha256"] == melixTestSHA256Hex(Data(#"{"type":"object","required":["answer"]}"#.utf8)))
        #expect(parsedEvalOptions.parameters["schema_size_bytes"] == "39")
        #expect(parsedEvalOptions.parameters["hints_path"] == hintsPath.path)
        #expect(parsedEvalOptions.parameters["hints_sha256"] == melixTestSHA256Hex(Data("Return the normalized answer.\n".utf8)))
        #expect(parsedEvalOptions.parameters["hints_size_bytes"] == "30")
        #expect(parsedEvalOptions.parameters["hints_format"] == "text")
        #expect(parsedEvalOptions.parameters["evaluation_hints_text"] == "Return the normalized answer.")
        #expect(parsedEvalOptions.evalPromptFile == "/tmp/eval-prompt.txt")
        #expect(parsedEvalOptions.json)
    }

    @Test("command codec exposes stable ids and supported argv mappings")
    func commandCodecExposesStableIDsAndSupportedArgvMappings() throws {
        let allCommands: [(MelixCLICommand, String)] = [
            (.doctor(.init()), "doctor"),
            (.estimateImport(.init(repoID: "mlx/qwen", json: true)), "estimate.import"),
            (.estimateImport(.init(repoID: "mlx/qwen", targetKind: "benchmark", json: true)), "estimate.benchmark"),
            (.estimateImport(.init(repoID: "mlx/qwen", targetKind: "eval", json: true)), "estimate.eval"),
            (.estimateImport(.init(repoID: "mlx/qwen", targetKind: "train", json: true)), "estimate.train"),
            (.convert(.init(modelID: "model", outputDir: "/tmp/out", targetFormat: "bundle", json: true)), "convert"),
            (.quantize(.init(modelID: "model", outputDir: "/tmp/out", quantProfileID: "q4", weightQuant: "int4", kvQuant: "int8", quantizationMode: "ptq", sourceArtifactKind: "base_model", sourceArtifactPath: "/tmp/model", calibrationDatasetURI: "/tmp/calibration", qualityDelta: "-0.01", latencyDelta: "-0.2", localInferenceSmokeMode: "runtime_generate", localInferenceSmokePrompt: "smoke", json: true)), "quantize"),
            (.upload(.init(modelID: "model", outputDir: "/tmp/out", targetRepo: "melix/model", artifactPath: "/tmp/model", artifactKind: "bundle", artifactManifestPath: "/tmp/model/manifest.json", json: true)), "upload"),
            (.modelList(.init(json: true)), "model.list"),
            (.modelInspect(.init(modelID: "model", json: true)), "model.inspect"),
            (.modelLoad(.init(modelID: "model", memoryBudgetBytes: 1024, json: true)), "model.load"),
            (.modelUnload(.init(modelID: "model", json: true)), "model.unload"),
            (.modelDownload(.init(modelID: "model", outputDir: "/tmp/model", json: true)), "model.download"),
            (.modelImport(.init(path: "/tmp/model", modelID: "model", modelKind: "text", revision: "main", json: true)), "model.import"),
            (.modelHubSearch(.init(query: "qwen", pageSize: 5, cursor: "next", mlxOnly: false, json: true)), "model.hub.search"),
            (.modelHubShow(.init(repoID: "mlx/qwen", json: true)), "model.hub.show"),
            (.modelHubDownload(.init(repoID: "mlx/qwen", revision: "main", json: true)), "model.hub.download"),
            (.datasetList(.init(json: true)), "dataset.list"),
            (.datasetHubDownload(.init(repoID: "org/dataset", revision: "main", json: true)), "dataset.hub.download"),
            (.datasetRemove(.init(repoID: "org/dataset", revision: "main", snapshotID: "abc123", json: true)), "dataset.remove"),
            (.uriInspect(.init(uri: "hf://model/org/model", json: true)), "uri.inspect"),
            (.uriImport(.init(uri: "hf://model/org/model", modelID: "model", revision: "main", dryRun: true, json: true)), "uri.import"),
            (.recipesList(.init(task: "import", json: true)), "recipes.list"),
            (.recipesShow(.init(recipeID: "import.hf-mlx-model", version: "1", json: true)), "recipes.show"),
            (.recipesValidate(.init(target: "import.hf-mlx-model", json: true)), "recipes.validate"),
            (.recipesPlan(.init(recipeID: "import.hf-mlx-model", version: "1", values: ["repo_id": "org/model", "model_id": "model"], outputPath: "/tmp/plan.json", json: true)), "recipes.plan"),
            (.recipesApply(.init(recipeID: "benchmark.eval.smoke", version: "1", values: ["model_id": "model"], dryRun: true, resume: true, fromStepID: "benchmark", json: true)), "recipes.apply"),
            (.recipesInit(.init(sourceURI: "hf://model/org/model", task: "import", outputPath: "/tmp/import.recipe.json", json: true)), "recipes.init"),
            (.modelRootsList(.init(json: true)), "model.roots.list"),
            (.modelRootsAdd(.init(path: "/models", json: true)), "model.roots.add"),
            (.modelRootsRemove(.init(path: "/models", json: true)), "model.roots.remove"),
            (.modelRootsMove(.init(path: "/models", index: 1, json: true)), "model.roots.move"),
            (.modelRootsRescan(.init(json: true)), "model.roots.rescan"),
            (.serverSnapshot(.init(json: true)), "server.snapshot"),
            (.serverSessionList(.init(json: true)), "server.session.list"),
            (.serverSessionCreate(.init(title: "Server", servedModelIDs: ["model"], host: "127.0.0.1", port: 8080, rateLimitPerMinute: 120, timeoutSeconds: 60, json: true)), "server.session.create"),
            (.serverSessionUpdate(.init(serverSessionID: "server-session-1", title: "Server", servedModelIDs: ["model"], host: "127.0.0.1", port: 8081, rateLimitPerMinute: 60, timeoutSeconds: 30, json: true)), "server.session.update"),
            (.serverSessionRemove(.init(serverSessionID: "server-session-1", json: true)), "server.session.remove"),
            (.serverSessionSelect(.init(serverSessionID: "server-session-1", json: true)), "server.session.select"),
            (.serverStart(.init(serverSessionID: "server-session-1", json: true)), "server.start"),
            (.serverStart(.init(serverTitle: "Gemma 31B", servedModelIDs: ["mlx-community/gemma-4-31b-it-4bit"], host: "127.0.0.1", port: 12434, json: true)), "server.start"),
            (.serverPause(.init(serverSessionID: "server-session-1", json: true)), "server.pause"),
            (.serverResume(.init(serverSessionID: "server-session-1", json: true)), "server.resume"),
            (.serverWake(.init(serverSessionID: "server-session-1", json: true)), "server.wake"),
            (.serverStop(.init(serverSessionID: "server-session-1", json: true)), "server.stop"),
            (.serverSetIdlePolicy(.init(serverSessionID: "server-session-1", autoSleepEnabled: true, lightSleepAfterSeconds: 30, deepSleepAfterSeconds: 60, json: true)), "server.set-idle-policy"),
            (.remoteServerList(.init(json: true)), "remote-server.list"),
            (.remoteServerAdd(.init(remoteServerID: "custom", title: "Custom", providerPreset: .custom, providerKind: "openai-compatible", baseURL: "https://sub2api.example/v1", defaultModelID: "remote-model", apiKey: "sk-secret", timeoutSeconds: 60, rateLimitPerMinute: 10, json: true)), "remote-server.add"),
            (.remoteServerUpdate(.init(remoteServerID: "custom", title: "Custom Updated", providerPreset: .custom, providerKind: "openai-compatible", baseURL: "https://sub2api.example/updated/v1", defaultModelID: "remote-model-2", apiKey: "sk-new", timeoutSeconds: 90, rateLimitPerMinute: 20, json: true)), "remote-server.update"),
            (.remoteServerRemove(.init(remoteServerID: "custom", json: true)), "remote-server.remove"),
            (.remoteServerTest(.init(remoteServerID: "custom", remoteModelID: "remote-model", json: true)), "remote-server.test"),
            (.chatRun(.init(modelID: "model", message: "hello", systemPrompt: "system", serverSessionID: "server-session-1", json: true)), "chat.run"),
            (.chatRun(.init(remoteServerID: "custom", remoteModelID: "remote-model", message: "hello", systemPrompt: "system", serverSessionID: "server-session-1", json: true)), "chat.run"),
            (.loraList(.init(modelID: "model", json: true)), "lora.list"),
            (.loraTrain(.init(modelID: "model", datasetSourceKind: "huggingface", datasetURI: "dataset/repo", adapterName: "adapter", targetRepo: "melix/adapter", trainingMode: "qlora", parameters: ["derived_model_alias": "derived", "response_only": "true"], preflightFitCheck: true, allowMemoryRisk: true, json: true)), "lora.train"),
            (.alignmentTrain(.init(modelID: "model", datasetURI: "/tmp/preference.jsonl", adapterName: "aligned", algorithm: "dpo", json: true)), "alignment.train"),
            (.loraDatasetInspect(.init(modelID: "model", datasetURI: "/tmp/data.jsonl", json: true)), "lora.dataset.inspect"),
            (.loraDatasetBuild(.init(modelID: "model", datasetURI: "/tmp/data.jsonl", outputDir: "/tmp/out", json: true)), "lora.dataset.build"),
            (.loraActivate(.init(modelID: "model", adapterPath: "/tmp/adapter.json", derivedModelAlias: "derived", activationMode: "adapter_backed_runtime", json: true)), "lora.activate"),
            (.loraRemoveDerived(.init(modelID: "model", derivedModelID: "derived", json: true)), "lora.remove-derived"),
            (.loraPublish(.init(modelID: "model", targetRepo: "melix/adapter", exportKind: .adapterExport, artifactPath: "/tmp/adapter", artifactManifestPath: "/tmp/adapter/manifest.json", json: true)), "lora.publish"),
            (.loraExperimentsList(.init(modelID: "model", json: true)), "lora.experiments.list"),
            (.loraExperimentsShow(.init(modelID: "model", groupID: "nightly-qwen35", json: true)), "lora.experiments.show"),
            (.loraPublishesList(.init(modelID: "model", json: true)), "lora.publishes.list"),
            (.loraPublishesShow(.init(modelID: "model", jobID: "model-ops-0042", json: true)), "lora.publishes.show"),
            (.loraResume(.init(modelID: "model", groupID: "nightly-qwen35", presetID: "balanced_adapter", adapterName: "resumed", datasetURI: "/tmp/data.jsonl", json: true)), "lora.resume"),
            (.benchRun(.init(modelID: "model", suites: ["smoke"], contextLengths: [1024], generationLength: 128, batchSizes: [1], repeats: 2, cacheProfile: "cold", reasoningMode: "disabled", structuredOutputMode: "disabled", parameters: ["sample_size": "4", "batch_factor": "1"], json: true)), "bench.run"),
            (.benchList(.init(json: true)), "bench.list"),
            (.benchExportCSV(.init(jobID: "bench-1", outputPath: "/tmp/bench.csv", json: true)), "bench.export-csv"),
            (.benchReport(.init(sourcePath: "/tmp/bench", format: "json")), "bench.report"),
            (.benchMatrixRun(.init(modelID: "model", taskKind: "text-generation", suites: ["smoke"], contextLengths: [1024], generationLengths: [128], batchSizes: [1], cacheProfiles: ["cold"], reasoningModes: ["disabled"], structuredOutputModes: ["disabled"], concurrencyLevels: [1], repeats: 2, requests: 4, allowLargeMatrix: true, json: true)), "bench.matrix.run"),
            (.benchMatrixList(.init(json: true)), "bench.matrix.list"),
            (.benchMatrixExportSummaryCSV(.init(jobID: "matrix-1", outputPath: "/tmp/matrix.csv", json: true)), "bench.matrix.export-summary-csv"),
            (.benchMatrixExportRequestsCSV(.init(jobID: "matrix-1", outputPath: "/tmp/matrix-requests.csv", json: true)), "bench.matrix.export-requests-csv"),
            (.evalRun(.init(hfRepoID: "model/repo", suites: ["mmlu"], datasetID: "mmlu.dev.v1", sampleSize: 4, source: .localCSV(path: "/tmp/eval.csv"), fieldMapping: .init(systemPath: "system", inputTextPath: "input", targetPath: "target", sampleIDPath: "id"), profile: .init(profileType: "final_result", resultKind: "text", extractionMode: "heuristic_final", threshold: 0.75, outputSchemaJSON: "{\"type\":\"string\"}", ignoredPaths: ["meta"]), parameters: ["batch_factor": "1"], preflightFitCheck: true, allowMemoryRisk: true, json: true)), "eval.run"),
            (.evalRun(.init(remoteServerID: "custom", remoteModelID: "remote-model", suites: ["event_extraction"], datasetID: "top200", sampleSize: 3, source: .localJSONL(path: "/tmp/top200.jsonl"), fieldMapping: .init(inputTextPath: "dialogue", targetPath: "events", sampleIDPath: "dialogue_id"), profile: .init(scoringMode: "event_extraction_weighted_f1"), evalPromptID: "event-prod", evalPromptRevisionID: "rev-1", json: true)), "eval.run"),
            (.evalPromptList(.init(json: true)), "eval.prompt.list"),
            (.evalPromptShow(.init(promptID: "event-prod", revisionID: "rev-1", json: true)), "eval.prompt.show"),
            (.evalPromptCreate(.init(promptID: "event-prod", title: "Event Prod", systemPromptFile: "/tmp/prompt.txt", json: true)), "eval.prompt.create"),
            (.evalPromptUpdate(.init(promptID: "event-prod", systemPromptFile: "/tmp/prompt.txt", json: true)), "eval.prompt.update"),
            (.evalPromptFreeze(.init(promptID: "event-prod", revisionID: "rev-1", json: true)), "eval.prompt.freeze"),
            (.evalPromptArchive(.init(promptID: "event-prod", json: true)), "eval.prompt.archive"),
            (.evalCompare(.init(modelID: "base", targetModelIDs: ["target"], suites: ["mmlu"], datasetID: "mmlu.dev.v1", sampleSize: 4, json: true)), "eval.compare"),
            (.evalList(.init(json: true)), "eval.list"),
            (.evalCompareExportSummaryCSV(.init(jobID: "compare-1", outputPath: "/tmp/compare.csv", json: true)), "eval.compare.export-summary-csv"),
            (.evalCompareExportSamplesCSV(.init(jobID: "compare-1", outputPath: "/tmp/compare-samples.csv", json: true)), "eval.compare.export-samples-csv"),
            (.evalCompareExportSamplesJSONL(.init(jobID: "compare-1", outputPath: "/tmp/compare-samples.jsonl", json: true)), "eval.compare.export-samples-jsonl"),
            (.evalExportSummaryCSV(.init(jobID: "eval-1", outputPath: "/tmp/eval.csv", json: true)), "eval.export-summary-csv"),
            (.evalExportSamplesCSV(.init(jobID: "eval-1", outputPath: "/tmp/eval-samples.csv", json: true)), "eval.export-samples-csv"),
            (.evalExportSamplesJSONL(.init(jobID: "eval-1", outputPath: "/tmp/eval-samples.jsonl", json: true)), "eval.export-samples-jsonl"),
            (.evalReport(.init(sourcePath: "/tmp/eval", format: "markdown")), "eval.report"),
            (.runsList(.init(sourcePath: "/tmp/runs", json: true)), "runs.list"),
            (.runsShow(.init(runID: "bench-1", sourcePath: "/tmp/runs", json: true)), "runs.show"),
            (.runsExport(.init(runID: "bench-1", sourcePath: "/tmp/runs", format: "md", outputPath: "/tmp/run.md")), "runs.export"),
            (.pipelineRun(.init(filePath: "/tmp/pipeline.json", inputsPath: "/tmp/inputs.json", receiptDir: "/tmp/receipts", traceID: "trace", resume: true, fromStepID: "chat", dryRun: true)), "pipeline.run"),
        ]

        for (command, expectedID) in allCommands {
            #expect(MelixCLICommandCodec.commandID(for: command) == expectedID)
        }

        let supportedCommands: [MelixCLICommand] = [
            .doctor(.init(json: true)),
            .estimateImport(.init(repoID: "mlx/qwen", json: true)),
            .estimateImport(.init(repoID: "mlx/qwen", targetKind: "benchmark", json: true)),
            .estimateImport(.init(repoID: "mlx/qwen", targetKind: "eval", json: true)),
            .estimateImport(.init(repoID: "mlx/qwen", targetKind: "train", json: true)),
            .convert(.init(modelID: "model", outputDir: "/tmp/out", targetFormat: "bundle", json: true)),
            .quantize(.init(modelID: "model", outputDir: "/tmp/out", quantProfileID: "q4", weightQuant: "int4", kvQuant: "int8", quantizationMode: "ptq", sourceArtifactKind: "base_model", sourceArtifactPath: "/tmp/model", calibrationDatasetURI: "/tmp/calibration", qualityDelta: "-0.01", latencyDelta: "-0.2", localInferenceSmokeMode: "runtime_generate", localInferenceSmokePrompt: "smoke", json: true)),
            .upload(.init(modelID: "model", outputDir: "/tmp/out", targetRepo: "melix/model", artifactPath: "/tmp/model", artifactKind: "bundle", artifactManifestPath: "/tmp/model/manifest.json", json: true)),
            .modelImport(.init(path: "/tmp/model", modelID: "model", modelKind: "text", revision: "main", json: true)),
            .modelHubDownload(.init(repoID: "mlx/qwen", revision: "main", json: true)),
            .datasetList(.init(json: true)),
            .datasetHubDownload(.init(repoID: "org/dataset", revision: "main", json: true)),
            .datasetRemove(.init(repoID: "org/dataset", revision: "main", snapshotID: "abc123", json: true)),
            .uriInspect(.init(uri: "hf://model/org/model", json: true)),
            .uriImport(.init(uri: "hf://model/org/model", modelID: "model", revision: "main", dryRun: true, json: true)),
            .recipesList(.init(task: "import", json: true)),
            .recipesShow(.init(recipeID: "import.hf-mlx-model", version: "1", json: true)),
            .recipesValidate(.init(target: "import.hf-mlx-model", json: true)),
            .recipesPlan(.init(recipeID: "import.hf-mlx-model", version: "1", values: ["repo_id": "org/model", "model_id": "model"], outputPath: "/tmp/plan.json", json: true)),
            .recipesApply(.init(recipeID: "benchmark.eval.smoke", version: "1", values: ["model_id": "model"], dryRun: true, resume: true, fromStepID: "benchmark", json: true)),
            .recipesInit(.init(sourceURI: "hf://model/org/model", task: "import", outputPath: "/tmp/import.recipe.json", json: true)),
            .modelRootsList(.init(json: true)),
            .modelRootsAdd(.init(path: "/models", json: true)),
            .modelRootsRemove(.init(path: "/models", json: true)),
            .modelRootsMove(.init(path: "/models", index: 1, json: true)),
            .modelRootsRescan(.init(json: true)),
            .serverSessionCreate(.init(title: "Server", servedModelIDs: ["model"], host: "127.0.0.1", port: 8080, rateLimitPerMinute: 120, timeoutSeconds: 60, json: true)),
            .serverSessionUpdate(.init(serverSessionID: "server-session-1", title: "Server", servedModelIDs: ["model"], host: "127.0.0.1", port: 8081, rateLimitPerMinute: 60, timeoutSeconds: 30, json: true)),
            .serverSessionRemove(.init(serverSessionID: "server-session-1", json: true)),
            .serverSessionSelect(.init(serverSessionID: "server-session-1", json: true)),
            .serverStart(.init(serverSessionID: "server-session-1", json: true)),
            .serverPause(.init(serverSessionID: "server-session-1", json: true)),
            .serverResume(.init(serverSessionID: "server-session-1", json: true)),
            .serverWake(.init(serverSessionID: "server-session-1", json: true)),
            .serverStop(.init(serverSessionID: "server-session-1", json: true)),
            .serverSetIdlePolicy(.init(serverSessionID: "server-session-1", autoSleepEnabled: false, lightSleepAfterSeconds: 30, deepSleepAfterSeconds: 60, json: true)),
            .remoteServerList(.init(json: true)),
            .remoteServerAdd(.init(remoteServerID: "custom", title: "Custom", providerPreset: .custom, providerKind: "openai-compatible", baseURL: "https://sub2api.example/v1", defaultModelID: "remote-model", apiKey: "sk-secret", timeoutSeconds: 60, rateLimitPerMinute: 10, json: true)),
            .remoteServerUpdate(.init(remoteServerID: "custom", title: "Custom Updated", providerPreset: .custom, providerKind: "openai-compatible", baseURL: "https://sub2api.example/updated/v1", defaultModelID: "remote-model-2", apiKey: "sk-new", timeoutSeconds: 90, rateLimitPerMinute: 20, json: true)),
            .remoteServerRemove(.init(remoteServerID: "custom", json: true)),
            .remoteServerTest(.init(remoteServerID: "custom", remoteModelID: "remote-model", json: true)),
            .chatRun(.init(modelID: "model", message: "hello", systemPrompt: "system", serverSessionID: "server-session-1", json: true)),
            .chatRun(.init(remoteServerID: "custom", remoteModelID: "remote-model", message: "hello", systemPrompt: "system", serverSessionID: "server-session-1", json: true)),
            .loraTrain(.init(modelID: "model", datasetSourceKind: "huggingface", datasetURI: "dataset/repo", adapterName: "adapter", targetRepo: "melix/adapter", trainingMode: "qlora", parameters: ["derived_model_alias": "derived", "response_only": "true"], json: true)),
            .alignmentTrain(.init(modelID: "model", datasetURI: "/tmp/preference.jsonl", adapterName: "aligned", algorithm: "dpo", json: true)),
            .loraActivate(.init(modelID: "model", adapterPath: "/tmp/adapter.json", derivedModelAlias: "derived", activationMode: "adapter_backed_runtime", json: true)),
            .loraPublish(.init(modelID: "model", targetRepo: "melix/adapter", exportKind: .adapterExport, artifactPath: "/tmp/adapter/manifest.json", artifactManifestPath: "/tmp/adapter/manifest.json", json: true)),
            .benchRun(.init(modelID: "model", suites: ["smoke"], contextLengths: [1024], generationLength: 128, batchSizes: [1], repeats: 2, cacheProfile: "cold", reasoningMode: "disabled", structuredOutputMode: "disabled", parameters: ["sample_size": "4", "batch_factor": "1"], json: true)),
            .benchMatrixRun(.init(modelID: "model", taskKind: "text-generation", suites: ["smoke"], contextLengths: [1024], generationLengths: [128], batchSizes: [1], cacheProfiles: ["cold"], reasoningModes: ["disabled"], structuredOutputModes: ["disabled"], concurrencyLevels: [1], repeats: 2, requests: 4, allowLargeMatrix: true, json: true)),
            .benchExportCSV(.init(jobID: "bench-1", outputPath: "/tmp/bench.csv", json: true)),
            .benchMatrixExportSummaryCSV(.init(jobID: "matrix-1", outputPath: "/tmp/matrix.csv", json: true)),
            .benchMatrixExportRequestsCSV(.init(jobID: "matrix-1", outputPath: "/tmp/matrix-requests.csv", json: true)),
            .evalRun(.init(modelID: "model", suites: ["mmlu"], datasetID: "mmlu.dev.v1", sampleSize: 4, source: .huggingFaceDataset(datasetPath: "org/ds", datasetName: "name", datasetRevision: "rev", split: "test"), fieldMapping: .init(systemPath: "system", inputTextPath: "input", targetPath: "target", sampleIDPath: "id"), profile: .init(profileType: "final_result", resultKind: "text", extractionMode: "heuristic_final", threshold: 0.75, outputSchemaJSON: "{\"type\":\"string\"}", ignoredPaths: ["meta"]), parameters: ["batch_factor": "1"], json: true)),
            .evalRun(.init(remoteServerID: "custom", remoteModelID: "remote-model", suites: ["event_extraction"], datasetID: "top200", sampleSize: 3, source: .localJSONL(path: "/tmp/top200.jsonl"), fieldMapping: .init(inputTextPath: "dialogue", targetPath: "events", sampleIDPath: "dialogue_id"), profile: .init(scoringMode: "event_extraction_weighted_f1"), evalPromptID: "event-prod", evalPromptRevisionID: "rev-1", json: true)),
            .evalPromptList(.init(json: true)),
            .evalPromptShow(.init(promptID: "event-prod", revisionID: "rev-1", json: true)),
            .evalPromptCreate(.init(promptID: "event-prod", title: "Event Prod", systemPromptFile: "/tmp/prompt.txt", json: true)),
            .evalPromptUpdate(.init(promptID: "event-prod", systemPromptFile: "/tmp/prompt.txt", json: true)),
            .evalPromptFreeze(.init(promptID: "event-prod", revisionID: "rev-1", json: true)),
            .evalPromptArchive(.init(promptID: "event-prod", json: true)),
            .evalExportSummaryCSV(.init(jobID: "eval-1", outputPath: "/tmp/eval.csv", json: true)),
            .evalExportSamplesCSV(.init(jobID: "eval-1", outputPath: "/tmp/eval-samples.csv", json: true)),
            .evalExportSamplesJSONL(.init(jobID: "eval-1", outputPath: "/tmp/eval-samples.jsonl", json: true)),
            .pipelineRun(.init(filePath: "/tmp/pipeline.json", inputsPath: "/tmp/inputs.json", receiptDir: "/tmp/receipts", traceID: "trace", resume: true, fromStepID: "chat", dryRun: true)),
        ]

        for command in supportedCommands {
            let arguments = try MelixCLICommandCodec.arguments(for: command)
            #expect(arguments.isEmpty == false)
            if case .pipelineRun = command {
                #expect(arguments.contains("--json") == false)
            } else {
                #expect(arguments.contains("--json"))
                let jsonCommand = try MelixCLICommandCodec.jsonEnabledCommand(for: command)
                #expect(MelixCLICommandCodec.commandID(for: jsonCommand) == MelixCLICommandCodec.commandID(for: command))
                #expect(try MelixCLICommandCodec.arguments(for: jsonCommand).contains("--json"))
            }
        }

        let formatOwningCommands: [MelixCLICommand] = [
            .benchReport(.init(sourcePath: "/tmp/bench", format: "json")),
            .evalReport(.init(sourcePath: "/tmp/eval", format: "markdown")),
            .runsList(.init(sourcePath: "/tmp/runs", json: true)),
            .runsShow(.init(runID: "bench-1", sourcePath: "/tmp/runs", json: true)),
            .runsExport(.init(runID: "bench-1", sourcePath: "/tmp/runs", format: "md", outputPath: "/tmp/run.md")),
        ]
        for command in formatOwningCommands {
            let arguments = try MelixCLICommandCodec.arguments(for: command)
            #expect(arguments.isEmpty == false)
            #expect(try MelixCLIParser.parse(arguments) == command)
        }

        let unsupported: [MelixCLICommand] = [
            .modelList(.init()),
            .loraDatasetInspect(.init(modelID: "model", datasetURI: "/tmp/data.jsonl")),
        ]
        for command in unsupported {
            do {
                _ = try MelixCLICommandCodec.arguments(for: command)
                Issue.record("Expected unsupported codec command \(MelixCLICommandCodec.commandID(for: command)) to fail.")
            } catch let error as MelixCLIError {
                #expect(error == .runtime("Command codec does not support \(MelixCLICommandCodec.commandID(for: command))."))
            }
        }
    }

    @Test("parses estimate import with positional and option repo ids")
    func parsesEstimateImportCommand() throws {
        let positionalCommand = try MelixCLIParser.parse([
            "estimate",
            "import",
            "mlx-community/Qwen3.5-9B-MLX-4bit",
            "--json",
        ])
        let optionCommand = try MelixCLIParser.parse([
            "estimate",
            "import",
            "--repo-id", "mlx-community/Qwen3.5-9B-MLX-8bit",
        ])

        guard case .estimateImport(let positionalOptions) = positionalCommand else {
            Issue.record("Expected estimateImport command")
            return
        }
        guard case .estimateImport(let optionOptions) = optionCommand else {
            Issue.record("Expected estimateImport command")
            return
        }

        #expect(positionalOptions.repoID == "mlx-community/Qwen3.5-9B-MLX-4bit")
        #expect(positionalOptions.json)
        #expect(optionOptions.repoID == "mlx-community/Qwen3.5-9B-MLX-8bit")
        #expect(optionOptions.json == false)
    }

    @Test("parses estimate benchmark eval and train receipts")
    func parsesEstimateRunTargetReceipts() throws {
        let cases: [(String, String, [String], String, String)] = [
            ("benchmark", "benchmark", ["--context-length", "4096"], "context_length", "4096"),
            ("eval", "eval", ["--context", "event dialog", "--dataset", "top200"], "dataset", "top200"),
            ("train", "train", ["--model", "mlx-community/Qwen3.5-9B-MLX-4bit", "--dataset", "alpaca", "--lora", "adapter"], "lora", "adapter"),
        ]
        for (action, targetKind, extraArguments, inputKey, inputValue) in cases {
            let command = try MelixCLIParser.parse([
                "estimate",
                action,
                action == "train" ? "" : "--repo-id", action == "train" ? "" : "mlx-community/Qwen3.5-9B-MLX-4bit",
            ].filter { $0.isEmpty == false } + extraArguments + [
                "--json",
            ])
            guard case .estimateImport(let options) = command else {
                Issue.record("Expected estimateImport command for \(action)")
                continue
            }

            #expect(options.repoID == "mlx-community/Qwen3.5-9B-MLX-4bit")
            #expect(options.targetKind == targetKind)
            #expect(options.targetInputs[inputKey] == inputValue)
            #expect(options.json)
            #expect(MelixCLICommandCodec.commandID(for: command) == "estimate.\(targetKind)")
            #expect(try MelixCLIParser.parse(MelixCLICommandCodec.arguments(for: command)) == command)
        }
    }

    @Test("estimate import rejects missing conflicting and unknown inputs")
    func estimateImportRejectsInvalidInputs() throws {
        try assertError(
            for: [
                "estimate",
            ],
            equals: .usage(MelixCLIParser.usageText)
        )
        try assertError(
            for: [
                "estimate",
                "import",
            ],
            equals: .missingRequired("HF_REPO or --repo-id is required for melix estimate import.")
        )
        try assertError(
            for: [
                "estimate",
                "import",
                "mlx-community/Qwen3.5-9B-MLX-4bit",
                "--repo-id", "mlx-community/Qwen3.5-9B-MLX-8bit",
            ],
            equals: .usage("melix estimate import accepts only one Hugging Face repo id.")
        )
        try assertError(
            for: [
                "estimate",
                "eval",
                "--repo-id", "mlx-community/Qwen3.5-9B-MLX-4bit",
                "--model", "mlx-community/Qwen3.5-9B-MLX-8bit",
            ],
            equals: .usage("melix estimate eval accepts only one Hugging Face repo id.")
        )
    }

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

    @Test("parses model download hub download list and roots commands")
    func parsesModelDownloadHubDownloadListAndRootsCommands() throws {
        let modelDownloadCommand = try MelixCLIParser.parse([
            "model",
            "download",
            "--model-id", "melix-dev-text",
            "--output-dir", "/tmp/melix-downloads/melix-dev-text",
            "--json",
        ])
        let downloadCommand = try MelixCLIParser.parse([
            "model",
            "hub",
            "download",
            "--repo-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--revision", "main",
            "--hf-token", "hf_secret_token",
            "--json",
        ])
        let listCommand = try MelixCLIParser.parse([
            "model",
            "list",
            "--json",
        ])
        let addRootCommand = try MelixCLIParser.parse([
            "model",
            "roots",
            "add",
            "--path", "/tmp/models-a",
        ])
        let moveRootCommand = try MelixCLIParser.parse([
            "model",
            "roots",
            "move",
            "--path", "/tmp/models-a",
            "--index", "1",
        ])

        guard case .modelDownload(let modelDownloadOptions) = modelDownloadCommand else {
            Issue.record("Expected modelDownload command")
            return
        }
        guard case .modelHubDownload(let downloadOptions) = downloadCommand else {
            Issue.record("Expected modelHubDownload command")
            return
        }
        guard case .modelList(let listOptions) = listCommand else {
            Issue.record("Expected modelList command")
            return
        }
        guard case .modelRootsAdd(let addOptions) = addRootCommand else {
            Issue.record("Expected modelRootsAdd command")
            return
        }
        guard case .modelRootsMove(let moveOptions) = moveRootCommand else {
            Issue.record("Expected modelRootsMove command")
            return
        }

        #expect(modelDownloadOptions.modelID == "melix-dev-text")
        #expect(modelDownloadOptions.outputDir == "/tmp/melix-downloads/melix-dev-text")
        #expect(modelDownloadOptions.json)
        #expect(downloadOptions.repoID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(downloadOptions.revision == "main")
        #expect(downloadOptions.hfToken == "hf_secret_token")
        #expect(downloadOptions.json)
        #expect(listOptions.json)
        #expect(addOptions.path == "/tmp/models-a")
        #expect(moveOptions.path == "/tmp/models-a")
        #expect(moveOptions.index == 1)
    }

    @Test("parses dataset list download and remove commands")
    func parsesDatasetListDownloadAndRemoveCommands() throws {
        let listCommand = try MelixCLIParser.parse([
            "dataset",
            "list",
            "--json",
        ])
        let downloadCommand = try MelixCLIParser.parse([
            "dataset",
            "hub",
            "download",
            "--repo-id", "Jax-dan/HundredCV-Chat",
            "--revision", "main",
            "--hf-token", "hf_secret_token",
            "--json",
        ])
        let removeCommand = try MelixCLIParser.parse([
            "dataset",
            "remove",
            "--repo-id", "Jax-dan/HundredCV-Chat",
            "--snapshot-id", "abc123",
            "--json",
        ])

        guard case .datasetList(let listOptions) = listCommand else {
            Issue.record("Expected datasetList command")
            return
        }
        guard case .datasetHubDownload(let downloadOptions) = downloadCommand else {
            Issue.record("Expected datasetHubDownload command")
            return
        }
        guard case .datasetRemove(let removeOptions) = removeCommand else {
            Issue.record("Expected datasetRemove command")
            return
        }

        #expect(listOptions.json)
        #expect(downloadOptions.repoID == "Jax-dan/HundredCV-Chat")
        #expect(downloadOptions.revision == "main")
        #expect(downloadOptions.hfToken == "hf_secret_token")
        #expect(downloadOptions.json)
        #expect(removeOptions.repoID == "Jax-dan/HundredCV-Chat")
        #expect(removeOptions.revision == "main")
        #expect(removeOptions.snapshotID == "abc123")
        #expect(removeOptions.json)
    }

    @Test("parses uri resolver commands")
    func parsesURIResolverCommands() throws {
        let inspect = try MelixCLIParser.parse([
            "uri",
            "inspect",
            "hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--json",
        ])
        let importCommand = try MelixCLIParser.parse([
            "uri",
            "import",
            "hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--model-id", "qwen35-08b",
            "--revision", "refs/pr/1",
            "--dry-run",
            "--json",
        ])
        let importFromRevisionURI = try MelixCLIParser.parse([
            "uri",
            "import",
            "hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit@refs/pr/2",
            "--dry-run",
            "--json",
        ])

        #expect(
            inspect ==
                .uriInspect(
                    .init(
                        uri: "hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                        json: true
                    )
                )
        )
        #expect(
            importFromRevisionURI ==
                .uriImport(
                    .init(
                        uri: "hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit@refs/pr/2",
                        dryRun: true,
                        json: true
                    )
                )
        )
        #expect(
            importCommand ==
                .uriImport(
                    .init(
                        uri: "hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                        modelID: "qwen35-08b",
                        revision: "refs/pr/1",
                        dryRun: true,
                        json: true
                    )
                )
        )

        #expect(throws: MelixCLIError.missingRequired("URI is required for melix uri inspect.")) {
            try MelixCLIParser.parse(["uri", "inspect", "--json"])
        }
        #expect(throws: MelixCLIError.missingRequired("URI is required for melix uri import.")) {
            try MelixCLIParser.parse(["uri", "import", "--json"])
        }
    }

    @Test("parses workflow recipe catalog commands")
    func parsesWorkflowRecipeCatalogCommands() throws {
        let list = try MelixCLIParser.parse([
            "recipes",
            "list",
            "--task", "import",
            "--json",
        ])
        let show = try MelixCLIParser.parse([
            "recipes",
            "show",
            "import.hf-mlx-model",
            "--version", "1",
            "--json",
        ])
        let validate = try MelixCLIParser.parse([
            "recipes",
            "validate",
            "import.hf-mlx-model",
            "--json",
        ])
        let plan = try MelixCLIParser.parse([
            "recipes",
            "plan",
            "import.hf-mlx-model",
            "--set", "repo_id=mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--set", "model_id=qwen35-08b",
            "--output", "/tmp/recipe-plan.json",
            "--json",
        ])
        let apply = try MelixCLIParser.parse([
            "recipes",
            "apply",
            "benchmark.eval.smoke",
            "--version", "1",
            "--set", "model_id=qwen35-08b",
            "--dry-run",
            "--resume",
            "--from-step", "benchmark",
            "--json",
        ])
        let initCommand = try MelixCLIParser.parse([
            "recipes",
            "init",
            "--from", "hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--task", "import",
            "--output", "/tmp/import.recipe.json",
            "--json",
        ])

        #expect(list == .recipesList(.init(task: "import", json: true)))
        #expect(show == .recipesShow(.init(recipeID: "import.hf-mlx-model", version: "1", json: true)))
        #expect(validate == .recipesValidate(.init(target: "import.hf-mlx-model", json: true)))
        #expect(
            plan ==
                .recipesPlan(
                    .init(
                        recipeID: "import.hf-mlx-model",
                        values: [
                            "repo_id": "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                            "model_id": "qwen35-08b",
                        ],
                        outputPath: "/tmp/recipe-plan.json",
                        json: true
                    )
                )
        )
        #expect(
            apply ==
                .recipesApply(
                    .init(
                        recipeID: "benchmark.eval.smoke",
                        version: "1",
                        values: ["model_id": "qwen35-08b"],
                        dryRun: true,
                        resume: true,
                        fromStepID: "benchmark",
                        json: true
                    )
                )
        )
        #expect(
            initCommand ==
                .recipesInit(
                    .init(
                        sourceURI: "hf://model/mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                        task: "import",
                        outputPath: "/tmp/import.recipe.json",
                        json: true
                    )
                )
        )

        #expect(throws: MelixCLIError.missingRequired("RECIPE_ID is required for melix recipes show.")) {
            try MelixCLIParser.parse(["recipes", "show", "--json"])
        }
        #expect(throws: MelixCLIError.usage("--set must use KEY=VALUE.")) {
            try MelixCLIParser.parse(["recipes", "plan", "import.hf-mlx-model", "--set", "=bad"])
        }
        #expect(throws: MelixCLIError.missingRequired("--from is required for melix recipes init.")) {
            try MelixCLIParser.parse(["recipes", "init", "--task", "import"])
        }
        #expect(throws: MelixCLIError.missingRequired("--task is required for melix recipes init.")) {
            try MelixCLIParser.parse(["recipes", "init", "--from", "hf://model/org/repo"])
        }
    }

    @Test("parses model import command and rejects missing import path")
    func parsesModelImportCommandAndRejectsMissingImportPath() throws {
        let importCommand = try MelixCLIParser.parse([
            "model",
            "import",
            "--path", "/tmp/qwen-local-model",
            "--model-id", "melix-dev-qwen-local",
            "--model-kind", "text",
            "--revision", "main",
            "--json",
        ])

        #expect(
            importCommand ==
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

        #expect(throws: MelixCLIError.missingRequired("--path is required for melix model import.")) {
            try MelixCLIParser.parse([
                "model",
                "import",
                "--model-id", "melix-dev-qwen-local",
            ])
        }

        #expect(throws: MelixCLIError.missingRequired("--model-id is required for melix model import.")) {
            try MelixCLIParser.parse([
                "model",
                "import",
                "--path", "/tmp/qwen-local-model",
            ])
        }
    }

    @Test("parses chat run command and rejects missing message")
    func parsesChatRunCommandAndRejectsMissingMessage() throws {
        let chatCommand = try MelixCLIParser.parse([
            "chat",
            "run",
            "--model-id", "melix-dev-qwen-local",
            "--message", "Reply with BASE_OK",
            "--system", "Be terse.",
            "--server-session-id", "server-session-1",
            "--json",
        ])

        #expect(
            chatCommand ==
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

        #expect(throws: MelixCLIError.missingRequired("--message is required for melix chat run.")) {
            try MelixCLIParser.parse([
                "chat",
                "run",
                "--model-id", "melix-dev-qwen-local",
            ])
        }
    }

    @Test("chat parser rejects missing subcommand missing model id and unknown actions")
    func chatParserRejectsMissingSubcommandMissingModelIDAndUnknownActions() throws {
        #expect(throws: MelixCLIError.usage(MelixCLIParser.usageText)) {
            try MelixCLIParser.parse([
                "chat",
            ])
        }

        #expect(throws: MelixCLIError.missingRequired("Exactly one of --model-id or --remote-server-id is required for melix chat run.")) {
            try MelixCLIParser.parse([
                "chat",
                "run",
                "--message", "Reply with BASE_OK",
            ])
        }

        #expect(throws: MelixCLIError.usage(MelixCLIParser.usageText)) {
            try MelixCLIParser.parse([
                "chat",
                "inspect",
            ])
        }
    }

    @Test("parses server session create update remove and select commands")
    func parsesServerSessionCRUDCommands() throws {
        let createCommand = try MelixCLIParser.parse([
            "server",
            "session",
            "create",
            "--title", "Qwen Session",
            "--models", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit,melix-secondary",
            "--default-model", "melix-secondary",
            "--host", "127.0.0.1",
            "--port", "12434",
            "--model-idle-timeout-seconds", "300",
            "--draft-model-id", "z-lab/Qwen3.5-27B-DFlash",
            "--num-draft-tokens", "4",
            "--json",
        ])
        let updateCommand = try MelixCLIParser.parse([
            "server",
            "session",
            "update",
            "--server-session-id", "server-session-qwen",
            "--model", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--model", "melix-secondary",
            "--default-model", "melix-secondary",
            "--port", "12434",
            "--timeout-seconds", "90",
            "--model-idle-timeout-seconds", "240",
            "--acceleration-mode", "speculative_decode",
            "--draft-model-id", "z-lab/Qwen3.5-27B-DFlash",
            "--num-draft-tokens", "8",
        ])
        let removeCommand = try MelixCLIParser.parse([
            "server",
            "session",
            "remove",
            "--server-session-id", "server-session-qwen",
        ])
        let selectCommand = try MelixCLIParser.parse([
            "server",
            "session",
            "select",
            "--server-session-id", "server-session-qwen",
        ])

        guard case .serverSessionCreate(let createOptions) = createCommand else {
            Issue.record("Expected serverSessionCreate command")
            return
        }
        guard case .serverSessionUpdate(let updateOptions) = updateCommand else {
            Issue.record("Expected serverSessionUpdate command")
            return
        }
        guard case .serverSessionRemove(let removeOptions) = removeCommand else {
            Issue.record("Expected serverSessionRemove command")
            return
        }
        guard case .serverSessionSelect(let selectOptions) = selectCommand else {
            Issue.record("Expected serverSessionSelect command")
            return
        }

        #expect(createOptions.title == "Qwen Session")
        #expect(createOptions.defaultModelID == "melix-secondary")
        #expect(createOptions.servedModelIDs == [
            "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "melix-secondary",
        ])
        #expect(createOptions.host == "127.0.0.1")
        #expect(createOptions.port == 12434)
        #expect(createOptions.modelIdleTimeoutSeconds == 300)
        #expect(createOptions.accelerationMode == "speculative_decode")
        #expect(createOptions.draftModelID == "z-lab/Qwen3.5-27B-DFlash")
        #expect(createOptions.numDraftTokens == 4)
        #expect(createOptions.json)
        #expect(updateOptions.serverSessionID == "server-session-qwen")
        #expect(updateOptions.defaultModelID == "melix-secondary")
        #expect(updateOptions.servedModelIDs == [
            "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "melix-secondary",
        ])
        #expect(updateOptions.port == 12434)
        #expect(updateOptions.timeoutSeconds == 90)
        #expect(updateOptions.modelIdleTimeoutSeconds == 240)
        #expect(updateOptions.accelerationMode == "speculative_decode")
        #expect(updateOptions.draftModelID == "z-lab/Qwen3.5-27B-DFlash")
        #expect(updateOptions.numDraftTokens == 8)
        #expect(removeOptions.serverSessionID == "server-session-qwen")
        #expect(selectOptions.serverSessionID == "server-session-qwen")
    }

    @Test("parses server start resume wake and stop commands")
    func parsesServerLifecycleCommands() throws {
        let startCommand = try MelixCLIParser.parse([
            "server",
            "start",
            "--server-session-id", "server-session-2",
            "--json",
        ])
        let titledStartCommand = try MelixCLIParser.parse([
            "server",
            "start",
            "Gemma 31B",
            "--models", "mlx-community/gemma-4-31b-it-4bit,melix-secondary",
            "--default-model", "melix-secondary",
            "--host", "127.0.0.1",
            "--port", "12434",
            "--rate-limit-per-minute", "60",
            "--timeout-seconds", "240",
            "--model-idle-timeout-seconds", "300",
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
        guard case .serverStart(let titledStartOptions) = titledStartCommand else {
            Issue.record("Expected titled serverStart command")
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
        #expect(titledStartOptions.serverSessionID == "server-session-1")
        #expect(titledStartOptions.serverTitle == "Gemma 31B")
        #expect(titledStartOptions.defaultModelID == "melix-secondary")
        #expect(titledStartOptions.servedModelIDs == [
            "mlx-community/gemma-4-31b-it-4bit",
            "melix-secondary",
        ])
        #expect(titledStartOptions.host == "127.0.0.1")
        #expect(titledStartOptions.port == 12434)
        #expect(titledStartOptions.rateLimitPerMinute == 60)
        #expect(titledStartOptions.timeoutSeconds == 240)
        #expect(titledStartOptions.modelIdleTimeoutSeconds == 300)
        #expect(titledStartOptions.json)
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
            "--training-mode", "dora",
            "--preset", "balanced_adapter",
            "--experiment-group", "nightly-qwen35",
            "--rank", "8",
            "--alpha", "16",
            "--dropout", "0.05",
            "--target-modules", "q_proj,k_proj,v_proj",
            "--num-layers", "12",
            "--batch-size", "2",
            "--epochs", "3",
            "--max-steps", "5",
            "--learning-rate", "0.0001",
            "--max-seq-length", "4096",
            "--response-only",
            "--gradient-checkpointing",
            "--preflight-fit-check",
            "--allow-memory-risk",
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
        #expect(options.trainingMode == "dora")
        #expect(options.parameters["preset_id"] == "balanced_adapter")
        #expect(options.parameters["experiment_group_id"] == "nightly-qwen35")
        #expect(options.parameters["rank"] == "8")
        #expect(options.parameters["alpha"] == "16")
        #expect(options.parameters["dropout"] == "0.05")
        #expect(options.parameters["target_modules"] == "q_proj,k_proj,v_proj")
        #expect(options.parameters["num_layers"] == "12")
        #expect(options.parameters["batch_size"] == "2")
        #expect(options.parameters["epochs"] == "3")
        #expect(options.parameters["max_steps"] == "5")
        #expect(options.parameters["learning_rate"] == "0.0001")
        #expect(options.parameters["max_seq_length"] == "4096")
        #expect(options.parameters["response_only"] == "true")
        #expect(options.parameters["gradient_checkpointing"] == "true")
        #expect(options.preflightFitCheck)
        #expect(options.allowMemoryRisk)
        #expect(options.json)
    }

    @Test("parses lora train with gradient accumulation and a resume adapter")
    func parsesLoraTrainWithGradientAccumulationAndResumeAdapter() throws {
        let command = try MelixCLIParser.parse([
            "lora", "train",
            "--model-id", "melix-dev-text",
            "--dataset-uri", "/tmp/data/alpaca.jsonl",
            "--adapter-name", "demo-adapter",
            "--gradient-accumulation", "4",
            "--resume-adapter", "/tmp/prior/adapters",
            "--json",
        ])

        guard case .loraTrain(let options) = command else {
            Issue.record("Expected loraTrain command")
            return
        }

        #expect(options.parameters["gradient_accumulation"] == "4")
        #expect(options.parameters["resume_source_path"] == "/tmp/prior/adapters")
        #expect(options.parameters["resume_manifest_path"] == nil)
    }

    @Test("parses lora train with a resume manifest path")
    func parsesLoraTrainWithResumeManifest() throws {
        let command = try MelixCLIParser.parse([
            "lora", "train",
            "--model-id", "melix-dev-text",
            "--dataset-uri", "/tmp/data/alpaca.jsonl",
            "--adapter-name", "demo-adapter",
            "--resume-from-manifest", "/tmp/prior/manifest.json",
        ])

        guard case .loraTrain(let options) = command else {
            Issue.record("Expected loraTrain command")
            return
        }

        #expect(options.parameters["resume_source_path"] == nil)
        #expect(options.parameters["resume_manifest_path"] == "/tmp/prior/manifest.json")
    }

    @Test("lora train rejects setting both resume flags")
    func loraTrainRejectsBothResumeFlags() throws {
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse([
                "lora", "train",
                "--model-id", "melix-dev-text",
                "--dataset-uri", "/tmp/data.jsonl",
                "--adapter-name", "demo",
                "--resume-adapter", "/tmp/a",
                "--resume-from-manifest", "/tmp/b.json",
            ])
        }
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
            "--sample-limit", "8",
            "--text-feature", "messages",
            "--prompt-feature", "prompt",
            "--completion-feature", "completion",
            "--chat-feature", "messages",
            "--training-mode", "qlora",
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
        #expect(options.parameters["sample_limit"] == "8")
        #expect(options.parameters["text_feature"] == "messages")
        #expect(options.parameters["prompt_feature"] == "prompt")
        #expect(options.parameters["completion_feature"] == "completion")
        #expect(options.parameters["chat_feature"] == "messages")
        #expect(options.parameters["mask_prompt"] == "true")
        #expect(options.parameters["derived_model_alias"] == "melix-dev-text-ultrachat")
        #expect(options.trainingMode == "qlora")
    }

    @Test("parses alignment train with preference and RL parameters")
    func parsesAlignmentTrainCommand() throws {
        #expect(MelixCLIParser.usageText.contains("melix alignment train"))
        #expect(MelixCLIParser.usageText.contains("--source-adapter-path is the upstream/base LoRA adapter"))

        let command = try MelixCLIParser.parse([
            "alignment",
            "train",
            "--model-id", "melix-dev-text",
            "--dataset-uri", "/tmp/data/preference.jsonl",
            "--adapter-name", "aligned-adapter",
            "--algorithm", "grpo",
            "--grpo-candidate-count", "4",
            "--candidate-generation-mode", " Runtime_Generate ",
            "--candidate-scoring-mode", " Reward_Model ",
            "--candidate-generation-max-tokens", "16",
            "--source-adapter-path", "/tmp/source/train_lora.adapter.json",
            "--reference-model-path", "/tmp/reference-model",
            "--reward-model-manifest-path", "/tmp/reward/manifest.json",
            "--sample-limit", "8",
            "--max-steps", "3",
            "--json",
        ])

        guard case .alignmentTrain(let options) = command else {
            Issue.record("Expected alignmentTrain command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.datasetSourceKind == "local_package")
        #expect(options.datasetURI == "/tmp/data/preference.jsonl")
        #expect(options.adapterName == "aligned-adapter")
        #expect(options.algorithm == "grpo")
        #expect(options.parameters["grpo_candidate_count"] == "4")
        #expect(options.parameters["candidate_generation_mode"] == "runtime_generate")
        #expect(options.parameters["candidate_scoring_mode"] == "reward_model")
        #expect(options.parameters["candidate_generation_max_tokens"] == "16")
        #expect(options.parameters["source_adapter_path"] == "/tmp/source/train_lora.adapter.json")
        #expect(options.parameters["reference_model_path"] == "/tmp/reference-model")
        #expect(options.parameters["reward_model_manifest_path"] == "/tmp/reward/manifest.json")
        #expect(options.parameters["sample_limit"] == "8")
        #expect(options.parameters["max_steps"] == "3")
        #expect(options.json)
    }

    @Test("alignment train rejects unsupported algorithms")
    func alignmentTrainRejectsUnsupportedAlgorithms() throws {
        try assertError(
            for: [
                "alignment", "train",
                "--model-id", "melix-dev-text",
                "--dataset-uri", "/tmp/data.jsonl",
                "--adapter-name", "aligned-adapter",
                "--algorithm", "ppo",
            ],
            equals: .usage("Invalid value for --algorithm. Expected one of: dpo, orpo, cpo, grpo, rlhf.")
        )
    }

    @Test("alignment train rejects unsupported candidate generation controls")
    func alignmentTrainRejectsUnsupportedCandidateGenerationControls() throws {
        try assertError(
            for: [
                "alignment", "train",
                "--model-id", "melix-dev-text",
                "--dataset-uri", "/tmp/data.jsonl",
                "--adapter-name", "aligned-adapter",
                "--algorithm", "grpo",
                "--candidate-generation-mode", "remote",
            ],
            equals: .usage("Invalid value for --candidate-generation-mode. Expected one of: scored_trace, runtime_generate.")
        )
        try assertError(
            for: [
                "alignment", "train",
                "--model-id", "melix-dev-text",
                "--dataset-uri", "/tmp/data.jsonl",
                "--adapter-name", "aligned-adapter",
                "--algorithm", "grpo",
                "--candidate-scoring-mode", "dataset",
            ],
            equals: .usage("Invalid value for --candidate-scoring-mode. Expected one of: dataset_score, seed_overlap_proxy, reward_model.")
        )
    }

    @Test("alignment train rejects LoRA checkpoint resume flags")
    func alignmentTrainRejectsLoraCheckpointResumeFlags() throws {
        try assertError(
            for: [
                "alignment", "train",
                "--model-id", "melix-dev-text",
                "--dataset-uri", "/tmp/data.jsonl",
                "--adapter-name", "aligned-adapter",
                "--algorithm", "grpo",
                "--resume-adapter", "/tmp/lora-checkpoint",
            ],
            equals: .usage("--resume-adapter and --resume-from-manifest are only for melix lora train checkpoint resumption. For melix alignment train, use --source-adapter-path for the upstream/base LoRA adapter to carry into GRPO/RLHF output.")
        )
    }

    @Test("parses lora dataset inspect with local source conversion and preview controls")
    func parsesLoraDatasetInspectCommand() throws {
        let command = try MelixCLIParser.parse([
            "lora",
            "dataset",
            "inspect",
            "--model-id", "melix-dev-text",
            "--dataset-uri", "/tmp/data/alpaca.jsonl",
            "--template", "alpaca",
            "--validation-ratio", "0.2",
            "--preview-count", "4",
            "--json",
        ])

        guard case .loraDatasetInspect(let options) = command else {
            Issue.record("Expected loraDatasetInspect command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.datasetSourceKind == "local_path")
        #expect(options.datasetURI == "/tmp/data/alpaca.jsonl")
        #expect(options.parameters["template"] == "alpaca")
        #expect(options.parameters["validation_ratio"] == "0.2")
        #expect(options.parameters["preview_count"] == "4")
        #expect(options.json)
    }

    @Test("parses lora dataset build with a Hugging Face source and explicit output directory")
    func parsesLoraDatasetBuildCommandForHFDataset() throws {
        let command = try MelixCLIParser.parse([
            "lora",
            "dataset",
            "build",
            "--model-id", "melix-dev-text",
            "--hf-dataset-path", "HuggingFaceH4/ultrachat_200k",
            "--hf-dataset-name", "default",
            "--hf-train-split", "train_sft",
            "--hf-valid-split", "test_sft",
            "--template", "chat_messages",
            "--dataset-id", "melix-ultrachat-built",
            "--output-dir", "/tmp/melix-built-dataset",
        ])

        guard case .loraDatasetBuild(let options) = command else {
            Issue.record("Expected loraDatasetBuild command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.datasetSourceKind == "hf_dataset")
        #expect(options.datasetURI.isEmpty)
        #expect(options.outputDir == "/tmp/melix-built-dataset")
        #expect(options.parameters["hf_dataset_path"] == "HuggingFaceH4/ultrachat_200k")
        #expect(options.parameters["hf_dataset_name"] == "default")
        #expect(options.parameters["hf_train_split"] == "train_sft")
        #expect(options.parameters["hf_valid_split"] == "test_sft")
        #expect(options.parameters["template"] == "chat_messages")
        #expect(options.parameters["dataset_id"] == "melix-ultrachat-built")
    }

    @Test("parses lora experiments list with optional model id")
    func parsesLoraExperimentsListCommand() throws {
        let command = try MelixCLIParser.parse([
            "lora", "experiments", "list",
            "--model-id", "melix-dev-text",
            "--json",
        ])

        guard case .loraExperimentsList(let options) = command else {
            Issue.record("Expected loraExperimentsList command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.json)
    }

    @Test("parses lora experiments show with explicit group id")
    func parsesLoraExperimentsShowCommand() throws {
        let command = try MelixCLIParser.parse([
            "lora", "experiments", "show",
            "--group-id", "nightly-qwen35",
            "--json",
        ])

        guard case .loraExperimentsShow(let options) = command else {
            Issue.record("Expected loraExperimentsShow command")
            return
        }

        #expect(options.groupID == "nightly-qwen35")
        #expect(options.json)
    }

    @Test("lora experiments show requires a group id")
    func loraExperimentsShowRequiresGroupID() throws {
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["lora", "experiments", "show"])
        }
    }

    @Test("parses lora resume with overrides")
    func parsesLoraResumeCommand() throws {
        let command = try MelixCLIParser.parse([
            "lora", "resume",
            "--group-id", "nightly-qwen35",
            "--model-id", "melix-dev-text",
            "--preset", "quality_adapter",
            "--adapter-name", "resumed",
            "--dataset-uri", "/tmp/new-dataset.jsonl",
            "--json",
        ])

        guard case .loraResume(let options) = command else {
            Issue.record("Expected loraResume command")
            return
        }

        #expect(options.groupID == "nightly-qwen35")
        #expect(options.modelID == "melix-dev-text")
        #expect(options.presetID == "quality_adapter")
        #expect(options.adapterName == "resumed")
        #expect(options.datasetURI == "/tmp/new-dataset.jsonl")
        #expect(options.json)
    }

    @Test("lora resume requires a group id")
    func loraResumeRequiresGroupID() throws {
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["lora", "resume"])
        }
    }

    @Test("parses lora publishes list with optional model id")
    func parsesLoraPublishesListCommand() throws {
        let command = try MelixCLIParser.parse([
            "lora", "publishes", "list",
            "--model-id", "melix-dev-text",
            "--json",
        ])
        guard case .loraPublishesList(let options) = command else {
            Issue.record("Expected loraPublishesList command")
            return
        }
        #expect(options.modelID == "melix-dev-text")
        #expect(options.json)
    }

    @Test("parses lora publishes show with explicit job id")
    func parsesLoraPublishesShowCommand() throws {
        let command = try MelixCLIParser.parse([
            "lora", "publishes", "show",
            "--job-id", "model-ops-0042",
            "--json",
        ])
        guard case .loraPublishesShow(let options) = command else {
            Issue.record("Expected loraPublishesShow command")
            return
        }
        #expect(options.jobID == "model-ops-0042")
        #expect(options.json)
    }

    @Test("lora publishes show requires a job id")
    func loraPublishesShowRequiresJobID() throws {
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse(["lora", "publishes", "show"])
        }
    }

    @Test("lora publish --manifest-path with explicit --export-kind carries the explicit value forward")
    func loraPublishExplicitExportKindCarriesForward() throws {
        let command = try MelixCLIParser.parse([
            "lora", "publish",
            "--model-id", "melix-dev-text",
            "--target-repo", "melix/adapters/demo",
            "--manifest-path", "/tmp/demo/manifest.json",
            "--export-kind", "adapter",
            "--publish-backend", "local_filesystem",
            "--local-publish-root", "/tmp/melix-local-publish",
        ])
        guard case .loraPublish(let options) = command else {
            Issue.record("Expected loraPublish command")
            return
        }
        #expect(options.exportKind == .adapterExport)
        #expect(options.artifactPath == "/tmp/demo/manifest.json")
        #expect(options.artifactManifestPath == "/tmp/demo/manifest.json")
        #expect(options.publishBackend == "local_filesystem")
        #expect(options.localPublishRoot == "/tmp/melix-local-publish")
    }

    @Test("lora publish --manifest-path without --export-kind defers classification to the runner")
    func loraPublishDeferredExportKind() throws {
        let command = try MelixCLIParser.parse([
            "lora", "publish",
            "--model-id", "melix-dev-text",
            "--target-repo", "melix/adapters/demo",
            "--manifest-path", "/tmp/demo/manifest.json",
        ])
        guard case .loraPublish(let options) = command else {
            Issue.record("Expected loraPublish command")
            return
        }
        #expect(options.exportKind == nil)
        #expect(options.artifactManifestPath == "/tmp/demo/manifest.json")
    }

    @Test("lora publish rejects unknown --export-kind values")
    func loraPublishRejectsUnknownExportKind() throws {
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse([
                "lora", "publish",
                "--model-id", "melix-dev-text",
                "--target-repo", "melix/adapters/demo",
                "--manifest-path", "/tmp/demo/manifest.json",
                "--export-kind", "mystery",
            ])
        }
    }

    @Test("lora publish rejects mismatched --export-kind and --adapter-path")
    func loraPublishRejectsMismatchedExportKindAdapter() throws {
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse([
                "lora", "publish",
                "--model-id", "melix-dev-text",
                "--target-repo", "melix/adapters/demo",
                "--adapter-path", "/tmp/demo.adapter.json",
                "--export-kind", "merged",
            ])
        }
    }

    @Test("lora publish rejects mismatched --export-kind and --merged-model-path")
    func loraPublishRejectsMismatchedExportKindMerged() throws {
        #expect(throws: MelixCLIError.self) {
            _ = try MelixCLIParser.parse([
                "lora", "publish",
                "--model-id", "melix-dev-text",
                "--target-repo", "melix/models/demo",
                "--merged-model-path", "/tmp/demo-merged",
                "--export-kind", "adapter",
            ])
        }
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
        #expect(options.preflightFitCheck == false)
        #expect(options.allowMemoryRisk == false)
        #expect(options.json)
    }

    @Test("parses bench run memory fit preflight flags")
    func parsesBenchRunMemoryFitPreflightFlags() throws {
        let command = try MelixCLIParser.parse([
            "bench",
            "run",
            "--repo-id", "mlx-community/Qwen3.6-35B-A3B-4bit",
            "--suite", "smoke",
            "--preflight-fit-check",
            "--allow-memory-risk",
            "--json",
        ])

        guard case .benchRun(let options) = command else {
            Issue.record("Expected benchRun command")
            return
        }

        #expect(options.hfRepoID == "mlx-community/Qwen3.6-35B-A3B-4bit")
        #expect(options.preflightFitCheck)
        #expect(options.allowMemoryRisk)
        #expect(options.json)
    }

    @Test("parses bench run with managed dataset reference")
    func parsesBenchRunWithManagedDatasetReference() throws {
        let command = try MelixCLIParser.parse([
            "bench",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "latency",
            "--dataset-ref", "Jax-dan/HundredCV-Chat@main",
            "--hf-dataset-name", "default",
            "--hf-dataset-split", "train",
            "--prompt-feature", "messages",
        ])

        guard case .benchRun(let options) = command else {
            Issue.record("Expected benchRun command")
            return
        }

        #expect(options.parameters["dataset_ref"] == "Jax-dan/HundredCV-Chat@main")
        #expect(options.parameters["hf_dataset_path"] == "Jax-dan/HundredCV-Chat")
        #expect(options.parameters["hf_dataset_revision"] == "main")
        #expect(options.parameters["hf_dataset_name"] == "default")
        #expect(options.parameters["hf_dataset_split"] == "train")
        #expect(options.parameters["prompt_feature"] == "messages")

        let defaultRevisionCommand = try MelixCLIParser.parse([
            "bench",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "latency",
            "--dataset-ref", "Jax-dan/HundredCV-Chat",
        ])
        #expect(defaultRevisionCommand == .benchRun(.init(
            modelID: "melix-dev-text",
            suites: ["latency"],
            parameters: [
                "dataset_ref": "Jax-dan/HundredCV-Chat",
                "hf_dataset_path": "Jax-dan/HundredCV-Chat",
                "hf_dataset_revision": "main",
            ]
        )))
    }

    @Test("rejects malformed managed dataset references")
    func rejectsMalformedManagedDatasetReferences() throws {
        try assertError(
            for: [
                "bench",
                "run",
                "--model-id", "melix-dev-text",
                "--suite", "latency",
                "--dataset-ref", "org@repo@main",
            ],
            equals: .usage("Invalid --dataset-ref: 'org@repo' is not a valid repo id; expected format is repo/name[@revision].")
        )
    }

    @Test("parses batch run dry-run foundation options")
    func parsesBatchRunDryRunFoundationOptions() throws {
        #expect(MelixCLIParser.usageText.contains("melix batch run --models PATH"))
        #expect(MelixCLIParser.usageText.contains("melix batch status"))
        #expect(MelixCLIParser.usageText.contains("melix batch resume"))

        let command = try MelixCLIParser.parse([
            "batch", "run",
            "--models", "/tmp/models.txt",
            "--config", "/tmp/melix-batch.yaml",
            "--run-id", "run-1",
            "--output-root", "/tmp/downloads",
            "--temp-root", "/tmp/runtime",
            "--start-index", "2",
            "--max-models", "3",
            "--judge-remote-server-id", "judge",
            "--judge-model", "gpt-test",
            "--bench-suite", "smoke",
            "--bench-context-length", "2048",
            "--bench-generation-length", "256",
            "--bench-batch-size", "2",
            "--bench-repeats", "4",
            "--bench-sample-size", "5",
            "--bench-batch-factor", "6",
            "--eval-suite", "event_extraction",
            "--eval-dataset-id", "events.v1",
            "--eval-scoring-mode", "event_extraction_weighted_f1",
            "--eval-sample-size", "7",
            "--eval-batch-factor", "8",
            "--continue-on-failure", "false",
            "--restart-stack-per-model", "false",
            "--preflight",
            "--dry-run",
            "--json",
        ])

        guard case .batchRun(let options) = command else {
            Issue.record("Expected batchRun command")
            return
        }

        #expect(options.modelListPath == "/tmp/models.txt")
        #expect(options.configPath == "/tmp/melix-batch.yaml")
        #expect(options.runID == "run-1")
        #expect(options.outputRoot == "/tmp/downloads")
        #expect(options.tempRoot == "/tmp/runtime")
        #expect(options.startIndex == 2)
        #expect(options.maxModels == 3)
        #expect(options.judgeRemoteServerID == "judge")
        #expect(options.judgeModelID == "gpt-test")
        #expect(options.benchContextLength == 2048)
        #expect(options.evalSampleSize == 7)
        #expect(options.continueOnFailure == false)
        #expect(options.restartStackPerModel == false)
        #expect(options.preflight)
        #expect(options.dryRun)
        #expect(options.json)
    }

    @Test("parses batch status and resume commands")
    func parsesBatchStatusAndResumeCommands() throws {
        let status = try MelixCLIParser.parse([
            "batch", "status",
            "--run-id", "run-1",
            "--output-root", "/tmp/out",
            "--temp-root", "/tmp/tmp",
            "--json",
        ])
        guard case .batchStatus(let statusOptions) = status else {
            Issue.record("Expected batchStatus command")
            return
        }
        #expect(statusOptions.runID == "run-1")
        #expect(statusOptions.outputRoot == "/tmp/out")
        #expect(statusOptions.tempRoot == "/tmp/tmp")
        #expect(statusOptions.json)

        let resume = try MelixCLIParser.parse([
            "batch", "resume",
            "--run-id", "run-1",
            "--output-root", "/tmp/out",
            "--temp-root", "/tmp/tmp",
            "--models", "/tmp/models.txt",
            "--config", "/tmp/batch.yaml",
            "--eval-only",
            "--missing-only", "false",
            "--continue-on-failure", "false",
            "--dry-run",
            "--json",
        ])
        guard case .batchResume(let resumeOptions) = resume else {
            Issue.record("Expected batchResume command")
            return
        }
        #expect(resumeOptions.runID == "run-1")
        #expect(resumeOptions.outputRoot == "/tmp/out")
        #expect(resumeOptions.tempRoot == "/tmp/tmp")
        #expect(resumeOptions.modelListPath == "/tmp/models.txt")
        #expect(resumeOptions.configPath == "/tmp/batch.yaml")
        #expect(resumeOptions.evalOnly)
        #expect(resumeOptions.missingOnly == false)
        #expect(resumeOptions.continueOnFailure == false)
        #expect(resumeOptions.dryRun)
        #expect(resumeOptions.json)
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
        let reportCommand = try MelixCLIParser.parse([
            "bench",
            "report",
            "--from", "/tmp/melix/bench/runs",
            "--format", "json",
        ])

        guard case .benchList(let listOptions) = listCommand else {
            Issue.record("Expected benchList command")
            return
        }
        guard case .benchExportCSV(let exportOptions) = exportCommand else {
            Issue.record("Expected benchExportCSV command")
            return
        }
        guard case .benchReport(let reportOptions) = reportCommand else {
            Issue.record("Expected benchReport command")
            return
        }

        #expect(listOptions.json)
        #expect(exportOptions.jobID == "bench-1")
        #expect(exportOptions.outputPath == "/tmp/melix/bench-1.csv")
        #expect(exportOptions.json)
        #expect(reportOptions.sourcePath == "/tmp/melix/bench/runs")
        #expect(reportOptions.format == "json")
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
            "--dataset-root", "/tmp/mmlu-split-01",
            "--sample-size", "8",
            "--batch-factor", "2",
            "--seed", "7",
            "--few-shot", "4",
            "--preflight-fit-check",
            "--allow-memory-risk",
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
        #expect(options.parameters["dataset_root"] == "/tmp/mmlu-split-01")
        #expect(options.parameters["batch_factor"] == "2")
        #expect(options.parameters["seed"] == "7")
        #expect(options.parameters["few_shot"] == "4")
        #expect(options.preflightFitCheck)
        #expect(options.allowMemoryRisk)
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

    @Test("parses eval run with custom Hugging Face dataset source mapping and profile controls")
    func parsesEvalRunWithCustomHFDatasetSource() throws {
        let command = try MelixCLIParser.parse([
            "eval",
            "run",
            "--repo-id", "unsloth/gemma-4-E4B-it-MLX-8bit",
            "--suite", "dolly",
            "--hf-dataset-path", "databricks/databricks-dolly-15k",
            "--hf-dataset-revision", "main",
            "--hf-dataset-split", "train",
            "--field-input-text-path", "instruction",
            "--field-target-path", "response",
            "--field-sample-id-path", "sample_id",
            "--profile-type", "final_result",
            "--result-kind", "text",
            "--extraction-mode", "heuristic_final",
            "--scoring-mode", "normalized_exact_match",
            "--threshold", "1.0",
            "--ignored-path", "metadata.trace_id",
        ])

        guard case .evalRun(let options) = command else {
            Issue.record("Expected evalRun command")
            return
        }

        #expect(options.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(options.source.kind == .huggingFaceDataset)
        #expect(options.source.datasetPath == "databricks/databricks-dolly-15k")
        #expect(options.source.datasetRevision == "main")
        #expect(options.source.split == "train")
        #expect(options.fieldMapping.inputTextPath == "instruction")
        #expect(options.fieldMapping.targetPath == "response")
        #expect(options.fieldMapping.sampleIDPath == "sample_id")
        #expect(options.profile.profileType == "final_result")
        #expect(options.profile.resultKind == "text")
        #expect(options.profile.extractionMode == "heuristic_final")
        #expect(options.profile.scoringMode == "normalized_exact_match")
        #expect(options.profile.threshold == 1.0)
        #expect(options.profile.ignoredPaths == ["metadata.trace_id"])
    }

    @Test("parses eval run schema and hints files as reproducibility metadata")
    func parsesEvalRunWithSchemaAndHintsFiles() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let schemaPath = root.appendingPathComponent("result.schema.json")
        let hintsPath = root.appendingPathComponent("math-hints.md")
        try #"{"type":"object","required":["answer"]}"#.write(to: schemaPath, atomically: true, encoding: .utf8)
        try "Prefer integer answers.\n".write(to: hintsPath, atomically: true, encoding: .utf8)

        let command = try MelixCLIParser.parse([
            "eval",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "math",
            "--schema", schemaPath.path,
            "--hints", hintsPath.path,
            "--result-kind", "json",
        ])

        guard case .evalRun(let options) = command else {
            Issue.record("Expected evalRun command")
            return
        }

        #expect(options.profile.resultKind == "json")
        #expect(options.profile.outputSchemaJSON == #"{"required":["answer"],"type":"object"}"#)
        #expect(options.parameters["schema_path"] == schemaPath.path)
        #expect(options.parameters["schema_sha256"] == melixTestSHA256Hex(Data(#"{"type":"object","required":["answer"]}"#.utf8)))
        #expect(options.parameters["schema_size_bytes"] == "39")
        #expect(options.parameters["hints_path"] == hintsPath.path)
        #expect(options.parameters["hints_sha256"] == melixTestSHA256Hex(Data("Prefer integer answers.\n".utf8)))
        #expect(options.parameters["hints_size_bytes"] == "24")
        #expect(options.parameters["hints_format"] == "markdown")
        #expect(options.parameters["evaluation_hints_text"] == "Prefer integer answers.")
    }

    @Test("parses eval run with ad hoc prompt text and file")
    func parsesEvalRunWithAdHocPromptInputs() throws {
        let promptTextCommand = try MelixCLIParser.parse([
            "eval",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "mmlu",
            "--eval-prompt", "Answer using the provided rubric.",
        ])
        let promptFileCommand = try MelixCLIParser.parse([
            "eval",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "gsm8k",
            "--eval-prompt-file", "/tmp/eval-prompt.txt",
        ])

        guard case .evalRun(let promptTextOptions) = promptTextCommand else {
            Issue.record("Expected evalRun command")
            return
        }
        guard case .evalRun(let promptFileOptions) = promptFileCommand else {
            Issue.record("Expected evalRun command")
            return
        }

        #expect(promptTextOptions.evalPrompt == "Answer using the provided rubric.")
        #expect(promptTextOptions.evalPromptFile.isEmpty)
        #expect(promptFileOptions.evalPrompt.isEmpty)
        #expect(promptFileOptions.evalPromptFile == "/tmp/eval-prompt.txt")
    }

    @Test("eval run ad hoc prompt parser rejects ambiguous prompt choices")
    func evalRunAdHocPromptParserRejectsAmbiguousPromptChoices() throws {
        try assertError(
            for: [
                "eval", "run",
                "--model-id", "melix-dev-text",
                "--suite", "mmlu",
                "--eval-prompt", "Prompt",
                "--eval-prompt-file", "/tmp/prompt.txt",
            ],
            equals: .usage("--eval-prompt and --eval-prompt-file are mutually exclusive.")
        )
        try assertError(
            for: [
                "eval", "run",
                "--model-id", "melix-dev-text",
                "--suite", "mmlu",
                "--eval-prompt", "Prompt",
                "--eval-prompt-id", "event-prod",
            ],
            equals: .usage("--eval-prompt and --eval-prompt-file cannot be combined with --eval-prompt-id.")
        )
        try assertError(
            for: [
                "eval", "run",
                "--model-id", "melix-dev-text",
                "--suite", "mmlu",
                "--eval-prompt-file", "/tmp/prompt.txt",
                "--eval-prompt-revision", "rev-1",
            ],
            equals: .usage("--eval-prompt-revision requires --eval-prompt-id.")
        )
        try assertError(
            for: [
                "eval", "run",
                "--model-id", "melix-dev-text",
                "--suite", "mmlu",
                "--eval-prompt-revision", "rev-1",
            ],
            equals: .usage("--eval-prompt-revision requires --eval-prompt-id.")
        )
        try assertError(
            for: [
                "eval", "run",
                "--model-id", "melix-dev-text",
                "--suite", "mmlu",
                "--eval-prompt", "   ",
            ],
            equals: .usage("--eval-prompt must contain non-empty text.")
        )
    }

    @Test("eval run schema file parser surfaces reproducibility input errors")
    func evalRunSchemaFileParserSurfacesReproducibilityInputErrors() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let invalidJSONPath = root.appendingPathComponent("invalid.schema.json")
        let arrayJSONPath = root.appendingPathComponent("array.schema.json")
        try "{".write(to: invalidJSONPath, atomically: true, encoding: .utf8)
        try #"["answer"]"#.write(to: arrayJSONPath, atomically: true, encoding: .utf8)

        try assertSchemaUsageError(
            schemaPath: root.appendingPathComponent("missing.schema.json").path,
            contains: "Failed to read --schema"
        )
        try assertSchemaUsageError(
            schemaPath: invalidJSONPath.path,
            contains: "--schema must contain valid JSON"
        )
        try assertSchemaUsageError(
            schemaPath: arrayJSONPath.path,
            contains: "--schema must contain a JSON object."
        )
    }

    @Test("parses eval run with managed dataset reference")
    func parsesEvalRunWithManagedDatasetReference() throws {
        let command = try MelixCLIParser.parse([
            "eval",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "dolly",
            "--dataset-ref", "IRUCAAI/extract_group_chat_dataset_with_summary@main",
            "--hf-dataset-split", "train",
            "--field-input-text-path", "dialogue",
            "--field-target-path", "summary",
        ])

        guard case .evalRun(let options) = command else {
            Issue.record("Expected evalRun command")
            return
        }

        #expect(options.source.kind == .huggingFaceDataset)
        #expect(options.source.datasetPath == "IRUCAAI/extract_group_chat_dataset_with_summary")
        #expect(options.source.datasetRevision == "main")
        #expect(options.source.split == "train")
        #expect(options.parameters["dataset_ref"] == "IRUCAAI/extract_group_chat_dataset_with_summary@main")
        #expect(options.parameters["hf_dataset_path"] == "IRUCAAI/extract_group_chat_dataset_with_summary")
        #expect(options.parameters["hf_dataset_revision"] == "main")
        #expect(options.fieldMapping.inputTextPath == "dialogue")
        #expect(options.fieldMapping.targetPath == "summary")
    }

    @Test("eval dataset revision option overrides managed dataset reference revision")
    func evalDatasetRevisionOptionOverridesManagedDatasetReferenceRevision() throws {
        let command = try MelixCLIParser.parse([
            "eval",
            "run",
            "--model-id", "melix-dev-text",
            "--suite", "dolly",
            "--dataset-ref", "IRUCAAI/extract_group_chat_dataset_with_summary@pinned",
            "--hf-dataset-revision", "main",
            "--field-input-text-path", "dialogue",
            "--field-target-path", "summary",
        ])

        guard case .evalRun(let options) = command else {
            Issue.record("Expected evalRun command")
            return
        }

        #expect(options.source.datasetPath == "IRUCAAI/extract_group_chat_dataset_with_summary")
        #expect(options.source.datasetRevision == "main")
        #expect(options.parameters["dataset_ref"] == "IRUCAAI/extract_group_chat_dataset_with_summary@pinned")
        #expect(options.parameters["hf_dataset_revision"] == "main")
    }

    @Test("parses eval compare with target model ids and comparison controls")
    func parsesEvalCompareCommand() throws {
        let command = try MelixCLIParser.parse([
            "eval",
            "compare",
            "--model-id", "melix-dev-text",
            "--target-model-id", "melix-dev-text-lora-a",
            "--target-model-id", "melix-dev-text-lora-b",
            "--suite", "mmlu",
            "--dataset-id", "mmlu.dev.v1",
            "--dataset-root", "/tmp/mmlu-split-01",
            "--sample-size", "8",
            "--batch-factor", "2",
            "--few-shot", "4",
            "--seed", "7",
            "--scoring-mode", "multiple_choice_accuracy",
            "--code-exec-policy", "sandboxed",
            "--json",
        ])

        guard case .evalCompare(let options) = command else {
            Issue.record("Expected evalCompare command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.hfRepoID.isEmpty)
        #expect(options.targetModelIDs == ["melix-dev-text-lora-a", "melix-dev-text-lora-b"])
        #expect(options.suites == ["mmlu"])
        #expect(options.datasetID == "mmlu.dev.v1")
        #expect(options.sampleSize == 8)
        #expect(options.parameters["dataset_root"] == "/tmp/mmlu-split-01")
        #expect(options.parameters["batch_factor"] == "2")
        #expect(options.parameters["few_shot"] == "4")
        #expect(options.parameters["seed"] == "7")
        #expect(options.parameters["scoring_mode"] == "multiple_choice_accuracy")
        #expect(options.parameters["code_exec_policy"] == "sandboxed")
        #expect(options.json)
    }

    @Test("parses eval compare with adapter-manifest targets (Module 2)")
    func parsesEvalCompareWithAdapterTargets() throws {
        // Module 2 admits repeatable --target-adapter alongside the
        // existing --target-model-id flag. A compare invocation with
        // adapter targets only (no registered-model targets) must parse
        // successfully.
        let command = try MelixCLIParser.parse([
            "eval",
            "compare",
            "--model-id", "melix-dev-text",
            "--target-adapter", "/tmp/melix-adapters/alpha.adapter.json",
            "--target-adapter", "/tmp/melix-adapters/beta.adapter.json",
            "--suite", "mmlu",
            "--dataset-id", "mmlu.dev.v1",
            "--sample-size", "4",
            "--json",
        ])

        guard case .evalCompare(let options) = command else {
            Issue.record("Expected evalCompare command")
            return
        }

        #expect(options.targetModelIDs.isEmpty)
        #expect(options.targetAdapterManifestPaths == [
            "/tmp/melix-adapters/alpha.adapter.json",
            "/tmp/melix-adapters/beta.adapter.json",
        ])
        #expect(options.suites == ["mmlu"])
    }

    @Test("parses eval compare mixing registered and adapter targets")
    func parsesEvalCompareMixedTargets() throws {
        // Module 2 lets a single compare target both registered models
        // (via --target-model-id) and adapter manifests (via
        // --target-adapter). The runner sends both sets as distinct
        // request parameters; the worker combines them per target.
        let command = try MelixCLIParser.parse([
            "eval",
            "compare",
            "--model-id", "melix-dev-text",
            "--target-model-id", "melix-dev-text-lora-registered",
            "--target-adapter", "/tmp/melix-adapters/fresh.adapter.json",
            "--suite", "mmlu",
            "--dataset-id", "mmlu.dev.v1",
            "--sample-size", "2",
            "--json",
        ])

        guard case .evalCompare(let options) = command else {
            Issue.record("Expected evalCompare command")
            return
        }

        #expect(options.targetModelIDs == ["melix-dev-text-lora-registered"])
        #expect(options.targetAdapterManifestPaths == ["/tmp/melix-adapters/fresh.adapter.json"])
    }

    @Test("parses eval compare with managed dataset reference")
    func parsesEvalCompareWithManagedDatasetReference() throws {
        let command = try MelixCLIParser.parse([
            "eval",
            "compare",
            "--model-id", "melix-dev-text",
            "--target-model-id", "melix-dev-text-lora",
            "--suite", "dolly",
            "--dataset-ref", "IRUCAAI/extract_group_chat_dataset_with_summary@main",
            "--hf-dataset-split", "train",
            "--field-input-text-path", "dialogue",
            "--field-target-path", "summary",
            "--json",
        ])

        guard case .evalCompare(let options) = command else {
            Issue.record("Expected evalCompare command")
            return
        }

        #expect(options.suites == ["dolly"])
        #expect(options.source.kind == .huggingFaceDataset)
        #expect(options.source.datasetPath == "IRUCAAI/extract_group_chat_dataset_with_summary")
        #expect(options.source.datasetRevision == "main")
        #expect(options.source.split == "train")
        #expect(options.fieldMapping.inputTextPath == "dialogue")
        #expect(options.fieldMapping.targetPath == "summary")
        #expect(options.parameters["dataset_ref"] == "IRUCAAI/extract_group_chat_dataset_with_summary@main")
        #expect(options.parameters["hf_dataset_path"] == "IRUCAAI/extract_group_chat_dataset_with_summary")
        #expect(options.parameters["hf_dataset_revision"] == "main")
    }

    @Test("eval compare rejects invocations missing both target types")
    func parsesEvalCompareRejectsMissingTargets() {
        // Neither --target-model-id nor --target-adapter — must surface a
        // missingRequired error with a message that names both flags so
        // the operator knows adapter targets are an option now.
        do {
            _ = try MelixCLIParser.parse([
                "eval",
                "compare",
                "--model-id", "melix-dev-text",
                "--suite", "mmlu",
                "--dataset-id", "mmlu.dev.v1",
                "--sample-size", "1",
                "--json",
            ])
            Issue.record("Expected missingRequired error")
        } catch let error as MelixCLIError {
            if case .missingRequired(let message) = error {
                #expect(message.contains("--target-model-id"))
                #expect(message.contains("--target-adapter"))
            } else {
                Issue.record("Expected missingRequired, got \(error)")
            }
        } catch {
            Issue.record("Expected MelixCLIError.missingRequired, got \(error)")
        }
    }

    @Test("parses eval compare with custom JSONL source mapping and profile controls")
    func parsesEvalCompareWithCustomJSONLSource() throws {
        let command = try MelixCLIParser.parse([
            "eval",
            "compare",
            "--model-id", "melix-dev-text",
            "--target-model-id", "melix-dev-text-lora",
            "--suite", "mmlu",
            "--source-jsonl", "/tmp/eval/mmlu.jsonl",
            "--field-input-text-path", "prompt",
            "--field-target-path", "expected",
            "--field-sample-id-path", "sample_id",
            "--result-kind", "text",
            "--extraction-mode", "heuristic_final",
            "--scoring-mode", "normalized_exact_match",
            "--threshold", "0.8",
            "--ignored-path", "metadata.trace_id",
            "--json",
        ])

        guard case .evalCompare(let options) = command else {
            Issue.record("Expected evalCompare command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.targetModelIDs == ["melix-dev-text-lora"])
        #expect(options.source.kind == .localJSONL)
        #expect(options.source.path == "/tmp/eval/mmlu.jsonl")
        #expect(options.fieldMapping.inputTextPath == "prompt")
        #expect(options.fieldMapping.targetPath == "expected")
        #expect(options.fieldMapping.sampleIDPath == "sample_id")
        #expect(options.profile.resultKind == "text")
        #expect(options.profile.extractionMode == "heuristic_final")
        #expect(options.profile.scoringMode == "normalized_exact_match")
        #expect(options.profile.threshold == 0.8)
        #expect(options.profile.ignoredPaths == ["metadata.trace_id"])
        #expect(options.json)
    }

    @Test("parses eval list and standard plus compare export commands")
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
        let compareSummaryCommand = try MelixCLIParser.parse([
            "eval",
            "compare",
            "export-summary-csv",
            "--job-id", "eval-compare-1",
            "--output", "/tmp/melix/eval-compare-1-summary.csv",
        ])
        let compareSamplesCommand = try MelixCLIParser.parse([
            "eval",
            "compare",
            "export-samples-jsonl",
            "--job-id", "eval-compare-1",
            "--output", "/tmp/melix/eval-compare-1-samples.jsonl",
            "--json",
        ])
        let reportCommand = try MelixCLIParser.parse([
            "eval",
            "report",
            "--from", "/tmp/melix/evaluation/runs",
            "--format", "markdown",
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
        guard case .evalCompareExportSummaryCSV(let compareSummaryOptions) = compareSummaryCommand else {
            Issue.record("Expected evalCompareExportSummaryCSV command")
            return
        }
        guard case .evalCompareExportSamplesJSONL(let compareSamplesOptions) = compareSamplesCommand else {
            Issue.record("Expected evalCompareExportSamplesJSONL command")
            return
        }
        guard case .evalReport(let reportOptions) = reportCommand else {
            Issue.record("Expected evalReport command")
            return
        }

        #expect(listOptions.json)
        #expect(summaryOptions.jobID == "eval-1")
        #expect(summaryOptions.outputPath == "/tmp/melix/eval-1-summary.csv")
        #expect(summaryOptions.json)
        #expect(samplesOptions.jobID == "eval-1")
        #expect(samplesOptions.outputPath == "/tmp/melix/eval-1-samples.jsonl")
        #expect(samplesOptions.json == false)
        #expect(compareSummaryOptions.jobID == "eval-compare-1")
        #expect(compareSummaryOptions.outputPath == "/tmp/melix/eval-compare-1-summary.csv")
        #expect(compareSummaryOptions.json == false)
        #expect(compareSamplesOptions.jobID == "eval-compare-1")
        #expect(compareSamplesOptions.outputPath == "/tmp/melix/eval-compare-1-samples.jsonl")
        #expect(compareSamplesOptions.json)
        #expect(reportOptions.sourcePath == "/tmp/melix/evaluation/runs")
        #expect(reportOptions.format == "markdown")
    }

    @Test("parses offline run record commands")
    func parsesOfflineRunRecordCommands() throws {
        let listCommand = try MelixCLIParser.parse([
            "runs",
            "list",
            "--from", "/tmp/melix/jobs",
            "--json",
        ])
        let showCommand = try MelixCLIParser.parse([
            "runs",
            "show",
            "bench-1",
            "--from", "/tmp/melix/jobs",
            "--json",
        ])
        let exportCommand = try MelixCLIParser.parse([
            "runs",
            "export",
            "bench-1",
            "--format", "md",
            "--from", "/tmp/melix/jobs",
            "--output", "/tmp/melix/bench-1.md",
        ])

        guard case .runsList(let listOptions) = listCommand else {
            Issue.record("Expected runsList command")
            return
        }
        guard case .runsShow(let showOptions) = showCommand else {
            Issue.record("Expected runsShow command")
            return
        }
        guard case .runsExport(let exportOptions) = exportCommand else {
            Issue.record("Expected runsExport command")
            return
        }

        #expect(listOptions.sourcePath == "/tmp/melix/jobs")
        #expect(listOptions.json)
        #expect(showOptions.runID == "bench-1")
        #expect(showOptions.sourcePath == "/tmp/melix/jobs")
        #expect(showOptions.json)
        #expect(exportOptions.runID == "bench-1")
        #expect(exportOptions.format == "md")
        #expect(exportOptions.sourcePath == "/tmp/melix/jobs")
        #expect(exportOptions.outputPath == "/tmp/melix/bench-1.md")
    }

    @Test("parses lora activate with explicit alias and adapter path")
    func parsesLoraActivateCommand() throws {
        let command = try MelixCLIParser.parse([
            "lora",
            "activate",
            "--model-id", "melix-dev-text",
            "--adapter-path", "/tmp/melix/adapter/train_lora.adapter.json",
            "--activation-mode", "adapter_backed_runtime",
            "--alias", "melix-dev-text-lora",
        ])

        guard case .loraActivate(let options) = command else {
            Issue.record("Expected loraActivate command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.adapterPath == "/tmp/melix/adapter/train_lora.adapter.json")
        #expect(options.derivedModelAlias == "melix-dev-text-lora")
        #expect(options.activationMode == "adapter_backed_runtime")
    }

    @Test("parses lora remove-derived with an explicit derived model id")
    func parsesLoraRemoveDerivedCommand() throws {
        let command = try MelixCLIParser.parse([
            "lora",
            "remove-derived",
            "--model-id", "melix-dev-text",
            "--derived-model-id", "melix-dev-text-lora",
            "--json",
        ])

        guard case .loraRemoveDerived(let options) = command else {
            Issue.record("Expected loraRemoveDerived command")
            return
        }

        #expect(options.modelID == "melix-dev-text")
        #expect(options.derivedModelID == "melix-dev-text-lora")
        #expect(options.manifestPath.isEmpty)
        #expect(options.json)
    }

    @Test("parses lora publish for adapter and merged exports")
    func parsesLoraPublishCommands() throws {
        let adapterCommand = try MelixCLIParser.parse([
            "lora",
            "publish",
            "--model-id", "melix-dev-text",
            "--target-repo", "melix/adapters/demo",
            "--adapter-path", "/tmp/melix/train_lora.adapter.json",
        ])
        let mergedCommand = try MelixCLIParser.parse([
            "lora",
            "publish",
            "--model-id", "melix-dev-text",
            "--target-repo", "melix/models/demo-merged",
            "--manifest-path", "/tmp/melix/activate_adapter/manifest.json",
            "--export-kind", "merged",
            "--json",
        ])

        guard case .loraPublish(let adapterOptions) = adapterCommand else {
            Issue.record("Expected adapter loraPublish command")
            return
        }
        guard case .loraPublish(let mergedOptions) = mergedCommand else {
            Issue.record("Expected merged loraPublish command")
            return
        }

        #expect(adapterOptions.modelID == "melix-dev-text")
        #expect(adapterOptions.targetRepo == "melix/adapters/demo")
        #expect(adapterOptions.exportKind == .adapterExport)
        #expect(adapterOptions.artifactPath == "/tmp/melix/train_lora.adapter.json")
        #expect(adapterOptions.artifactManifestPath == "/tmp/melix/train_lora.adapter.json")
        #expect(adapterOptions.json == false)

        #expect(mergedOptions.targetRepo == "melix/models/demo-merged")
        #expect(mergedOptions.exportKind == .mergedExport)
        #expect(mergedOptions.artifactPath == "/tmp/melix/activate_adapter/manifest.json")
        #expect(mergedOptions.artifactManifestPath == "/tmp/melix/activate_adapter/manifest.json")
        #expect(mergedOptions.json)
    }

    @Test("surfaces usage and missing required parser errors")
    func surfacesUsageAndMissingRequiredErrors() throws {
        try assertError(for: [], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["unknown"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["doctor", "oops"], equals: .usage(MelixCLIParser.usageText))
        try assertError(
            for: ["convert"],
            equals: .missingRequired("--model-id is required for melix convert.")
        )
        try assertError(
            for: ["quantize"],
            equals: .missingRequired("--model-id is required for melix quantize.")
        )
        try assertError(
            for: [
                "quantize",
                "--model-id", "melix-dev-text",
                "--quantization-mode", "mystery",
            ],
            equals: .usage("Invalid value for --quantization-mode. Expected one of: ptq, qat.")
        )
        try assertError(
            for: [
                "quantize",
                "--model-id", "melix-dev-text",
                "--source-artifact-kind", "checkpoint",
            ],
            equals: .usage("Invalid value for --source-artifact-kind. Expected one of: base_model, merged_adapter, adapter_export.")
        )
        try assertError(
            for: [
                "quantize",
                "--model-id", "melix-dev-text",
                "--quantization-backend", "script",
            ],
            equals: .usage("Invalid value for --quantization-backend. Expected one of: manifest_only, mlx_lm_convert.")
        )
        try assertError(
            for: [
                "quantize",
                "--model-id", "melix-dev-text",
                "--mlx-lm-q-mode", "log",
            ],
            equals: .usage("Invalid value for --mlx-lm-q-mode. Expected one of: affine, mxfp4, nvfp4, mxfp8.")
        )
        try assertError(
            for: [
                "quantize",
                "--model-id", "melix-dev-text",
                "--mlx-lm-q-bits", "four",
            ],
            equals: .usage("Invalid value for --mlx-lm-q-bits. Expected an integer.")
        )
        try assertError(
            for: [
                "quantize",
                "--model-id", "melix-dev-text",
                "--mlx-lm-q-group-size", "wide",
            ],
            equals: .usage("Invalid value for --mlx-lm-q-group-size. Expected an integer.")
        )
        try assertError(
            for: [
                "quantize",
                "--model-id", "melix-dev-text",
                "--local-inference-smoke-mode", "screenshot",
            ],
            equals: .usage("Invalid value for --local-inference-smoke-mode. Expected one of: structural, runtime_generate.")
        )
        try assertError(
            for: ["upload", "--model-id", "melix-dev-text"],
            equals: .missingRequired("--target-repo is required for melix upload.")
        )
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
            for: ["lora", "dataset", "inspect", "--dataset-uri", "/tmp/data.jsonl"],
            equals: .missingRequired("--model-id is required for melix lora dataset inspect.")
        )
        try assertError(
            for: ["lora", "dataset", "build", "--model-id", "melix-dev-text"],
            equals: .missingRequired("Either --dataset-uri or --hf-dataset-path is required for melix lora dataset build.")
        )
        try assertError(
            for: ["lora", "dataset", "oops", "--model-id", "melix-dev-text", "--dataset-uri", "/tmp/data.jsonl"],
            equals: .usage(MelixCLIParser.usageText)
        )
        try assertError(
            for: [
                "lora", "train",
                "--model-id", "melix-dev-text",
                "--dataset-uri", "/tmp/data.jsonl",
                "--adapter-name", "demo",
                "--training-mode", "mystery",
            ],
            equals: .usage("Invalid value for --training-mode. Expected one of: lora, qlora, dora.")
        )
        try assertError(
            for: [
                "lora", "train",
                "--model-id", "melix-dev-text",
                "--dataset-uri", "/tmp/data.jsonl",
                "--adapter-name", "demo",
                "--training-mode", "dpo",
            ],
            equals: .usage("Invalid value for --training-mode. For alignment training modes (dpo, orpo, cpo, grpo, rlhf), use `melix alignment train --algorithm <mode>`.")
        )
        try assertError(
            for: [
                "lora", "activate",
                "--adapter-path", "/tmp/melix/adapter/train_lora.adapter.json",
            ],
            equals: .missingRequired("--model-id is required for melix lora activate.")
        )
        try assertError(
            for: ["lora", "activate", "--model-id", "melix-dev-text"],
            equals: .missingRequired("--adapter-path is required for melix lora activate.")
        )
        try assertError(
            for: [
                "lora", "activate",
                "--model-id", "melix-dev-text",
                "--adapter-path", "/tmp/melix/adapter/train_lora.adapter.json",
                "--activation-mode", "mystery_mode",
            ],
            equals: .usage("Invalid value for --activation-mode. Expected one of: fused_derived_model, adapter_backed_runtime.")
        )
        try assertError(
            for: ["lora", "remove-derived", "--derived-model-id", "melix-dev-text-lora"],
            equals: .missingRequired("--model-id is required for melix lora remove-derived.")
        )
        try assertError(
            for: ["lora", "remove-derived", "--model-id", "melix-dev-text"],
            equals: .missingRequired("Either --derived-model-id or --manifest-path is required for melix lora remove-derived.")
        )
        try assertError(
            for: ["lora", "publish", "--target-repo", "melix/adapters/demo", "--adapter-path", "/tmp/melix/train_lora.adapter.json"],
            equals: .missingRequired("--model-id is required for melix lora publish.")
        )
        try assertError(
            for: ["lora", "publish", "--model-id", "melix-dev-text", "--adapter-path", "/tmp/melix/train_lora.adapter.json"],
            equals: .missingRequired("--target-repo is required for melix lora publish.")
        )
        try assertError(
            for: ["lora", "publish", "--model-id", "melix-dev-text", "--target-repo", "melix/adapters/demo"],
            equals: .missingRequired("Exactly one of --adapter-path, --merged-model-path, or --manifest-path is required for melix lora publish.")
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
            equals: .missingRequired("Exactly one of --model-id, --repo-id, or --remote-server-id is required for melix eval run.")
        )
        try assertError(
            for: ["eval", "run", "--model-id", "melix-dev-text", "--repo-id", "repo"],
            equals: .missingRequired("Exactly one of --model-id, --repo-id, or --remote-server-id is required for melix eval run.")
        )
        try assertError(
            for: [
                "eval", "run",
                "--remote-server-id", "judge-target",
                "--semantic-judge-model", "judge-model",
            ],
            equals: .missingRequired("--semantic-judge-remote-server-id is required when using --semantic-judge-model for melix eval run.")
        )
        try assertError(
            for: ["eval", "compare", "--model-id", "melix-dev-text"],
            equals: .missingRequired("At least one --target-model-id or --target-adapter is required for melix eval compare.")
        )
        try assertError(
            for: [
                "eval", "compare",
                "--model-id", "melix-dev-text",
                "--repo-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "--target-model-id", "melix-dev-text-lora-a",
            ],
            equals: .missingRequired("Exactly one of --model-id or --repo-id is required for melix eval compare.")
        )
        try assertError(
            for: ["eval", "compare", "export-summary-csv", "--output", "/tmp/out.csv"],
            equals: .missingRequired("--job-id is required for melix eval compare export-summary-csv.")
        )
        try assertError(
            for: ["eval", "compare", "export-samples-csv", "--job-id", "eval-compare-1"],
            equals: .missingRequired("--output is required for melix eval compare export-samples-csv.")
        )
        try assertError(for: ["eval"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["eval", "oops"], equals: .usage(MelixCLIParser.usageText))
        try assertError(
            for: [
                "eval", "run",
                "--model-id", "melix-dev-text",
                "--schema", "/tmp/result.schema.json",
                "--output-schema-json", #"{"type":"object"}"#,
            ],
            equals: .usage("--schema and --output-schema-json are mutually exclusive.")
        )
        try assertError(
            for: ["eval", "export-summary-csv", "--output", "/tmp/out.csv"],
            equals: .missingRequired("--job-id is required for melix eval export-summary-csv.")
        )
        try assertError(
            for: ["eval", "export-samples-csv", "--job-id", "eval-1"],
            equals: .missingRequired("--output is required for melix eval export-samples-csv.")
        )
        try assertError(
            for: ["bench", "report"],
            equals: .missingRequired("--from is required for melix bench report.")
        )
        try assertError(
            for: ["eval", "report"],
            equals: .missingRequired("--from is required for melix eval report.")
        )
        try assertError(
            for: ["runs", "show"],
            equals: .missingRequired("RUN_ID is required for melix runs show.")
        )
        try assertError(
            for: ["runs", "show", " "],
            equals: .missingRequired("RUN_ID is required for melix runs show.")
        )
        try assertError(
            for: ["runs", "export", "bench-1"],
            equals: .missingRequired("--format is required for melix runs export.")
        )
        try assertError(for: ["runs"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["runs", "oops"], equals: .usage(MelixCLIParser.usageText))
    }

    @Test("surfaces malformed option errors")
    func surfacesMalformedOptionErrors() throws {
        try assertError(for: ["dataset"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["dataset", "unknown"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["dataset", "hub"], equals: .usage(MelixCLIParser.usageText))
        try assertError(for: ["dataset", "hub", "unknown"], equals: .usage(MelixCLIParser.usageText))
        try assertError(
            for: ["dataset", "hub", "download"],
            equals: .missingRequired("--repo-id is required for melix dataset hub download.")
        )
        try assertError(
            for: ["dataset", "remove"],
            equals: .missingRequired("--repo-id is required for melix dataset remove.")
        )
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
        try assertError(
            for: [
                "eval",
                "run",
                "--model-id", "melix-dev-text",
                "--source-csv", "/tmp/eval.csv",
                "--dataset-ref", "org/dataset",
            ],
            equals: .usage("At most one of --source-csv, --source-jsonl, --hf-dataset-path, or --dataset-ref may be provided for melix eval run.")
        )
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

private func assertSchemaUsageError(schemaPath: String, contains expectedText: String) throws {
    do {
        _ = try MelixCLIParser.parse([
            "eval",
            "run",
            "--model-id", "melix-dev-text",
            "--schema", schemaPath,
        ])
        Issue.record("Expected parser to throw for schema path: \(schemaPath)")
    } catch let error as MelixCLIError {
        #expect(error.errorDescription?.contains(expectedText) == true)
    }
}

private func melixTestSHA256Hex(_ data: Data) -> String {
    SHA256.hash(data: data)
        .map { String(format: "%02x", $0) }
        .joined()
}
