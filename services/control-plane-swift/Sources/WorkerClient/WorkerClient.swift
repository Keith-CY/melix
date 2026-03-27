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
