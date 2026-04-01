import Foundation
import MelixWorkerProtocol

public enum WorkerClientError: Error, Equatable {
    case unavailable
}

public struct WorkerMemoryEvidence: Equatable, Sendable {
    public let residentBytes: UInt64
    public let modelResidentBytes: UInt64
    public let cacheResidentBytes: UInt64
    public let kvCacheBytes: UInt64
    public let peakAllocationBytes: UInt64
    public let memoryHeadroomBytes: UInt64

    public init(stats: Melix_Worker_V1_RuntimeStats) {
        let modelResidentBytes = stats.modelResidentBytes > 0 ? stats.modelResidentBytes : stats.residentBytes
        let cacheResidentBytes = stats.cacheResidentBytes > 0 ? stats.cacheResidentBytes : stats.l1CacheBytes
        let kvCacheBytes = stats.kvCacheBytes
        let normalizedResidentBytes = WorkerMemoryEvidence.sumResidentBytes(
            modelResidentBytes,
            cacheResidentBytes,
            kvCacheBytes
        )

        self.modelResidentBytes = modelResidentBytes
        self.cacheResidentBytes = cacheResidentBytes
        self.kvCacheBytes = kvCacheBytes
        self.residentBytes = max(stats.residentBytes, normalizedResidentBytes)
        self.peakAllocationBytes = stats.peakAllocationBytes
        self.memoryHeadroomBytes = stats.memoryHeadroomBytes
    }

    private static func sumResidentBytes(_ values: UInt64...) -> UInt64 {
        values.reduce(0) { partial, value in
            let (sum, overflow) = partial.addingReportingOverflow(value)
            return overflow ? UInt64.max : sum
        }
    }
}

public extension Melix_Worker_V1_GetRuntimeStatsResponse {
    var memoryEvidence: WorkerMemoryEvidence {
        WorkerMemoryEvidence(stats: stats)
    }
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

    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse
}

public extension WorkerRoutingClient {
    func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        throw WorkerClientError.unavailable
    }
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

    func runEvaluation(
        request: Melix_Worker_V1_RunEvaluationRequest
    ) async throws -> Melix_Worker_V1_RunEvaluationResponse

    func exportResults(
        request: Melix_Worker_V1_ExportResultsRequest
    ) async throws -> Melix_Worker_V1_ExportResultsResponse

    func submitResults(
        request: Melix_Worker_V1_SubmitResultsRequest
    ) async throws -> Melix_Worker_V1_SubmitResultsResponse
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

    public func unloadModel(
        request: Melix_Worker_V1_UnloadModelRequest
    ) async throws -> Melix_Worker_V1_UnloadModelResponse {
        throw WorkerClientError.unavailable
    }
}
