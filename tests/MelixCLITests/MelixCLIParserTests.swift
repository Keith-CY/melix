import Testing

@testable import MelixCLICore
import MelixControlPlaneCore

@Suite("Melix CLI Parser")
struct MelixCLIParserTests {
    @Test("documents eval dataset root in usage text")
    func documentsEvalDatasetRootInUsageText() {
        #expect(MelixCLIParser.usageText.contains("[--dataset-root PATH]"))
    }

    @Test("documents and parses public model ops commands")
    func documentsAndParsesPublicModelOpsCommands() throws {
        #expect(MelixCLIParser.usageText.contains("melix doctor [--json]"))
        #expect(MelixCLIParser.usageText.contains("melix convert --model-id MODEL_ID"))
        #expect(MelixCLIParser.usageText.contains("melix quantize --model-id MODEL_ID"))
        #expect(MelixCLIParser.usageText.contains("melix upload --model-id MODEL_ID"))

        let doctorCommand = try MelixCLIParser.parse([
            "doctor",
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
        #expect(convertOptions.modelID == "melix-dev-text")
        #expect(convertOptions.outputDir == "/tmp/melix-convert")
        #expect(convertOptions.targetFormat == "melix_model_bundle")
        #expect(convertOptions.json)
        #expect(quantizeOptions.modelID == "melix-dev-text")
        #expect(quantizeOptions.outputDir == "/tmp/melix-quantize")
        #expect(quantizeOptions.quantProfileID == "q4")
        #expect(quantizeOptions.weightQuant == "q4")
        #expect(quantizeOptions.kvQuant == "q8")
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
        #expect(MelixCLIParser.requestedOutputFormat(["doctor"]) == .legacy)
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
    }

    @Test("command codec exposes stable ids and supported argv mappings")
    func commandCodecExposesStableIDsAndSupportedArgvMappings() throws {
        let allCommands: [(MelixCLICommand, String)] = [
            (.doctor(.init()), "doctor"),
            (.convert(.init(modelID: "model", outputDir: "/tmp/out", targetFormat: "bundle", json: true)), "convert"),
            (.quantize(.init(modelID: "model", outputDir: "/tmp/out", quantProfileID: "q4", weightQuant: "int4", kvQuant: "int8", json: true)), "quantize"),
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
            (.modelRootsList(.init(json: true)), "model.roots.list"),
            (.modelRootsAdd(.init(path: "/models", json: true)), "model.roots.add"),
            (.modelRootsRemove(.init(path: "/models", json: true)), "model.roots.remove"),
            (.modelRootsMove(.init(path: "/models", index: 1, json: true)), "model.roots.move"),
            (.modelRootsRescan(.init(json: true)), "model.roots.rescan"),
            (.serverSnapshot(.init(json: true)), "server.snapshot"),
            (.serverSessionList(.init(json: true)), "server.session.list"),
            (.serverSessionCreate(.init(title: "Server", modelID: "model", host: "127.0.0.1", port: 8080, rateLimitPerMinute: 120, timeoutSeconds: 60, json: true)), "server.session.create"),
            (.serverSessionUpdate(.init(serverSessionID: "server-session-1", title: "Server", modelID: "model", host: "127.0.0.1", port: 8081, rateLimitPerMinute: 60, timeoutSeconds: 30, json: true)), "server.session.update"),
            (.serverSessionRemove(.init(serverSessionID: "server-session-1", json: true)), "server.session.remove"),
            (.serverSessionSelect(.init(serverSessionID: "server-session-1", json: true)), "server.session.select"),
            (.serverStart(.init(serverSessionID: "server-session-1", json: true)), "server.start"),
            (.serverPause(.init(serverSessionID: "server-session-1", json: true)), "server.pause"),
            (.serverResume(.init(serverSessionID: "server-session-1", json: true)), "server.resume"),
            (.serverWake(.init(serverSessionID: "server-session-1", json: true)), "server.wake"),
            (.serverStop(.init(serverSessionID: "server-session-1", json: true)), "server.stop"),
            (.serverSetIdlePolicy(.init(serverSessionID: "server-session-1", autoSleepEnabled: true, lightSleepAfterSeconds: 30, deepSleepAfterSeconds: 60, json: true)), "server.set-idle-policy"),
            (.chatRun(.init(modelID: "model", message: "hello", systemPrompt: "system", serverSessionID: "server-session-1", json: true)), "chat.run"),
            (.loraList(.init(modelID: "model", json: true)), "lora.list"),
            (.loraTrain(.init(modelID: "model", datasetSourceKind: "huggingface", datasetURI: "dataset/repo", adapterName: "adapter", targetRepo: "melix/adapter", trainingMode: "qlora", parameters: ["derived_model_alias": "derived", "response_only": "true"], json: true)), "lora.train"),
            (.loraDatasetInspect(.init(modelID: "model", datasetURI: "/tmp/data.jsonl", json: true)), "lora.dataset.inspect"),
            (.loraDatasetBuild(.init(modelID: "model", datasetURI: "/tmp/data.jsonl", outputDir: "/tmp/out", json: true)), "lora.dataset.build"),
            (.loraActivate(.init(modelID: "model", adapterPath: "/tmp/adapter.json", derivedModelAlias: "derived", activationMode: "adapter_backed_runtime", json: true)), "lora.activate"),
            (.loraRemoveDerived(.init(modelID: "model", derivedModelID: "derived", json: true)), "lora.remove-derived"),
            (.loraPublish(.init(modelID: "model", targetRepo: "melix/adapter", exportKind: .adapterExport, artifactPath: "/tmp/adapter", artifactManifestPath: "/tmp/adapter/manifest.json", json: true)), "lora.publish"),
            (.loraExperimentsList(.init(modelID: "model", json: true)), "lora.experiments.list"),
            (.loraExperimentsShow(.init(modelID: "model", groupID: "nightly-qwen35", json: true)), "lora.experiments.show"),
            (.loraResume(.init(modelID: "model", groupID: "nightly-qwen35", presetID: "balanced_adapter", adapterName: "resumed", datasetURI: "/tmp/data.jsonl", json: true)), "lora.resume"),
            (.benchRun(.init(modelID: "model", suites: ["smoke"], contextLengths: [1024], generationLength: 128, batchSizes: [1], repeats: 2, cacheProfile: "cold", reasoningMode: "disabled", structuredOutputMode: "disabled", parameters: ["sample_size": "4", "batch_factor": "1"], json: true)), "bench.run"),
            (.benchList(.init(json: true)), "bench.list"),
            (.benchExportCSV(.init(jobID: "bench-1", outputPath: "/tmp/bench.csv", json: true)), "bench.export-csv"),
            (.benchMatrixRun(.init(modelID: "model", taskKind: "text-generation", suites: ["smoke"], contextLengths: [1024], generationLengths: [128], batchSizes: [1], cacheProfiles: ["cold"], reasoningModes: ["disabled"], structuredOutputModes: ["disabled"], concurrencyLevels: [1], repeats: 2, requests: 4, allowLargeMatrix: true, json: true)), "bench.matrix.run"),
            (.benchMatrixList(.init(json: true)), "bench.matrix.list"),
            (.benchMatrixExportSummaryCSV(.init(jobID: "matrix-1", outputPath: "/tmp/matrix.csv", json: true)), "bench.matrix.export-summary-csv"),
            (.benchMatrixExportRequestsCSV(.init(jobID: "matrix-1", outputPath: "/tmp/matrix-requests.csv", json: true)), "bench.matrix.export-requests-csv"),
            (.evalRun(.init(modelID: "model", suites: ["mmlu"], datasetID: "mmlu.dev.v1", sampleSize: 4, source: .localCSV(path: "/tmp/eval.csv"), fieldMapping: .init(systemPath: "system", inputTextPath: "input", targetPath: "target", sampleIDPath: "id"), profile: .init(profileType: "final_result", resultKind: "text", extractionMode: "heuristic_final", threshold: 0.75, outputSchemaJSON: "{\"type\":\"string\"}", ignoredPaths: ["meta"]), parameters: ["batch_factor": "1"], json: true)), "eval.run"),
            (.evalCompare(.init(modelID: "base", targetModelIDs: ["target"], suites: ["mmlu"], datasetID: "mmlu.dev.v1", sampleSize: 4, json: true)), "eval.compare"),
            (.evalList(.init(json: true)), "eval.list"),
            (.evalCompareExportSummaryCSV(.init(jobID: "compare-1", outputPath: "/tmp/compare.csv", json: true)), "eval.compare.export-summary-csv"),
            (.evalCompareExportSamplesCSV(.init(jobID: "compare-1", outputPath: "/tmp/compare-samples.csv", json: true)), "eval.compare.export-samples-csv"),
            (.evalCompareExportSamplesJSONL(.init(jobID: "compare-1", outputPath: "/tmp/compare-samples.jsonl", json: true)), "eval.compare.export-samples-jsonl"),
            (.evalExportSummaryCSV(.init(jobID: "eval-1", outputPath: "/tmp/eval.csv", json: true)), "eval.export-summary-csv"),
            (.evalExportSamplesCSV(.init(jobID: "eval-1", outputPath: "/tmp/eval-samples.csv", json: true)), "eval.export-samples-csv"),
            (.evalExportSamplesJSONL(.init(jobID: "eval-1", outputPath: "/tmp/eval-samples.jsonl", json: true)), "eval.export-samples-jsonl"),
            (.pipelineRun(.init(filePath: "/tmp/pipeline.json", inputsPath: "/tmp/inputs.json", receiptDir: "/tmp/receipts", traceID: "trace", resume: true, fromStepID: "chat", dryRun: true)), "pipeline.run"),
        ]

        for (command, expectedID) in allCommands {
            #expect(MelixCLICommandCodec.commandID(for: command) == expectedID)
        }

        let supportedCommands: [MelixCLICommand] = [
            .doctor(.init(json: true)),
            .convert(.init(modelID: "model", outputDir: "/tmp/out", targetFormat: "bundle", json: true)),
            .quantize(.init(modelID: "model", outputDir: "/tmp/out", quantProfileID: "q4", weightQuant: "int4", kvQuant: "int8", json: true)),
            .upload(.init(modelID: "model", outputDir: "/tmp/out", targetRepo: "melix/model", artifactPath: "/tmp/model", artifactKind: "bundle", artifactManifestPath: "/tmp/model/manifest.json", json: true)),
            .modelImport(.init(path: "/tmp/model", modelID: "model", modelKind: "text", revision: "main", json: true)),
            .modelHubDownload(.init(repoID: "mlx/qwen", revision: "main", json: true)),
            .modelRootsList(.init(json: true)),
            .modelRootsAdd(.init(path: "/models", json: true)),
            .modelRootsRemove(.init(path: "/models", json: true)),
            .modelRootsMove(.init(path: "/models", index: 1, json: true)),
            .modelRootsRescan(.init(json: true)),
            .serverSessionCreate(.init(title: "Server", modelID: "model", host: "127.0.0.1", port: 8080, rateLimitPerMinute: 120, timeoutSeconds: 60, json: true)),
            .serverSessionUpdate(.init(serverSessionID: "server-session-1", title: "Server", modelID: "model", host: "127.0.0.1", port: 8081, rateLimitPerMinute: 60, timeoutSeconds: 30, json: true)),
            .serverSessionRemove(.init(serverSessionID: "server-session-1", json: true)),
            .serverSessionSelect(.init(serverSessionID: "server-session-1", json: true)),
            .serverStart(.init(serverSessionID: "server-session-1", json: true)),
            .serverPause(.init(serverSessionID: "server-session-1", json: true)),
            .serverResume(.init(serverSessionID: "server-session-1", json: true)),
            .serverWake(.init(serverSessionID: "server-session-1", json: true)),
            .serverStop(.init(serverSessionID: "server-session-1", json: true)),
            .serverSetIdlePolicy(.init(serverSessionID: "server-session-1", autoSleepEnabled: false, lightSleepAfterSeconds: 30, deepSleepAfterSeconds: 60, json: true)),
            .chatRun(.init(modelID: "model", message: "hello", systemPrompt: "system", serverSessionID: "server-session-1", json: true)),
            .loraTrain(.init(modelID: "model", datasetSourceKind: "huggingface", datasetURI: "dataset/repo", adapterName: "adapter", targetRepo: "melix/adapter", trainingMode: "qlora", parameters: ["derived_model_alias": "derived", "response_only": "true"], json: true)),
            .loraActivate(.init(modelID: "model", adapterPath: "/tmp/adapter.json", derivedModelAlias: "derived", activationMode: "adapter_backed_runtime", json: true)),
            .loraPublish(.init(modelID: "model", targetRepo: "melix/adapter", exportKind: .adapterExport, artifactPath: "/tmp/adapter/manifest.json", artifactManifestPath: "/tmp/adapter/manifest.json", json: true)),
            .benchRun(.init(modelID: "model", suites: ["smoke"], contextLengths: [1024], generationLength: 128, batchSizes: [1], repeats: 2, cacheProfile: "cold", reasoningMode: "disabled", structuredOutputMode: "disabled", parameters: ["sample_size": "4", "batch_factor": "1"], json: true)),
            .benchMatrixRun(.init(modelID: "model", taskKind: "text-generation", suites: ["smoke"], contextLengths: [1024], generationLengths: [128], batchSizes: [1], cacheProfiles: ["cold"], reasoningModes: ["disabled"], structuredOutputModes: ["disabled"], concurrencyLevels: [1], repeats: 2, requests: 4, allowLargeMatrix: true, json: true)),
            .benchExportCSV(.init(jobID: "bench-1", outputPath: "/tmp/bench.csv", json: true)),
            .benchMatrixExportSummaryCSV(.init(jobID: "matrix-1", outputPath: "/tmp/matrix.csv", json: true)),
            .benchMatrixExportRequestsCSV(.init(jobID: "matrix-1", outputPath: "/tmp/matrix-requests.csv", json: true)),
            .evalRun(.init(modelID: "model", suites: ["mmlu"], datasetID: "mmlu.dev.v1", sampleSize: 4, source: .huggingFaceDataset(datasetPath: "org/ds", datasetName: "name", datasetRevision: "rev", split: "test"), fieldMapping: .init(systemPath: "system", inputTextPath: "input", targetPath: "target", sampleIDPath: "id"), profile: .init(profileType: "final_result", resultKind: "text", extractionMode: "heuristic_final", threshold: 0.75, outputSchemaJSON: "{\"type\":\"string\"}", ignoredPaths: ["meta"]), parameters: ["batch_factor": "1"], json: true)),
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

        let unsupported: [MelixCLICommand] = [
            .modelList(.init()),
            .loraDatasetInspect(.init(modelID: "model", datasetURI: "/tmp/data.jsonl")),
            .evalCompare(.init(modelID: "base", targetModelIDs: ["target"])),
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
        #expect(downloadOptions.json)
        #expect(listOptions.json)
        #expect(addOptions.path == "/tmp/models-a")
        #expect(moveOptions.path == "/tmp/models-a")
        #expect(moveOptions.index == 1)
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

        #expect(throws: MelixCLIError.missingRequired("--model-id is required for melix chat run.")) {
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
            "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--host", "127.0.0.1",
            "--port", "12434",
            "--draft-model-id", "z-lab/Qwen3.5-27B-DFlash",
            "--num-draft-tokens", "4",
            "--json",
        ])
        let updateCommand = try MelixCLIParser.parse([
            "server",
            "session",
            "update",
            "--server-session-id", "server-session-qwen",
            "--model-id", "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            "--port", "12434",
            "--timeout-seconds", "90",
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
        #expect(createOptions.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(createOptions.host == "127.0.0.1")
        #expect(createOptions.port == 12434)
        #expect(createOptions.accelerationMode == "speculative_decode")
        #expect(createOptions.draftModelID == "z-lab/Qwen3.5-27B-DFlash")
        #expect(createOptions.numDraftTokens == 4)
        #expect(createOptions.json)
        #expect(updateOptions.serverSessionID == "server-session-qwen")
        #expect(updateOptions.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(updateOptions.port == 12434)
        #expect(updateOptions.timeoutSeconds == 90)
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
            "--dataset-root", "/tmp/mmlu-split-01",
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
        #expect(options.parameters["dataset_root"] == "/tmp/mmlu-split-01")
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
            equals: .usage("Invalid value for --training-mode. Expected one of: lora, qlora.")
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
            equals: .missingRequired("Exactly one of --model-id or --repo-id is required for melix eval run.")
        )
        try assertError(
            for: ["eval", "run", "--model-id", "melix-dev-text", "--repo-id", "repo"],
            equals: .missingRequired("Exactly one of --model-id or --repo-id is required for melix eval run.")
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
