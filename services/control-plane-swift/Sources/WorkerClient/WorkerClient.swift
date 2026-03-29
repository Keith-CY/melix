import Foundation
import MelixWorkerProtocol

public enum WorkerClientError: Error, Equatable {
    case unavailable
}

public protocol WorkerClient: Sendable {
    func canDispatchRequests() async -> Bool
    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>
    func abort(requestID: String) async throws -> Bool
}

public protocol NonTextInferenceWorkerClientProtocol: WorkerClient {
    func embed(
        request: Melix_Worker_V1_EmbedRequest
    ) async throws -> Melix_Worker_V1_EmbedResponse

    func rerank(
        request: Melix_Worker_V1_RerankRequest
    ) async throws -> Melix_Worker_V1_RerankResponse

    func transcribe(
        request: Melix_Worker_V1_TranscribeRequest
    ) async throws -> Melix_Worker_V1_TranscribeResponse

    func speak(
        request: Melix_Worker_V1_SpeakRequest
    ) async throws -> Melix_Worker_V1_SpeakResponse

    func imageGenerate(
        request: Melix_Worker_V1_ImageGenerateRequest
    ) async throws -> Melix_Worker_V1_ImageGenerateResponse

    func imageEdit(
        request: Melix_Worker_V1_ImageEditRequest
    ) async throws -> Melix_Worker_V1_ImageEditResponse
}

public protocol PhaseAwareWorkerClientProtocol: WorkerClient {
    func prefill(
        request: Melix_Worker_V1_PrefillRequest
    ) async throws -> Melix_Worker_V1_PrefillResponse

    func decode(
        request: Melix_Worker_V1_DecodeRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>
}

public protocol CacheIntrospectingWorkerClientProtocol: WorkerClient {
    func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse
    func cacheStats() async throws -> Melix_Worker_V1_GetCacheStatsResponse
}

public protocol RuntimeIntrospectingWorkerClientProtocol: WorkerClient {
    func runtimeStats() async throws -> Melix_Worker_V1_GetRuntimeStatsResponse
}

public protocol WorkerRoutingClient: WorkerClient {
    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse
}

public protocol ModelOperationsWorkerClientProtocol: WorkerClient {
    func getModelInfo(
        request: Melix_Worker_V1_GetModelInfoRequest
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse

    func convertModel(
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error>

    func runDoctor(
        request: Melix_Worker_V1_RunDoctorRequest
    ) async throws -> Melix_Worker_V1_RunDoctorResponse

    func runBench(
        request: Melix_Worker_V1_RunBenchRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_RunBenchEvent, Error>
}

public struct NullWorkerClient: WorkerRoutingClient {
    public init() {}

    public func canDispatchRequests() async -> Bool {
        false
    }

    public func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        throw WorkerClientError.unavailable
    }

    public func abort(requestID: String) async throws -> Bool {
        false
    }

    public func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        throw WorkerClientError.unavailable
    }
}
