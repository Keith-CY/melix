import Foundation
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
    case imageGenerate = "image-generate"
    case imageEdit = "image-edit"
    case getModelInfo = "get-model-info"
    case convertModel = "convert-model"
    case runDoctor = "run-doctor"
    case searchHubModels = "search-hub-models"
    case getHubModelCard = "get-hub-model-card"
    case runBench = "run-bench"
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
        try await sendStream(kind: .generate, request: request, as: Melix_Worker_V1_ExecuteEvent.self)
    }

    public func prefill(
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse {
        try await sendUnary(kind: .prefill, request: request, as: Melix_Worker_V1_PrefillResponse.self)
    }

    public func decode(
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        try await sendStream(kind: .decode, request: request, as: Melix_Worker_V1_ExecuteEvent.self)
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

    public func cacheStats() async throws -> Melix_Worker_V1_GetCacheStatsResponse {
        try await sendUnary(
            kind: .getCacheStats,
            request: Melix_Worker_V1_GetCacheStatsRequest(),
            as: Melix_Worker_V1_GetCacheStatsResponse.self
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
        try await sendStream(kind: .convertModel, request: request, as: Melix_Worker_V1_ConvertModelEvent.self)
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

    public func searchHubModels(
        request: Melix_Worker_V1_SearchHubModelsRequest
    ) async throws -> Melix_Worker_V1_SearchHubModelsResponse {
        try await sendUnary(
            kind: .searchHubModels,
            request: request,
            as: Melix_Worker_V1_SearchHubModelsResponse.self
        )
    }

    public func getHubModelCard(
        request: Melix_Worker_V1_GetHubModelCardRequest
    ) async throws -> Melix_Worker_V1_GetHubModelCardResponse {
        try await sendUnary(
            kind: .getHubModelCard,
            request: request,
            as: Melix_Worker_V1_GetHubModelCardResponse.self
        )
    }

    public func runBench(
        request: Melix_Worker_V1_RunBenchRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_RunBenchEvent, Error> {
        try await sendStream(kind: .runBench, request: request, as: Melix_Worker_V1_RunBenchEvent.self)
    }

    public func runEvaluation(
        request: Melix_Worker_V1_RunEvaluationRequest
    ) async throws -> Melix_Worker_V1_RunEvaluationResponse {
        try await sendUnary(
            kind: .runEvaluation,
            request: request,
            as: Melix_Worker_V1_RunEvaluationResponse.self
        )
    }

    public func exportResults(
        request: Melix_Worker_V1_ExportResultsRequest
    ) async throws -> Melix_Worker_V1_ExportResultsResponse {
        try await sendUnary(
            kind: .exportResults,
            request: request,
            as: Melix_Worker_V1_ExportResultsResponse.self
        )
    }

    public func submitResults(
        request: Melix_Worker_V1_SubmitResultsRequest
    ) async throws -> Melix_Worker_V1_SubmitResultsResponse {
        try await sendUnary(
            kind: .submitResults,
            request: request,
            as: Melix_Worker_V1_SubmitResultsResponse.self
        )
    }

    private func sendStream<Request: SwiftProtobuf.Message, Response: SwiftProtobuf.Message>(
        kind: BridgeCommandKind,
        request: Request,
        as _: Response.Type
    ) async throws -> AsyncThrowingStream<Response, Error> {
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
        let baseSpec: Melix_Worker_V1_ModelSpec
        if let builtIn = modelSpec(for: summary.modelID) {
            baseSpec = builtIn
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
        for key in capabilityExtKeys {
            applyExtOverride(for: key, from: summary, to: &spec)
        }
        for key in genericTextExtKeys {
            applyExtOverride(for: key, from: summary, to: &spec)
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
}
