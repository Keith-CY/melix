import Foundation
import SwiftProtobuf

import MelixControlPlaneProtocol
import MelixWorkerProtocol

public enum BridgeCommandKind: String, Sendable {
    case handshake = "handshake"
    case loadModel = "load-model"
    case unloadModel = "unload-model"
    case getRuntimeStats = "get-runtime-stats"
    case generate = "generate"
    case abort = "abort"
    case embed = "embed"
    case rerank = "rerank"
    case transcribe = "transcribe"
    case speak = "speak"
    case imageGenerate = "image-generate"
    case imageEdit = "image-edit"
    case getModelInfo = "get-model-info"
    case convertModel = "convert-model"
    case runDoctor = "run-doctor"
    case runBench = "run-bench"
}

public struct BridgeCommand: Sendable {
    public let kind: BridgeCommandKind
    public let socketPath: String
    public let requestData: Data

    public init(kind: BridgeCommandKind, socketPath: String, requestData: Data) {
        self.kind = kind
        self.socketPath = socketPath
        self.requestData = requestData
    }
}

public protocol WorkerBridgeRunning: Sendable {
    func runUnary(command: BridgeCommand) async throws -> String
    func runStream(command: BridgeCommand) async throws -> AsyncThrowingStream<String, Error>
}

public struct PythonBridgeWorkerClient:
    WorkerRoutingClient,
    NonTextInferenceWorkerClientProtocol,
    RuntimeIntrospectingWorkerClientProtocol,
    ModelOperationsWorkerClientProtocol,
    Sendable
{
    private let socketPath: String
    private let runner: any WorkerBridgeRunning

    public init(socketPath: String, runner: any WorkerBridgeRunning) {
        self.socketPath = socketPath
        self.runner = runner
    }

    public init(
        socketPath: String,
        repoRoot: String,
        processEnvironment: [String: String] = ProcessInfo.processInfo.environment
    ) {
        self.init(
            socketPath: socketPath,
            runner: ProcessWorkerBridgeRunner(
                repoRoot: repoRoot,
                environment: processEnvironment
            )
        )
    }

    public func canDispatchRequests() async -> Bool {
        var request = Melix_Worker_V1_HandshakeRequest()
        request.protocolVersion = "melix.worker.v1"
        request.workerID = "control-plane"
        request.controlplaneInstanceID = "melix-control-plane"

        do {
            _ = try await sendUnary(
                kind: .handshake,
                request: request,
                as: Melix_Worker_V1_HandshakeResponse.self
            )
            return true
        } catch {
            return false
        }
    }

    public func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        try await sendUnary(kind: .loadModel, request: request, as: Melix_Worker_V1_LoadModelResponse.self)
    }

    public func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        try await sendUnary(kind: .unloadModel, request: request, as: Melix_Worker_V1_UnloadModelResponse.self)
    }

    public func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        let lineStream = try await runner.runStream(
            command: BridgeCommand(
                kind: .generate,
                socketPath: socketPath,
                requestData: try request.serializedData()
            )
        )

        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for try await line in lineStream {
                        let event: Melix_Worker_V1_ExecuteEvent = try decodeLine(line)
                        continuation.yield(event)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    public func abort(requestID: String) async throws -> Bool {
        var request = Melix_Worker_V1_AbortRequest()
        request.requestID = requestID

        let response: Melix_Worker_V1_AbortResponse = try await sendUnary(
            kind: .abort,
            request: request,
            as: Melix_Worker_V1_AbortResponse.self
        )
        return response.ok && response.found
    }

    public func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        try await sendUnary(
            kind: .getRuntimeStats,
            request: Melix_Worker_V1_GetRuntimeStatsRequest(),
            as: Melix_Worker_V1_GetRuntimeStatsResponse.self
        )
    }

    public func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        try await sendUnary(kind: .embed, request: request, as: Melix_Worker_V1_EmbedResponse.self)
    }

    public func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        try await sendUnary(kind: .rerank, request: request, as: Melix_Worker_V1_RerankResponse.self)
    }

    public func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        try await sendUnary(kind: .transcribe, request: request, as: Melix_Worker_V1_TranscribeResponse.self)
    }

    public func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        try await sendUnary(kind: .speak, request: request, as: Melix_Worker_V1_SpeakResponse.self)
    }

    public func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        try await sendUnary(kind: .imageGenerate, request: request, as: Melix_Worker_V1_ImageGenerateResponse.self)
    }

    public func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        try await sendUnary(kind: .imageEdit, request: request, as: Melix_Worker_V1_ImageEditResponse.self)
    }

    public func getModelInfo(
        request: Melix_Worker_V1_GetModelInfoRequest
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse {
        try await sendUnary(
            kind: .getModelInfo,
            request: request,
            as: Melix_Worker_V1_GetModelInfoResponse.self
        )
    }

    public func convertModel(
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error> {
        let lineStream = try await runner.runStream(
            command: BridgeCommand(
                kind: .convertModel,
                socketPath: socketPath,
                requestData: try request.serializedData()
            )
        )

        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for try await line in lineStream {
                        let event: Melix_Worker_V1_ConvertModelEvent = try decodeLine(line)
                        continuation.yield(event)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    public func runDoctor(
        request: Melix_Worker_V1_RunDoctorRequest
    ) async throws -> Melix_Worker_V1_RunDoctorResponse {
        try await sendUnary(
            kind: .runDoctor,
            request: request,
            as: Melix_Worker_V1_RunDoctorResponse.self
        )
    }

    public func runBench(
        request: Melix_Worker_V1_RunBenchRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_RunBenchEvent, Error> {
        let lineStream = try await runner.runStream(
            command: BridgeCommand(
                kind: .runBench,
                socketPath: socketPath,
                requestData: try request.serializedData()
            )
        )

        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for try await line in lineStream {
                        let event: Melix_Worker_V1_RunBenchEvent = try decodeLine(line)
                        continuation.yield(event)
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    private func sendUnary<Request: SwiftProtobuf.Message, Response: SwiftProtobuf.Message>(
        kind: BridgeCommandKind,
        request: Request,
        as _: Response.Type
    ) async throws -> Response {
        let line = try await runner.runUnary(
            command: BridgeCommand(
                kind: kind,
                socketPath: socketPath,
                requestData: try request.serializedData()
            )
        )
        return try decodeLine(line)
    }

    private func decodeLine<Message: SwiftProtobuf.Message>(_ line: String) throws -> Message {
        let payload = try WorkerBridgeLine.decode(from: line)
        switch payload.kind {
        case "message":
            guard let encoded = payload.messageBase64, let data = Data(base64Encoded: encoded) else {
                throw WorkerClientError.unavailable
            }
            return try Message(serializedBytes: data)
        case "error":
            throw WorkerClientError.unavailable
        default:
            throw WorkerClientError.unavailable
        }
    }
}

public enum BootstrapWorkerPreparation {
    private static let adapterSetHashExtKey = "melix.adapter_set_hash"

    public static func modelSpec(for modelID: String) -> Melix_Worker_V1_ModelSpec? {
        switch modelID {
        case "melix-dev-text":
            return devTextModel()
        case "melix-dev-embed":
            return devEmbeddingModel()
        case "melix-dev-rerank":
            return devRerankModel()
        case "melix-dev-ocr":
            return devOCRModel()
        case "melix-dev-vlm":
            return devVLMModel()
        case "melix-dev-transcribe":
            return devTranscriptionModel()
        case "melix-dev-speech":
            return devSpeechModel()
        case "melix-dev-image":
            return devImageModel()
        default:
            return nil
        }
    }

    public static func modelSpec(
        for summary: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Worker_V1_ModelSpec? {
        guard var spec = modelSpec(for: summary.modelID) else { return nil }
        if let adapterSetHash = summary.settings.ext[adapterSetHashExtKey], !adapterSetHash.isEmpty {
            spec.ext[adapterSetHashExtKey] = adapterSetHash
        }
        return spec
    }

    public static func preloadDevTextModel(
        workerClient: any WorkerRoutingClient,
        modelCatalog: ModelCatalog,
        memoryBudgetBytes: UInt64 = 0
    ) async throws -> Bool {
        try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: devTextModel(),
            memoryBudgetBytes: memoryBudgetBytes
        )
    }

    public static func preloadPhaseFivePythonModels(
        workerClient: any WorkerRoutingClient,
        modelCatalog: ModelCatalog,
        memoryBudgetBytes: UInt64 = 0
    ) async throws {
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: devEmbeddingModel(),
            memoryBudgetBytes: memoryBudgetBytes
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: devRerankModel(),
            memoryBudgetBytes: memoryBudgetBytes
        )
    }

    public static func preloadPhaseSixPythonModels(
        workerClient: any WorkerRoutingClient,
        modelCatalog: ModelCatalog,
        memoryBudgetBytes: UInt64 = 0
    ) async throws {
        try await preloadPhaseFivePythonModels(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            memoryBudgetBytes: memoryBudgetBytes
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: devOCRModel(),
            memoryBudgetBytes: memoryBudgetBytes
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: devVLMModel(),
            memoryBudgetBytes: memoryBudgetBytes
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: devTranscriptionModel(),
            memoryBudgetBytes: memoryBudgetBytes
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: devSpeechModel(),
            memoryBudgetBytes: memoryBudgetBytes
        )
    }

    public static func preloadPhaseSevenPythonModels(
        workerClient: any WorkerRoutingClient,
        modelCatalog: ModelCatalog,
        memoryBudgetBytes: UInt64 = 0
    ) async throws {
        try await preloadPhaseSixPythonModels(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            memoryBudgetBytes: memoryBudgetBytes
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: devImageModel(),
            memoryBudgetBytes: memoryBudgetBytes
        )
    }

    @discardableResult
    private static func preloadModel(
        workerClient: any WorkerRoutingClient,
        modelCatalog: ModelCatalog,
        model: Melix_Worker_V1_ModelSpec,
        memoryBudgetBytes: UInt64
    ) async throws -> Bool {
        _ = await modelCatalog.beginLoad(id: model.modelID)
        var request = Melix_Worker_V1_LoadModelRequest()
        request.model = model
        request.memoryBudgetBytes = memoryBudgetBytes
        request.pinOnLoad = true
        request.warmupAfterLoad = false

        let response = try await workerClient.loadModel(request: request)
        guard response.ok, !response.modelHandle.isEmpty else {
            _ = await modelCatalog.recordLoadFailed(id: model.modelID)
            return false
        }

        _ = await modelCatalog.recordLoadSucceeded(
            id: request.model.modelID,
            dispatchHandle: response.modelHandle,
            pinRequested: request.pinOnLoad,
            workerResidency: response.hasResidency ? response.residency : nil
        )
        return true
    }

    private static func devTextModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-text"
        model.modelPath = "models/melix-dev-text"
        model.modelKind = "text"
        model.revision = "dev"
        model.tokenizerHash = "tok-dev"
        model.quantProfileID = "q4"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 8192
        return model
    }

    private static func devEmbeddingModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-embed"
        model.modelPath = "models/melix-dev-embed"
        model.modelKind = "embedding"
        model.revision = "dev"
        model.tokenizerHash = "tok-embed-dev"
        model.quantProfileID = "q8"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 8192
        return model
    }

    private static func devRerankModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-rerank"
        model.modelPath = "models/melix-dev-rerank"
        model.modelKind = "rerank"
        model.revision = "dev"
        model.tokenizerHash = "tok-rerank-dev"
        model.quantProfileID = "q8"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 8192
        return model
    }

    private static func devOCRModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-ocr"
        model.modelPath = "models/melix-dev-ocr"
        model.modelKind = "ocr"
        model.revision = "dev"
        model.tokenizerHash = "tok-ocr-dev"
        model.quantProfileID = "q8"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 4096
        return model
    }

    private static func devVLMModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-vlm"
        model.modelPath = "models/melix-dev-vlm"
        model.modelKind = "vlm"
        model.revision = "dev"
        model.tokenizerHash = "tok-vlm-dev"
        model.quantProfileID = "q8"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 4096
        return model
    }

    private static func devTranscriptionModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-transcribe"
        model.modelPath = "models/melix-dev-transcribe"
        model.modelKind = "transcription"
        model.revision = "dev"
        model.tokenizerHash = "tok-transcribe-dev"
        model.quantProfileID = "q8"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 4096
        return model
    }

    private static func devSpeechModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-speech"
        model.modelPath = "models/melix-dev-speech"
        model.modelKind = "speech"
        model.revision = "dev"
        model.tokenizerHash = "tok-speech-dev"
        model.quantProfileID = "q8"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 4096
        return model
    }

    private static func devImageModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-dev-image"
        model.modelPath = "models/melix-dev-image"
        model.modelKind = "image"
        model.revision = "dev"
        model.tokenizerHash = "tok-image-dev"
        model.quantProfileID = "q8"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 4096
        return model
    }
}

