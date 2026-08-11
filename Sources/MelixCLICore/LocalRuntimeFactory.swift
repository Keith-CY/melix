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

enum MelixLocalRuntimeClientRoute: Equatable, Sendable {
    case inProcess
    case controlPlaneIPC(socketPath: String)
}

private struct MelixActiveRuntimeDescriptor: Decodable {
    let schemaVersion: String
    let appProcessId: Int32
    let controlPlaneProcessId: Int32
    let pythonWorkerProcessId: Int32
    let swiftTextWorkerProcessId: Int32
    let pythonWorkerSocketPath: String
    let swiftTextWorkerSocketPath: String
    let controlPlaneSocketPath: String?
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

private struct LeaseHoldingControlPlaneService: ControlPlaneExecuting {
    let service: any ControlPlaneExecuting
    // Retained for exactly as long as the in-process service remains reachable.
    let lease: ControlPlaneHomeOwnershipLease

    func handshake(
        _ request: Melix_Controlplane_V1_HandshakeRequest
    ) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        try await service.handshake(request)
    }

    func subscribe(
        _ request: Melix_Controlplane_V1_SubscribeRequest
    ) async -> ControlPlaneSubscription {
        await service.subscribe(request)
    }

    func unsubscribe(_ subscriptionID: String) async {
        await service.unsubscribe(subscriptionID)
    }

    func startChat(
        _ request: ControlPlaneChatRequest
    ) async throws -> ControlPlaneChatExecution {
        try await service.startChat(request)
    }

    func startAgentRun(
        _ command: Melix_Controlplane_V1_StartAgentRun,
        actorID: String,
        remoteTarget: ControlPlaneChatRequest.RemoteTarget?
    ) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
        try await service.startAgentRun(
            command,
            actorID: actorID,
            remoteTarget: remoteTarget
        )
    }

    func execute(
        _ request: Melix_Controlplane_V1_ControlPlaneRequest
    ) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        try await service.execute(request)
    }
}

private struct UnavailableControlPlaneService: ControlPlaneExecuting {
    let code: String
    let message: String

    private func failure() -> ControlPlaneXPCClientError {
        .requestFailed(code: code, message: message)
    }

    func handshake(
        _ request: Melix_Controlplane_V1_HandshakeRequest
    ) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        _ = request
        throw failure()
    }

    func subscribe(
        _ request: Melix_Controlplane_V1_SubscribeRequest
    ) async -> ControlPlaneSubscription {
        _ = request
        return ControlPlaneSubscription(
            subscriptionID: "unavailable",
            stream: AsyncStream { $0.finish() }
        )
    }

    func unsubscribe(_ subscriptionID: String) async {
        _ = subscriptionID
    }

    func startChat(
        _ request: ControlPlaneChatRequest
    ) async throws -> ControlPlaneChatExecution {
        _ = request
        throw failure()
    }

    func startAgentRun(
        _ command: Melix_Controlplane_V1_StartAgentRun,
        actorID: String,
        remoteTarget: ControlPlaneChatRequest.RemoteTarget?
    ) async throws -> Melix_Controlplane_V1_AgentRunSnapshot {
        _ = command
        _ = actorID
        _ = remoteTarget
        throw failure()
    }

    func execute(
        _ request: Melix_Controlplane_V1_ControlPlaneRequest
    ) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        _ = request
        throw failure()
    }
}

public enum MelixLocalRuntimeFactory {
    private static let activeRuntimeSchemaVersion = "melix.active_runtime.v1"
    private static let maximumActiveRuntimeDescriptorByteCount = 64 * 1_024

