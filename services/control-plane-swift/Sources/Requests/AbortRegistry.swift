public actor AbortRegistry {
    private var states: [String: Bool]

    public init() {
        self.states = [:]
    }

    public func begin(requestID: String) -> Bool {
        guard states[requestID] == nil else {
            return false
        }
        states[requestID] = false
        return true
    }

    public func finish(requestID: String) {
        states.removeValue(forKey: requestID)
    }

    public func contains(_ requestID: String) -> Bool {
        states[requestID] != nil
    }

    public func abort(_ requestID: String) -> Bool {
        guard states[requestID] != nil else {
            return false
        }
        states[requestID] = true
        return true
    }

    public func isAborted(_ requestID: String) -> Bool {
        states[requestID] ?? false
    }
}
