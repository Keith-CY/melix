import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public enum ControlPlaneXPCClientError: Error, Equatable {
    case requestFailed(code: String, message: String)
}

public protocol ControlPlaneXPCClient: Sendable {
    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse
    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>
    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution
    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot
    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary
    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary
    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary
    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo
    func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult
}

public protocol ControlPlaneExecuting: Sendable {
    func handshake(_ request: Melix_Controlplane_V1_HandshakeRequest) async throws -> Melix_Controlplane_V1_HandshakeResponse
    func subscribe(_ request: Melix_Controlplane_V1_SubscribeRequest) async -> ControlPlaneSubscription
    func unsubscribe(_ subscriptionID: String) async
    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution
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

    public func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        try await service.startChat(request)
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

    public func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        try await execute(makeSetModelPolicyRequest(modelID: modelID, values: values)) { response in
            response.model.model
        }
    }

    public func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        try await execute(makeGetModelInfoRequest(modelID: modelID)) { response in
            response.model.info
        }
    }

    public func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String] = [:]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        try await execute(
            makeRunModelOperationRequest(
                modelID: modelID,
                operation: operation,
                outputDir: outputDir,
                weightQuant: weightQuant,
                kvQuant: kvQuant,
                ext: ext
            )
        ) { response in
            response.model.operation
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

    private func makeSetModelPolicyRequest(
        modelID: String,
        values: [String: String]
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-set-policy-\(modelID)"
        request.commandType = "model.set_policy"
        request.model = Melix_Controlplane_V1_ModelCommand()
        request.model.setPolicy = Melix_Controlplane_V1_SetModelPolicy()
        request.model.setPolicy.modelID = modelID
        request.model.setPolicy.values = values
        return request
    }

    private func makeGetModelInfoRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-model-info-\(modelID)"
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
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-model-op-\(modelID)-\(operation)"
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
        return request
    }
}
