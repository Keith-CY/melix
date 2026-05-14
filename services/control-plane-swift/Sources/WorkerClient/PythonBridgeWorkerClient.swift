import Foundation
import GRPCCore
import GRPCNIOTransportHTTP2Posix
import NIOCore
import NIOPosix
import SwiftProtobuf

import MelixControlPlaneProtocol
import MelixWorkerProtocol

public enum BridgeCommandKind: String, Sendable {
    case handshake = "handshake"
    case loadModel = "load-model"
    case unloadModel = "unload-model"
    case getRuntimeStats = "get-runtime-stats"
    case getCacheStats = "get-cache-stats"
    case generate = "generate"
    case prefill = "prefill"
    case decode = "decode"
    case abort = "abort"
    case embed = "embed"
    case rerank = "rerank"
    case transcribe = "transcribe"
    case speak = "speak"
    case speakStream = "speak-stream"
    case imageGenerate = "image-generate"
    case imageEdit = "image-edit"
    case getModelInfo = "get-model-info"
    case convertModel = "convert-model"
    case runDoctor = "run-doctor"
    case searchHubModels = "search-hub-models"
    case getHubModelCard = "get-hub-model-card"
    case runBench = "run-bench"
    case runBenchMatrix = "run-bench-matrix"
    case runEvaluation = "run-evaluation"
    case exportResults = "export-results"
    case submitResults = "submit-results"
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

public protocol PythonWorkerRPCRunning: Sendable {
    func handshake(
        socketPath: String,
        request: Melix_Worker_V1_HandshakeRequest
    ) async throws -> Melix_Worker_V1_HandshakeResponse

    func loadModel(
        socketPath: String,
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse

    func unloadModel(
        socketPath: String,
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse

    func runtimeStats(
        socketPath: String,
        request: Melix_Worker_V1_GetRuntimeStatsRequest
    ) async throws -> Melix_Worker_V1_GetRuntimeStatsResponse

    func cacheStats(
        socketPath: String,
        request: Melix_Worker_V1_GetCacheStatsRequest
    ) async throws -> Melix_Worker_V1_GetCacheStatsResponse

    func generate(
        socketPath: String,
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>

    func prefill(
        socketPath: String,
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse

    func decode(
        socketPath: String,
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>

    func abort(
        socketPath: String,
        request: Melix_Worker_V1_AbortRequest
    ) async throws -> Melix_Worker_V1_AbortResponse

    func embed(
        socketPath: String,
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse

    func rerank(
        socketPath: String,
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse

    func transcribe(
        socketPath: String,
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse

    func speak(
        socketPath: String,
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse

    func speakStream(
        socketPath: String,
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_SpeakStreamEvent, Error>

    func imageGenerate(
        socketPath: String,
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse

    func imageEdit(
        socketPath: String,
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse

    func getModelInfo(
        socketPath: String,
        request: Melix_Worker_V1_GetModelInfoRequest
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse

    func convertModel(
        socketPath: String,
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error>

    func runDoctor(
        socketPath: String,
        request: Melix_Worker_V1_RunDoctorRequest
    ) async throws -> Melix_Worker_V1_RunDoctorResponse

    func searchHubModels(
        socketPath: String,
        request: Melix_Worker_V1_SearchHubModelsRequest
    ) async throws -> Melix_Worker_V1_SearchHubModelsResponse

    func getHubModelCard(
        socketPath: String,
        request: Melix_Worker_V1_GetHubModelCardRequest
    ) async throws -> Melix_Worker_V1_GetHubModelCardResponse

    func runBench(
        socketPath: String,
        request: Melix_Worker_V1_RunBenchRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_RunBenchEvent, Error>

    func runBenchMatrix(
        socketPath: String,
        request: Melix_Worker_V1_RunBenchMatrixRequest
    ) async throws -> Melix_Worker_V1_RunBenchMatrixResponse

    func runEvaluation(
        socketPath: String,
        request: Melix_Worker_V1_RunEvaluationRequest
    ) async throws -> Melix_Worker_V1_RunEvaluationResponse

    func exportResults(
        socketPath: String,
        request: Melix_Worker_V1_ExportResultsRequest
    ) async throws -> Melix_Worker_V1_ExportResultsResponse

    func submitResults(
        socketPath: String,
        request: Melix_Worker_V1_SubmitResultsRequest
    ) async throws -> Melix_Worker_V1_SubmitResultsResponse
}

private enum PythonWorkerTransport: Sendable {
    case bridge(any WorkerBridgeRunning)
    case rpc(any PythonWorkerRPCRunning)
}

public struct PythonBridgeWorkerClient:
    WorkerRoutingClient,
    PhaseAwareWorkerClientProtocol,
    NonTextInferenceWorkerClientProtocol,
    CacheIntrospectingWorkerClientProtocol,
    RuntimeIntrospectingWorkerClientProtocol,
    ModelOperationsWorkerClientProtocol,
    Sendable
{
    private let socketPath: String
    private let transport: PythonWorkerTransport

    public init(socketPath: String, runner: any WorkerBridgeRunning) {
        self.socketPath = socketPath
        self.transport = .bridge(runner)
    }

    public init(socketPath: String, rpcRunner: any PythonWorkerRPCRunning) {
        self.socketPath = socketPath
        self.transport = .rpc(rpcRunner)
    }

    public init(socketPath: String) {
        self.init(socketPath: socketPath, rpcRunner: GRPCPythonWorkerRunner())
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
            switch transport {
            case .bridge:
                _ = try await sendUnary(
                    kind: .handshake,
                    request: request,
                    as: Melix_Worker_V1_HandshakeResponse.self
                )
            case .rpc(let runner):
                _ = try await runner.handshake(socketPath: socketPath, request: request)
            }
            return true
        } catch {
            return false
        }
    }

    public func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(kind: .loadModel, request: request, as: Melix_Worker_V1_LoadModelResponse.self)
        case .rpc(let runner):
            return try await runner.loadModel(socketPath: socketPath, request: request)
        }
    }

    public func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(kind: .unloadModel, request: request, as: Melix_Worker_V1_UnloadModelResponse.self)
        case .rpc(let runner):
            return try await runner.unloadModel(socketPath: socketPath, request: request)
        }
    }

    public func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        switch transport {
        case .bridge:
            return try await sendStream(kind: .generate, request: request, as: Melix_Worker_V1_ExecuteEvent.self)
        case .rpc(let runner):
            return try await runner.generate(socketPath: socketPath, request: request)
        }
    }

    public func prefill(
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(kind: .prefill, request: request, as: Melix_Worker_V1_PrefillResponse.self)
        case .rpc(let runner):
            return try await runner.prefill(socketPath: socketPath, request: request)
        }
    }

    public func decode(
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        switch transport {
        case .bridge:
            return try await sendStream(kind: .decode, request: request, as: Melix_Worker_V1_ExecuteEvent.self)
        case .rpc(let runner):
            return try await runner.decode(socketPath: socketPath, request: request)
        }
    }

    public func abort(requestID: String) async throws -> Bool {
        var request = Melix_Worker_V1_AbortRequest()
        request.requestID = requestID

        let response: Melix_Worker_V1_AbortResponse = switch transport {
        case .bridge:
            try await sendUnary(
                kind: .abort,
                request: request,
                as: Melix_Worker_V1_AbortResponse.self
            )
        case .rpc(let runner):
            try await runner.abort(socketPath: socketPath, request: request)
        }
        return response.ok && response.found
    }

    public func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        let request = Melix_Worker_V1_GetRuntimeStatsRequest()
        switch transport {
        case .bridge:
            return try await sendUnary(
                kind: .getRuntimeStats,
                request: request,
                as: Melix_Worker_V1_GetRuntimeStatsResponse.self
            )
        case .rpc(let runner):
            return try await runner.runtimeStats(socketPath: socketPath, request: request)
        }
    }

    public func cacheStats() async throws -> Melix_Worker_V1_GetCacheStatsResponse {
        let request = Melix_Worker_V1_GetCacheStatsRequest()
        switch transport {
        case .bridge:
            return try await sendUnary(
                kind: .getCacheStats,
                request: request,
                as: Melix_Worker_V1_GetCacheStatsResponse.self
            )
        case .rpc(let runner):
            return try await runner.cacheStats(socketPath: socketPath, request: request)
        }
    }

    public func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(kind: .embed, request: request, as: Melix_Worker_V1_EmbedResponse.self)
        case .rpc(let runner):
            return try await runner.embed(socketPath: socketPath, request: request)
        }
    }

    public func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(kind: .rerank, request: request, as: Melix_Worker_V1_RerankResponse.self)
        case .rpc(let runner):
            return try await runner.rerank(socketPath: socketPath, request: request)
        }
    }

    public func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(kind: .transcribe, request: request, as: Melix_Worker_V1_TranscribeResponse.self)
        case .rpc(let runner):
            return try await runner.transcribe(socketPath: socketPath, request: request)
        }
    }

    public func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(kind: .speak, request: request, as: Melix_Worker_V1_SpeakResponse.self)
        case .rpc(let runner):
            return try await runner.speak(socketPath: socketPath, request: request)
        }
    }

