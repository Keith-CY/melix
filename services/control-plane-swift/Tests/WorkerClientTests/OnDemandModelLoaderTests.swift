import Foundation
import SwiftProtobuf
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("On-Demand Model Loader")
struct OnDemandModelLoaderTests {
    @Test("stale lazy load cleanup cannot unload a replacement reusing the handle")
    func staleLazyLoadCleanupCannotUnloadReplacementReusingHandle() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let worker = LoaderTestingWorkerClient()
        await worker.prepareStaleLoadCleanupRace()
        let registry = WorkerRegistry(defaultTextClient: worker, modelCatalog: catalog)
        let staleLoad = Task {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore()
            )
        }

        let staleRequest = await worker.waitForFirstLoadRequest()
        let replacementReservation = try #require(await catalog.beginBackendRouteLoad(
            id: "melix-dev-text",
            routeKind: .swiftText,
            workerInstanceID: worker.staleLoadCleanupWorkerInstanceID,
            reason: "explicit_replacement"
        ))
        await worker.installReplacement(identity: replacementReservation.identity)
        _ = try #require(await catalog.recordLoadSucceeded(
            id: "melix-dev-text",
            dispatchHandle: worker.staleLoadCleanupReusedHandle,
            routeKind: .swiftText,
            expectedRouteGeneration: replacementReservation.generation,
            workerInstanceID: replacementReservation.workerInstanceID
        ))

        await worker.releaseFirstLoad()
        await #expect(throws: OnDemandModelLoadError.workerUnavailable) {
            _ = try await staleLoad.value
        }

        let cleanup = try #require(await worker.unloadRequests.first)
        let replacement = try #require(await catalog.backendRouteBinding(
            for: "melix-dev-text",
            routeKind: .swiftText
        ))
        #expect(cleanup.modelHandle == worker.staleLoadCleanupReusedHandle)
        #expect(!cleanup.force)
        #expect(cleanup.expectedBackendIdentity == staleRequest.backendIdentity)
        #expect(cleanup.expectedBackendIdentity != replacement.identity)
        #expect(await worker.unloadResponseCodes == ["model_identity_mismatch"])
        #expect(await worker.currentResidentIdentity() == replacement.identity)
        #expect(replacement.generation == replacementReservation.generation)
    }

    @Test("ready handles are reused without warm-path eviction planning")
    func readyHandlesAreReusedWithoutWarmPathEvictionPlanning() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        let clock = ClockBox(nowUnixMs: 100_000)
        let catalog = ModelCatalog(
            seedModels: [
                makeTextModel(
                    id: "melix-old-text",
                    state: .modelWarm,
                    ttlSeconds: 60
                ),
                makeTextModel(
                    id: "melix-dev-text",
                    state: .modelWarm
                ),
            ],
            nowUnixMs: { clock.nowUnixMs }
        )
        _ = await catalog.recordLoadSucceeded(
            id: "melix-old-text",
            dispatchHandle: "melix-old-text::swift",
            reason: "seed_load"
        )
        _ = await catalog.recordLoadSucceeded(
            id: "melix-dev-text",
            dispatchHandle: "melix-dev-text::swift",
            reason: "seed_load"
        )
        clock.nowUnixMs += 61_000

        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setUnloadResponse(ok: true)
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let oldModel = try #require(await catalog.model(id: "melix-old-text"))
        let metrics = await metricsStore.snapshot()

        #expect(handle == "melix-dev-text::swift")
        #expect(oldModel.state == .modelWarm)
        #expect(await workerClient.unloadHandles == [])
        #expect(await workerClient.loadRequestCount == 0)
        #expect(metrics.values["control_plane.model_eviction_plan_count", default: 0] == 0)
        #expect(metrics.values["control_plane.model_eviction_ttl_count", default: 0] == 0)
        #expect(metrics.values["control_plane.model_eviction_success_count", default: 0] == 0)
    }

    @Test("complete backend route bindings are reused without loading")
    func completeBackendRouteBindingsAreReusedWithoutLoading() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        _ = await catalog.recordLoadSucceeded(
            id: "melix-dev-text",
            dispatchHandle: "melix-dev-text::bound",
            routeKind: .swiftText,
            workerInstanceID: "bound-worker"
        )
        let workerClient = LoaderTestingWorkerClient()
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: MetricsStore()
        )

        #expect(handle == "melix-dev-text::bound")
        #expect(await workerClient.loadRequestCount == 0)
    }

    @Test("a stale handle from another control plane force unload is invalidated and lazy reloaded")
    func staleCrossControlPlaneHandleIsInvalidatedAndLazyReloaded() async throws {
        let sharedWorker = SharedResidencyTestingWorkerClient()
        let firstCatalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let secondCatalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let firstRegistry = WorkerRegistry(defaultTextClient: sharedWorker, modelCatalog: firstCatalog)
        let secondRegistry = WorkerRegistry(defaultTextClient: sharedWorker, modelCatalog: secondCatalog)

        let firstHandle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: firstCatalog,
            workerRegistry: firstRegistry,
            metricsStore: MetricsStore()
        )
        let secondHandle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: secondCatalog,
            workerRegistry: secondRegistry,
            metricsStore: MetricsStore()
        )
        #expect(firstHandle == "melix-dev-text::shared-1")
        #expect(secondHandle == firstHandle)

        let reusedHandle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: secondCatalog,
            workerRegistry: secondRegistry,
            metricsStore: MetricsStore()
        )
        #expect(reusedHandle == firstHandle)

        var forceUnloadRequest = Melix_Worker_V1_UnloadModelRequest()
        forceUnloadRequest.modelHandle = firstHandle
        forceUnloadRequest.force = true
        let forceUnloadResponse = try await sharedWorker.unloadModel(request: forceUnloadRequest)
        #expect(forceUnloadResponse.ok)
        _ = await firstCatalog.recordUnloadSucceeded(id: "melix-dev-text", reason: "operator_unload")

        let recoveryMetrics = MetricsStore()
        let recoveredHandle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: secondCatalog,
            workerRegistry: secondRegistry,
            metricsStore: recoveryMetrics
        )
        let recoveredModel = try #require(await secondCatalog.model(id: "melix-dev-text"))
        let metrics = await recoveryMetrics.snapshot()

        var generateRequest = Melix_Worker_V1_GenerateRequest()
        generateRequest.execution.id.requestID = "req-after-stale-recovery"
        generateRequest.execution.modelHandle = recoveredHandle
        let stream = try await sharedWorker.generate(request: generateRequest)
        for try await _ in stream {}

        #expect(recoveredHandle == "melix-dev-text::shared-2")
        #expect(recoveredModel.state == .modelWarm)
        #expect(recoveredModel.residency.transitionReason == "lazy_text_load")
        #expect(await sharedWorker.loadRequestCount == 3)
        #expect(await sharedWorker.listRequestCount == 2)
        #expect(await sharedWorker.loadedHandles == ["melix-dev-text::shared-2"])
        #expect(await sharedWorker.canDispatchRequests())
        #expect(try await sharedWorker.abort(requestID: "req-after-stale-recovery"))
        #expect(metrics.values.keys.contains("control_plane.model_handle_validation_ms"))
        #expect(metrics.values["control_plane.model_stale_handle_recovery_count"] == 1)
    }

    @Test("loaded model introspection failures invalidate and reload the cached handle")
    func loadedModelIntrospectionFailuresInvalidateAndReloadCachedHandle() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        _ = await catalog.recordLoadSucceeded(
            id: "melix-dev-text",
            dispatchHandle: "melix-dev-text::cached",
            reason: "seed_load"
        )
        let worker = SharedResidencyTestingWorkerClient()
        await worker.setListFailure(WorkerClientError.unavailable)
        let registry = WorkerRegistry(defaultTextClient: worker, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )
        let metrics = await metricsStore.snapshot()

        #expect(handle == "melix-dev-text::shared-1")
        #expect(await worker.loadRequestCount == 1)
        #expect(metrics.values.keys.contains("control_plane.model_handle_validation_ms"))
        #expect(metrics.values["control_plane.model_handle_validation_failure_count"] == 1)
        #expect(metrics.values["control_plane.model_stale_handle_recovery_count"] == 1)
    }

    @Test("catalog invalidation clears only the expected stale handle and records the transition")
    func catalogInvalidationClearsExpectedStaleHandleAndRecordsTransition() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        _ = await catalog.recordLoadSucceeded(
            id: "melix-dev-text",
            dispatchHandle: "melix-dev-text::stale",
            reason: "seed_load",
            routeKind: .swiftText
        )

        let invalidated = await catalog.invalidateDispatchHandle(
            for: "melix-dev-text",
            expectedDispatchHandle: "melix-dev-text::stale"
        )
        let invalidatedAgain = await catalog.invalidateDispatchHandle(
            for: "melix-dev-text",
            expectedDispatchHandle: "melix-dev-text::stale"
        )
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(invalidated)
        #expect(!invalidatedAgain)
        #expect(model.state == .modelUnloaded)
        #expect(model.residency.transitionReason == "worker_handle_missing")
        #expect(await catalog.dispatchHandle(for: "melix-dev-text", routeKind: .swiftText) == nil)
    }

    @Test("lazy loads evict ttl-expired residents before contacting workers")
    func lazyLoadsEvictTTLExpiredResidentsBeforeContactingWorkers() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        let clock = ClockBox(nowUnixMs: 100_000)
        let catalog = ModelCatalog(
            seedModels: [
                makeTextModel(
                    id: "melix-old-text",
                    state: .modelWarm,
                    ttlSeconds: 60
                ),
                makeTextModel(
                    id: "melix-dev-text",
                    state: .modelDiscovered
                ),
            ],
            nowUnixMs: { clock.nowUnixMs }
        )
        _ = await catalog.recordLoadSucceeded(
            id: "melix-old-text",
            dispatchHandle: "melix-old-text::swift",
            reason: "seed_load"
        )
        clock.nowUnixMs += 61_000

        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-text::swift",
            estimatedResidentBytes: 4_096
        )
        await workerClient.setUnloadResponse(ok: true)
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let oldModel = try #require(await catalog.model(id: "melix-old-text"))
        let metrics = await metricsStore.snapshot()

        #expect(handle == "melix-dev-text::swift")
        #expect(oldModel.state == .modelUnloaded)
        #expect(await workerClient.unloadHandles == ["melix-old-text::swift"])
        #expect(await workerClient.loadRequestCount == 1)
        #expect(metrics.values["control_plane.model_eviction_plan_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_ttl_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_success_count"] == 1)
    }

    @Test("idle sweep unloads only idle served models and protects pinned models")
    func idleSweepUnloadsOnlyIdleServedModelsAndProtectsPinnedModels() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        let clock = ClockBox(nowUnixMs: 100_000)
        let catalog = ModelCatalog(
            seedModels: [
                makeTextModel(id: "served-idle", state: .modelWarm),
                makeTextModel(id: "unserved-idle", state: .modelWarm),
                makePinnedTextModel(id: "served-pinned"),
            ],
            nowUnixMs: { clock.nowUnixMs }
        )
        _ = await catalog.recordLoadSucceeded(id: "served-idle", dispatchHandle: "served-idle::swift")
        _ = await catalog.recordLoadSucceeded(id: "unserved-idle", dispatchHandle: "unserved-idle::swift")
        _ = await catalog.recordLoadSucceeded(
            id: "served-pinned",
            dispatchHandle: "served-pinned::swift",
            pinRequested: true
        )
        clock.nowUnixMs += 11_000
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setUnloadResponse(ok: true)
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        let plan = await OnDemandModelLoader.sweepIdleModels(
            servedModelIDs: ["served-idle", "served-pinned"],
            idleTimeoutSeconds: 10,
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )
        let servedIdle = try #require(await catalog.model(id: "served-idle"))
        let unservedIdle = try #require(await catalog.model(id: "unserved-idle"))
        let servedPinned = try #require(await catalog.model(id: "served-pinned"))
        let metrics = await metricsStore.snapshot()

        #expect(plan.decisions.map(\.modelID) == ["served-idle"])
        #expect(plan.pinnedProtectedModelIDs == ["served-pinned"])
        #expect(servedIdle.state == .modelUnloaded)
        #expect(unservedIdle.state == .modelWarm)
        #expect(servedPinned.state == .modelPinned)
        #expect(await workerClient.unloadHandles == ["served-idle::swift"])
        #expect(metrics.values["control_plane.model_idle_unload_count"] == 1)
        #expect(metrics.values["control_plane.model_idle_skip_pinned_count"] == 1)
    }

    @Test("idle sweep protects models with active requests")
    func idleSweepProtectsModelsWithActiveRequests() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        let clock = ClockBox(nowUnixMs: 200_000)
        let catalog = ModelCatalog(
            seedModels: [makeTextModel(id: "served-active", state: .modelWarm)],
            nowUnixMs: { clock.nowUnixMs }
        )
        _ = await catalog.recordLoadSucceeded(id: "served-active", dispatchHandle: "served-active::swift")
        await catalog.beginRequest(modelID: "served-active")
        clock.nowUnixMs += 11_000
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setUnloadResponse(ok: true)
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        let plan = await OnDemandModelLoader.sweepIdleModels(
            servedModelIDs: ["served-active"],
            idleTimeoutSeconds: 10,
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )
        let active = try #require(await catalog.model(id: "served-active"))
        let metrics = await metricsStore.snapshot()

        #expect(plan.decisions.isEmpty)
        #expect(plan.activeProtectedModelIDs == ["served-active"])
        #expect(active.state == .modelWarm)
        #expect(await workerClient.unloadHandles.isEmpty)
        #expect(metrics.values["control_plane.model_idle_skip_active_count"] == 1)
    }

    @Test("discovered text models lazy-load with runtime resident bytes and explicit memory budgets")
    func discoveredTextModelsLazyLoadWithRuntimeResidentBytesAndExplicitMemoryBudgets() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-text::swift",
            estimatedResidentBytes: 4_096
        )
        await workerClient.setRuntimeResidentBytes(8_192)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore,
            memoryBudgetBytes: 65_536
        )

        let model = try #require(await catalog.model(id: "melix-dev-text"))
        let loadRequest = try #require(await workerClient.lastLoadModelRequest)
        let metrics = await metricsStore.snapshot()

        #expect(handle == "melix-dev-text::swift")
        #expect(model.state == .modelWarm)
        #expect(model.residency.transitionReason == "lazy_text_load")
        #expect(loadRequest.memoryBudgetBytes == 65_536)
        #expect(loadRequest.pinOnLoad == false)
        #expect(loadRequest.diskStreamingMode == .diskStreamingDisabled)
        #expect(metrics.values["control_plane.text_first_load_estimated_resident_bytes"] == 4_096)
        #expect(metrics.values["control_plane.text_first_load_resident_bytes"] == 8_192)
    }

    @Test("discovered text models lazy-load with configured default memory budgets")
    func discoveredTextModelsLazyLoadWithConfiguredDefaultMemoryBudgets() async throws {
        var model = ModelCatalog.devTextModel()
        model.settings.memoryBudgetBytes = 32_768
        let catalog = ModelCatalog(seedModels: [model])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-text::swift",
            estimatedResidentBytes: 4_096
        )

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        _ = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let loadRequest = try #require(await workerClient.lastLoadModelRequest)
        #expect(loadRequest.memoryBudgetBytes == 32_768)
    }

    @Test("canonical python text compatibility metadata routes to the python compatibility worker")
    func canonicalPythonTextCompatibilityMetadataRoutesToPythonCompatibilityWorker() async throws {
        var model = makeTextModel(id: "registry-text", state: .modelDiscovered)
        model.routeClass = .unspecified
        model.settings.ext["melix.capability.route_kind"] = "python_text_compatibility"
        let catalog = ModelCatalog(seedModels: [model])
        let swiftClient = LoaderTestingWorkerClient()
        await swiftClient.setLoadResponse(
            ok: true,
            handle: "registry-text::swift",
            estimatedResidentBytes: 4_096
        )
        let pythonClient = LoaderTestingWorkerClient()
        await pythonClient.setLoadResponse(
            ok: true,
            handle: "registry-text::python",
            estimatedResidentBytes: 8_192
        )
        let registry = WorkerRegistry(
            defaultTextClient: swiftClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "registry-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        #expect(handle == "registry-text::python")
        #expect(await pythonClient.loadRequestCount == 1)
        #expect(await swiftClient.loadRequestCount == 0)
    }

    @Test("python compatibility lazy loads forward default-safe model-load trust policy")
    func pythonCompatibilityLazyLoadsForwardDefaultSafeModelLoadTrustPolicy() async throws {
        var model = makeTextModel(id: "registry-text", state: .modelDiscovered)
        model.routeClass = .workerRoutePythonTextCompatibility
        model.settings.ext["melix.capability.route_kind"] = "python_text_compatibility"
        let catalog = ModelCatalog(seedModels: [model])
        let swiftClient = LoaderTestingWorkerClient()
        let pythonClient = LoaderTestingWorkerClient()
        await pythonClient.setLoadResponse(
            ok: true,
            handle: "registry-text::python",
            estimatedResidentBytes: 8_192
        )
        let registry = WorkerRegistry(
            defaultTextClient: swiftClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )
        let metricsStore = MetricsStore()

        _ = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "registry-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let loadRequest = try #require(await pythonClient.lastLoadModelRequest)
        let loadedModel = try #require(await catalog.model(id: "registry-text"))
        let metrics = await metricsStore.snapshot()

        #expect(loadRequest.loadTrust.requestedMode == .modelLoadTrustDefaultSafe)
        #expect(loadRequest.loadTrust.effectiveMode == .modelLoadTrustDefaultSafe)
        #expect(loadRequest.loadTrust.policySource == "default_safe")
        #expect(loadRequest.loadTrust.routeClass == .workerRoutePythonTextCompatibility)
        #expect(loadRequest.loadTrust.loaderFamily == "python_text_compatibility")
        #expect(loadedModel.loadTrust.effectiveMode == .modelLoadTrustDefaultSafe)
        #expect(loadedModel.loadTrust.policySource == "default_safe")
        #expect(metrics.values.keys.contains("control_plane.model_load_trust_resolution_ms"))
    }

    @Test("python compatibility lazy loads forward explicit trust-remote-code opt-in")
    func pythonCompatibilityLazyLoadsForwardExplicitTrustRemoteCodeOptIn() async throws {
        var model = makeTextModel(id: "trusted-text", state: .modelDiscovered)
        model.routeClass = .workerRoutePythonTextCompatibility
        model.settings.ext["melix.capability.route_kind"] = "python_text_compatibility"
        model.settings.loadTrustMode = .modelLoadTrustTrustRemoteCode
        let catalog = ModelCatalog(seedModels: [model])
        let swiftClient = LoaderTestingWorkerClient()
        let pythonClient = LoaderTestingWorkerClient()
        await pythonClient.setLoadResponse(
            ok: true,
            handle: "trusted-text::python",
            estimatedResidentBytes: 8_192
        )
        let registry = WorkerRegistry(
            defaultTextClient: swiftClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )

        _ = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "trusted-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: MetricsStore()
        )

        let loadRequest = try #require(await pythonClient.lastLoadModelRequest)
        let loadedModel = try #require(await catalog.model(id: "trusted-text"))

        #expect(loadRequest.model.settings.loadTrustMode == .modelLoadTrustTrustRemoteCode)
        #expect(loadRequest.loadTrust.requestedMode == .modelLoadTrustTrustRemoteCode)
        #expect(loadRequest.loadTrust.effectiveMode == .modelLoadTrustTrustRemoteCode)
        #expect(loadRequest.loadTrust.policySource == "model_settings")
        #expect(loadedModel.loadTrust.requestedMode == .modelLoadTrustTrustRemoteCode)
        #expect(loadedModel.loadTrust.effectiveMode == .modelLoadTrustTrustRemoteCode)
    }

    @Test("text-capable VLM models lazy-load through the Python VLM route")
    func textCapableVLMModelsLazyLoadThroughThePythonVLMRoute() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devVLMModel()])
        let swiftClient = LoaderTestingWorkerClient()
        await swiftClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-vlm::swift",
            estimatedResidentBytes: 4_096
        )
        let pythonClient = LoaderTestingWorkerClient()
        await pythonClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-vlm::python",
            estimatedResidentBytes: 8_192
        )
        let registry = WorkerRegistry(
            defaultTextClient: swiftClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-vlm",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let loadRequest = try #require(await pythonClient.lastLoadModelRequest)
        #expect(handle == "melix-dev-vlm::python")
        #expect(loadRequest.model.modelKind == "vlm")
        #expect(loadRequest.model.ext["melix.capability.route_kind"] == "python_vlm")
        #expect(await pythonClient.loadRequestCount == 1)
        #expect(await swiftClient.loadRequestCount == 0)
    }

    @Test("Python VLM cached handles are validated against worker residency before reuse")
    func pythonVLMCachedHandlesAreValidatedAgainstWorkerResidencyBeforeReuse() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devVLMModel()])
        _ = await catalog.recordLoadSucceeded(
            id: "melix-dev-vlm",
            dispatchHandle: "melix-dev-vlm::stale",
            reason: "seed_load",
            routeKind: .pythonVLM
        )
        let runner = PythonInventoryBridgeRunner(
            loadedHandles: [],
            loadHandle: "melix-dev-vlm::reloaded"
        )
        let pythonClient = PythonBridgeWorkerClient(
            socketPath: "/tmp/melix-python-inventory-test.sock",
            runner: runner
        )
        let registry = WorkerRegistry(
            defaultTextClient: NullWorkerClient(),
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-vlm",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )
        let metrics = await metricsStore.snapshot()

        #expect(handle == "melix-dev-vlm::reloaded")
        #expect(await runner.listRequestCount == 1)
        #expect(await runner.loadRequestCount == 1)
        #expect(metrics.values["control_plane.model_stale_handle_recovery_count"] == 1)
    }

    @Test("VLM text loading falls back to ext when structured capability fields are empty")
    func vlmTextLoadingFallsBackToExtWhenStructuredCapabilityFieldsAreEmpty() async throws {
        var model = ModelCatalog.devVLMModel()
        model.modelID = "melix-dev-vlm-ext-only"
        model.supportedModalities = []
        model.supportedTasks = []
        model.settings.ext["melix.capability.supported_modalities"] = "text,image"
        model.settings.ext["melix.capability.supported_tasks"] = "vlm,generate"
        model.settings.ext["melix.model_path"] = "/tmp/melix-dev-vlm-ext-only"

        let catalog = ModelCatalog(seedModels: [model])
        let swiftClient = LoaderTestingWorkerClient()
        let pythonClient = LoaderTestingWorkerClient()
        await pythonClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-vlm-ext-only::python",
            estimatedResidentBytes: 4_096
        )
        let registry = WorkerRegistry(
            defaultTextClient: swiftClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )
        let metricsStore = MetricsStore()

        let handle = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-vlm-ext-only",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        #expect(handle == "melix-dev-vlm-ext-only::python")
        #expect(await pythonClient.loadRequestCount == 1)
        #expect(await swiftClient.loadRequestCount == 0)
    }

    @Test("lazy load falls back to estimated resident bytes when runtime stats are unavailable")
    func lazyLoadFallsBackToEstimatedResidentBytesWhenRuntimeStatsAreUnavailable() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-text::swift",
            estimatedResidentBytes: 12_288
        )
        await workerClient.setRuntimeStatsFailure(WorkerClientError.unavailable)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        _ = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let metrics = await metricsStore.snapshot()
        #expect(metrics.values["control_plane.text_first_load_estimated_resident_bytes"] == 12_288)
        #expect(metrics.values["control_plane.text_first_load_resident_bytes"] == 12_288)
    }

    @Test("missing or non-text models return model-not-ready without contacting workers")
    func missingOrNonTextModelsReturnModelNotReadyWithoutContactingWorkers() async throws {
        let workerClient = LoaderTestingWorkerClient()
        let registry = WorkerRegistry(defaultTextClient: workerClient)
        let missingCatalog = ModelCatalog(seedModels: [])
        let nonTextCatalog = ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()])
        let imageCatalog = ModelCatalog(seedModels: [ModelCatalog.devImageModel()])
        let metricsStore = MetricsStore()

        await #expect(throws: OnDemandModelLoadError.modelNotReady) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: missingCatalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }

        await #expect(throws: OnDemandModelLoadError.modelNotReady) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-embed",
                modelCatalog: nonTextCatalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }

        await #expect(throws: OnDemandModelLoadError.modelNotReady) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-image",
                modelCatalog: imageCatalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }

        #expect(await workerClient.loadRequestCount == 0)
    }

    @Test("VLM text loading honors structured capability fields before ext fallbacks")
    func vlmTextLoadingHonorsStructuredCapabilityFieldsBeforeExtFallbacks() async throws {
        var imageOnlyVLM = ModelCatalog.devVLMModel()
        imageOnlyVLM.modelID = "melix-dev-vlm-image-only"
        imageOnlyVLM.supportedModalities = ["image"]
        imageOnlyVLM.supportedTasks = ["vlm", "generate"]
        imageOnlyVLM.settings.ext["melix.capability.supported_modalities"] = "text,image"
        imageOnlyVLM.settings.ext["melix.capability.supported_tasks"] = "vlm,generate"
        imageOnlyVLM.settings.ext["melix.model_path"] = "/tmp/melix-dev-vlm-image-only"

        var noGenerateVLM = ModelCatalog.devVLMModel()
        noGenerateVLM.modelID = "melix-dev-vlm-no-generate"
        noGenerateVLM.supportedModalities = ["text", "image"]
        noGenerateVLM.supportedTasks = ["vlm"]
        noGenerateVLM.settings.ext["melix.capability.supported_modalities"] = "text,image"
        noGenerateVLM.settings.ext["melix.capability.supported_tasks"] = "vlm,generate"
        noGenerateVLM.settings.ext["melix.model_path"] = "/tmp/melix-dev-vlm-no-generate"

        let catalog = ModelCatalog(seedModels: [imageOnlyVLM, noGenerateVLM])
        let swiftClient = LoaderTestingWorkerClient()
        let pythonClient = LoaderTestingWorkerClient()
        await pythonClient.setLoadResponse(
            ok: true,
            handle: "unexpected-vlm::python",
            estimatedResidentBytes: 4_096
        )
        let registry = WorkerRegistry(
            defaultTextClient: swiftClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )
        let metricsStore = MetricsStore()

        await #expect(throws: OnDemandModelLoadError.modelNotReady) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-vlm-image-only",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }
        await #expect(throws: OnDemandModelLoadError.modelNotReady) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-vlm-no-generate",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }

        #expect(await pythonClient.loadRequestCount == 0)
        #expect(await swiftClient.loadRequestCount == 0)
    }

    @Test("worker unavailability and failed lazy loads record failed model state")
    func workerUnavailabilityAndFailedLazyLoadsRecordFailedModelState() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let unavailableMetrics = MetricsStore()

        await #expect(throws: OnDemandModelLoadError.workerUnavailable) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: nil,
                metricsStore: unavailableMetrics
            )
        }

        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: false,
            handle: "",
            estimatedResidentBytes: 0
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        await #expect(throws: OnDemandModelLoadError.workerUnavailable) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore()
            )
        }

        let model = try #require(await catalog.model(id: "melix-dev-text"))
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "lazy_text_load_failed")
    }

    @Test("failed lazy loads preserve explicit worker error codes in transition reasons")
    func failedLazyLoadsPreserveExplicitWorkerErrorCodesInTransitionReasons() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = LoaderTestingWorkerClient()
        let metricsStore = MetricsStore()
        await workerClient.setLoadResponse(
            ok: false,
            handle: "",
            estimatedResidentBytes: 0,
            errorCode: "memory_budget_exceeded",
            errorMessage: "Projected resident memory would exceed the process budget.",
            errorDetails: [
                "budget_bytes": "32768",
                "headroom_bytes": "2048",
                "required_bytes": "34816",
            ]
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        var expectedMemoryError = Melix_Worker_V1_ErrorStatus()
        expectedMemoryError.code = "memory_budget_exceeded"
        expectedMemoryError.message = "Projected resident memory would exceed the process budget."
        expectedMemoryError.details = [
            "budget_bytes": "32768",
            "headroom_bytes": "2048",
            "required_bytes": "34816",
        ]
        await #expect(throws: OnDemandModelLoadError.workerRejected(expectedMemoryError)) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: metricsStore
            )
        }

        let model = try #require(await catalog.model(id: "melix-dev-text"))
        let metrics = await metricsStore.snapshot()
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "lazy_text_load_memory_budget_exceeded")
        #expect(model.residency.memoryBudgetBytes == 32_768)
        #expect(model.residency.memoryHeadroomBytes == 2_048)
        #expect(model.residency.requiredBytes == 34_816)
        #expect(metrics.values["control_plane.text_load_memory_budget_rejection_count"] == 1)
        #expect(metrics.values["control_plane.text_load_last_budget_bytes"] == 32_768)
        #expect(metrics.values["control_plane.text_load_last_headroom_bytes"] == 2_048)
        #expect(metrics.values["control_plane.text_load_last_required_bytes"] == 34_816)
    }

    @Test("failed lazy loads persist worker model-load trust receipts")
    func failedLazyLoadsPersistWorkerModelLoadTrustReceipts() async throws {
        var model = makeTextModel(id: "unsafe-text", state: .modelDiscovered)
        model.routeClass = .workerRoutePythonTextCompatibility
        model.settings.ext["melix.capability.route_kind"] = "python_text_compatibility"
        let catalog = ModelCatalog(seedModels: [model])
        let swiftClient = LoaderTestingWorkerClient()
        let pythonClient = LoaderTestingWorkerClient()
        var workerTrust = Melix_Worker_V1_ModelLoadTrustPolicy()
        workerTrust.requestedMode = .modelLoadTrustDefaultSafe
        workerTrust.effectiveMode = .modelLoadTrustDefaultSafe
        workerTrust.policySource = "default_safe"
        workerTrust.customLoaderRequired = true
        workerTrust.customLoaderDetectionSource = "config_json:auto_map"
        workerTrust.blockReason = "custom_loader_requires_trust_remote_code"
        workerTrust.routeClass = .workerRoutePythonTextCompatibility
        workerTrust.loaderFamily = "mlx_lm"
        await pythonClient.setLoadResponse(
            ok: false,
            handle: "",
            estimatedResidentBytes: 0,
            errorCode: "unsafe_load_rejected",
            errorMessage: "Custom loader requires an explicit trust_remote_code opt-in.",
            loadTrust: workerTrust
        )
        let registry = WorkerRegistry(
            defaultTextClient: swiftClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )

        var expectedError = Melix_Worker_V1_ErrorStatus()
        expectedError.code = "unsafe_load_rejected"
        expectedError.message = "Custom loader requires an explicit trust_remote_code opt-in."
        await #expect(throws: OnDemandModelLoadError.workerRejected(expectedError)) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "unsafe-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore()
            )
        }

        let failedModel = try #require(await catalog.model(id: "unsafe-text"))
        #expect(failedModel.state == .modelFailed)
        #expect(failedModel.loadTrust.customLoaderRequired)
        #expect(failedModel.loadTrust.customLoaderDetectionSource == "config_json:auto_map")
        #expect(failedModel.loadTrust.blockReason == "custom_loader_requires_trust_remote_code")
        #expect(failedModel.loadTrust.loaderFamily == "mlx_lm")
    }

    @Test("thrown worker request failures are surfaced as worker rejections")
    func thrownWorkerRequestFailuresAreSurfacedAsWorkerRejections() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadFailure(
            WorkerClientError.requestFailed(code: "load_failed", message: "MLX load failed")
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        var expectedError = Melix_Worker_V1_ErrorStatus()
        expectedError.code = "load_failed"
        expectedError.message = "MLX load failed"
        await #expect(throws: OnDemandModelLoadError.workerRejected(expectedError)) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore()
            )
        }

        let model = try #require(await catalog.model(id: "melix-dev-text"))
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "lazy_text_load_load_failed")
    }

    @Test("unexpected lazy load failures record failed state and trust policy")
    func unexpectedLazyLoadFailuresRecordFailedStateAndTrustPolicy() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadFailure(OnDemandModelLoaderTestError())
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        await #expect(throws: OnDemandModelLoadError.workerUnavailable) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore()
            )
        }

        let model = try #require(await catalog.model(id: "melix-dev-text"))
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "lazy_text_load_failed")
        #expect(model.loadTrust.policySource == "not_applicable")
    }

    @Test("empty backend worker identity rejects lazy load before dispatch")
    func emptyBackendWorkerIdentityRejectsLazyLoadBeforeDispatch() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setHealthWorkerInstanceID("   ")
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        await #expect(throws: OnDemandModelLoadError.workerUnavailable) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore()
            )
        }

        #expect(await workerClient.loadRequestCount == 0)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("failed lazy loads forward disk-streaming mode and preserve explicit worker rejection codes")
    func failedLazyLoadsForwardDiskStreamingModeAndPreserveExplicitWorkerRejectionCodes() async throws {
        var model = ModelCatalog.devTextModel()
        model.settings.diskStreamingMode = .diskStreamingPreferDisk
        let catalog = ModelCatalog(seedModels: [model])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: false,
            handle: "",
            estimatedResidentBytes: 0,
            errorCode: "disk_streaming_unsupported",
            errorMessage: "The selected runtime does not support disk-streaming mode."
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        var expectedDiskStreamingError = Melix_Worker_V1_ErrorStatus()
        expectedDiskStreamingError.code = "disk_streaming_unsupported"
        expectedDiskStreamingError.message = "The selected runtime does not support disk-streaming mode."
        await #expect(throws: OnDemandModelLoadError.workerRejected(expectedDiskStreamingError)) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore()
            )
        }

        let loadRequest = try #require(await workerClient.lastLoadModelRequest)
        let failedModel = try #require(await catalog.model(id: "melix-dev-text"))
        #expect(loadRequest.diskStreamingMode == .diskStreamingPreferDisk)
        #expect(failedModel.state == .modelFailed)
        #expect(failedModel.residency.transitionReason == "lazy_text_load_disk_streaming_unsupported")
    }

    @Test("failed lazy loads sanitize non-identifier worker error codes in transition reasons")
    func failedLazyLoadsSanitizeNonIdentifierWorkerErrorCodesInTransitionReasons() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: false,
            handle: "",
            estimatedResidentBytes: 0,
            errorCode: "memory-budget.exceeded",
            errorMessage: "Projected resident memory would exceed the process budget."
        )
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)

        var expectedSanitizedError = Melix_Worker_V1_ErrorStatus()
        expectedSanitizedError.code = "memory-budget.exceeded"
        expectedSanitizedError.message = "Projected resident memory would exceed the process budget."
        await #expect(throws: OnDemandModelLoadError.workerRejected(expectedSanitizedError)) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: registry,
                metricsStore: MetricsStore()
            )
        }

        let model = try #require(await catalog.model(id: "melix-dev-text"))
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "lazy_text_load_memory_budget_exceeded")
    }

    @Test("eviction falls back to local unloads and records pinned protection when no routing client is available")
    func evictionFallsBackToLocalUnloadsAndRecordsPinnedProtectionWhenNoRoutingClientIsAvailable() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        let clock = ClockBox(nowUnixMs: 300_000)
        let catalog = ModelCatalog(
            seedModels: [
                makeTextModel(id: "ttl-text", state: .modelWarm, ttlSeconds: 60),
                makePinnedTextModel(id: "pinned-text"),
                ModelCatalog.devTextModel(),
            ],
            nowUnixMs: { clock.nowUnixMs }
        )
        _ = await catalog.recordLoadSucceeded(id: "ttl-text", dispatchHandle: "ttl-text::swift", reason: "seed_load")
        _ = await catalog.recordLoadSucceeded(
            id: "pinned-text",
            dispatchHandle: "pinned-text::swift",
            pinRequested: true,
            reason: "seed_load"
        )
        clock.nowUnixMs += 61_000

        let metricsStore = MetricsStore()

        await #expect(throws: OnDemandModelLoadError.workerUnavailable) {
            try await OnDemandModelLoader.ensureTextModelReady(
                modelID: "melix-dev-text",
                modelCatalog: catalog,
                workerRegistry: nil,
                metricsStore: metricsStore
            )
        }

        let evicted = try #require(await catalog.model(id: "ttl-text"))
        let protected = try #require(await catalog.model(id: "pinned-text"))
        let metrics = await metricsStore.snapshot()

        #expect(evicted.state == .modelUnloaded)
        #expect(protected.state == .modelPinned)
        #expect(metrics.values["control_plane.model_eviction_plan_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_pinned_protected_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_last_pinned_protected_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_success_count"] == 1)
    }

    @Test("eviction records lru and failure metrics for unsuccessful worker unloads")
    func evictionRecordsLruAndFailureMetricsForUnsuccessfulWorkerUnloads() async throws {
        let catalog = ModelCatalog(
            seedModels: [
                makeTextModel(id: "lru-text", state: .modelWarm),
                ModelCatalog.devTextModel(),
            ]
        )
        _ = await catalog.recordLoadSucceeded(id: "lru-text", dispatchHandle: "lru-text::swift", reason: "seed_load")

        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-text::swift",
            estimatedResidentBytes: 2_048
        )
        await workerClient.setUnloadResponse(ok: false)
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        _ = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let lruModel = try #require(await catalog.model(id: "lru-text"))
        let metrics = await metricsStore.snapshot()

        #expect(lruModel.state == .modelFailed)
        #expect(metrics.values["control_plane.model_eviction_lru_same_capability_count"] == 1)
        #expect(metrics.values["control_plane.model_eviction_failure_count"] == 1)
    }

    @Test("eviction records thrown unload failures and exposes the fallback metric bucket")
    func evictionRecordsThrownUnloadFailuresAndExposesTheFallbackMetricBucket() async throws {
        let catalog = ModelCatalog(
            seedModels: [
                makeTextModel(id: "throw-text", state: .modelWarm),
                ModelCatalog.devTextModel(),
            ]
        )
        _ = await catalog.recordLoadSucceeded(id: "throw-text", dispatchHandle: "throw-text::swift", reason: "seed_load")

        let workerClient = LoaderTestingWorkerClient()
        await workerClient.setLoadResponse(
            ok: true,
            handle: "melix-dev-text::swift",
            estimatedResidentBytes: 2_048
        )
        await workerClient.setUnloadFailure(WorkerClientError.unavailable)
        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let metricsStore = MetricsStore()

        _ = try await OnDemandModelLoader.ensureTextModelReady(
            modelID: "melix-dev-text",
            modelCatalog: catalog,
            workerRegistry: registry,
            metricsStore: metricsStore
        )

        let failed = try #require(await catalog.model(id: "throw-text"))
        let metrics = await metricsStore.snapshot()

        #expect(failed.state == .modelFailed)
        #expect(metrics.values["control_plane.model_eviction_failure_count"] == 1)
        #expect(OnDemandModelLoader.evictionMetricKey(for: "custom_reason") == "control_plane.model_eviction_other_count")
    }
}

