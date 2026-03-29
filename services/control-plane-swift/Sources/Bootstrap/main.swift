import Foundation
@preconcurrency import Network
import MelixControlPlaneCore

@main
enum MelixControlPlaneBootstrap {
    static func main() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let bootstrapEnvironment = BootstrapEnvironment(environment: ProcessInfo.processInfo.environment)
        let metricsStore = MetricsStore(exportPath: bootstrapEnvironment.controlPlaneMetricsPath)
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
        let swiftTextWorkerClient = SwiftTextWorkerClient(
            socketPath: bootstrapEnvironment.swiftTextWorkerSocketPath
        )
        let pythonCompatibilityClient = PythonBridgeWorkerClient(
            socketPath: bootstrapEnvironment.pythonWorkerSocketPath,
            repoRoot: bootstrapEnvironment.repoRoot,
            processEnvironment: ProcessInfo.processInfo.environment
        )
        let workerRegistry = WorkerRegistry(
            defaultTextClient: swiftTextWorkerClient,
            pythonCompatibilityClient: pythonCompatibilityClient,
            modelCatalog: modelCatalog
        )

        let preloadStartedAt = Date()
        do {
            _ = try await BootstrapWorkerPreparation.preloadDevTextModel(
                workerClient: swiftTextWorkerClient,
                modelCatalog: modelCatalog
            )
            await metricsStore.set(
                Date().timeIntervalSince(preloadStartedAt) * 1000,
                forKey: "control_plane.worker_preload_ms"
            )
        } catch {
            print("Melix worker preload skipped: \(error)")
            await metricsStore.set(
                Date().timeIntervalSince(preloadStartedAt) * 1000,
                forKey: "control_plane.worker_preload_ms"
            )
        }

        do {
            try await BootstrapWorkerPreparation.preloadPhaseSevenPythonModels(
                workerClient: pythonCompatibilityClient,
                modelCatalog: modelCatalog
            )
        } catch {
            print("Melix phase-7 python model preload skipped: \(error)")
        }

        _ = ControlPlaneService(
            modelCatalog: modelCatalog,
            metricsStore: metricsStore,
            eventHub: eventHub,
            schedulerReadModel: schedulerReadModel,
            cacheMetadataStore: cacheMetadataStore,
            sessionGraphStore: sessionGraphStore,
            imageJobReadModel: imageJobReadModel
        )

        let handler = OpenAIHandler(
            modelCatalog: modelCatalog,
            requestCoordinator: RequestCoordinator(
                workerRegistry: workerRegistry,
                abortRegistry: AbortRegistry(),
                schedulerReadModel: schedulerReadModel,
                metricsStore: metricsStore,
                sessionGraphStore: sessionGraphStore,
                cacheMetadataStore: cacheMetadataStore
            ),
            workerRegistry: workerRegistry,
            metricsStore: metricsStore,
            schedulerReadModel: schedulerReadModel,
            imageJobReadModel: imageJobReadModel,
            cacheMetadataStore: cacheMetadataStore
        )

        let server = try BootstrapHTTPServer(
            host: ProcessInfo.processInfo.environment["MELIX_HTTP_HOST"] ?? "127.0.0.1",
            port: Self.httpPort(),
            handler: handler
        )
        try await server.start()
        print("Melix control plane ready on http://127.0.0.1:\(Self.httpPort())")
        await server.waitUntilStopped()
    }

    private static func httpPort() -> UInt16 {
        guard
            let raw = ProcessInfo.processInfo.environment["MELIX_HTTP_PORT"],
            let port = UInt16(raw)
        else {
            return 11434
        }
        return port
    }
}

private struct BootstrapEnvironment {
    let repoRoot: String
    let pythonWorkerSocketPath: String
    let swiftTextWorkerSocketPath: String
    let controlPlaneMetricsPath: String?

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
    private let host: String
    private let queue = DispatchQueue(label: "com.melix.http-gateway")

    init(host: String, port: UInt16, handler: OpenAIHandler) throws {
        guard let port = NWEndpoint.Port(rawValue: port) else {
            throw BootstrapHTTPServerError.invalidPort
        }
        self.host = host
        self.handler = handler
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
            switch Self.parseRequest(from: updatedBuffer) {
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
            case .failure(.invalid):
                Task {
                    try await self.send(Self.badRequestResponse(), on: connection)
                }
            }
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

    private static func badRequestResponse() -> HTTPResponse {
        HTTPResponse(
            statusCode: 400,
            headers: ["content-type": "application/json"],
            body: .data(Data(#"{"error":{"code":"bad_request","message":"Unable to parse HTTP request."}}"#.utf8))
        )
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
        case 503:
            return "Service Unavailable"
        default:
            return "OK"
        }
    }

    private static func parseRequest(from data: Data) -> Result<HTTPRequest, ParseError> {
        guard let headerRange = data.range(of: Data("\r\n\r\n".utf8)) else {
            return .failure(.incomplete)
        }

        let headerData = data[..<headerRange.lowerBound]
        guard let headerText = String(data: headerData, encoding: .utf8) else {
            return .failure(.invalid)
        }

        let lines = headerText.components(separatedBy: "\r\n")
        guard let requestLine = lines.first else {
            return .failure(.invalid)
        }

        let requestParts = requestLine.split(separator: " ")
        guard requestParts.count == 3 else {
            return .failure(.invalid)
        }

        let method: HTTPMethod
        switch String(requestParts[0]).uppercased() {
        case "GET":
            method = .get
        case "POST":
            method = .post
        default:
            return .failure(.invalid)
        }

        var headers: [String: String] = [:]
        for line in lines.dropFirst() {
            let pair = line.split(separator: ":", maxSplits: 1)
            guard pair.count == 2 else { continue }
            headers[String(pair[0]).lowercased()] = String(pair[1]).trimmingCharacters(in: .whitespaces)
        }

        let bodyStart = headerRange.upperBound
        let contentLength = Int(headers["content-length"] ?? "0") ?? 0
        let expectedBodyEnd = bodyStart + contentLength
        guard data.count >= expectedBodyEnd else {
            return .failure(.incomplete)
        }

        let body = data[bodyStart..<expectedBodyEnd]
        return .success(
            HTTPRequest(
                method: method,
                path: String(requestParts[1]),
                headers: headers,
                body: Data(body)
            )
        )
    }
}

private enum BootstrapHTTPServerError: Error {
    case invalidPort
}

private enum ParseError: Error {
    case incomplete
    case invalid
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
