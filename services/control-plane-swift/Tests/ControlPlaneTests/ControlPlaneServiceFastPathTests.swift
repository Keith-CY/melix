import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Control Plane Service Fast Paths")
struct ControlPlaneServiceFastPathTests {
    @Test("local model load succeeds without worker routing")
    func localModelLoadSucceedsWithoutWorkerRouting() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let service = ControlPlaneService(modelCatalog: catalog)

        let response = try await service.execute(makeLocalLoadRequest(modelID: "melix-dev-text"))
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(response.ok)
        #expect(response.model.model.state == Melix_Controlplane_V1_ModelState.modelWarm)
        #expect(model.state == Melix_Controlplane_V1_ModelState.modelWarm)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::local")
        #expect(model.residency.transitionReason == "operator_load")
    }

    @Test("local model unload succeeds without worker routing")
    func localModelUnloadSucceedsWithoutWorkerRouting() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let service = ControlPlaneService(modelCatalog: catalog)
        _ = try await service.execute(makeLocalLoadRequest(modelID: "melix-dev-text"))

        let response = try await service.execute(makeLocalUnloadRequest(modelID: "melix-dev-text"))
        let model = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(response.ok)
        #expect(response.model.model.state == Melix_Controlplane_V1_ModelState.modelUnloaded)
        #expect(model.state == Melix_Controlplane_V1_ModelState.modelUnloaded)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
        #expect(model.residency.transitionReason == "operator_unload")
    }
}

private func makeLocalLoadRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
    var request = Melix_Controlplane_V1_ControlPlaneRequest()
    request.requestID = "fast-load-\(modelID)"
    request.commandType = "model.load"
    request.model = Melix_Controlplane_V1_ModelCommand()
    request.model.load = Melix_Controlplane_V1_LoadModel()
    request.model.load.modelID = modelID
    return request
}

private func makeLocalUnloadRequest(modelID: String) -> Melix_Controlplane_V1_ControlPlaneRequest {
    var request = Melix_Controlplane_V1_ControlPlaneRequest()
    request.requestID = "fast-unload-\(modelID)"
    request.commandType = "model.unload"
    request.model = Melix_Controlplane_V1_ModelCommand()
    request.model.unload = Melix_Controlplane_V1_UnloadModel()
    request.model.unload.modelID = modelID
    return request
}