private struct WorkerBridgeLine: Decodable {
    let kind: String
    let messageBase64: String?

    enum CodingKeys: String, CodingKey {
        case kind
        case messageBase64 = "message_b64"
    }

    static func decode(from line: String) throws -> WorkerBridgeLine {
        try JSONDecoder().decode(Self.self, from: Data(line.utf8))
    }
}

private actor ProcessTerminationState {
    private var status: Int32?
    private var waiters: [CheckedContinuation<Int32, Never>] = []

    func markTerminated(status: Int32) {
        guard self.status == nil else {
            return
        }
        self.status = status
        let waiters = self.waiters
        self.waiters.removeAll(keepingCapacity: false)
        for waiter in waiters {
            waiter.resume(returning: status)
        }
    }

    func waitForExit() async -> Int32 {
        if let status {
            return status
        }
        return await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }
}

public struct ProcessWorkerBridgeRunner: WorkerBridgeRunning, Sendable {
    private let repoRoot: String
    private let environment: [String: String]

    public init(repoRoot: String, environment: [String: String]) {
        self.repoRoot = repoRoot
        self.environment = environment
    }

    public func runUnary(command: BridgeCommand) async throws -> String {
        let (process, terminationState) = configuredProcess(for: command)
        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()
        let terminationStatus = await waitForTermination(
            of: process,
            state: terminationState
        )

        let output = String(decoding: try stdout.fileHandleForReading.readToEnd() ?? Data(), as: UTF8.self)
        _ = String(decoding: try stderr.fileHandleForReading.readToEnd() ?? Data(), as: UTF8.self)

        guard terminationStatus == 0,
              let line = output.split(separator: "\n").last.map(String.init),
              !line.isEmpty
        else {
            throw WorkerClientError.unavailable
        }
        return line
    }

