import Foundation

package struct WorkerConfiguration: Sendable, Equatable {
    var workerID: String
    var socketPath: String
    var backendMode: String
    var runtimeVersion: String
    var metricsExportPath: String?
    var cacheRootPath: String
    var memoryEnforcementDisabled: Bool
    var processMemoryBudgetBytes: UInt64
    var modelLoadHeadroomBytes: UInt64
    var prefillMemoryHeadroomBytes: UInt64
    var prefillQuadraticGuardTokenThreshold: UInt32
    var initialCacheBlocks: UInt32

    init(
        workerID: String = "swift-text-worker-001",
        socketPath: String = "/var/run/melix/swift-text-worker.sock",
        backendMode: String = "swift",
        runtimeVersion: String = "melix-swift-text-worker/dev",
        metricsExportPath: String? = nil,
        cacheRootPath: String = ".runtime/swift-text-worker-cache",
        memoryEnforcementDisabled: Bool = false,
        processMemoryBudgetBytes: UInt64 = 0,
        modelLoadHeadroomBytes: UInt64 = 0,
        prefillMemoryHeadroomBytes: UInt64 = 0,
        prefillQuadraticGuardTokenThreshold: UInt32 = 0,
        initialCacheBlocks: UInt32 = 0
    ) {
        self.workerID = workerID
        self.socketPath = socketPath
        self.backendMode = backendMode
        self.runtimeVersion = runtimeVersion
        self.metricsExportPath = metricsExportPath
        self.cacheRootPath = cacheRootPath
        self.memoryEnforcementDisabled = memoryEnforcementDisabled
        self.processMemoryBudgetBytes = processMemoryBudgetBytes
        self.modelLoadHeadroomBytes = modelLoadHeadroomBytes
        self.prefillMemoryHeadroomBytes = prefillMemoryHeadroomBytes
        self.prefillQuadraticGuardTokenThreshold = prefillQuadraticGuardTokenThreshold
        self.initialCacheBlocks = initialCacheBlocks
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
            memoryEnforcementDisabled: truthyBool(
                from: environment["MELIX_SWIFT_TEXT_WORKER_DISABLE_MEMORY_ENFORCEMENT"]
            ),
            processMemoryBudgetBytes: positiveUInt64(
                from: environment["MELIX_SWIFT_TEXT_WORKER_PROCESS_MEMORY_BUDGET_BYTES"]
            ),
            modelLoadHeadroomBytes: positiveUInt64(
                from: environment["MELIX_SWIFT_TEXT_WORKER_MODEL_LOAD_HEADROOM_BYTES"]
            ),
            prefillMemoryHeadroomBytes: positiveUInt64(
                from: environment["MELIX_SWIFT_TEXT_WORKER_PREFILL_MEMORY_HEADROOM_BYTES"]
            ),
            prefillQuadraticGuardTokenThreshold: positiveUInt32(
                from: environment["MELIX_SWIFT_TEXT_WORKER_PREFILL_QUADRATIC_GUARD_TOKEN_THRESHOLD"]
            ),
            initialCacheBlocks: positiveUInt32(
                from: environment["MELIX_SWIFT_TEXT_WORKER_INITIAL_CACHE_BLOCKS"]
            )
        )
    }

    var memoryEnforcementEnabled: Bool {
        !memoryEnforcementDisabled
    }

    private static func positiveUInt64(from rawValue: String?) -> UInt64 {
        guard let rawValue, let parsed = UInt64(rawValue), parsed > 0 else {
            return 0
        }
        return parsed
    }

    private static func positiveUInt32(from rawValue: String?) -> UInt32 {
        guard let rawValue, let parsed = UInt32(rawValue), parsed > 0 else {
            return 0
        }
        return parsed
    }

    private static func truthyBool(from rawValue: String?) -> Bool {
        guard let normalized = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() else {
            return false
        }
        switch normalized {
        case "1", "true", "yes", "on":
            return true
        default:
            return false
        }
    }
}
