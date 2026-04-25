import Foundation
import MelixControlPlaneCore

public enum MelixCLICommandCodec {
    public static func commandID(for command: MelixCLICommand) -> String {
        switch command {
        case .doctor:
            return "doctor"
        case .convert:
            return "convert"
        case .quantize:
            return "quantize"
        case .upload:
            return "upload"
        case .modelList:
            return "model.list"
        case .modelInspect:
            return "model.inspect"
        case .modelLoad:
            return "model.load"
        case .modelUnload:
            return "model.unload"
        case .modelDownload:
            return "model.download"
        case .modelImport:
            return "model.import"
        case .modelHubSearch:
            return "model.hub.search"
        case .modelHubShow:
            return "model.hub.show"
        case .modelHubDownload:
            return "model.hub.download"
        case .modelRootsList:
            return "model.roots.list"
        case .modelRootsAdd:
            return "model.roots.add"
        case .modelRootsRemove:
            return "model.roots.remove"
        case .modelRootsMove:
            return "model.roots.move"
        case .modelRootsRescan:
            return "model.roots.rescan"
        case .serverSnapshot:
            return "server.snapshot"
        case .serverSessionList:
            return "server.session.list"
        case .serverSessionCreate:
            return "server.session.create"
        case .serverSessionUpdate:
            return "server.session.update"
        case .serverSessionRemove:
            return "server.session.remove"
        case .serverSessionSelect:
            return "server.session.select"
        case .serverStart:
            return "server.start"
        case .serverPause:
            return "server.pause"
        case .serverResume:
            return "server.resume"
        case .serverWake:
            return "server.wake"
        case .serverStop:
            return "server.stop"
        case .serverSetIdlePolicy:
            return "server.set-idle-policy"
        case .chatRun:
            return "chat.run"
        case .loraList:
            return "lora.list"
        case .loraTrain:
            return "lora.train"
        case .loraDatasetInspect:
            return "lora.dataset.inspect"
        case .loraDatasetBuild:
            return "lora.dataset.build"
        case .loraActivate:
            return "lora.activate"
        case .loraRemoveDerived:
            return "lora.remove-derived"
        case .loraPublish:
            return "lora.publish"
        case .loraExperimentsList:
            return "lora.experiments.list"
        case .loraExperimentsShow:
            return "lora.experiments.show"
        case .loraResume:
            return "lora.resume"
        case .benchRun:
            return "bench.run"
        case .benchList:
            return "bench.list"
        case .benchExportCSV:
            return "bench.export-csv"
        case .benchMatrixRun:
            return "bench.matrix.run"
        case .benchMatrixList:
            return "bench.matrix.list"
        case .benchMatrixExportSummaryCSV:
            return "bench.matrix.export-summary-csv"
        case .benchMatrixExportRequestsCSV:
            return "bench.matrix.export-requests-csv"
        case .evalRun:
            return "eval.run"
        case .evalCompare:
            return "eval.compare"
        case .evalList:
            return "eval.list"
        case .evalCompareExportSummaryCSV:
            return "eval.compare.export-summary-csv"
        case .evalCompareExportSamplesCSV:
            return "eval.compare.export-samples-csv"
        case .evalCompareExportSamplesJSONL:
            return "eval.compare.export-samples-jsonl"
        case .evalExportSummaryCSV:
            return "eval.export-summary-csv"
        case .evalExportSamplesCSV:
            return "eval.export-samples-csv"
        case .evalExportSamplesJSONL:
            return "eval.export-samples-jsonl"
        case .pipelineRun:
            return "pipeline.run"
        }
    }

    public static func jsonEnabledCommand(for command: MelixCLICommand) throws -> MelixCLICommand {
        if case .pipelineRun = command {
            return command
        }
        var arguments = try arguments(for: command)
        if arguments.contains("--json") == false {
            arguments.append("--json")
        }
        return try MelixCLIParser.parse(arguments)
    }