    public func runStream(command: BridgeCommand) async throws -> AsyncThrowingStream<String, Error> {
        let (process, terminationState) = configuredProcess(for: command)
        let stdout = Pipe()
        let stderr = Pipe()
        process.standardOutput = stdout
        process.standardError = stderr

        try process.run()

        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for try await line in stdout.fileHandleForReading.bytes.lines {
                        continuation.yield(String(line))
                    }
                    let terminationStatus = await waitForTermination(
                        of: process,
                        state: terminationState
                    )
                    if terminationStatus == 0 {
                        continuation.finish()
                    } else {
                        _ = try stderr.fileHandleForReading.readToEnd()
                        continuation.finish(throwing: WorkerClientError.unavailable)
                    }
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
                if process.isRunning {
                    process.terminate()
                }
            }
        }
    }

    private func configuredProcess(for command: BridgeCommand) -> (Process, ProcessTerminationState) {
        let process = Process()
        let terminationState = ProcessTerminationState()
        process.currentDirectoryURL = URL(fileURLWithPath: repoRoot, isDirectory: true)
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = [
            "uv",
            "run",
            "--project",
            "\(repoRoot)/services/mlx-worker-python",
            "python",
            "\(repoRoot)/services/mlx-worker-python/worker/control_plane_bridge.py",
            command.kind.rawValue,
            "--socket-path",
            command.socketPath,
            "--request-b64",
            command.requestData.base64EncodedString(),
        ]
        process.environment = mergedEnvironment()
        process.terminationHandler = { terminatedProcess in
            Task {
                await terminationState.markTerminated(status: terminatedProcess.terminationStatus)
            }
        }
        return (process, terminationState)
    }

    private func mergedEnvironment() -> [String: String] {
        var merged = environment
        let pythonPathEntry = "\(repoRoot):\(repoRoot)/services/mlx-worker-python"
        if let existing = merged["PYTHONPATH"], !existing.isEmpty {
            merged["PYTHONPATH"] = "\(pythonPathEntry):\(existing)"
        } else {
            merged["PYTHONPATH"] = pythonPathEntry
        }
        merged["UV_CACHE_DIR"] = merged["UV_CACHE_DIR"] ?? "\(repoRoot)/.uv-cache"
        merged["PYTHONUNBUFFERED"] = "1"
        return merged
    }

    private func waitForTermination(
        of process: Process,
        state: ProcessTerminationState
    ) async -> Int32 {
        if !process.isRunning {
            return process.terminationStatus
        }
        return await state.waitForExit()
    }
}
