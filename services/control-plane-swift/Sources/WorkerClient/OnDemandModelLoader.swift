import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

enum OnDemandModelLoadError: Error, Equatable {
    case modelNotReady
    case runtimeCacheMissing
    case workerRejected(Melix_Worker_V1_ErrorStatus)
    case workerUnavailable

    static func == (lhs: OnDemandModelLoadError, rhs: OnDemandModelLoadError) -> Bool {
        switch (lhs, rhs) {
        case (.modelNotReady, .modelNotReady),
             (.runtimeCacheMissing, .runtimeCacheMissing),
             (.workerUnavailable, .workerUnavailable):
            return true
        case (.workerRejected(let lhsError), .workerRejected(let rhsError)):
            return lhsError.code == rhsError.code
                && lhsError.message == rhsError.message
                && lhsError.details == rhsError.details
        default:
            return false
        }
    }
}

enum OnDemandModelLoader {
    static func sweepIdleModels(
        servedModelIDs: [String],
        idleTimeoutSeconds: UInt32,
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry?,
        metricsStore: MetricsStore
    ) async -> ModelCatalog.IdleSweepPlan {
        let startedAt = Date()
        let plan = await modelCatalog.idleSweepPlan(
            servedModelIDs: servedModelIDs,
            idleTimeoutSeconds: idleTimeoutSeconds
        )
        await metricsStore.set(
            Date().timeIntervalSince(startedAt) * 1000,
            forKey: "control_plane.model_idle_sweep_ms"
        )
        if !plan.activeProtectedModelIDs.isEmpty {
            await metricsStore.increment(
                "control_plane.model_idle_skip_active_count",
                by: Double(plan.activeProtectedModelIDs.count)
            )
        }
        if !plan.pinnedProtectedModelIDs.isEmpty {
            await metricsStore.increment(
                "control_plane.model_idle_skip_pinned_count",
                by: Double(plan.pinnedProtectedModelIDs.count)
            )
        }
        for decision in plan.decisions {
            guard let evicting = await modelCatalog.beginUnload(id: decision.modelID, reason: decision.reason) else {
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
                await metricsStore.increment("control_plane.model_idle_unload_count")
            }
        }
        return plan
    }

    static func ensureTextModelReady(
        modelID: String,
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry?,
        metricsStore: MetricsStore,
        memoryBudgetBytes: UInt64 = 0,
        evictBeforeReadyHandle: Bool = false,
        routeKindOverride: WorkerRouteKind? = nil
    ) async throws -> String {
        try await ensureModelReady(
            modelID: modelID,
            modelCatalog: modelCatalog,
            workerRegistry: workerRegistry,
            metricsStore: metricsStore,
            memoryBudgetBytes: memoryBudgetBytes,
            evictBeforeReadyHandle: evictBeforeReadyHandle,
            loadReason: "lazy_text_load",
            metricsPrefix: "text",
            requiresTextCapability: true,
            routeKindOverride: routeKindOverride
        )
    }

