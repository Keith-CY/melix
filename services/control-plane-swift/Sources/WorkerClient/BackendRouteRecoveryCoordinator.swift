import Foundation
import MelixWorkerProtocol

struct BackendIdentityRecoveryDiagnosticsSnapshot: Codable, Equatable, Sendable {
    let mismatchCount: UInt64
    let retryAllowedCount: UInt64
    let retrySuppressedCount: UInt64
    let retryExhaustedCount: UInt64
    let lastMismatch: BackendIdentityMismatchDiagnosticReceipt?

    enum CodingKeys: String, CodingKey {
        case mismatchCount = "mismatch_count"
        case retryAllowedCount = "retry_allowed_count"
        case retrySuppressedCount = "retry_suppressed_count"
        case retryExhaustedCount = "retry_exhausted_count"
        case lastMismatch = "last_mismatch"
    }
}

struct BackendIdentityMismatchDiagnosticReceipt: Codable, Equatable, Sendable {
    let requestedModelID: String
    let loadedModelID: String
    let requestedAdapterID: String
    let loadedAdapterID: String
    let requestedRouteGeneration: UInt64
    let loadedRouteGeneration: UInt64
    let observedAtUnixMs: Int64
    let mismatchReason: String
    let requestedWorkerInstanceID: String
    let loadedWorkerInstanceID: String

    enum CodingKeys: String, CodingKey {
        case requestedModelID = "requested_model_id"
        case loadedModelID = "loaded_model_id"
        case requestedAdapterID = "requested_adapter_id"
        case loadedAdapterID = "loaded_adapter_id"
        case requestedRouteGeneration = "requested_route_generation"
        case loadedRouteGeneration = "loaded_route_generation"
        case observedAtUnixMs = "observed_at_unix_ms"
        case mismatchReason = "mismatch_reason"
        case requestedWorkerInstanceID = "requested_worker_instance_id"
        case loadedWorkerInstanceID = "loaded_worker_instance_id"
    }
}

actor BackendIdentityRecoveryDiagnostics {
    static let shared = BackendIdentityRecoveryDiagnostics()

    private var mismatchCount: UInt64 = 0
    private var retryAllowedCount: UInt64 = 0
    private var retrySuppressedCount: UInt64 = 0
    private var retryExhaustedCount: UInt64 = 0
    private var lastMismatch: BackendIdentityMismatchDiagnosticReceipt?

    func recordMismatch(_ status: Melix_Worker_V1_ErrorStatus) {
        mismatchCount = incremented(mismatchCount)
        guard status.hasBackendIdentityMismatch else {
            return
        }
        let receipt = status.backendIdentityMismatch
        lastMismatch = BackendIdentityMismatchDiagnosticReceipt(
            requestedModelID: diagnosticBackendIdentifier(receipt.requestedModelID),
            loadedModelID: diagnosticBackendIdentifier(receipt.loadedModelID),
            requestedAdapterID: diagnosticBackendIdentifier(receipt.requestedAdapterID),
            loadedAdapterID: diagnosticBackendIdentifier(receipt.loadedAdapterID),
            requestedRouteGeneration: receipt.requestedRouteGeneration,
            loadedRouteGeneration: receipt.loadedRouteGeneration,
            observedAtUnixMs: receipt.observedAtUnixMs,
            mismatchReason: String(receipt.mismatchReason.prefix(128)),
            requestedWorkerInstanceID: diagnosticBackendIdentifier(receipt.requestedWorkerInstanceID),
            loadedWorkerInstanceID: diagnosticBackendIdentifier(receipt.loadedWorkerInstanceID)
        )
    }

    func recordRetryAllowed() {
        retryAllowedCount = incremented(retryAllowedCount)
    }

    func recordRetrySuppressed() {
        retrySuppressedCount = incremented(retrySuppressedCount)
    }

    func recordRetryExhausted() {
        retryExhaustedCount = incremented(retryExhaustedCount)
    }

    func snapshot() -> BackendIdentityRecoveryDiagnosticsSnapshot {
        BackendIdentityRecoveryDiagnosticsSnapshot(
            mismatchCount: mismatchCount,
            retryAllowedCount: retryAllowedCount,
            retrySuppressedCount: retrySuppressedCount,
            retryExhaustedCount: retryExhaustedCount,
            lastMismatch: lastMismatch
        )
    }

    func resetForTesting() {
        mismatchCount = 0
        retryAllowedCount = 0
        retrySuppressedCount = 0
        retryExhaustedCount = 0
        lastMismatch = nil
    }

    private func incremented(_ value: UInt64) -> UInt64 {
        value == UInt64.max ? UInt64.max : value + 1
    }
}

