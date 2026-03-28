import Testing

@testable import AppMain
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Control Plane XPC Client")
struct ControlPlaneXPCClientTests {
    @Test("local client hydrates from handshake and receives model-state events")
    func localClientHydratesAndSubscribes() async throws {
        let service = ControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        let handshake = try await client.handshake()
        #expect(handshake.snapshot.serverState == .serverReady)
        #expect(handshake.snapshot.models.first?.modelID == "melix-dev-text")
        #expect(handshake.snapshot.models.first?.state == .modelDiscovered)

        let stream = await client.subscribe(lastSeenSeq: 0)
        let nextEvent = Task {
            var iterator = stream.makeAsyncIterator()
            return try #require(await iterator.next())
        }

        let loaded = try await client.loadModel(modelID: "melix-dev-text")
        let event = try await nextEvent.value

        #expect(loaded.modelID == "melix-dev-text")
        #expect(loaded.state == .modelWarm)
        #expect(event.eventType == "model.state_changed")
        #expect(event.modelState.modelID == "melix-dev-text")
        #expect(event.modelState.state == .modelWarm)
    }

    @Test("local client unloads the model through control-plane execute")
    func localClientUnloadsModel() async throws {
        let service = ControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)
        _ = try await client.loadModel(modelID: "melix-dev-text")

        let unloaded = try await client.unloadModel(modelID: "melix-dev-text")

        #expect(unloaded.modelID == "melix-dev-text")
        #expect(unloaded.state == .modelUnloaded)
    }

    @Test("local client can request a fresh server snapshot through control-plane execute")
    func localClientFetchesServerSnapshot() async throws {
        let service = ControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        let snapshot = try await client.serverSnapshot()

        #expect(snapshot.serverState == .serverReady)
        #expect(snapshot.models.first?.modelID == "melix-dev-text")
        #expect(snapshot.queues.lanes.contains(where: { $0.laneID == "text.decode.interactive" }))
    }

    @Test("load and unload surface request failures for unknown models")
    func loadAndUnloadSurfaceRequestFailures() async throws {
        let service = ControlPlaneService()
        let client = LocalControlPlaneXPCClient(service: service)

        do {
            _ = try await client.loadModel(modelID: "missing-model")
            Issue.record("Expected loadModel to throw for an unknown model")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "not_found",
                    message: "Unknown model ID."
                )
            )
        }

        do {
            _ = try await client.unloadModel(modelID: "missing-model")
            Issue.record("Expected unloadModel to throw for an unknown model")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "not_found",
                    message: "Unknown model ID."
                )
            )
        }
    }

    @Test("local client surfaces snapshot request failures")
    func localClientSurfacesSnapshotRequestFailures() async throws {
        let service = FailingExecuteControlPlaneService(
            code: "unavailable",
            message: "Snapshot path unavailable."
        )
        let client = LocalControlPlaneXPCClient(service: service)

        do {
            _ = try await client.serverSnapshot()
            Issue.record("Expected serverSnapshot to throw for a failed execute response")
        } catch let error as ControlPlaneXPCClientError {
            #expect(
                error == .requestFailed(
                    code: "unavailable",
                    message: "Snapshot path unavailable."
                )
            )
        }
    }
}

private actor FailingExecuteControlPlaneService: ControlPlaneExecuting {
    private let code: String
    private let message: String

    init(code: String, message: String) {
        self.code = code
        self.message = message
    }

    func handshake(_ request: Melix_Controlplane_V1_HandshakeRequest) async throws -> Melix_Controlplane_V1_HandshakeResponse {
        _ = request
        return Melix_Controlplane_V1_HandshakeResponse()
    }

    func subscribe(_ request: Melix_Controlplane_V1_SubscribeRequest) async -> ControlPlaneSubscription {
        _ = request
        return ControlPlaneSubscription(
            subscriptionID: "test",
            stream: AsyncStream { continuation in
                continuation.finish()
            }
        )
    }

    func unsubscribe(_ subscriptionID: String) async {
        _ = subscriptionID
    }

    func execute(_ request: Melix_Controlplane_V1_ControlPlaneRequest) async throws -> Melix_Controlplane_V1_ControlPlaneResponse {
        _ = request
        var response = Melix_Controlplane_V1_ControlPlaneResponse()
        response.ok = false
        response.error.code = code
        response.error.message = message
        return response
    }
}