    public static func arguments(for command: MelixCLICommand) throws -> [String] {
        var arguments: [String]
        let json: Bool
        switch command {
        case .doctor(let options):
            arguments = ["doctor"]
            json = options.json
        case .convert(let options):
            arguments = ["convert"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--output-dir", value: options.outputDir, into: &arguments)
            appendOption("--target-format", value: options.targetFormat, into: &arguments)
            json = options.json
        case .quantize(let options):
            arguments = ["quantize"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--output-dir", value: options.outputDir, into: &arguments)
            appendOption("--quant-profile-id", value: options.quantProfileID, into: &arguments)
            appendOption("--weight-quant", value: options.weightQuant, into: &arguments)
            appendOption("--kv-quant", value: options.kvQuant, into: &arguments)
            json = options.json
        case .upload(let options):
            arguments = ["upload"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--output-dir", value: options.outputDir, into: &arguments)
            appendOption("--target-repo", value: options.targetRepo, into: &arguments)
            appendOption("--artifact-path", value: options.artifactPath, into: &arguments)
            appendOption("--artifact-kind", value: options.artifactKind, into: &arguments)
            appendOption("--artifact-manifest-path", value: options.artifactManifestPath, into: &arguments)
            json = options.json
        case .modelImport(let options):
            arguments = ["model", "import"]
            appendOption("--path", value: options.path, into: &arguments)
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--model-kind", value: options.modelKind, into: &arguments)
            appendOption("--revision", value: options.revision, into: &arguments)
            json = options.json
        case .modelHubDownload(let options):
            arguments = ["model", "hub", "download"]
            appendOption("--repo-id", value: options.repoID, into: &arguments)
            appendOption("--revision", value: options.revision, into: &arguments)
            appendOption("--hf-token", value: options.hfToken, into: &arguments)
            json = options.json
        case .modelRootsRescan(let options):
            arguments = ["model", "roots", "rescan"]
            json = options.json
        case .modelRootsList(let options):
            arguments = ["model", "roots", "list"]
            json = options.json
        case .modelRootsAdd(let options):
            arguments = ["model", "roots", "add"]
            appendOption("--path", value: options.path, into: &arguments)
            json = options.json
        case .modelRootsRemove(let options):
            arguments = ["model", "roots", "remove"]
            appendOption("--path", value: options.path, into: &arguments)
            json = options.json
        case .modelRootsMove(let options):
            arguments = ["model", "roots", "move"]
            appendOption("--path", value: options.path, into: &arguments)
            appendPositiveInt("--index", value: options.index, into: &arguments)
            json = options.json
        case .serverSessionUpdate(let options):
            arguments = ["server", "session", "update"]
            appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            appendOption("--title", value: options.title, into: &arguments)
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--host", value: options.host, into: &arguments)
            appendPositiveInt("--port", value: options.port, into: &arguments)
            appendPositiveInt("--rate-limit-per-minute", value: options.rateLimitPerMinute, into: &arguments)
            appendPositiveInt("--timeout-seconds", value: options.timeoutSeconds, into: &arguments)
            appendOption("--acceleration-mode", value: options.accelerationMode, into: &arguments)
            appendOption("--draft-model-id", value: options.draftModelID, into: &arguments)
            appendPositiveInt("--num-draft-tokens", value: options.numDraftTokens, into: &arguments)
            json = options.json
        case .serverSessionCreate(let options):
            arguments = ["server", "session", "create"]
            appendOption("--title", value: options.title, into: &arguments)
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--host", value: options.host, into: &arguments)
            appendPositiveInt("--port", value: options.port, into: &arguments)
            appendPositiveInt("--rate-limit-per-minute", value: options.rateLimitPerMinute, into: &arguments)
            appendPositiveInt("--timeout-seconds", value: options.timeoutSeconds, into: &arguments)
            appendOption("--acceleration-mode", value: options.accelerationMode, into: &arguments)
            appendOption("--draft-model-id", value: options.draftModelID, into: &arguments)
            appendPositiveInt("--num-draft-tokens", value: options.numDraftTokens, into: &arguments)
            json = options.json
        case .serverSessionRemove(let options):
            arguments = ["server", "session", "remove"]
            appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            json = options.json
        case .serverSessionSelect(let options):
            arguments = ["server", "session", "select"]
            appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            json = options.json
        case .serverStart(let options):
            arguments = ["server", "start"]
            appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            json = options.json
        case .serverPause(let options):
            arguments = ["server", "pause"]
            appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            json = options.json
        case .serverResume(let options):
            arguments = ["server", "resume"]
            appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            json = options.json
        case .serverWake(let options):
            arguments = ["server", "wake"]
            appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            json = options.json
        case .serverStop(let options):
            arguments = ["server", "stop"]
            appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            json = options.json
        case .serverSetIdlePolicy(let options):
            arguments = ["server", "set-idle-policy"]
            appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            appendOption("--auto-sleep", value: options.autoSleepEnabled ? "true" : "false", into: &arguments)
            appendPositiveUInt32("--light-sleep-after", value: options.lightSleepAfterSeconds, into: &arguments)
            appendPositiveUInt32("--deep-sleep-after", value: options.deepSleepAfterSeconds, into: &arguments)
            json = options.json
        case .chatRun(let options):
            arguments = ["chat", "run"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--message", value: options.message, into: &arguments)
            appendOption("--system", value: options.systemPrompt, into: &arguments)
            appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            json = options.json
        case .loraTrain(let options):
            arguments = ["lora", "train"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--adapter-name", value: options.adapterName, into: &arguments)
            if options.datasetSourceKind == "huggingface" || options.datasetSourceKind == "hf_dataset" {
                appendOption("--hf-dataset-path", value: options.datasetURI, into: &arguments)
            } else {
                appendOption("--dataset-uri", value: options.datasetURI, into: &arguments)
            }
            appendOption("--target-repo", value: options.targetRepo, into: &arguments)
            appendOption("--training-mode", value: options.trainingMode, into: &arguments)
            appendTrainingParameters(options.parameters, into: &arguments)
            json = options.json
        case .loraActivate(let options):
            arguments = ["lora", "activate"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--adapter-path", value: options.adapterPath, into: &arguments)
            appendOption("--alias", value: options.derivedModelAlias, into: &arguments)
            appendOption("--activation-mode", value: options.activationMode, into: &arguments)
            json = options.json
        case .loraPublish(let options):
            arguments = ["lora", "publish"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--target-repo", value: options.targetRepo, into: &arguments)
            switch options.exportKind {
            case .adapterExport:
                appendOption("--adapter-path", value: options.artifactPath, into: &arguments)
            case .mergedExport:
                if options.artifactManifestPath.isEmpty == false {
                    appendOption("--manifest-path", value: options.artifactManifestPath, into: &arguments)
                } else {
                    appendOption("--merged-model-path", value: options.artifactPath, into: &arguments)
                }
            }
            json = options.json
        case .benchRun(let options):
            arguments = ["bench", "run"]
            appendTarget(modelID: options.modelID, hfRepoID: options.hfRepoID, into: &arguments)
            appendMultiOption("--suite", values: options.suites, into: &arguments)
            appendMultiUInt32("--context-length", values: options.contextLengths, into: &arguments)
            appendPositiveUInt32("--generation-length", value: options.generationLength, into: &arguments)
            appendMultiUInt32("--batch-size", values: options.batchSizes, into: &arguments)
            appendPositiveUInt32("--repeats", value: options.repeats, into: &arguments)
            appendOption("--cache-profile", value: options.cacheProfile, into: &arguments)
            appendOption("--reasoning-mode", value: options.reasoningMode, into: &arguments)
            appendOption("--structured-output-mode", value: options.structuredOutputMode, into: &arguments)
            appendOption("--sample-size", value: options.parameters["sample_size"], into: &arguments)
            appendOption("--batch-factor", value: options.parameters["batch_factor"], into: &arguments)
            json = options.json
        case .benchMatrixRun(let options):
            arguments = ["bench", "matrix", "run"]
            appendTarget(modelID: options.modelID, hfRepoID: options.hfRepoID, into: &arguments)
            appendOption("--task-kind", value: options.taskKind, into: &arguments)
            appendMultiOption("--suite", values: options.suites, into: &arguments)
            appendMultiUInt32("--context-length", values: options.contextLengths, into: &arguments)
            appendMultiUInt32("--generation-length", values: options.generationLengths, into: &arguments)
            appendMultiUInt32("--batch-size", values: options.batchSizes, into: &arguments)
            appendMultiOption("--cache-profile", values: options.cacheProfiles, into: &arguments)
            appendMultiOption("--reasoning-mode", values: options.reasoningModes, into: &arguments)
            appendMultiOption("--structured-output-mode", values: options.structuredOutputModes, into: &arguments)
            appendMultiUInt32("--concurrency", values: options.concurrencyLevels, into: &arguments)
            appendPositiveUInt32("--repeats", value: options.repeats, into: &arguments)
            appendPositiveUInt32("--requests", value: options.requests, into: &arguments)
            appendPositiveUInt32("--duration-seconds", value: options.durationSeconds, into: &arguments)
            if options.allowLargeMatrix {
                arguments.append("--allow-large-matrix")
            }
            json = options.json
        case .benchExportCSV(let options):
            arguments = ["bench", "export-csv"]
            appendExportOptions(options.jobID, options.outputPath, into: &arguments)
            json = options.json
        case .benchMatrixExportSummaryCSV(let options):
            arguments = ["bench", "matrix", "export-summary-csv"]
            appendExportOptions(options.jobID, options.outputPath, into: &arguments)
            json = options.json
        case .benchMatrixExportRequestsCSV(let options):
            arguments = ["bench", "matrix", "export-requests-csv"]
            appendExportOptions(options.jobID, options.outputPath, into: &arguments)
            json = options.json
        case .evalRun(let options):
            arguments = ["eval", "run"]
            appendTarget(modelID: options.modelID, hfRepoID: options.hfRepoID, into: &arguments)
            appendMultiOption("--suite", values: options.suites, into: &arguments)
            appendOption("--dataset-id", value: options.datasetID, into: &arguments)
            appendPositiveUInt32("--sample-size", value: options.sampleSize, into: &arguments)
            appendEvaluationSourceArguments(
                source: options.source,
                fieldMapping: options.fieldMapping,
                profile: options.profile,
                into: &arguments
            )
            appendEvalParameters(options.parameters, into: &arguments)
            json = options.json
        case .evalExportSummaryCSV(let options):
            arguments = ["eval", "export-summary-csv"]
            appendExportOptions(options.jobID, options.outputPath, into: &arguments)
            json = options.json
        case .evalExportSamplesCSV(let options):
            arguments = ["eval", "export-samples-csv"]
            appendExportOptions(options.jobID, options.outputPath, into: &arguments)
            json = options.json
        case .evalExportSamplesJSONL(let options):
            arguments = ["eval", "export-samples-jsonl"]
            appendExportOptions(options.jobID, options.outputPath, into: &arguments)
            json = options.json
        case .pipelineRun(let options):
            arguments = ["pipeline", "run"]
            appendOption("--file", value: options.filePath, into: &arguments)
            appendOption("--inputs", value: options.inputsPath, into: &arguments)
            appendOption("--receipt-dir", value: options.receiptDir, into: &arguments)
            appendOption("--trace-id", value: options.traceID, into: &arguments)
            if options.resume {
                arguments.append("--resume")
            }
            appendOption("--from-step", value: options.fromStepID, into: &arguments)
            if options.dryRun {
                arguments.append("--dry-run")
            }
            json = false
        default:
            throw MelixCLIError.runtime("Command codec does not support \(commandID(for: command)).")
        }
        if json {
            arguments.append("--json")
        }
        return arguments
    }

    private static func appendTarget(modelID: String, hfRepoID: String, into arguments: inout [String]) {
        if modelID.isEmpty == false {
            arguments.append(contentsOf: ["--model-id", modelID])
        } else if hfRepoID.isEmpty == false {
            arguments.append(contentsOf: ["--repo-id", hfRepoID])
        }
    }

    private static func appendExportOptions(_ jobID: String, _ outputPath: String, into arguments: inout [String]) {
        appendOption("--job-id", value: jobID, into: &arguments)
        appendOption("--output", value: outputPath, into: &arguments)
    }

    private static func appendOption(_ option: String, value: String?, into arguments: inout [String]) {
        guard let value, value.isEmpty == false else {
            return
        }
        arguments.append(contentsOf: [option, value])
    }

    private static func appendPositiveInt(_ option: String, value: Int, into arguments: inout [String]) {
        guard value > 0 else {
            return
        }
        arguments.append(contentsOf: [option, String(value)])
    }

    private static func appendPositiveUInt32(_ option: String, value: UInt32, into arguments: inout [String]) {
        guard value > 0 else {
            return
        }
        arguments.append(contentsOf: [option, String(value)])
    }

    private static func appendMultiOption(_ option: String, values: [String], into arguments: inout [String]) {
        for value in values where value.isEmpty == false {
            arguments.append(contentsOf: [option, value])
        }
    }

    private static func appendMultiUInt32(_ option: String, values: [UInt32], into arguments: inout [String]) {
        for value in values where value > 0 {
            arguments.append(contentsOf: [option, String(value)])
        }
    }

    private static func appendTrainingParameters(_ parameters: [String: String], into arguments: inout [String]) {
        let mapping: [(String, String)] = [
            ("preset", "--preset"),
            ("preset_id", "--preset"),
            ("experiment_group", "--experiment-group"),
            ("experiment_group_id", "--experiment-group"),
            ("rank", "--rank"),
            ("alpha", "--alpha"),
            ("dropout", "--dropout"),
            ("target_modules", "--target-modules"),
            ("num_layers", "--num-layers"),
            ("batch_size", "--batch-size"),
            ("epochs", "--epochs"),
            ("max_steps", "--max-steps"),
            ("learning_rate", "--learning-rate"),
            ("max_seq_length", "--max-seq-length"),
            ("sample_limit", "--sample-limit"),
            ("hf_dataset_name", "--hf-dataset-name"),
            ("hf_dataset_revision", "--hf-dataset-revision"),
            ("hf_train_split", "--hf-train-split"),
            ("hf_valid_split", "--hf-valid-split"),
            ("text_feature", "--text-feature"),
            ("prompt_feature", "--prompt-feature"),
            ("completion_feature", "--completion-feature"),
            ("chat_feature", "--chat-feature"),
            ("derived_model_alias", "--derived-model-alias"),
            ("gradient_accumulation", "--gradient-accumulation"),
            ("resume_source_path", "--resume-adapter"),
            ("resume_manifest_path", "--resume-from-manifest"),
        ]
        for (key, option) in mapping {
            appendOption(option, value: parameters[key], into: &arguments)
        }
        appendBooleanFlag("--response-only", value: parameters["response_only"], into: &arguments)
        appendBooleanFlag("--mask-prompt", value: parameters["mask_prompt"], into: &arguments)
        appendBooleanFlag("--gradient-checkpointing", value: parameters["gradient_checkpointing"], into: &arguments)
    }

    private static func appendEvalParameters(_ parameters: [String: String], into arguments: inout [String]) {
        let mapping: [(String, String)] = [
            ("batch_factor", "--batch-factor"),
            ("dataset_root", "--dataset-root"),
            ("seed", "--seed"),
            ("few_shot", "--few-shot"),
            ("scoring_mode", "--scoring-mode"),
            ("code_exec_policy", "--code-exec-policy"),
        ]
        for (key, option) in mapping {
            appendOption(option, value: parameters[key], into: &arguments)
        }
    }

    private static func appendEvaluationSourceArguments(
        source: ControlPlaneEvaluationRequest.Source,
        fieldMapping: ControlPlaneEvaluationRequest.FieldMapping,
        profile: ControlPlaneEvaluationRequest.Profile,
        into arguments: inout [String]
    ) {
        switch source.kind {
        case .builtinPackage:
            break
        case .localCSV:
            appendOption("--source-csv", value: source.path, into: &arguments)
        case .localJSONL:
            appendOption("--source-jsonl", value: source.path, into: &arguments)
        case .huggingFaceDataset:
            appendOption("--hf-dataset-path", value: source.datasetPath, into: &arguments)
            appendOption("--hf-dataset-name", value: source.datasetName, into: &arguments)
            appendOption("--hf-dataset-revision", value: source.datasetRevision, into: &arguments)
            appendOption("--hf-dataset-split", value: source.split, into: &arguments)
        }
        appendOption("--field-system-path", value: fieldMapping.systemPath, into: &arguments)
        appendOption("--field-input-text-path", value: fieldMapping.inputTextPath, into: &arguments)
        appendOption("--field-target-path", value: fieldMapping.targetPath, into: &arguments)
        appendOption("--field-sample-id-path", value: fieldMapping.sampleIDPath, into: &arguments)
        appendOption("--profile-type", value: profile.profileType, into: &arguments)
        appendOption("--result-kind", value: profile.resultKind, into: &arguments)
        appendOption("--extraction-mode", value: profile.extractionMode, into: &arguments)
        if profile.threshold != 0 {
            appendOption("--threshold", value: String(profile.threshold), into: &arguments)
        }
        appendOption("--output-schema-json", value: profile.outputSchemaJSON, into: &arguments)
        appendMultiOption("--ignored-path", values: profile.ignoredPaths, into: &arguments)
    }

    private static func appendBooleanFlag(_ option: String, value: String?, into arguments: inout [String]) {
        guard value == "true" else {
            return
        }
        arguments.append(option)
    }
}