private func makeTextModel(
    id: String,
    state: Melix_Controlplane_V1_ModelState,
    ttlSeconds: UInt32 = 0
) -> Melix_Controlplane_V1_ModelSummary {
    var model = ModelCatalog.devTextModel()
    model.modelID = id
    model.state = state
    model.settings.memoryPolicy = ttlSeconds > 0 ? .memoryResidencyTtl : .memoryResidencyEvictable
    model.settings.ttlSeconds = ttlSeconds
    switch state {
    case .modelDiscovered:
        model.residency.state = .discovered
    case .modelLoading:
        model.residency.state = .loading
    case .modelPinned:
        model.residency.state = .pinned
        model.pinned = true
    case .modelWarm:
        model.residency.state = .warm
    case .modelEvicting:
        model.residency.state = .evicting
    case .modelUnloaded:
        model.residency.state = .unloaded
    case .modelFailed:
        model.residency.state = .failed
    default:
        model.residency.state = .unspecified
    }
    return model
}

private func makePinnedTextModel(id: String) -> Melix_Controlplane_V1_ModelSummary {
    var model = makeTextModel(id: id, state: .modelPinned)
    model.settings.pinOnLoad = true
    model.settings.memoryPolicy = .memoryResidencyPinned
    model.pinned = true
    return model
}

