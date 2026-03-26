public protocol WorkerClient: Sendable {
    func canDispatchRequests() async -> Bool
}

public struct NullWorkerClient: WorkerClient {
    public init() {}

    public func canDispatchRequests() async -> Bool {
        false
    }
}
