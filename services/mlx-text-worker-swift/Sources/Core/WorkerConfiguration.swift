import Foundation

package struct WorkerConfiguration: Sendable, Equatable {
    var workerID: String
    var socketPath: String
    var backendMode: String
    var runtimeVersion: String
    var metricsExportPath: String?
    var cacheRootPath: String
    var processMemoryBudgetBytes: UInt64
    var modelLoadHeadroomBytes: UInt64

    init(
        workerID: String = "swift-text-worker-001",
        socketPath: String = "/var/run/melix/swift-text-worker.sock",
        backendMode: String = "swift",
        runtimeVersion: String = "melix-swift-text-worker/dev",
        metricsExportPath: String? = nil,
        cacheRootPath: String = ".runtime/swift-text-worker-cache",
        processMemoryBudgetBytes: UInt64 = 0,
        modelLoadHeadroomBytes: UInt64 = 0
    ) {
        self.workerID = workerID
        self.socketPath = socketPath
        self.backendMode = backendMode
        self.runtimeVersion = runtimeVersion
        self.metricsExportPath = metricsExportPath
        self.cacheRootPath = cacheRootPath
        self.processMemoryBudgetBytes = processMemoryBudgetBytes
        self.modelLoadHeadroomBytes = modelLoadHeadroomBytes
    }

    package static func fromEnvironment(
        _ environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> WorkerConfiguration {
        WorkerConfiguration(
            workerID: environment["MELIX_SWIFT_TEXT_WORKER_ID"] ?? "swift-text-worker-001",
            socketPath: environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] ?? "/var/run/melix/swift-text-worker.sock",
            backendMode: environment["MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE"] ?? "swift",
            runtimeVersion: environment["MELIX_SWIFT_TEXT_WORKER_RUNTIME_VERSION"] ?? "melix-swift-text-worker/dev",
            metricsExportPath: environment["MELIX_SWIFT_TEXT_WORKER_METRICS_PATH"],
            cacheRootPath: environment["MELIX_SWIFT_TEXT_WORKER_CACHE_ROOT"] ?? ".runtime/swift-text-worker-cache",
            processMemoryBudgetBytes: positiveUInt64(
                from: environment["MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES"]
            ),
            modelLoadHeadroomBytes: positiveUInt64(
                from: environment["MELIX_SWIFT_TEXT_WORKER_MODEL_LOAD_HEADROOM_BYTES"]
            )
        )
    }

    private static func positiveUInt64(from rawValue: String?) -> UInt64 {
        guard let rawValue, let parsed = UInt64(rawValue), parsed > 0 else {
            return 0
        }
        return parsed
    }
}
