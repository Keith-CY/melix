import Foundation
@preconcurrency import Network
import MelixControlPlaneCore

@main
enum MelixControlPlaneBootstrap {
    static func main() async throws {
        let bootstrapStartedAt = Date()
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let bootstrapEnvironment = BootstrapEnvironment(environment: ProcessInfo.processInfo.environment)
        let mcpLoadStartedAt = Date()
        let mcpToolCatalog = MCPToolCatalog.load(environment: ProcessInfo.processInfo.environment)
        let gatewayAccessPolicy = GatewayAccessPolicy.load(environment: ProcessInfo.processInfo.environment)
        let gatewayAccessPolicyStore = GatewayAccessPolicyStore(gatewayAccessPolicy)
        let gatewayConfigStore = GatewayConfigStore(environment: ProcessInfo.processInfo.environment)
        let gatewayServingDefaultsStore = GatewayServingDefaultsStore(environment: ProcessInfo.processInfo.environment)
        let gatewayRuntimeBinding = await gatewayConfigStore.bootstrapBinding()
        let metricsStore = MetricsStore(exportPath: bootstrapEnvironment.controlPlaneMetricsPath)
        let persistentAuthSessionStore = PersistentAuthSessionStore(
            environment: ProcessInfo.processInfo.environment,
            metricsStore: metricsStore
        )
        _ = try? await persistentAuthSessionStore.restorePersistedSessions()
        try? await persistentAuthSessionStore.reconcile(with: gatewayAccessPolicy)
        await metricsStore.set(
            Date().timeIntervalSince(mcpLoadStartedAt) * 1000,
            forKey: "mcp.config_load_latency_ms"
        )
        await metricsStore.set(
            Double(mcpToolCatalog.sources.filter { !$0.enabled }.count),
            forKey: "mcp.disabled_tool_source_count"
        )
        await metricsStore.set(Double(mcpToolCatalog.refusedNamespaceCount), forKey: "mcp.refused_tool_count")
        await metricsStore.set(gatewayAccessPolicy.metricModeCode, forKey: "gateway.auth_mode_code")
        await metricsStore.set(Double(gatewayAccessPolicy.acceptedAPIKeyCount), forKey: "gateway.accepted_api_key_count")
        await metricsStore.set(gatewayAccessPolicy.sharedAccessEnabled ? 1 : 0, forKey: "shared_access.enabled")
        await metricsStore.set(gatewayAccessPolicy.sharedAccessReady ? 1 : 0, forKey: "shared_access.ready")
        await metricsStore.set(Double(gatewayRuntimeBinding.port), forKey: "gateway.listener_port")
        await metricsStore.set(0, forKey: "gateway.api_key_apply_ms")
        await metricsStore.set(0, forKey: "gateway.config_apply_ms")
        await metricsStore.set(0, forKey: "gateway.config_persist_failures")
        await metricsStore.set(0, forKey: "gateway.config_requires_restart_count")
        await metricsStore.set(0, forKey: "gateway.serving_defaults_apply_ms")
        await metricsStore.set(0, forKey: "gateway.serving_defaults_persist_failures")
        await metricsStore.set(0, forKey: "gateway.generation_default_merge_count")
        await metricsStore.set(0, forKey: "gateway.speculative_config_apply_ms")
        await metricsStore.set(0, forKey: "gateway.auth_validation_failures")
        await metricsStore.set(0, forKey: "http.request_header_rejected_count")
        await metricsStore.set(0, forKey: "http.request_body_rejected_count")
        await metricsStore.set(0, forKey: "http.forwarded_prefix_rejected_count")
        await metricsStore.set(0, forKey: "shared_access.accepted_client_count")
        await metricsStore.set(0, forKey: "shared_access.rejected_request_count")
        await metricsStore.set(0, forKey: "persistent_session.active_session_count")
        await metricsStore.set(0, forKey: "persistent_session.remembered_session_count")
        await metricsStore.set(0, forKey: "persistent_session.expired_session_count")
        await metricsStore.set(0, forKey: "persistent_session.restore_success_rate")
        await metricsStore.set(0, forKey: "persistent_session.sign_out_latency_ms")
        await metricsStore.set(
            Double(
                max(
                    Int(
                        ProcessInfo.processInfo.environment["MELIX_PERSISTENT_AUTH_SESSION_TTL_SECONDS"] ?? ""
                    ) ?? 2_592_000,
                    1
                )
            ),
            forKey: "persistent_session.retention_ttl_seconds"
        )
        let eventHub = EventSubscriptionHub()
        let sessionGraphStore = SessionGraphStore(metricsStore: metricsStore)
        let cacheMetadataStore = CacheMetadataStore()
        let imageJobReadModel = ImageJobReadModel(
            eventPublisher: { event in
                await eventHub.publish(event)
            }
        )
        let schedulerReadModel = SchedulerReadModel(
            metricsStore: metricsStore,
            eventPublisher: { event in
                await eventHub.publish(event)
            }
        )
        let imageJobAdmissionController = ImageJobAdmissionController(
            schedulerReadModel: schedulerReadModel,
            metricsStore: metricsStore
        )
        let swiftTextWorkerClient = SwiftTextWorkerClient(
            socketPath: bootstrapEnvironment.swiftTextWorkerSocketPath
        )
        let pythonCompatibilityClient = PythonBridgeWorkerClient(
            socketPath: bootstrapEnvironment.pythonWorkerSocketPath
        )
        let workerRegistry = WorkerRegistry(
            defaultTextClient: swiftTextWorkerClient,
            pythonCompatibilityClient: pythonCompatibilityClient,
            modelCatalog: modelCatalog
        )

        _ = ControlPlaneService(
            modelCatalog: modelCatalog,
            metricsStore: metricsStore,
            eventHub: eventHub,
            schedulerReadModel: schedulerReadModel,
            cacheMetadataStore: cacheMetadataStore,
            sessionGraphStore: sessionGraphStore,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: imageJobAdmissionController,
            mcpToolCatalog: mcpToolCatalog,
            gatewayConfigStore: gatewayConfigStore,
            gatewayServingDefaultsStore: gatewayServingDefaultsStore,
            gatewayRuntimeBinding: gatewayRuntimeBinding,
            gatewayAccessPolicyStore: gatewayAccessPolicyStore,
            persistentAuthSessionStore: persistentAuthSessionStore
        )

        let handler = OpenAIHandler(
            modelCatalog: modelCatalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: workerRegistry,
                abortRegistry: AbortRegistry(),
                schedulerReadModel: schedulerReadModel,
                metricsStore: metricsStore,
                modelCatalog: modelCatalog,
                sessionGraphStore: sessionGraphStore,
                cacheMetadataStore: cacheMetadataStore
            ),
            workerRegistry: workerRegistry,
            metricsStore: metricsStore,
            schedulerReadModel: schedulerReadModel,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: imageJobAdmissionController,
            cacheMetadataStore: cacheMetadataStore,
            mcpToolCatalog: mcpToolCatalog,
            gatewayAccessPolicyStore: gatewayAccessPolicyStore,
            gatewayServingDefaultsStore: gatewayServingDefaultsStore,
            gatewayRuntimeBinding: gatewayRuntimeBinding,
            persistentAuthSessionStore: persistentAuthSessionStore
        )

