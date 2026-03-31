import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Control Plane Service")
struct ControlPlaneServiceTests {
    @Test("handshake returns a typed snapshot")
    func handshakeReturnsTypedSnapshot() async throws {
        let service = ControlPlaneService()

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-1"

        let response = try await service.handshake(request)

        #expect(response.protocolVersion == "melix.controlplane.v1")
        #expect(!response.serverVersion.isEmpty)
        #expect(!response.daemonInstanceID.isEmpty)
        #expect(response.snapshot.serverState == .serverReady)
        #expect(response.features.contains("cache-metadata"))
        #expect(response.features.contains("session-graph"))
        #expect(response.features.contains("image-jobs"))
    }

    @Test("execute handles server.get_snapshot")
    func executeHandlesServerSnapshot() async throws {
        let service = ControlPlaneService()
        let request = makeServerSnapshotRequest()

        let response = try await service.execute(request)

        #expect(response.ok)
        #expect(response.requestID == request.requestID)
        #expect(response.commandType == request.commandType)
        #expect(response.server.snapshot.serverState == .serverReady)
    }

    @Test("execute handles model.list")
    func executeHandlesModelList() async throws {
        let service = ControlPlaneService()
        let request = makeListModelsRequest()

        let response = try await service.execute(request)

        #expect(response.ok)
        #expect(response.model.models.count == 1)
        #expect(response.model.models.first?.modelID == "melix-dev-text")
        #expect(response.model.models.first?.state == .modelDiscovered)
    }

    @Test("execute handles model.load and emits a state change event")
    func executeHandlesModelLoad() async throws {
        let service = ControlPlaneService()
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return try #require(await iterator.next())
        }

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let event = try await eventTask.value

