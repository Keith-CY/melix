import Testing
import MelixWorkerProtocol
@testable import MelixControlPlaneCore

@Suite("Backend model identity")
struct BackendModelIdentityTests {
    @Test("route generations reject stale load completion and advance after invalidation")
    func routeGenerationLifecycle() async throws {
        var model = ModelCatalog.devTextModel()
        model.settings.ext["melix.adapter_set_hash"] = "adapter-alpha"
        let catalog = ModelCatalog(seedModels: [model])

        let first = try #require(
            await catalog.beginBackendRouteLoad(
                id: model.modelID,
                routeKind: .swiftText,
                workerInstanceID: "swift-test-worker",
                reason: "identity-test"
            )
        )
        #expect(first.generation == 1)
        #expect(first.modelID == model.modelID)
        #expect(first.adapterID == "adapter-alpha")

        _ = await catalog.recordLoadSucceeded(
            id: model.modelID,
            dispatchHandle: "handle-generation-1",
            reason: "identity-test",
            routeKind: .swiftText,
            expectedRouteGeneration: first.generation
        )
        let bound = try #require(
            await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText)
        )
        #expect(bound.handle == "handle-generation-1")
        #expect(bound.generation == first.generation)

        #expect(
            await catalog.invalidateBackendRouteBinding(
                for: model.modelID,
                expected: bound,
                reason: "model_identity_mismatch"
            )
        )
        #expect(await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText) == nil)

        let second = try #require(
            await catalog.beginBackendRouteLoad(
                id: model.modelID,
                routeKind: .swiftText,
                workerInstanceID: "swift-test-worker",
                reason: "identity-recovery"
            )
        )
        #expect(second.generation > first.generation)

        let stale = await catalog.recordLoadSucceeded(
            id: model.modelID,
            dispatchHandle: "stale-handle",
            reason: "stale-completion",
            routeKind: .swiftText,
            expectedRouteGeneration: first.generation
        )
        #expect(stale == nil)
        #expect(await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText) == nil)

        _ = await catalog.recordLoadSucceeded(
            id: model.modelID,
            dispatchHandle: "handle-generation-2",
            reason: "identity-recovery",
            routeKind: .swiftText,
            expectedRouteGeneration: second.generation
        )
        let recovered = try #require(
            await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText)
        )
        #expect(recovered.generation == second.generation)
        #expect(recovered.identity.requestedModelID == model.modelID)
        #expect(recovered.identity.requestedAdapterID == "adapter-alpha")
        #expect(recovered.identity.routeGeneration == second.generation)
    }

    @Test("route-scoped load failure preserves unrelated backend bindings")
    func routeScopedLoadFailurePreservesOtherBindings() async throws {
        let model = ModelCatalog.devTextModel()
        let catalog = ModelCatalog(seedModels: [model])
        let swiftLoad = try #require(
            await catalog.beginBackendRouteLoad(
                id: model.modelID,
                routeKind: .swiftText,
                workerInstanceID: "swift-test-worker"
            )
        )
        _ = await catalog.recordLoadSucceeded(
            id: model.modelID,
            dispatchHandle: "swift-handle",
            routeKind: .swiftText,
            expectedRouteGeneration: swiftLoad.generation
        )
        let compatibilityLoad = try #require(
            await catalog.beginBackendRouteLoad(
                id: model.modelID,
                routeKind: .pythonCompatibility,
                workerInstanceID: "python-test-worker"
            )
        )
        _ = await catalog.recordLoadSucceeded(
            id: model.modelID,
            dispatchHandle: "python-handle",
            routeKind: .pythonCompatibility,
            expectedRouteGeneration: compatibilityLoad.generation
        )

        let failedReload = try #require(
            await catalog.beginBackendRouteLoad(
                id: model.modelID,
                routeKind: .swiftText,
                workerInstanceID: "swift-test-worker"
            )
        )
        _ = await catalog.recordLoadFailed(
            id: model.modelID,
            routeKind: .swiftText,
            expectedRouteGeneration: failedReload.generation
        )
        let staleCompletion = await catalog.recordLoadSucceeded(
            id: model.modelID,
            dispatchHandle: "late-failed-generation",
            routeKind: .swiftText,
            expectedRouteGeneration: failedReload.generation
        )

        #expect(staleCompletion == nil)
        #expect(await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText) == nil)
        let compatibilityBinding = await catalog.backendRouteBinding(
            for: model.modelID,
            routeKind: .pythonCompatibility
        )
        #expect(compatibilityBinding?.handle == "python-handle")
        #expect(await catalog.dispatchHandle(for: model.modelID) == "python-handle")
        #expect(await catalog.model(id: model.modelID)?.state == .modelWarm)
    }

    @Test("operator unload wins against a late load completion")
    func unloadWinsLateLoadCompletion() async throws {
        let model = ModelCatalog.devTextModel()
        let catalog = ModelCatalog(seedModels: [model])
        let reservation = try #require(
            await catalog.beginBackendRouteLoad(
                id: model.modelID,
                routeKind: .swiftText,
                workerInstanceID: "swift-test-worker"
            )
        )

        _ = await catalog.beginUnload(id: model.modelID, reason: "operator_unload")
        let stale = await catalog.recordLoadSucceeded(
            id: model.modelID,
            dispatchHandle: "late-handle",
            routeKind: .swiftText,
            expectedRouteGeneration: reservation.generation
        )

        #expect(stale == nil)
        #expect(await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText) == nil)
    }

    @Test("operator unload wins between recovery invalidation and reload reservation")
    func unloadWinsRecoveryReservationRace() async throws {
        let model = ModelCatalog.devTextModel()
        let catalog = ModelCatalog(seedModels: [model])
        _ = await catalog.loadModel(id: model.modelID, dispatchHandle: "failed-handle")
        let failed = try #require(
            await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText)
        )
        let gate = RecoveryRaceGate()
        let coordinator = BackendRouteRecoveryCoordinator(
            beforeReload: { _, _ in
                await gate.arriveAndWaitForRelease()
            }
        )
        let worker = RecoveryLoadFailureWorkerClient()
        let registry = WorkerRegistry(defaultTextClient: worker, modelCatalog: catalog)

        let recovery = Task {
            try await BackendRouteRecovery.recoverBinding(
                failedBinding: failed,
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore(),
                coordinator: coordinator
            )
        }
        await gate.waitForArrival()
        _ = await catalog.beginUnload(id: model.modelID, reason: "operator_unload")
        await gate.release()

        do {
            _ = try await recovery.value
            Issue.record("Expected operator unload to prevent recovery reservation.")
        } catch {
            #expect(error is OnDemandModelLoadError)
        }
        #expect(await worker.loadCallCount == 0)
        #expect(await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText) == nil)
        #expect(await catalog.model(id: model.modelID)?.state == .modelEvicting)
    }

    @Test(
        "backend residency settings invalidate every route binding",
        arguments: [
            ("melix.model_path", "/models/replacement"),
            ("melix.model_revision", "revision-replacement"),
            ("melix.adapter_set_hash", "adapter-replacement"),
        ]
    )
    func backendResidencySettingsInvalidateBindings(key: String, value: String) async throws {
        var model = ModelCatalog.devTextModel()
        model.settings.ext[key] = "original"
        let catalog = ModelCatalog(seedModels: [model])
        let reservation = try #require(await catalog.beginBackendRouteLoad(
            id: model.modelID,
            routeKind: .swiftText,
            workerInstanceID: "worker-before-settings"
        ))
        _ = await catalog.recordLoadSucceeded(
            id: model.modelID,
            dispatchHandle: "handle-before-settings",
            routeKind: .swiftText,
            expectedRouteGeneration: reservation.generation,
            workerInstanceID: reservation.workerInstanceID
        )

        var replacement = model.settings
        replacement.ext[key] = value
        let updated = try #require(await catalog.updateSettings(id: model.modelID, settings: replacement))
        let next = try #require(await catalog.beginBackendRouteLoad(
            id: model.modelID,
            routeKind: .swiftText,
            workerInstanceID: "worker-after-settings"
        ))

        #expect(updated.state == .modelUnloaded)
        #expect(await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText) == nil)
        #expect(next.generation > reservation.generation)
    }

    @Test("non-residency settings preserve the current backend binding")
    func nonResidencySettingsPreserveBinding() async throws {
        let model = ModelCatalog.devTextModel()
        let catalog = ModelCatalog(seedModels: [model])
        _ = await catalog.loadModel(id: model.modelID, dispatchHandle: "stable-handle")
        let before = try #require(
            await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText)
        )
        var settings = model.settings
        settings.alias = "Renamed model"

        _ = await catalog.updateSettings(id: model.modelID, settings: settings)

        #expect(await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText) == before)
    }

    @Test("an explicit replacement wins against recovery of an older binding")
    func explicitReplacementWinsRecoveryRace() async throws {
        let model = ModelCatalog.devTextModel()
        let catalog = ModelCatalog(seedModels: [model])
        _ = await catalog.loadModel(id: model.modelID, dispatchHandle: "failed-handle")
        let failed = try #require(
            await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText)
        )
        #expect(await catalog.invalidateBackendRouteBinding(
            for: model.modelID,
            expected: failed,
            reason: "explicit_replacement"
        ))
        let replacementReservation = try #require(await catalog.beginBackendRouteLoad(
            id: model.modelID,
            routeKind: .swiftText,
            workerInstanceID: "replacement-worker"
        ))
        _ = await catalog.recordLoadSucceeded(
            id: model.modelID,
            dispatchHandle: "replacement-handle",
            routeKind: .swiftText,
            expectedRouteGeneration: replacementReservation.generation,
            workerInstanceID: replacementReservation.workerInstanceID
        )
        let registry = WorkerRegistry(
            defaultTextClient: RecoveryLoadFailureWorkerClient(),
            modelCatalog: catalog
        )

        await #expect(throws: OnDemandModelLoadError.workerUnavailable) {
            _ = try await BackendRouteRecovery.recoverBinding(
                failedBinding: failed,
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore(),
                coordinator: BackendRouteRecoveryCoordinator()
            )
        }
        #expect(await catalog.backendRouteBinding(
            for: model.modelID,
            routeKind: .swiftText
        )?.handle == "replacement-handle")
    }

    @Test("one binding stamps every production inference request shape")
    func stampsEveryInferenceRequestShape() {
        let binding = ModelCatalog.BackendRouteBinding(
            modelID: "public-model",
            adapterID: "public-adapter",
            generation: 9,
            handle: "worker-handle",
            routeKind: .pythonVLM
        )

        var generate = Melix_Worker_V1_GenerateRequest()
        var prefill = Melix_Worker_V1_PrefillRequest()
        var decode = Melix_Worker_V1_DecodeRequest()
        var embed = Melix_Worker_V1_EmbedRequest()
        var rerank = Melix_Worker_V1_RerankRequest()
        var transcribe = Melix_Worker_V1_TranscribeRequest()
        var speak = Melix_Worker_V1_SpeakRequest()
        var imageGenerate = Melix_Worker_V1_ImageGenerateRequest()
        var imageEdit = Melix_Worker_V1_ImageEditRequest()

        BackendModelIdentityStamping.stamp(binding, on: &generate)
        BackendModelIdentityStamping.stamp(binding, on: &prefill)
        BackendModelIdentityStamping.stamp(binding, on: &decode)
        BackendModelIdentityStamping.stamp(binding, on: &embed)
        BackendModelIdentityStamping.stamp(binding, on: &rerank)
        BackendModelIdentityStamping.stamp(binding, on: &transcribe)
        BackendModelIdentityStamping.stamp(binding, on: &speak)
        BackendModelIdentityStamping.stamp(binding, on: &imageGenerate)
        BackendModelIdentityStamping.stamp(binding, on: &imageEdit)

        let executionRequests = [generate.execution, prefill.execution, decode.execution]
        for execution in executionRequests {
            #expect(execution.modelHandle == binding.handle)
            #expect(execution.backendIdentity == binding.identity)
        }
        #expect(embed.modelHandle == binding.handle)
        #expect(embed.backendIdentity == binding.identity)
        #expect(rerank.modelHandle == binding.handle)
        #expect(rerank.backendIdentity == binding.identity)
        #expect(transcribe.modelHandle == binding.handle)
        #expect(transcribe.backendIdentity == binding.identity)
        #expect(speak.modelHandle == binding.handle)
        #expect(speak.backendIdentity == binding.identity)
        #expect(imageGenerate.modelHandle == binding.handle)
        #expect(imageGenerate.backendIdentity == binding.identity)
        #expect(imageEdit.modelHandle == binding.handle)
        #expect(imageEdit.backendIdentity == binding.identity)
    }

    @Test("concurrent recovery for one failed generation performs one replacement")
    func concurrentRecoveryCoalesces() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let coordinator = BackendRouteRecoveryCoordinator()
        let reservation = try #require(
            await catalog.beginBackendRouteLoad(
                id: "melix-dev-text",
                routeKind: .swiftText,
                workerInstanceID: "swift-test-worker"
            )
        )
        _ = await catalog.recordLoadSucceeded(
            id: "melix-dev-text",
            dispatchHandle: "failed-handle",
            routeKind: .swiftText,
            expectedRouteGeneration: reservation.generation
        )
        let failed = try #require(
            await catalog.backendRouteBinding(for: "melix-dev-text", routeKind: .swiftText)
        )
        let calls = RecoveryCallCounter()
        let gate = RecoveryRaceGate()
        let coalescedGate = RecoveryRaceGate()

        let first = Task {
            try await coordinator.recover(catalog: catalog, failedBinding: failed) {
                await calls.increment()
                await gate.arriveAndWaitForRelease()
                return ModelCatalog.BackendRouteBinding(
                    modelID: failed.modelID,
                    adapterID: failed.adapterID,
                    generation: failed.generation + 1,
                    handle: "replacement",
                    routeKind: failed.routeKind
                )
            }
        }
        await gate.waitForArrival()
        let second = Task {
            try await coordinator.recover(
                catalog: catalog,
                failedBinding: failed,
                onCoalesced: {
                    await coalescedGate.arriveAndWaitForRelease()
                }
            ) {
                await calls.increment()
                return ModelCatalog.BackendRouteBinding(
                    modelID: failed.modelID,
                    adapterID: failed.adapterID,
                    generation: failed.generation + 2,
                    handle: "unexpected",
                    routeKind: failed.routeKind
                )
            }
        }
        await coalescedGate.waitForArrival()
        await coalescedGate.release()
        await gate.release()

        let results = try await [first.value, second.value]
        #expect(results[0] == results[1])
        #expect(results[0].handle == "replacement")
        #expect(await calls.value == 1)
    }
    @Test("only identity mismatch and pre-response transport failures are recoverable")
    func retryClassifierIsClosed() {
        var mismatch = Melix_Worker_V1_ErrorStatus()
        mismatch.code = "model_identity_mismatch"
        var missing = Melix_Worker_V1_ErrorStatus()
        missing.code = "model_identity_missing"

        #expect(BackendRouteRecoveryClassifier.shouldRecover(mismatch))
        #expect(!BackendRouteRecoveryClassifier.shouldRecover(missing))
        #expect(BackendRouteRecoveryClassifier.shouldRecover(WorkerClientError.unavailable))
        #expect(BackendRouteRecoveryClassifier.shouldRecover(
            WorkerClientError.requestFailed(code: "model_identity_mismatch", message: "stale binding")
        ))
        for code in [
            "CONNECT_ERROR",
            "READ_ERROR",
            "WRITE_ERROR",
            "PROTOCOL_ERROR",
            "DEADLINE_EXCEEDED",
            "TIMEOUT",
        ] {
            #expect(BackendRouteRecoveryClassifier.shouldRecover(
                WorkerClientError.requestFailed(code: code, message: "pre-response failure")
            ))
        }
        #expect(!BackendRouteRecoveryClassifier.shouldRecover(
            WorkerClientError.requestFailed(code: "INVALID_ARGUMENT", message: "bad request")
        ))
    }

    @Test("control-plane diagnostics bound and redact the last mismatch receipt")
    func controlPlaneDiagnosticsAreBoundedAndRedacted() async {
        let diagnostics = BackendIdentityRecoveryDiagnostics()
        let metrics = MetricsStore()
        var status = Melix_Worker_V1_ErrorStatus()
        status.code = "model_identity_mismatch"
        status.backendIdentityMismatch.requestedModelID = "public-model"
        status.backendIdentityMismatch.loadedModelID = "/Users/operator/private/model"
        status.backendIdentityMismatch.requestedAdapterID = "../private/adapter"
        status.backendIdentityMismatch.loadedAdapterID = "FILE:///private/adapter"
        status.backendIdentityMismatch.requestedRouteGeneration = 8
        status.backendIdentityMismatch.loadedRouteGeneration = 7
        status.backendIdentityMismatch.requestedWorkerInstanceID = "public-worker"
        status.backendIdentityMismatch.loadedWorkerInstanceID = "\\\\server\\share\\worker"
        status.backendIdentityMismatch.observedAtUnixMs = 123
        status.backendIdentityMismatch.mismatchReason = String(repeating: "x", count: 256)

        await BackendRouteRecovery.recordMismatch(
            status,
            metricsStore: metrics,
            diagnostics: diagnostics
        )
        await BackendRouteRecovery.recordRetryAllowed(
            metricsStore: metrics,
            diagnostics: diagnostics
        )
        await BackendRouteRecovery.recordRetrySuppressed(
            metricsStore: metrics,
            diagnostics: diagnostics
        )
        await BackendRouteRecovery.recordRetryExhausted(
            metricsStore: metrics,
            diagnostics: diagnostics
        )
        let snapshot = await diagnostics.snapshot()
        let metricSnapshot = await metrics.snapshot()

        #expect(snapshot.mismatchCount == 1)
        #expect(snapshot.retryAllowedCount == 1)
        #expect(snapshot.retrySuppressedCount == 1)
        #expect(snapshot.retryExhaustedCount == 1)
        #expect(snapshot.lastMismatch?.requestedModelID == "public-model")
        #expect(snapshot.lastMismatch?.loadedModelID == "[local-path-redacted]")
        #expect(snapshot.lastMismatch?.requestedAdapterID == "[local-path-redacted]")
        #expect(snapshot.lastMismatch?.loadedAdapterID == "[local-path-redacted]")
        #expect(snapshot.lastMismatch?.requestedWorkerInstanceID == "public-worker")
        #expect(snapshot.lastMismatch?.loadedWorkerInstanceID == "[local-path-redacted]")
        #expect(snapshot.lastMismatch?.mismatchReason.count == 128)
        #expect(metricSnapshot.values["control_plane.backend_identity_mismatch_count"] == 1)
        #expect(metricSnapshot.values["control_plane.backend_identity_retry_allowed_count"] == 1)
        #expect(metricSnapshot.values["control_plane.backend_identity_retry_suppressed_count"] == 1)
        #expect(metricSnapshot.values["control_plane.backend_identity_retry_exhausted_count"] == 1)
    }

    @Test("unary recovery load failure returns stable typed exhaustion")
    func unaryRecoveryLoadFailureIsTyped() async throws {
        let model = ModelCatalog.devTextModel()
        let catalog = ModelCatalog(seedModels: [model])
        _ = await catalog.loadModel(id: model.modelID, dispatchHandle: "failed-handle")
        let binding = try #require(
            await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText)
        )
        let metrics = MetricsStore()
        let worker = RecoveryLoadFailureWorkerClient()
        let registry = WorkerRegistry(defaultTextClient: worker, modelCatalog: catalog)

        do {
            _ = try await BackendRouteRecovery.performReplaySafeUnary(
                binding: binding,
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: metrics,
                dispatch: { _ in
                    var response = Melix_Worker_V1_EmbedResponse()
                    response.error.code = "model_identity_mismatch"
                    return response
                },
                errorStatus: { $0.error }
            )
            Issue.record("Expected typed backend route recovery exhaustion.")
        } catch let error as WorkerClientError {
            #expect(error == .requestFailed(
                code: "backend_route_recovery_exhausted",
                message: "The backend route could not be recovered before response output began."
            ))
        }

        #expect(await worker.loadCallCount == 1)
        #expect(await metrics.value(forKey: "control_plane.backend_identity_retry_exhausted_count") == 1)
    }

    @Test("recovery retires only residency proven to belong to the failed binding")
    func recoveryRetiresOnlyOwnedResidency() async throws {
        for workerStillOwnsFailedResidency in [true, false] {
            let model = ModelCatalog.devTextModel()
            let catalog = ModelCatalog(seedModels: [model])
            let reservation = try #require(await catalog.beginBackendRouteLoad(
                id: model.modelID,
                routeKind: .swiftText,
                workerInstanceID: "failed-worker"
            ))
            _ = await catalog.recordLoadSucceeded(
                id: model.modelID,
                dispatchHandle: "failed-handle",
                routeKind: .swiftText,
                expectedRouteGeneration: reservation.generation,
                workerInstanceID: reservation.workerInstanceID
            )
            let failedBinding = try #require(
                await catalog.backendRouteBinding(for: model.modelID, routeKind: .swiftText)
            )
            var listedIdentity = failedBinding.identity
            let healthWorkerID: String
            if workerStillOwnsFailedResidency {
                healthWorkerID = failedBinding.workerInstanceID
            } else {
                healthWorkerID = "replacement-worker"
                listedIdentity.workerInstanceID = healthWorkerID
            }
            let worker = ResidencyRetirementWorkerClient(
                healthWorkerID: healthWorkerID,
                listedHandle: failedBinding.handle,
                listedIdentity: listedIdentity
            )
            let metrics = MetricsStore()
            let registry = WorkerRegistry(defaultTextClient: worker, modelCatalog: catalog)

            await #expect(throws: WorkerClientError.requestFailed(
                code: "backend_route_recovery_exhausted",
                message: "The backend route could not be recovered before response output began."
            )) {
                _ = try await BackendRouteRecovery.performReplaySafeUnary(
                    binding: failedBinding,
                    modelCatalog: catalog,
                    workerRegistry: registry,
                    metricsStore: metrics,
                    dispatch: { _ in
                        var response = Melix_Worker_V1_EmbedResponse()
                        response.error.code = "model_identity_mismatch"
                        return response
                    },
                    errorStatus: { $0.error }
                )
            }

            #expect(await worker.unloadedHandles == (
                workerStillOwnsFailedResidency ? [failedBinding.handle] : []
            ))
            #expect(await worker.unloadRequests.count == 1)
            #expect(await worker.unloadRequests.first?.expectedBackendIdentity == failedBinding.identity)
            #expect(await metrics.value(
                forKey: workerStillOwnsFailedResidency
                    ? "control_plane.backend_identity_failed_residency_retire_count"
                    : "control_plane.backend_identity_failed_residency_retire_skipped_count"
            ) == 1)
        }
    }
}

