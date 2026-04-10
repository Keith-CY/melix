import Foundation
import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public protocol MelixOperatorCommandRunning: Sendable {
    func run(_ command: MelixCLICommand) async throws -> String
    func performModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult
    func inspectModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo
    func loadModel(modelID: String, memoryBudgetBytes: UInt64) async throws -> Melix_Controlplane_V1_ModelSummary
    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary
    func searchHubModels(
        query: String,
        pageSize: UInt32,
        cursor: String,
        mlxOnly: Bool
    ) async throws -> Melix_Controlplane_V1_HubSearchResult
    func getHubModelCard(repoID: String) async throws -> Melix_Controlplane_V1_HubModelCard
    func downloadHubModel(repoID: String, revision: String) async throws -> Melix_Controlplane_V1_ModelOperationResult
    func applyConfiguredServerSessionGatewayConfig(
        serverSessionID: String
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot
    func applyConfiguredServerSessionServingDefaults(
        serverSessionID: String
    ) async throws -> Melix_Controlplane_V1_ServerSnapshot
    func runBenchmark(_ options: BenchRunOptions) async throws -> ControlPlaneBenchResult
    func runBenchmarkMatrix(_ options: BenchMatrixRunOptions) async throws -> ControlPlaneBenchMatrixResult
    func runEvaluations(_ options: EvalRunOptions) async throws -> [ControlPlaneEvaluationResult]
    func fetchBenchmarkExportBundle(outputDir: String) async throws -> ControlPlaneBenchmarkExportBundle
}

extension MelixCLIRunner: MelixOperatorCommandRunning {}

public extension MelixOperatorCommandRunning {
    func performModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        try await performModelOperation(
            modelID: modelID,
            operation: operation,
            outputDir: outputDir,
            quantProfileID: "",
            weightQuant: "",
            kvQuant: "",
            ext: ext
        )
    }

    func searchHubModels(
        query: String,
        mlxOnly: Bool
    ) async throws -> Melix_Controlplane_V1_HubSearchResult {
        try await searchHubModels(
            query: query,
            pageSize: 10,
            cursor: "",
            mlxOnly: mlxOnly
        )
    }
}
