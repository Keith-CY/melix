import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Event Subscription Hub")
struct EventSubscriptionHubTests {
    @Test("subscribe receives typed events with monotonic sequence numbers")
    func subscribeReceivesMonotonicEvents() async throws {
        let hub = EventSubscriptionHub()
        let subscription = await hub.subscribe()

        let consumer = Task { () -> [Melix_Controlplane_V1_ControlPlaneEvent] in
            var iterator = subscription.stream.makeAsyncIterator()
            let first = try #require(await iterator.next())
            let second = try #require(await iterator.next())
            return [first, second]
        }

        var serverChanged = Melix_Controlplane_V1_ControlPlaneEvent()
        serverChanged.eventType = "server.state_changed"
        serverChanged.source = "server_snapshot_builder"
        serverChanged.serverState = Melix_Controlplane_V1_ServerStateChanged()
        serverChanged.serverState.state = .serverReady

        var modelChanged = Melix_Controlplane_V1_ControlPlaneEvent()
        modelChanged.eventType = "model.state_changed"
        modelChanged.source = "model_catalog"
        modelChanged.modelState = Melix_Controlplane_V1_ModelStateChanged()
        modelChanged.modelState.modelID = "melix-dev-text"
        modelChanged.modelState.state = .modelWarm

        await hub.publish(serverChanged)
        await hub.publish(modelChanged)

        let events = try await consumer.value
        #expect(events.count == 2)
        #expect(events[0].subscriptionID == subscription.subscriptionID)
        #expect(events[1].subscriptionID == subscription.subscriptionID)
        #expect(events[0].seq == 1)
        #expect(events[1].seq == 2)
        #expect(events[0].eventType == "server.state_changed")
        #expect(events[1].eventType == "model.state_changed")

        await hub.unsubscribe(subscription.subscriptionID)
    }

    @Test("subscribe resumes sequence numbers from last seen and ignores unknown unsubscriptions")
    func subscribeResumesSequenceNumbers() async throws {
        let hub = EventSubscriptionHub()
        let subscription = await hub.subscribe(lastSeenSeq: 41)

        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "server.state_changed"
        event.source = "test"

        let consumer = Task {
            var iterator = subscription.stream.makeAsyncIterator()
            return try #require(await iterator.next())
        }

        await hub.unsubscribe("missing-subscription")
        await hub.publish(event)

        let delivered = try await consumer.value
        #expect(delivered.seq == 42)
    }

