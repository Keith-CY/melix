import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
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

    @Test("route selection honors explicit route classes before capability inference")
    func routeSelectionHonorsExplicitRouteClassesBeforeCapabilityInference() async {
        let registry = WorkerRegistry(defaultTextClient: RouteTestingWorkerClient())
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-embed"
        model.kind = "embedding"
        model.capabilityClass = .modelCapabilityText
        model.routeClass = .workerRoutePythonEmbedding

        #expect(await registry.route(for: model) == .pythonEmbedding)
    }

    @Test("route inference falls back to model kind when capability metadata is unspecified")
    func routeInferenceFallsBackToModelKindWhenCapabilityMetadataIsUnspecified() async {
        let registry = WorkerRegistry(defaultTextClient: RouteTestingWorkerClient())
        var textModel = Melix_Controlplane_V1_ModelSummary()
        textModel.modelID = "melix-dev-text"
        textModel.kind = "text"

        var compatibilityModel = Melix_Controlplane_V1_ModelSummary()
        compatibilityModel.modelID = "melix-dev-audio"
        compatibilityModel.kind = "audio"

        #expect(await registry.route(for: textModel) == .swiftText)
        #expect(await registry.route(for: compatibilityModel) == .pythonCompatibility)
    }

    @Test("empty model identifiers and missing compatibility clients return nil")
    func emptyModelIdentifiersAndMissingCompatibilityClientsReturnNil() async {
        let registry = WorkerRegistry(defaultTextClient: RouteTestingWorkerClient())

        #expect(await registry.route(forModelID: "") == nil)
        #expect(await registry.client(for: .pythonCompatibility) == nil)
        #expect(await registry.client(for: .pythonEmbedding) == nil)
        #expect(await registry.client(for: .pythonRerank) == nil)
        #expect(await registry.client(for: .pythonModelOperations) == nil)
    }

    @Test("dedicated phase-five clients win over the shared python compatibility client")
    func dedicatedPhaseFiveClientsWinOverTheSharedPythonCompatibilityClient() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let defaultTextClient = RouteTestingWorkerClient()
        let sharedPythonClient = RouteTestingWorkerClient()
        let embeddingClient = RouteTestingWorkerClient()
        let rerankClient = RouteTestingWorkerClient()
        let modelOpsClient = RouteTestingWorkerClient()
        let registry = WorkerRegistry(
            defaultTextClient: defaultTextClient,
            pythonCompatibilityClient: sharedPythonClient,
            embeddingClient: embeddingClient,
            rerankClient: rerankClient,
            modelOperationsClient: modelOpsClient,
            modelCatalog: catalog
        )

        #expect((await registry.client(forModelID: "melix-dev-text") as? RouteTestingWorkerClient) === defaultTextClient)
        #expect((await registry.client(forModelID: "melix-dev-embed") as? RouteTestingWorkerClient) === embeddingClient)
        #expect((await registry.client(forModelID: "melix-dev-rerank") as? RouteTestingWorkerClient) === rerankClient)
        #expect((await registry.client(forModelID: "melix-dev-model-ops") as? RouteTestingWorkerClient) === modelOpsClient)
    }

    @Test("phase seven multimodal routes resolve to typed python worker families")
    func phaseSevenMultimodalRoutesResolveToTypedPythonWorkerFamilies() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let registry = WorkerRegistry(
            defaultTextClient: RouteTestingWorkerClient(),
            pythonCompatibilityClient: RouteTestingWorkerClient(),
            modelCatalog: catalog
        )

        #expect(await registry.route(forModelID: "melix-dev-ocr") == .pythonOCR)
        #expect(await registry.route(forModelID: "melix-dev-vlm") == .pythonVLM)
        #expect(await registry.route(forModelID: "melix-dev-transcribe") == .pythonTranscription)
        #expect(await registry.route(forModelID: "melix-dev-speech") == .pythonSpeech)
        #expect(await registry.route(forModelID: "melix-dev-image") == .pythonImage)
    }

    @Test("explicit multimodal route classes override capability inference")
    func explicitMultimodalRouteClassesOverrideCapabilityInference() async throws {
        let registry = WorkerRegistry(
            defaultTextClient: RouteTestingWorkerClient(),
            pythonCompatibilityClient: RouteTestingWorkerClient()
        )

        var ocrModel = Melix_Controlplane_V1_ModelSummary()
        ocrModel.modelID = "melix-dev-ocr"
        ocrModel.kind = "text"
        ocrModel.capabilityClass = .modelCapabilityText
        ocrModel.routeClass = .workerRoutePythonOcr

        var vlmModel = Melix_Controlplane_V1_ModelSummary()
        vlmModel.modelID = "melix-dev-vlm"
        vlmModel.kind = "text"
        vlmModel.capabilityClass = .modelCapabilityText
        vlmModel.routeClass = .workerRoutePythonVlm

        var transcriptionModel = Melix_Controlplane_V1_ModelSummary()
        transcriptionModel.modelID = "melix-dev-transcribe"
        transcriptionModel.kind = "text"
        transcriptionModel.capabilityClass = .modelCapabilityText
        transcriptionModel.routeClass = .workerRoutePythonTranscription

        var speechModel = Melix_Controlplane_V1_ModelSummary()
        speechModel.modelID = "melix-dev-speech"
        speechModel.kind = "text"
        speechModel.capabilityClass = .modelCapabilityText
        speechModel.routeClass = .workerRoutePythonSpeech

        var imageModel = Melix_Controlplane_V1_ModelSummary()
        imageModel.modelID = "melix-dev-image"
        imageModel.kind = "text"
        imageModel.capabilityClass = .modelCapabilityText
        imageModel.routeClass = .workerRoutePythonImage

        #expect(await registry.route(for: ocrModel) == .pythonOCR)
        #expect(await registry.route(for: vlmModel) == .pythonVLM)
        #expect(await registry.route(for: transcriptionModel) == .pythonTranscription)
        #expect(await registry.route(for: speechModel) == .pythonSpeech)
        #expect(await registry.route(for: imageModel) == .pythonImage)
    }

    @Test("multimodal worker families use the shared compatibility client when present")
    func multimodalWorkerFamiliesUseTheSharedCompatibilityClientWhenPresent() async throws {
        let defaultTextClient = RouteTestingWorkerClient()
        let sharedPythonClient = RouteTestingWorkerClient()
        let registry = WorkerRegistry(
            defaultTextClient: defaultTextClient,
            pythonCompatibilityClient: sharedPythonClient
        )

        #expect((await registry.client(for: .pythonOCR) as? RouteTestingWorkerClient) === sharedPythonClient)
        #expect((await registry.client(for: .pythonVLM) as? RouteTestingWorkerClient) === sharedPythonClient)
        #expect((await registry.client(for: .pythonTranscription) as? RouteTestingWorkerClient) === sharedPythonClient)
        #expect((await registry.client(for: .pythonSpeech) as? RouteTestingWorkerClient) === sharedPythonClient)
        #expect((await registry.client(for: .pythonImage) as? RouteTestingWorkerClient) === sharedPythonClient)
        #expect((await registry.client(for: .swiftText) as? RouteTestingWorkerClient) === defaultTextClient)
    }

    @Test("missing compatibility clients return nil for multimodal worker families")
    func missingCompatibilityClientsReturnNilForMultimodalWorkerFamilies() async {
        let registry = WorkerRegistry(defaultTextClient: RouteTestingWorkerClient())

        #expect(await registry.client(for: .pythonOCR) == nil)
        #expect(await registry.client(for: .pythonVLM) == nil)
        #expect(await registry.client(for: .pythonTranscription) == nil)
        #expect(await registry.client(for: .pythonSpeech) == nil)
        #expect(await registry.client(for: .pythonImage) == nil)
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
