import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public enum ControlPlaneXPCClientError: Error, Equatable {
    case requestFailed(code: String, message: String)
}

public protocol ControlPlaneXPCClient: Sendable {
    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse
    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>
    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot
    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary
    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary
}

public protocol ControlPlaneExecuting: Sendable {
    func handshake(_ request: Melix_Controlplane_V1_HandshakeRequest) async throws -> Melix_Controlplane_V1_HandshakeResponse
    func subscribe(_ request: Melix_Controlplane_V1_SubscribeRequest) async -> ControlPlaneSubscription
    func unsubscribe(_ subscriptionID: String) async
    func execute(_ request: Melix_Controlplane_V1_ControlPlaneRequest) async throws -> Melix_Controlplane_V1_ControlPlaneResponse
}

extension ControlPlaneService: ControlPlaneExecuting {}

public actor LocalControlPlaneXPCClient: ControlPlaneXPCClient {
    private let service: any ControlPlaneExecuting

    public init(service: any ControlPlaneExecuting = ControlPlaneService()) {
        self.service = service
    }

    public func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var request = Melix_Controlplane_V1_HandshakeRequest()
        request.protocolVersion = "melix.controlplane.v1"
        request.appVersion = "0.1.0"
        request.bundleID = "com.melix.app"
        request.clientInstanceID = UUID().uuidString
        return try await service.handshake(request)
    }

    public func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        var request = Melix_Controlplane_V1_SubscribeRequest()
        request.lastSeenSeq = lastSeenSeq
        let subscription = await service.subscribe(request)

        return AsyncStream { continuation in
            let forwardTask = Task {
                for await event in subscription.stream {
                    continuation.yield(event)
                }
                continuation.finish()
            }

            continuation.onTermination = { _ in
                forwardTask.cancel()
                Task {
                    await self.service.unsubscribe(subscription.subscriptionID)
                }
            }
        }
    }

    public func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await execute(makeLoadRequest(modelID: modelID)) { response in
            response.model.model
        }
    }

    public func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        try await execute(makeServerSnapshotRequest()) { response in
            response.server.snapshot
        }
    }

    public func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await execute(makeUnloadRequest(modelID: modelID)) { response in
            response.model.model
        }
    }

    private func execute<T>(
        _ request: Melix_Controlplane_V1_ControlPlaneRequest,
        transform: (Melix_Controlplane_V1_ControlPlaneResponse) -> T
    ) async throws -> T {
        let response = try await service.execute(request)
        guard response.ok else {
            throw ControlPlaneXPCClientError.requestFailed(
                code: response.error.code,
                message: response.error.message
            )
        }
        return transform(response)
    }

    private func makeLoadRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-load-\(modelID)"
        request.commandType = "model.load"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.load = Melix_Controlplane_V1_LoadModel()
        request.model.load.modelID = modelID
        return request
    }

    private func makeServerSnapshotRequest() -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-server-snapshot"
        request.commandType = "server.get_snapshot"
        request.server = Melix_Controlplane_V1_ServerCommand()
        request.server.getSnapshot = Melix_Controlplane_V1_GetServerSnapshot()
        return request
    }

    private func makeUnloadRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-unload-\(modelID)"
        request.commandType = "model.unload"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.unload = Melix_Controlplane_V1_UnloadModel()
        request.model.unload.modelID = modelID
        return request
    }
}
