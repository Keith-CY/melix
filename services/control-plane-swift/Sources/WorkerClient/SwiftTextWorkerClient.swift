import Foundation
import GRPCCore
import GRPCNIOTransportHTTP2Posix

import MelixWorkerProtocol

public protocol SwiftTextWorkerRPCRunning: Sendable {
    func handshake(
        socketPath: String,
        request: Melix_Worker_V1_HandshakeRequest
    ) async throws -> Melix_Worker_V1_HandshakeResponse

    func loadModel(
        socketPath: String,
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse

    func runtimeStats(
        socketPath: String,
        request: Melix_Worker_V1_GetRuntimeStatsRequest
    ) async throws -> Melix_Worker_V1_GetRuntimeStatsResponse

    func cacheStats(
        socketPath: String,
        request: Melix_Worker_V1_GetCacheStatsRequest
    ) async throws -> Melix_Worker_V1_GetCacheStatsResponse

    func generate(
        socketPath: String,
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>

    func prefill(
        socketPath: String,
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse

    func decode(
        socketPath: String,
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>

    func abort(
        socketPath: String,
        request: Melix_Worker_V1_AbortRequest
    ) async throws -> Melix_Worker_V1_AbortResponse
}

public struct SwiftTextWorkerClient:
    WorkerRoutingClient,
    PhaseAwareWorkerClientProtocol,
    CacheIntrospectingWorkerClientProtocol,
    Sendable
{
    private let socketPath: String
    private let runner: any SwiftTextWorkerRPCRunning

    public init(socketPath: String, runner: any SwiftTextWorkerRPCRunning) {
        self.socketPath = socketPath
        self.runner = runner
    }

    public init(socketPath: String) {
        self.init(socketPath: socketPath, runner: GRPCSwiftTextWorkerRunner())
    }

    public func canDispatchRequests() async -> Bool {
        var request = Melix_Worker_V1_HandshakeRequest()
        request.protocolVersion = "melix.worker.v1"
        request.workerID = "control-plane"
        request.controlplaneInstanceID = "melix-control-plane"

        do {
            _ = try await runner.handshake(socketPath: socketPath, request: request)
            return true
        } catch {
            return false
        }
    }

    public func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        try await runner.loadModel(socketPath: socketPath, request: request)
    }

    public func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        try await runner.runtimeStats(
            socketPath: socketPath,
            request: Melix_Worker_V1_GetRuntimeStatsRequest()
        )
    }

    public func cacheStats() async throws -> Melix_Worker_V1_GetCacheStatsResponse {
        try await runner.cacheStats(
            socketPath: socketPath,
            request: Melix_Worker_V1_GetCacheStatsRequest()
        )
    }

    public func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        try await runner.generate(socketPath: socketPath, request: request)
    }

    public func prefill(
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse {
        try await runner.prefill(socketPath: socketPath, request: request)
    }

    public func decode(
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        try await runner.decode(socketPath: socketPath, request: request)
    }

    public func abort(requestID: String) async throws -> Bool {
        var request = Melix_Worker_V1_AbortRequest()
        request.requestID = requestID

        let response = try await runner.abort(socketPath: socketPath, request: request)
        return response.ok && response.found
    }
}

public struct GRPCSwiftTextWorkerRunner: SwiftTextWorkerRPCRunning, Sendable {
    public init() {}

    public func handshake(
        socketPath: String,
        request: Melix_Worker_V1_HandshakeRequest
    ) async throws -> Melix_Worker_V1_HandshakeResponse {
        try await withRPCClients(socketPath: socketPath) { runtimeClient, _, _ in
            try await runtimeClient.handshake(request)
        }
    }

    public func loadModel(
        socketPath: String,
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        try await withRPCClients(socketPath: socketPath) { runtimeClient, _, _ in
            try await runtimeClient.loadModel(request)
        }
    }

    public func runtimeStats(
        socketPath: String,
        request: Melix_Worker_V1_GetRuntimeStatsRequest
    ) async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        try await withRPCClients(socketPath: socketPath) { runtimeClient, _, _ in
            try await runtimeClient.getRuntimeStats(request)
        }
    }

    public func cacheStats(
        socketPath: String,
        request: Melix_Worker_V1_GetCacheStatsRequest
    ) async throws -> Melix_Worker_V1_GetCacheStatsResponse {
        try await withRPCClients(socketPath: socketPath) { _, _, cacheClient in
            try await cacheClient.getCacheStats(request)
        }
    }

    public func generate(
        socketPath: String,
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _ in
                        try await inferenceClient.generate(request) { response in
                            for try await event in response.messages {
                                continuation.yield(event)
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: WorkerClientError.unavailable)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    public func prefill(
        socketPath: String,
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse {
        try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _ in
            try await inferenceClient.prefill(request)
        }
    }

    public func decode(
        socketPath: String,
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _ in
                        try await inferenceClient.decode(request) { response in
                            for try await event in response.messages {
                                continuation.yield(event)
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: WorkerClientError.unavailable)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    public func abort(
        socketPath: String,
        request: Melix_Worker_V1_AbortRequest
    ) async throws -> Melix_Worker_V1_AbortResponse {
        try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _ in
            try await inferenceClient.abort(request)
        }
    }

    private func withRPCClients<Result: Sendable>(
        socketPath: String,
        operation: @Sendable @escaping (
            Melix_Worker_V1_RuntimeService.Client<HTTP2ClientTransport.Posix>,
            Melix_Worker_V1_InferenceService.Client<HTTP2ClientTransport.Posix>,
            Melix_Worker_V1_CacheService.Client<HTTP2ClientTransport.Posix>
        ) async throws -> Result
    ) async throws -> Result {
        do {
            return try await withGRPCClient(
                transport: .http2NIOPosix(
                    target: .unixDomainSocket(path: socketPath),
                    transportSecurity: .plaintext
                )
            ) { client in
                let runtimeClient = Melix_Worker_V1_RuntimeService.Client(wrapping: client)
                let inferenceClient = Melix_Worker_V1_InferenceService.Client(wrapping: client)
                let cacheClient = Melix_Worker_V1_CacheService.Client(wrapping: client)
                return try await operation(runtimeClient, inferenceClient, cacheClient)
            }
        } catch {
            throw WorkerClientError.unavailable
        }
    }
}
