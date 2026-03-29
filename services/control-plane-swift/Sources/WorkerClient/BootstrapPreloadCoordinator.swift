import Foundation

public enum BootstrapPreloadCoordinator {
    public static func preloadTextReadyModel(
        workerClient: any WorkerRoutingClient,
        modelCatalog: ModelCatalog,
        metricsStore: MetricsStore,
        memoryBudgetBytes: UInt64 = 0
    ) async {
        let preloadStartedAt = Date()
        do {
            _ = try await BootstrapWorkerPreparation.preloadDevTextModel(
                workerClient: workerClient,
                modelCatalog: modelCatalog,
                memoryBudgetBytes: memoryBudgetBytes
            )
        } catch {
            print("Melix worker preload skipped: \(error)")
        }

        let elapsedMs = Date().timeIntervalSince(preloadStartedAt) * 1000
        await metricsStore.set(elapsedMs, forKey: "control_plane.worker_preload_ms")
        await metricsStore.set(elapsedMs, forKey: "control_plane.text_ready_preload_ms")
    }

    @discardableResult
    public static func startBackgroundPhaseSevenPythonPreload(
        workerClient: any WorkerRoutingClient,
        modelCatalog: ModelCatalog,
        metricsStore: MetricsStore,
        memoryBudgetBytes: UInt64 = 0
    ) -> Task<Void, Never> {
        Task.detached(priority: .background) {
            let preloadStartedAt = Date()
            var success = 0.0

            do {
                try await BootstrapWorkerPreparation.preloadPhaseSevenPythonModels(
                    workerClient: workerClient,
                    modelCatalog: modelCatalog,
                    memoryBudgetBytes: memoryBudgetBytes
                )
                success = 1.0
            } catch {
                print("Melix phase-7 python model preload skipped: \(error)")
            }

            let elapsedMs = Date().timeIntervalSince(preloadStartedAt) * 1000
            await metricsStore.set(elapsedMs, forKey: "control_plane.background_preload_ms")
            await metricsStore.set(success, forKey: "control_plane.background_preload_success")
        }
    }
}