        let server = try BootstrapHTTPServer(
            host: gatewayRuntimeBinding.host,
            port: UInt16(gatewayRuntimeBinding.port),
            handler: handler,
            metricsStore: metricsStore
        )
        try await server.start()
        await metricsStore.set(
            Date().timeIntervalSince(bootstrapStartedAt) * 1000,
            forKey: "control_plane.http_ready_ms"
        )
        let _: Task<Void, Never> = BootstrapPreloadCoordinator.startBackgroundPhaseSevenPythonPreload(
            workerClient: pythonCompatibilityClient,
            modelCatalog: modelCatalog,
            metricsStore: metricsStore
        )
        print("Melix control plane ready on http://\(gatewayRuntimeBinding.host):\(gatewayRuntimeBinding.port)")
        await server.waitUntilStopped()
    }
}

private struct BootstrapEnvironment {
    let repoRoot: String
    let pythonWorkerSocketPath: String
    let swiftTextWorkerSocketPath: String
    let controlPlaneMetricsPath: String?
    let mcpConfigPath: String?

    init(environment: [String: String]) {
        if let repoRoot = environment["MELIX_REPO_ROOT"], !repoRoot.isEmpty {
            self.repoRoot = repoRoot
        } else {
            self.repoRoot = BootstrapEnvironment.inferRepoRoot()
        }
        self.pythonWorkerSocketPath = environment["MELIX_WORKER_SOCKET_PATH"] ?? "/tmp/melix-worker.sock"
        self.swiftTextWorkerSocketPath =
            environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] ?? "/var/run/melix/swift-text-worker.sock"
        self.controlPlaneMetricsPath = environment["MELIX_CONTROL_PLANE_METRICS_PATH"]
        self.mcpConfigPath = environment["MELIX_MCP_CONFIG_PATH"]
    }

    private static func inferRepoRoot() -> String {
        let sourceFile = URL(fileURLWithPath: #filePath)
        return sourceFile
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .path
    }
}

private final class BootstrapHTTPServer: @unchecked Sendable {
    private let listener: NWListener
    private let handler: OpenAIHandler
    private let metricsStore: MetricsStore
    private let host: String
    private let queue = DispatchQueue(label: "com.melix.http-gateway")