private actor RecoveryCallCounter {
    private(set) var value = 0

    func increment() {
        value += 1
    }
}

private actor RecoveryRaceGate {
    private var arrived = false
    private var released = false
    private var arrivalWaiters: [CheckedContinuation<Void, Never>] = []
    private var releaseWaiters: [CheckedContinuation<Void, Never>] = []

    func arriveAndWaitForRelease() async {
        arrived = true
        let waiters = arrivalWaiters
        arrivalWaiters.removeAll()
        for waiter in waiters {
            waiter.resume()
        }
        guard !released else {
            return
        }
        await withCheckedContinuation { continuation in
            releaseWaiters.append(continuation)
        }
    }

    func waitForArrival() async {
        guard !arrived else {
            return
        }
        await withCheckedContinuation { continuation in
            arrivalWaiters.append(continuation)
        }
    }

    func release() {
        released = true
        let waiters = releaseWaiters
        releaseWaiters.removeAll()
        for waiter in waiters {
            waiter.resume()
        }
    }
}

private actor RecoveryLoadFailureWorkerClient:
    WorkerRoutingClient,
    BackendHealthIdentifyingWorkerClientProtocol
{
    private(set) var loadCallCount = 0

    func canDispatchRequests() async -> Bool {
        true
    }

    func backendHealthIdentity() async throws -> Melix_Worker_V1_HandshakeResponse {
        var response = Melix_Worker_V1_HandshakeResponse()
        response.workerInstanceID = "swift-test-worker"
        return response
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        loadCallCount += 1
        throw WorkerClientError.unavailable
    }
}

