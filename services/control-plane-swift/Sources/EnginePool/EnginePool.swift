public actor EnginePool {
    private let workerClient: any WorkerClient

    public init(workerClient: any WorkerClient = NullWorkerClient()) {
        self.workerClient = workerClient
    }

    public func hasDispatchCapacity() async -> Bool {
        await workerClient.canDispatchRequests()
    }
}