    @Test("request progress events preserve phase-aware lifecycle and acceleration fields")
    func requestProgressEventsPreservePhaseAwareFields() async throws {
        let hub = EventSubscriptionHub()
        let subscription = await hub.subscribe()

        let consumer = Task { () -> [Melix_Controlplane_V1_ControlPlaneEvent] in
            var iterator = subscription.stream.makeAsyncIterator()
            let first = try #require(await iterator.next())
            let second = try #require(await iterator.next())
            let third = try #require(await iterator.next())
            let fourth = try #require(await iterator.next())
            let fifth = try #require(await iterator.next())
            return [first, second, third, fourth, fifth]
        }

        var queued = Melix_Controlplane_V1_ControlPlaneEvent()
        queued.eventType = "request.progress"
        queued.source = "scheduler"
        queued.requestProgress = Melix_Controlplane_V1_RequestProgressEvent()
        queued.requestProgress.requestID = "req-queued"
        queued.requestProgress.phase = .requestQueued
        queued.requestProgress.lane = "text.decode.interactive"
        queued.requestProgress.queuePosition = 2
        queued.requestProgress.admissionState = .admissionQueued

        var admitted = Melix_Controlplane_V1_ControlPlaneEvent()
        admitted.eventType = "request.progress"
        admitted.source = "scheduler"
        admitted.requestProgress = Melix_Controlplane_V1_RequestProgressEvent()
        admitted.requestProgress.requestID = "req-admitted"
        admitted.requestProgress.phase = .requestAdmitted
        admitted.requestProgress.lane = "text.decode.interactive"
        admitted.requestProgress.workerID = "swift-text-worker"
        admitted.requestProgress.queueDelayMs = 5
        admitted.requestProgress.admissionState = .admissionAdmitted

        var prefill = Melix_Controlplane_V1_ControlPlaneEvent()
        prefill.eventType = "request.progress"
        prefill.source = "swift-text-worker"
        prefill.requestProgress = Melix_Controlplane_V1_RequestProgressEvent()
        prefill.requestProgress.requestID = "req-prefill"
        prefill.requestProgress.phase = .requestPrefilling
        prefill.requestProgress.lane = "text.prefill.hot"
        prefill.requestProgress.accelerationMode = .acceleratedPrefill
        prefill.requestProgress.accelerationProfileID = "lookup-v1"

        var decode = Melix_Controlplane_V1_ControlPlaneEvent()
        decode.eventType = "request.progress"
        decode.source = "swift-text-worker"
        decode.requestProgress = Melix_Controlplane_V1_RequestProgressEvent()
        decode.requestProgress.requestID = "req-decode"
        decode.requestProgress.phase = .requestDecoding
        decode.requestProgress.lane = "text.decode.interactive"
        decode.requestProgress.decodeHandle = "decode-123"
        decode.requestProgress.accelerationMode = .speculativeDecode
        decode.requestProgress.draftModelID = "draft-q4"

        var completed = Melix_Controlplane_V1_ControlPlaneEvent()
        completed.eventType = "request.progress"
        completed.source = "swift-text-worker"
        completed.requestProgress = Melix_Controlplane_V1_RequestProgressEvent()
        completed.requestProgress.requestID = "req-done"
        completed.requestProgress.phase = .requestCompleted
        completed.requestProgress.lane = "text.decode.interactive"
        completed.requestProgress.workerID = "swift-text-worker"

        await hub.publish(queued)
        await hub.publish(admitted)
        await hub.publish(prefill)
        await hub.publish(decode)
        await hub.publish(completed)

        let events = try await consumer.value
        #expect(events.count == 5)
        #expect(events[0].requestProgress.phase == .requestQueued)
        #expect(events[0].requestProgress.queuePosition == 2)
        #expect(events[0].requestProgress.admissionState == .admissionQueued)
        #expect(events[1].requestProgress.phase == .requestAdmitted)
        #expect(events[1].requestProgress.workerID == "swift-text-worker")
        #expect(events[2].requestProgress.phase == .requestPrefilling)
        #expect(events[2].requestProgress.accelerationMode == .acceleratedPrefill)
        #expect(events[2].requestProgress.accelerationProfileID == "lookup-v1")
        #expect(events[3].requestProgress.phase == .requestDecoding)
        #expect(events[3].requestProgress.decodeHandle == "decode-123")
        #expect(events[3].requestProgress.accelerationMode == .speculativeDecode)
        #expect(events[3].requestProgress.draftModelID == "draft-q4")
        #expect(events[4].requestProgress.phase == .requestCompleted)
        #expect(events[4].requestProgress.workerID == "swift-text-worker")

        await hub.unsubscribe(subscription.subscriptionID)
    }
}

@Suite("Core Utilities")
struct CoreUtilityTests {
    @Test("abort registry preserves active state until the matching request finishes")
    func abortRegistryPreservesActiveStateUntilTheMatchingRequestFinishes() async {
        let registry = AbortRegistry()

        #expect(await registry.begin(requestID: "req-1"))
        #expect(await registry.contains("req-1"))
        #expect(!(await registry.isAborted("req-1")))
        #expect(!(await registry.abort("other-req")))

        await registry.finish(requestID: "other-req")
        #expect(await registry.contains("req-1"))

        #expect(await registry.abort("req-1"))
        #expect(await registry.isAborted("req-1"))

        await registry.finish(requestID: "req-1")
        #expect(!(await registry.contains("req-1")))
        #expect(!(await registry.isAborted("req-1")))
    }

