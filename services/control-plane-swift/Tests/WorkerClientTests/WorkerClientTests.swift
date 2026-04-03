import Testing

@testable import MelixControlPlaneCore
import MelixWorkerProtocol

@Suite("Worker Client")
struct WorkerClientTests {
    @Test("null worker client reports unavailability across lifecycle calls")
    func nullWorkerClientReportsUnavailabilityAcrossLifecycleCalls() async throws {
        let client = NullWorkerClient()

        #expect(!(await client.canDispatchRequests()))
        #expect(!(try await client.abort(requestID: "missing-request")))

        var generateRequest = Melix_Worker_V1_GenerateRequest()
        generateRequest.execution.id.requestID = "req-null"
        generateRequest.execution.modelHandle = "missing::handle"

        do {
            _ = try await client.generate(request: generateRequest)
            Issue.record("Expected null worker generate to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }

        var loadRequest = Melix_Worker_V1_LoadModelRequest()
        loadRequest.model.modelID = "melix-dev-text"

        do {
            _ = try await client.loadModel(request: loadRequest)
            Issue.record("Expected null worker load to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }

        var unloadRequest = Melix_Worker_V1_UnloadModelRequest()
        unloadRequest.modelHandle = "missing::handle"

        do {
            _ = try await client.unloadModel(request: unloadRequest)
            Issue.record("Expected null worker unload to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("worker-routing default unload model throws unavailable")
    func workerRoutingDefaultUnloadModelThrowsUnavailable() async throws {
        let client = DefaultUnloadWorkerClient()
        var unloadRequest = Melix_Worker_V1_UnloadModelRequest()
        unloadRequest.modelHandle = "missing::handle"

        do {
            _ = try await client.unloadModel(request: unloadRequest)
            Issue.record("Expected default unload implementation to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("model-operations default bench matrix helper throws unavailable")
    func modelOperationsDefaultBenchMatrixHelperThrowsUnavailable() async throws {
        let client = DefaultModelOperationsWorkerClient()

        do {
            _ = try await client.runBenchMatrix(request: Melix_Worker_V1_RunBenchMatrixRequest())
            Issue.record("Expected default bench matrix implementation to fail.")
        } catch let error as WorkerClientError {
            #expect(error == .unavailable)
        }
    }

    @Test("worker memory evidence normalizes shared runtime stats fields")
    func workerMemoryEvidenceNormalizesSharedRuntimeStatsFields() {
        var stats = Melix_Worker_V1_RuntimeStats()
        stats.residentBytes = 6_144
        stats.l1CacheBytes = 2_048
        stats.kvCacheBytes = 512
        stats.peakAllocationBytes = 10_240
        stats.memoryHeadroomBytes = 4_096

        let evidence = WorkerMemoryEvidence(stats: stats)

        #expect(evidence.modelResidentBytes == 6_144)
        #expect(evidence.cacheResidentBytes == 2_048)
        #expect(evidence.kvCacheBytes == 512)
        #expect(evidence.residentBytes == 8_704)
        #expect(evidence.peakAllocationBytes == 10_240)
        #expect(evidence.memoryHeadroomBytes == 4_096)
    }

    @Test("worker memory evidence prefers explicit accounting fields when available")
    func workerMemoryEvidencePrefersExplicitAccountingFieldsWhenAvailable() {
        var stats = Melix_Worker_V1_RuntimeStats()
        stats.residentBytes = 4_096
        stats.modelResidentBytes = 5_120
        stats.cacheResidentBytes = 1_024
        stats.kvCacheBytes = 256

        let evidence = WorkerMemoryEvidence(stats: stats)

        #expect(evidence.modelResidentBytes == 5_120)
        #expect(evidence.cacheResidentBytes == 1_024)
        #expect(evidence.kvCacheBytes == 256)
        #expect(evidence.residentBytes == 6_400)
    }
}

private struct DefaultUnloadWorkerClient: WorkerRoutingClient {
    func canDispatchRequests() async -> Bool { true }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool { false }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        return response
    }
}

private struct DefaultModelOperationsWorkerClient: ModelOperationsWorkerClientProtocol {
    func canDispatchRequests() async -> Bool { true }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool { false }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        return response
    }

    func getModelInfo(
        request: Melix_Worker_V1_GetModelInfoRequest
    ) async throws -> Melix_Worker_V1_GetModelInfoResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func convertModel(
        request: Melix_Worker_V1_ConvertModelRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ConvertModelEvent, Error> {
        _ = request
        throw WorkerClientError.unavailable
    }

    func runDoctor(
        request: Melix_Worker_V1_RunDoctorRequest
    ) async throws -> Melix_Worker_V1_RunDoctorResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func searchHubModels(
        request: Melix_Worker_V1_SearchHubModelsRequest
    ) async throws -> Melix_Worker_V1_SearchHubModelsResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func getHubModelCard(
        request: Melix_Worker_V1_GetHubModelCardRequest
    ) async throws -> Melix_Worker_V1_GetHubModelCardResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func runBench(
        request: Melix_Worker_V1_RunBenchRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_RunBenchEvent, Error> {
        _ = request
        throw WorkerClientError.unavailable
    }

    func runEvaluation(
        request: Melix_Worker_V1_RunEvaluationRequest
    ) async throws -> Melix_Worker_V1_RunEvaluationResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func exportResults(
        request: Melix_Worker_V1_ExportResultsRequest
    ) async throws -> Melix_Worker_V1_ExportResultsResponse {
        _ = request
        throw WorkerClientError.unavailable
    }

    func submitResults(
        request: Melix_Worker_V1_SubmitResultsRequest
    ) async throws -> Melix_Worker_V1_SubmitResultsResponse {
        _ = request
        throw WorkerClientError.unavailable
    }
}