        #expect(response.ok)
        #expect(response.model.model.modelID == "melix-dev-text")
        #expect(response.model.model.state == .modelWarm)
        #expect(response.model.models.first?.state == .modelWarm)
        #expect(event.eventType == "model.state_changed")
        #expect(event.modelState.modelID == "melix-dev-text")
        #expect(event.modelState.state == .modelWarm)
    }

    @Test("execute workerless model.load falls back to local catalog success")
    func executeWorkerlessModelLoadFallsBackToLocalCatalogSuccess() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let service = ControlPlaneService(modelCatalog: catalog)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(response.ok)
        #expect(model.state == .modelWarm)
        #expect(model.residency.transitionReason == "operator_load")
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::local")
    }

    @Test("execute handles model.unload and emits a state change event")
    func executeHandlesModelUnload() async throws {
        let service = ControlPlaneService()
        _ = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))

        let subscription = await service.subscribe()
        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return try #require(await iterator.next())
        }

        let response = try await service.execute(makeUnloadModelRequest(modelID: "melix-dev-text"))
        let event = try await eventTask.value

        #expect(response.ok)
        #expect(response.model.model.modelID == "melix-dev-text")
        #expect(response.model.model.state == .modelUnloaded)
        #expect(response.model.models.first?.state == .modelUnloaded)
        #expect(event.modelState.modelID == "melix-dev-text")
        #expect(event.modelState.state == .modelUnloaded)
    }

    @Test("execute handles worker-backed model.load with loading and warm transitions")
    func executeHandlesWorkerBackedModelLoadWithIntermediateTransitions() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-dev-text::swift"
        loadResponse.residency.state = .warm
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value

        #expect(response.ok)
        #expect(events.map(\.modelState.state) == [.modelLoading, .modelWarm])
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::swift")
    }

    @Test("execute worker-backed model.load succeeds without explicit error mapping")
    func executeWorkerBackedModelLoadSucceedsWithoutExplicitErrorMapping() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-dev-text::swift"
        loadResponse.residency.state = .warm
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(response.ok)
        #expect(model.state == .modelWarm)
        #expect(model.residency.transitionReason == "operator_load")
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::swift")
    }

    @Test("execute worker-backed model.load forwards adapter-set hash from model settings")
    func executeWorkerBackedModelLoadForwardsAdapterSetHashFromModelSettings() async throws {
        var seeded = ModelCatalog.devTextModel()
        seeded.settings.ext["melix.adapter_set_hash"] = "adapter-alpha"

        let catalog = ModelCatalog(seedModels: [seeded])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-dev-text::swift"
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let loadRequest = try #require(await workerClient.loadRequests.first)

        #expect(response.ok)
        #expect(loadRequest.model.modelID == "melix-dev-text")
        #expect(loadRequest.model.ext["melix.adapter_set_hash"] == "adapter-alpha")
    }

    @Test("execute returns unavailable and records failed state when worker-backed model.load fails")
    func executeReturnsUnavailableAndRecordsFailedStateWhenWorkerBackedModelLoadFails() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        await workerClient.setLoadError(WorkerClientError.unavailable)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(events.map(\.modelState.state) == [.modelLoading, .modelFailed])
        #expect(model.state == .modelFailed)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("execute worker-backed model.load maps thrown worker failures to failed state")
    func executeWorkerBackedModelLoadMapsThrownWorkerFailuresToFailedState() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        await workerClient.setLoadError(WorkerClientError.unavailable)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "operator_load_failed")
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("execute returns unavailable when worker-backed model.load returns a non-ready response")
    func executeReturnsUnavailableWhenWorkerBackedModelLoadReturnsNonReadyResponse() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = false
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(events.map(\.modelState.state) == [.modelLoading, .modelFailed])
        #expect(model.state == .modelFailed)
    }

    @Test("execute surfaces explicit memory budget rejections from worker-backed model.load")
    func executeSurfacesExplicitMemoryBudgetRejectionsFromWorkerBackedModelLoad() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = false
        loadResponse.error.code = "memory_budget_exceeded"
        loadResponse.error.message = "Projected resident memory would exceed the process budget."
        loadResponse.error.details = [
            "budget_bytes": "4500",
            "headroom_bytes": "1024",
            "required_bytes": "5120",
        ]
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(!response.ok)
        #expect(response.error.code == "memory_budget_exceeded")
        #expect(response.error.message == "Projected resident memory would exceed the process budget.")
        #expect(response.error.details["budget_bytes"] == "4500")
        #expect(events.map(\.modelState.state) == [.modelLoading, .modelFailed])
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "operator_load_memory_budget_exceeded")
    }

    @Test("execute sanitizes explicit worker error codes before recording failure transitions")
    func executeSanitizesExplicitWorkerErrorCodesBeforeRecordingFailureTransitions() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = false
        loadResponse.error.code = "memory-budget.exceeded"
        loadResponse.error.message = "Projected resident memory would exceed the process budget."
        await workerClient.setLoadResponse(loadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(!response.ok)
        #expect(response.error.code == "memory-budget.exceeded")
        #expect(model.state == .modelFailed)
        #expect(model.residency.transitionReason == "operator_load_memory_budget_exceeded")
    }

    @Test("execute handles worker-backed model.unload with evicting and unloaded transitions")
    func executeHandlesWorkerBackedModelUnloadWithIntermediateTransitions() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        _ = await catalog.recordLoadSucceeded(id: "melix-dev-text", dispatchHandle: "melix-dev-text::swift")

        let workerClient = ModelLifecycleWorkerClient()
        var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
        unloadResponse.ok = true
        await workerClient.setUnloadResponse(unloadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeUnloadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value

        #expect(response.ok)
        #expect(events.map(\.modelState.state) == [.modelEvicting, .modelUnloaded])
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("execute returns unavailable and records failed state when worker-backed model.unload fails")
    func executeReturnsUnavailableAndRecordsFailedStateWhenWorkerBackedModelUnloadFails() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        _ = await catalog.recordLoadSucceeded(id: "melix-dev-text", dispatchHandle: "melix-dev-text::swift")

        let workerClient = ModelLifecycleWorkerClient()
        await workerClient.setUnloadError(WorkerClientError.unavailable)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeUnloadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(events.map(\.modelState.state) == [.modelEvicting, .modelFailed])
        #expect(model.state == .modelFailed)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("execute falls back to local success when a worker-backed unload loses its registry")
    func executeFallsBackToLocalSuccessWhenWorkerBackedUnloadLosesItsRegistry() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devEmbeddingModel()])
        _ = await catalog.recordLoadSucceeded(id: "melix-dev-embed", dispatchHandle: "melix-dev-embed::python")
        let service = ControlPlaneService(modelCatalog: catalog)

        let response = try await service.execute(makeUnloadModelRequest(modelID: "melix-dev-embed"))
        let model = try #require(await catalog.model(id: "melix-dev-embed"))

        #expect(response.ok)
        #expect(model.state == .modelUnloaded)
        #expect(model.residency.transitionReason == "operator_unload")
    }

    @Test("execute returns unavailable when worker-backed model.unload returns a non-ok response")
    func executeReturnsUnavailableWhenWorkerBackedModelUnloadReturnsNonOkResponse() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        _ = await catalog.recordLoadSucceeded(id: "melix-dev-text", dispatchHandle: "melix-dev-text::swift")

        let workerClient = ModelLifecycleWorkerClient()
        var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
        unloadResponse.ok = false
        await workerClient.setUnloadResponse(unloadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)
        let subscription = await service.subscribe()

        let eventTask = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return [
                try #require(await iterator.next()),
                try #require(await iterator.next()),
            ]
        }

        let response = try await service.execute(makeUnloadModelRequest(modelID: "melix-dev-text"))
        let events = try await eventTask.value
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(!response.ok)
        #expect(response.error.code == "unavailable")
        #expect(events.map(\.modelState.state) == [.modelEvicting, .modelFailed])
        #expect(model.state == .modelFailed)
    }

    @Test("execute model.load opportunistically evicts ttl-expired residents before operator loads")
    func executeModelLoadEvictsTTLExpiredResidentsBeforeOperatorLoads() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        let clock = ClockBox(nowUnixMs: 100_000)
        let catalog = ModelCatalog(
            seedModels: [
                makeTextCatalogModel(
                    id: "melix-old-text",
                    state: .modelWarm,
                    ttlSeconds: 60
                ),
                ModelCatalog.devTextModel(),
            ],
            nowUnixMs: { clock.nowUnixMs }
        )
        clock.nowUnixMs += 61_000

        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-dev-text::swift"
        loadResponse.residency.state = .warm
        await workerClient.setLoadResponse(loadResponse)

        var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
        unloadResponse.ok = true
        await workerClient.setUnloadResponse(unloadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let metrics = try await service.execute(makeMetricsRequest())
        let operations = await workerClient.recordedOperations
        let evicted = try #require(await catalog.model(id: "melix-old-text"))
        let loaded = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(response.ok)
        #expect(operations == [
            "unload:melix-old-text::local",
            "load:melix-dev-text",
        ])
        #expect(evicted.state == .modelUnloaded)
        #expect(evicted.residency.transitionReason == "ttl_expired")
        #expect(loaded.state == .modelWarm)
        #expect(loaded.residency.transitionReason == "operator_load")
        #expect(metrics.ops.metrics.values["control_plane.model_eviction_ttl_count"] == 1)
        #expect(metrics.ops.metrics.values["control_plane.model_eviction_success_count"] == 1)
    }

    @Test("startChat evicts ttl-expired residents before reusing a ready text model")
    func startChatEvictsTTLExpiredResidentsBeforeReusingReadyTextModel() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        let clock = ClockBox(nowUnixMs: 200_000)
        let readyText = makeTextCatalogModel(id: "melix-dev-text", state: .modelWarm)
        let expiredText = makeTextCatalogModel(
            id: "melix-old-text",
            state: .modelWarm,
            ttlSeconds: 60
        )
        let catalog = ModelCatalog(
            seedModels: [expiredText, readyText],
            nowUnixMs: { clock.nowUnixMs }
        )
        clock.nowUnixMs += 61_000

        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-ready-eviction"),
            makeTokenExecuteEvent(requestID: "chat-ready-eviction", text: "assistant"),
            makeCompletedExecuteEvent(
                requestID: "chat-ready-eviction",
                finishReason: "stop",
                assistant: "assistant",
                reasoning: ""
            ),
        ])
        let service = ControlPlaneService(
            modelCatalog: catalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: catalog),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-ready-eviction" })
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )
        _ = try await Array(execution.stream)

        let unloadRequests = await textClient.unloadRequests
        let generated = try #require(await textClient.lastGenerateRequest)
        let evicted = try #require(await catalog.model(id: "melix-old-text"))
        let ready = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(unloadRequests.map(\.modelHandle) == ["melix-old-text::local"])
        #expect(generated.execution.modelHandle == "melix-dev-text::local")
        #expect(evicted.state == .modelUnloaded)
        #expect(evicted.residency.transitionReason == "ttl_expired")
        #expect(ready.state == .modelWarm)
    }

    @Test("execute model.load records pinned protection and lru eviction metrics")
    func executeModelLoadRecordsPinnedProtectionAndLruEvictionMetrics() async throws {
        let catalog = ModelCatalog(
            seedModels: [
                makeTextCatalogModel(id: "melix-lru-text", state: .modelWarm),
                makeTextCatalogModel(id: "melix-pinned-text", state: .modelPinned, pinOnLoad: true),
                ModelCatalog.devTextModel(),
            ]
        )
        let workerClient = ModelLifecycleWorkerClient()
        var loadResponse = Melix_Worker_V1_LoadModelResponse()
        loadResponse.ok = true
        loadResponse.modelHandle = "melix-dev-text::swift"
        loadResponse.residency.state = .warm
        await workerClient.setLoadResponse(loadResponse)

        var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
        unloadResponse.ok = true
        await workerClient.setUnloadResponse(unloadResponse)

        let registry = WorkerRegistry(defaultTextClient: workerClient, modelCatalog: catalog)
        let service = ControlPlaneService(modelCatalog: catalog, workerRegistry: registry)

        let response = try await service.execute(makeLoadModelRequest(modelID: "melix-dev-text"))
        let metrics = try await service.execute(makeMetricsRequest())
        let pinned = try #require(await catalog.model(id: "melix-pinned-text"))
        let evicted = try #require(await catalog.model(id: "melix-lru-text"))

        #expect(response.ok)
        #expect(pinned.state == .modelPinned)
        #expect(evicted.state == .modelUnloaded)
        #expect(metrics.ops.metrics.values["control_plane.model_eviction_lru_same_capability_count"] == 1)
        #expect(metrics.ops.metrics.values["control_plane.model_eviction_pinned_protected_count"] == 1)
        #expect(await service.evictionMetricKey(for: "custom_reason") == "control_plane.model_eviction_other_count")
    }

    @Test("startChat returns unavailable when lazy text loading cannot prepare the model")
    func startChatReturnsUnavailableWhenLazyTextLoadingCannotPrepareTheModel() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let service = ControlPlaneService(modelCatalog: catalog)

        await #expect(throws: ControlPlaneChatExecutionError.unavailable) {
            try await service.startChat(
                ControlPlaneChatRequest(
                    modelID: "melix-dev-text",
                    messages: [.init(role: "user", content: "hello")]
                )
            )
        }
    }

    @Test("execute handles model.set_policy and updates typed model settings")
    func executeHandlesModelSetPolicyAndUpdatesTypedModelSettings() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let response = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "alias": "Melix Text Turbo",
                    "pin_on_load": "true",
                    "memory_policy": "pinned",
                    "default_acceleration_mode": "speculative_decode",
                    "acceleration_profile_id": "draft-q4",
                ]
            )
        )

        #expect(response.ok)
        #expect(response.model.model.modelID == "melix-dev-text")
        #expect(response.model.model.settings.alias == "Melix Text Turbo")
        #expect(response.model.model.settings.pinOnLoad)
        #expect(response.model.model.settings.memoryPolicy == .memoryResidencyPinned)
        #expect(response.model.model.settings.defaultAccelerationMode == .speculativeDecode)
        #expect(response.model.model.settings.accelerationProfileID == "draft-q4")
    }

    @Test("execute handles model.get_info through the model-operations worker")
    func executeHandlesModelGetInfoThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setInfoResponse({
            var response = Melix_Worker_V1_GetModelInfoResponse()
            response.ok = true
            response.modelKind = "text"
            response.maxContext = 8192
            response.supportedParsers = ["text", "json"]
            response.supportedModalities = ["text"]
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeGetModelInfoRequest(modelID: "melix-dev-text"))
        let lastRequest = try #require(await modelOpsClient.lastInfoRequest)

        #expect(response.ok)
        #expect(lastRequest.sourceModel == "melix-dev-text")
        #expect(response.model.info.ok)
        #expect(response.model.info.modelKind == "text")
        #expect(response.model.info.maxContext == 8192)
        #expect(response.model.info.supportedParsers == ["text", "json"])
    }

    @Test("execute handles model.run_operation through the model-operations worker")
    func executeHandlesModelRunOperationThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.progress = Melix_Worker_V1_ConvertProgress()
                event.progress.stage = "write_artifact"
                event.progress.pct = 0.75
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.manifest = Melix_Worker_V1_ConvertManifest()
                event.manifest.manifestJson = #"{"operation":"quantize"}"#
                event.manifest.quantProfile = Melix_Worker_V1_QuantizationProfile()
                event.manifest.quantProfile.algorithm = "oq"
                event.manifest.quantProfile.schemaVersion = "melix.quant_profile.v1"
                event.manifest.quantProfile.quantProfileID = "q4"
                event.manifest.quantProfile.weightQuant = "q4"
                event.manifest.quantProfile.kvQuant = "q8"
                event.manifest.artifact = Melix_Worker_V1_QuantizedArtifact()
                event.manifest.artifact.schemaVersion = "melix.quantized_bundle.v1"
                event.manifest.artifact.artifactKind = "quantized_model_bundle"
                event.manifest.artifact.manifestPath = "/tmp/melix-ops/quantize.artifact/manifest.json"
                event.manifest.artifact.bundlePath = "/tmp/melix-ops/quantize.artifact"
                event.manifest.artifact.artifactBytes = 256
                event.manifest.artifact.manifestBytes = 128
                event.manifest.artifact.servingCompatible = true
                event.manifest.artifact.smokeTestRequested = true
                event.manifest.artifact.smokeTestPassed = true
                event.manifest.artifact.runtime = "mlx_text"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-ops/quantize.artifact"
                event.completed.quantProfile = Melix_Worker_V1_QuantizationProfile()
                event.completed.quantProfile.algorithm = "oq"
                event.completed.quantProfile.schemaVersion = "melix.quant_profile.v1"
                event.completed.quantProfile.quantProfileID = "q4"
                event.completed.quantProfile.weightQuant = "q4"
                event.completed.quantProfile.kvQuant = "q8"
                event.completed.artifact = Melix_Worker_V1_QuantizedArtifact()
                event.completed.artifact.schemaVersion = "melix.quantized_bundle.v1"
                event.completed.artifact.artifactKind = "quantized_model_bundle"
                event.completed.artifact.manifestPath = "/tmp/melix-ops/quantize.artifact/manifest.json"
                event.completed.artifact.bundlePath = "/tmp/melix-ops/quantize.artifact"
                event.completed.artifact.artifactBytes = 256
                event.completed.artifact.manifestBytes = 128
                event.completed.artifact.servingCompatible = true
                event.completed.artifact.smokeTestRequested = true
                event.completed.artifact.smokeTestPassed = true
                event.completed.artifact.runtime = "mlx_text"
                return event
            }(),
        ])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/melix-ops",
                weightQuant: "q4",
                kvQuant: "q8",
                ext: ["target_repo": "melix/upload-target"]
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)

        #expect(response.ok)
        #expect(lastRequest.sourceModel == "melix-dev-text")
        #expect(lastRequest.ext["operation"] == "quantize")
        #expect(lastRequest.weightQuant == "q4")
        #expect(lastRequest.kvQuant == "q8")
        #expect(lastRequest.quantProfile.algorithm == "oq")
        #expect(lastRequest.quantProfile.schemaVersion == "melix.quant_profile.v1")
        #expect(lastRequest.quantProfile.quantProfileID == "q4")
        #expect(lastRequest.quantProfile.weightQuant == "q4")
        #expect(lastRequest.quantProfile.kvQuant == "q8")
        #expect(lastRequest.ext["target_repo"] == "melix/upload-target")
        #expect(response.model.operation.ok)
        #expect(response.model.operation.operation == "quantize")
        #expect(response.model.operation.jobID == "job-123")
        #expect(response.model.operation.stage == "write_artifact")
        #expect(response.model.operation.outputPath == "/tmp/melix-ops/quantize.artifact")
        #expect(response.model.operation.manifestJson == #"{"operation":"quantize"}"#)
        #expect(response.model.operation.quantProfile.algorithm == "oq")
        #expect(response.model.operation.quantProfile.quantProfileID == "q4")
        #expect(response.model.operation.quantProfile.kvQuant == "q8")
        #expect(response.model.operation.artifact.artifactKind == "quantized_model_bundle")
        #expect(response.model.operation.artifact.manifestPath == "/tmp/melix-ops/quantize.artifact/manifest.json")
        #expect(response.model.operation.artifact.bundlePath == "/tmp/melix-ops/quantize.artifact")
        #expect(response.model.operation.artifact.artifactBytes == 256)
        #expect(response.model.operation.artifact.manifestBytes == 128)
        #expect(response.model.operation.artifact.smokeTestRequested)
        #expect(response.model.operation.artifact.smokeTestPassed)
    }

    @Test("execute prefers explicit quant profile selection for quantize operations")
    func executePrefersExplicitQuantProfileSelectionForQuantizeOperations() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-q6"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.completed = Melix_Worker_V1_ConvertCompleted()
                event.completed.outputPath = "/tmp/melix-ops/quantize.artifact"
                return event
            }(),
        ])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/melix-ops",
                quantProfileID: "q6",
                weightQuant: "",
                kvQuant: "q8"
            )
        )
        let lastRequest = try #require(await modelOpsClient.lastConvertRequest)

        #expect(response.ok)
        #expect(lastRequest.quantProfile.quantProfileID == "q6")
        #expect(lastRequest.quantProfile.weightQuant == "q6")
        #expect(lastRequest.quantProfile.kvQuant == "q8")
        #expect(lastRequest.weightQuant.isEmpty)
    }

    @Test("execute handles ops.run_doctor through the model-operations worker")
    func executeHandlesOpsRunDoctorThroughTheModelOperationsWorker() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setDoctorResponse({
            var response = Melix_Worker_V1_RunDoctorResponse()
            response.ok = true
            response.reportMarkdown = "# Melix Doctor\n\n- worker_state: idle\n"
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunDoctorRequest())
        let lastRequest = try #require(await modelOpsClient.lastDoctorRequest)

        #expect(response.ok)
        #expect(lastRequest.includeCacheDiagnostics)
        #expect(lastRequest.includeMemoryReport)
        #expect(response.ops.reportMarkdown.contains("Melix Doctor"))
    }

    @Test("execute handles ops.run_bench through the model-operations worker")
    func executeHandlesOpsRunBenchThroughTheModelOperationsWorker() async throws {
        let reportPath = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("melix-bench-report.md").path
        try "# Melix Bench\n".write(toFile: reportPath, atomically: true, encoding: .utf8)

        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setBenchEvents([
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.started = Melix_Worker_V1_BenchStarted()
                event.started.jobID = "bench-123"
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.progress = Melix_Worker_V1_BenchProgress()
                event.progress.suite = "smoke"
                event.progress.pct = 0.5
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.metric = Melix_Worker_V1_BenchMetric()
                event.metric.name = "bench.smoke.ttft_ms"
                event.metric.value = 24.45
                event.metric.unit = "ms"
                return event
            }(),
            {
                var event = Melix_Worker_V1_RunBenchEvent()
                event.completed = Melix_Worker_V1_BenchCompleted()
                event.completed.reportPath = reportPath
                return event
            }(),
        ])
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let response = try await service.execute(makeRunBenchRequest())
        let lastRequest = try #require(await modelOpsClient.lastBenchRequest)
        let snapshot = try await service.execute(makeMetricsRequest())

        #expect(response.ok)
        #expect(lastRequest.suites == ["smoke", "latency"])
        #expect(response.ops.reportPath == reportPath)
        #expect(response.ops.reportMarkdown.contains("Melix Bench"))
        #expect(response.ops.metrics.values["bench.smoke.ttft_ms"] == 24.45)
        #expect(response.ops.benchmarkJob.schemaVersion == "melix.serving_benchmark_job.v1")
        #expect(response.ops.benchmarkJob.jobID == "bench-123")
        #expect(response.ops.benchmarkJob.modelID == "melix-dev-text")
        #expect(response.ops.benchmarkJob.suites == ["smoke", "latency"])
        #expect(response.ops.benchmarkJob.status == "completed")
        #expect(response.ops.benchmarkResults.count == 1)
        #expect(response.ops.benchmarkResults[0].schemaVersion == "melix.serving_benchmark_result.v1")
        #expect(response.ops.benchmarkResults[0].jobID == "bench-123")
        #expect(response.ops.benchmarkResults[0].suite == "smoke")
        #expect(response.ops.benchmarkResults[0].metrics.count == 1)
        #expect(response.ops.benchmarkResults[0].metrics[0].name == "bench.smoke.ttft_ms")
        #expect(response.ops.benchmarkResults[0].metrics[0].unit == "ms")
        #expect(response.ops.benchmarkResults[0].metrics[0].value == 24.45)
        #expect(snapshot.ops.metrics.values["bench.smoke.ttft_ms"] == 24.45)
    }

    @Test("execute handles image.generate through the image worker and records the image job")
    func executeHandlesImageGenerateThroughTheImageWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate"
            response.job.jobID = "req-image-generate::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            response.job.artifacts = [makeWorkerArtifact(jobID: "req-image-generate::image-generate")]
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a neon fox",
                size: "512x512",
                n: 2
            )
        )
        let forwardedRequest = try #require(await imageClient.lastImageGenerateRequest)
        let snapshot = try await service.execute(makeServerSnapshotRequest())

        #expect(response.ok)
        #expect(forwardedRequest.modelHandle == "melix-dev-image::python")
        #expect(forwardedRequest.prompt == "Draw a neon fox")
        #expect(forwardedRequest.size == "512x512")
        #expect(forwardedRequest.n == 2)
        #expect(response.image.job.jobID == "req-image-generate::image-generate")
        #expect(response.image.job.state == .imageJobCompleted)
        #expect(snapshot.server.snapshot.imageJobs.contains(where: { $0.jobID == "req-image-generate::image-generate" }))
    }

    @Test("execute handles image.edit through the image worker and records artifact metadata")
    func executeHandlesImageEditThroughTheImageWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageEditResponse({
            var response = Melix_Worker_V1_ImageEditResponse()
            response.job.requestID = "req-image-edit"
            response.job.jobID = "req-image-edit::image-edit"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_edit"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            response.job.artifacts = [
                makeWorkerArtifact(jobID: "req-image-edit::image-edit", role: .imageArtifactEditSource, artifactID: "source"),
                makeWorkerArtifact(jobID: "req-image-edit::image-edit", role: .imageArtifactMask, artifactID: "mask"),
                makeWorkerArtifact(jobID: "req-image-edit::image-edit", role: .imageArtifactGenerated, artifactID: "output"),
            ]
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageEditRequest(
                modelID: "melix-dev-image",
                prompt: "Replace the sky",
                imageURI: "file:///tmp/source.png",
                maskURI: "file:///tmp/mask.png",
                strength: 0.6
            )
        )
        let forwardedRequest = try #require(await imageClient.lastImageEditRequest)

        #expect(response.ok)
        #expect(forwardedRequest.modelHandle == "melix-dev-image::python")
        #expect(forwardedRequest.prompt == "Replace the sky")
        #expect(forwardedRequest.imageUri == "file:///tmp/source.png")
        #expect(forwardedRequest.maskUri == "file:///tmp/mask.png")
        #expect(forwardedRequest.strength == 0.6)
        #expect(response.image.job.jobID == "req-image-edit::image-edit")
        #expect(response.image.job.artifacts.count == 3)
        #expect(response.image.job.artifacts.last?.role == .imageArtifactGenerated)
    }

    @Test("execute returns unimplemented for image commands without a kind")
    func executeReturnsUnimplementedForEmptyImageCommands() async throws {
        let service = ControlPlaneService()
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-image-empty"
        request.commandType = "image.empty"
        request.image = Melix_Controlplane_V1_ImageCommand()

        let response = try await service.execute(request)

        #expect(response.ok == false)
        #expect(response.error.code == "unimplemented")
    }

    @Test("execute returns not_ready when image generation is requested before the model is loaded")
    func executeReturnsNotReadyForImageGenerateWithoutLoadedModel() async throws {
        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )

        #expect(response.ok == false)
        #expect(response.error.code == "not_ready")
    }

    @Test("execute returns unavailable when the image worker is missing")
    func executeReturnsUnavailableForImageGenerateWithoutWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let service = ControlPlaneService(modelCatalog: modelCatalog)

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
    }

    @Test("execute returns invalid_argument when image edits omit the source image")
    func executeReturnsInvalidArgumentForImageEditWithoutSource() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageEditRequest(
                modelID: "melix-dev-image",
                prompt: "Replace the sky",
                imageURI: "",
                maskURI: "",
                strength: 1
            )
        )

        #expect(response.ok == false)
        #expect(response.error.code == "invalid_argument")
    }

    @Test("execute surfaces worker image.generate failures and records the failed job state")
    func executeSurfacesImageGenerateWorkerFailures() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate"
            response.job.jobID = "req-image-generate::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobFailed
            response.job.error.code = "runtime_error"
            response.job.error.message = "GPU pressure"
            response.error.code = "runtime_error"
            response.error.message = "GPU pressure"
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok == false)
        #expect(response.error.code == "runtime_error")
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "runtime_error")
    }

    @Test("execute records a failed image generate when the worker throws")
    func executeRecordsFailedImageGenerateWhenWorkerThrows() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateError(ImageWorkerFailure.synthetic)
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(recordedJob.jobID == "req-image-generate::image-generate")
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "unavailable")
    }

    @Test("execute fills an implicit image job identifier when the worker omits one")
    func executeFillsImplicitImageJobIdentifier() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate-empty-job"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobCompleted
            response.job.progress.stage = "completed"
            response.job.progress.pct = 1
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )

        #expect(response.ok)
        #expect(response.image.job.jobID == "req-image-generate::image-generate")
    }

    @Test("execute records failed image phases when the worker reports imageJobFailed without an error payload")
    func executeRecordsFailedImagePhaseWithoutWorkerErrorPayload() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate-failed-phase"
            response.job.jobID = "req-image-generate-failed-phase::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobFailed
            response.job.progress.stage = "failed"
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                requestID: "req-image-generate-failed-phase",
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok)
        #expect(response.image.job.state == .imageJobFailed)
        #expect(recordedJob.state == .imageJobFailed)
    }

    @Test("execute records a failed image edit when the worker throws")
    func executeRecordsFailedImageEditWhenWorkerThrows() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageEditError(ImageWorkerFailure.synthetic)
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageEditRequest(
                modelID: "melix-dev-image",
                prompt: "Replace the sky",
                imageURI: "file:///tmp/source.png",
                maskURI: "file:///tmp/mask.png",
                strength: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(recordedJob.jobID == "req-image-edit::image-edit")
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "unavailable")
    }

    @Test("execute returns unavailable when image.generate admission fails generically")
    func executeReturnsUnavailableWhenImageGenerateAdmissionFailsGenerically() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageJobReadModel = ImageJobReadModel()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: StubImageJobAdmissionController(acquireError: ImageWorkerFailure.synthetic),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                requestID: "req-image-generate-admission-failure",
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let recordedJob = try #require(await imageJobReadModel.job(requestID: "req-image-generate-admission-failure"))

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message.contains("Image admission failed"))
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "unavailable")
    }

    @Test("execute returns unavailable when image.edit admission fails generically")
    func executeReturnsUnavailableWhenImageEditAdmissionFailsGenerically() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageJobReadModel = ImageJobReadModel()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: StubImageJobAdmissionController(acquireError: ImageWorkerFailure.synthetic),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageEditRequest(
                requestID: "req-image-edit-admission-failure",
                modelID: "melix-dev-image",
                prompt: "Replace the sky",
                imageURI: "file:///tmp/source.png",
                maskURI: "",
                strength: 1
            )
        )
        let recordedJob = try #require(await imageJobReadModel.job(requestID: "req-image-edit-admission-failure"))

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message.contains("Image admission failed"))
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "unavailable")
    }

    @Test("execute records runtime_error when the image worker returns a non-terminal generate state")
    func executeMarksInvalidGenerateTerminalStatesAsRuntimeErrors() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = ScriptedImageWorkerClient()
        await imageClient.setImageGenerateResponse({
            var response = Melix_Worker_V1_ImageGenerateResponse()
            response.job.requestID = "req-image-generate"
            response.job.jobID = "req-image-generate::image-generate"
            response.job.modelHandle = "melix-dev-image::python"
            response.job.operation = "image_generate"
            response.job.state = .imageJobRunning
            response.job.progress.stage = "render"
            response.job.progress.pct = 0.4
            return response
        }())
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeImageGenerateRequest(
                modelID: "melix-dev-image",
                prompt: "Draw a fox",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())
        let recordedJob = try #require(snapshot.server.snapshot.imageJobs.first)

        #expect(response.ok)
        #expect(response.image.job.state == .imageJobRunning)
        #expect(recordedJob.state == .imageJobFailed)
        #expect(recordedJob.error.code == "runtime_error")
    }

    @Test("ops.cancel_request cancels queued image work before it reaches the worker")
    func cancelRequestCancelsQueuedImageWorkBeforeWorkerDispatch() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = BlockingImageWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobAdmissionController: ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let firstTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-generate-1",
                    modelID: "melix-dev-image",
                    prompt: "Draw a fox",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected first image request to start") {
            await imageClient.startedRequestIDs == ["req-image-generate-1"]
        }

        let queuedTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-generate-2",
                    modelID: "melix-dev-image",
                    prompt: "Draw another fox",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await Task.sleep(for: .milliseconds(50))

        let cancelResponse = try await service.execute(
            makeCancelRequest(requestID: "req-image-generate-2")
        )
        let queuedResponse = try await queuedTask.value
        await imageClient.finishGenerate(requestID: "req-image-generate-1")
        _ = try await firstTask.value
        let snapshot = try await service.execute(makeServerSnapshotRequest())

        #expect(cancelResponse.ok)
        #expect(queuedResponse.ok == false)
        #expect(queuedResponse.error.code == "cancelled")
        #expect(await imageClient.startedRequestIDs == ["req-image-generate-1"])
        #expect(snapshot.server.snapshot.imageJobs.contains {
            $0.requestID == "req-image-generate-2" && $0.state == .imageJobCanceled
        })
    }

    @Test("image.edit returns cancelled when queued admission is aborted before execution")
    func executeReturnsCancelledWhenQueuedImageEditAdmissionIsAborted() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = BlockingImageWorkerClient()
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let firstTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-edit-cancel-active",
                    modelID: "melix-dev-image",
                    prompt: "Hold the image worker",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected active image request to start") {
            await imageClient.startedRequestIDs == ["req-image-edit-cancel-active"]
        }

        let queuedTask = Task {
            try await service.execute(
                makeImageEditRequest(
                    requestID: "req-image-edit-cancel-queued",
                    modelID: "melix-dev-image",
                    prompt: "Cancel this edit",
                    imageURI: "file:///tmp/source.png",
                    maskURI: "",
                    strength: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected queued image edit") {
            await imageJobReadModel.job(requestID: "req-image-edit-cancel-queued")?.state == .imageJobQueued
        }

        let disposition = await admissionController.cancel(requestID: "req-image-edit-cancel-queued")
        let queuedResponse = try await queuedTask.value
        let cancelledJob = try #require(await imageJobReadModel.job(requestID: "req-image-edit-cancel-queued"))

        await imageClient.finishGenerate(requestID: "req-image-edit-cancel-active")
        _ = try await firstTask.value

        #expect(disposition == .queued)
        #expect(queuedResponse.ok == false)
        #expect(queuedResponse.error.code == "cancelled")
        #expect(cancelledJob.state == .imageJobCanceled)
    }

    @Test("ops.cancel_request aborts running image work through the worker")
    func cancelRequestAbortsRunningImageWorkThroughWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = BlockingImageWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobAdmissionController: ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let runningTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-running",
                    modelID: "melix-dev-image",
                    prompt: "Draw a wolf",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected image request to start") {
            await imageClient.startedRequestIDs == ["req-image-running"]
        }

        let cancelResponse = try await service.execute(
            makeCancelRequest(requestID: "req-image-running")
        )
        let runningResponse = try await runningTask.value
        let snapshot = try await service.execute(makeServerSnapshotRequest())

        #expect(cancelResponse.ok)
        #expect(runningResponse.ok == false)
        #expect(runningResponse.error.code == "cancelled")
        #expect(await imageClient.abortedRequestIDs == ["req-image-running"])
        #expect(snapshot.server.snapshot.imageJobs.contains {
            $0.requestID == "req-image-running" && $0.state == .imageJobCanceled
        })
    }

    @Test("ops.cancel_request returns not_found when the image request is unknown")
    func cancelRequestReturnsNotFoundForUnknownImageWork() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeCancelRequest(requestID: "req-image-missing")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "not_found")
        #expect(response.error.message == "Unknown request ID.")
    }

    @Test("ops.cancel_request returns unavailable when a running image job loses its worker")
    func cancelRequestReturnsUnavailableWhenRunningImageWorkHasNoWorker() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)
        await imageJobReadModel.recordQueued(
            requestID: "req-image-orphaned",
            jobID: "req-image-orphaned::image-generate",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        try await admissionController.acquire(
            requestID: "req-image-orphaned",
            laneHint: "image.generate.background",
            workerID: "image-worker-1"
        )
        await imageJobReadModel.recordRunning(
            jobID: "req-image-orphaned::image-generate",
            workerID: "image-worker-1",
            pct: 0.25
        )
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController
        )

        let response = try await service.execute(
            makeCancelRequest(requestID: "req-image-orphaned")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message == "Image worker is unavailable.")
    }

    @Test("ops.cancel_request returns not_found when the image worker says the request is no longer active")
    func cancelRequestReturnsNotFoundWhenImageAbortReturnsFalse() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)
        await imageJobReadModel.recordQueued(
            requestID: "req-image-stale",
            jobID: "req-image-stale::image-generate",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        try await admissionController.acquire(
            requestID: "req-image-stale",
            laneHint: "image.generate.background",
            workerID: "image-worker-1"
        )
        await imageJobReadModel.recordRunning(
            jobID: "req-image-stale::image-generate",
            workerID: "image-worker-1",
            pct: 0.5
        )
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: AbortFalseImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeCancelRequest(requestID: "req-image-stale")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "not_found")
        #expect(response.error.message == "Image request is no longer active.")
    }

    @Test("ops.cancel_request returns unavailable when the running image worker abort throws")
    func cancelRequestReturnsUnavailableWhenImageAbortThrows() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageJobReadModel = ImageJobReadModel()
        let admissionController = ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 1)
        await imageJobReadModel.recordQueued(
            requestID: "req-image-running-throws",
            jobID: "job-image-running-throws",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        try await admissionController.acquire(
            requestID: "req-image-running-throws",
            laneHint: "image.generate.background",
            workerID: "image-worker-1"
        )
        await imageJobReadModel.recordRunning(
            jobID: "job-image-running-throws",
            workerID: "image-worker-1",
            pct: 0.5
        )
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: admissionController,
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ThrowingAbortImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeCancelRequest(requestID: "req-image-running-throws")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message.contains("Image cancel failed"))
    }

    @Test("ops.cancel_request returns not_found when the image admission controller no longer tracks the request")
    func cancelRequestReturnsNotFoundWhenImageAdmissionControllerNoLongerTracksRequest() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageJobReadModel = ImageJobReadModel()
        await imageJobReadModel.recordQueued(
            requestID: "req-image-lost",
            jobID: "job-image-lost",
            modelID: "melix-dev-image",
            operation: "image_generate",
            lane: "image.generate.background"
        )
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobReadModel: imageJobReadModel,
            imageJobAdmissionController: StubImageJobAdmissionController(cancelDisposition: .notFound),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: ScriptedImageWorkerClient(),
                modelCatalog: modelCatalog
            )
        )

        let response = try await service.execute(
            makeCancelRequest(requestID: "req-image-lost")
        )

        #expect(response.ok == false)
        #expect(response.error.code == "not_found")
        #expect(response.error.message == "Image request is no longer active.")
    }

    @Test("ops.cancel_request returns ok when the text request coordinator cancels an active request")
    func cancelRequestReturnsOkWhenTextCoordinatorCancelsActiveRequest() async throws {
        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")
        let textClient = BlockingAbortTextWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: modelCatalog)
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "cancel this")]
            )
        )
        try await waitForControlPlaneCondition("expected text request to start") {
            await textClient.startedRequestIDs.contains(execution.requestID)
        }

        let response = try await service.execute(makeCancelRequest(requestID: execution.requestID))

        #expect(response.ok)
        #expect(response.ops.reportMarkdown == "cancel_requested")
    }

    @Test("ops.cancel_request returns unavailable when the text request coordinator abort throws")
    func cancelRequestReturnsUnavailableWhenTextCoordinatorAbortThrows() async throws {
        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")
        let textClient = BlockingAbortTextWorkerClient(abortError: WorkerClientError.unavailable)
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: modelCatalog)
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "cancel this")]
            )
        )
        try await waitForControlPlaneCondition("expected text request to start") {
            await textClient.startedRequestIDs.contains(execution.requestID)
        }

        let response = try await service.execute(makeCancelRequest(requestID: execution.requestID))

        #expect(response.ok == false)
        #expect(response.error.code == "unavailable")
        #expect(response.error.message.contains("Cancel request failed"))
    }

    @Test("image.generate returns resource_exhausted when the background queue is saturated")
    func executeReturnsResourceExhaustedWhenImageGenerateQueueIsSaturated() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = BlockingImageWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobAdmissionController: ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 0),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let firstTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-saturated-1",
                    modelID: "melix-dev-image",
                    prompt: "Hold the image worker",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected first image request to start") {
            await imageClient.startedRequestIDs == ["req-image-saturated-1"]
        }

        let saturatedResponse = try await service.execute(
            makeImageGenerateRequest(
                requestID: "req-image-saturated-2",
                modelID: "melix-dev-image",
                prompt: "This request should saturate",
                size: "1024x1024",
                n: 1
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())

        await imageClient.finishGenerate(requestID: "req-image-saturated-1")
        _ = try await firstTask.value

        #expect(saturatedResponse.ok == false)
        #expect(saturatedResponse.error.code == "resource_exhausted")
        #expect(snapshot.server.snapshot.imageJobs.contains {
            $0.requestID == "req-image-saturated-2" &&
            $0.state == .imageJobFailed &&
            $0.error.code == "resource_exhausted"
        })
    }

    @Test("image.edit returns resource_exhausted when the background queue is saturated")
    func executeReturnsResourceExhaustedWhenImageEditQueueIsSaturated() async throws {
        let modelCatalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        _ = await modelCatalog.loadModel(id: "melix-dev-image", dispatchHandle: "melix-dev-image::python")
        let imageClient = BlockingImageWorkerClient()
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            imageJobAdmissionController: ImageJobAdmissionController(maxConcurrentJobs: 1, maxQueuedJobs: 0),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                pythonCompatibilityClient: imageClient,
                modelCatalog: modelCatalog
            )
        )

        let firstTask = Task {
            try await service.execute(
                makeImageGenerateRequest(
                    requestID: "req-image-edit-saturated-1",
                    modelID: "melix-dev-image",
                    prompt: "Keep the image worker busy",
                    size: "1024x1024",
                    n: 1
                )
            )
        }
        try await waitForControlPlaneCondition("expected first image request to start") {
            await imageClient.startedRequestIDs == ["req-image-edit-saturated-1"]
        }

        let saturatedResponse = try await service.execute(
            makeImageEditRequest(
                requestID: "req-image-edit-saturated-2",
                modelID: "melix-dev-image",
                prompt: "This edit should saturate",
                imageURI: "file:///tmp/source.png",
                maskURI: "",
                strength: 0.7
            )
        )
        let snapshot = try await service.execute(makeServerSnapshotRequest())

        await imageClient.finishGenerate(requestID: "req-image-edit-saturated-1")
        _ = try await firstTask.value

        #expect(saturatedResponse.ok == false)
        #expect(saturatedResponse.error.code == "resource_exhausted")
        #expect(snapshot.server.snapshot.imageJobs.contains {
            $0.requestID == "req-image-edit-saturated-2" &&
            $0.state == .imageJobFailed &&
            $0.error.code == "resource_exhausted"
        })
    }

    @Test("startChat reuses the request coordinator and streams typed chat events")
    func startChatReusesTheRequestCoordinatorAndStreamsTypedChatEvents() async throws {
        let modelCatalog = ModelCatalog()
        _ = await modelCatalog.loadModel(id: "melix-dev-text")
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-service"),
            makeTokenExecuteEvent(requestID: "chat-service", text: "assistant"),
            makeReasoningExecuteEvent(requestID: "chat-service", text: "trace"),
            makeToolExecuteEvent(requestID: "chat-service", callID: "tool-1", toolName: "search", arguments: #"{"q":"melix"}"#),
            makeUsageExecuteEvent(requestID: "chat-service", promptTokens: 3, completionTokens: 5),
            makeCompletedExecuteEvent(requestID: "chat-service", finishReason: "stop", assistant: "assistant", reasoning: "trace"),
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient)
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )
        var events: [ControlPlaneChatStreamEvent] = []
        for try await event in execution.stream {
            events.append(event)
        }

        #expect(execution.modelID == "melix-dev-text")
        #expect(events.contains(where: {
            if case .queued(let lane, _, _) = $0 { return lane == "text.decode.interactive" }
            return false
        }))
        #expect(events.contains(where: {
            if case .reasoningDelta("trace") = $0 { return true }
            return false
        }))
        #expect(events.contains(where: {
            if case .toolCallDelta(let callID, let toolName, _) = $0 {
                return callID == "tool-1" && toolName == "search"
            }
            return false
        }))
    }

    @Test("startChat applies model OCR defaults for OCR models")
    func startChatAppliesModelOCRDefaultsForOCRModels() async throws {
        var ocrModel = ModelCatalog.devOCRModel()
        ocrModel.state = .modelWarm
        let modelCatalog = ModelCatalog(seedModels: [ocrModel])
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-ocr-service"),
            makeCompletedExecuteEvent(
                requestID: "chat-ocr-service",
                finishReason: "stop",
                assistant: "done",
                reasoning: ""
            ),
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-ocr-service" })
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-ocr",
                messages: [.init(role: "user", content: "Read this image.")]
            )
        )
        _ = try await Array(execution.stream)
        let generated = try #require(await textClient.lastGenerateRequest)

        #expect(execution.modelID == "melix-dev-ocr")
        #expect(generated.execution.modelHandle == "melix-dev-ocr::local")
        #expect(generated.sampling.stop == ["<ocr:end>"])
        #expect(generated.execution.ext["melix.ocr.prompt_profile_id"] == "ocr-default-v1")
        #expect(generated.execution.ext["melix.ocr.prompt_source"] == "request")
        #expect(generated.execution.ext["melix.ocr.sampling_source"] == "model")
    }

    @Test("startChat lazily loads a discovered text model before streaming")
    func startChatLazilyLoadsDiscoveredTextModel() async throws {
        let modelCatalog = ModelCatalog()
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-lazy"),
            makeTokenExecuteEvent(requestID: "chat-lazy", text: "assistant"),
            makeCompletedExecuteEvent(
                requestID: "chat-lazy",
                finishReason: "stop",
                assistant: "assistant",
                reasoning: ""
            )
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: modelCatalog),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-lazy" })
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )
        let loadRequest = try #require(await textClient.lastLoadModelRequest)
        let generated = try #require(await textClient.lastGenerateRequest)
        let model = await modelCatalog.model(id: "melix-dev-text")

        _ = try await Array(execution.stream)

        #expect(loadRequest.model.modelID == "melix-dev-text")
        #expect(loadRequest.pinOnLoad == false)
        #expect(generated.execution.modelHandle == "melix-dev-text")
        #expect(model?.state == .modelWarm)
    }

    @Test("startChat lazy text loads preserve adapter-set hash in worker requests")
    func startChatLazyTextLoadsPreserveAdapterSetHashInWorkerRequests() async throws {
        var seeded = ModelCatalog.devTextModel()
        seeded.state = .modelDiscovered
        seeded.settings.ext["melix.adapter_set_hash"] = "adapter-alpha"

        let modelCatalog = ModelCatalog(seedModels: [seeded])
        let textClient = ScriptedChatWorkerClient(events: [
            makeQueuedExecuteEvent(requestID: "chat-lazy-adapter"),
            makeCompletedExecuteEvent(
                requestID: "chat-lazy-adapter",
                finishReason: "stop",
                assistant: "assistant",
                reasoning: ""
            ),
        ])
        let service = ControlPlaneService(
            modelCatalog: modelCatalog,
            workerRegistry: WorkerRegistry(defaultTextClient: textClient, modelCatalog: modelCatalog),
            chatTranslator: ChatRequestTranslator(requestIDGenerator: { "chat-lazy-adapter" })
        )

        let execution = try await service.startChat(
            ControlPlaneChatRequest(
                modelID: "melix-dev-text",
                messages: [.init(role: "user", content: "hello")]
            )
        )

        _ = try await Array(execution.stream)
        let loadRequest = try #require(await textClient.lastLoadModelRequest)

        #expect(loadRequest.model.ext["melix.adapter_set_hash"] == "adapter-alpha")
    }

    @Test("execute maps fallback model policy values")
    func executeMapsFallbackModelPolicyValues() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let response = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "type_override": "mlx-text",
                    "ttl_seconds": "600",
                    "pin_on_load": "no",
                    "memory_policy": "ttl",
                    "default_acceleration_mode": "active_kv_quantized",
                    "custom_hint": "prefetch",
                ]
            )
        )

        #expect(response.ok)
        #expect(response.model.model.settings.typeOverride == "mlx-text")
        #expect(response.model.model.settings.ttlSeconds == 600)
        #expect(response.model.model.settings.pinOnLoad == false)
        #expect(response.model.model.settings.memoryPolicy == .memoryResidencyTtl)
        #expect(response.model.model.settings.defaultAccelerationMode == .activeKvQuantized)
        #expect(response.model.model.settings.ext["custom_hint"] == "prefetch")
    }

    @Test("execute maps sparse prefill model policy values")
    func executeMapsSparsePrefillModelPolicyValues() async throws {
        let service = ControlPlaneService(modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()))

        let response = try await service.execute(
            makeSetModelPolicyRequest(
                modelID: "melix-dev-text",
                values: [
                    "default_acceleration_mode": "sparse_prefill",
                    "acceleration_profile_id": "structured-user",
                ]
            )
        )

        #expect(response.ok)
        #expect(response.model.model.settings.defaultAccelerationMode == .sparsePrefill)
        #expect(response.model.model.settings.accelerationProfileID == "structured-user")
    }

    @Test("execute surfaces structured errors for missing or unavailable model tools")
    func executeSurfacesStructuredErrorsForMissingOrUnavailableModelTools() async throws {
        let unavailableService = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(defaultTextClient: NullWorkerClient())
        )

        let missingPolicy = try await unavailableService.execute(
            makeSetModelPolicyRequest(modelID: "missing-model", values: [:])
        )
        let missingInfo = try await unavailableService.execute(
            makeGetModelInfoRequest(modelID: "missing-model")
        )
        let unavailableInfo = try await unavailableService.execute(
            makeGetModelInfoRequest(modelID: "melix-dev-text")
        )
        let unavailableOperation = try await unavailableService.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/melix-ops",
                weightQuant: "q4",
                kvQuant: "q8"
            )
        )

        #expect(!missingPolicy.ok)
        #expect(missingPolicy.error.code == "not_found")
        #expect(!missingInfo.ok)
        #expect(missingInfo.error.code == "not_found")
        #expect(!unavailableInfo.ok)
        #expect(unavailableInfo.error.code == "unavailable")
        #expect(!unavailableOperation.ok)
        #expect(unavailableOperation.error.code == "unavailable")
    }

    @Test("execute surfaces worker-side failures for model info and model operations")
    func executeSurfacesWorkerSideFailuresForModelInfoAndOperations() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setInfoResponse({
            var response = Melix_Worker_V1_GetModelInfoResponse()
            response.ok = false
            response.error = Melix_Worker_V1_ErrorStatus()
            response.error.code = "invalid_model"
            response.error.message = "Model metadata unavailable."
            return response
        }())
        await modelOpsClient.setConvertEvents([
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.started = Melix_Worker_V1_ConvertStarted()
                event.started.jobID = "job-failed"
                return event
            }(),
            {
                var event = Melix_Worker_V1_ConvertModelEvent()
                event.failed = Melix_Worker_V1_ConvertFailed()
                event.failed.error = Melix_Worker_V1_ErrorStatus()
                event.failed.error.code = "convert_failed"
                event.failed.error.message = "Quantization failed."
                event.failed.error.retriable = false
                return event
            }(),
            Melix_Worker_V1_ConvertModelEvent(),
        ])

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let infoResponse = try await service.execute(makeGetModelInfoRequest(modelID: "melix-dev-text"))
        let operationResponse = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/melix-ops",
                weightQuant: "q4",
                kvQuant: "q8"
            )
        )

        #expect(!infoResponse.ok)
        #expect(infoResponse.error.code == "invalid_model")
        #expect(infoResponse.error.message == "Model metadata unavailable.")
        #expect(!operationResponse.ok)
        #expect(operationResponse.error.code == "convert_failed")
        #expect(operationResponse.error.message == "Quantization failed.")
    }

    @Test("execute surfaces thrown model info and operation worker errors")
    func executeSurfacesThrownModelInfoAndOperationWorkerErrors() async throws {
        let modelOpsClient = ScriptedModelOperationsWorkerClient()
        await modelOpsClient.setInfoError(TestWorkerError(description: "info transport down"))
        await modelOpsClient.setConvertError(TestWorkerError(description: "operation transport down"))

        let service = ControlPlaneService(
            modelCatalog: ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels()),
            workerRegistry: WorkerRegistry(
                defaultTextClient: NullWorkerClient(),
                modelOperationsClient: modelOpsClient
            )
        )

        let infoResponse = try await service.execute(makeGetModelInfoRequest(modelID: "melix-dev-text"))
        let operationResponse = try await service.execute(
            makeRunModelOperationRequest(
                modelID: "melix-dev-text",
                operation: "upload",
                outputDir: "/tmp/melix-upload",
                weightQuant: "",
                kvQuant: ""
            )
        )

        #expect(!infoResponse.ok)
        #expect(infoResponse.error.code == "unavailable")
        #expect(infoResponse.error.message.contains("info transport down"))
        #expect(!operationResponse.ok)
        #expect(operationResponse.error.code == "unavailable")
        #expect(operationResponse.error.message.contains("operation transport down"))
    }

    @Test("execute returns not found for unknown model operations")
    func executeReturnsNotFoundForUnknownModelOperations() async throws {
        let service = ControlPlaneService()

        let loadResponse = try await service.execute(makeLoadModelRequest(modelID: "missing-model"))
        let unloadResponse = try await service.execute(makeUnloadModelRequest(modelID: "missing-model"))

        #expect(!loadResponse.ok)
        #expect(loadResponse.error.code == "not_found")
        #expect(!unloadResponse.ok)
        #expect(unloadResponse.error.code == "not_found")
    }

    @Test("execute handles ops.get_metrics")
    func executeHandlesOpsMetrics() async throws {
        let service = ControlPlaneService()
        let response = try await service.execute(makeMetricsRequest())

        #expect(response.ok)
        #expect(response.ops.metrics.values["requests.inflight"] == 0)
        #expect(response.ops.metrics.values["workers.connected"] == 0)
    }

    @Test("execute handles cache.get_snapshot with typed cache metadata")
    func executeHandlesCacheSnapshot() async throws {
        let cacheStore = CacheMetadataStore(snapshot: makeCacheSnapshot())
        let service = ControlPlaneService(cacheMetadataStore: cacheStore)

        let response = try await service.execute(makeCacheSnapshotRequest())

        #expect(response.ok)
        #expect(response.cache.summary.blockCount == 4)
        #expect(response.cache.summary.compressionRatio == 2.5)
        #expect(response.cache.snapshot.scopes.count == 1)
        #expect(response.cache.snapshot.hotPrefixes.count == 1)
        #expect(response.cache.snapshot.snapshots.first?.snapshotID == "snap-1")
    }

    @Test("execute handles session.get_state with typed branch metadata")
    func executeHandlesSessionState() async throws {
        let sessionStore = SessionGraphStore(sessions: [makeSessionState()])
        let service = ControlPlaneService(sessionGraphStore: sessionStore)

        let response = try await service.execute(makeSessionStateRequest(sessionID: "session-1"))

        #expect(response.ok)
        #expect(response.session.session.sessionID == "session-1")
        #expect(response.session.session.activeBranchID == "branch-main")
        #expect(response.session.session.branches.count == 2)
        #expect(response.session.session.availableSnapshots.first?.snapshotID == "snap-1")
        #expect(response.session.session.branches.first?.headCacheKey.scope.modelID == "melix-dev-text")
    }

    @Test("execute returns not found for unknown session state")
    func executeReturnsNotFoundForUnknownSessionState() async throws {
        let service = ControlPlaneService()
        let response = try await service.execute(makeSessionStateRequest(sessionID: "missing-session"))

        #expect(!response.ok)
        #expect(response.error.code == "not_found")
    }

    @Test("execute handles session lifecycle mutations and publishes typed state events")
    func executeHandlesSessionLifecycleMutations() async throws {
        let service = ControlPlaneService()
        let subscription = await service.subscribe()

        let created = try await service.execute(makeSessionCreateRequest())
        #expect(created.ok)
        let sessionID = created.session.session.sessionID
        #expect(!sessionID.isEmpty)
        #expect(created.session.session.activeBranchID == "branch-main")

        let branched = try await service.execute(
            makeCreateBranchRequest(sessionID: sessionID, parentBranchID: "branch-main")
        )
        #expect(branched.ok)
        #expect(branched.session.session.branches.count == 2)
        let derivedBranchID = branched.session.session.activeBranchID
        #expect(!derivedBranchID.isEmpty)
        #expect(derivedBranchID != "branch-main")

        var iterator = subscription.stream.makeAsyncIterator()
        let firstEvent = await iterator.next()
        let secondEvent = await iterator.next()
        #expect(firstEvent?.eventType == "session.state_changed")
        #expect(firstEvent?.source == "session_graph")
        #expect(secondEvent?.eventType == "session.state_changed")
        #expect(secondEvent?.source == "session_graph")
        #expect(secondEvent?.sessionState.state.activeBranchID == derivedBranchID)
    }

    @Test("execute handles tool registration, resume, and close for sessions")
    func executeHandlesToolResumeAndCloseForSessions() async throws {
        let sessionStore = SessionGraphStore(
            sessions: [makeSessionState()],
            nowUnixMs: { 5_000 }
        )
        let service = ControlPlaneService(sessionGraphStore: sessionStore)

        let registered = try await service.execute(
            makeRegisterToolResultRequest(
                sessionID: "session-1",
                branchID: "branch-alt",
                toolCallID: "tool-99"
            )
        )
        #expect(registered.ok)
        #expect(registered.session.session.activeBranchID == "branch-alt")
        #expect(registered.session.session.latestToolCallID == "tool-99")

        let resumed = try await service.execute(
            makeResumeAfterToolRequest(
                sessionID: "session-1",
                branchID: "branch-alt",
                snapshotID: "snap-tool"
            )
        )
        #expect(resumed.ok)
        #expect(resumed.session.session.latestSnapshotID == "snap-tool")
        #expect(resumed.session.session.branches.last?.resumeSnapshotID == "snap-tool")

        let closed = try await service.execute(makeCloseSessionRequest(sessionID: "session-1"))
        #expect(closed.ok)
        #expect(closed.session.session.sessionID == "session-1")

        let missing = try await service.execute(makeSessionStateRequest(sessionID: "session-1"))
        #expect(!missing.ok)
        #expect(missing.error.code == "not_found")
    }

    @Test("execute returns not found for invalid session mutation requests")
    func executeReturnsNotFoundForInvalidSessionMutations() async throws {
        let sessionStore = SessionGraphStore(sessions: [makeSessionState()])
        let service = ControlPlaneService(sessionGraphStore: sessionStore)

        let missingSession = try await service.execute(
            makeCreateBranchRequest(sessionID: "missing-session", parentBranchID: "branch-main")
        )
        let missingBranch = try await service.execute(
            makeRegisterToolResultRequest(
                sessionID: "session-1",
                branchID: "branch-missing",
                toolCallID: "tool-404"
            )
        )
        let missingResumeBranch = try await service.execute(
            makeResumeAfterToolRequest(
                sessionID: "session-1",
                branchID: "branch-missing",
                snapshotID: "snap-404"
            )
        )
        let missingClose = try await service.execute(makeCloseSessionRequest(sessionID: "missing-session"))

        #expect(!missingSession.ok)
        #expect(missingSession.error.code == "not_found")
        #expect(!missingBranch.ok)
        #expect(missingBranch.error.code == "not_found")
        #expect(!missingResumeBranch.ok)
        #expect(missingResumeBranch.error.code == "not_found")
        #expect(!missingClose.ok)
        #expect(missingClose.error.code == "not_found")
    }

    @Test("session mutation responses preserve correlation metadata")
    func sessionMutationResponsesPreserveCorrelationMetadata() async throws {
        let service = ControlPlaneService()
        var request = makeSessionCreateRequest()
        request.correlationID = "corr-session"
        request.causationID = "cause-session"

        let response = try await service.execute(request)

        #expect(response.ok)
        #expect(response.requestID == request.requestID)
        #expect(response.commandType == request.commandType)
        #expect(response.correlationID == "corr-session")
        #expect(response.causationID == "cause-session")
    }

    @Test("handshake includes live scheduler queue summary")
    func handshakeIncludesLiveSchedulerQueueSummary() async throws {
        let schedulerReadModel = SchedulerReadModel()
        _ = await schedulerReadModel.recordAdmitted(
            requestID: "req-live-queue",
            laneHint: "text.decode.interactive",
            priority: 100,
            workerID: "swift-text-worker",
            admissionLatencyMs: 3
        )
        let service = ControlPlaneService(schedulerReadModel: schedulerReadModel)

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-live-queue"

        let response = try await service.handshake(request)
        let interactiveLane = response.snapshot.queues.lanes.first { lane in
            lane.laneID == "text.decode.interactive"
        }

        #expect(response.snapshot.queues.activeRequests == 1)
        #expect(response.snapshot.queues.admittedRequests == 1)
        #expect(response.snapshot.queues.admissionLatencyMs == 3)
        #expect(response.snapshot.queues.backpressure == 1)
        #expect(interactiveLane?.activeRequests == 1)
        #expect(interactiveLane?.backpressure == 1)
    }

    @Test("handshake includes cache summary and session summaries")
    func handshakeIncludesCacheAndSessionSummaries() async throws {
        let cacheStore = CacheMetadataStore(snapshot: makeCacheSnapshot())
        let sessionStore = SessionGraphStore(sessions: [makeSessionState()])
        let service = ControlPlaneService(
            cacheMetadataStore: cacheStore,
            sessionGraphStore: sessionStore
        )

        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = "ui-session-cache"

        let response = try await service.handshake(request)

        #expect(response.snapshot.cache.blockCount == 4)
        #expect(response.snapshot.cache.hotPrefixes.count == 1)
        #expect(response.snapshot.sessions.count == 1)
        #expect(response.snapshot.sessions.first?.sessionID == "session-1")
        #expect(response.snapshot.sessions.first?.branchCount == 2)
    }

    @Test("execute returns unimplemented for unsupported command families")
    func executeReturnsUnimplementedForUnsupportedCommandFamilies() async throws {
        let service = ControlPlaneService()
        let response = try await service.execute(makePresetRequest())

        #expect(!response.ok)
        #expect(response.requestID == "req-preset-list")
        #expect(response.commandType == "preset.list")
        #expect(response.error.code == "unimplemented")
    }

    @Test("execute returns unimplemented for unsupported server, model, and ops variants")
    func executeReturnsUnimplementedForUnsupportedVariants() async throws {
        let service = ControlPlaneService()

        let serverResponse = try await service.execute(makeServerShutdownRequest())
        let modelResponse = try await service.execute(makeModelPinRequest())
        let opsResponse = try await service.execute(makeOpsTraceRequest())

        #expect(!serverResponse.ok)
        #expect(serverResponse.error.code == "unimplemented")
        #expect(!modelResponse.ok)
        #expect(modelResponse.error.code == "unimplemented")
        #expect(!opsResponse.ok)
        #expect(opsResponse.error.code == "unimplemented")
    }

    @Test("unsubscribe closes the subscription stream")
    func unsubscribeClosesSubscriptionStream() async throws {
        let service = ControlPlaneService()
        let subscription = await service.subscribe()
        await service.unsubscribe(subscription.subscriptionID)

        var iterator = subscription.stream.makeAsyncIterator()
        let next = await iterator.next()

        #expect(next == nil)
    }

    private func makeServerSnapshotRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-snapshot"
        request.commandType = "server.get_snapshot"
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.getSnapshot = Melix_Controlplane_V1_GetServerSnapshot()
        return request
    }

    private func makeListModelsRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-list"
        request.commandType = "model.list"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.list = Melix_Controlplane_V1_ListModels()
        return request
    }

    private func makeLoadModelRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-load-\(modelID)"
        request.commandType = "model.load"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.load = Melix_Controlplane_V1_LoadModel()
        request.model.load.modelID = modelID
        return request
    }

    private func makeUnloadModelRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-unload-\(modelID)"
        request.commandType = "model.unload"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.unload = Melix_Controlplane_V1_UnloadModel()
        request.model.unload.modelID = modelID
        return request
    }

    private func makeImageGenerateRequest(
        requestID: String = "req-image-generate",
        modelID: String,
        prompt: String,
        size: String,
        n: UInt32
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = requestID
        request.commandType = "image.generate"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.generate = Melix_Controlplane_V1_GenerateImage()
        request.image.generate.modelID = modelID
        request.image.generate.prompt = prompt
        request.image.generate.size = size
        request.image.generate.n = n
        request.image.generate.responseFormat = "png"
        return request
    }

    private func makeImageEditRequest(
        requestID: String = "req-image-edit",
        modelID: String,
        prompt: String,
        imageURI: String,
        maskURI: String,
        strength: Float
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = requestID
        request.commandType = "image.edit"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.edit = Melix_Controlplane_V1_EditImage()
        request.image.edit.modelID = modelID
        request.image.edit.prompt = prompt
        request.image.edit.imageUri = imageURI
        request.image.edit.maskUri = maskURI
        request.image.edit.strength = strength
        request.image.edit.size = "1024x1024"
        request.image.edit.n = 1
        request.image.edit.responseFormat = "png"
        return request
    }

    private func makeMetricsRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-metrics"
        request.commandType = "ops.get_metrics"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.getMetrics = Melix_Controlplane_V1_GetMetricsSnapshot()
        return request
    }

    private func makeRunDoctorRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-doctor"
        request.commandType = "ops.run_doctor"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.runDoctor = Melix_Controlplane_V1_RunDoctor()
        return request
    }

    private func makeRunBenchRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-bench"
        request.commandType = "ops.run_bench"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.runBench = Melix_Controlplane_V1_RunBench()
        return request
    }

    private func makeCancelRequest(
        requestID targetRequestID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-cancel-\(targetRequestID)"
        request.commandType = "ops.cancel_request"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.cancelRequest = Melix_Controlplane_V1_CancelRequest()
        request.ops.cancelRequest.requestID = targetRequestID
        return request
    }

    private func makeCacheSnapshotRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-cache-snapshot"
        request.commandType = "cache.get_snapshot"
        request.cache = Melix_Controlplane_V1_CacheCommand()
        request.cache.getSnapshot = Melix_Controlplane_V1_GetCacheSnapshot()
        return request
    }

    private func makeSessionStateRequest(sessionID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-state-\(sessionID)"
        request.commandType = "session.get_state"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.getState = Melix_Controlplane_V1_GetSessionState()
        request.session.getState.sessionID = sessionID
        return request
    }

    private func makeSessionCreateRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-create"
        request.commandType = "session.create"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.createSession = Melix_Controlplane_V1_CreateSession()
        return request
    }

    private func makeCreateBranchRequest(
        sessionID: String,
        parentBranchID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-branch-\(sessionID)"
        request.commandType = "session.create_branch"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.createBranch = Melix_Controlplane_V1_CreateBranch()
        request.session.createBranch.sessionID = sessionID
        request.session.createBranch.parentBranchID = parentBranchID
        return request
    }

    private func makeRegisterToolResultRequest(
        sessionID: String,
        branchID: String,
        toolCallID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-tool-\(toolCallID)"
        request.commandType = "session.register_tool_result"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.registerToolResult = Melix_Controlplane_V1_RegisterToolResult()
        request.session.registerToolResult.sessionID = sessionID
        request.session.registerToolResult.branchID = branchID
        request.session.registerToolResult.toolCallID = toolCallID
        return request
    }

    private func makeResumeAfterToolRequest(
        sessionID: String,
        branchID: String,
        snapshotID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-resume-\(snapshotID)"
        request.commandType = "session.resume_after_tool"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.resumeAfterTool = Melix_Controlplane_V1_ResumeAfterTool()
        request.session.resumeAfterTool.sessionID = sessionID
        request.session.resumeAfterTool.branchID = branchID
        request.session.resumeAfterTool.snapshotID = snapshotID
        return request
    }

    private func makeCloseSessionRequest(sessionID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-session-close-\(sessionID)"
        request.commandType = "session.close"
        request.session = Melix_Controlplane_V1_SessionCommand()
        request.session.closeSession = Melix_Controlplane_V1_CloseSession()
        request.session.closeSession.sessionID = sessionID
        return request
    }

    private func makePresetRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-preset-list"
        request.commandType = "preset.list"
        request.preset = Melix_Controlplane_V1_PresetCommand()
        request.preset.list = Melix_Controlplane_V1_ListPresets()
        return request
    }

    private func makeServerShutdownRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-server-stop"
        request.commandType = "server.stop"
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.stop = Melix_Controlplane_V1_StopServer()
        return request
    }

    private func makeModelPinRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-pin"
        request.commandType = "model.pin"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.pin = Melix_Controlplane_V1_PinModel()
        request.model.pin.modelID = "melix-dev-text"
        return request
    }

    private func makeOpsTraceRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-ops-tail-logs"
        request.commandType = "ops.tail_logs"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.tailLogs = Melix_Controlplane_V1_TailLogs()
        return request
    }

    private func makeSetModelPolicyRequest(
        modelID: String,
        values: [String: String]
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-set-policy-\(modelID)"
        request.commandType = "model.set_policy"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.setPolicy = Melix_Controlplane_V1_SetModelPolicy()
        request.model.setPolicy.modelID = modelID
        request.model.setPolicy.values = values
        return request
    }

    private func makeGetModelInfoRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-get-info-\(modelID)"
        request.commandType = "model.get_info"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.getInfo = Melix_Controlplane_V1_GetModelInfo()
        request.model.getInfo.modelID = modelID
        return request
    }

    private func makeRunModelOperationRequest(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String = "",
        weightQuant: String,
        kvQuant: String,
        ext: [String: String] = [:]
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "req-model-run-operation-\(modelID)-\(operation)"
        request.commandType = "model.run_operation"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.runOperation = Melix_Controlplane_V1_RunModelOperation()
        request.model.runOperation.modelID = modelID
        request.model.runOperation.operation = operation
        request.model.runOperation.outputDir = outputDir
        request.model.runOperation.weightQuant = weightQuant
        request.model.runOperation.kvQuant = kvQuant
        request.model.runOperation.generateManifest = true
        request.model.runOperation.runSmokeTest = true
        request.model.runOperation.ext = ext
        if !quantProfileID.isEmpty {
            request.model.runOperation.quantProfile = Melix_Controlplane_V1_QuantizationProfile()
            request.model.runOperation.quantProfile.algorithm = "oq"
            request.model.runOperation.quantProfile.schemaVersion = "melix.quant_profile.v1"
            request.model.runOperation.quantProfile.quantProfileID = quantProfileID
            request.model.runOperation.quantProfile.weightQuant = quantProfileID
            request.model.runOperation.quantProfile.kvQuant = kvQuant
        }
        return request
    }

    private func makeCacheSnapshot() -> Melix_Controlplane_V1_CacheSnapshot {
        var summary = Melix_Controlplane_V1_CacheSummary()
        summary.l1Bytes = 2048
        summary.l2Bytes = 8192
        summary.blockCount = 4
        summary.checkpointCount = 1
        summary.compressionRatio = 2.5
        summary.l2RestoreHitRate = 0.5

        var cacheKey = Melix_Controlplane_V1_CacheKey()
        cacheKey.prefixHash = Data([0xAA, 0xBB])
        cacheKey.scope = Melix_Controlplane_V1_CacheScopeKey()
        cacheKey.scope.modelID = "melix-dev-text"
        cacheKey.scope.revision = "main"
        cacheKey.scope.tokenizerHash = "tok-1"
        cacheKey.scope.quantProfileID = "q4"

        var prefix = Melix_Controlplane_V1_PrefixRef()
        prefix.prefixID = "prefix-1"
        prefix.cacheKey = cacheKey
        prefix.tokenLength = 64
        prefix.tier = "l1"
        prefix.pinned = true

        var block = Melix_Controlplane_V1_CacheBlockRef()
        block.blockID = "block-1"
        block.tokenLength = 64
        block.bytes = 2048

        var snapshotRef = Melix_Controlplane_V1_SnapshotRef()
        snapshotRef.snapshotID = "snap-1"
        snapshotRef.tokenBoundary = 64
        snapshotRef.requestID = "req-main"
        snapshotRef.sessionID = "session-1"
        snapshotRef.branchID = "branch-main"
        snapshotRef.checkpointID = "ckpt-main"

        var scope = Melix_Controlplane_V1_CacheScopeSummary()
        scope.scopeID = "scope-1"
        scope.scope = cacheKey.scope
        scope.l1Bytes = 2048
        scope.l2Bytes = 8192
        scope.blockCount = 4
        scope.prefixCount = 1
        scope.snapshotCount = 1
        scope.hotBlocks = [block]
        scope.recentSnapshots = [snapshotRef]

        summary.hotKeys = [cacheKey]
        summary.hotPrefixes = [prefix]
        summary.recentSnapshots = [snapshotRef]

        var snapshot = Melix_Controlplane_V1_CacheSnapshot()
        snapshot.summary = summary
        snapshot.scopes = [scope]
        snapshot.pinnedPrefixes = [prefix]
        snapshot.hotPrefixes = [prefix]
        snapshot.snapshots = [snapshotRef]
        return snapshot
    }

    private func makeSessionState() -> Melix_Controlplane_V1_SessionState {
        var cacheKey = Melix_Controlplane_V1_CacheKey()
        cacheKey.prefixHash = Data([0xAA])
        cacheKey.scope = Melix_Controlplane_V1_CacheScopeKey()
        cacheKey.scope.modelID = "melix-dev-text"
        cacheKey.scope.revision = "main"

        var branchMain = Melix_Controlplane_V1_BranchState()
        branchMain.branchID = "branch-main"
        branchMain.parentBranchID = ""
        branchMain.headRequestID = "req-main"
        branchMain.headCheckpointID = "ckpt-main"
        branchMain.resumeSnapshotID = "snap-1"
        branchMain.lastToolCallID = "tool-1"
        branchMain.label = "main"
        branchMain.createdAtUnixMs = 1000
        branchMain.updatedAtUnixMs = 2000
        branchMain.headCacheKey = cacheKey

        var branchAlt = Melix_Controlplane_V1_BranchState()
        branchAlt.branchID = "branch-alt"
        branchAlt.parentBranchID = "branch-main"
        branchAlt.headRequestID = "req-alt"
        branchAlt.headCheckpointID = "ckpt-alt"
        branchAlt.resumeSnapshotID = "snap-2"
        branchAlt.lastToolCallID = "tool-2"
        branchAlt.label = "alternate"
        branchAlt.createdAtUnixMs = 3000
        branchAlt.updatedAtUnixMs = 4000
        branchAlt.headCacheKey = cacheKey

        var snapshot = Melix_Controlplane_V1_SnapshotRef()
        snapshot.snapshotID = "snap-1"
        snapshot.tokenBoundary = 64
        snapshot.requestID = "req-main"
        snapshot.sessionID = "session-1"
        snapshot.branchID = "branch-main"
        snapshot.checkpointID = "ckpt-main"

        var session = Melix_Controlplane_V1_SessionState()
        session.sessionID = "session-1"
        session.branches = [branchMain, branchAlt]
        session.activeBranchID = "branch-main"
        session.latestRequestID = "req-main"
        session.latestCheckpointID = "ckpt-main"
        session.latestSnapshotID = "snap-1"
        session.createdAtUnixMs = 1000
        session.updatedAtUnixMs = 4000
        session.latestToolCallID = "tool-2"
        session.availableSnapshots = [snapshot]
        return session
    }
}

