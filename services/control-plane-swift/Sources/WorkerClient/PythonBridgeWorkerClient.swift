import Foundation
import SwiftProtobuf

import MelixWorkerProtocol

public enum BridgeCommandKind: String, Sendable {
    case handshake = "handshake"
    case loadModel = "load-model"
    case generate = "generate"
    case abort = "abort"
}

public struct BridgeCommand: Sendable {
    public let kind: BridgeCommandKind
    public let socketPath: String
    public let requestData: Data

    public init(kind: BridgeCommandKind, socketPath: String, requestData: Data) {
        self.kind = kind
        self.socketPath = socketPath
        self.requestData = requestData
    }
}

public protocol WorkerBridgeRunning: Sendable {
    func runUnary(command: BridgeCommand) async throws -> String
    func runStream(command: BridgeCommand) async throws -> AsyncThrowingStream<String, Error>
}

public struct PythonBridgeWorkerClient: WorkerClient, Sendable {
    private let socketPath: String
    private let runner: any WorkerBridgeRunning

    public init(socketPath: String, runner: any WorkerBridgeRunning) {
        self.socketPath = socketPath
        self.runner = runner
    }

    public init(
        socketPath: String,
        repoRoot: String,
        processEnvironment: [String: String] = ProcessInfo.processInfo.environment
    ) {
        self.init(
            socketPath: socketPath,
            runner: ProcessWorkerBridgeRunner(
                repoRoot: repoRoot,
                environment: processEnvironment
            )
        )
    }

    public func canDispatchRequests() async -> Bool {
        var request = Melix_Worker_V1_HandshakeRequest()
        request.protocolVersion = "melix.worker.v1"
        request.workerID = "control-plane"
        request.controlplaneInstanceID = "melix-control-plane"

        do {
            _ = try await sendUnary(
                kind: .handshake,
                request: request,
                as: Melix_Worker_V1_HandshakeResponse.self
            )
            return true
        } catch {
            return false
        }
    }

    public func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        try await sendUnary(kind: .loadModel, request: request, as: Melix_Worker_V1_LoadModelResponse.self)
    }

    public func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        let lineStream = try await runner.runStream(
            command: BridgeCommand(
                kind: .generate,
                socketPath: socketPath,
                requestData: try request.serializedData()
            )
        )

        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for try await line in lineStream {
                        let event: Melix_Worker_V1_ExecuteEvent = try decodeLine(line)
                        continuation.yield(event)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    public func abort(requestID: String) async throws -> Bool {
        var request = Melix_Worker_V1_AbortRequest()
        request.requestID = requestID

        let response: Melix_Worker_V1_AbortResponse = try await sendUnary(
            kind: .abort,
            request: request,
            as: Melix_Worker_V1_AbortResponse.self
        )
        return response.ok && response.found
    }

    private func sendUnary<Request: SwiftProtobuf.Message, Response: SwiftProtobuf.Message>(
        kind: BridgeCommandKind,
        request: Request,
        as _: Response.Type
    ) async throws -> Response {
        let line = try await runner.runUnary(
            command: BridgeCommand(
                kind: kind,
                socketPath: socketPath,
                requestData: try request.serializedData()
            )
        )
        return try decodeLine(line)
    }

    private func decodeLine<Message: SwiftProtobuf.Message>(_ line: String) throws -> Message {
        let payload = try WorkerBridgeLine.decode(from: line)
        switch payload.kind {
        case "message":
            guard let encoded = payload.messageBase64, let data = Data(base64Encoded: encoded) else {
                throw WorkerClientError.unavailable
            }
            return try Message(serializedBytes: data)
        case "error":
            throw WorkerClientError.unavailable
        default:
            throw WorkerClientError.unavailable
        }
    }
}

