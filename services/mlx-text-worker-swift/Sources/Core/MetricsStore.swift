import Foundation

final class MetricsStore: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [String: Int] = [
        "swift_text.bootstrap_ms": 0,
        "swift_text.handshake_ms": 0,
        "swift_text.runtime_stats_ms": 0,
        "swift_text.rpc_error_count": 0,
        "swift_text.unimplemented_rpc_count": 0,
    ]

    var counters: [String: Int] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    func increment(_ key: String, by amount: Int = 1) {
        lock.lock()
        storage[key, default: 0] += amount
        lock.unlock()
    }

    func recordMilliseconds(_ key: String, value: Int) {
        lock.lock()
        storage[key] = value
        lock.unlock()
    }
}