    public func speakStream(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_SpeakStreamEvent, Error> {
        switch transport {
        case .bridge:
            return try await sendStream(kind: .speakStream, request: request, as: Melix_Worker_V1_SpeakStreamEvent.self)
        case .rpc(let runner):
            return try await runner.speakStream(socketPath: socketPath, request: request)
        }
    }

    public func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(kind: .imageGenerate, request: request, as: Melix_Worker_V1_ImageGenerateResponse.self)
        case .rpc(let runner):
            return try await runner.imageGenerate(socketPath: socketPath, request: request)
        }
    }

    public func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(kind: .imageEdit, request: request, as: Melix_Worker_V1_ImageEditResponse.self)
        case .rpc(let runner):
            return try await runner.imageEdit(socketPath: socketPath, request: request)
        }
    }

    public func getModelInfo(
        request: Melix_Worker_V1_GetModelInfoRequest
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(
                kind: .getModelInfo,
                request: request,
                as: Melix_Worker_V1_GetModelInfoResponse.self
            )
        case .rpc(let runner):
            return try await runner.getModelInfo(socketPath: socketPath, request: request)
        }
    }

    public func convertModel(
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error> {
        switch transport {
        case .bridge:
            return try await sendStream(kind: .convertModel, request: request, as: Melix_Worker_V1_ConvertModelEvent.self)
        case .rpc(let runner):
            return try await runner.convertModel(socketPath: socketPath, request: request)
        }
    }

    public func runDoctor(
        request: Melix_Worker_V1_RunDoctorRequest
    ) async throws -> Melix_Worker_V1_RunDoctorResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(
                kind: .runDoctor,
                request: request,
                as: Melix_Worker_V1_RunDoctorResponse.self
            )
        case .rpc(let runner):
            return try await runner.runDoctor(socketPath: socketPath, request: request)
        }
    }

    public func searchHubModels(
        request: Melix_Worker_V1_SearchHubModelsRequest
    ) async throws -> Melix_Worker_V1_SearchHubModelsResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(
                kind: .searchHubModels,
                request: request,
                as: Melix_Worker_V1_SearchHubModelsResponse.self
            )
        case .rpc(let runner):
            return try await runner.searchHubModels(socketPath: socketPath, request: request)
        }
    }

    public func getHubModelCard(
        request: Melix_Worker_V1_GetHubModelCardRequest
    ) async throws -> Melix_Worker_V1_GetHubModelCardResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(
                kind: .getHubModelCard,
                request: request,
                as: Melix_Worker_V1_GetHubModelCardResponse.self
            )
        case .rpc(let runner):
            return try await runner.getHubModelCard(socketPath: socketPath, request: request)
        }
    }

    public func runBench(
        request: Melix_Worker_V1_RunBenchRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_RunBenchEvent, Error> {
        switch transport {
        case .bridge:
            return try await sendStream(kind: .runBench, request: request, as: Melix_Worker_V1_RunBenchEvent.self)
        case .rpc(let runner):
            return try await runner.runBench(socketPath: socketPath, request: request)
        }
    }

    public func runBenchMatrix(
        request: Melix_Worker_V1_RunBenchMatrixRequest
    ) async throws -> Melix_Worker_V1_RunBenchMatrixResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(
                kind: .runBenchMatrix,
                request: request,
                as: Melix_Worker_V1_RunBenchMatrixResponse.self
            )
        case .rpc(let runner):
            return try await runner.runBenchMatrix(socketPath: socketPath, request: request)
        }
    }

    public func runEvaluation(
        request: Melix_Worker_V1_RunEvaluationRequest
    ) async throws -> Melix_Worker_V1_RunEvaluationResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(
                kind: .runEvaluation,
                request: request,
                as: Melix_Worker_V1_RunEvaluationResponse.self
            )
        case .rpc(let runner):
            return try await runner.runEvaluation(socketPath: socketPath, request: request)
        }
    }

    public func exportResults(
        request: Melix_Worker_V1_ExportResultsRequest
    ) async throws -> Melix_Worker_V1_ExportResultsResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(
                kind: .exportResults,
                request: request,
                as: Melix_Worker_V1_ExportResultsResponse.self
            )
        case .rpc(let runner):
            return try await runner.exportResults(socketPath: socketPath, request: request)
        }
    }

    public func submitResults(
        request: Melix_Worker_V1_SubmitResultsRequest
    ) async throws -> Melix_Worker_V1_SubmitResultsResponse {
        switch transport {
        case .bridge:
            return try await sendUnary(
                kind: .submitResults,
                request: request,
                as: Melix_Worker_V1_SubmitResultsResponse.self
            )
        case .rpc(let runner):
            return try await runner.submitResults(socketPath: socketPath, request: request)
        }
    }

    private func sendStream<Request: SwiftProtobuf.Message, Response: SwiftProtobuf.Message>(
        kind: BridgeCommandKind,
        request: Request,
        as _: Response.Type
    ) async throws -> AsyncThrowingStream<Response, Error> {
        guard case .bridge(let runner) = transport else {
            throw WorkerClientError.unavailable
        }
        let lineStream = try await runner.runStream(
            command: BridgeCommand(
                kind: kind,
                socketPath: socketPath,
                requestData: try request.serializedData()
            )
        )

        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for try await line in lineStream {
                        let event: Response = try decodeLine(line)
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
        guard case .bridge(let runner) = transport else {
            throw WorkerClientError.unavailable
        }
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
            throw WorkerClientError.requestFailed(
                code: payload.code ?? "unavailable",
                message: payload.message ?? "Worker bridge request failed."
            )
        default:
            throw WorkerClientError.unavailable
        }
    }
}