private actor ScriptedImageWorkerClient: WorkerRoutingClient, NonTextInferenceWorkerClientProtocol {
    private(set) var lastImageGenerateRequest: Melix_Worker_V1_ImageGenerateRequest?
    private(set) var lastImageEditRequest: Melix_Worker_V1_ImageEditRequest?
    private var imageGenerateResponse = Melix_Worker_V1_ImageGenerateResponse()
    private var imageEditResponse = Melix_Worker_V1_ImageEditResponse()
    private var imageGenerateError: Error?
    private var imageEditError: Error?

    func setImageGenerateResponse(_ response: Melix_Worker_V1_ImageGenerateResponse) {
        imageGenerateResponse = response
        imageGenerateError = nil
    }

    func setImageEditResponse(_ response: Melix_Worker_V1_ImageEditResponse) {
        imageEditResponse = response
        imageEditError = nil
    }

    func setImageGenerateError(_ error: Error) {
        imageGenerateError = error
    }

    func setImageEditError(_ error: Error) {
        imageEditError = error
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
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        Melix_Worker_V1_EmbedResponse()
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        Melix_Worker_V1_RerankResponse()
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        Melix_Worker_V1_TranscribeResponse()
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        Melix_Worker_V1_SpeakResponse()
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        lastImageGenerateRequest = request
        if let imageGenerateError {
            throw imageGenerateError
        }
        return imageGenerateResponse
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        lastImageEditRequest = request
        if let imageEditError {
            throw imageEditError
        }
        return imageEditResponse
    }
}

