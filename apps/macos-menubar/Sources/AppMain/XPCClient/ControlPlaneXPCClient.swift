import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public enum ControlPlaneXPCClientError: Error, Equatable {
    case requestFailed(code: String, message: String)
}

public struct ControlPlaneImageGenerationRequest: Equatable, Sendable {
    public let modelID: String
    public let prompt: String
    public let size: String
    public let n: UInt32
    public let responseFormat: String
    public let artifactNamespace: String

    public init(
        modelID: String,
        prompt: String,
        size: String = "1024x1024",
        n: UInt32 = 1,
        responseFormat: String = "png",
        artifactNamespace: String = ""
    ) {
        self.modelID = modelID
        self.prompt = prompt
        self.size = size
        self.n = n
        self.responseFormat = responseFormat
        self.artifactNamespace = artifactNamespace
    }
}

public struct ControlPlaneImageEditRequest: Equatable, Sendable {
    public let modelID: String
    public let prompt: String
    public let imageData: Data
    public let imageURL: String
    public let maskData: Data
    public let maskURL: String
    public let strength: Float
    public let size: String
    public let n: UInt32
    public let responseFormat: String

    public init(
        modelID: String,
        prompt: String,
        imageData: Data = Data(),
        imageURL: String = "",
        maskData: Data = Data(),
        maskURL: String = "",
        strength: Float = 1,
        size: String = "1024x1024",
        n: UInt32 = 1,
        responseFormat: String = "png"
    ) {
        self.modelID = modelID
        self.prompt = prompt
        self.imageData = imageData
        self.imageURL = imageURL
        self.maskData = maskData
        self.maskURL = maskURL
        self.strength = strength
        self.size = size
        self.n = n
        self.responseFormat = responseFormat
    }
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
    func generateImage(
        _ request: ControlPlaneImageGenerationRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary
    func editImage(
        _ request: ControlPlaneImageEditRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary
    func cancelRequest(requestID: String) async throws -> Bool
}

public extension ControlPlaneXPCClient {
    func generateImage(
        _ request: ControlPlaneImageGenerationRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        _ = request
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Image generation is not implemented for this control-plane client."
        )
    }

    func editImage(
        _ request: ControlPlaneImageEditRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        _ = request
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Image editing is not implemented for this control-plane client."
        )
    }

    func cancelRequest(requestID: String) async throws -> Bool {
        _ = requestID
        throw ControlPlaneXPCClientError.requestFailed(
            code: "unimplemented",
            message: "Request cancellation is not implemented for this control-plane client."
        )
    }
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

    public func generateImage(
        _ request: ControlPlaneImageGenerationRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        try await execute(makeImageGenerateRequest(request)) { response in
            response.image.job
        }
    }

    public func editImage(
        _ request: ControlPlaneImageEditRequest
    ) async throws -> Melix_Controlplane_V1_ImageJobSummary {
        try await execute(makeImageEditRequest(request)) { response in
            response.image.job
        }
    }

    public func cancelRequest(requestID: String) async throws -> Bool {
        try await execute(makeCancelRequest(requestID: requestID)) { _ in
            true
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

    private func makeImageGenerateRequest(
        _ generation: ControlPlaneImageGenerationRequest
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-image-generate-\(UUID().uuidString)"
        request.commandType = "image.generate"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.generate = Melix_Controlplane_V1_GenerateImage()
        request.image.generate.modelID = generation.modelID
        request.image.generate.prompt = generation.prompt
        request.image.generate.size = generation.size
        request.image.generate.n = generation.n
        request.image.generate.responseFormat = generation.responseFormat
        request.image.generate.artifactNamespace = generation.artifactNamespace
        return request
    }

    private func makeImageEditRequest(
        _ edit: ControlPlaneImageEditRequest
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-image-edit-\(UUID().uuidString)"
        request.commandType = "image.edit"
        request.image = Melix_Controlplane_V1_ImageCommand()
        request.image.edit = Melix_Controlplane_V1_EditImage()
        request.image.edit.modelID = edit.modelID
        request.image.edit.prompt = edit.prompt
        request.image.edit.image = edit.imageData
        request.image.edit.imageUri = edit.imageURL
        request.image.edit.mask = edit.maskData
        request.image.edit.maskUri = edit.maskURL
        request.image.edit.strength = edit.strength
        request.image.edit.size = edit.size
        request.image.edit.n = edit.n
        request.image.edit.responseFormat = edit.responseFormat
        return request
    }

    private func makeCancelRequest(
        requestID: String
    ) -> Melix_Controlplane_V1_ControlPlaneRequest {
        var request = Melix_Controlplane_V1_ControlPlaneRequest()
        request.requestID = "menubar-cancel-\(requestID)"
        request.commandType = "ops.cancel_request"
        request.ops = Melix_Controlplane_V1_OpsCommand()
        request.ops.cancelRequest = Melix_Controlplane_V1_CancelRequest()
        request.ops.cancelRequest.requestID = requestID
        return request
    }
}
