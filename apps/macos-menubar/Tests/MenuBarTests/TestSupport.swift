import Foundation

@testable import AppMain
import MelixControlPlaneProtocol

actor FakeControlPlaneXPCClient: ControlPlaneXPCClient {
    private let stream: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>
    private let continuation: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>.Continuation

    private(set) var recordedActions: [String] = []
    private(set) var handshakeCount = 0
    private var modelState: Melix_Controlplane_V1_ModelState = .modelDiscovered
    private var handshakeError: Error?
    private var loadError: Error?
    private var unloadError: Error?

    init() {
        var capturedContinuation: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>.Continuation?
        stream = AsyncStream { continuation in
            capturedContinuation = continuation
        }
        continuation = capturedContinuation!
    }

    func configureErrors(
        handshake: Error? = nil,
        load: Error? = nil,
        unload: Error? = nil
    ) {
        handshakeError = handshake
        loadError = load
        unloadError = unload
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        handshakeCount += 1
        if let handshakeError {
            throw handshakeError
        }

        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "daemon-1"
        response.snapshot = makeSnapshot(state: modelState)
        return response
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        _ = lastSeenSeq
        return stream
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("load:\(modelID)")
        if let loadError {
            throw loadError
        }

        modelState = .modelWarm
        return makeModelSummary(state: modelState)
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("unload:\(modelID)")
        if let unloadError {
            throw unloadError
        }

        modelState = .modelUnloaded
        return makeModelSummary(state: modelState)
    }

    func sendModelStateChanged(state: Melix_Controlplane_V1_ModelState) {
        modelState = state
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "model.state_changed"
        event.modelState = Melix_Controlplane_V1_ModelStateChanged()
        event.modelState.modelID = "melix-dev-text"
        event.modelState.state = state
        continuation.yield(event)
    }

    func makeSnapshot(state: Melix_Controlplane_V1_ModelState) -> Melix_Controlplane_V1_ServerSnapshot {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [makeModelSummary(state: state)]
        return snapshot
    }

    private func makeModelSummary(
        state: Melix_Controlplane_V1_ModelState
    ) -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-text"
        model.kind = "text"
        model.state = state
        model.features = ["chat"]
        model.maxContext = 8192
        return model
    }
}

struct MenuBarTestError: Error, CustomStringConvertible {
    let description: String
}
