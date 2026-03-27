public actor AbortRegistry {
    private var activeRequestID: String?

    public init() {}

    public func begin(requestID: String) -> Bool {
        guard activeRequestID == nil else {
            return false
        }
        activeRequestID = requestID
        return true
    }

    public func finish(requestID: String) {
        guard activeRequestID == requestID else {
            return
        }
        activeRequestID = nil
    }

    public func contains(_ requestID: String) -> Bool {
        activeRequestID == requestID
    }
}
