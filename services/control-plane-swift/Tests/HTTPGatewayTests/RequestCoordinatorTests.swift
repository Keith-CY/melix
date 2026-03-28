import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Request Coordinator")
struct RequestCoordinatorTests {
    @Test("empty model identifiers are rejected before dispatch")
    func emptyModelIdentifiersAreRejectedBeforeDispatch() async throws {
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: BlockingWorkerClient()),
            abortRegistry: AbortRegistry()
        )

        do {
            _ = try await coordinator.startChatCompletion(
                makeTranslatedChatRequest(requestID: "req-empty-model", modelID: "")
            )
            Issue.record("Expected worker unavailable to be thrown.")
        } catch let error as RequestCoordinatorError {
            #expect(error == .workerUnavailable)
        }
    }

    @Test("request cancellation triggers worker abort")
    func cancellationTriggersWorkerAbort() async throws {
        let workerClient = BlockingWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )
        let translated = makeTranslatedChatRequest(requestID: "req-cancel")

        _ = try await coordinator.startChatCompletion(translated)
        let cancelled = try await coordinator.cancel(requestID: "req-cancel")

        #expect(cancelled)
        #expect(await workerClient.abortedRequestIDs == ["req-cancel"])
    }

    @Test("only one active request is admitted at a time")
    func onlyOneActiveRequestIsAdmittedAtATime() async throws {
        let workerClient = BlockingWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )

        _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-1"))

        do {
            _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-2"))
            Issue.record("Expected the second request to be rejected.")
        } catch let error as RequestCoordinatorError {
            #expect(error == .requestAlreadyActive)
        }

        _ = try await coordinator.cancel(requestID: "req-1")
        _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-3"))

        #expect(await workerClient.generatedRequestIDs == ["req-1", "req-3"])
    }

    @Test("worker unavailable requests are rejected before dispatch")
    func workerUnavailableRequestsAreRejected() async throws {
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: UnavailableCoordinatorWorkerClient()),
            abortRegistry: AbortRegistry()
        )

        do {
            _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-unavailable"))
            Issue.record("Expected worker unavailable to be thrown.")
        } catch let error as RequestCoordinatorError {
            #expect(error == .workerUnavailable)
        }
    }

    @Test("cancelling an unknown request returns false")
    func cancellingUnknownRequestReturnsFalse() async throws {
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: BlockingWorkerClient()),
            abortRegistry: AbortRegistry()
        )
        let cancelled = try await coordinator.cancel(requestID: "missing-request")
        #expect(!cancelled)
    }

    @Test("text requests route to the swift text client by default")
    func textRequestsRouteToTheSwiftTextClientByDefault() async throws {
        let swiftWorker = BlockingWorkerClient()
        let pythonWorker = BlockingWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(
                defaultTextClient: swiftWorker,
                pythonCompatibilityClient: pythonWorker
            ),
            abortRegistry: AbortRegistry()
        )

        _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-swift"))

        #expect(await swiftWorker.generatedRequestIDs == ["req-swift"])
        #expect(await pythonWorker.generatedRequestIDs.isEmpty)
    }

    @Test("swift route failure does not fall back to python text execution")
    func swiftRouteFailureDoesNotFallBackToPythonTextExecution() async throws {
        let pythonWorker = BlockingWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(
                defaultTextClient: UnavailableCoordinatorWorkerClient(),
                pythonCompatibilityClient: pythonWorker
            ),
            abortRegistry: AbortRegistry()
        )

        do {
            _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-no-fallback"))
            Issue.record("Expected worker unavailable to be thrown.")
        } catch let error as RequestCoordinatorError {
            #expect(error == .workerUnavailable)
        }

        #expect(await pythonWorker.generatedRequestIDs.isEmpty)
    }

    @Test("stream failures propagate and release request tracking")
    func streamFailuresPropagateAndReleaseRequestTracking() async throws {
        let workerClient = ThrowingStreamWorkerClient()
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: workerClient),
            abortRegistry: AbortRegistry()
        )

        let execution = try await coordinator.startChatCompletion(
            makeTranslatedChatRequest(requestID: "req-stream-error")
        )

        do {
            for try await _ in execution.stream {
            }
            Issue.record("Expected the upstream stream to fail.")
        } catch let error as TestWorkerFailure {
            #expect(error == .streamFailed)
        }

        let cancelled = try await coordinator.cancel(requestID: "req-stream-error")
        #expect(!cancelled)
    }

    @Test("generate unavailability is surfaced without fallback")
    func generateUnavailabilityIsSurfacedWithoutFallback() async throws {
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: FailingGenerateWorkerClient(error: WorkerClientError.unavailable)),
            abortRegistry: AbortRegistry()
        )

        do {
            _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-generate-unavailable"))
            Issue.record("Expected worker unavailable to be thrown.")
        } catch let error as RequestCoordinatorError {
            #expect(error == .workerUnavailable)
        }
    }

    @Test("generate failures propagate when the worker throws a generic error")
    func generateFailuresPropagateWhenTheWorkerThrowsAGenericError() async throws {
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: FailingGenerateWorkerClient(error: TestWorkerFailure.generateFailed)),
            abortRegistry: AbortRegistry()
        )

        do {
            _ = try await coordinator.startChatCompletion(makeTranslatedChatRequest(requestID: "req-generate-failure"))
            Issue.record("Expected the worker failure to be thrown.")
        } catch let error as TestWorkerFailure {
            #expect(error == .generateFailed)
        }
    }

    @Test("cancel returns false when request tracking exists without an active worker")
    func cancelReturnsFalseWhenRequestTrackingExistsWithoutAnActiveWorker() async throws {
        let abortRegistry = AbortRegistry()
        _ = await abortRegistry.begin(requestID: "req-missing-worker")
        let coordinator = RequestCoordinator(
            workerRegistry: WorkerRegistry(defaultTextClient: BlockingWorkerClient()),
            abortRegistry: abortRegistry
        )

        let cancelled = try await coordinator.cancel(requestID: "req-missing-worker")
        #expect(!cancelled)
    }
}