private enum ImageWorkerFailure: Error {
    case synthetic
}

private actor BlockingImageWorkerClient: WorkerRoutingClient, NonTextInferenceWorkerClientProtocol {
    private var generateRequests: [String: Melix_Worker_V1_ImageGenerateRequest] = [:]
    private var generateContinuations: [String: CheckedContinuation<Melix_Worker_V1_ImageGenerateResponse, Error>] = [:]

    private(set) var startedRequestIDs: [String] = []
    private(set) var abortedRequestIDs: [String] = []

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
        abortedRequestIDs.append(requestID)
        guard let request = generateRequests.removeValue(forKey: requestID),
              let continuation = generateContinuations.removeValue(forKey: requestID) else {
            return false
        }

        var response = Melix_Worker_V1_ImageGenerateResponse()
        response.job.requestID = requestID
        response.job.jobID = "\(requestID)::image-generate"
        response.job.modelHandle = request.modelHandle
        response.job.operation = "image_generate"
        response.job.state = .imageJobCanceled
        response.job.progress.stage = "canceled"
        response.job.error.code = "cancelled"
        response.job.error.message = "Image generation was canceled."
        response.error.code = "cancelled"
        response.error.message = "Image generation was canceled."
        continuation.resume(returning: response)
        return true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        Melix_Worker_V1_EmbedResponse()
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        Melix_Worker_V1_RerankResponse()
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        Melix_Worker_V1_TranscribeResponse()
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        Melix_Worker_V1_SpeakResponse()
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        let requestID = request.id.requestID
        startedRequestIDs.append(requestID)
        generateRequests[requestID] = request
        return try await withCheckedThrowingContinuation { continuation in
            generateContinuations[requestID] = continuation
        }
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        Melix_Worker_V1_ImageEditResponse()
    }

    func finishGenerate(requestID: String) {
        guard let request = generateRequests.removeValue(forKey: requestID),
              let continuation = generateContinuations.removeValue(forKey: requestID) else {
            return
        }

        var response = Melix_Worker_V1_ImageGenerateResponse()
        response.job.requestID = requestID
        response.job.jobID = "\(requestID)::image-generate"
        response.job.modelHandle = request.modelHandle
        response.job.operation = "image_generate"
        response.job.state = .imageJobCompleted
        response.job.progress.stage = "completed"
        response.job.progress.pct = 1
        response.job.artifacts = [makeWorkerArtifact(jobID: "\(requestID)::image-generate")]
        continuation.resume(returning: response)
    }
}

