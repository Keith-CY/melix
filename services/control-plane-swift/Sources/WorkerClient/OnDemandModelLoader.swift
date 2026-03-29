import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

enum OnDemandModelLoadError: Error {
    case modelNotReady
    case workerUnavailable
}

enum OnDemandModelLoader {
    static func ensureTextModelReady(
        modelID: String,
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry?,
        metricsStore: MetricsStore,
        memoryBudgetBytes: UInt64 = 0
    ) async throws -> String {
        if let handle = await modelCatalog.dispatchHandle(for: modelID) {
            return handle
        }

        guard let model = await modelCatalog.model(id: modelID) else {
            throw OnDemandModelLoadError.modelNotReady
        }
        guard model.kind == "text" || model.capabilityClass == .modelCapabilityText else {
            throw OnDemandModelLoadError.modelNotReady
        }
        guard let modelSpec = BootstrapWorkerPreparation.modelSpec(for: modelID) else {
            throw OnDemandModelLoadError.modelNotReady
        }
        guard let workerRegistry,
              let workerClient = await workerRegistry.client(forModelID: modelID) else {
            throw OnDemandModelLoadError.workerUnavailable
        }

        var request = Melix_Worker_V1_LoadModelRequest()
        request.model = modelSpec
        request.memoryBudgetBytes = memoryBudgetBytes
        request.pinOnLoad = false
        request.warmupAfterLoad = false

        let startedAt = Date()
        let response: Melix_Worker_V1_LoadModelResponse
        do {
            response = try await workerClient.loadModel(request: request)
        } catch {
            throw OnDemandModelLoadError.workerUnavailable
        }
        guard response.ok, !response.modelHandle.isEmpty else {
            throw OnDemandModelLoadError.workerUnavailable
        }

        _ = await modelCatalog.loadModel(id: modelID, dispatchHandle: response.modelHandle)

        let elapsedMs = Date().timeIntervalSince(startedAt) * 1000
        await metricsStore.set(elapsedMs, forKey: "control_plane.text_first_load_ms")
        await metricsStore.set(
            Double(response.estimatedResidentBytes),
            forKey: "control_plane.text_first_load_estimated_resident_bytes"
        )

        let residentBytes: Double
        if let runtimeClient = workerClient as? any RuntimeIntrospectingWorkerClientProtocol,
           let runtimeStats = try? await runtimeClient.runtimeStats() {
            residentBytes = Double(runtimeStats.stats.residentBytes)
        } else {
            residentBytes = Double(response.estimatedResidentBytes)
        }
        await metricsStore.set(
            residentBytes,
            forKey: "control_plane.text_first_load_resident_bytes"
        )

        return response.modelHandle
    }
}
