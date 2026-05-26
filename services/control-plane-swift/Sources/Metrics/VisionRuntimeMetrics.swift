import MelixWorkerProtocol

func visionMultimodalDecodeModeMetricValue(_ mode: String) -> Double {
    switch mode {
    case "baseline":
        return 0
    case "single_stream":
        return 1
    case "image_cache_reuse":
        return 2
    case "native_quantized":
        return 3
    case "fallback":
        return 4
    case "mixed":
        return 5
    case "text_only_step":
        return 6
    case "text_only_batch_generator":
        return 7
    case "":
        return 0
    default:
        return -1
    }
}

func visionMultimodalFallbackReasonMetricValue(_ reason: String) -> Double {
    switch reason {
    case "", "not_reported":
        return 0
    case "no_media":
        return 1
    case "text_backed_no_vision_weights":
        return 2
    case "unsupported_family":
        return 3
    case "video_fast_path_unimplemented":
        return 4
    case "mixed":
        return 5
    case "text_only_batch_generator_not_enabled":
        return 6
    case "media_inputs_present":
        return 7
    case "isolated_detokenizer_unavailable":
        return 8
    case "non_greedy_sampling":
        return 9
    default:
        return -1
    }
}

func visionMultimodalDecodeSyncModeMetricValue(_ mode: String) -> Double {
    switch mode {
    case "baseline", "":
        return 0
    case "executor_stream":
        return 1
    case "mixed":
        return 2
    case "executor_step":
        return 3
    case "executor_batch_generator":
        return 4
    default:
        return -1
    }
}

func recordPythonVLMRuntimeProbeMetrics(
    from stats: Melix_Worker_V1_RuntimeStats,
    metricsStore: MetricsStore
) async {
    let decodeMode = stats.lastMultimodalDecodeMode
    let fallbackReason = stats.lastMultimodalFallbackReason
    let syncMode = stats.lastMultimodalDecodeSyncMode
    await metricsStore.set(
        visionMultimodalDecodeModeMetricValue(decodeMode),
        forKey: "vision.multimodal_decode_mode_code"
    )
    await metricsStore.set(
        visionMultimodalFallbackReasonMetricValue(fallbackReason),
        forKey: "vision.multimodal_fallback_reason_code"
    )
    await metricsStore.set(
        visionMultimodalDecodeSyncModeMetricValue(syncMode),
        forKey: "vision.multimodal_decode_sync_mode_code"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorSubmittedRequestCount),
        forKey: "vision.text_batch_generator.submitted_request_count"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorCompletedRequestCount),
        forKey: "vision.text_batch_generator.completed_request_count"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorStepCount),
        forKey: "vision.text_batch_generator.step_count"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorGeneratedTokenCount),
        forKey: "vision.text_batch_generator.generated_token_count"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorPeakActiveBatchSize),
        forKey: "vision.text_batch_generator.peak_active_batch_size"
    )
    await metricsStore.set(
        stats.textBatchGeneratorQueueWaitMsTotal,
        forKey: "vision.text_batch_generator.queue_wait_ms_total"
    )
    await metricsStore.set(
        stats.textBatchGeneratorInsertMsTotal,
        forKey: "vision.text_batch_generator.insert_ms_total"
    )
    await metricsStore.set(
        stats.textBatchGeneratorExecutorStepMsTotal,
        forKey: "vision.text_batch_generator.executor_step_ms_total"
    )
    await metricsStore.set(
        stats.textBatchGeneratorNextMsTotal,
        forKey: "vision.text_batch_generator.next_ms_total"
    )
    await metricsStore.set(
        stats.textBatchGeneratorEmitMsTotal,
        forKey: "vision.text_batch_generator.emit_ms_total"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorActiveBatchSize),
        forKey: "vision.text_batch_generator.active_batch_size"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorGeneratedResponseCount),
        forKey: "vision.text_batch_generator.generated_response_count"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorFailedRequestCount),
        forKey: "vision.text_batch_generator.failed_request_count"
    )
    await metricsStore.set(
        stats.textBatchGeneratorPrepareMsTotal,
        forKey: "vision.text_batch_generator.prepare_ms_total"
    )
    await metricsStore.set(
        stats.textBatchGeneratorFirstResponseMsTotal,
        forKey: "vision.text_batch_generator.first_response_ms_total"
    )
    await metricsStore.set(
        stats.textBatchGeneratorFirstVisibleMsTotal,
        forKey: "vision.text_batch_generator.first_visible_ms_total"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorFirstVisibleTokenIndexTotal),
        forKey: "vision.text_batch_generator.first_visible_token_index_total"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorFirstEmptySegmentCount),
        forKey: "vision.text_batch_generator.first_empty_segment_count"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorSpeculativeCycleCountTotal),
        forKey: "vision.text_batch_generator.speculative_cycle_count_total"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorSpeculativeAcceptedCountTotal),
        forKey: "vision.text_batch_generator.speculative_accepted_count_total"
    )
    await metricsStore.set(
        Double(stats.textBatchGeneratorSpeculativeRejectedCountTotal),
        forKey: "vision.text_batch_generator.speculative_rejected_count_total"
    )
    await metricsStore.set(
        stats.textBatchGeneratorSpeculativeBackboneMsTotal,
        forKey: "vision.text_batch_generator.speculative_backbone_ms_total"
    )
    await metricsStore.set(
        stats.textBatchGeneratorSpeculativeMtpHeadMsTotal,
        forKey: "vision.text_batch_generator.speculative_mtp_head_ms_total"
    )
    await metricsStore.set(
        stats.textBatchGeneratorSpeculativeSampleMsTotal,
        forKey: "vision.text_batch_generator.speculative_sample_ms_total"
    )
    await metricsStore.set(
        stats.textBatchGeneratorSpeculativeCacheOpsMsTotal,
        forKey: "vision.text_batch_generator.speculative_cache_ops_ms_total"
    )
}