actor BackendRouteRecoveryCoordinator {
    typealias BeforeReload = @Sendable (String, WorkerRouteKind) async throws -> Void

    static let shared = BackendRouteRecoveryCoordinator()

    private struct Key: Hashable, Sendable {
        let catalogID: ObjectIdentifier
        let modelID: String
        let routeKind: String
        let failedGeneration: UInt64
    }

    private struct Entry: Sendable {
        let id: UUID
        let task: Task<ModelCatalog.BackendRouteBinding, Error>
    }

    private let reloadPreparation: BeforeReload
    private var inFlight: [Key: Entry] = [:]

    init(
        beforeReload: @escaping BeforeReload = { _, _ in }
    ) {
        self.reloadPreparation = beforeReload
    }

    func recover(
        catalog: ModelCatalog,
        failedBinding: ModelCatalog.BackendRouteBinding,
        onCoalesced: @escaping @Sendable () async -> Void = {},
        operation: @escaping @Sendable () async throws -> ModelCatalog.BackendRouteBinding
    ) async throws -> ModelCatalog.BackendRouteBinding {
        let key = Key(
            catalogID: ObjectIdentifier(catalog),
            modelID: failedBinding.modelID,
            routeKind: failedBinding.routeKind.rawValue,
            failedGeneration: failedBinding.generation
        )
        if let existing = inFlight[key] {
            await onCoalesced()
            return try await existing.task.value
        }

        let task = Task {
            return try await operation()
        }
        let entry = Entry(id: UUID(), task: task)
        inFlight[key] = entry
        defer {
            if inFlight[key]?.id == entry.id {
                inFlight.removeValue(forKey: key)
            }
        }
        return try await task.value
    }

    func prepareForReload(modelID: String, routeKind: WorkerRouteKind) async throws {
        try await reloadPreparation(modelID, routeKind)
    }
}

enum BackendRouteRecovery {
    enum StreamEventDisposition {
        case output
        case terminal
        case error(Melix_Worker_V1_ErrorStatus)
    }

    static func performReplaySafeUnary<Response>(
        binding: ModelCatalog.BackendRouteBinding,
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry,
        metricsStore: MetricsStore,
        mode: BackendRouteRecoveryMode = .identityAndTransport,
        dispatch: @escaping (ModelCatalog.BackendRouteBinding) async throws -> Response,
        errorStatus: (Response) -> Melix_Worker_V1_ErrorStatus
    ) async throws -> Response {
        let diagnostics = BackendIdentityRecoveryDiagnostics.shared
        do {
            let response = try await dispatch(binding)
            let status = errorStatus(response)
            guard BackendRouteRecoveryClassifier.shouldRecover(status) else {
                return response
            }
            await recordMismatch(status, metricsStore: metricsStore, diagnostics: diagnostics)
        } catch {
            guard BackendRouteRecoveryClassifier.shouldRecover(error, mode: mode) else {
                throw error
            }
        }

        await recordRetryAllowed(metricsStore: metricsStore, diagnostics: diagnostics)
        let replacement: ModelCatalog.BackendRouteBinding
        do {
            replacement = try await recoverBinding(
                failedBinding: binding,
                modelCatalog: modelCatalog,
                workerRegistry: workerRegistry,
                metricsStore: metricsStore
            )
        } catch {
            await recordRetryExhausted(metricsStore: metricsStore, diagnostics: diagnostics)
            throw recoveryExhaustedError()
        }

        do {
            let response = try await dispatch(replacement)
            let status = errorStatus(response)
            guard BackendRouteRecoveryClassifier.shouldRecover(status) else {
                return response
            }
            await recordMismatch(status, metricsStore: metricsStore, diagnostics: diagnostics)
        } catch {
            guard BackendRouteRecoveryClassifier.shouldRecover(error, mode: mode) else {
                throw error
            }
        }
        await recordRetryExhausted(metricsStore: metricsStore, diagnostics: diagnostics)
        throw recoveryExhaustedError()
    }