private struct OnDemandModelLoaderTestError: Error {}

protocol OnDemandTestWorkerHealth: BackendHealthIdentifyingWorkerClientProtocol {
    func testWorkerInstanceID() async throws -> String
}

extension OnDemandTestWorkerHealth {
    func testWorkerInstanceID() async throws -> String {
        String(reflecting: Self.self)
    }

    func backendHealthIdentity() async throws -> Melix_Worker_V1_HandshakeResponse {
        var response = Melix_Worker_V1_HandshakeResponse()
        response.workerInstanceID = try await testWorkerInstanceID()
        return response
    }
}

actor LoaderTestingWorkerClient:
    WorkerRoutingClient,
    RuntimeIntrospectingWorkerClientProtocol,
    OnDemandTestWorkerHealth
{
    let staleLoadCleanupWorkerInstanceID = "stale-load-cleanup-worker"
    let staleLoadCleanupReusedHandle = "melix-dev-text::reused"

    private var loadResponse = Melix_Worker_V1_LoadModelResponse()
    private var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
    private var loadFailure: Error?
    private var unloadFailure: Error?
    private var healthWorkerInstanceID = String(reflecting: LoaderTestingWorkerClient.self)
    private var runtimeStatsResponse = Melix_Worker_V1_GetRuntimeStatsResponse()
    private var runtimeStatsFailure: Error?
    private var staleLoadCleanupRaceEnabled = false
    private var firstLoadRequest: Melix_Worker_V1_LoadModelRequest?
    private var firstLoadRequestWaiters: [CheckedContinuation<Melix_Worker_V1_LoadModelRequest, Never>] = []
    private var firstLoadRelease: CheckedContinuation<Void, Never>?
    private var residentIdentity: Melix_Worker_V1_BackendModelIdentity?

    private(set) var lastLoadModelRequest: Melix_Worker_V1_LoadModelRequest?
    private(set) var unloadHandles: [String] = []
    private(set) var loadRequestCount = 0
    private(set) var unloadRequests: [Melix_Worker_V1_UnloadModelRequest] = []
    private(set) var unloadResponseCodes: [String] = []

    func prepareStaleLoadCleanupRace() {
        staleLoadCleanupRaceEnabled = true
        healthWorkerInstanceID = staleLoadCleanupWorkerInstanceID
        loadResponse.ok = true
        loadResponse.modelHandle = staleLoadCleanupReusedHandle
        loadResponse.residency.state = .warm
    }

    func setLoadResponse(
        ok: Bool,
        handle: String,
        estimatedResidentBytes: UInt64,
        errorCode: String = "",
        errorMessage: String = "",
        errorDetails: [String: String] = [:],
        loadTrust: Melix_Worker_V1_ModelLoadTrustPolicy? = nil
    ) {
        loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = ok
        loadResponse.modelHandle = handle
        loadResponse.estimatedResidentBytes = estimatedResidentBytes
        loadResponse.residency.state = ok ? .warm : .failed
        loadResponse.error.code = errorCode
        loadResponse.error.message = errorMessage
        loadResponse.error.details = errorDetails
        if let loadTrust {
            loadResponse.loadTrust = loadTrust
        }
    }

    func setUnloadResponse(ok: Bool) {
        unloadResponse = Melix_Worker_V1_UnloadModelResponse()
        unloadResponse.ok = ok
    }

    func setLoadFailure(_ error: Error?) {
        loadFailure = error
    }

    func setUnloadFailure(_ error: Error?) {
        unloadFailure = error
    }

    func setHealthWorkerInstanceID(_ workerInstanceID: String) {
        healthWorkerInstanceID = workerInstanceID
    }

    func testWorkerInstanceID() async throws -> String {
        healthWorkerInstanceID
    }

    func setRuntimeResidentBytes(_ residentBytes: UInt64) {
        runtimeStatsResponse = Melix_Worker_V1_GetRuntimeStatsResponse()
        runtimeStatsResponse.stats.residentBytes = residentBytes
    }

    func setRuntimeStatsFailure(_ error: Error?) {
        runtimeStatsFailure = error
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        loadRequestCount += 1
        lastLoadModelRequest = request
        if let loadFailure {
            throw loadFailure
        }
        if staleLoadCleanupRaceEnabled {
            firstLoadRequest = request
            residentIdentity = request.backendIdentity
            firstLoadRequestWaiters.forEach { $0.resume(returning: request) }
            firstLoadRequestWaiters.removeAll()
            await withCheckedContinuation { continuation in
                firstLoadRelease = continuation
            }
        }
        return loadResponse
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        unloadHandles.append(request.modelHandle)
        unloadRequests.append(request)
        if let unloadFailure {
            throw unloadFailure
        }
        if staleLoadCleanupRaceEnabled,
           (!request.hasExpectedBackendIdentity || request.expectedBackendIdentity != residentIdentity) {
            var response = Melix_Worker_V1_UnloadModelResponse()
            response.error.code = "model_identity_mismatch"
            unloadResponseCodes.append(response.error.code)
            return response
        }
        return unloadResponse
    }

    func waitForFirstLoadRequest() async -> Melix_Worker_V1_LoadModelRequest {
        if let firstLoadRequest {
            return firstLoadRequest
        }
        return await withCheckedContinuation { continuation in
            firstLoadRequestWaiters.append(continuation)
        }
    }

    func installReplacement(identity: Melix_Worker_V1_BackendModelIdentity) {
        residentIdentity = identity
    }

    func releaseFirstLoad() {
        firstLoadRelease?.resume()
        firstLoadRelease = nil
    }

    func currentResidentIdentity() -> Melix_Worker_V1_BackendModelIdentity? {
        residentIdentity
    }

    func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        if let runtimeStatsFailure {
            throw runtimeStatsFailure
        }
        return runtimeStatsResponse
    }
}

