import Foundation

final class MetricsStore: @unchecked Sendable {
    private let lock = NSLock()
    private let exportPath: String?
    private var storage: [String: Int] = [
        "swift_text.spawn_to_bootstrap_ms": 0,
        "swift_text.bootstrap_ms": 0,
        "swift_text.registry_init_ms": 0,
        "swift_text.services_init_ms": 0,
        "swift_text.server_construct_ms": 0,
        "swift_text.handshake_ms": 0,
        "swift_text.load_model_ms": 0,
        "swift_text.unload_model_ms": 0,
        "swift_text.runtime_stats_ms": 0,
        "swift_text.prefill_ms": 0,
        "swift_text.prefill_prompt_tokens": 0,
        "swift_text.prefill_context_count": 0,
        "swift_text.prefill_guard_rejection_count": 0,
        "swift_text.prefill_context_limit_rejection_count": 0,
        "swift_text.prefill_memory_guard_rejection_count": 0,
        "swift_text.prefill_quadratic_guard_rejection_count": 0,
        "swift_text.prefill_guard_last_prompt_tokens": 0,
        "swift_text.prefill_guard_last_required_bytes": 0,
        "swift_text.prefill_guard_last_budget_bytes": 0,
        "swift_text.accelerated_prefill_gain_pct": 0,
        "swift_text.active_kv_quantization_ratio": 0,
        "swift_text.cache_l1_bytes": 0,
        "swift_text.cache_l2_bytes": 0,
        "swift_text.cache_block_count": 0,
        "swift_text.cache_prefix_count": 0,
        "swift_text.cache_pinned_prefix_count": 0,
        "swift_text.cache_snapshot_count": 0,
        "swift_text.cache_l1_hit_rate": 0,
        "swift_text.cache_l2_restore_hit_rate": 0,
        "swift_text.cache_block_reuse_ratio": 0,
        "swift_text.cache_quantized_bytes": 0,
        "swift_text.cache_compression_ratio": 0,
        "swift_text.cache_snapshot_save_ms": 0,
        "swift_text.cache_snapshot_restore_ms": 0,
        "swift_text.decode_ms": 0,
        "swift_text.decode_ttft_ms": 0,
        "swift_text.decode_tokens_per_second": 0,
        "swift_text.decode_stream_event_count": 0,
        "swift_text.speculative_acceptance_rate": 0,
        "swift_text.speculative_rollback_rate": 0,
        "swift_text.generate_ms": 0,
        "swift_text.ttft_ms": 0,
        "swift_text.tokens_per_second": 0,
        "swift_text.abort_ms": 0,
        "swift_text.stream_event_count": 0,
        "swift_text.memory_enforcement_disabled": 0,
        "swift_text.cache_initial_block_target": 0,
        "swift_text.peak_resident_bytes": 0,
        "swift_text.loaded_model_count": 0,
        "swift_text.rpc_error_count": 0,
        "swift_text.unimplemented_rpc_count": 0,
    ]

    init(exportPath: String? = nil) {
        self.exportPath = exportPath
    }

    var counters: [String: Int] {
        lock.lock()
        defer { lock.unlock() }
        return storage
    }

    func increment(_ key: String, by amount: Int = 1) {
        lock.lock()
        storage[key, default: 0] += amount
        let snapshot = storage
        lock.unlock()
        writeExportIfNeeded(snapshot)
    }

    func recordMilliseconds(_ key: String, value: Int) {
        set(key, value: value)
    }

    func set(_ key: String, value: Int) {
        lock.lock()
        storage[key] = value
        let snapshot = storage
        lock.unlock()
        writeExportIfNeeded(snapshot)
    }

    private func writeExportIfNeeded(_ snapshot: [String: Int]) {
        guard let exportPath, !exportPath.isEmpty else {
            return
        }

        let payload: [String: Any] = [
            "updated_at_unix_ms": Int(Date().timeIntervalSince1970 * 1000),
            "values": snapshot,
        ]

        guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]) else {
            return
        }

        let url = URL(fileURLWithPath: exportPath)
        try? FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try? data.write(to: url, options: [.atomic])
    }
}