    static func performReplaySafeStream<Event: Sendable>(
        binding: ModelCatalog.BackendRouteBinding,
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry,
        metricsStore: MetricsStore,
        mode: BackendRouteRecoveryMode = .identityAndTransport,
        dispatch: @escaping @Sendable (ModelCatalog.BackendRouteBinding) async throws
            -> AsyncThrowingStream<Event, Error>,
        classify: @escaping @Sendable (Event) -> StreamEventDisposition
    ) -> AsyncThrowingStream<Event, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                var attemptBinding = binding
                for attemptIndex in 0...1 {
                    var responseOpened = false
                    do {
                        let stream = try await dispatch(attemptBinding)
                        var retryRequested = false
                        for try await event in stream {
                            switch classify(event) {
                            case .error(let status):
                                let recoverable = BackendRouteRecoveryClassifier.shouldRecover(status)
                                if recoverable {
                                    await recordMismatch(status, metricsStore: metricsStore)
                                }
                                if responseOpened {
                                    if recoverable {
                                        await recordRetrySuppressed(metricsStore: metricsStore)
                                    }
                                    continuation.finish(throwing: partialStreamFailure())
                                    return
                                }
                                if recoverable, attemptIndex == 0 {
                                    retryRequested = true
                                    break
                                }
                                if recoverable {
                                    await recordRetryExhausted(metricsStore: metricsStore)
                                    continuation.finish(throwing: recoveryExhaustedError())
                                    return
                                }
                                continuation.yield(event)
                                continuation.finish()
                                return
                            case .terminal:
                                continuation.yield(event)
                                continuation.finish()
                                return
                            case .output:
                                responseOpened = true
                                continuation.yield(event)
                            }
                        }

                        if retryRequested {
                            await recordRetryAllowed(metricsStore: metricsStore)
                            do {
                                attemptBinding = try await recoverBinding(
                                    failedBinding: attemptBinding,
                                    modelCatalog: modelCatalog,
                                    workerRegistry: workerRegistry,
                                    metricsStore: metricsStore
                                )
                            } catch {
                                await recordRetryExhausted(metricsStore: metricsStore)
                                continuation.finish(throwing: recoveryExhaustedError())
                                return
                            }
                            continue
                        }
                        if !responseOpened {
                            throw WorkerClientError.unavailable
                        }
                        await recordRetrySuppressed(metricsStore: metricsStore)
                        continuation.finish(throwing: partialStreamFailure())
                        return
                    } catch {
                        if responseOpened {
                            if BackendRouteRecoveryClassifier.shouldRecover(error, mode: mode) {
                                await recordRetrySuppressed(metricsStore: metricsStore)
                            }
                            continuation.finish(throwing: partialStreamFailure())
                            return
                        }
                        guard BackendRouteRecoveryClassifier.shouldRecover(error, mode: mode) else {
                            continuation.finish(throwing: error)
                            return
                        }
                        guard attemptIndex == 0 else {
                            await recordRetryExhausted(metricsStore: metricsStore)
                            continuation.finish(throwing: recoveryExhaustedError())
                            return
                        }
                        await recordRetryAllowed(metricsStore: metricsStore)
                        do {
                            attemptBinding = try await recoverBinding(
                                failedBinding: attemptBinding,
                                modelCatalog: modelCatalog,
                                workerRegistry: workerRegistry,
                                metricsStore: metricsStore
                            )
                        } catch {
                            await recordRetryExhausted(metricsStore: metricsStore)
                            continuation.finish(throwing: recoveryExhaustedError())
                            return
                        }
                    }
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    static func recoverBinding(
        failedBinding: ModelCatalog.BackendRouteBinding,
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry,
        metricsStore: MetricsStore,
        coordinator: BackendRouteRecoveryCoordinator = .shared
    ) async throws -> ModelCatalog.BackendRouteBinding {
        try await coordinator.recover(
            catalog: modelCatalog,
            failedBinding: failedBinding,
            onCoalesced: {
                await metricsStore.increment(
                    "control_plane.backend_identity_recovery_coalesced_caller_count"
                )
            }
        ) {
            let invalidation = await modelCatalog.invalidateBackendRouteBindingForRecovery(
                for: failedBinding.modelID,
                expected: failedBinding,
                reason: "backend_route_recovery"
            )
            if invalidation != nil {
                await metricsStore.increment("control_plane.backend_identity_recovery_count")
            } else {
                throw OnDemandModelLoadError.workerUnavailable
            }
            guard let invalidation else {
                throw OnDemandModelLoadError.workerUnavailable
            }
            await retireFailedResidencyIfStillOwned(
                failedBinding,
                workerRegistry: workerRegistry,
                metricsStore: metricsStore
            )
            try await coordinator.prepareForReload(
                modelID: failedBinding.modelID,
                routeKind: failedBinding.routeKind
            )

            let replacement = try await OnDemandModelLoader.ensureModelBindingReady(
                modelID: failedBinding.modelID,
                modelCatalog: modelCatalog,
                workerRegistry: workerRegistry,
                metricsStore: metricsStore,
                loadReason: "backend_route_recovery",
                metricsPrefix: "backend_identity_recovery",
                routeKindOverride: failedBinding.routeKind,
                expectedCurrentRouteGeneration: invalidation.currentGeneration
            )
            await metricsStore.increment(
                "control_plane.backend_identity_fresh_binding_count"
            )
            return replacement
        }
    }

    private static func retireFailedResidencyIfStillOwned(
        _ failedBinding: ModelCatalog.BackendRouteBinding,
        workerRegistry: WorkerRegistry,
        metricsStore: MetricsStore
    ) async {
        guard let workerClient = await workerRegistry.client(for: failedBinding.routeKind) else {
            await metricsStore.increment(
                "control_plane.backend_identity_failed_residency_retire_skipped_count"
            )
            return
        }

        do {
            var request = Melix_Worker_V1_UnloadModelRequest()
            request.modelHandle = failedBinding.handle
            request.force = true
            request.expectedBackendIdentity = failedBinding.identity
            let response = try await workerClient.unloadModel(request: request)
            if response.ok {
                await metricsStore.increment(
                    "control_plane.backend_identity_failed_residency_retire_count"
                )
            } else if response.error.code == "model_identity_mismatch"
                || response.error.code == "not_found" {
                await metricsStore.increment(
                    "control_plane.backend_identity_failed_residency_retire_skipped_count"
                )
            } else {
                await metricsStore.increment(
                    "control_plane.backend_identity_failed_residency_retire_failure_count"
                )
            }
        } catch {
            await metricsStore.increment(
                "control_plane.backend_identity_failed_residency_retire_failure_count"
            )
        }
    }

    static func recordMismatch(
        _ status: Melix_Worker_V1_ErrorStatus,
        metricsStore: MetricsStore,
        diagnostics: BackendIdentityRecoveryDiagnostics = .shared
    ) async {
        await diagnostics.recordMismatch(status)
        await metricsStore.increment("control_plane.backend_identity_mismatch_count")
        if status.hasBackendIdentityMismatch {
            await metricsStore.set(
                Double(status.backendIdentityMismatch.requestedRouteGeneration),
                forKey: "control_plane.backend_identity_last_requested_route_generation"
            )
            await metricsStore.set(
                Double(status.backendIdentityMismatch.loadedRouteGeneration),
                forKey: "control_plane.backend_identity_last_loaded_route_generation"
            )
        }
    }

    static func recordRetryAllowed(
        metricsStore: MetricsStore,
        diagnostics: BackendIdentityRecoveryDiagnostics = .shared
    ) async {
        await diagnostics.recordRetryAllowed()
        await metricsStore.increment("control_plane.backend_identity_retry_allowed_count")
    }

    static func recordRetrySuppressed(
        metricsStore: MetricsStore,
        diagnostics: BackendIdentityRecoveryDiagnostics = .shared
    ) async {
        await diagnostics.recordRetrySuppressed()
        await metricsStore.increment("control_plane.backend_identity_retry_suppressed_count")
    }

    static func recordRetryExhausted(
        metricsStore: MetricsStore,
        diagnostics: BackendIdentityRecoveryDiagnostics = .shared
    ) async {
        await diagnostics.recordRetryExhausted()
        await metricsStore.increment("control_plane.backend_identity_retry_exhausted_count")
    }

    static func recoveryExhaustedError() -> WorkerClientError {
        .requestFailed(
            code: "backend_route_recovery_exhausted",
            message: "The backend route could not be recovered before response output began."
        )
    }

    static func partialStreamFailure() -> WorkerClientError {
        .requestFailed(
            code: "partial_stream_failure",
            message: "The backend stream failed after response output began and was not replayed."
        )
    }
}

enum BackendRouteRecoveryMode: Equatable, Sendable {
    case identityAndTransport
    case identityMismatchOnly
}

enum BackendRouteRecoveryClassifier {
    static func shouldRecover(_ status: Melix_Worker_V1_ErrorStatus) -> Bool {
        status.code == "model_identity_mismatch"
    }

