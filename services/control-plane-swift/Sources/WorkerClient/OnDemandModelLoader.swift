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
        try await ensureModelReady(
            modelID: modelID,
            modelCatalog: modelCatalog,
            workerRegistry: workerRegistry,
            metricsStore: metricsStore,
            memoryBudgetBytes: memoryBudgetBytes,
            loadReason: "lazy_text_load",
            metricsPrefix: "text",
            requiresTextCapability: true
        )
    }

    static func ensureModelReady(
        modelID: String,
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry?,
        metricsStore: MetricsStore,
        memoryBudgetBytes: UInt64 = 0,
        loadReason: String = "lazy_model_load",
        metricsPrefix: String = "model",
        requiresTextCapability: Bool = false
    ) async throws -> String {
        _ = await evictModelsIfNeededForLoad(
            targetModelID: modelID,
            modelCatalog: modelCatalog,
            workerRegistry: workerRegistry,
            metricsStore: metricsStore
        )
        if let handle = await modelCatalog.dispatchHandle(for: modelID) {
            _ = await modelCatalog.markModelUsed(id: modelID)
            return handle
        }

        guard let model = await modelCatalog.model(id: modelID) else {
            throw OnDemandModelLoadError.modelNotReady
        }
        if requiresTextCapability,
           !(model.kind == "text" || model.capabilityClass == .modelCapabilityText) {
            throw OnDemandModelLoadError.modelNotReady
        }
        guard let modelSpec = BootstrapWorkerPreparation.modelSpec(for: model) else {
            throw OnDemandModelLoadError.modelNotReady
        }
        guard let workerRegistry,
              let route = await workerRegistry.route(for: model),
              let workerClient = await workerRegistry.client(for: route) else {
            throw OnDemandModelLoadError.workerUnavailable
        }

        _ = await modelCatalog.beginLoad(id: modelID, reason: loadReason)
        var request = Melix_Worker_V1_LoadModelRequest()
        request.model = modelSpec
        request.memoryBudgetBytes = memoryBudgetBytes
        request.pinOnLoad = false
        request.warmupAfterLoad = false
        request.diskStreamingMode = modelSpec.settings.diskStreamingMode

        let startedAt = Date()
        let response: Melix_Worker_V1_LoadModelResponse
        do {
            response = try await workerClient.loadModel(request: request)
        } catch {
            _ = await modelCatalog.recordLoadFailed(id: modelID, reason: "\(loadReason)_failed")
            throw OnDemandModelLoadError.workerUnavailable
        }
        guard response.ok, !response.modelHandle.isEmpty else {
            let failureReason = if response.error.code.isEmpty {
                "\(loadReason)_failed"
            } else {
                "\(loadReason)_\(sanitizeTransitionReasonComponent(response.error.code))"
            }
            _ = await modelCatalog.recordLoadFailed(id: modelID, reason: failureReason)
            throw OnDemandModelLoadError.workerUnavailable
        }

        _ = await modelCatalog.recordLoadSucceeded(
            id: modelID,
            dispatchHandle: response.modelHandle,
            pinRequested: request.pinOnLoad,
            workerResidency: response.hasResidency ? response.residency : nil,
            reason: loadReason
        )

        let elapsedMs = Date().timeIntervalSince(startedAt) * 1000
        await metricsStore.set(elapsedMs, forKey: "control_plane.\(metricsPrefix)_first_load_ms")
        await metricsStore.set(
            Double(response.estimatedResidentBytes),
            forKey: "control_plane.\(metricsPrefix)_first_load_estimated_resident_bytes"
        )

        let residentBytes: Double
        if let runtimeClient = workerClient as? any RuntimeIntrospectingWorkerClientProtocol,
           let runtimeStats = try? await runtimeClient.runtimeStats() {
            residentBytes = Double(runtimeStats.memoryEvidence.residentBytes)
        } else {
            residentBytes = Double(response.estimatedResidentBytes)
        }
        await metricsStore.set(
            residentBytes,
            forKey: "control_plane.\(metricsPrefix)_first_load_resident_bytes"
        )

        return response.modelHandle
    }

    @discardableResult
    private static func evictModelsIfNeededForLoad(
        targetModelID: String,
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry?,
        metricsStore: MetricsStore
    ) async -> ModelCatalog.EvictionPlan {
        let plan = await modelCatalog.evictionPlanForLoad(id: targetModelID)
        await recordEvictionPlanMetrics(plan, metricsStore: metricsStore)

        guard !plan.decisions.isEmpty else {
            return plan
        }

        for decision in plan.decisions {
            await metricsStore.increment("control_plane.model_eviction_decision_count")
            await metricsStore.increment(evictionMetricKey(for: decision.reason))
            guard let evicting = await modelCatalog.beginUnload(id: decision.modelID, reason: decision.reason) else {
                await metricsStore.increment("control_plane.model_eviction_failure_count")
                continue
            }

            let unloaded = await unloadModel(
                modelID: decision.modelID,
                fallbackSummary: evicting,
                reason: decision.reason,
                modelCatalog: modelCatalog,
                workerRegistry: workerRegistry
            )
            if unloaded.state == .modelUnloaded {
                await metricsStore.increment("control_plane.model_eviction_success_count")
            } else {
                await metricsStore.increment("control_plane.model_eviction_failure_count")
            }
        }

        return plan
    }

    private static func unloadModel(
        modelID: String,
        fallbackSummary: Melix_Controlplane_V1_ModelSummary,
        reason: String,
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry?
    ) async -> Melix_Controlplane_V1_ModelSummary {
        guard let workerRegistry,
              let handle = await modelCatalog.storedDispatchHandle(for: modelID),
              let workerClient = await workerRegistry.client(forModelID: modelID) else {
            return await modelCatalog.recordUnloadSucceeded(id: modelID, reason: reason) ?? fallbackSummary
        }

        var workerRequest = Melix_Worker_V1_UnloadModelRequest()
        workerRequest.modelHandle = handle

        do {
            let response = try await workerClient.unloadModel(request: workerRequest)
            guard response.ok else {
                return await modelCatalog.recordUnloadFailed(id: modelID, reason: reason) ?? fallbackSummary
            }
            return await modelCatalog.recordUnloadSucceeded(id: modelID, reason: reason) ?? fallbackSummary
        } catch {
            return await modelCatalog.recordUnloadFailed(id: modelID, reason: reason) ?? fallbackSummary
        }
    }

    private static func recordEvictionPlanMetrics(
        _ plan: ModelCatalog.EvictionPlan,
        metricsStore: MetricsStore
    ) async {
        await metricsStore.set(
            Double(plan.decisions.count),
            forKey: "control_plane.model_eviction_last_plan_size"
        )
        await metricsStore.set(
            Double(plan.pinnedProtectedModelIDs.count),
            forKey: "control_plane.model_eviction_last_pinned_protected_count"
        )
        if !plan.decisions.isEmpty || !plan.pinnedProtectedModelIDs.isEmpty {
            await metricsStore.increment("control_plane.model_eviction_plan_count")
        }
        if !plan.pinnedProtectedModelIDs.isEmpty {
            await metricsStore.increment(
                "control_plane.model_eviction_pinned_protected_count",
                by: Double(plan.pinnedProtectedModelIDs.count)
            )
        }
    }

    static func evictionMetricKey(for reason: String) -> String {
        switch reason {
        case "ttl_expired":
            return "control_plane.model_eviction_ttl_count"
        case "lru_same_capability":
            return "control_plane.model_eviction_lru_same_capability_count"
        default:
            return "control_plane.model_eviction_other_count"
        }
    }

    private static func sanitizeTransitionReasonComponent(_ rawCode: String) -> String {
        let lowered = rawCode.lowercased()
        return String(lowered.map { character in
            switch character {
            case "a"..."z", "0"..."9", "_":
                return character
            default:
                return "_"
            }
        })
    }
}
