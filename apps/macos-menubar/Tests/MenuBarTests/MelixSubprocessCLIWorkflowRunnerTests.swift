import Foundation
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Melix Subprocess CLI Workflow Runner", .serialized)
struct MelixSubprocessCLIWorkflowRunnerTests {
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
