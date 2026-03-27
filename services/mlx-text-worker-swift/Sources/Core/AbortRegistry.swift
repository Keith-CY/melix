import Foundation

final class AbortRegistry: @unchecked Sendable {
    private let lock = NSLock()
    private var requestIDs: Set<String> = []

    func register(_ requestID: String) {
        lock.lock()
        requestIDs.insert(requestID)
        lock.unlock()
    }

    func remove(_ requestID: String) {
        lock.lock()
        requestIDs.remove(requestID)
        lock.unlock()
    }

    func abort(_ requestID: String) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        return requestIDs.remove(requestID) != nil
    }
}