private actor BlockingWorkerClient: WorkerRoutingClient {
    private(set) var generatedRequestIDs: [String] = []
    private(set) var abortedRequestIDs: [String] = []
    private var continuations: [String: AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error>.Continuation] = [:]

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        generatedRequestIDs.append(request.execution.id.requestID)
        let requestID = request.execution.id.requestID
        return AsyncThrowingStream { continuation in
            continuations[requestID] = continuation
        }
    }

    func abort(requestID: String) async throws -> Bool {
        abortedRequestIDs.append(requestID)
        continuations.removeValue(forKey: requestID)?.finish()
        return true
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private actor UnavailableCoordinatorWorkerClient: WorkerRoutingClient {
    func canDispatchRequests() async -> Bool {
        false
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        throw WorkerClientError.unavailable
    }

    func abort(requestID: String) async throws -> Bool {
        false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        throw WorkerClientError.unavailable
    }
}

private actor ThrowingStreamWorkerClient: WorkerRoutingClient {
    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish(throwing: TestWorkerFailure.streamFailed)
        }
    }

    func abort(requestID: String) async throws -> Bool {
        false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private actor FailingGenerateWorkerClient: WorkerRoutingClient {
    let error: Error

    init(error: Error) {
        self.error = error
    }

    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        throw error
    }

    func abort(requestID: String) async throws -> Bool {
        false
    }

    func loadModel(
        request: Melix_Worker_V1_LoadModelRequest
    ) async throws -> Melix_Worker_V1_LoadModelResponse {
        var response = Melix_Worker_V1_LoadModelResponse()
        response.ok = true
        response.modelHandle = "melix-dev-text::swift"
        return response
    }
}

private enum TestWorkerFailure: Error, Equatable {
    case streamFailed
    case generateFailed
}

private func makeTranslatedChatRequest(requestID: String, modelID: String = "melix-dev-text") -> TranslatedChatRequest {
    var workerRequest = Melix_Worker_V1_GenerateRequest()
    workerRequest.execution = Melix_Worker_V1_ExecutionMetadata()
    workerRequest.execution.id = Melix_Worker_V1_RequestIdentity()
    workerRequest.execution.id.requestID = requestID
    workerRequest.execution.modelHandle = "melix-dev-text::local"
    workerRequest.execution.scheduling = Melix_Worker_V1_SchedulingHints()
    workerRequest.execution.scheduling.lane = "text.decode.interactive"
    workerRequest.execution.scheduling.priority = 100
    workerRequest.execution.scheduling.latencySensitive = true

    return TranslatedChatRequest(
        requestID: requestID,
        modelID: modelID,
        workerRequest: workerRequest,
        stream: true
    )
}