    @Test("null worker client reports no dispatch capacity")
    func nullWorkerClientReportsNoDispatchCapacity() async {
        let client = NullWorkerClient()
        let canDispatch = await client.canDispatchRequests()
        #expect(!canDispatch)
    }

    @Test("engine pool proxies worker availability")
    func enginePoolProxiesWorkerAvailability() async {
        let pool = EnginePool(workerClient: StubWorkerClient(canDispatch: true))
        let canDispatch = await pool.hasDispatchCapacity()
        #expect(canDispatch)
    }

    @Test("null worker client rejects generate and abort")
    func nullWorkerClientRejectsGenerateAndAbort() async throws {
        let client = NullWorkerClient()

        do {
            _ = try await client.generate(request: Melix_Worker_V1_GenerateRequest())
            Issue.record("Expected null worker client generate to throw.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }

        let aborted = try await client.abort(requestID: "missing-request")
        #expect(!aborted)
    }

    @Test("model catalog can load, unload, and reject missing models")
    func modelCatalogStateTransitions() async {
        let catalog = ModelCatalog()

        let initial = await catalog.listModels()
        let loaded = await catalog.loadModel(id: "melix-dev-text")
        let unloaded = await catalog.unloadModel(id: "melix-dev-text")
        let missing = await catalog.loadModel(id: "missing-model")

        #expect(initial.count == 1)
        #expect(initial.first?.state == .modelDiscovered)
        #expect(loaded?.state == .modelWarm)
        #expect(unloaded?.state == .modelUnloaded)
        #expect(missing == nil)
    }

    @Test("model catalog resolves dispatch handles only for loaded models")
    func modelCatalogResolvesDispatchHandles() async {
        let catalog = ModelCatalog()
        let missingBeforeLoad = await catalog.dispatchHandle(for: "melix-dev-text")
        _ = await catalog.loadModel(id: "melix-dev-text")
        let loadedHandle = await catalog.dispatchHandle(for: "melix-dev-text")
        _ = await catalog.unloadModel(id: "melix-dev-text")
        let unloadedHandle = await catalog.dispatchHandle(for: "melix-dev-text")

        #expect(missingBeforeLoad == nil)
        #expect(loadedHandle == "melix-dev-text::local")
        #expect(unloadedHandle == nil)
    }

    @Test("metrics store records and clamps values")
    func metricsStoreRecordsAndClampsValues() async {
        let store = MetricsStore()
        await store.increment("requests.inflight")
        await store.set(3.5, forKey: "http.translation_ms")
        await store.decrement("requests.inflight", by: 5)

        let snapshot = await store.snapshot()
        #expect(snapshot.values["requests.inflight"] == 0)
        #expect(snapshot.values["http.translation_ms"] == 3.5)
    }

    @Test("metrics store exports snapshots when an export path is configured")
    func metricsStoreExportsSnapshotsWhenAnExportPathIsConfigured() async throws {
        let exportURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("json")
        let store = MetricsStore(exportPath: exportURL.path)

        await store.set(12.5, forKey: "scheduler.queue_delay_ms")
        await store.flushExport()
        let data = try Data(contentsOf: exportURL)
        let payload = try #require(
            JSONSerialization.jsonObject(with: data) as? [String: Any]
        )
        let values = try #require(payload["values"] as? [String: Double])

        #expect(values["scheduler.queue_delay_ms"] == 12.5)
    }

    @Test("metrics store throttles export writes and can flush latest values")
    func metricsStoreThrottlesExportWritesAndCanFlushLatestValues() async throws {
        let exportURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension("json")
        let store = MetricsStore(exportPath: exportURL.path, exportMinimumInterval: 60)

        await store.set(1, forKey: "http.stream_event_count")
        let firstData = try Data(contentsOf: exportURL)
        let firstPayload = try #require(
            JSONSerialization.jsonObject(with: firstData) as? [String: Any]
        )
        let firstValues = try #require(firstPayload["values"] as? [String: Double])
        #expect(firstValues["http.stream_event_count"] == 1)

        await store.set(2, forKey: "http.stream_event_count")
        let throttledData = try Data(contentsOf: exportURL)
        let throttledPayload = try #require(
            JSONSerialization.jsonObject(with: throttledData) as? [String: Any]
        )
        let throttledValues = try #require(throttledPayload["values"] as? [String: Double])
        #expect(throttledValues["http.stream_event_count"] == 1)