private actor SharedResidencyTestingWorkerClient:
    WorkerRoutingClient,
    LoadedModelsIntrospectingWorkerClientProtocol,
    OnDemandTestWorkerHealth
{
    private var residentHandleByModelID: [String: String] = [:]
    private var residentIdentityByModelID: [String: Melix_Worker_V1_BackendModelIdentity] = [:]
    private var nextHandleOrdinal = 1
    private var listFailure: Error?

    private(set) var loadRequestCount = 0
    private(set) var listRequestCount = 0

    var loadedHandles: [String] {
        residentHandleByModelID.values.sorted()
    }

    func setListFailure(_ error: Error?) {
        listFailure = error
    }

    func forceUnload(handle: String) {
        let removedModelIDs = residentHandleByModelID.compactMap { modelID, residentHandle in
            residentHandle == handle ? modelID : nil
        }
        residentHandleByModelID = residentHandleByModelID.filter { $0.value != handle }
        for modelID in removedModelIDs {
            residentIdentityByModelID.removeValue(forKey: modelID)
        }
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        guard residentHandleByModelID.values.contains(request.execution.modelHandle) else {
            throw WorkerClientError.requestFailed(code: "not_found", message: "Model handle is not loaded.")
        }
        return AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        loadRequestCount += 1
        let handle: String
        if let residentHandle = residentHandleByModelID[request.model.modelID] {
            handle = residentHandle
        } else {
            handle = "\(request.model.modelID)::shared-\(nextHandleOrdinal)"
            nextHandleOrdinal += 1
            residentHandleByModelID[request.model.modelID] = handle
        }
        residentIdentityByModelID[request.model.modelID] = request.backendIdentity

        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = handle
        response.residency.state = .warm
        return response
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        forceUnload(handle: request.modelHandle)
        var response = Melix_Worker_V1_UnloadModelResponse()
        response.ok = true
        return response
    }

    func listLoadedModels() async throws -> Melix_Worker_V1_ListLoadedModelsResponse {
        listRequestCount += 1
        if let listFailure {
            throw listFailure
        }
        var response = Melix_Worker_V1_ListLoadedModelsResponse()
        response.modelHandles = loadedHandles
        response.loadedModels = residentHandleByModelID.map { modelID, handle in
            var loaded = Melix_Worker_V1_LoadedModelSummary()
            loaded.modelHandle = handle
            loaded.model.modelID = modelID
            if let identity = residentIdentityByModelID[modelID] {
                loaded.backendIdentity = identity
            }
            return loaded
        }
        return response
    }
}

