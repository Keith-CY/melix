import Foundation
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Melix Subprocess CLI Workflow Runner", .serialized)
struct MelixSubprocessCLIWorkflowRunnerTests {
    @Test("eval compare export commands expose stable workflow command ids")
    func evalCompareExportCommandsExposeStableWorkflowCommandIDs() {
        #expect(
            MelixCLICommand.evalCompareExportSummaryCSV(
                .init(jobID: "eval-compare-1", outputPath: "/tmp/eval-compare-summary.csv")
            ).workflowCommandID == "eval.compare.export-summary-csv"
        )
        #expect(
            MelixCLICommand.evalCompareExportSamplesCSV(
                .init(jobID: "eval-compare-1", outputPath: "/tmp/eval-compare-samples.csv")
            ).workflowCommandID == "eval.compare.export-samples-csv"
        )
        #expect(
            MelixCLICommand.evalCompareExportSamplesJSONL(
                .init(jobID: "eval-compare-1", outputPath: "/tmp/eval-compare-samples.jsonl")
            ).workflowCommandID == "eval.compare.export-samples-jsonl"
        )
    }

    @Test("lora publish exposes a stable workflow command id")
    func loraPublishExposesAStableWorkflowCommandID() {
        #expect(
            MelixCLICommand.loraPublish(
                    .init(
                        modelID: "melix-dev-qwen-local",
                        targetRepo: "melix/adapters/melix-dev-adapter",
                        exportKind: .adapterExport,
                        artifactPath: "/tmp/melix-dev-adapter",
                        artifactManifestPath: "/tmp/melix-dev-adapter/manifest.json",
                        json: true
                    )
            ).workflowCommandID == "lora.publish"
        )
    }

    @Test("download hub model shells out through the melix cli and decodes a managed receipt")
    func downloadHubModelShellsOutThroughTheMelixCLIAndDecodesAManagedReceipt() async throws {
        let processExecutor = RecordingCLIProcessExecutor()
        await processExecutor.enqueueOutput(
            makeManagedModelReceiptJSON(
                modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                managedModelPath: "/tmp/melix-managed/qwen35",
                sourceKind: "hub_repo",
                sourceLocator: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
            )
        )
        let runner = MelixSubprocessCLIWorkflowRunner(
            cliExecutablePath: "/tmp/melix",
            environment: ["MELIX_HOME": "/tmp/melix-home"],
            processExecutor: processExecutor
        )

        let receipt = try await runner.downloadHubModel(
            repoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
            revision: "main"
        )
        let invocation = try #require(await processExecutor.recordedInvocations.first)

        #expect(invocation.executablePath == "/tmp/melix")
        #expect(
            invocation.arguments == [
                "model",
                "hub",
                "download",
                "--repo-id",
                "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                "--revision",
                "main",
                "--json",
            ]
        )
        #expect(invocation.environment["MELIX_HOME"] == "/tmp/melix-home")
        #expect(receipt.modelID == "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        #expect(receipt.managedModelPath == "/tmp/melix-managed/qwen35")
    }

    @Test("malformed subprocess json is surfaced as an invalid-json workflow error")
    func malformedSubprocessJSONIsSurfacedAsAnInvalidJSONWorkflowError() async throws {
        let processExecutor = RecordingCLIProcessExecutor()
        await processExecutor.enqueueOutput("{")
        let runner = MelixSubprocessCLIWorkflowRunner(
            cliExecutablePath: "/tmp/melix",
            processExecutor: processExecutor
        )

        do {
            _ = try await runner.downloadHubModel(
                repoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                revision: "main"
            )
            Issue.record("Expected invalid JSON failure.")
        } catch let error as MelixCLIWorkflowError {
            switch error {
            case .invalidJSON(let commandID, let surface, _):
                #expect(commandID == "model.hub.download")
                #expect(surface == .subprocess)
            default:
                Issue.record("Expected invalidJSON, got \(error)")
            }
        }
    }

    @Test("chat run shells out through the melix cli and decodes a chat receipt")
    func chatRunShellsOutThroughTheMelixCLIAndDecodesAChatReceipt() async throws {
        let processExecutor = RecordingCLIProcessExecutor()
        await processExecutor.enqueueOutput(
            """
            {
              "model_id": "melix-dev-text",
              "server_session_id": "server-session-1",
              "assistant_text": "BASE_OK",
              "finish_reason": "stop",
              "request_id": "chat-base"
            }
            """
        )
        let runner = MelixSubprocessCLIWorkflowRunner(
            cliExecutablePath: "/tmp/melix",
            environment: ["MELIX_HOME": "/tmp/melix-home"],
            processExecutor: processExecutor
        )

        let receipt = try await runner.decodeJSON(
            ChatRunReceipt.self,
            command: .chatRun(
                .init(
                    modelID: "melix-dev-text",
                    message: "Reply with BASE_OK",
                    systemPrompt: "You are Melix.",
                    serverSessionID: "server-session-1",
                    json: true
                )
            )
        )
        let invocation = try #require(await processExecutor.recordedInvocations.first)

        #expect(invocation.executablePath == "/tmp/melix")
        #expect(
            invocation.arguments == [
                "chat",
                "run",
                "--model-id",
                "melix-dev-text",
                "--message",
                "Reply with BASE_OK",
                "--system",
                "You are Melix.",
                "--server-session-id",
                "server-session-1",
                "--json",
            ]
        )
        #expect(invocation.environment["MELIX_HOME"] == "/tmp/melix-home")
        #expect(receipt.modelID == "melix-dev-text")
        #expect(receipt.assistantText == "BASE_OK")
    }

    @Test("chat run subprocess failures are surfaced as typed process failures")
    func chatRunSubprocessFailuresAreSurfacedAsTypedProcessFailures() async throws {
        let processExecutor = RecordingCLIProcessExecutor()
        await processExecutor.enqueueFailure(
            .nonZeroExit(
                executablePath: "/tmp/melix",
                arguments: [
                    "chat",
                    "run",
                    "--model-id",
                    "melix-dev-text",
                    "--message",
                    "Reply with BASE_OK",
                    "--json",
                ],
                exitCode: 3,
                stderr: "chat failed"
            )
        )
        let runner = MelixSubprocessCLIWorkflowRunner(
            cliExecutablePath: "/tmp/melix",
            processExecutor: processExecutor
        )

        do {
            _ = try await runner.run(
                .chatRun(
                    .init(
                        modelID: "melix-dev-text",
                        message: "Reply with BASE_OK",
                        json: true
                    )
                )
            )
            Issue.record("Expected subprocess exit failure.")
        } catch let error as MelixCLIWorkflowError {
            switch error {
            case .processFailed(let commandID, let surface, let exitCode, let stderr):
                #expect(commandID == "chat.run")
                #expect(surface == .subprocess)
                #expect(exitCode == 3)
                #expect(stderr == "chat failed")
            default:
                Issue.record("Expected processFailed, got \(error)")
            }
        }
    }

    @Test("lora train shells out with parser-compatible arguments")
    func loraTrainShellsOutWithParserCompatibleArguments() async throws {
        let processExecutor = RecordingCLIProcessExecutor()
        await processExecutor.enqueueOutput(
            """
            {
              "operation": "train_lora",
              "job_id": "model-ops-0001",
              "output_path": "/tmp/melix-train-lora/model-ops-0001/adapters.safetensors"
            }
            """
        )
        let runner = MelixSubprocessCLIWorkflowRunner(
            cliExecutablePath: "/tmp/melix",
            processExecutor: processExecutor
        )

        _ = try await runner.run(
            .loraTrain(
                .init(
                    modelID: "melix-dev-qwen-local",
                    datasetSourceKind: "local_package",
                    datasetURI: "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
                    adapterName: "phase8-acceptance",
                    trainingMode: "lora",
                    parameters: [
                        "derived_model_alias": "phase8-acceptance-derived",
                        "response_only": "true",
                        "gradient_checkpointing": "false",
                    ],
                    json: true
                )
            )
        )
        let invocation = try #require(await processExecutor.recordedInvocations.first)

        #expect(
            invocation.arguments == [
                "lora",
                "train",
                "--model-id",
                "melix-dev-qwen-local",
                "--adapter-name",
                "phase8-acceptance",
                "--dataset-uri",
                "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1",
                "--training-mode",
                "lora",
                "--derived-model-alias",
                "phase8-acceptance-derived",
                "--response-only",
                "--json",
            ]
        )
    }

    @Test("lora activate shells out with alias-compatible arguments")
    func loraActivateShellsOutWithAliasCompatibleArguments() async throws {
        let processExecutor = RecordingCLIProcessExecutor()
        await processExecutor.enqueueOutput(
            """
            {
              "operation": "activate_adapter",
              "job_id": "model-ops-0002",
              "derived_model_id": "melix-dev-qwen-local-lora",
              "derived_model_path": "/tmp/melix-activate/model-ops-0002/derived"
            }
            """
        )
        let runner = MelixSubprocessCLIWorkflowRunner(
            cliExecutablePath: "/tmp/melix",
            processExecutor: processExecutor
        )

        _ = try await runner.run(
            .loraActivate(
                .init(
                    modelID: "melix-dev-qwen-local",
                    adapterPath: "/tmp/melix-train-lora/model-ops-0001/train_lora.adapter.json",
                    derivedModelAlias: "phase8-acceptance-derived",
                    activationMode: "fused_derived_model",
                    json: true
                )
            )
        )
        let invocation = try #require(await processExecutor.recordedInvocations.first)

        #expect(
            invocation.arguments == [
                "lora",
                "activate",
                "--model-id",
                "melix-dev-qwen-local",
                "--adapter-path",
                "/tmp/melix-train-lora/model-ops-0001/train_lora.adapter.json",
                "--alias",
                "phase8-acceptance-derived",
                "--activation-mode",
                "fused_derived_model",
                "--json",
            ]
        )
    }

    @Test("unsupported lora dataset subprocess commands preserve their public command ids")
    func unsupportedLoraDatasetCommandsPreservePublicCommandIDs() async throws {
        let processExecutor = RecordingCLIProcessExecutor()
        let runner = MelixSubprocessCLIWorkflowRunner(
            cliExecutablePath: "/tmp/melix",
            processExecutor: processExecutor
        )

        do {
            _ = try await runner.run(
                .loraDatasetInspect(
                    .init(
                        modelID: "melix-dev-qwen-local",
                        datasetURI: "/tmp/data/alpaca.jsonl",
                        parameters: ["template": "alpaca"],
                        json: true
                    )
                )
            )
            Issue.record("Expected loraDatasetInspect to remain unsupported for the subprocess runner.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error == .unsupportedCommand(commandID: "lora.dataset.inspect", surface: .subprocess))
        }

        do {
            _ = try await runner.run(
                .loraDatasetBuild(
                    .init(
                        modelID: "melix-dev-qwen-local",
                        datasetSourceKind: "hf_dataset",
                        datasetURI: "HuggingFaceH4/ultrachat_200k",
                        outputDir: "/tmp/melix-built-dataset",
                        parameters: ["hf_train_split": "train_sft"],
                        json: true
                    )
                )
            )
            Issue.record("Expected loraDatasetBuild to remain unsupported for the subprocess runner.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error == .unsupportedCommand(commandID: "lora.dataset.build", surface: .subprocess))
        }

        #expect(await processExecutor.recordedInvocations.isEmpty)
    }

    @Test("non-zero subprocess exits are surfaced as typed process failures")
    func nonZeroSubprocessExitsAreSurfacedAsTypedProcessFailures() async throws {
        let processExecutor = RecordingCLIProcessExecutor()
        await processExecutor.enqueueFailure(
            .nonZeroExit(
                executablePath: "/tmp/melix",
                arguments: [
                    "bench",
                    "run",
                    "--model-id",
                    "melix-dev-text",
                    "--suite",
                    "smoke",
                    "--json",
                ],
                exitCode: 2,
                stderr: "benchmark failed"
            )
        )
        let runner = MelixSubprocessCLIWorkflowRunner(
            cliExecutablePath: "/tmp/melix",
            processExecutor: processExecutor
        )

        do {
            _ = try await runner.run(
                .benchRun(
                    .init(
                        modelID: "melix-dev-text",
                        suites: ["smoke"],
                        json: true
                    )
                )
            )
            Issue.record("Expected subprocess exit failure.")
        } catch let error as MelixCLIWorkflowError {
            switch error {
            case .processFailed(let commandID, let surface, let exitCode, let stderr):
                #expect(commandID == "bench.run")
                #expect(surface == .subprocess)
                #expect(exitCode == 2)
                #expect(stderr == "benchmark failed")
            default:
                Issue.record("Expected processFailed, got \(error)")
            }
        }
    }
}
