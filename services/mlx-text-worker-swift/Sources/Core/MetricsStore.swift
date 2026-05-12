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
        "swift_text.prefill_chunk_count": 0,
        "swift_text.prefill_chunk_target_tokens": 0,
        "swift_text.prefill_last_chunk_tokens": 0,
        "swift_text.prefill_context_count": 0,
        "swift_text.prefill_guard_rejection_count": 0,
        "swift_text.prefill_context_limit_rejection_count": 0,
        "swift_text.prefill_memory_guard_rejection_count": 0,
        "swift_text.prefill_quadratic_guard_rejection_count": 0,
        "swift_text.prefill_guard_last_prompt_tokens": 0,
        "swift_text.prefill_guard_last_required_bytes": 0,
        "swift_text.prefill_guard_last_budget_bytes": 0,
        "swift_text.accelerated_prefill_gain_pct": 0,
        "swift_text.sparse_prefill_accepted_skip_count": 0,
        "swift_text.sparse_prefill_rejected_opportunity_count": 0,
        "swift_text.sparse_prefill_protected_region_count": 0,
        "swift_text.active_kv_quantization_ratio": 0,
        "swift_text.active_kv_backend_code": 0,
        "swift_text.active_kv_kernel_path_code": 0,
        "swift_text.active_kv_runtime_route_code": 0,
        "swift_text.active_kv_runtime_block_reason_code": 0,
        "swift_text.active_kv_prefill_quantize_us": 0,
        "swift_text.active_kv_decode_model_total_us": 0,
        "swift_text.active_kv_decode_model_call_count": 0,
        "swift_text.active_kv_decode_model_avg_us": 0,
        "swift_text.active_kv_decode_token_eval_total_us": 0,
        "swift_text.active_kv_decode_token_eval_call_count": 0,
        "swift_text.active_kv_decode_token_eval_avg_us": 0,
        "swift_text.active_kv_decode_model_eval_sync_total_us": 0,
        "swift_text.active_kv_decode_model_eval_sync_call_count": 0,
        "swift_text.active_kv_decode_model_eval_sync_avg_us": 0,
        "swift_text.active_kv_decode_sample_total_us": 0,
        "swift_text.active_kv_decode_sample_call_count": 0,
        "swift_text.active_kv_decode_sample_avg_us": 0,
        "swift_text.active_kv_decode_token_id_total_us": 0,
        "swift_text.active_kv_decode_token_id_call_count": 0,
        "swift_text.active_kv_decode_token_id_avg_us": 0,
        "swift_text.active_kv_decode_detokenize_total_us": 0,
        "swift_text.active_kv_decode_detokenize_call_count": 0,
        "swift_text.active_kv_decode_detokenize_avg_us": 0,
        "swift_text.active_kv_decode_stream_yield_total_us": 0,
        "swift_text.active_kv_decode_stream_yield_call_count": 0,
        "swift_text.active_kv_decode_stream_yield_avg_us": 0,
        "swift_text.active_kv_decode_summary_total_us": 0,
        "swift_text.active_kv_decode_summary_call_count": 0,
        "swift_text.active_kv_decode_summary_avg_us": 0,
        "swift_text.active_kv_turboquant_candidate_total_us": 0,
        "swift_text.active_kv_turboquant_candidate_call_count": 0,
        "swift_text.active_kv_turboquant_candidate_avg_us": 0,
        "swift_text.active_kv_decode_quantize_total_us": 0,
        "swift_text.active_kv_decode_quantize_avg_us": 0,
        "swift_text.active_kv_decode_loop_total_us": 0,
        "swift_text.active_kv_decode_token_count": 0,
        "swift_text.active_kv_fused_attention_total_us": 0,
        "swift_text.active_kv_fused_attention_call_count": 0,
        "swift_text.active_kv_fused_attention_avg_us": 0,
        "swift_text.active_kv_fused_attention_route_total_us": 0,
        "swift_text.active_kv_fused_attention_route_avg_us": 0,
        "swift_text.active_kv_cache_update_total_us": 0,
        "swift_text.active_kv_cache_update_call_count": 0,
        "swift_text.active_kv_cache_update_avg_us": 0,
        "swift_text.active_kv_cache_expand_total_us": 0,
        "swift_text.active_kv_cache_quantize_total_us": 0,
        "swift_text.active_kv_cache_append_total_us": 0,
        "swift_text.active_kv_cache_materialize_total_us": 0,
        "swift_text.active_kv_cache_materialize_call_count": 0,
        "swift_text.active_kv_cache_materialize_avg_us": 0,
        "swift_text.active_kv_estimated_fp16_bytes": 0,
        "swift_text.active_kv_estimated_quantized_bytes": 0,
        "swift_text.active_kv_estimated_memory_savings_pct": 0,
        "swift_text.active_kv_fallback_count": 0,
        "swift_text.active_kv_candidate_dispatch_code": 0,
        "swift_text.active_kv_candidate_eligibility_check_count": 0,
        "swift_text.cache_l1_bytes": 0,
        "swift_text.cache_l2_bytes": 0,
        "swift_text.cache_block_count": 0,
        "swift_text.cache_prefix_count": 0,
        "swift_text.cache_pinned_prefix_count": 0,
        "swift_text.cache_snapshot_count": 0,
        "swift_text.cache_l1_hit_rate": 0,
        "swift_text.cache_l2_hit_rate": 0,
        "swift_text.cache_l2_restore_hit_rate": 0,
        "swift_text.cache_l2_writeback_queue_depth": 0,
        "swift_text.cache_l2_restore_queue_depth": 0,
        "swift_text.cache_l2_writeback_count": 0,
        "swift_text.cache_active_mode": 1,
        "swift_text.cache_rotating_mode_active": 0,
        "swift_text.cache_hybrid_mode_active": 0,
        "swift_text.cache_block_reuse_ratio": 0,
        "swift_text.cache_exact_hit_count": 0,
        "swift_text.cache_partial_hit_count": 0,
        "swift_text.cache_fallback_count": 0,
        "swift_text.cache_reconstruction_failure_count": 0,
        "swift_text.cache_quantized_bytes": 0,
        "swift_text.cache_compression_ratio": 0,
        "swift_text.cache_snapshot_save_ms": 0,
        "swift_text.cache_snapshot_restore_ms": 0,
        "swift_text.runtime_cache_fingerprint_code": 0,
        "swift_text.cache_namespace_mismatch_count": 0,
        "swift_text.active_memory_bytes": 0,
        "swift_text.max_working_set_bytes": 0,
        "swift_text.effective_cache_budget_bytes": 0,
        "swift_text.decode_ms": 0,
        "swift_text.decode_ttft_ms": 0,
        "swift_text.decode_tokens_per_second": 0,
        "swift_text.decode_stream_event_count": 0,
        "swift_text.speculative_acceptance_rate": 0,
        "swift_text.speculative_rollback_rate": 0,
        "swift_text.speculative_accepted_tokens": 0,
        "swift_text.speculative_rejected_tokens": 0,
        "swift_text.speculative_fallback_count": 0,
        "swift_text.speculative_draft_model_configured": 0,
        "swift_text.speculative_num_draft_tokens": 0,
        "swift_text.speculative_draft_propose_ms": 0,
        "swift_text.speculative_target_verify_ms": 0,
        "swift_text.dflash_enabled": 0,
        "swift_text.dflash_block_size": 0,
        "swift_text.dflash_rollback_count": 0,
        "swift_text.dflash_target_hidden_layers": 0,
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
