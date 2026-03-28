import Foundation
import MelixWorkerProtocol

public enum WorkerClientError: Error, Equatable {
    case unavailable
}

public protocol WorkerClient: Sendable {
    func canDispatchRequests() async -> Bool
    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>
    func abort(requestID: String) async throws -> Bool
}

public protocol PhaseAwareWorkerClientProtocol: WorkerClient {
    func prefill(
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse

    func decode(
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>
}

public protocol CacheIntrospectingWorkerClientProtocol: WorkerClient {
    func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse
    func cacheStats() async throws -> Melix_Worker_V1_GetCacheStatsResponse
}

public protocol WorkerRoutingClient: WorkerClient {
    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse
}

public struct NullWorkerClient: WorkerClient {
    public init() {}

    public func canDispatchRequests() async -> Bool {
        false
    }

    public func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        throw WorkerClientError.unavailable
    }

    public func abort(requestID: String) async throws -> Bool {
        false
    }
}
