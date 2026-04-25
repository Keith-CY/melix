import MelixWorkerProtocol

func recordPythonWorkerStreamOwnershipMetrics(
    from stats: Melix_Worker_V1_RuntimeStats,
    metricsStore: MetricsStore
) async {
    await metricsStore.set(
        pythonWorkerGenerationStreamOwnerModeCode(stats.generationStreamOwnerMode),
        forKey: "python_worker.generation_stream_owner_mode_code"
    )
    await metricsStore.set(
        stats.workerThreadInitLatencyMs,
        forKey: "python_worker.worker_thread_init_latency_ms"
    )
    await metricsStore.set(
        Double(stats.streamSyncFallbackCount),
        forKey: "python_worker.stream_sync_fallback_count"
    )
}

func pythonWorkerGenerationStreamOwnerModeCode(_ mode: String) -> Double {
    switch mode {
    case "executor_owned":
        return 1
    case "executor_owned_no_stream":
        return 2
    case "executor_owned_stream_init_failed":
        return 3
    default:
        return 0
    }
}
