import Foundation

final class AbortHandle: @unchecked Sendable {
    private let lock = NSLock()
    private var aborted = false

    var isAborted: Bool {
        lock.lock()
        defer { lock.unlock() }
        return aborted
    }

    func markAborted() {
        lock.lock()
        aborted = true
        lock.unlock()
    }
}

final class AbortRegistry: @unchecked Sendable {
    private let lock = NSLock()
    private var handles: [String: AbortHandle] = [:]

    @discardableResult
    func register(_ requestID: String) -> AbortHandle {
        lock.lock()
        let handle = AbortHandle()
        handles[requestID] = handle
        lock.unlock()
        return handle
    }

    func remove(_ requestID: String) {
        lock.lock()
        handles.removeValue(forKey: requestID)
        lock.unlock()
    }

    func abort(_ requestID: String) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard let handle = handles.removeValue(forKey: requestID) else {
            return false
        }
        handle.markAborted()
        return true
    }

    func handle(for requestID: String) -> AbortHandle? {
        lock.lock()
        defer { lock.unlock() }
        return handles[requestID]
    }
}
