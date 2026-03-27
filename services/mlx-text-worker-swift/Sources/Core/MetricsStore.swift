import Foundation

final class MetricsStore: @unchecked Sendable {
    private let lock = NSLock()
    private var storage: [String: Int] = [
        "swift_text.bootstrap_ms": 0,
        "swift_text.handshake_ms": 0,
        "swift_text.load_model_ms": 0,
        "swift_text.unload_model_ms": 0,
        "swift_text.runtime_stats_ms": 0,
        "swift_text.peak_resident_bytes": 0,
        "swift_text.loaded_model_count": 0,
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
        set(key, value: value)
    }

    func set(_ key: String, value: Int) {
        lock.lock()
        storage[key] = value
        lock.unlock()
    }
}