        let snapshot = await store.snapshot()
        #expect(snapshot.values["http.stream_event_count"] == 2)

        await store.flushExport()
        let flushedData = try Data(contentsOf: exportURL)
        let flushedPayload = try #require(
            JSONSerialization.jsonObject(with: flushedData) as? [String: Any]
        )
        let flushedValues = try #require(flushedPayload["values"] as? [String: Double])
        #expect(flushedValues["http.stream_event_count"] == 2)
    }

    @Test("admission gate serializes active requests and admits the next queued request")
    func admissionGateSerializesActiveRequestsAndAdmitsTheNextQueuedRequest() async {
        let gate = AdmissionGate()

        let first = await gate.acquire(requestID: "req-1")
        #expect(first.outcome == .admitted)
        #expect(await gate.nextQueuePosition() == 1)

        let secondTask = Task {
            await gate.acquire(requestID: "req-2")
        }
        let snapshotBeforeRelease = await waitForAdmissionGateSnapshot(gate) { snapshot in
            snapshot.activeRequestID == "req-1" && snapshot.queuedRequestIDs == ["req-2"]
        }
        #expect(snapshotBeforeRelease.activeRequestID == "req-1")
        #expect(snapshotBeforeRelease.queuedRequestIDs == ["req-2"])

        await gate.release(requestID: "req-1")
        let second = await secondTask.value
        let snapshotAfterRelease = await gate.snapshot()

        #expect(second.outcome == .admitted)
        #expect(snapshotAfterRelease.activeRequestID == "req-2")
        #expect(snapshotAfterRelease.activeRequestIDs == ["req-2"])
        #expect(snapshotAfterRelease.queuedRequestIDs.isEmpty)
    }

    @Test("admission gate batches compatible requests without skipping queued cohorts")
    func admissionGateBatchesCompatibleRequestsWithoutSkippingQueuedCohorts() async {
        let gate = AdmissionGate()

        let first = await gate.acquire(
            requestID: "req-batch-1",
            cohortID: "swift-text|hot",
            maxBatchSize: 2
        )
        #expect(first.outcome == .admitted)
        #expect(first.batchPosition == 1)
        #expect(first.batchSize == 1)
        #expect(first.batchCapacity == 2)
        #expect(first.mergedIntoBatch == false)

        let second = await gate.acquire(
            requestID: "req-batch-2",
            cohortID: "swift-text|hot",
            maxBatchSize: 2
        )
        #expect(second.outcome == .admitted)
        #expect(second.batchPosition == 2)
        #expect(second.batchSize == 2)
        #expect(second.batchCapacity == 2)
        #expect(second.mergedIntoBatch)

        let secondSnapshot = await gate.snapshot()
        #expect(secondSnapshot.activeRequestIDs == ["req-batch-1", "req-batch-2"])
        #expect(secondSnapshot.activeCohortID == "swift-text|hot")

        let queuedCold = Task {
            await gate.acquire(
                requestID: "req-cold-queued",
                cohortID: "swift-text|cold",
                maxBatchSize: 2
            )
        }
        await Task.yield()

        let queuedHot = Task {
            await gate.acquire(
                requestID: "req-hot-queued",
                cohortID: "swift-text|hot",
                maxBatchSize: 2
            )
        }
        await Task.yield()

        let queuedSnapshot = await waitForAdmissionGateSnapshot(gate) { snapshot in
            snapshot.queuedRequestIDs.count == 2
        }
        #expect(queuedSnapshot.queuedRequestIDs == ["req-cold-queued", "req-hot-queued"])

        await gate.release(requestID: "req-batch-1")
        let halfReleasedSnapshot = await gate.snapshot()
        #expect(halfReleasedSnapshot.activeRequestIDs == ["req-batch-2"])
        #expect(halfReleasedSnapshot.queuedRequestIDs == ["req-cold-queued", "req-hot-queued"])

        await gate.release(requestID: "req-batch-2")
        let coldGrant = await queuedCold.value
        let coldSnapshot = await gate.snapshot()
        #expect(coldGrant.outcome == .admitted)
        #expect(coldGrant.batchPosition == 1)
        #expect(coldGrant.batchSize == 1)
        #expect(coldSnapshot.activeRequestIDs == ["req-cold-queued"])
        #expect(coldSnapshot.queuedRequestIDs == ["req-hot-queued"])

        await gate.release(requestID: "req-cold-queued")
        let hotGrant = await queuedHot.value
        let finalSnapshot = await gate.snapshot()
        #expect(hotGrant.outcome == .admitted)
        #expect(hotGrant.batchPosition == 1)
        #expect(hotGrant.batchSize == 1)
        #expect(finalSnapshot.activeRequestIDs == ["req-hot-queued"])
        #expect(finalSnapshot.queuedRequestIDs.isEmpty)
    }

    @Test("dev text model has the expected defaults")
    func devTextModelDefaults() {
        let model = ModelCatalog.devTextModel()
        #expect(model.modelID == "melix-dev-text")
        #expect(model.kind == "text")
        #expect(model.quantProfileID == "dev-q4")
        #expect(model.maxContext == 8192)
        #expect(model.features == ["chat", "adaptive_thinking"])
    }

    @Test("server snapshot builder exposes Phase 7 lane identities")
    func serverSnapshotBuilderExposesPhaseSevenLaneIdentities() {
        let builder = ServerSnapshotBuilder()
        let snapshot = builder.build(
            models: [],
            metrics: Melix_Controlplane_V1_MetricsSummary()
        )

        let lanes = snapshot.queues.lanes
        #expect(lanes.count == 8)
        #expect(lanes.map(\.laneID) == [
            "text.decode.interactive",
            "text.prefill.hot",
            "text.prefill.background",
            "multimodal.vision.background",
            "multimodal.audio.transcription.background",
            "multimodal.audio.speech.background",
            "image.generate.background",
            "image.edit.background",
        ])
        #expect(lanes.map(\.laneClass) == [
            "interactive-decode",
            "hot-prefill",
            "background-prefill",
            "background-vision",
            "background-audio-transcription",
            "background-audio-speech",
            "background-image-generate",
            "background-image-edit",
        ])
    }
}

private func waitForAdmissionGateSnapshot(
    _ gate: AdmissionGate,
    attempts: Int = 50,
    predicate: @escaping @Sendable (
        (
            activeRequestID: String?,
            activeRequestIDs: [String],
            activeCohortID: String?,
            queuedRequestIDs: [String]
        )
    ) -> Bool
) async -> (
    activeRequestID: String?,
    activeRequestIDs: [String],
    activeCohortID: String?,
    queuedRequestIDs: [String]
) {
    for _ in 0..<attempts {
        let snapshot = await gate.snapshot()
        if predicate(snapshot) {
            return snapshot
        }
        try? await Task.sleep(nanoseconds: 10_000_000)
    }
    return await gate.snapshot()
}

private struct StubWorkerClient: WorkerClient {
    let canDispatch: Bool

    func canDispatchRequests() async -> Bool {
        canDispatch
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        false
    }
}