    init(host: String, port: UInt16, handler: OpenAIHandler, metricsStore: MetricsStore) throws {
        guard let port = NWEndpoint.Port(rawValue: port) else {
            throw BootstrapHTTPServerError.invalidPort
        }
        self.host = host
        self.handler = handler
        self.metricsStore = metricsStore
        listener = try NWListener(using: .tcp, on: port)
    }

    func start() async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            let startState = ListenerStartState()
            listener.stateUpdateHandler = { newState in
                switch newState {
                case .ready:
                    guard startState.resumeIfNeeded() else { return }
                    continuation.resume()
                case .failed(let error):
                    guard startState.resumeIfNeeded() else { return }
                    continuation.resume(throwing: error)
                default:
                    break
                }
            }

            listener.newConnectionHandler = { [weak self] connection in
                self?.handle(connection)
            }
            listener.start(queue: queue)
        }
    }

    func waitUntilStopped() async {
        while true {
            try? await Task.sleep(for: .seconds(3600))
        }
    }

    private func handle(_ connection: NWConnection) {
        connection.start(queue: queue)
        receive(on: connection, buffer: Data())
    }

    private func receive(on connection: NWConnection, buffer: Data) {
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { [weak self] data, _, isComplete, error in
            guard let self else { return }
            if let error {
                connection.cancel()
                print("Melix HTTP receive failed: \(error)")
                return
            }

            let updatedBuffer = buffer + (data ?? Data())
            switch HTTPGatewayRequestParser.parseRequest(from: updatedBuffer) {
            case .success(let request):
                Task {
                    let response = try await self.handler.handle(request)
                    try await self.send(response, on: connection)
                }
            case .failure(.incomplete):
                guard !isComplete else {
                    connection.cancel()
                    return
                }
                self.receive(on: connection, buffer: updatedBuffer)
            case .failure(let parseError):
                Task {
                    await self.recordParserRefusal(parseError)
                    try await self.send(Self.errorResponse(for: parseError), on: connection)
                }
            }
        }
    }

    private func recordParserRefusal(_ parseError: HTTPGatewayRequestParseError) async {
        switch parseError {
        case .headersTooLarge, .duplicateHeader:
            await metricsStore.increment("http.request_header_rejected_count")
        case .bodyTooLarge, .unsupportedChunkedBody:
            await metricsStore.increment("http.request_body_rejected_count")
        case .invalidForwardedPrefix:
            await metricsStore.increment("http.forwarded_prefix_rejected_count")
        case .incomplete, .invalidRequest:
            break
        }
    }

    private func send(_ response: HTTPResponse, on connection: NWConnection) async throws {
        var headers = response.headers
        headers["host"] = host

        switch response.body {
        case .data(let data):
            headers["content-length"] = String(data.count)
            headers["connection"] = "close"
            try await connection.send(content: Self.headerBlock(statusCode: response.statusCode, headers: headers))
            try await connection.send(content: data)
        case .stream(let stream):
            headers["connection"] = "close"
            try await connection.send(content: Self.headerBlock(statusCode: response.statusCode, headers: headers))
            for try await chunk in stream {
                try await connection.send(content: chunk)
            }
        }

        connection.cancel()
    }

    private static func errorResponse(for parseError: HTTPGatewayRequestParseError) -> HTTPResponse {
        HTTPGatewayRequestParser.errorResponse(for: parseError)
    }

    private static func headerBlock(statusCode: Int, headers: [String: String]) -> Data {
        var lines = ["HTTP/1.1 \(statusCode) \(reasonPhrase(for: statusCode))"]
        for key in headers.keys.sorted() {
            if let value = headers[key] {
                lines.append("\(key): \(value)")
            }
        }
        lines.append("")
        lines.append("")
        return Data(lines.joined(separator: "\r\n").utf8)
    }

    private static func reasonPhrase(for statusCode: Int) -> String {
        switch statusCode {
        case 200:
            return "OK"
        case 400:
            return "Bad Request"
        case 404:
            return "Not Found"
        case 409:
            return "Conflict"
        case 413:
            return "Payload Too Large"
        case 431:
            return "Request Header Fields Too Large"
        case 503:
            return "Service Unavailable"
        default:
            return "OK"
        }
    }

}

private enum BootstrapHTTPServerError: Error {
    case invalidPort
}

private final class ListenerStartState: @unchecked Sendable {
    private let lock = NSLock()
    private var resumed = false

    func resumeIfNeeded() -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard !resumed else {
            return false
        }
        resumed = true
        return true
    }
}

private extension NWConnection {
    func send(content: Data) async throws {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            self.send(content: content, completion: .contentProcessed { error in
                if let error {
                    continuation.resume(throwing: error)
                } else {
                    continuation.resume()
                }
            })
        }
    }
}
