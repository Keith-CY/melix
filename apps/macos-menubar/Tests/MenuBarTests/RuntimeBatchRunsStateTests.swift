import Foundation
import Testing

@testable import AppMain

@Suite("Runtime Batch Runs State")
struct RuntimeBatchRunsStateTests {
    @Test("batch run setup input state parses models and config validation messages")
    @MainActor
    func batchRunSetupInputStateParsesModelsAndConfigValidationMessages() {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())

        #expect(viewModel.batchRunSetupCanRequestPreflight == false)
        #expect(viewModel.batchRunSetupValidationMessages.contains { $0.message == "Add at least one model repository." })

        viewModel.updateBatchRunModelListText(
            """
            # smoke targets
            01 | mlx-community/Qwen3-8B
            mlx-community/Mistral-7B
            """
        )
        viewModel.updateBatchRunConfigText(
            """
            run_id: smoke-batch
            bench_batch_size: 2
            api_token: plain-secret
            unknown_key: value
            broken line
            """
        )

        #expect(viewModel.batchRunModelInputs.map(\.repoID) == [
            "mlx-community/Qwen3-8B",
            "mlx-community/Mistral-7B",
        ])
        #expect(viewModel.batchRunModelInputs.map(\.index) == ["01", "02"])
        #expect(viewModel.batchRunConfigEntries.map(\.key).prefix(2) == ["run_id", "bench_batch_size"])
        #expect(viewModel.batchRunSetupCanRequestPreflight == false)
        #expect(viewModel.batchRunSetupValidationMessages.contains { $0.message.contains("api_token") })
        #expect(viewModel.batchRunSetupValidationMessages.contains { $0.message.contains("unknown_key") })
        #expect(viewModel.batchRunSetupValidationMessages.contains { $0.message.contains("line 5") })

        viewModel.updateBatchRunConfigText(
            """
            run_id: smoke-batch
            bench_batch_size: 2
            preflight: true
            """
        )

        #expect(viewModel.batchRunSetupCanRequestPreflight == true)
        #expect(viewModel.batchRunSetupValidationMessages.allSatisfy { $0.severity != .error })
        #expect(viewModel.batchRunSetupSummaryText == "2 models • 3 config values")
    }
}
