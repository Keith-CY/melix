import MelixControlPlaneProtocol

public struct ServerSnapshotBuilder {
    public init() {}

    public func build(
        models: [Melix_Controlplane_V1_ModelSummary],
        metrics: Melix_Controlplane_V1_MetricsSummary,
        queues: Melix_Controlplane_V1_QueueSummary? = nil,
        cache: Melix_Controlplane_V1_CacheSummary? = nil,
        sessions: [Melix_Controlplane_V1_SessionSummary] = [],
        runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState] = [],
        imageJobs: [Melix_Controlplane_V1_ImageJobSummary] = [],
        mcpTools: Melix_Controlplane_V1_MCPToolCatalogSummary? = nil,
        gatewayAccess: Melix_Controlplane_V1_GatewayAccessSummary? = nil,
        gatewayConfig: Melix_Controlplane_V1_GatewayConfigSummary? = nil,
        servingDefaults: Melix_Controlplane_V1_ServingDefaultsSummary? = nil,
        toolingSettings: Melix_Controlplane_V1_ToolingSettingsSummary? = nil,
        apiOnboarding: Melix_Controlplane_V1_APIOnboardingSummary? = nil
    ) -> Melix_Controlplane_V1_ServerSnapshot {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        let cacheSummary = cache ?? CacheMetadataStore.emptySummary()
        snapshot.serverState = serverState(for: runtimeSessions)
        snapshot.models = models.map { resolvedCachePolicyModel($0, cache: cacheSummary) }
        snapshot.queues = queues ?? emptyQueueSummary()
        snapshot.cache = cacheSummary
        snapshot.resources = Melix_Controlplane_V1_ResourceSnapshot()
        snapshot.metrics = metrics
        snapshot.sessions = sessions
        snapshot.runtimeSessions = runtimeSessions
        snapshot.imageJobs = imageJobs
        if let mcpTools {
            snapshot.mcpTools = mcpTools
        }
        if let gatewayAccess {
            // Gateway access is projected from the runtime store, never from raw secret material.
            snapshot.gatewayAccess = gatewayAccess
        }
        if let gatewayConfig {
            snapshot.gatewayConfig = gatewayConfig
        }
        if let servingDefaults {
            snapshot.servingDefaults = servingDefaults
        }
        if let toolingSettings {
            snapshot.toolingSettings = toolingSettings
        }
        if let apiOnboarding {
            snapshot.apiOnboarding = apiOnboarding
        }
        return snapshot
    }

    private func resolvedCachePolicyModel(
        _ source: Melix_Controlplane_V1_ModelSummary,
        cache: Melix_Controlplane_V1_CacheSummary
    ) -> Melix_Controlplane_V1_ModelSummary {
        var model = source
        model.cachePolicy = resolvedCachePolicy(for: model, cache: cache)
        return model
    }

    private func resolvedCachePolicy(
        for model: Melix_Controlplane_V1_ModelSummary,
        cache: Melix_Controlplane_V1_CacheSummary
    ) -> Melix_Controlplane_V1_CachePolicySummary {
        var summary = Melix_Controlplane_V1_CachePolicySummary()
        let requestedMode = model.settings.cacheMode == .unspecified ? cache.activeMode : model.settings.cacheMode
        let supportedModes = cache.supportedModes
        let supportedModeSet = Set(supportedModes)
        let diskStreamingActive = model.residency.effectiveDiskStreamingMode == .diskStreamingPreferDisk
            || model.residency.effectiveDiskStreamingMode == .diskStreamingRequireDisk
            || model.settings.diskStreamingMode == .diskStreamingPreferDisk
            || model.settings.diskStreamingMode == .diskStreamingRequireDisk
        let supportsMultimodalBudget = model.supportedModalities.contains("image")
            || model.kind == "vlm"
            || model.kind == "ocr"

        summary.requestedMode = requestedMode
        summary.supportedModes = supportedModes
        summary.supportsPrefixCache = cache.supportsPrefixCache
        summary.supportsPagedCache = cache.supportsPagedCache
        summary.supportsDiskCache = cache.supportsDiskCache
        summary.supportsBoundarySnapshots = cache.supportsBoundarySnapshots
        summary.requestedDirectory = model.settings.cacheDirectory
        summary.initialCacheBlocks = cache.initialCacheBlocks
        summary.requestedBlockSizeTokens = model.settings.cacheBlockSizeTokens
        summary.requestedCacheMemoryBudgetBytes = model.settings.cacheMemoryBudgetBytes
        summary.requestedCacheMemoryBudgetPct = model.settings.cacheMemoryBudgetPct
        summary.requestedMultimodalCacheBudgetBytes = model.settings.multimodalCacheBudgetBytes

        var compatibility = supportedModes.isEmpty
            ? Melix_Controlplane_V1_CacheCompatibilityState.cacheCompatibilityUnknown
            : .cacheCompatibilityCompatible
        var reasons: [String] = []

        if requestedMode == .unspecified {
            summary.effectiveMode = cache.activeMode == .unspecified ? .tiered : cache.activeMode
        } else if supportedModeSet.contains(requestedMode) {
            summary.effectiveMode = requestedMode
        } else {
            compatibility = degradeCacheCompatibility(compatibility, to: .cacheCompatibilityLimited)
            summary.effectiveMode = supportedModeSet.contains(.tiered) ? .tiered : cache.activeMode
            reasons.append("requested cache mode is not advertised by the worker")
        }

        if summary.effectiveMode == .unspecified {
            summary.effectiveMode = .tiered
        }

        if model.settings.cacheDirectory.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            summary.effectiveDirectory = cache.cacheRoot
        } else if cache.supportsDiskCache {
            summary.effectiveDirectory = model.settings.cacheDirectory
        } else {
            compatibility = degradeCacheCompatibility(compatibility, to: .cacheCompatibilityLimited)
            summary.effectiveDirectory = cache.cacheRoot
            reasons.append("per-model cache directory overrides are not supported by the current worker")
        }

        summary.effectiveBlockSizeTokens = model.settings.cacheBlockSizeTokens
        summary.effectiveCacheMemoryBudgetBytes = model.settings.cacheMemoryBudgetBytes
        summary.effectiveCacheMemoryBudgetPct = model.settings.cacheMemoryBudgetPct
        summary.effectiveMultimodalCacheBudgetBytes = supportsMultimodalBudget
            ? model.settings.multimodalCacheBudgetBytes
            : 0

        if diskStreamingActive && cache.supportsDiskCache == false {
            compatibility = degradeCacheCompatibility(compatibility, to: .cacheCompatibilityLimited)
            reasons.append("disk streaming is requested but the worker does not advertise a persistent disk cache tier")
        }

        if model.settings.multimodalCacheBudgetBytes > 0 && supportsMultimodalBudget == false {
            compatibility = degradeCacheCompatibility(compatibility, to: .cacheCompatibilityLimited)
            reasons.append("multimodal cache budget is ignored for non-image models")
        }

        if model.settings.cacheMemoryBudgetBytes > 0 && model.settings.cacheMemoryBudgetPct > 0 {
            compatibility = degradeCacheCompatibility(compatibility, to: .cacheCompatibilityLimited)
            summary.effectiveCacheMemoryBudgetPct = 0
            reasons.append("fixed cache budget bytes take precedence over percentage budgets")
        }

        if cache.cacheRoot.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            compatibility = degradeCacheCompatibility(compatibility, to: .cacheCompatibilityUnknown)
            reasons.append("worker cache root is unavailable")
        }

        summary.compatibility = compatibility
        if reasons.isEmpty {
            switch compatibility {
            case .cacheCompatibilityCompatible:
                summary.compatibilityReason = "requested policy is compatible with the current worker cache capabilities"
            case .cacheCompatibilityLimited:
                summary.compatibilityReason = "requested policy requires one or more compatibility downgrades"
            case .cacheCompatibilityDisabled:
                summary.compatibilityReason = "requested cache policy is disabled by the current worker safety profile"
            default:
                summary.compatibilityReason = "worker cache compatibility evidence is unavailable"
            }
        } else {
            summary.compatibilityReason = reasons.joined(separator: " • ")
        }
        return summary
    }

    private func degradeCacheCompatibility(
        _ current: Melix_Controlplane_V1_CacheCompatibilityState,
        to next: Melix_Controlplane_V1_CacheCompatibilityState
    ) -> Melix_Controlplane_V1_CacheCompatibilityState {
        let ranking: [Melix_Controlplane_V1_CacheCompatibilityState: Int] = [
            .cacheCompatibilityCompatible: 0,
            .cacheCompatibilityLimited: 1,
            .cacheCompatibilityDisabled: 2,
            .cacheCompatibilityUnknown: 3,
            .unspecified: -1,
        ]
        return (ranking[next] ?? 0) > (ranking[current] ?? 0) ? next : current
    }

    private func emptyQueueSummary() -> Melix_Controlplane_V1_QueueSummary {
        var queue = Melix_Controlplane_V1_QueueSummary()
        queue.lanes = [
            lane(id: "text.decode.interactive", laneClass: "interactive-decode"),
            lane(id: "text.prefill.hot", laneClass: "hot-prefill"),
            lane(id: "text.prefill.background", laneClass: "background-prefill"),
            lane(id: "multimodal.vision.background", laneClass: "background-vision"),
            lane(id: "multimodal.audio.transcription.background", laneClass: "background-audio-transcription"),
            lane(id: "multimodal.audio.speech.background", laneClass: "background-audio-speech"),
            lane(id: "image.generate.background", laneClass: "background-image-generate"),
            lane(id: "image.edit.background", laneClass: "background-image-edit"),
        ]
        return queue
    }

    private func lane(id: String, laneClass: String) -> Melix_Controlplane_V1_QueueLaneSummary {
        var lane = Melix_Controlplane_V1_QueueLaneSummary()
        lane.laneID = id
        lane.laneClass = laneClass
        return lane
    }

    private func serverState(
        for runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState]
    ) -> Melix_Controlplane_V1_ServerState {
        guard !runtimeSessions.isEmpty else {
            return .serverReady
        }
        if runtimeSessions.contains(where: { $0.lifecycleState == .error }) {
            return .serverFailed
        }
        if runtimeSessions.contains(where: { $0.lifecycleState == .loading }) {
            return .serverBooting
        }
        if runtimeSessions.allSatisfy({ $0.lifecycleState == .stopped }) {
            return .serverStopped
        }
        if runtimeSessions.contains(where: { $0.lifecycleState == .paused || $0.lifecycleState == .sleeping }) {
            return .serverDegraded
        }
        return .serverReady
    }
}