private actor AbortFalseImageWorkerClient: WorkerRoutingClient, NonTextInferenceWorkerClientProtocol {
    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        return AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        _ = request
        return Melix_Worker_V1_EmbedResponse()
    }

    func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        _ = request
        return Melix_Worker_V1_RerankResponse()
    }

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        _ = request
        return Melix_Worker_V1_TranscribeResponse()
    }

    func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        _ = request
        return Melix_Worker_V1_SpeakResponse()
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        _ = request
        return Melix_Worker_V1_ImageGenerateResponse()
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        _ = request
        return Melix_Worker_V1_ImageEditResponse()
    }
}

private actor ThrowingAbortImageWorkerClient: WorkerRoutingClient, NonTextInferenceWorkerClientProtocol {
    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        return AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        throw WorkerClientError.unavailable
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "\(request.model.modelID)::python"
        return response
    }

    func embed(request: Melix_Worker_V1_EmbedRequest) async throws -> Melix_Worker_V1_EmbedResponse {
        _ = request
        return Melix_Worker_V1_EmbedResponse()
    }

    func rerank(request: Melix_Worker_V1_RerankRequest) async throws -> Melix_Worker_V1_RerankResponse {
        _ = request
        return Melix_Worker_V1_RerankResponse()
    }

    func transcribe(request: Melix_Worker_V1_TranscribeRequest) async throws -> Melix_Worker_V1_TranscribeResponse {
        _ = request
        return Melix_Worker_V1_TranscribeResponse()
    }

    func speak(request: Melix_Worker_V1_SpeakRequest) async throws -> Melix_Worker_V1_SpeakResponse {
        _ = request
        return Melix_Worker_V1_SpeakResponse()
    }

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        _ = request
        return Melix_Worker_V1_ImageGenerateResponse()
    }

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        _ = request
        return Melix_Worker_V1_ImageEditResponse()
    }
}

