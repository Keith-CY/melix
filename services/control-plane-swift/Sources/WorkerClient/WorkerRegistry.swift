public actor WorkerRegistry {
    private let defaultTextClient: any WorkerRoutingClient
    private let pythonCompatibilityClient: (any WorkerRoutingClient)?

    public init(
        defaultTextClient: any WorkerRoutingClient,
        pythonCompatibilityClient: (any WorkerRoutingClient)? = nil
    ) {
        self.defaultTextClient = defaultTextClient
        self.pythonCompatibilityClient = pythonCompatibilityClient
    }

    public func route(forModelID modelID: String) -> WorkerRouteKind? {
        guard !modelID.isEmpty else {
            return nil
        }
        return .swiftText
    }

    public func client(forModelID modelID: String) -> (any WorkerRoutingClient)? {
        guard let route = route(forModelID: modelID) else {
            return nil
        }
        return client(for: route)
    }

    public func client(for route: WorkerRouteKind) -> (any WorkerRoutingClient)? {
        switch route {
        case .swiftText:
            return defaultTextClient
        case .pythonCompatibility:
            return pythonCompatibilityClient
        }
    }
}
