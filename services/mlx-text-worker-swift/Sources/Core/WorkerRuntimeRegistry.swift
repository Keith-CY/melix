import MelixWorkerProtocol

actor WorkerRuntimeRegistry {
    private let configuration: WorkerConfiguration
    private var loadedModelHandles: [String]
    private var activeRequests: UInt64
    private var draining: Bool

    init(configuration: WorkerConfiguration) {
        self.configuration = configuration
        self.loadedModelHandles = []
        self.activeRequests = 0
        self.draining = false
    }

    func capabilities() -> Melix_Worker_V1_RuntimeCapabilities {
        var capabilities = Melix_Worker_V1_RuntimeCapabilities()

        var cache = Melix_Worker_V1_CacheCapabilities()
        cache.supportsPrefixCache = true
        cache.supportsPagedCache = false
        cache.supportsDiskCache = false
        cache.kvQuantProfiles = ["q4"]
        cache.supportsBoundarySnapshots = false
        capabilities.cache = cache

        var execution = Melix_Worker_V1_ExecutionCapabilities()
        execution.supportsContinuousBatching = false
        execution.supportsSpeculativeDecoding = false
        capabilities.execution = execution

        var ext = Melix_Worker_V1_Capability()
        ext.name = "engine_family"
        ext.metadata = ["value": configuration.backendMode]
        capabilities.ext = [ext]

        return capabilities
    }

    func runtimeStats() -> Melix_Worker_V1_RuntimeStats {
        var stats = Melix_Worker_V1_RuntimeStats()
        stats.workerState = draining ? "draining" : "idle"
        stats.residentBytes = 0
        stats.activeRequests = activeRequests
        stats.activePrefills = 0
        stats.activeDecodes = 0
        stats.l1CacheBytes = 0
        stats.l2CacheBytes = 0
        stats.l1HitRate = 0
        stats.l2HitRate = 0
        return stats
    }

    func listLoadedModels() -> [String] {
        loadedModelHandles
    }

    func setDraining(_ draining: Bool) {
        self.draining = draining
    }
}
