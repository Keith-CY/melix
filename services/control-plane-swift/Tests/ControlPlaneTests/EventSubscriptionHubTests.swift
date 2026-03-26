import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

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
}

@Suite("Core Utilities")
struct CoreUtilityTests {
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

    @Test("dev text model has the expected defaults")
    func devTextModelDefaults() {
        let model = ModelCatalog.devTextModel()
        #expect(model.modelID == "melix-dev-text")
        #expect(model.kind == "text")
        #expect(model.quantProfileID == "dev-q4")
        #expect(model.maxContext == 8192)
        #expect(model.features == ["chat"])
    }
}

private struct StubWorkerClient: WorkerClient {
    let canDispatch: Bool

    func canDispatchRequests() async -> Bool {
        canDispatch
    }
}
