import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixWorkerProtocol

@Suite("Worker Registry")
struct WorkerRegistryTests {
    @Test("default text models resolve to the swift text route")
    func defaultTextModelsResolveToTheSwiftTextRoute() async throws {
        let registry = WorkerRegistry(
            defaultTextClient: RouteTestingWorkerClient(),
            pythonCompatibilityClient: RouteTestingWorkerClient()
        )

        #expect(await registry.route(forModelID: "melix-dev-text") == .swiftText)
    }

    @Test("typed model metadata resolves phase five worker routes")
    func typedModelMetadataResolvesPhaseFiveRoutes() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let registry = WorkerRegistry(
            defaultTextClient: RouteTestingWorkerClient(),
            pythonCompatibilityClient: RouteTestingWorkerClient(),
            modelCatalog: catalog
        )

        #expect(await registry.route(forModelID: "melix-dev-text") == .swiftText)
        #expect(await registry.route(forModelID: "melix-dev-embed") == .pythonEmbedding)
        #expect(await registry.route(forModelID: "melix-dev-rerank") == .pythonRerank)
        #expect(await registry.route(forModelID: "melix-dev-model-ops") == .pythonModelOperations)
    }

    @Test("python fallback client backs non-text routes when dedicated clients are absent")
    func pythonFallbackClientBacksNonTextRoutes() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let defaultTextClient = RouteTestingWorkerClient()
        let pythonClient = RouteTestingWorkerClient()
        let registry = WorkerRegistry(
            defaultTextClient: defaultTextClient,
            pythonCompatibilityClient: pythonClient,
            modelCatalog: catalog
        )

        let embeddingClient = try #require(await registry.client(forModelID: "melix-dev-embed") as? RouteTestingWorkerClient)
        let rerankClient = try #require(await registry.client(forModelID: "melix-dev-rerank") as? RouteTestingWorkerClient)
        let modelOpsClient = try #require(await registry.client(forModelID: "melix-dev-model-ops") as? RouteTestingWorkerClient)

        #expect(embeddingClient === pythonClient)
        #expect(rerankClient === pythonClient)
        #expect(modelOpsClient === pythonClient)
        #expect((await registry.client(forModelID: "melix-dev-text") as? RouteTestingWorkerClient) === defaultTextClient)
    }

    @Test("bootstrap preload accepts the shared routing client abstraction")
    func bootstrapPreloadAcceptsTheSharedRoutingClientAbstraction() async throws {
        let catalog = ModelCatalog()
        let client = RouteTestingWorkerClient()

        let preloaded = try await BootstrapWorkerPreparation.preloadDevTextModel(
            workerClient: client,
            modelCatalog: catalog
        )

        #expect(preloaded)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::swift")
    }
}

private actor RouteTestingWorkerClient: WorkerRoutingClient {
    func canDispatchRequests() async -> Bool {
        true
    }

    func generate(
        request: Melix_Worker_V1_GenerateRequest
    ) async throws -> AsyncThrowingStream<Melix_Worker_V1_ExecuteEvent, Error> {
        AsyncThrowingStream { continuation in
            continuation.finish()
        }
    }

    func abort(requestID: String) async throws -> Bool {
        true
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
