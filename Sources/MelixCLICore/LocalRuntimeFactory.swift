import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public struct MelixLocalRuntimeContext: Sendable {
    public let service: any ControlPlaneExecuting
    public let metricsStore: MetricsStore

    public init(service: any ControlPlaneExecuting, metricsStore: MetricsStore) {
        self.service = service
        self.metricsStore = metricsStore
    }
}

public enum MelixLocalRuntimeFactory {
    public static func makeContext(environment: [String: String]) -> MelixLocalRuntimeContext {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let metricsStore = MetricsStore(exportPath: environment["MELIX_CONTROL_PLANE_METRICS_PATH"])
        let mcpToolCatalog = MCPToolCatalog.load(environment: environment)
        let gatewayAccessPolicyStore = GatewayAccessPolicyStore(GatewayAccessPolicy.load(environment: environment))

        let swiftTextWorkerClient = SwiftTextWorkerClient(
            socketPath: environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] ?? "/var/run/melix/swift-text-worker.sock"
        )
        let pythonCompatibilityClient = PythonBridgeWorkerClient(
            socketPath: environment["MELIX_WORKER_SOCKET_PATH"] ?? "/tmp/melix-worker.sock",
            repoRoot: repoRoot(environment: environment),
            processEnvironment: environment
        )
        let workerRegistry = WorkerRegistry(
            defaultTextClient: swiftTextWorkerClient,
            pythonCompatibilityClient: pythonCompatibilityClient,
            modelCatalog: modelCatalog
        )

        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            metricsStore: metricsStore,
            workerRegistry: workerRegistry,
            mcpToolCatalog: mcpToolCatalog,
            gatewayAccessPolicyStore: gatewayAccessPolicyStore
        )
        return MelixLocalRuntimeContext(service: service, metricsStore: metricsStore)
    }

    public static func makeService(environment: [String: String]) -> any ControlPlaneExecuting {
        makeContext(environment: environment).service
    }

    public static func makeClient(environment: [String: String]) -> any ControlPlaneXPCClient {
        let context = makeContext(environment: environment)
        return LocalControlPlaneXPCClient(service: context.service)
    }

    private static func repoRoot(environment: [String: String]) -> String {
        if let repoRoot = environment["MELIX_REPO_ROOT"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           !repoRoot.isEmpty {
            return repoRoot
        }

        return URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .path
    }
}
