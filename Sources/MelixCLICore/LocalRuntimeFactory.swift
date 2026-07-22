import Darwin
import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol

struct MelixLocalRuntimeSocketPaths: Equatable, Sendable {
    static let defaults = MelixLocalRuntimeSocketPaths(
        pythonWorkerSocketPath: "/tmp/melix-worker.sock",
        swiftTextWorkerSocketPath: "/var/run/melix/swift-text-worker.sock"
    )

    let pythonWorkerSocketPath: String
    let swiftTextWorkerSocketPath: String
}

private struct MelixActiveRuntimeDescriptor: Decodable {
    let schemaVersion: String
    let appProcessId: Int32
    let controlPlaneProcessId: Int32
    let pythonWorkerProcessId: Int32
    let swiftTextWorkerProcessId: Int32
    let pythonWorkerSocketPath: String
    let swiftTextWorkerSocketPath: String
    let serviceBaseUrl: String
    let updatedAtUnixMs: Int64
}

public struct MelixLocalRuntimeContext: Sendable {
    public let service: any ControlPlaneExecuting
    public let metricsStore: MetricsStore

    public init(service: any ControlPlaneExecuting, metricsStore: MetricsStore) {
        self.service = service
        self.metricsStore = metricsStore
    }
}

public enum MelixLocalRuntimeFactory {
    private static let activeRuntimeSchemaVersion = "melix.active_runtime.v1"
    private static let maximumActiveRuntimeDescriptorByteCount = 64 * 1_024

    public static func makeContext(environment: [String: String]) -> MelixLocalRuntimeContext {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let metricsStore = MetricsStore(exportPath: environment["MELIX_CONTROL_PLANE_METRICS_PATH"])
        let mcpToolCatalog = MCPToolCatalog.load(environment: environment)
        let gatewayAccessPolicyStore = GatewayAccessPolicyStore(GatewayAccessPolicy.load(environment: environment))
        let gatewayConfigStore = GatewayConfigStore(environment: environment)
        let gatewayServingDefaultsStore = GatewayServingDefaultsStore(environment: environment)
        let imageDefaultsStore = ImageDefaultsStore(environment: environment)
        let workerSocketPaths = resolvedWorkerSocketPaths(environment: environment)

        let swiftTextWorkerClient = SwiftTextWorkerClient(
            socketPath: workerSocketPaths.swiftTextWorkerSocketPath
        )
        let pythonCompatibilityClient = PythonBridgeWorkerClient(
            socketPath: workerSocketPaths.pythonWorkerSocketPath,
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
            gatewayConfigStore: gatewayConfigStore,
            gatewayServingDefaultsStore: gatewayServingDefaultsStore,
            imageDefaultsStore: imageDefaultsStore,
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

    static func resolvedWorkerSocketPaths(
        environment: [String: String]
    ) -> MelixLocalRuntimeSocketPaths {
        resolvedWorkerSocketPaths(
            environment: environment,
            processIsAlive: activeRuntimeProcessIsAlive,
            socketPathIsUsable: activeRuntimeSocketPathIsUsable
        )
    }

    static func resolvedWorkerSocketPaths(
        environment: [String: String],
        processIsAlive: (Int32) -> Bool,
        socketPathIsUsable: (String) -> Bool
    ) -> MelixLocalRuntimeSocketPaths {
        let explicitPythonSocketPath = environment["MELIX_WORKER_SOCKET_PATH"]
        let explicitSwiftTextSocketPath = environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"]

        if explicitPythonSocketPath != nil || explicitSwiftTextSocketPath != nil {
            return MelixLocalRuntimeSocketPaths(
                pythonWorkerSocketPath: explicitPythonSocketPath
                    ?? MelixLocalRuntimeSocketPaths.defaults.pythonWorkerSocketPath,
                swiftTextWorkerSocketPath: explicitSwiftTextSocketPath
                    ?? MelixLocalRuntimeSocketPaths.defaults.swiftTextWorkerSocketPath
            )
        }

        guard let descriptor = loadActiveRuntimeDescriptor(environment: environment),
              descriptor.schemaVersion == activeRuntimeSchemaVersion,
              descriptor.appProcessId > 1,
              descriptor.controlPlaneProcessId > 1,
              descriptor.pythonWorkerProcessId > 1,
              descriptor.swiftTextWorkerProcessId > 1,
              descriptor.updatedAtUnixMs > 0,
              !descriptor.serviceBaseUrl.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              let pythonSocketPath = normalizedAbsolutePath(descriptor.pythonWorkerSocketPath),
              let swiftTextSocketPath = normalizedAbsolutePath(descriptor.swiftTextWorkerSocketPath)
        else {
            return .defaults
        }

        guard processIsAlive(descriptor.appProcessId),
              socketPathIsUsable(pythonSocketPath),
              socketPathIsUsable(swiftTextSocketPath)
        else {
            return .defaults
        }

        return MelixLocalRuntimeSocketPaths(
            pythonWorkerSocketPath: pythonSocketPath,
            swiftTextWorkerSocketPath: swiftTextSocketPath
        )
    }

    private static func loadActiveRuntimeDescriptor(
        environment: [String: String]
    ) -> MelixActiveRuntimeDescriptor? {
        let descriptorURL: URL
        if let overriddenPath = nonEmptyPath(environment["MELIX_ACTIVE_RUNTIME_PATH"]) {
            let expandedPath = (overriddenPath as NSString).expandingTildeInPath
            guard (expandedPath as NSString).isAbsolutePath else {
                return nil
            }
            descriptorURL = URL(
                fileURLWithPath: expandedPath,
                isDirectory: false
            ).standardizedFileURL
        } else if environment["MELIX_ACTIVE_RUNTIME_PATH"] != nil {
            return nil
        } else {
            descriptorURL = MelixPathLayout(environment: environment)
                .runtimeDirectoryURL
                .appendingPathComponent("active-runtime.json", isDirectory: false)
        }

        guard let attributes = try? FileManager.default.attributesOfItem(atPath: descriptorURL.path),
              attributes[.type] as? FileAttributeType == .typeRegular,
              (attributes[.posixPermissions] as? NSNumber)?.intValue == 0o600,
              (attributes[.ownerAccountID] as? NSNumber)?.uint32Value == geteuid(),
              let fileSize = (attributes[.size] as? NSNumber)?.intValue,
              fileSize > 0,
              fileSize <= maximumActiveRuntimeDescriptorByteCount,
              let data = try? Data(contentsOf: descriptorURL),
              data.count <= maximumActiveRuntimeDescriptorByteCount
        else {
            return nil
        }

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try? decoder.decode(MelixActiveRuntimeDescriptor.self, from: data)
    }

    private static func activeRuntimeProcessIsAlive(_ processID: Int32) -> Bool {
        errno = 0
        return kill(processID, 0) == 0 || errno == EPERM
    }

    private static func activeRuntimeSocketPathIsUsable(_ path: String) -> Bool {
        FileManager.default.fileExists(atPath: path)
    }

    private static func normalizedAbsolutePath(_ rawValue: String) -> String? {
        let path = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !path.isEmpty, (path as NSString).isAbsolutePath else {
            return nil
        }
        return URL(fileURLWithPath: path, isDirectory: false).standardizedFileURL.path
    }

    private static func nonEmptyPath(_ rawValue: String?) -> String? {
        let value = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? nil : value
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