    public static func makeContext(environment: [String: String]) -> MelixLocalRuntimeContext {
        let metricsStore = MetricsStore(exportPath: environment["MELIX_CONTROL_PLANE_METRICS_PATH"])
        let homeOwnershipLease: ControlPlaneHomeOwnershipLease
        do {
            homeOwnershipLease = try ControlPlaneHomeOwnershipLease.acquire(
                environment: environment
            )
        } catch let error as ControlPlaneHomeOwnershipError {
            let code: String
            switch error {
            case .alreadyOwned:
                code = "control_plane_home_already_owned"
            case .unsafePath, .systemCall:
                code = "control_plane_home_ownership_unavailable"
            }
            return MelixLocalRuntimeContext(
                service: UnavailableControlPlaneService(
                    code: code,
                    message: error.localizedDescription
                ),
                metricsStore: metricsStore
            )
        } catch {
            return MelixLocalRuntimeContext(
                service: UnavailableControlPlaneService(
                    code: "control_plane_home_ownership_unavailable",
                    message: "Melix could not acquire the MELIX_HOME writer lease."
                ),
                metricsStore: metricsStore
            )
        }

        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
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
            gatewayAccessPolicyStore: gatewayAccessPolicyStore,
            environment: environment
        )
        return MelixLocalRuntimeContext(
            service: LeaseHoldingControlPlaneService(
                service: service,
                lease: homeOwnershipLease
            ),
            metricsStore: metricsStore
        )
    }

    public static func makeService(environment: [String: String]) -> any ControlPlaneExecuting {
        makeContext(environment: environment).service
    }

    public static func makeClient(environment: [String: String]) -> any ControlPlaneXPCClient {
        switch resolvedClientRoute(environment: environment) {
        case .inProcess:
            let context = makeContext(environment: environment)
            return LocalControlPlaneXPCClient(service: context.service)
        case let .controlPlaneIPC(socketPath):
            return LocalControlPlaneXPCClient(
                service: ControlPlaneIPCExecutionClient(socketPath: socketPath)
            )
        }
    }

    static func resolvedClientRoute(
        environment: [String: String]
    ) -> MelixLocalRuntimeClientRoute {
        resolvedClientRoute(
            environment: environment,
            processIsAlive: activeRuntimeProcessIsAlive,
            socketPathIsUsable: activeRuntimeSocketPathIsUsable
        )
    }

    static func resolvedClientRoute(
        environment: [String: String],
        processIsAlive: (Int32) -> Bool,
        socketPathIsUsable: (String) -> Bool
    ) -> MelixLocalRuntimeClientRoute {
        // The presence of an explicit value is authoritative, including an
        // invalid or blank value. The IPC client validates it and fails closed
        // instead of silently constructing a second mutable control plane.
        if let explicitSocketPath = environment["MELIX_CONTROL_PLANE_SOCKET_PATH"] {
            return .controlPlaneIPC(
                socketPath: explicitSocketPath.trimmingCharacters(
                    in: .whitespacesAndNewlines
                )
            )
        }

        guard let descriptor = loadActiveRuntimeDescriptor(environment: environment),
              descriptor.schemaVersion == activeRuntimeSchemaVersion,
              descriptor.controlPlaneProcessId > 1,
              let socketPath = descriptor.controlPlaneSocketPath.flatMap(
                normalizedAbsolutePath
              ),
              processIsAlive(descriptor.controlPlaneProcessId),
              socketPathIsUsable(socketPath)
        else {
            return .inProcess
        }
        return .controlPlaneIPC(socketPath: socketPath)
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

        // A fully explicit pair is an atomic override and must not be mixed
        // with a descriptor from another runtime instance.
        if let explicitPythonSocketPath, let explicitSwiftTextSocketPath {
            return MelixLocalRuntimeSocketPaths(
                pythonWorkerSocketPath: explicitPythonSocketPath,
                swiftTextWorkerSocketPath: explicitSwiftTextSocketPath
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
              let pythonSocketPath = explicitPythonSocketPath
                ?? normalizedAbsolutePath(descriptor.pythonWorkerSocketPath),
              let swiftTextSocketPath = explicitSwiftTextSocketPath
                ?? normalizedAbsolutePath(descriptor.swiftTextWorkerSocketPath)
        else {
            return MelixLocalRuntimeSocketPaths(
                pythonWorkerSocketPath: explicitPythonSocketPath
                    ?? MelixLocalRuntimeSocketPaths.defaults.pythonWorkerSocketPath,
                swiftTextWorkerSocketPath: explicitSwiftTextSocketPath
                    ?? MelixLocalRuntimeSocketPaths.defaults.swiftTextWorkerSocketPath
            )
        }

        guard processIsAlive(descriptor.appProcessId),
              explicitPythonSocketPath != nil || socketPathIsUsable(pythonSocketPath),
              explicitSwiftTextSocketPath != nil || socketPathIsUsable(swiftTextSocketPath)
        else {
            return MelixLocalRuntimeSocketPaths(
                pythonWorkerSocketPath: explicitPythonSocketPath
                    ?? MelixLocalRuntimeSocketPaths.defaults.pythonWorkerSocketPath,
                swiftTextWorkerSocketPath: explicitSwiftTextSocketPath
                    ?? MelixLocalRuntimeSocketPaths.defaults.swiftTextWorkerSocketPath
            )
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