private actor PythonInventoryBridgeRunner: WorkerBridgeRunning {
    private let loadedHandles: [String]
    private let loadHandle: String

    private(set) var listRequestCount = 0
    private(set) var loadRequestCount = 0

    init(loadedHandles: [String], loadHandle: String) {
        self.loadedHandles = loadedHandles
        self.loadHandle = loadHandle
    }

    func runUnary(command: BridgeCommand) async throws -> String {
        switch command.kind {
        case .handshake:
            var response = Melix_Worker_V1_HandshakeResponse()
            response.workerInstanceID = "python-inventory-worker"
            return try messageLine(response)
        case .listLoadedModels:
            listRequestCount += 1
            var response = Melix_Worker_V1_ListLoadedModelsResponse()
            response.modelHandles = loadedHandles
            return try messageLine(response)
        case .loadModel:
            loadRequestCount += 1
            var response = Melix_Worker_V1_LoadModelResponse()
            response.ok = true
            response.modelHandle = loadHandle
            response.residency.state = .warm
            return try messageLine(response)
        case .getRuntimeStats:
            return try messageLine(Melix_Worker_V1_GetRuntimeStatsResponse())
        default:
            throw WorkerClientError.unavailable
        }
    }

    func runStream(command: BridgeCommand) async throws -> AsyncThrowingStream<String, Error> {
        _ = command
        throw WorkerClientError.unavailable
    }

    private func messageLine<MessageType: SwiftProtobuf.Message>(
        _ message: MessageType
    ) throws -> String {
        let encoded = try message.serializedData().base64EncodedString()
        return #"{"kind":"message","message_b64":"\#(encoded)"}"#
    }
}
