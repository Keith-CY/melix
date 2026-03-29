import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Model Catalog")
struct ModelCatalogTests {
    @Test("phase five development seed models expose typed capabilities and routes")
    func phaseFiveSeedModelsExposeTypedCapabilitiesAndRoutes() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let models = await catalog.listModels()

        #expect(models.map(\.modelID) == [
            "melix-dev-embed",
            "melix-dev-model-ops",
            "melix-dev-rerank",
            "melix-dev-text",
        ])
        #expect(models.first(where: { $0.modelID == "melix-dev-text" })?.capabilityClass == .modelCapabilityText)
        #expect(models.first(where: { $0.modelID == "melix-dev-embed" })?.routeClass == .workerRoutePythonEmbedding)
        #expect(models.first(where: { $0.modelID == "melix-dev-rerank" })?.routeClass == .workerRoutePythonRerank)
        #expect(models.first(where: { $0.modelID == "melix-dev-model-ops" })?.routeClass == .workerRoutePythonModelOperations)
    }

    @Test("model settings updates persist alias residency and pin semantics")
    func modelSettingsUpdatesPersistAliasResidencyAndPinSemantics() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        var settings = Melix_Controlplane_V1_ModelSettings()
        settings.alias = "Operations Embed"
        settings.pinOnLoad = true
        settings.ttlSeconds = 900
        settings.memoryPolicy = .memoryResidencyTtl
        settings.defaultAccelerationMode = .activeKvQuantized
        settings.accelerationProfileID = "embed-q8"

        let updated = try #require(await catalog.updateSettings(id: "melix-dev-embed", settings: settings))
        let reloaded = try #require(await catalog.model(id: "melix-dev-embed"))

        #expect(updated.settings.alias == "Operations Embed")
        #expect(updated.settings.pinOnLoad)
        #expect(updated.settings.ttlSeconds == 900)
        #expect(updated.settings.memoryPolicy == .memoryResidencyTtl)
        #expect(updated.settings.defaultAccelerationMode == .activeKvQuantized)
        #expect(updated.settings.accelerationProfileID == "embed-q8")
        #expect(updated.pinned)
        #expect(reloaded == updated)
    }

    @Test("phase six contract seed models expose multimodal routes and task visibility")
    func phaseSixContractSeedModelsExposeMultimodalRoutesAndTasks() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSixContractSeedModels())
        let models = await catalog.listModels()

        #expect(models.first(where: { $0.modelID == "melix-dev-ocr" })?.routeClass == .workerRoutePythonOcr)
        #expect(models.first(where: { $0.modelID == "melix-dev-vlm" })?.capabilityClass == .modelCapabilityVlm)
        #expect(models.first(where: { $0.modelID == "melix-dev-transcribe" })?.supportedTasks == ["transcribe"])
        #expect(models.first(where: { $0.modelID == "melix-dev-speech" })?.supportedModalities == ["text", "audio"])
    }

    @Test("phase seven contract seed models expose image routes and tasks")
    func phaseSevenContractSeedModelsExposeImageRoutesAndTasks() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let models = await catalog.listModels()

        let imageModel = try #require(models.first(where: { $0.modelID == "melix-dev-image" }))
        #expect(imageModel.capabilityClass == .modelCapabilityImageGeneration)
        #expect(imageModel.routeClass == .workerRoutePythonImage)
        #expect(imageModel.supportedTasks == ["image_generate", "image_edit"])
        #expect(imageModel.supportedModalities == ["text", "image"])
    }
}