    static func ensureModelReady(
        modelID: String,
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry?,
        metricsStore: MetricsStore,
        memoryBudgetBytes: UInt64 = 0,
        evictBeforeReadyHandle: Bool = false,
        loadReason: String = "lazy_model_load",
        metricsPrefix: String = "model",
        requiresTextCapability: Bool = false,
        summaryOverride: Melix_Controlplane_V1_ModelSummary? = nil,
        routeKindOverride: WorkerRouteKind? = nil
    ) async throws -> String {
        let resolvedModel = if let summaryOverride {
            summaryOverride
        } else {
            await modelCatalog.model(id: modelID)
        }
        guard let model = resolvedModel else {
            throw OnDemandModelLoadError.modelNotReady
        }
        if ModelRuntimeAvailability.isRuntimeCacheMissing(model) {
            throw OnDemandModelLoadError.runtimeCacheMissing
        }
        if evictBeforeReadyHandle {
            _ = await evictModelsIfNeededForLoad(
                targetModelID: modelID,
                modelCatalog: modelCatalog,
                workerRegistry: workerRegistry,
                metricsStore: metricsStore
            )
        }
        if let routeKindOverride {
            if let handle = await modelCatalog.dispatchHandle(for: modelID, routeKind: routeKindOverride) {
                _ = await modelCatalog.markModelUsed(id: modelID)
                return handle
            }
        } else if let handle = await modelCatalog.dispatchHandle(for: modelID) {
            _ = await modelCatalog.markModelUsed(id: modelID)
            return handle
        }
        if !evictBeforeReadyHandle {
            _ = await evictModelsIfNeededForLoad(
                targetModelID: modelID,
                modelCatalog: modelCatalog,
                workerRegistry: workerRegistry,
                metricsStore: metricsStore
            )
        }
        if requiresTextCapability,
           !supportsTextServing(model) {
            throw OnDemandModelLoadError.modelNotReady
        }
        let effectiveMemoryBudgetBytes = requestedMemoryBudgetBytes(
            override: memoryBudgetBytes,
            model: model
        )
        guard var modelSpec = BootstrapWorkerPreparation.modelSpec(for: model) else {
            throw OnDemandModelLoadError.modelNotReady
        }
        guard let workerRegistry else {
            throw OnDemandModelLoadError.workerUnavailable
        }
        let route: WorkerRouteKind
        if let routeKindOverride {
            route = routeKindOverride
        } else if let inferredRoute = await workerRegistry.route(for: model) {
            route = inferredRoute
        } else {
            throw OnDemandModelLoadError.workerUnavailable
        }
        applyRouteOverrideMetadata(route, model: model, to: &modelSpec)
        if let handle = await modelCatalog.dispatchHandle(for: modelID, routeKind: route) {
            _ = await modelCatalog.markModelUsed(id: modelID)
            return handle
        }
        guard let workerClient = await workerRegistry.client(for: route) else {
            throw OnDemandModelLoadError.workerUnavailable
        }
        let trustStartedAt = Date()
        let loadTrustPolicy = ModelLoadTrustPolicyResolver.resolvePolicy(for: model, route: route)
        await metricsStore.set(
            Date().timeIntervalSince(trustStartedAt) * 1000,
            forKey: "control_plane.model_load_trust_resolution_ms"
        )

        _ = await modelCatalog.beginLoad(id: modelID, reason: loadReason)
        var request = Melix_Worker_V1_LoadModelRequest()
        request.model = modelSpec
        request.memoryBudgetBytes = effectiveMemoryBudgetBytes
        request.pinOnLoad = false
        request.warmupAfterLoad = false
        request.diskStreamingMode = modelSpec.settings.diskStreamingMode
        request.loadTrust = ModelLoadTrustPolicyResolver.workerPolicy(from: loadTrustPolicy)

        let startedAt = Date()
        let response: Melix_Worker_V1_LoadModelResponse
        do {
            response = try await workerClient.loadModel(request: request)
        } catch let workerError as WorkerClientError {
            switch workerError {
            case .requestFailed(let code, let message):
                let errorStatus = workerErrorStatus(code: code, message: message)
                let failureReason = if errorStatus.code.isEmpty {
                    "\(loadReason)_failed"
                } else {
                    "\(loadReason)_\(sanitizeTransitionReasonComponent(errorStatus.code))"
                }
                let memoryBudgetEvidence = memoryBudgetEvidence(from: errorStatus)
                if let memoryBudgetEvidence {
                    await recordMemoryBudgetMetrics(
                        memoryBudgetEvidence,
                        metricsStore: metricsStore,
                        metricsPrefix: metricsPrefix
                    )
                }
                _ = await modelCatalog.recordLoadFailed(
                    id: modelID,
                    reason: failureReason,
                    memoryBudgetEvidence: memoryBudgetEvidence
                )
                throw OnDemandModelLoadError.workerRejected(errorStatus)
            case .unavailable:
                _ = await modelCatalog.recordLoadFailed(id: modelID, reason: "\(loadReason)_failed")
                throw OnDemandModelLoadError.workerUnavailable
            }
        } catch {
            _ = await modelCatalog.recordLoadFailed(
                id: modelID,
                reason: "\(loadReason)_failed",
                loadTrust: loadTrustPolicy
            )
            throw OnDemandModelLoadError.workerUnavailable
        }
        guard response.ok, !response.modelHandle.isEmpty else {
            let failureReason = if response.error.code.isEmpty {
                "\(loadReason)_failed"
            } else {
                "\(loadReason)_\(sanitizeTransitionReasonComponent(response.error.code))"
            }
            let memoryBudgetEvidence = memoryBudgetEvidence(from: response.error)
            if let memoryBudgetEvidence {
                await recordMemoryBudgetMetrics(
                    memoryBudgetEvidence,
                    metricsStore: metricsStore,
                    metricsPrefix: metricsPrefix
                )
            }
            _ = await modelCatalog.recordLoadFailed(
                id: modelID,
                reason: failureReason,
                memoryBudgetEvidence: memoryBudgetEvidence,
                loadTrust: ModelLoadTrustPolicyResolver.receiptForLoadFailure(
                    response: response,
                    fallback: loadTrustPolicy
                )
            )
            if !response.error.code.isEmpty
                || !response.error.message.isEmpty
                || !response.error.details.isEmpty {
                throw OnDemandModelLoadError.workerRejected(response.error)
            }
            throw OnDemandModelLoadError.workerUnavailable
        }

        _ = await modelCatalog.recordLoadSucceeded(
            id: modelID,
            dispatchHandle: response.modelHandle,
            pinRequested: request.pinOnLoad,
            workerResidency: response.hasResidency ? response.residency : nil,
            loadTrust: response.hasLoadTrust
                ? ModelLoadTrustPolicyResolver.controlPlanePolicy(from: response.loadTrust, fallback: loadTrustPolicy)
                : loadTrustPolicy,
            reason: loadReason,
            routeKind: route
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

    private static func applyRouteOverrideMetadata(
        _ route: WorkerRouteKind,
        model: Melix_Controlplane_V1_ModelSummary,
        to spec: inout Melix_Worker_V1_ModelSpec
    ) {
        spec.ext["melix.capability.route_kind"] = route.metadataIdentifier
        guard let declaration = routeDeclaration(for: route, model: model) else {
            return
        }
        spec.ext["melix.capability.supported_modalities"] = declaration.supportedModalities
            .filter { $0 != .unspecified }
            .map(routeModalityIdentifier)
            .joined(separator: ",")
        spec.ext["melix.capability.supported_tasks"] = routeTaskIdentifier(declaration.task)
        spec.ext["melix.route.model_family_target"] = declaration.modelFamilyTarget
        spec.ext["melix.route.is_text_companion"] = declaration.isTextCompanion ? "true" : "false"
    }

    private static func routeDeclaration(
        for route: WorkerRouteKind,
        model: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_RequestRouteDeclaration? {
        guard let workerFamily = Melix_Controlplane_V1_WorkerFamily(workerRouteKind: route) else {
            return nil
        }
        let candidates = model.requestRoutes.filter { $0.workerFamily == workerFamily }
        if route == .swiftText {
            return candidates.first(where: { $0.task == .generateText })
        }
        if route == .swiftVision {
            return candidates.first(where: { $0.task == .generateMultimodal })
        }
        return candidates.first
    }

    private static func routeTaskIdentifier(
        _ task: Melix_Controlplane_V1_InferenceTask
    ) -> String {
        switch task {
        case .generateText:
            return "generate"
        case .generateMultimodal:
            return "generate_multimodal"
        case .embedText:
            return "embed"
        case .rerankText:
            return "rerank"
        case .transcribeAudio:
            return "transcribe"
        case .speakText:
            return "speak"
        case .imageGenerate:
            return "image_generate"
        case .imageEdit:
            return "image_edit"
        case .UNRECOGNIZED, .unspecified:
            return ""
        }
    }

    private static func routeModalityIdentifier(
        _ modality: Melix_Controlplane_V1_RouteModality
    ) -> String {
        switch modality {
        case .text:
            return "text"
        case .image:
            return "image"
        case .audio:
            return "audio"
        case .video:
            return "video"
        case .UNRECOGNIZED, .unspecified:
            return ""
        }
    }

    private static func supportsTextServing(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        let modelKind = normalizedIdentifier(model.kind)
        if modelKind == "text" || model.capabilityClass == .modelCapabilityText {
            return true
        }

        let capabilityClass = normalizedIdentifier(model.settings.ext["melix.capability.class"])
        let modalities = normalizedIdentifierSet(
            model.supportedModalities,
            fallback: model.settings.ext["melix.capability.supported_modalities"]
        )
        let tasks = normalizedIdentifierSet(
            model.supportedTasks,
            fallback: model.settings.ext["melix.capability.supported_tasks"]
        )
        let isOCR = modelKind == "ocr"
            || capabilityClass == "ocr"
            || model.capabilityClass == .modelCapabilityOcr
        if isOCR {
            return (modalities.isEmpty || modalities.contains("image"))
                && (tasks.isEmpty || tasks.contains("ocr") || tasks.contains("generate"))
        }

        // Model summaries can come from built-ins, registry scans, or workers; each path
        // may populate a different VLM identity field.
        let isVLM = modelKind == "vlm"
            || capabilityClass == "vlm"
            || model.capabilityClass == .modelCapabilityVlm
        guard isVLM else {
            return false
        }

        return modalities.contains("text") && tasks.contains("generate")
    }

    private static func normalizedIdentifierSet(
        _ values: [String],
        fallback: String?
    ) -> Set<String> {
        let identifiers = Set(values.map(normalizedIdentifier).filter { !$0.isEmpty })
        guard identifiers.isEmpty, let fallback else {
            return identifiers
        }
        // Capability ext values use unquoted comma-separated identifier tokens.
        return Set(
            fallback
                .split(separator: ",")
                .map { normalizedIdentifier(String($0)) }
                .filter { !$0.isEmpty }
        )
    }

    private static func normalizedIdentifier(_ value: String?) -> String {
        (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }

    private static func requestedMemoryBudgetBytes(
        override: UInt64,
        model: Melix_Controlplane_V1_ModelSummary
    ) -> UInt64 {
        override > 0 ? override : model.settings.memoryBudgetBytes
    }

    private static func memoryBudgetEvidence(
        from workerError: Melix_Worker_V1_ErrorStatus
    ) -> ModelCatalog.MemoryBudgetEvidence? {
        guard workerError.code == "memory_budget_exceeded" || workerError.code == "unsafe_load_rejected" else {
            return nil
        }
        let evidence = ModelCatalog.MemoryBudgetEvidence(
            memoryBudgetBytes: UInt64(workerError.details["budget_bytes"] ?? "") ?? 0,
            memoryHeadroomBytes: UInt64(workerError.details["headroom_bytes"] ?? "") ?? 0,
            requiredBytes: UInt64(workerError.details["required_bytes"] ?? "") ?? 0
        )
        return evidence.isEmpty ? nil : evidence
    }

    private static func workerErrorStatus(code: String, message: String) -> Melix_Worker_V1_ErrorStatus {
        var errorStatus = Melix_Worker_V1_ErrorStatus()
        errorStatus.code = code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "worker_unavailable" : code
        errorStatus.message = message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? "Worker bridge request failed."
            : message
        return errorStatus
    }

    private static func recordMemoryBudgetMetrics(
        _ evidence: ModelCatalog.MemoryBudgetEvidence,
        metricsStore: MetricsStore,
        metricsPrefix: String
    ) async {
        await metricsStore.increment("control_plane.\(metricsPrefix)_load_memory_budget_rejection_count")
        await metricsStore.set(
            Double(evidence.memoryBudgetBytes),
            forKey: "control_plane.\(metricsPrefix)_load_last_budget_bytes"
        )
        await metricsStore.set(
            Double(evidence.memoryHeadroomBytes),
            forKey: "control_plane.\(metricsPrefix)_load_last_headroom_bytes"
        )
        await metricsStore.set(
            Double(evidence.requiredBytes),
            forKey: "control_plane.\(metricsPrefix)_load_last_required_bytes"
        )
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
              let route = await workerRegistry.route(for: fallbackSummary) else {
            return await modelCatalog.recordUnloadSucceeded(id: modelID, reason: reason) ?? fallbackSummary
        }
        let routeHandle = await modelCatalog.storedDispatchHandle(for: modelID, routeKind: route)
        let legacyHandle = routeHandle == nil
            ? await modelCatalog.storedDispatchHandle(for: modelID)
            : nil
        guard let handle = routeHandle ?? legacyHandle,
              let workerClient = await workerRegistry.client(for: route) else {
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

private extension Melix_Controlplane_V1_WorkerFamily {
    init?(workerRouteKind route: WorkerRouteKind) {
        switch route {
        case .swiftText:
            self = .text
        case .swiftVision:
            self = .vision
        default:
            return nil
        }
    }
}