public enum BootstrapWorkerPreparation {
    public static func preloadDevTextModel(
        workerClient: PythonBridgeWorkerClient,
        modelCatalog: ModelCatalog,
        memoryBudgetBytes: UInt64 = 0
    ) async throws -> Bool {
        var request = Melix_Worker_V1_LoadModelRequest()
        request.model = devTextModel()
        request.memoryBudgetBytes = memoryBudgetBytes
        request.pinOnLoad = true
        request.warmupAfterLoad = false

        let response = try await workerClient.loadModel(request: request)
        guard response.ok, !response.modelHandle.isEmpty else {
            return false
        }

        _ = await modelCatalog.loadModel(id: request.model.modelID, dispatchHandle: response.modelHandle)
        return true
    }

    private static func devTextModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-text"
        model.modelPath = "models/melix-dev-text"
        model.modelKind = "text"
        model.revision = "dev"
        model.tokenizerHash = "tok-dev"
        model.quantProfileID = "q4"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 8192
        return model
    }
}

private struct WorkerBridgeLine: Decodable {
    let kind: String
    let messageBase64: String?

    enum CodingKeys: String, CodingKey {
        case kind
        case messageBase64 = "message_b64"
    }

    static func decode(from line: String) throws -> WorkerBridgeLine {
        try JSONDecoder().decode(Self.self, from: Data(line.utf8))
    }
}

public struct ProcessWorkerBridgeRunner: WorkerBridgeRunning, Sendable {
    private let repoRoot: String
    private let environment: [String: String]

    public init(repoRoot: String, environment: [String: String]) {
        self.repoRoot = repoRoot
        self.environment = environment
    }

    public func runUnary(command: BridgeCommand) async throws -> String {
        let process = configuredProcess(for: command)
        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()
        process.waitUntilExit()

        let output = String(decoding: try stdout.fileHandleForReading.readToEnd() ?? Data(), as: UTF8.self)
        _ = String(decoding: try stderr.fileHandleForReading.readToEnd() ?? Data(), as: UTF8.self)

        guard process.terminationStatus == 0,
              let line = output.split(separator: "\n").last.map(String.init),
              !line.isEmpty
        else {
            throw WorkerClientError.unavailable
        }
        return line
    }

    public func runStream(command: BridgeCommand) async throws -> AsyncThrowingStream<String, Error> {
        let process = configuredProcess(for: command)
        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()

        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for try await line in stdout.fileHandleForReading.bytes.lines {
                        continuation.yield(String(line))
                    }
                    process.waitUntilExit()
                    if process.terminationStatus == 0 {
                        continuation.finish()
                    } else {
                        _ = try stderr.fileHandleForReading.readToEnd()
                        continuation.finish(throwing: WorkerClientError.unavailable)
                    }
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
                if process.isRunning {
                    process.terminate()
                }
            }
        }
    }

    private func configuredProcess(for command: BridgeCommand) -> Process {
        let process = Process()
        process.currentDirectoryURL = URL(fileURLWithPath: repoRoot, isDirectory: true)
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = [
            "uv",
            "run",
            "--project",
            "\(repoRoot)/services/mlx-worker-python",
            "python",
            "\(repoRoot)/services/mlx-worker-python/worker/control_plane_bridge.py",
            command.kind.rawValue,
            "--socket-path",
            command.socketPath,
            "--request-b64",
            command.requestData.base64EncodedString(),
        ]
        process.environment = mergedEnvironment()
        return process
    }

    private func mergedEnvironment() -> [String: String] {
        var merged = environment
        let pythonPathEntry = "\(repoRoot):\(repoRoot)/services/mlx-worker-python"
        if let existing = merged["PYTHONPATH"], !existing.isEmpty {
            merged["PYTHONPATH"] = "\(pythonPathEntry):\(existing)"
        } else {
            merged["PYTHONPATH"] = pythonPathEntry
        }
        merged["UV_CACHE_DIR"] = merged["UV_CACHE_DIR"] ?? "\(repoRoot)/.uv-cache"
        merged["PYTHONUNBUFFERED"] = "1"
        return merged
    }
}