public enum BootstrapWorkerPreparation {
    private static let adapterSetHashExtKey = "melix.adapter_set_hash"
    private static let ocrExtKeys = [
        "ocr_prompt_profile_id",
        "ocr_prompt_template",
        "ocr_auto_prompt",
        "ocr_stop_sequences",
        "ocr_sampling_profile_id",
        "ocr_default_temperature",
        "ocr_default_top_p",
        "ocr_default_max_tokens",
    ]
    private static let vlmExtKeys = [
        "vision_family_id",
        "vision_prompt_profile_id",
        "vision_tokenization_mode",
        "vision_max_images_per_prompt",
        "vision_supports_tool_calls",
        "melix.multimodal_adapter_hash",
    ]
    private static let embeddingExtKeys = [
        "embedding_backend_id",
        "embedding_family_id",
        "embedding_pooling_mode",
        "embedding_normalization",
        "embedding_dimensions",
    ]
    private static let rerankExtKeys = [
        "rerank_backend_id",
        "rerank_family_id",
        "rerank_scoring_mode",
        "rerank_yes_no_labels",
    ]
    private static let audioExtKeys = [
        "melix.audio.backend_id",
        "melix.audio.family_id",
        "melix.audio.install_profile",
        "melix.audio.languages",
        "melix.audio.voice_mode",
        "melix.audio.output_formats",
        "melix.audio.supports_instructions",
        "melix.audio.voice_catalog_summary",
        "melix.audio.voice_locales",
        "melix.audio.default_locale",
        "melix.audio.packaged_default_locale",
        "melix.audio.locale_policy",
    ]
    private static let imageExtKeys = [
        "melix.image.backend_id",
        "melix.image.family_id",
        "melix.image.task_kind",
        "melix.image.default_workflow_role",
        "melix.image.supports_generation",
        "melix.image.supports_edit",
        "detected_family_id",
        "detected_task_kind",
        "detected_identity_source",
        "identity_override",
        "task_override",
    ]
    private static let capabilityExtKeys = [
        "melix.capability.route_kind",
        "melix.capability.class",
        "melix.capability.supported_modalities",
        "melix.capability.supported_tasks",
        "melix.capability.supported_parsers",
        "tool_parser_mode",
        "tool_parser_namespaces",
        "tool_parser_xml_fallback",
    ]
    private static let genericTextExtKeys = [
        "text_backend_id",
        "text_family_id",
        "model_architecture",
        "detected_architecture",
        "detected_family_id",
        "detected_identity_source",
        "identity_override",
        "melix.text.attention_profile",
        "melix.text.rope_profile",
        "melix.text.moe.enabled",
        "melix.text.moe.expert_count",
        "melix.text.moe.gate_dequant",
        "melix.model_path",
        "melix.model_revision",
        "melix.tokenizer_hash",
        "melix.parser_mode",
        "melix.reasoning_mode",
        "melix.derived_from_adapter",
        "melix.derived_from_model_id",
        "melix.derived_from_model_revision",
        "melix.activation_mode",
    ]
    private static let generationConfigExtKeys = [
        "melix.generation_config.source",
        "melix.generation_config.temperature",
        "melix.generation_config.top_p",
        "melix.generation_config.max_tokens",
        "melix.generation_config.do_sample",
    ]

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
        case "melix-whisper-mlx":
            return mlxWhisperModel()
        case "melix-parakeet-mlx":
            return mlxParakeetModel()
        case "melix-kokoro-mlx":
            return mlxKokoroModel()
        case "melix-qwen3-tts-mlx":
            return mlxQwen3TTSModel()
        case "melix-dev-image":
            return devImageModel()
        default:
            return nil
        }
    }

    public static func modelSpec(
        for summary: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Worker_V1_ModelSpec? {
        let baseSpec: Melix_Worker_V1_ModelSpec
        if let builtIn = modelSpec(for: summary.modelID) {
            baseSpec = builtIn
        } else if let generic = genericOCRModel(from: summary) {
            baseSpec = generic
        } else if let generic = genericVLMModel(from: summary) {
            baseSpec = generic
        } else if let generic = genericImageModel(from: summary) {
            baseSpec = generic
        } else if let generic = genericTextModel(from: summary) {
            baseSpec = generic
        } else {
            return nil
        }
        var spec = baseSpec
        applyExtOverride(for: adapterSetHashExtKey, from: summary, to: &spec)
        for key in ocrExtKeys {
            applyExtOverride(for: key, from: summary, to: &spec)
        }
        for key in vlmExtKeys {
            applyExtOverride(for: key, from: summary, to: &spec)
        }
        for key in embeddingExtKeys {
            applyExtOverride(for: key, from: summary, to: &spec)
        }
        for key in rerankExtKeys {
            applyExtOverride(for: key, from: summary, to: &spec)
        }
        for key in audioExtKeys {
            applyExtOverride(for: key, from: summary, to: &spec)
        }
        for key in imageExtKeys {
            applyExtOverride(for: key, from: summary, to: &spec)
        }
        for key in capabilityExtKeys {
            applyExtOverride(for: key, from: summary, to: &spec)
        }
        for key in genericTextExtKeys {
            applyExtOverride(for: key, from: summary, to: &spec)
        }
        for key in generationConfigExtKeys {
            applyExtOverride(for: key, from: summary, to: &spec)
        }
        let overriddenModelPath = summary.settings.ext["melix.model_path"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !overriddenModelPath.isEmpty {
            spec.modelPath = overriddenModelPath
        }
        let overriddenRevision = summary.settings.ext["melix.model_revision"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !overriddenRevision.isEmpty {
            spec.revision = overriddenRevision
        }
        let overriddenTokenizerHash = summary.settings.ext["melix.tokenizer_hash"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !overriddenTokenizerHash.isEmpty {
            spec.tokenizerHash = overriddenTokenizerHash
        }
        let adaptiveThinkingMode = summary.settings.adaptiveThinking.mode
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        if !adaptiveThinkingMode.isEmpty {
            spec.reasoningMode = adaptiveThinkingMode
        }
        if summary.settings.adaptiveThinking.budgetTokens > 0 {
            spec.ext["melix.adaptive_thinking.budget_tokens"] = String(summary.settings.adaptiveThinking.budgetTokens)
        }
        applySettingsOverride(from: summary, to: &spec)
        return spec
    }

    private static func genericTextModel(
        from summary: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Worker_V1_ModelSpec? {
        guard summary.kind == "text" else {
            return nil
        }
        let modelPath = summary.settings.ext["melix.model_path"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !modelPath.isEmpty else {
            return nil
        }

        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = summary.modelID
        model.modelPath = modelPath
        model.modelKind = "text"
        model.revision = summary.settings.ext["melix.model_revision"] ?? "derived"
        model.tokenizerHash = summary.settings.ext["melix.tokenizer_hash"] ?? "tok-derived"
        model.quantProfileID = summary.quantProfileID
        model.parserMode = summary.settings.ext["melix.parser_mode"] ?? "text"
        model.reasoningMode = summary.settings.ext["melix.reasoning_mode"] ?? "off"
        model.maxContext = summary.maxContext
        model.ext.merge(summary.settings.ext) { _, new in new }
        return model
    }

    private static func genericOCRModel(
        from summary: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Worker_V1_ModelSpec? {
        guard summary.kind == "ocr" else {
            return nil
        }
        let modelPath = summary.settings.ext["melix.model_path"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !modelPath.isEmpty else {
            return nil
        }

        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = summary.modelID
        model.modelPath = modelPath
        model.modelKind = "ocr"
        model.revision = summary.settings.ext["melix.model_revision"] ?? "imported"
        model.tokenizerHash = summary.settings.ext["melix.tokenizer_hash"] ?? "tok-ocr-imported"
        model.quantProfileID = summary.quantProfileID
        model.parserMode = summary.settings.ext["melix.parser_mode"] ?? "text"
        model.reasoningMode = summary.settings.ext["melix.reasoning_mode"] ?? "off"
        model.maxContext = summary.maxContext
        model.ext.merge(summary.settings.ext) { _, new in new }
        return model
    }

    private static func genericVLMModel(
        from summary: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Worker_V1_ModelSpec? {
        guard summary.kind == "vlm" else {
            return nil
        }
        let modelPath = summary.settings.ext["melix.model_path"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !modelPath.isEmpty else {
            return nil
        }

        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = summary.modelID
        model.modelPath = modelPath
        model.modelKind = "vlm"
        model.revision = summary.settings.ext["melix.model_revision"] ?? "imported"
        model.tokenizerHash = summary.settings.ext["melix.tokenizer_hash"] ?? "tok-vlm-imported"
        model.quantProfileID = summary.quantProfileID
        model.parserMode = summary.settings.ext["melix.parser_mode"] ?? "text"
        model.reasoningMode = summary.settings.ext["melix.reasoning_mode"] ?? "off"
        model.maxContext = summary.maxContext
        model.ext.merge(summary.settings.ext) { _, new in new }
        return model
    }

    private static func genericImageModel(
        from summary: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Worker_V1_ModelSpec? {
        guard summary.kind == "image" else {
            return nil
        }
        let modelPath = summary.settings.ext["melix.model_path"]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !modelPath.isEmpty else {
            return nil
        }

        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = summary.modelID
        model.modelPath = modelPath
        model.modelKind = "image"
        model.revision = summary.settings.ext["melix.model_revision"] ?? "imported"
        model.tokenizerHash = summary.settings.ext["melix.tokenizer_hash"] ?? "tok-image-imported"
        model.quantProfileID = summary.quantProfileID
        model.parserMode = summary.settings.ext["melix.parser_mode"] ?? "text"
        model.reasoningMode = summary.settings.ext["melix.reasoning_mode"] ?? "off"
        model.maxContext = summary.maxContext
        model.ext.merge(summary.settings.ext) { _, new in new }
        return model
    }

    private static func applyExtOverride(
        for key: String,
        from summary: Melix_Controlplane_V1_ModelSummary,
        to spec: inout Melix_Worker_V1_ModelSpec
    ) {
        guard let value = summary.settings.ext[key] else {
            return
        }
        if value.isEmpty {
            spec.ext.removeValue(forKey: key)
        } else {
            spec.ext[key] = value
        }
    }

    private static func applySettingsOverride(
        from summary: Melix_Controlplane_V1_ModelSummary,
        to spec: inout Melix_Worker_V1_ModelSpec
    ) {
        spec.settings.alias = summary.settings.alias
        spec.settings.typeOverride = summary.settings.typeOverride
        spec.settings.ttlSeconds = summary.settings.ttlSeconds
        spec.settings.pinOnLoad = summary.settings.pinOnLoad
        spec.settings.memoryPolicy = workerMemoryPolicy(for: summary.settings.memoryPolicy)
        spec.settings.diskStreamingMode = workerDiskStreamingMode(for: summary.settings.diskStreamingMode)
        spec.settings.cacheMode = workerCacheMode(for: summary.settings.cacheMode)
        spec.settings.cacheMemoryBudgetBytes = summary.settings.cacheMemoryBudgetBytes
        spec.settings.cacheMemoryBudgetPct = summary.settings.cacheMemoryBudgetPct
        spec.settings.cacheBlockSizeTokens = summary.settings.cacheBlockSizeTokens
        spec.settings.cacheDirectory = summary.settings.cacheDirectory
        spec.settings.multimodalCacheBudgetBytes = summary.settings.multimodalCacheBudgetBytes
        spec.settings.ext.merge(summary.settings.ext) { _, new in new }
    }

    private static func workerMemoryPolicy(
        for policy: Melix_Controlplane_V1_MemoryResidencyPolicy
    ) -> Melix_Worker_V1_MemoryResidencyPolicy {
        switch policy {
        case .memoryResidencyPinned:
            return .memoryResidencyPinned
        case .memoryResidencyTtl:
            return .memoryResidencyTtl
        case .memoryResidencyEvictable:
            return .memoryResidencyEvictable
        default:
            return .unspecified
        }
    }

    private static func workerDiskStreamingMode(
        for mode: Melix_Controlplane_V1_DiskStreamingMode
    ) -> Melix_Worker_V1_DiskStreamingMode {
        switch mode {
        case .diskStreamingDisabled:
            return .diskStreamingDisabled
        case .diskStreamingPreferDisk:
            return .diskStreamingPreferDisk
        case .diskStreamingRequireDisk:
            return .diskStreamingRequireDisk
        default:
            return .diskStreamingDisabled
        }
    }

    private static func workerCacheMode(
        for mode: Melix_Controlplane_V1_CacheMode
    ) -> Melix_Worker_V1_CacheMode {
        switch mode {
        case .tiered:
            return .tiered
        case .rotating:
            return .rotating
        case .hybrid:
            return .hybrid
        default:
            return .unspecified
        }
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
        let embeddingModel = await catalogAwareModelSpec(
            for: "melix-dev-embed",
            modelCatalog: modelCatalog,
            fallback: devEmbeddingModel()
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: embeddingModel,
            memoryBudgetBytes: memoryBudgetBytes
        )
        let rerankModel = await catalogAwareModelSpec(
            for: "melix-dev-rerank",
            modelCatalog: modelCatalog,
            fallback: devRerankModel()
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: rerankModel,
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
        let ocrModel = await catalogAwareModelSpec(
            for: "melix-dev-ocr",
            modelCatalog: modelCatalog,
            fallback: devOCRModel()
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: ocrModel,
            memoryBudgetBytes: memoryBudgetBytes
        )
        let vlmModel = await catalogAwareModelSpec(
            for: "melix-dev-vlm",
            modelCatalog: modelCatalog,
            fallback: devVLMModel()
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: vlmModel,
            memoryBudgetBytes: memoryBudgetBytes
        )
        let transcriptionModel = await catalogAwareModelSpec(
            for: "melix-dev-transcribe",
            modelCatalog: modelCatalog,
            fallback: devTranscriptionModel()
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: transcriptionModel,
            memoryBudgetBytes: memoryBudgetBytes
        )
        let speechModel = await catalogAwareModelSpec(
            for: "melix-dev-speech",
            modelCatalog: modelCatalog,
            fallback: devSpeechModel()
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: speechModel,
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
        let imageModel = await catalogAwareModelSpec(
            for: "melix-dev-image",
            modelCatalog: modelCatalog,
            fallback: devImageModel()
        )
        _ = try await preloadModel(
            workerClient: workerClient,
            modelCatalog: modelCatalog,
            model: imageModel,
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
        request.diskStreamingMode = model.settings.diskStreamingMode

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

    private static func catalogAwareModelSpec(
        for modelID: String,
        modelCatalog: ModelCatalog,
        fallback: Melix_Worker_V1_ModelSpec
    ) async -> Melix_Worker_V1_ModelSpec {
        if let summary = await modelCatalog.model(id: modelID),
           let spec = modelSpec(for: summary) {
            return spec
        }
        return fallback
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
        model.ext["embedding_backend_id"] = "bert-v1"
        model.ext["embedding_family_id"] = "bert"
        model.ext["embedding_pooling_mode"] = "cls"
        model.ext["embedding_normalization"] = "l2"
        model.ext["embedding_dimensions"] = "8"
        model.ext["melix.adapter_set_hash"] = "embedding-family-bert"
        model.ext["melix.capability.route_kind"] = "python_embedding"
        model.ext["melix.capability.class"] = "embedding"
        model.ext["melix.capability.supported_modalities"] = "text"
        model.ext["melix.capability.supported_tasks"] = "embed"
        model.ext["melix.capability.supported_parsers"] = "text"
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
        model.ext["rerank_backend_id"] = "token-overlap-v1"
        model.ext["rerank_family_id"] = "jina-v3"
        model.ext["rerank_scoring_mode"] = "order-aware-overlap"
        model.ext["melix.adapter_set_hash"] = "rerank-family-jina-v3"
        model.ext["melix.capability.route_kind"] = "python_rerank"
        model.ext["melix.capability.class"] = "rerank"
        model.ext["melix.capability.supported_modalities"] = "text"
        model.ext["melix.capability.supported_tasks"] = "rerank"
        model.ext["melix.capability.supported_parsers"] = "text"
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
        model.ext["ocr_prompt_profile_id"] = "ocr-default-v1"
        model.ext["ocr_prompt_template"] = "OCR instruction: {prompt}"
        model.ext["ocr_auto_prompt"] = "Extract the text from the image exactly as written."
        model.ext["ocr_stop_sequences"] = "<ocr:end>"
        model.ext["ocr_sampling_profile_id"] = "ocr-deterministic"
        model.ext["ocr_default_temperature"] = "0.0"
        model.ext["ocr_default_top_p"] = "1.0"
        model.ext["ocr_default_max_tokens"] = "256"
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
        model.ext["vision_family_id"] = "llava-v1"
        model.ext["vision_prompt_profile_id"] = "llava-chatml-v1"
        model.ext["vision_tokenization_mode"] = "interleaved"
        model.ext["vision_max_images_per_prompt"] = "8"
        model.ext["vision_supports_tool_calls"] = "true"
        model.ext["melix.multimodal_adapter_hash"] = "vision-family-llava-v1"
        model.ext["melix.adapter_set_hash"] = "vision-family-llava-v1"
        model.ext["melix.capability.route_kind"] = "python_vlm"
        model.ext["melix.capability.class"] = "vlm"
        model.ext["melix.capability.supported_modalities"] = "text,image"
        model.ext["melix.capability.supported_tasks"] = "vlm,generate"
        model.ext["melix.capability.supported_parsers"] = "text,qwen"
        model.ext["tool_parser_mode"] = "qwen"
        model.ext["tool_parser_namespaces"] = "tools.vision"
        model.ext["tool_parser_xml_fallback"] = "true"
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
        model.ext["melix.audio.backend_id"] = "deterministic"
        model.ext["melix.audio.family_id"] = "deterministic-transcription"
        model.ext["melix.audio.install_profile"] = ""
        model.ext["melix.audio.languages"] = "und"
        model.ext["melix.audio.voice_mode"] = ""
        model.ext["melix.audio.output_formats"] = ""
        model.ext["melix.audio.supports_instructions"] = "false"
        model.ext["melix.audio.voice_catalog_summary"] = ""
        model.ext["melix.audio.voice_locales"] = ""
        model.ext["melix.audio.default_locale"] = ""
        model.ext["melix.audio.packaged_default_locale"] = ""
        model.ext["melix.audio.locale_policy"] = ""
        model.ext["melix.adapter_set_hash"] = "audio-family-deterministic-transcription"
        model.ext["melix.capability.route_kind"] = "python_transcription"
        model.ext["melix.capability.class"] = "transcription"
        model.ext["melix.capability.supported_modalities"] = "audio,text"
        model.ext["melix.capability.supported_tasks"] = "transcribe"
        model.ext["melix.capability.supported_parsers"] = "text"
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
        model.ext["melix.audio.backend_id"] = "deterministic"
        model.ext["melix.audio.family_id"] = "deterministic-speech"
        model.ext["melix.audio.install_profile"] = ""
        model.ext["melix.audio.languages"] = "und"
        model.ext["melix.audio.voice_mode"] = "named"
        model.ext["melix.audio.output_formats"] = "wav,mp3"
        model.ext["melix.audio.supports_instructions"] = "false"
        model.ext["melix.audio.voice_catalog_summary"] = "Deterministic synthetic default voice."
        model.ext["melix.audio.voice_locales"] = "und"
        model.ext["melix.audio.default_locale"] = "und"
        model.ext["melix.audio.packaged_default_locale"] = "und"
        model.ext["melix.audio.locale_policy"] = "request>model_default>packaged_default"
        model.ext["melix.adapter_set_hash"] = "audio-family-deterministic-speech"
        model.ext["melix.capability.route_kind"] = "python_speech"
        model.ext["melix.capability.class"] = "speech"
        model.ext["melix.capability.supported_modalities"] = "text,audio"
        model.ext["melix.capability.supported_tasks"] = "speak"
        model.ext["melix.capability.supported_parsers"] = "text"
        return model
    }

    private static func mlxWhisperModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-whisper-mlx"
        model.modelPath = "mlx-community/whisper-large-v3-turbo-asr-fp16"
        model.modelKind = "transcription"
        model.revision = "mlx-audio"
        model.tokenizerHash = "tok-whisper-mlx"
        model.quantProfileID = "fp16"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 4096
        model.ext["melix.audio.backend_id"] = "mlx_audio.stt"
        model.ext["melix.audio.family_id"] = "whisper"
        model.ext["melix.audio.install_profile"] = "audio-stt"
        model.ext["melix.audio.languages"] = "auto"
        model.ext["melix.audio.voice_mode"] = ""
        model.ext["melix.audio.output_formats"] = ""
        model.ext["melix.audio.supports_instructions"] = "false"
        model.ext["melix.audio.voice_catalog_summary"] = ""
        model.ext["melix.audio.voice_locales"] = ""
        model.ext["melix.audio.default_locale"] = ""
        model.ext["melix.audio.packaged_default_locale"] = ""
        model.ext["melix.audio.locale_policy"] = ""
        model.ext["melix.adapter_set_hash"] = "audio-family-whisper"
        model.ext["melix.capability.route_kind"] = "python_transcription"
        model.ext["melix.capability.class"] = "transcription"
        model.ext["melix.capability.supported_modalities"] = "audio,text"
        model.ext["melix.capability.supported_tasks"] = "transcribe"
        model.ext["melix.capability.supported_parsers"] = "text"
        return model
    }

    private static func mlxParakeetModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-parakeet-mlx"
        model.modelPath = "mlx-community/parakeet-tdt-0.6b-v2"
        model.modelKind = "transcription"
        model.revision = "mlx-audio"
        model.tokenizerHash = "tok-parakeet-mlx"
        model.quantProfileID = "fp16"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 4096
        model.ext["melix.audio.backend_id"] = "mlx_audio.stt"
        model.ext["melix.audio.family_id"] = "parakeet"
        model.ext["melix.audio.install_profile"] = "audio-stt"
        model.ext["melix.audio.languages"] = "auto"
        model.ext["melix.audio.voice_mode"] = ""
        model.ext["melix.audio.output_formats"] = ""
        model.ext["melix.audio.supports_instructions"] = "false"
        model.ext["melix.audio.voice_catalog_summary"] = ""
        model.ext["melix.audio.voice_locales"] = ""
        model.ext["melix.audio.default_locale"] = ""
        model.ext["melix.audio.packaged_default_locale"] = ""
        model.ext["melix.audio.locale_policy"] = ""
        model.ext["melix.adapter_set_hash"] = "audio-family-parakeet"
        model.ext["melix.capability.route_kind"] = "python_transcription"
        model.ext["melix.capability.class"] = "transcription"
        model.ext["melix.capability.supported_modalities"] = "audio,text"
        model.ext["melix.capability.supported_tasks"] = "transcribe"
        model.ext["melix.capability.supported_parsers"] = "text"
        return model
    }

    private static func mlxKokoroModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-kokoro-mlx"
        model.modelPath = "mlx-community/Kokoro-82M-bf16"
        model.modelKind = "speech"
        model.revision = "mlx-audio"
        model.tokenizerHash = "tok-kokoro-mlx"
        model.quantProfileID = "bf16"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 4096
        model.ext["melix.audio.backend_id"] = "mlx_audio.tts"
        model.ext["melix.audio.family_id"] = "kokoro"
        model.ext["melix.audio.install_profile"] = "audio-tts"
        model.ext["melix.audio.languages"] = "en"
        model.ext["melix.audio.voice_mode"] = "named"
        model.ext["melix.audio.output_formats"] = "wav"
        model.ext["melix.audio.supports_instructions"] = "false"
        model.ext["melix.audio.voice_catalog_summary"] =
            "Named English voices exposed by the Kokoro speaker catalog."
        model.ext["melix.audio.voice_locales"] = "en"
        model.ext["melix.audio.default_locale"] = "en"
        model.ext["melix.audio.packaged_default_locale"] = "en"
        model.ext["melix.audio.locale_policy"] = "request>model_default>packaged_default"
        model.ext["melix.adapter_set_hash"] = "audio-family-kokoro"
        model.ext["melix.capability.route_kind"] = "python_speech"
        model.ext["melix.capability.class"] = "speech"
        model.ext["melix.capability.supported_modalities"] = "text,audio"
        model.ext["melix.capability.supported_tasks"] = "speak"
        model.ext["melix.capability.supported_parsers"] = "text"
        return model
    }

    private static func mlxQwen3TTSModel() -> Melix_Worker_V1_ModelSpec {
        var model = Melix_Worker_V1_ModelSpec()
        model.modelID = "melix-qwen3-tts-mlx"
        model.modelPath = "mlx-community/Qwen3-TTS-4B-Instruct-2507-4bit"
        model.modelKind = "speech"
        model.revision = "mlx-audio"
        model.tokenizerHash = "tok-qwen3-tts-mlx"
        model.quantProfileID = "4bit"
        model.parserMode = "text"
        model.reasoningMode = "off"
        model.maxContext = 4096
        model.ext["melix.audio.backend_id"] = "mlx_audio.tts"
        model.ext["melix.audio.family_id"] = "qwen3-tts"
        model.ext["melix.audio.install_profile"] = "audio-tts"
        model.ext["melix.audio.languages"] = "zh,en"
        model.ext["melix.audio.voice_mode"] = "hybrid"
        model.ext["melix.audio.output_formats"] = "wav"
        model.ext["melix.audio.supports_instructions"] = "true"
        model.ext["melix.audio.voice_catalog_summary"] =
            "Hybrid named and instruction-conditioned multilingual voices for Chinese and English synthesis."
        model.ext["melix.audio.voice_locales"] = "zh,en"
        model.ext["melix.audio.default_locale"] = "zh"
        model.ext["melix.audio.packaged_default_locale"] = "zh"
        model.ext["melix.audio.locale_policy"] = "request>model_default>packaged_default"
        model.ext["melix.adapter_set_hash"] = "audio-family-qwen3-tts"
        model.ext["melix.capability.route_kind"] = "python_speech"
        model.ext["melix.capability.class"] = "speech"
        model.ext["melix.capability.supported_modalities"] = "text,audio"
        model.ext["melix.capability.supported_tasks"] = "speak"
        model.ext["melix.capability.supported_parsers"] = "text"
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
    let code: String?
    let message: String?

    enum CodingKeys: String, CodingKey {
        case kind
        case messageBase64 = "message_b64"
        case code
        case message
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

public struct GRPCPythonWorkerRunner: PythonWorkerRPCRunning, Sendable {
    private let makeEventLoopGroup: @Sendable () -> MultiThreadedEventLoopGroup
    private let shutdownEventLoopGroup: @Sendable (MultiThreadedEventLoopGroup) async throws -> Void

    public init(
        makeEventLoopGroup: @escaping @Sendable () -> MultiThreadedEventLoopGroup = {
            MultiThreadedEventLoopGroup(numberOfThreads: 1)
        },
        shutdownEventLoopGroup: @escaping @Sendable (MultiThreadedEventLoopGroup) async throws -> Void = { group in
            try await group.shutdownGracefully()
        }
    ) {
        self.makeEventLoopGroup = makeEventLoopGroup
        self.shutdownEventLoopGroup = shutdownEventLoopGroup
    }

    public func handshake(
        socketPath: String,
        request: Melix_Worker_V1_HandshakeRequest
    ) async throws -> Melix_Worker_V1_HandshakeResponse {
        try await withRPCClients(socketPath: socketPath) { runtimeClient, _, _, _ in
            try await runtimeClient.handshake(request)
        }
    }

    public func loadModel(
        socketPath: String,
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        try await withRPCClients(socketPath: socketPath) { runtimeClient, _, _, _ in
            try await runtimeClient.loadModel(request)
        }
    }

    public func unloadModel(
        socketPath: String,
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        try await withRPCClients(socketPath: socketPath) { runtimeClient, _, _, _ in
            try await runtimeClient.unloadModel(request)
        }
    }

    public func runtimeStats(
        socketPath: String,
        request: Melix_Worker_V1_GetRuntimeStatsRequest
    ) async throws -> Melix_Worker_V1_GetRuntimeStatsResponse {
        try await withRPCClients(socketPath: socketPath) { runtimeClient, _, _, _ in
            try await runtimeClient.getRuntimeStats(request)
        }
    }

    public func cacheStats(
        socketPath: String,
        request: Melix_Worker_V1_GetCacheStatsRequest
    ) async throws -> Melix_Worker_V1_GetCacheStatsResponse {
        try await withRPCClients(socketPath: socketPath) { _, _, cacheClient, _ in
            try await cacheClient.getCacheStats(request)
        }
    }

    public func generate(
        socketPath: String,
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _, _ in
                        try await inferenceClient.generate(request) { response in
                            for try await event in response.messages {
                                continuation.yield(event)
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: workerClientError(from: error))
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    public func prefill(
        socketPath: String,
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse {
        try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _, _ in
            try await inferenceClient.prefill(request)
        }
    }

    public func decode(
        socketPath: String,
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        let startupLatch = StreamStartupLatch()
        let stream = AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _, _ in
                        try await inferenceClient.decode(request) { response in
                            await startupLatch.markReady()
                            for try await event in response.messages {
                                continuation.yield(event)
                            }
                        }
                    }
                    await startupLatch.markReady()
                    continuation.finish()
                } catch {
                    let clientError = workerClientError(from: error)
                    await startupLatch.markFailed(clientError)
                    continuation.finish(throwing: clientError)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
        try await startupLatch.waitUntilReady()
        return stream
    }

    public func abort(
        socketPath: String,
        request: Melix_Worker_V1_AbortRequest
    ) async throws -> Melix_Worker_V1_AbortResponse {
        try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _, _ in
            try await inferenceClient.abort(request)
        }
    }

    public func embed(
        socketPath: String,
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse {
        try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _, _ in
            try await inferenceClient.embed(request)
        }
    }

    public func rerank(
        socketPath: String,
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse {
        try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _, _ in
            try await inferenceClient.rerank(request)
        }
    }

    public func transcribe(
        socketPath: String,
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse {
        try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _, _ in
            try await inferenceClient.transcribe(request)
        }
    }

    public func speak(
        socketPath: String,
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse {
        try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _, _ in
            try await inferenceClient.speak(request)
        }
    }

    public func speakStream(
        socketPath: String,
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_SpeakStreamEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _, _ in
                        try await inferenceClient.speakStream(request) { response in
                            for try await event in response.messages {
                                continuation.yield(event)
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: workerClientError(from: error))
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    public func imageGenerate(
        socketPath: String,
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse {
        try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _, _ in
            try await inferenceClient.imageGenerate(request, options: imageRequestOptions())
        }
    }

    public func imageEdit(
        socketPath: String,
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse {
        try await withRPCClients(socketPath: socketPath) { _, inferenceClient, _, _ in
            try await inferenceClient.imageEdit(request, options: imageRequestOptions())
        }
    }

    public func getModelInfo(
        socketPath: String,
        request: Melix_Worker_V1_GetModelInfoRequest
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse {
        try await withRPCClients(socketPath: socketPath) { _, _, _, maintenanceClient in
            try await maintenanceClient.getModelInfo(request)
        }
    }

    public func convertModel(
        socketPath: String,
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    try await withRPCClients(socketPath: socketPath) { _, _, _, maintenanceClient in
                        try await maintenanceClient.convertModel(request) { response in
                            for try await event in response.messages {
                                continuation.yield(event)
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: workerClientError(from: error))
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    public func runDoctor(
        socketPath: String,
        request: Melix_Worker_V1_RunDoctorRequest
    ) async throws -> Melix_Worker_V1_RunDoctorResponse {
        try await withRPCClients(socketPath: socketPath) { _, _, _, maintenanceClient in
            try await maintenanceClient.runDoctor(request)
        }
    }

    public func searchHubModels(
        socketPath: String,
        request: Melix_Worker_V1_SearchHubModelsRequest
    ) async throws -> Melix_Worker_V1_SearchHubModelsResponse {
        try await withRPCClients(socketPath: socketPath) { _, _, _, maintenanceClient in
            try await maintenanceClient.searchHubModels(request)
        }
    }

    public func getHubModelCard(
        socketPath: String,
        request: Melix_Worker_V1_GetHubModelCardRequest
    ) async throws -> Melix_Worker_V1_GetHubModelCardResponse {
        try await withRPCClients(socketPath: socketPath) { _, _, _, maintenanceClient in
            try await maintenanceClient.getHubModelCard(request)
        }
    }

    public func runBench(
        socketPath: String,
        request: Melix_Worker_V1_RunBenchRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_RunBenchEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    try await withRPCClients(socketPath: socketPath) { _, _, _, maintenanceClient in
                        try await maintenanceClient.runBench(request) { response in
                            for try await event in response.messages {
                                continuation.yield(event)
                            }
                        }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: workerClientError(from: error))
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    public func runBenchMatrix(
        socketPath: String,
        request: Melix_Worker_V1_RunBenchMatrixRequest
    ) async throws -> Melix_Worker_V1_RunBenchMatrixResponse {
        try await withRPCClients(socketPath: socketPath) { _, _, _, maintenanceClient in
            try await maintenanceClient.runBenchMatrix(request)
        }
    }

    public func runEvaluation(
        socketPath: String,
        request: Melix_Worker_V1_RunEvaluationRequest
    ) async throws -> Melix_Worker_V1_RunEvaluationResponse {
        try await withRPCClients(socketPath: socketPath) { _, _, _, maintenanceClient in
            try await maintenanceClient.runEvaluation(request)
        }
    }

    public func exportResults(
        socketPath: String,
        request: Melix_Worker_V1_ExportResultsRequest
    ) async throws -> Melix_Worker_V1_ExportResultsResponse {
        try await withRPCClients(socketPath: socketPath) { _, _, _, maintenanceClient in
            try await maintenanceClient.exportResults(request)
        }
    }

    public func submitResults(
        socketPath: String,
        request: Melix_Worker_V1_SubmitResultsRequest
    ) async throws -> Melix_Worker_V1_SubmitResultsResponse {
        try await withRPCClients(socketPath: socketPath) { _, _, _, maintenanceClient in
            try await maintenanceClient.submitResults(request)
        }
    }

    private func withRPCClients<Result: Sendable>(
        socketPath: String,
        operation: @Sendable @escaping (
            Melix_Worker_V1_RuntimeService.Client<HTTP2ClientTransport.Posix>,
            Melix_Worker_V1_InferenceService.Client<HTTP2ClientTransport.Posix>,
            Melix_Worker_V1_CacheService.Client<HTTP2ClientTransport.Posix>,
            Melix_Worker_V1_MaintenanceService.Client<HTTP2ClientTransport.Posix>
        ) async throws -> Result
    ) async throws -> Result {
        let eventLoopGroup = makeEventLoopGroup()
        do {
            let result = try await withGRPCClient(
                transport: .http2NIOPosix(
                    target: .unixDomainSocket(path: socketPath),
                    transportSecurity: .plaintext,
                    eventLoopGroup: eventLoopGroup
                )
            ) { client in
                let runtimeClient = Melix_Worker_V1_RuntimeService.Client(wrapping: client)
                let inferenceClient = Melix_Worker_V1_InferenceService.Client(wrapping: client)
                let cacheClient = Melix_Worker_V1_CacheService.Client(wrapping: client)
                let maintenanceClient = Melix_Worker_V1_MaintenanceService.Client(wrapping: client)
                return try await operation(runtimeClient, inferenceClient, cacheClient, maintenanceClient)
            }
            try await shutdownEventLoopGroup(eventLoopGroup)
            return result
        } catch {
            try? await shutdownEventLoopGroup(eventLoopGroup)
            throw workerClientError(from: error)
        }
    }

    private func imageRequestOptions(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> GRPCCore.CallOptions {
        var options = GRPCCore.CallOptions.defaults
        let rawValue = environment["MELIX_IMAGE_REQUEST_TIMEOUT_SECONDS", default: ""]
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let timeoutSeconds = Int(rawValue).flatMap { $0 > 0 ? $0 : nil } ?? 1_800
        options.timeout = .seconds(timeoutSeconds)
        return options
    }
}

private func workerClientError(from error: Error) -> WorkerClientError {
    if let workerError = error as? WorkerClientError {
        return workerError
    }
    if let rpcError = error as? GRPCCore.RPCError {
        if rpcError.code == .unavailable {
            return .unavailable
        }
        return .requestFailed(
            code: bridgeCompatibleErrorCode(from: rpcError.code),
            message: rpcError.message.trimmingCharacters(in: .whitespacesAndNewlines)
        )
    }
    return .unavailable
}

private func bridgeCompatibleErrorCode(from code: GRPCCore.RPCError.Code) -> String {
    switch code {
    case .cancelled:
        return "CANCELLED"
    case .unknown:
        return "UNKNOWN"
    case .invalidArgument:
        return "INVALID_ARGUMENT"
    case .deadlineExceeded:
        return "DEADLINE_EXCEEDED"
    case .notFound:
        return "NOT_FOUND"
    case .alreadyExists:
        return "ALREADY_EXISTS"
    case .permissionDenied:
        return "PERMISSION_DENIED"
    case .resourceExhausted:
        return "RESOURCE_EXHAUSTED"
    case .failedPrecondition:
        return "FAILED_PRECONDITION"
    case .aborted:
        return "ABORTED"
    case .outOfRange:
        return "OUT_OF_RANGE"
    case .unimplemented:
        return "UNIMPLEMENTED"
    case .internalError:
        return "INTERNAL"
    case .unavailable:
        return "UNAVAILABLE"
    case .dataLoss:
        return "DATA_LOSS"
    case .unauthenticated:
        return "UNAUTHENTICATED"
    default:
        return code.description
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
        let stdoutTask = Task {
            try String(decoding: stdout.fileHandleForReading.readToEnd() ?? Data(), as: UTF8.self)
        }
        let stderrTask = Task {
            try String(decoding: stderr.fileHandleForReading.readToEnd() ?? Data(), as: UTF8.self)
        }
        defer {
            stdoutTask.cancel()
            stderrTask.cancel()
        }

        let terminationStatus = await waitForTermination(
            of: process,
            state: terminationState
        )

        let output = try await stdoutTask.value
        let errorOutput = try await stderrTask.value

        guard let line = output.split(separator: "\n").last.map(String.init),
              !line.isEmpty
        else {
            logBridgeProcessFailure(
                command: command,
                terminationStatus: terminationStatus,
                stdout: output,
                stderr: errorOutput
            )
            throw WorkerClientError.unavailable
        }
        if terminationStatus != 0 {
            logBridgeProcessFailure(
                command: command,
                terminationStatus: terminationStatus,
                stdout: output,
                stderr: errorOutput
            )
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
            let stderrTask = Task {
                try stderr.fileHandleForReading.readToEnd()
            }
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
                        _ = try await stderrTask.value
                        continuation.finish()
                    } else {
                        _ = try await stderrTask.value
                        continuation.finish(throwing: WorkerClientError.unavailable)
                    }
                } catch {
                    continuation.finish(throwing: error)
                }
            }

            continuation.onTermination = { _ in
                task.cancel()
                stderrTask.cancel()
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
        if let pythonExecutable = environment["MELIX_PYTHON_BRIDGE_EXECUTABLE"], !pythonExecutable.isEmpty {
            process.executableURL = URL(fileURLWithPath: pythonExecutable)
            process.arguments = [
                "\(repoRoot)/services/mlx-worker-python/worker/control_plane_bridge.py",
                command.kind.rawValue,
                "--socket-path",
                command.socketPath,
                "--request-b64",
                command.requestData.base64EncodedString(),
            ]
        } else {
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = [
                "uv",
                "run",
                "--project",
                "\(repoRoot)/services/mlx-worker-python",
                "--extra",
                "mlx",
                "python",
                "\(repoRoot)/services/mlx-worker-python/worker/control_plane_bridge.py",
                command.kind.rawValue,
                "--socket-path",
                command.socketPath,
                "--request-b64",
                command.requestData.base64EncodedString(),
            ]
        }
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

    private func logBridgeProcessFailure(
        command: BridgeCommand,
        terminationStatus: Int32,
        stdout: String,
        stderr: String
    ) {
        let stderrPreview = Self.preview(stderr)
        let stdoutPreview = Self.preview(stdout)
        print(
            "Melix Python bridge command \(command.kind.rawValue) ended with status \(terminationStatus); "
                + "stdout_bytes=\(stdout.utf8.count) stderr_bytes=\(stderr.utf8.count) "
                + "stdout_preview=\(stdoutPreview) stderr_preview=\(stderrPreview)"
        )
    }

    private static func preview(_ value: String) -> String {
        let collapsed = value
            .replacingOccurrences(of: "\n", with: "\\n")
            .replacingOccurrences(of: "\r", with: "\\r")
        let limit = 2_000
        guard collapsed.count > limit else {
            return collapsed
        }
        let endIndex = collapsed.index(collapsed.startIndex, offsetBy: limit)
        return String(collapsed[..<endIndex]) + "...<truncated>"
    }
}