private actor ResidencyRetirementWorkerClient:
    WorkerRoutingClient,
    BackendHealthIdentifyingWorkerClientProtocol
{
    private let healthWorkerID: String
    private let listedHandle: String
    private let listedIdentity: Melix_Worker_V1_BackendModelIdentity
    private(set) var unloadedHandles: [String] = []
    private(set) var unloadRequests: [Melix_Worker_V1_UnloadModelRequest] = []

    init(
        healthWorkerID: String,
        listedHandle: String,
        listedIdentity: Melix_Worker_V1_BackendModelIdentity
    ) {
        self.healthWorkerID = healthWorkerID
        self.listedHandle = listedHandle
        self.listedIdentity = listedIdentity
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func backendHealthIdentity() async throws -> Melix_Worker_V1_HandshakeResponse {
        var response = Melix_Worker_V1_HandshakeResponse()
        response.workerInstanceID = healthWorkerID
        return response
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        throw WorkerClientError.unavailable
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        unloadRequests.append(request)
        var response = Melix_Worker_V1_UnloadModelResponse()
        if request.modelHandle == listedHandle,
           request.hasExpectedBackendIdentity,
           request.expectedBackendIdentity == listedIdentity {
            unloadedHandles.append(request.modelHandle)
            response.ok = true
        } else {
            response.error.code = "model_identity_mismatch"
        }
        return response
    }
}