    static func shouldRecover(_ error: Error) -> Bool {
        shouldRecover(error, mode: .identityAndTransport)
    }

    static func shouldRecover(
        _ error: Error,
        mode: BackendRouteRecoveryMode
    ) -> Bool {
        guard let workerError = error as? WorkerClientError else {
            return false
        }
        switch workerError {
        case .unavailable:
            return mode == .identityAndTransport
        case .requestFailed(let code, _):
            let normalized = code.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if normalized == "model_identity_mismatch" {
                return true
            }
            guard mode == .identityAndTransport else {
                return false
            }
            return normalized == "deadline_exceeded"
                || normalized == "timeout"
                || normalized == "transport_error"
                || normalized == "connection_error"
                || normalized == "connect_error"
                || normalized == "connection_refused"
                || normalized == "connection_reset"
                || normalized == "read_error"
                || normalized == "write_error"
                || normalized == "protocol_error"
                || normalized == "unavailable"
        }
    }
}

private func diagnosticBackendIdentifier(_ value: String) -> String {
    let normalized = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty else {
        return ""
    }
    let isWindowsPath = normalized.count >= 3
        && normalized[normalized.index(after: normalized.startIndex)] == ":"
        && ["\\", "/"].contains(normalized[normalized.index(normalized.startIndex, offsetBy: 2)])
    let lowercased = normalized.lowercased()
    if normalized.hasPrefix("/")
        || normalized.hasPrefix("~/")
        || normalized.hasPrefix("./")
        || normalized.hasPrefix("../")
        || normalized.hasPrefix("\\\\")
        || normalized.hasPrefix(".\\")
        || normalized.hasPrefix("..\\")
        || lowercased.hasPrefix("file:")
        || isWindowsPath {
        return "[local-path-redacted]"
    }
    return normalized.count > 128 ? String(normalized.prefix(125)) + "..." : normalized
}
