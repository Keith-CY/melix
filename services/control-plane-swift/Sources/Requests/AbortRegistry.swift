public actor AbortRegistry {
    private var activeRequestID: String?
    private var abortedRequestID: String?

    public init() {}

    public func begin(requestID: String) -> Bool {
        guard activeRequestID == nil else {
            return false
        }
        activeRequestID = requestID
        abortedRequestID = nil
        return true
    }

    public func finish(requestID: String) {
        guard activeRequestID == requestID else {
            return
        }
        activeRequestID = nil
        abortedRequestID = nil
    }

    public func contains(_ requestID: String) -> Bool {
        activeRequestID == requestID
    }

    public func abort(_ requestID: String) -> Bool {
        guard activeRequestID == requestID else {
            return false
        }
        abortedRequestID = requestID
        return true
    }

    public func isAborted(_ requestID: String) -> Bool {
        abortedRequestID == requestID
    }
}
