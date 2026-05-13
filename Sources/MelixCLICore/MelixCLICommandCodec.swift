import Foundation
import MelixControlPlaneCore

public enum MelixCLICommandCodec {
    public static func commandID(for command: MelixCLICommand) -> String {
        switch command {
        case .settingsShow:
            return "settings.show"
        case .settingsSet:
            return "settings.set"
        case .settingsValidate:
            return "settings.validate"
        case .settingsReset:
            return "settings.reset"
        case .info:
            return "info"
        case .capabilities:
            return "capabilities"
        case .instructions:
            return "instructions"
        case .schema:
            return "schema"
        case .configMetadata:
            return "config.metadata"
        case .doctor:
            return "doctor"
        case .system:
            return "system"
        case .monitor:
            return "monitor"
        case .logs:
            return "logs"
        case .debugBundle:
            return "debug.bundle"
        case .estimateImport(let options):
            return "estimate.\(options.targetKind)"
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
        case .datasetList:
            return "dataset.list"
        case .datasetHubDownload:
            return "dataset.hub.download"
        case .datasetRemove:
            return "dataset.remove"
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
        case .remoteServerList:
            return "remote-server.list"
        case .remoteServerAdd:
            return "remote-server.add"
        case .remoteServerUpdate:
            return "remote-server.update"
        case .remoteServerRemove:
            return "remote-server.remove"
        case .remoteServerTest:
            return "remote-server.test"
        case .chatRun:
            return "chat.run"
        case .loraList:
            return "lora.list"
        case .loraTrain:
            return "lora.train"
        case .alignmentTrain:
            return "alignment.train"
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
        case .loraPublishesList:
            return "lora.publishes.list"
        case .loraPublishesShow:
            return "lora.publishes.show"
        case .loraResume:
            return "lora.resume"
        case .benchRun:
            return "bench.run"
        case .benchList:
            return "bench.list"
        case .benchExportCSV:
            return "bench.export-csv"
        case .benchReport:
            return "bench.report"
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
        case .evalPromptList:
            return "eval.prompt.list"
        case .evalPromptShow:
            return "eval.prompt.show"
        case .evalPromptCreate:
            return "eval.prompt.create"
        case .evalPromptUpdate:
            return "eval.prompt.update"
        case .evalPromptFreeze:
            return "eval.prompt.freeze"
        case .evalPromptArchive:
            return "eval.prompt.archive"
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
        case .evalReport:
            return "eval.report"
        case .batchRun:
            return "batch.run"
        case .runsList:
            return "runs.list"
        case .runsShow:
            return "runs.show"
        case .runsExport:
            return "runs.export"
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
        case .settingsShow(let options):
            arguments = ["settings", "show"]
            for key in options.overrides.keys.sorted() {
                appendOption("--override", value: "\(key)=\(options.overrides[key] ?? "")", into: &arguments)
            }
            json = options.json
        case .settingsSet(let options):
            arguments = ["settings", "set", options.key, options.value]
            json = options.json
        case .settingsValidate(let options):
            arguments = ["settings", "validate"]
            json = options.json
        case .settingsReset(let options):
            arguments = ["settings", "reset", options.key]
            json = options.json
        case .info(let options):
            arguments = ["info"]
            json = options.json
        case .capabilities(let options):
            arguments = ["capabilities"]
            appendOption("--model-query", value: options.modelQuery, into: &arguments)
            json = options.json
        case .instructions(let options):
            arguments = ["instructions"]
            json = options.json
        case .schema(let options):
            arguments = ["schema"]
            json = options.json
        case .configMetadata(let options):
            arguments = ["config", "metadata"]
            json = options.json
        case .doctor(let options):
            arguments = ["doctor"]
            json = options.json
        case .system(let options):
            arguments = ["system"]
            json = options.json
        case .monitor(let options):
            arguments = ["monitor"]
            appendOption("--from", value: options.sourcePath, into: &arguments)
            json = options.json
        case .logs(let options):
            arguments = ["logs", options.jobID]
            appendOption("--from", value: options.sourcePath, into: &arguments)
            if options.follow {
                arguments.append("--follow")
            }
            json = options.json
        case .debugBundle(let options):
            arguments = ["debug", "bundle", options.runID]
            appendOption("--from", value: options.sourcePath, into: &arguments)
            appendOption("--output", value: options.outputPath, into: &arguments)
            json = options.json
        case .estimateImport(let options):
            arguments = ["estimate", options.targetKind, options.repoID]
            appendOption("--context", value: options.targetInputs["context"], into: &arguments)
            appendOption("--context-length", value: options.targetInputs["context_length"], into: &arguments)
            appendOption("--dataset", value: options.targetInputs["dataset"], into: &arguments)
            appendOption("--lora", value: options.targetInputs["lora"], into: &arguments)
            appendOption("--batch-size", value: options.targetInputs["batch_size"], into: &arguments)
            appendOption("--sample-size", value: options.targetInputs["sample_size"], into: &arguments)
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
            appendOption("--quantization-mode", value: options.quantizationMode, into: &arguments)
            appendOption("--source-artifact-kind", value: options.sourceArtifactKind, into: &arguments)
            appendOption("--source-artifact-path", value: options.sourceArtifactPath, into: &arguments)
            appendOption("--quantization-backend", value: options.quantizationBackend, into: &arguments)
            appendOption("--mlx-lm-q-bits", value: options.mlxLMQBits, into: &arguments)
            appendOption("--mlx-lm-q-group-size", value: options.mlxLMQGroupSize, into: &arguments)
            appendOption("--mlx-lm-q-mode", value: options.mlxLMQMode, into: &arguments)
            appendOption("--calibration-dataset-uri", value: options.calibrationDatasetURI, into: &arguments)
            appendOption("--quality-delta", value: options.qualityDelta, into: &arguments)
            appendOption("--latency-delta", value: options.latencyDelta, into: &arguments)
            appendOption("--local-inference-smoke-mode", value: options.localInferenceSmokeMode, into: &arguments)
            appendOption("--local-inference-smoke-prompt", value: options.localInferenceSmokePrompt, into: &arguments)
            json = options.json
        case .upload(let options):
            arguments = ["upload"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--output-dir", value: options.outputDir, into: &arguments)
            appendOption("--target-repo", value: options.targetRepo, into: &arguments)
            appendOption("--artifact-path", value: options.artifactPath, into: &arguments)
            appendOption("--artifact-kind", value: options.artifactKind, into: &arguments)
            appendOption("--artifact-manifest-path", value: options.artifactManifestPath, into: &arguments)
            appendOption("--publish-backend", value: options.publishBackend, into: &arguments)
            appendOption("--local-publish-root", value: options.localPublishRoot, into: &arguments)
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
        case .datasetList(let options):
            arguments = ["dataset", "list"]
            json = options.json
        case .datasetHubDownload(let options):
            arguments = ["dataset", "hub", "download"]
            appendOption("--repo-id", value: options.repoID, into: &arguments)
            appendOption("--revision", value: options.revision, into: &arguments)
            appendOption("--hf-token", value: options.hfToken, into: &arguments)
            json = options.json
        case .datasetRemove(let options):
            arguments = ["dataset", "remove"]
            appendOption("--repo-id", value: options.repoID, into: &arguments)
            appendOption("--revision", value: options.revision, into: &arguments)
            appendOption("--snapshot-id", value: options.snapshotID, into: &arguments)
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
            if options.serverTitle.isEmpty == false {
                arguments.append(options.serverTitle)
            } else {
                appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            }
            appendOption("--model", value: options.modelID, into: &arguments)
            appendOption("--host", value: options.host, into: &arguments)
            appendPositiveInt("--port", value: options.port, into: &arguments)
            appendPositiveInt("--rate-limit-per-minute", value: options.rateLimitPerMinute, into: &arguments)
            appendPositiveInt("--timeout-seconds", value: options.timeoutSeconds, into: &arguments)
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
        case .remoteServerList(let options):
            arguments = ["remote-server", "list"]
            json = options.json
        case .remoteServerAdd(let options):
            arguments = ["remote-server", "add"]
            appendRemoteServerMutationOptions(options, into: &arguments)
            json = options.json
        case .remoteServerUpdate(let options):
            arguments = ["remote-server", "update"]
            appendRemoteServerMutationOptions(options, into: &arguments)
            json = options.json
        case .remoteServerRemove(let options):
            arguments = ["remote-server", "remove"]
            appendOption("--remote-server-id", value: options.remoteServerID, into: &arguments)
            json = options.json
        case .remoteServerTest(let options):
            arguments = ["remote-server", "test"]
            appendOption("--remote-server-id", value: options.remoteServerID, into: &arguments)
            appendOption("--model", value: options.remoteModelID, into: &arguments)
            json = options.json
        case .chatRun(let options):
            arguments = ["chat", "run"]
            if options.remoteServerID.isEmpty == false {
                appendOption("--remote-server-id", value: options.remoteServerID, into: &arguments)
                appendOption("--model", value: options.remoteModelID, into: &arguments)
            } else {
                appendOption("--model-id", value: options.modelID, into: &arguments)
            }
            appendOption("--message", value: options.message, into: &arguments)
            appendOption("--system", value: options.systemPrompt, into: &arguments)
            appendOption("--server-session-id", value: options.serverSessionID, into: &arguments)
            json = options.json
        case .loraTrain(let options):
            arguments = ["lora", "train"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--adapter-name", value: options.adapterName, into: &arguments)
            if options.datasetSourceKind == "huggingface" || options.datasetSourceKind == "hf_dataset" {
                let datasetPath = options.datasetURI.isEmpty ? options.parameters["hf_dataset_path"] : options.datasetURI
                appendOption("--hf-dataset-path", value: datasetPath, into: &arguments)
            } else {
                appendOption("--dataset-uri", value: options.datasetURI, into: &arguments)
            }
            appendOption("--target-repo", value: options.targetRepo, into: &arguments)
            appendOption("--training-mode", value: options.trainingMode, into: &arguments)
            appendTrainingParameters(options.parameters, into: &arguments)
            if options.preflightFitCheck {
                arguments.append("--preflight-fit-check")
            }
            if options.allowMemoryRisk {
                arguments.append("--allow-memory-risk")
            }
            json = options.json
        case .alignmentTrain(let options):
            arguments = ["alignment", "train"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--adapter-name", value: options.adapterName, into: &arguments)
            if options.datasetSourceKind == "huggingface" || options.datasetSourceKind == "hf_dataset" {
                let datasetPath = options.datasetURI.isEmpty ? options.parameters["hf_dataset_path"] : options.datasetURI
                appendOption("--hf-dataset-path", value: datasetPath, into: &arguments)
            } else {
                appendOption("--dataset-uri", value: options.datasetURI, into: &arguments)
            }
            appendOption("--algorithm", value: options.algorithm, into: &arguments)
            appendOption("--target-repo", value: options.targetRepo, into: &arguments)
            appendTrainingParameters(options.parameters, into: &arguments)
            appendAlignmentParameters(options.parameters, into: &arguments)
            json = options.json
        case .loraActivate(let options):
            arguments = ["lora", "activate"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--adapter-path", value: options.adapterPath, into: &arguments)
            appendOption("--alias", value: options.derivedModelAlias, into: &arguments)
            appendOption("--activation-mode", value: options.activationMode, into: &arguments)
            json = options.json
        case .loraPublish(let options):
            // Round-trip note: a `LoraPublishOptions` originally parsed from
            // `--manifest-path X --export-kind adapter` re-emits as
            // `--adapter-path X` (no `--export-kind`). The two argv variants
            // parse back to identical options because both forms produce
            // `exportKind=.adapterExport`, `artifactPath=X`,
            // `artifactManifestPath=X` — so this is a benign normalization,
            // not a round-trip break. Same applies to the merged path.
            arguments = ["lora", "publish"]
            appendOption("--model-id", value: options.modelID, into: &arguments)
            appendOption("--target-repo", value: options.targetRepo, into: &arguments)
            switch options.exportKind {
            case .some(.adapterExport):
                // `--adapter-path` alone is unambiguous — no `--export-kind` needed.
                appendOption("--adapter-path", value: options.artifactPath, into: &arguments)
            case .some(.mergedExport):
                if options.artifactManifestPath.isEmpty == false {
                    appendOption("--manifest-path", value: options.artifactManifestPath, into: &arguments)
                    // Round-trip an explicit merged selection so the parser does
                    // not have to read the manifest to re-derive it.
                    appendOption("--export-kind", value: "merged", into: &arguments)
                } else {
                    // `--merged-model-path` alone is unambiguous — no `--export-kind` needed.
                    appendOption("--merged-model-path", value: options.artifactPath, into: &arguments)
                }
            case .none:
                // The operator (or codec caller) left classification to the
                // runner; emit only `--manifest-path` and the runner infers.
                appendOption("--manifest-path", value: options.artifactManifestPath, into: &arguments)
            }
            appendOption("--publish-backend", value: options.publishBackend, into: &arguments)
            appendOption("--local-publish-root", value: options.localPublishRoot, into: &arguments)
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
            if options.preflightFitCheck {
                arguments.append("--preflight-fit-check")
            }
            if options.allowMemoryRisk {
                arguments.append("--allow-memory-risk")
            }
            appendOption("--dataset-ref", value: options.parameters["dataset_ref"], into: &arguments)
            appendOption("--hf-dataset-name", value: options.parameters["hf_dataset_name"], into: &arguments)
            appendOption("--hf-dataset-split", value: options.parameters["hf_dataset_split"], into: &arguments)
            appendOption("--prompt-feature", value: options.parameters["prompt_feature"], into: &arguments)
            appendOption("--text-feature", value: options.parameters["text_feature"], into: &arguments)
            appendOption("--image-feature", value: options.parameters["image_feature"], into: &arguments)
            appendOption("--source-image-feature", value: options.parameters["source_image_feature"], into: &arguments)
            appendOption("--mask-feature", value: options.parameters["mask_feature"], into: &arguments)
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
        case .benchReport(let options):
            arguments = ["bench", "report"]
            appendOption("--from", value: options.sourcePath, into: &arguments)
            appendOption("--format", value: options.format, into: &arguments)
            json = false
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
            appendEvalTarget(options, into: &arguments)
            appendMultiOption("--suite", values: options.suites, into: &arguments)
            appendOption("--dataset-id", value: options.datasetID, into: &arguments)
            appendPositiveUInt32("--sample-size", value: options.sampleSize, into: &arguments)
            appendEvaluationSourceArguments(
                source: options.source,
                fieldMapping: options.fieldMapping,
                profile: options.profile,
                schemaPath: options.parameters["schema_path"],
                into: &arguments
            )
            appendEvalParameters(options.parameters, into: &arguments)
            appendOption("--eval-prompt-id", value: options.evalPromptID, into: &arguments)
            appendOption("--eval-prompt-revision", value: options.evalPromptRevisionID, into: &arguments)
            appendOption("--eval-prompt", value: options.evalPrompt, into: &arguments)
            appendOption("--eval-prompt-file", value: options.evalPromptFile, into: &arguments)
            appendOption("--semantic-judge-remote-server-id", value: options.semanticJudgeRemoteServerID, into: &arguments)
            appendOption("--semantic-judge-model", value: options.semanticJudgeModelID, into: &arguments)
            appendPositiveUInt32("--remote-parallelism", value: options.remoteParallelism, into: &arguments)
            if options.preflightFitCheck {
                arguments.append("--preflight-fit-check")
            }
            if options.allowMemoryRisk {
                arguments.append("--allow-memory-risk")
            }
            json = options.json
        case .evalPromptList(let options):
            arguments = ["eval", "prompt", "list"]
            json = options.json
        case .evalPromptShow(let options):
            arguments = ["eval", "prompt", "show"]
            appendOption("--prompt-id", value: options.promptID, into: &arguments)
            appendOption("--revision-id", value: options.revisionID, into: &arguments)
            json = options.json
        case .evalPromptCreate(let options):
            arguments = ["eval", "prompt", "create"]
            appendOption("--prompt-id", value: options.promptID, into: &arguments)
            appendOption("--title", value: options.title, into: &arguments)
            appendOption("--system-prompt-file", value: options.systemPromptFile, into: &arguments)
            json = options.json
        case .evalPromptUpdate(let options):
            arguments = ["eval", "prompt", "update"]
            appendOption("--prompt-id", value: options.promptID, into: &arguments)
            appendOption("--system-prompt-file", value: options.systemPromptFile, into: &arguments)
            json = options.json
        case .evalPromptFreeze(let options):
            arguments = ["eval", "prompt", "freeze"]
            appendOption("--prompt-id", value: options.promptID, into: &arguments)
            appendOption("--revision-id", value: options.revisionID, into: &arguments)
            json = options.json
        case .evalPromptArchive(let options):
            arguments = ["eval", "prompt", "archive"]
            appendOption("--prompt-id", value: options.promptID, into: &arguments)
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
        case .evalReport(let options):
            arguments = ["eval", "report"]
            appendOption("--from", value: options.sourcePath, into: &arguments)
            appendOption("--format", value: options.format, into: &arguments)
            json = false
        case .batchRun(let options):
            arguments = ["batch", "run"]
            appendOption("--models", value: options.modelListPath, into: &arguments)
            appendOption("--config", value: options.configPath, into: &arguments)
            appendOption("--run-id", value: options.runID, into: &arguments)
            appendOption("--output-root", value: options.outputRoot, into: &arguments)
            appendOption("--temp-root", value: options.tempRoot, into: &arguments)
            appendInt(
                "--start-index",
                value: options.startIndex,
                defaultValue: 1,
                force: options.explicitOptions.contains("--start-index"),
                into: &arguments
            )
            appendInt(
                "--max-models",
                value: options.maxModels,
                defaultValue: 0,
                force: options.explicitOptions.contains("--max-models"),
                into: &arguments
            )
            appendOption("--judge-remote-server-id", value: options.judgeRemoteServerID, into: &arguments)
            appendOption("--judge-model", value: options.judgeModelID, into: &arguments)
            appendOption("--bench-suite", value: options.benchSuite, into: &arguments)
            appendUInt32("--bench-context-length", value: options.benchContextLength, defaultValue: 0, force: options.explicitOptions.contains("--bench-context-length"), into: &arguments)
            appendUInt32("--bench-generation-length", value: options.benchGenerationLength, defaultValue: 0, force: options.explicitOptions.contains("--bench-generation-length"), into: &arguments)
            appendUInt32("--bench-batch-size", value: options.benchBatchSize, defaultValue: 0, force: options.explicitOptions.contains("--bench-batch-size"), into: &arguments)
            appendUInt32("--bench-repeats", value: options.benchRepeats, defaultValue: 0, force: options.explicitOptions.contains("--bench-repeats"), into: &arguments)
            appendUInt32("--bench-sample-size", value: options.benchSampleSize, defaultValue: 0, force: options.explicitOptions.contains("--bench-sample-size"), into: &arguments)
            appendUInt32("--bench-batch-factor", value: options.benchBatchFactor, defaultValue: 0, force: options.explicitOptions.contains("--bench-batch-factor"), into: &arguments)
            appendOption("--eval-suite", value: options.evalSuite, into: &arguments)
            appendOption("--eval-dataset-id", value: options.evalDatasetID, into: &arguments)
            appendOption("--eval-scoring-mode", value: options.evalScoringMode, into: &arguments)
            appendUInt32("--eval-sample-size", value: options.evalSampleSize, defaultValue: 0, force: options.explicitOptions.contains("--eval-sample-size"), into: &arguments)
            appendUInt32("--eval-batch-factor", value: options.evalBatchFactor, defaultValue: 0, force: options.explicitOptions.contains("--eval-batch-factor"), into: &arguments)
            appendBool("--continue-on-failure", value: options.continueOnFailure, defaultValue: true, force: options.explicitOptions.contains("--continue-on-failure"), into: &arguments)
            appendBool("--restart-stack-per-model", value: options.restartStackPerModel, defaultValue: true, force: options.explicitOptions.contains("--restart-stack-per-model"), into: &arguments)
            if options.preflight {
                arguments.append("--preflight")
            }
            if options.dryRun {
                arguments.append("--dry-run")
            }
            json = options.json
        case .runsList(let options):
            arguments = ["runs", "list"]
            appendOption("--from", value: options.sourcePath, into: &arguments)
            json = options.json
        case .runsShow(let options):
            arguments = ["runs", "show", options.runID]
            appendOption("--from", value: options.sourcePath, into: &arguments)
            json = options.json
        case .runsExport(let options):
            arguments = ["runs", "export", options.runID]
            appendOption("--format", value: options.format, into: &arguments)
            appendOption("--from", value: options.sourcePath, into: &arguments)
            appendOption("--output", value: options.outputPath, into: &arguments)
            json = false
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

    private static func appendTarget(
        modelID: String,
        hfRepoID: String,
        remoteServerID: String = "",
        remoteModelID: String = "",
        into arguments: inout [String]
    ) {
        if modelID.isEmpty == false {
            arguments.append(contentsOf: ["--model-id", modelID])
        } else if hfRepoID.isEmpty == false {
            arguments.append(contentsOf: ["--repo-id", hfRepoID])
        } else if remoteServerID.isEmpty == false {
            arguments.append(contentsOf: ["--remote-server-id", remoteServerID])
            appendOption("--remote-model", value: remoteModelID, into: &arguments)
        }
    }

    private static func appendEvalTarget(_ options: EvalRunOptions, into arguments: inout [String]) {
        if options.modelID.isEmpty == false {
            arguments.append(contentsOf: ["--model-id", options.modelID])
        } else if options.hfRepoID.isEmpty == false {
            arguments.append(contentsOf: ["--repo-id", options.hfRepoID])
        } else {
            let targets = options.remoteTargets.isEmpty
                ? [EvalRemoteTargetOptions(remoteServerID: options.remoteServerID, remoteModelID: options.remoteModelID)]
                : options.remoteTargets
            for target in targets where target.remoteServerID.isEmpty == false {
                arguments.append(contentsOf: ["--remote-server-id", target.remoteServerID])
                appendOption("--remote-model", value: target.remoteModelID, into: &arguments)
            }
        }
    }

    private static func appendRemoteServerMutationOptions(
        _ options: RemoteServerMutationOptions,
        into arguments: inout [String]
    ) {
        appendOption("--remote-server-id", value: options.remoteServerID, into: &arguments)
        appendOption("--title", value: options.title, into: &arguments)
        appendOption("--provider", value: options.providerPreset?.rawValue, into: &arguments)
        appendOption("--base-url", value: options.baseURL, into: &arguments)
        appendOption("--model", value: options.defaultModelID, into: &arguments)
        appendOption("--api-key", value: options.apiKey, into: &arguments)
        appendPositiveUInt32("--timeout-seconds", value: options.timeoutSeconds, into: &arguments)
        appendPositiveUInt32("--rate-limit-per-minute", value: options.rateLimitPerMinute, into: &arguments)
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

    private static func appendInt(_ option: String, value: Int, defaultValue: Int, force: Bool, into arguments: inout [String]) {
        guard force || value != defaultValue else {
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

    private static func appendUInt32(_ option: String, value: UInt32, defaultValue: UInt32, force: Bool, into arguments: inout [String]) {
        guard force || value != defaultValue else {
            return
        }
        arguments.append(contentsOf: [option, String(value)])
    }

    private static func appendBool(_ option: String, value: Bool, defaultValue: Bool, force: Bool, into arguments: inout [String]) {
        guard force || value != defaultValue else {
            return
        }
        arguments.append(contentsOf: [option, value ? "true" : "false"])
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

    private static func appendAlignmentParameters(_ parameters: [String: String], into arguments: inout [String]) {
        let mapping: [(String, String)] = [
            ("grpo_candidate_count", "--grpo-candidate-count"),
            ("candidate_generation_mode", "--candidate-generation-mode"),
            ("candidate_scoring_mode", "--candidate-scoring-mode"),
            ("candidate_generation_max_tokens", "--candidate-generation-max-tokens"),
            ("source_adapter_path", "--source-adapter-path"),
            ("reference_model_path", "--reference-model-path"),
            ("reward_model_manifest_path", "--reward-model-manifest-path"),
            ("kl_penalty", "--kl-penalty"),
        ]
        for (key, option) in mapping {
            appendOption(option, value: parameters[key], into: &arguments)
        }
    }

    private static func appendEvalParameters(_ parameters: [String: String], into arguments: inout [String]) {
        let mapping: [(String, String)] = [
            ("batch_factor", "--batch-factor"),
            ("dataset_root", "--dataset-root"),
            ("seed", "--seed"),
            ("few_shot", "--few-shot"),
            ("scoring_mode", "--scoring-mode"),
            ("code_exec_policy", "--code-exec-policy"),
            ("remote_provider_extra_body_json", "--remote-extra-body-json"),
            ("hints_path", "--hints"),
        ]
        for (key, option) in mapping {
            appendOption(option, value: parameters[key], into: &arguments)
        }
    }

    private static func appendEvaluationSourceArguments(
        source: ControlPlaneEvaluationRequest.Source,
        fieldMapping: ControlPlaneEvaluationRequest.FieldMapping,
        profile: ControlPlaneEvaluationRequest.Profile,
        schemaPath: String? = nil,
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
        if let schemaPath, schemaPath.isEmpty == false {
            appendOption("--schema", value: schemaPath, into: &arguments)
        } else {
            appendOption("--output-schema-json", value: profile.outputSchemaJSON, into: &arguments)
        }
        appendMultiOption("--ignored-path", values: profile.ignoredPaths, into: &arguments)
    }

    private static func appendBooleanFlag(_ option: String, value: String?, into arguments: inout [String]) {
        guard value == "true" else {
            return
        }
        arguments.append(option)
    }
}
