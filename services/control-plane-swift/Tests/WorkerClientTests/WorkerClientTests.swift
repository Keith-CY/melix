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
    }
}