private actor StubImageJobAdmissionController: ImageJobAdmissionControlling {
    private let acquireError: Error?
    private let cancelDisposition: ImageJobCancelDisposition

    init(
        acquireError: Error? = nil,
        cancelDisposition: ImageJobCancelDisposition = .running
    ) {
        self.acquireError = acquireError
        self.cancelDisposition = cancelDisposition
    }

    func acquire(
        requestID: String,
        laneHint: String,
        workerID: String,
        priority: Int32
    ) async throws {
        _ = requestID
        _ = laneHint
        _ = workerID
        _ = priority
        if let acquireError {
            throw acquireError
        }
    }

    func finish(
        requestID: String,
        phase: Melix_Controlplane_V1_RequestPhase,
        workerID: String?
    ) async {
        _ = requestID
        _ = phase
        _ = workerID
    }

    func cancel(requestID: String) async -> ImageJobCancelDisposition {
        _ = requestID
        return cancelDisposition
    }
}

private actor BlockingAbortTextWorkerClient: WorkerRoutingClient {
    private let abortError: Error?
    private var continuations: [String: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>.Continuation] = [:]

    private(set) var startedRequestIDs: [String] = []

    init(abortError: Error? = nil) {
        self.abortError = abortError
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        let requestID = request.execution.id.requestID
        startedRequestIDs.append(requestID)
        return AsyncThrowingStream { continuation in
            continuations[requestID] = continuation
        }
    }

    func abort(requestID: String) async throws -> Bool {
        if let abortError {
            throw abortError
        }
        guard let continuation = continuations.removeValue(forKey: requestID) else {
            return false
        }
        continuation.finish()
        return true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.modelHandle = request.model.modelID
        return response
    }
}

