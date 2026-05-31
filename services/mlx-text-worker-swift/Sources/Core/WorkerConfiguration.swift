import Foundation

package struct WorkerConfiguration: Sendable, Equatable {
    private static let runtimeCacheFingerprintSchemaVersion = "cache-v1"
    static let defaultDecodeBatchPendingWindowNanos: UInt64 = 2_000_000
    static let defaultDecodeBatchCohortPendingWindowNanos: UInt64 = 2_000_000_000

    var workerID: String
    var socketPath: String
    var backendMode: String
    var runtimeVersion: String
    var runtimeCacheFingerprint: String
    var metricsExportPath: String?
    var cacheRootPath: String
    var memoryEnforcementDisabled: Bool
    var processMemoryBudgetBytes: UInt64
    var modelLoadHeadroomBytes: UInt64
    var prefillMemoryHeadroomBytes: UInt64
    var prefillQuadraticGuardTokenThreshold: UInt32
    var initialCacheBlocks: UInt32
    var decodeBatchPendingWindowNanos: UInt64
    var decodeBatchCohortPendingWindowNanos: UInt64
    var turboQuantCandidateProbeEnabled: Bool

    init(
        workerID: String = "swift-text-worker-001",
        socketPath: String = "/var/run/melix/swift-text-worker.sock",
        backendMode: String = "swift",
        runtimeVersion: String = "melix-swift-text-worker/dev",
        runtimeCacheFingerprint: String? = nil,
        metricsExportPath: String? = nil,
        cacheRootPath: String = ".runtime/swift-text-worker-cache",
        memoryEnforcementDisabled: Bool = false,
        processMemoryBudgetBytes: UInt64 = 0,
        modelLoadHeadroomBytes: UInt64 = 0,
        prefillMemoryHeadroomBytes: UInt64 = 0,
        prefillQuadraticGuardTokenThreshold: UInt32 = 0,
        initialCacheBlocks: UInt32 = 0,
        decodeBatchPendingWindowNanos: UInt64 = WorkerConfiguration.defaultDecodeBatchPendingWindowNanos,
        decodeBatchCohortPendingWindowNanos: UInt64 = WorkerConfiguration.defaultDecodeBatchCohortPendingWindowNanos,
        turboQuantCandidateProbeEnabled: Bool = false
    ) {
        self.workerID = workerID
        self.socketPath = socketPath
        self.backendMode = backendMode
        self.runtimeVersion = runtimeVersion
        self.runtimeCacheFingerprint = runtimeCacheFingerprint ?? WorkerConfiguration.makeRuntimeCacheFingerprint(
            backendMode: backendMode,
            runtimeVersion: runtimeVersion
        )
        self.metricsExportPath = metricsExportPath
        self.cacheRootPath = cacheRootPath
        self.memoryEnforcementDisabled = memoryEnforcementDisabled
        self.processMemoryBudgetBytes = processMemoryBudgetBytes
        self.modelLoadHeadroomBytes = modelLoadHeadroomBytes
        self.prefillMemoryHeadroomBytes = prefillMemoryHeadroomBytes
        self.prefillQuadraticGuardTokenThreshold = prefillQuadraticGuardTokenThreshold
        self.initialCacheBlocks = initialCacheBlocks
        self.decodeBatchPendingWindowNanos = decodeBatchPendingWindowNanos
        self.decodeBatchCohortPendingWindowNanos = decodeBatchCohortPendingWindowNanos
        self.turboQuantCandidateProbeEnabled = turboQuantCandidateProbeEnabled
    }

    package static func fromEnvironment(
        _ environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> WorkerConfiguration {
        let backendMode = environment["MELIX_SWIFT_TEXT_WORKER_BACKEND_MODE"] ?? "swift"
        let runtimeVersion = environment["MELIX_SWIFT_TEXT_WORKER_RUNTIME_VERSION"] ?? "melix-swift-text-worker/dev"
        return WorkerConfiguration(
            workerID: environment["MELIX_SWIFT_TEXT_WORKER_ID"] ?? "swift-text-worker-001",
            socketPath: environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"] ?? "/var/run/melix/swift-text-worker.sock",
            backendMode: backendMode,
            runtimeVersion: runtimeVersion,
            runtimeCacheFingerprint: runtimeCacheFingerprint(
                environmentOverride: environment["MELIX_SWIFT_TEXT_WORKER_RUNTIME_CACHE_FINGERPRINT"],
                backendMode: backendMode,
                runtimeVersion: runtimeVersion
            ),
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
            ),
            decodeBatchPendingWindowNanos: millisecondsToNanoseconds(
                from: environment["MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_PENDING_WINDOW_MS"],
                fallback: defaultDecodeBatchPendingWindowNanos
            ),
            decodeBatchCohortPendingWindowNanos: millisecondsToNanoseconds(
                from: environment["MELIX_SWIFT_TEXT_WORKER_DECODE_BATCH_COHORT_PENDING_WINDOW_MS"],
                fallback: defaultDecodeBatchCohortPendingWindowNanos,
                maxMilliseconds: 10_000
            ),
            turboQuantCandidateProbeEnabled: truthyBool(
                from: environment["MELIX_SWIFT_TURBOQUANT_CANDIDATE_PROBE"]
            )
        )
    }

    var memoryEnforcementEnabled: Bool {
        !memoryEnforcementDisabled
    }

    private static func runtimeCacheFingerprint(
        environmentOverride: String?,
        backendMode: String,
        runtimeVersion: String
    ) -> String {
        let override = environmentOverride?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !override.isEmpty {
            return override
        }
        return makeRuntimeCacheFingerprint(backendMode: backendMode, runtimeVersion: runtimeVersion)
    }

    private static func makeRuntimeCacheFingerprint(
        backendMode: String,
        runtimeVersion: String
    ) -> String {
        let source = [
            "swift-text-worker",
            backendMode,
            runtimeVersion,
            runtimeCacheFingerprintSchemaVersion,
        ].joined(separator: "\n")
        var hash: UInt64 = 0xcbf2_9ce4_8422_2325
        for byte in source.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x0000_0100_0000_01b3
        }
        return String(format: "%016llx", hash)
    }

    private static func positiveUInt64(from rawValue: String?) -> UInt64 {
        guard let rawValue, let parsed = UInt64(rawValue), parsed > 0 else {
            return 0
        }
        return parsed
    }

    private static func millisecondsToNanoseconds(
        from rawValue: String?,
        fallback: UInt64,
        maxMilliseconds: UInt64 = 1_000
    ) -> UInt64 {
        guard let rawValue, let parsed = UInt64(rawValue), parsed > 0 else {
            return fallback
        }
        let clamped = min(parsed, maxMilliseconds)
        return clamped * 1_000_000
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