private func makeWorkerArtifact(
    jobID: String,
    role: Melix_Worker_V1_ImageArtifactRole = .imageArtifactGenerated,
    artifactID: String = "artifact-0"
) -> Melix_Worker_V1_ImageArtifactMetadata {
    var artifact = Melix_Worker_V1_ImageArtifactMetadata()
    artifact.artifactID = "\(jobID)::\(artifactID)"
    artifact.jobID = jobID
    artifact.role = role
    artifact.mimeType = "image/png"
    artifact.format = "png"
    artifact.width = 512
    artifact.height = 512
    artifact.byteLength = 32
    artifact.storageUri = "/tmp/\(artifactID).png"
    artifact.sha256 = "sha256-\(artifactID)"
    artifact.variantIndex = 0
    return artifact
}

private func waitForControlPlaneCondition(
    _ description: String,
    timeout: Duration = .milliseconds(500),
    pollInterval: Duration = .milliseconds(10),
    condition: @escaping @Sendable () async -> Bool
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if await condition() {
            return
        }
        try await Task.sleep(for: pollInterval)
    }
    throw ControlPlaneConditionTimeoutError(description: description)
}

private struct ControlPlaneConditionTimeoutError: Error, CustomStringConvertible {
    let description: String
}

private actor ModelLifecycleWorkerClient: WorkerRoutingClient {
    private var loadResponse = Melix_Worker_V1_LoadModelResponse()
    private var unloadResponse = Melix_Worker_V1_UnloadModelResponse()
    private var loadError: Error?
    private var unloadError: Error?
    private(set) var loadRequests: [Melix_Worker_V1_LoadModelRequest] = []
    private(set) var unloadRequests: [Melix_Worker_V1_UnloadModelRequest] = []
    private(set) var recordedOperations: [String] = []

    func setLoadResponse(_ response: Melix_Worker_V1_LoadModelResponse) {
        loadResponse = response
    }

    func setUnloadResponse(_ response: Melix_Worker_V1_UnloadModelResponse) {
        unloadResponse = response
    }

    func setLoadError(_ error: Error?) {
        loadError = error
    }

    func setUnloadError(_ error: Error?) {
        unloadError = error
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        loadRequests.append(request)
        recordedOperations.append("load:\(request.model.modelID)")
        if let loadError {
            throw loadError
        }
        return loadResponse
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        unloadRequests.append(request)
        recordedOperations.append("unload:\(request.modelHandle)")
        if let unloadError {
            throw unloadError
        }
        return unloadResponse
    }
}

private actor ScriptedModelOperationsWorkerClient: WorkerRoutingClient, ModelOperationsWorkerClientProtocol {
    private(set) var lastInfoRequest: Melix_Worker_V1_GetModelInfoRequest?
    private(set) var lastConvertRequest: Melix_Worker_V1_ConvertModelRequest?
    private(set) var lastDoctorRequest: Melix_Worker_V1_RunDoctorRequest?
    private(set) var lastBenchRequest: Melix_Worker_V1_RunBenchRequest?
    private var infoResponse = Melix_Worker_V1_GetModelInfoResponse()
    private var convertEvents: [Melix_Worker_V1_ConvertModelEvent] = []
    private var doctorResponse = Melix_Worker_V1_RunDoctorResponse()
    private var benchEvents: [Melix_Worker_V1_RunBenchEvent] = []
    private var infoError: Error?
    private var convertError: Error?
    private var doctorError: Error?
    private var benchError: Error?

    func setInfoResponse(_ response: Melix_Worker_V1_GetModelInfoResponse) {
        infoResponse = response
    }

    func setConvertEvents(_ events: [Melix_Worker_V1_ConvertModelEvent]) {
        convertEvents = events
    }

    func setDoctorResponse(_ response: Melix_Worker_V1_RunDoctorResponse) {
        doctorResponse = response
    }

    func setBenchEvents(_ events: [Melix_Worker_V1_RunBenchEvent]) {
        benchEvents = events
    }

    func setInfoError(_ error: Error?) {
        infoError = error
    }

    func setConvertError(_ error: Error?) {
        convertError = error
    }

    func setDoctorError(_ error: Error?) {
        doctorError = error
    }

    func setBenchError(_ error: Error?) {
        benchError = error
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        _ = request
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func getModelInfo(
        request: Melix_Worker_V1_GetModelInfoRequest
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse {
        lastInfoRequest = request
        if let infoError {
            throw infoError
        }
        return infoResponse
    }

    func convertModel(
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error> {
        lastConvertRequest = request
        if let convertError {
            throw convertError
        }
        let events = convertEvents
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func runDoctor(
        request: Melix_Worker_V1_RunDoctorRequest
    ) async throws -> Melix_Worker_V1_RunDoctorResponse {
        lastDoctorRequest = request
        if let doctorError {
            throw doctorError
        }
        return doctorResponse
    }

    func runBench(
        request: Melix_Worker_V1_RunBenchRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_RunBenchEvent, Error> {
        lastBenchRequest = request
        if let benchError {
            throw benchError
        }
        let events = benchEvents
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }
}

private actor ScriptedChatWorkerClient: WorkerRoutingClient {
    private let events: [Melix_Worker_V1_ExecuteEvent]
    private(set) var lastGenerateRequest: Melix_Worker_V1_GenerateRequest?
    private(set) var lastLoadModelRequest: Melix_Worker_V1_LoadModelRequest?
    private(set) var unloadRequests: [Melix_Worker_V1_UnloadModelRequest] = []

    init(events: [Melix_Worker_V1_ExecuteEvent]) {
        self.events = events
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        lastGenerateRequest = request
        let events = self.events
        return AsyncThrowingStream { continuation in
            for event in events {
                continuation.yield(event)
            }
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        _ = requestID
        return false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        lastLoadModelRequest = request
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = request.model.modelID
        return response
    }

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        unloadRequests.append(request)
        var response = Melix_Worker_V1_UnloadModelResponse()
        response.ok = true
        return response
    }
}

private func makeTextCatalogModel(
    id: String,
    state: Melix_Controlplane_V1_ModelState,
    ttlSeconds: UInt32 = 0,
    pinOnLoad: Bool = false
) -> Melix_Controlplane_V1_ModelSummary {
    var model = ModelCatalog.devTextModel()
    model.modelID = id
    model.state = state
    if ttlSeconds > 0 {
        model.settings.ttlSeconds = ttlSeconds
        model.settings.memoryPolicy = .memoryResidencyTtl
    }
    if pinOnLoad {
        model.settings.pinOnLoad = true
        model.settings.memoryPolicy = .memoryResidencyPinned
        model.pinned = true
    }
    return model
}

private func makeQueuedExecuteEvent(requestID: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.queued = Melix_Worker_V1_Queued()
    event.queued.lane = "text.decode.interactive"
    return event
}

private func makeTokenExecuteEvent(requestID: String, text: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.tokenDelta = Melix_Worker_V1_TokenDelta()
    event.tokenDelta.text = text
    return event
}

private func makeReasoningExecuteEvent(requestID: String, text: String) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.reasoningDelta = Melix_Worker_V1_ReasoningDelta()
    event.reasoningDelta.text = text
    return event
}

private func makeToolExecuteEvent(
    requestID: String,
    callID: String,
    toolName: String,
    arguments: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.toolCallDelta = Melix_Worker_V1_ToolCallDelta()
    event.toolCallDelta.callID = callID
    event.toolCallDelta.toolName = toolName
    event.toolCallDelta.argumentsJsonFragment = arguments
    return event
}

private func makeUsageExecuteEvent(
    requestID: String,
    promptTokens: UInt32,
    completionTokens: UInt32
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.usageDelta = Melix_Worker_V1_UsageDelta()
    event.usageDelta.promptTokens = promptTokens
    event.usageDelta.completionTokens = completionTokens
    return event
}

private func makeCompletedExecuteEvent(
    requestID: String,
    finishReason: String,
    assistant: String,
    reasoning: String
) -> Melix_Worker_V1_ExecuteEvent {
    var event = Melix_Worker_V1_ExecuteEvent()
    event.requestID = requestID
    event.completed = Melix_Worker_V1_Completed()
    event.completed.finishReason = finishReason
    event.completed.assistantText = assistant
    event.completed.reasoningText = reasoning
    return event
}

private struct TestWorkerError: Error, CustomStringConvertible {
    let description: String
}
