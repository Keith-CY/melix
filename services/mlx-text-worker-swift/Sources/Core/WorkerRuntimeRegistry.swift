import Foundation
import MelixWorkerProtocol

struct LoadedModelRecord: @unchecked Sendable {
    let handle: String
    let spec: Melix_Worker_V1_ModelSpec
    let runtimeModel: LoadedTextModel
    let estimatedResidentBytes: UInt64
    let residency: Melix_Worker_V1_ResidencyInfo
}

struct StoredPrefillContext: @unchecked Sendable {
    let decodeHandle: String
    let modelHandle: String
    let requestID: String
    let promptTokens: Int
    let messages: [Melix_Worker_V1_ChatMessage]
    let resumeHint: String
    let acceleration: Melix_Worker_V1_AccelerationPolicy
    let activeKVQuantizationRatio: Int
    let blockTableID: String
    let blockTable: Melix_Worker_V1_BlockTable
    let restoredSnapshotID: String
    let prefix: Melix_Worker_V1_PrefixRef?
    let context: TextPrefillContext
}

struct WorkerPrefillResult: Sendable {
    let decodeHandle: String
    let blockTableID: String
    let blockTable: Melix_Worker_V1_BlockTable
    let promptTokens: Int
    let restoredSnapshotID: String
    let appliedAcceleration: Melix_Worker_V1_AccelerationPolicy
    let acceleratedPrefillGainPct: Int
    let requestedPrefillStepTokens: Int
    let effectivePrefillWindowTokens: Int
    let activeKVQuantizationRatio: Int
    let cacheStats: Melix_Worker_V1_CacheStats
    let hotPrefixCount: Int
    let restorePlan: Melix_Worker_V1_CacheRestorePlan?
    let cacheHitTaxonomy: HotCacheHitTaxonomy
}

struct WorkerDecodeSession: @unchecked Sendable {
    let loadedModel: LoadedModelRecord
    let prefill: StoredPrefillContext
}

struct WorkerDecodeBatchItem: @unchecked Sendable {
    let session: WorkerDecodeSession
    let sampling: Melix_Worker_V1_SamplingConfig
    let maxOutputTokens: UInt32
    let decodeStepSize: UInt32
    let prefillToken: String
    let acceleration: Melix_Worker_V1_AccelerationPolicy
    let shouldAbort: @Sendable () -> Bool
}

struct SpeculativeDraftModelReadiness: Sendable {
    let available: Bool
    let compatible: Bool
    let fallbackReason: String
    let errorMessage: String

    static func ready() -> SpeculativeDraftModelReadiness {
        SpeculativeDraftModelReadiness(
            available: true,
            compatible: true,
            fallbackReason: "",
            errorMessage: ""
        )
    }

    static func unavailable(reason: String) -> SpeculativeDraftModelReadiness {
        SpeculativeDraftModelReadiness(
            available: false,
            compatible: false,
            fallbackReason: reason,
            errorMessage: "Speculative decode requires a loaded draft model for the active Swift text backend."
        )
    }

    static func incompatible(reason: String, message: String) -> SpeculativeDraftModelReadiness {
        SpeculativeDraftModelReadiness(
            available: true,
            compatible: false,
            fallbackReason: reason,
            errorMessage: message
        )
    }
}

actor WorkerRuntimeRegistry {
    private static let estimatedPrefillResidentBytesPerToken: UInt64 = 2_048
    private static let estimatedMediaPartTokens = 256

    /// Tuple returned by `restoreBoundarySnapshotRecord`. Extracted so the shape
    /// stays in sync across the declaration and the `do/catch` capture site.
    private typealias BoundarySnapshotRecord = (
        snapshot: Melix_Worker_V1_SnapshotRef,
        model: Melix_Worker_V1_ModelSpec,
        messages: [Melix_Worker_V1_ChatMessage],
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        promptTokens: Int,
        blockTableID: String,
        blockTable: Melix_Worker_V1_BlockTable,
        decodeHandle: String
    )

    private let configuration: WorkerConfiguration
    private let modelCatalog: WorkerModelCatalog
    private let runtime: TextRuntime
    private let cacheStore: HotCacheStore

    private var loadedModels: [String: LoadedModelRecord]
    private var activeRequests: UInt64
    private var activePrefills: UInt64
    private var activeDecodes: UInt64
    private var draining: Bool
    private var nextModelHandle: UInt64
    private var nextDecodeHandle: UInt64
    private var prefillContexts: [String: StoredPrefillContext]

    init(
        configuration: WorkerConfiguration,
        modelCatalog: WorkerModelCatalog = WorkerModelCatalog(),
        runtime: TextRuntime = TextRuntime(),
        cacheStore: HotCacheStore? = nil
    ) {
        self.configuration = configuration
        self.modelCatalog = modelCatalog
        self.runtime = runtime
        self.cacheStore = cacheStore ?? HotCacheStore(
            diskStore: DiskCacheStore(
                rootPath: configuration.cacheRootPath,
                runtimeCacheFingerprint: configuration.runtimeCacheFingerprint
            ),
            cacheRootPath: configuration.cacheRootPath,
            runtimeCacheFingerprint: configuration.runtimeCacheFingerprint,
            initialCacheBlocks: configuration.initialCacheBlocks
        )
        self.loadedModels = [:]
        self.activeRequests = 0
        self.activePrefills = 0
        self.activeDecodes = 0
        self.draining = false
        self.nextModelHandle = 1
        self.nextDecodeHandle = 1
        self.prefillContexts = [:]
    }

    func capabilities() -> Melix_Worker_V1_RuntimeCapabilities {
        var capabilities = Melix_Worker_V1_RuntimeCapabilities()

        var cache = Melix_Worker_V1_CacheCapabilities()
        cache.supportsPrefixCache = true
        cache.supportsPagedCache = true
        cache.supportsDiskCache = false
        cache.kvQuantProfiles = ActiveKVQuantizationProfiles.supportedProfiles
        cache.supportsBoundarySnapshots = false
        cache.supportedModes = CacheModePolicy.supportedModes
        cache.experimentalModes = CacheModePolicy.experimentalModes
        capabilities.cache = cache

        var execution = Melix_Worker_V1_ExecutionCapabilities()
        execution.supportsContinuousBatching = true
        execution.supportsSpeculativeDecoding = supportsSpeculativeDecoding()
        execution.supportsDiskStreaming = false
        capabilities.execution = execution

        var ext = Melix_Worker_V1_Capability()
        ext.name = "engine_family"
        ext.metadata = ["value": configuration.backendMode]
        var acceleratedPrefill = Melix_Worker_V1_Capability()
        acceleratedPrefill.name = "accelerated_prefill"
        acceleratedPrefill.metadata = ["value": supportsAcceleratedPrefill() ? "yes" : "no"]

        var sparsePrefill = Melix_Worker_V1_Capability()
        sparsePrefill.name = "sparse_prefill"
        sparsePrefill.metadata = ["value": supportsSparsePrefill() ? "yes" : "no"]

        var activeKV = Melix_Worker_V1_Capability()
        activeKV.name = "active_kv_quantized"
        activeKV.metadata = [
            "value": supportsActiveKVQuantization() ? "yes" : "no",
            "profiles": ActiveKVQuantizationProfiles.supportedProfiles.joined(separator: ",")
        ]

        capabilities.ext = [ext, acceleratedPrefill, sparsePrefill, activeKV]

        return capabilities
    }

    func loadModel(
        _ requested: Melix_Worker_V1_ModelSpec,
        memoryBudgetBytes: UInt64 = 0,
        pinOnLoad: Bool = false,
        diskStreamingMode: Melix_Worker_V1_DiskStreamingMode = .unspecified
    ) async throws -> LoadedModelRecord {
        let resolved = modelCatalog.get(requested.modelID).map { catalogModel in
            mergeModelSpec(requested, fallback: catalogModel)
        } ?? requested
        try validateRequestRoutes(for: resolved, workerFamily: configuration.workerFamily)
        let requestedDiskStreamingMode = effectiveDiskStreamingMode(
            for: resolved,
            requestMode: diskStreamingMode
        )
        if requestedDiskStreamingMode == .diskStreamingPreferDisk
            || requestedDiskStreamingMode == .diskStreamingRequireDisk {
            throw WorkerRuntimeRegistryError.diskStreamingUnsupported(
                requestedMode: requestedDiskStreamingMode,
                modelID: resolved.modelID
            )
        }

        let loaded = try await runtime.loadModel(spec: resolved)
        let existingResidentBytes = loadedModels.values.reduce(0) { $0 + $1.estimatedResidentBytes }
        let projectedResidentBytes = existingResidentBytes &+ loaded.estimatedResidentBytes
        let requiredProcessBytes = projectedResidentBytes &+ configuration.modelLoadHeadroomBytes
        if configuration.memoryEnforcementEnabled,
           configuration.processMemoryBudgetBytes > 0,
           requiredProcessBytes > configuration.processMemoryBudgetBytes {
            await runtime.unloadModel(loaded.model)
            throw WorkerRuntimeRegistryError.memoryBudgetExceeded(
                budgetBytes: configuration.processMemoryBudgetBytes,
                headroomBytes: configuration.modelLoadHeadroomBytes,
                projectedResidentBytes: projectedResidentBytes,
                requiredBytes: requiredProcessBytes
            )
        }

        let requiredRequestBytes = loaded.estimatedResidentBytes &+ configuration.modelLoadHeadroomBytes
        if configuration.memoryEnforcementEnabled,
           memoryBudgetBytes > 0,
           requiredRequestBytes > memoryBudgetBytes {
            await runtime.unloadModel(loaded.model)
            throw WorkerRuntimeRegistryError.memoryBudgetExceeded(
                budgetBytes: memoryBudgetBytes,
                headroomBytes: configuration.modelLoadHeadroomBytes,
                projectedResidentBytes: loaded.estimatedResidentBytes,
                requiredBytes: requiredRequestBytes
            )
        }
        let handle = makeModelHandle(for: resolved, ordinal: nextModelHandle)
        nextModelHandle += 1

        let record = LoadedModelRecord(
            handle: handle,
            spec: resolved,
            runtimeModel: loaded.model,
            estimatedResidentBytes: loaded.estimatedResidentBytes,
            residency: loadedResidency(
                for: resolved,
                pinOnLoad: pinOnLoad,
                effectiveDiskStreamingMode: requestedDiskStreamingMode
            )
        )
        loadedModels[handle] = record
        return record
    }

    func unloadModel(_ handle: String) async -> Bool {
        guard let removed = loadedModels.removeValue(forKey: handle) else {
            return false
        }
        prefillContexts = prefillContexts.filter { $0.value.modelHandle != handle }
        await cacheStore.purgeScope(resolveCacheScope(Melix_Worker_V1_CacheScope(), fallback: removed.spec))
        await runtime.unloadModel(removed.runtimeModel)
        return true
    }

    func getLoadedModel(_ handle: String) -> LoadedModelRecord? {
        loadedModels[handle]
    }

    func startRequest() {
        activeRequests += 1
    }

    func finishRequest() {
        if activeRequests > 0 {
            activeRequests -= 1
        }
    }

    func listLoadedModels() -> [String] {
        loadedModels.keys.sorted()
    }

    private func loadedResidency(
        for model: Melix_Worker_V1_ModelSpec,
        pinOnLoad: Bool,
        effectiveDiskStreamingMode: Melix_Worker_V1_DiskStreamingMode
    ) -> Melix_Worker_V1_ResidencyInfo {
        var residency = Melix_Worker_V1_ResidencyInfo()
        let effectivePinned = pinOnLoad || model.settings.pinOnLoad
        residency.state = effectivePinned ? .pinned : .warm
        residency.policy = effectiveResidencyPolicy(for: model, pinOnLoad: pinOnLoad)
        residency.pinRequested = effectivePinned
        residency.pinned = effectivePinned
        residency.ttlSeconds = model.settings.ttlSeconds
        residency.transitionReason = "load_model"
        residency.effectiveDiskStreamingMode = effectiveDiskStreamingMode
        return residency
    }

    private func effectiveResidencyPolicy(
        for model: Melix_Worker_V1_ModelSpec,
        pinOnLoad: Bool
    ) -> Melix_Worker_V1_MemoryResidencyPolicy {
        if pinOnLoad || model.settings.pinOnLoad {
            return .memoryResidencyPinned
        }
        if model.settings.memoryPolicy != .unspecified {
            return model.settings.memoryPolicy
        }
        if model.settings.ttlSeconds > 0 {
            return .memoryResidencyTtl
        }
        return .memoryResidencyEvictable
    }

    private func effectiveDiskStreamingMode(
        for model: Melix_Worker_V1_ModelSpec,
        requestMode: Melix_Worker_V1_DiskStreamingMode
    ) -> Melix_Worker_V1_DiskStreamingMode {
        if requestMode != .unspecified {
            return requestMode
        }
        if model.settings.diskStreamingMode != .unspecified {
            return model.settings.diskStreamingMode
        }
        return .diskStreamingDisabled
    }

    func loadedModelCount() -> Int {
        loadedModels.count
    }

    func generateEvents(
        modelHandle: String,
        messages: [Melix_Worker_V1_ChatMessage],
        sampling: Melix_Worker_V1_SamplingConfig,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        guard let loaded = loadedModels[modelHandle] else {
            throw WorkerRuntimeRegistryError.unknownModelHandle
        }

        return try await runtime.generateEvents(
            model: loaded.runtimeModel,
            messages: messages,
            sampling: sampling,
            shouldAbort: shouldAbort
        )
    }

    func prefill(
        execution: Melix_Worker_V1_ExecutionMetadata,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        returnDecodeHandle: Bool,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> WorkerPrefillResult {
        let requestID = execution.id.requestID
        let modelHandle = execution.modelHandle
        guard let loaded = loadedModels[modelHandle] else {
            throw WorkerRuntimeRegistryError.unknownModelHandle
        }
        var effectiveExecution = execution
        if effectiveExecution.cacheHints.cacheMode == .unspecified,
           loaded.spec.settings.cacheMode != .unspecified {
            effectiveExecution.cacheHints.cacheMode = loaded.spec.settings.cacheMode
        }
        if effectiveExecution.cacheHints.preferredBlockSize == 0,
           loaded.spec.settings.cacheBlockSizeTokens > 0 {
            effectiveExecution.cacheHints.preferredBlockSize = loaded.spec.settings.cacheBlockSizeTokens
        }
        let cacheMode = CacheModePolicy.resolve(from: effectiveExecution.cacheHints)
        await cacheStore.setActiveMode(cacheMode)

        let resolvedAcceleration = normalizedAccelerationPolicy(acceleration)
        try enforcePrefillGuards(
            loaded: loaded,
            messages: messages,
            acceleration: resolvedAcceleration
        )
        try throwIfTextRuntimeCancellationRequested(shouldAbort)

        activeRequests += 1
        activePrefills += 1
        defer {
            if activeRequests > 0 {
                activeRequests -= 1
            }
            if activePrefills > 0 {
                activePrefills -= 1
            }
        }

        if !effectiveExecution.cacheHints.restoreSnapshotID.isEmpty {
            let restored: BoundarySnapshotRecord
            do {
                restored = try await restoreBoundarySnapshotRecord(
                    snapshotID: effectiveExecution.cacheHints.restoreSnapshotID,
                    shouldAbort: shouldAbort
                )
            } catch {
                // Operator asked for a restore, runtime could not reconstruct. Record
                // the observability blind spot and rethrow the original error.
                await cacheStore.recordReconstructionFailure()
                throw error
            }
            let requestMessages = messages.isEmpty ? restored.messages : messages
            let walkedBackPlan = makeWalkedBackCacheRestorePlan(
                snapshot: restored.snapshot,
                blockTableID: restored.blockTableID,
                blockTable: restored.blockTable,
                cachedMessages: restored.messages,
                requestMessages: requestMessages,
                tier: "l2",
                cacheMode: cacheMode
            )
            if let restorePlan = walkedBackPlan {
                if restorePlan.partial {
                    await cacheStore.recordPartialHit()
                } else {
                    await cacheStore.recordExactHit()
                }
                let restoreResumeHint = restoreResumeHint(
                    snapshotID: restored.snapshot.snapshotID,
                    restorePlan: restorePlan,
                    fallback: restored.resumeHint
                )
                let runtimePrefill = try await runtime.prefill(
                    model: loaded.runtimeModel,
                    messages: requestMessages,
                    prefillStepSize: prefillStepSize,
                    resumeHint: restoreResumeHint,
                    acceleration: normalizedAccelerationPolicy(restored.acceleration),
                    shouldAbort: shouldAbort
                )
                try throwIfTextRuntimeCancellationRequested(shouldAbort)

                let decodeHandle = "\(modelHandle)::decode::\(nextDecodeHandle)"
                nextDecodeHandle += 1
                let restoredPrefix = await cacheStore.lookupPrefix(for: restorePlan.blockTable.cacheKey)
                try throwIfTextRuntimeCancellationRequested(shouldAbort)
                prefillContexts[decodeHandle] = StoredPrefillContext(
                    decodeHandle: decodeHandle,
                    modelHandle: loaded.handle,
                    requestID: requestID,
                    promptTokens: runtimePrefill.promptTokens,
                    messages: requestMessages,
                    resumeHint: restoreResumeHint,
                    acceleration: runtimePrefill.appliedAcceleration,
                    activeKVQuantizationRatio: runtimePrefill.activeKVQuantizationRatio,
                    blockTableID: restorePlan.blockTableID,
                    blockTable: restorePlan.blockTable,
                    restoredSnapshotID: restored.snapshot.snapshotID,
                    prefix: restoredPrefix,
                    context: runtimePrefill.context
                )

                let cacheSnapshot = await cacheStore.snapshot()
                let cacheStats = cacheStatsWithRuntimeContext(cacheSnapshot.stats)
                let cacheHitTaxonomy = await cacheStore.hitTaxonomy()
                return WorkerPrefillResult(
                    decodeHandle: decodeHandle,
                    blockTableID: restorePlan.blockTableID,
                    blockTable: restorePlan.blockTable,
                    promptTokens: runtimePrefill.promptTokens,
                    restoredSnapshotID: restored.snapshot.snapshotID,
                    appliedAcceleration: runtimePrefill.appliedAcceleration,
                    acceleratedPrefillGainPct: runtimePrefill.acceleratedPrefillGainPct,
                    requestedPrefillStepTokens: runtimePrefill.requestedPrefillStepTokens,
                    effectivePrefillWindowTokens: runtimePrefill.effectivePrefillWindowTokens,
                    activeKVQuantizationRatio: runtimePrefill.activeKVQuantizationRatio,
                    cacheStats: cacheStats,
                    hotPrefixCount: cacheSnapshot.hotPrefixes.count,
                    restorePlan: restorePlan,
                    cacheHitTaxonomy: cacheHitTaxonomy
                )
            }
            await cacheStore.recordReconstructionFailure()
        }

        let result = try await runtime.prefill(
            model: loaded.runtimeModel,
            messages: messages,
            prefillStepSize: prefillStepSize,
            resumeHint: resumeHint,
            acceleration: resolvedAcceleration,
            shouldAbort: shouldAbort
        )
        try throwIfTextRuntimeCancellationRequested(shouldAbort)

        var decodeHandle = ""
        var blockTableID = ""
        var blockTable = Melix_Worker_V1_BlockTable()
        if returnDecodeHandle {
            decodeHandle = "\(modelHandle)::decode::\(nextDecodeHandle)"
            nextDecodeHandle += 1
            let registration = try await cacheStore.registerPrefill(
                execution: effectiveExecution,
                model: loaded.spec,
                messages: messages,
                promptTokens: result.promptTokens,
                decodeHandle: decodeHandle,
                activeKVQuantizationRatio: result.activeKVQuantizationRatio,
                shouldAbort: shouldAbort
            )
            try throwIfTextRuntimeCancellationRequested(shouldAbort)
            blockTableID = registration.blockTableID
            blockTable = registration.blockTable
            prefillContexts[decodeHandle] = StoredPrefillContext(
                decodeHandle: decodeHandle,
                modelHandle: modelHandle,
                requestID: requestID,
                promptTokens: result.promptTokens,
                messages: messages,
                resumeHint: resumeHint,
                acceleration: result.appliedAcceleration,
                activeKVQuantizationRatio: result.activeKVQuantizationRatio,
                blockTableID: blockTableID,
                blockTable: blockTable,
                restoredSnapshotID: "",
                prefix: registration.prefix,
                context: result.context
            )
        }

        let cacheSnapshot = await cacheStore.snapshot()
        let cacheStats = cacheStatsWithRuntimeContext(cacheSnapshot.stats)
        let cacheHitTaxonomy = await cacheStore.hitTaxonomy()

        return WorkerPrefillResult(
            decodeHandle: decodeHandle,
            blockTableID: blockTableID,
            blockTable: blockTable,
            promptTokens: result.promptTokens,
            restoredSnapshotID: "",
            appliedAcceleration: result.appliedAcceleration,
            acceleratedPrefillGainPct: result.acceleratedPrefillGainPct,
            requestedPrefillStepTokens: result.requestedPrefillStepTokens,
            effectivePrefillWindowTokens: result.effectivePrefillWindowTokens,
            activeKVQuantizationRatio: result.activeKVQuantizationRatio,
            cacheStats: cacheStats,
            hotPrefixCount: cacheSnapshot.hotPrefixes.count,
            restorePlan: nil,
            cacheHitTaxonomy: cacheHitTaxonomy
        )
    }

    func prefill(
        requestID: String,
        modelHandle: String,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        returnDecodeHandle: Bool,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> WorkerPrefillResult {
        var execution = Melix_Worker_V1_ExecutionMetadata()
        execution.id.requestID = requestID
        execution.modelHandle = modelHandle
        execution.acceleration = acceleration
        return try await prefill(
            execution: execution,
            messages: messages,
            prefillStepSize: prefillStepSize,
            returnDecodeHandle: returnDecodeHandle,
            resumeHint: resumeHint,
            acceleration: acceleration,
            shouldAbort: shouldAbort
        )
    }

    func cacheHitTaxonomy() async -> HotCacheHitTaxonomy {
        await cacheStore.hitTaxonomy()
    }

    func cacheOwnershipSnapshot() async -> HotCacheOwnershipSnapshot {
        await cacheStore.ownershipSnapshot()
    }

    func prefillContext(for decodeHandle: String) -> StoredPrefillContext? {
        prefillContexts[decodeHandle]
    }

    func prefillContextCount() -> Int {
        prefillContexts.count
    }

    func beginDecode(decodeHandle: String) throws -> WorkerDecodeSession {
        guard let stored = prefillContexts[decodeHandle] else {
            throw WorkerRuntimeRegistryError.unknownDecodeHandle
        }
        guard let loaded = loadedModels[stored.modelHandle] else {
            throw WorkerRuntimeRegistryError.unknownModelHandle
        }

        prefillContexts.removeValue(forKey: decodeHandle)
        activeRequests += 1
        activeDecodes += 1

        return WorkerDecodeSession(
            loadedModel: loaded,
            prefill: stored
        )
    }

    func finishDecode() {
        if activeRequests > 0 {
            activeRequests -= 1
        }
        if activeDecodes > 0 {
            activeDecodes -= 1
        }
    }

    func decodeEvents(
        session: WorkerDecodeSession,
        sampling: Melix_Worker_V1_SamplingConfig,
        maxOutputTokens: UInt32,
        decodeStepSize: UInt32,
        prefillToken: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> AsyncThrowingStream<TextGenerationEvent, Error> {
        let draftModel = loadedDraftModel(
            id: acceleration.draftModelID,
            excludingModelHandle: session.loadedModel.handle
        )?.runtimeModel
        return try await runtime.decodeEvents(
            model: session.loadedModel.runtimeModel,
            draftModel: draftModel,
            context: session.prefill.context,
            sampling: sampling,
            maxOutputTokens: maxOutputTokens,
            decodeStepSize: decodeStepSize,
            prefillToken: prefillToken,
            acceleration: acceleration,
            shouldAbort: shouldAbort
        )
    }

    func supportsHomogeneousBatchDecode() -> Bool {
        runtime.supportsHomogeneousBatchDecode
    }

    func decodeBatchEvents(
        items: [WorkerDecodeBatchItem]
    ) async throws -> AsyncThrowingStream<TextBatchGenerationEvent, Error> {
        let requests = items.map { item in
            TextRuntimeDecodeRequest(
                model: item.session.loadedModel.runtimeModel,
                draftModel: loadedDraftModel(
                    id: item.acceleration.draftModelID,
                    excludingModelHandle: item.session.loadedModel.handle
                )?.runtimeModel,
                context: item.session.prefill.context,
                sampling: item.sampling,
                maxOutputTokens: item.maxOutputTokens,
                decodeStepSize: item.decodeStepSize,
                prefillToken: item.prefillToken,
                acceleration: item.acceleration,
                shouldAbort: item.shouldAbort
            )
        }
        return try await runtime.decodeBatchEvents(requests: requests)
    }

    func supportsSpeculativeDecoding() -> Bool {
        switch configuration.backendMode.lowercased() {
        case "deterministic", "swift", "auto":
            return true
        default:
            return false
        }
    }

    func requiresLoadedDraftModelForSpeculativeDecoding() -> Bool {
        configuration.backendMode.lowercased() != "deterministic"
    }

    func hasLoadedDraftModel(id: String, excludingModelHandle: String) -> Bool {
        loadedDraftModel(id: id, excludingModelHandle: excludingModelHandle) != nil
    }

    func speculativeDraftModelReadiness(
        id: String,
        excludingModelHandle: String,
        targetSpec: Melix_Worker_V1_ModelSpec
    ) -> SpeculativeDraftModelReadiness {
        guard let draftModel = loadedDraftModel(id: id, excludingModelHandle: excludingModelHandle) else {
            return .unavailable(reason: "draft_model_unavailable")
        }

        if DFlashDraftSupport.isDFlashDraftModelSpec(draftModel.spec) {
            #if canImport(MLXLMCommon) && canImport(MLXLLM)
            if draftModel.runtimeModel.storage is SwiftDFlashDraftRuntime {
                return .ready()
            }
            #endif
            return .incompatible(
                reason: DFlashDraftSupport.unsupportedReason,
                message: DFlashDraftSupport.unsupportedMessage
            )
        }

        if let issue = speculativeDraftCompatibilityIssue(target: targetSpec, draft: draftModel.spec) {
            return .incompatible(
                reason: issue.reason,
                message: issue.message
            )
        }
        return .ready()
    }

    private func loadedDraftModel(
        id rawID: String,
        excludingModelHandle: String
    ) -> LoadedModelRecord? {
        let id = rawID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !id.isEmpty else {
            return nil
        }
        if let byHandle = loadedModels[id], byHandle.handle != excludingModelHandle {
            return byHandle
        }

        return loadedModels.values.first { candidate in
            guard candidate.handle != excludingModelHandle else {
                return false
            }
            return candidate.spec.modelID == id
                || candidate.spec.modelPath == id
                || candidate.spec.settings.alias == id
        }
    }

    func supportsAcceleratedPrefill() -> Bool {
        true
    }

    func supportsSparsePrefill() -> Bool {
        true
    }

    func supportsActiveKVQuantization() -> Bool {
        true
    }

    func runtimeStats() async -> Melix_Worker_V1_RuntimeStats {
        let modelResidentBytes = loadedModels.values.reduce(0) { $0 + $1.estimatedResidentBytes }
        let cacheStats = cacheStatsWithRuntimeContext(
            await cacheStore.stats(),
            modelResidentBytes: modelResidentBytes
        )
        let cacheResidentBytes = cacheStats.l1Bytes
        let kvCacheBytes: UInt64 = 0
        var stats = Melix_Worker_V1_RuntimeStats()
        if draining {
            stats.workerState = "draining"
        } else if activeRequests > 0 {
            stats.workerState = "busy"
        } else {
            stats.workerState = "idle"
        }
        stats.modelResidentBytes = modelResidentBytes
        stats.cacheResidentBytes = cacheResidentBytes
        stats.kvCacheBytes = kvCacheBytes
        stats.peakAllocationBytes = 0
        stats.memoryHeadroomBytes = configuration.memoryEnforcementEnabled ? configuration.modelLoadHeadroomBytes : 0
        stats.residentBytes = modelResidentBytes &+ cacheResidentBytes &+ kvCacheBytes
        stats.activeRequests = activeRequests
        stats.activePrefills = activePrefills
        stats.activeDecodes = activeDecodes
        stats.l1CacheBytes = cacheStats.l1Bytes
        stats.l2CacheBytes = cacheStats.l2Bytes
        stats.l1HitRate = cacheStats.l1HitRate
        stats.l2HitRate = cacheStats.l2HitRate
        if let overlay = await runtime.runtimeStatsOverlay() {
            applyRuntimeStatsOverlay(overlay, to: &stats)
        }
        return stats
    }

    func setDraining(_ draining: Bool) {
        self.draining = draining
    }

    func cacheStatsResponse() async -> Melix_Worker_V1_GetCacheStatsResponse {
        var response = Melix_Worker_V1_GetCacheStatsResponse()
        var snapshot = await cacheStore.snapshot()
        let stats = cacheStatsWithRuntimeContext(snapshot.stats)
        snapshot.stats = stats
        response.stats = stats
        response.snapshot = snapshot
        return response
    }

    func cacheTierMetrics() async -> HotCacheTierMetrics {
        await cacheStore.tierMetrics()
    }

    func pinPrefix(_ prefix: Melix_Worker_V1_PrefixRef) async -> Bool {
        await cacheStore.pinPrefix(prefix)
    }

    func unpinPrefix(_ prefix: Melix_Worker_V1_PrefixRef) async -> Bool {
        await cacheStore.unpinPrefix(prefix)
    }

    func purgeCache(
        scope: Melix_Worker_V1_CacheScope,
        cacheKey: Melix_Worker_V1_CacheKey,
        includePinned: Bool
    ) async -> UInt64 {
        await cacheStore.purgeCache(scope: scope, cacheKey: cacheKey, includePinned: includePinned)
    }

    func saveBoundarySnapshot(
        requestID: String,
        decodeHandle: String,
        tokenBoundary: UInt32
    ) async throws -> Melix_Worker_V1_SaveBoundarySnapshotResponse {
        guard let stored = prefillContexts[decodeHandle] else {
            throw WorkerRuntimeRegistryError.unknownDecodeHandle
        }
        guard let loaded = loadedModels[stored.modelHandle] else {
            throw WorkerRuntimeRegistryError.unknownModelHandle
        }

        let effectiveRequestID = requestID.isEmpty ? stored.requestID : requestID
        let boundary = tokenBoundary > 0 ? tokenBoundary : UInt32(max(0, stored.promptTokens))
        let savedSnapshot = await cacheStore.saveBoundarySnapshot(
            requestID: effectiveRequestID,
            tokenBoundary: boundary,
            model: loaded.spec,
            prefill: stored
        )

        var response = Melix_Worker_V1_SaveBoundarySnapshotResponse()
        response.ok = true
        response.snapshotID = savedSnapshot.snapshot.snapshotID
        response.snapshot = savedSnapshot.snapshot
        response.restoreBoundary = makeRestoreBoundaryRef(
            snapshot: savedSnapshot.snapshot,
            blockTable: savedSnapshot.blockTable
        )
        return response
    }

    func saveBoundarySnapshot(
        requestID: String,
        session: WorkerDecodeSession,
        tokenBoundary: UInt32
    ) async -> Melix_Worker_V1_SaveBoundarySnapshotResponse {
        let effectiveRequestID = requestID.isEmpty ? session.prefill.requestID : requestID
        let boundary = tokenBoundary > 0 ? tokenBoundary : UInt32(max(0, session.prefill.promptTokens))
        let savedSnapshot = await cacheStore.saveBoundarySnapshot(
            requestID: effectiveRequestID,
            tokenBoundary: boundary,
            model: session.loadedModel.spec,
            prefill: session.prefill
        )

        var response = Melix_Worker_V1_SaveBoundarySnapshotResponse()
        response.ok = true
        response.snapshotID = savedSnapshot.snapshot.snapshotID
        response.snapshot = savedSnapshot.snapshot
        response.restoreBoundary = makeRestoreBoundaryRef(
            snapshot: savedSnapshot.snapshot,
            blockTable: savedSnapshot.blockTable
        )
        return response
    }

    func restoreBoundarySnapshot(
        snapshotID: String
    ) async throws -> Melix_Worker_V1_RestoreBoundarySnapshotResponse {
        let restored = try await restoreBoundarySnapshotRecord(snapshotID: snapshotID)

        var response = Melix_Worker_V1_RestoreBoundarySnapshotResponse()
        response.ok = true
        response.decodeHandle = restored.decodeHandle
        response.blockTableID = restored.blockTableID
        response.blockTable = normalizedBlockTable(restored.blockTable)
        response.snapshot = restored.snapshot
        response.restoreBoundary = makeRestoreBoundaryRef(
            snapshot: restored.snapshot,
            blockTable: restored.blockTable
        )
        response.restorePlan = makeCacheRestorePlan(
            snapshot: restored.snapshot,
            blockTableID: restored.blockTableID,
            blockTable: restored.blockTable,
            tier: "l2",
            partial: false
        )
        return response
    }

    private func restoreBoundarySnapshotRecord(
        snapshotID: String,
        shouldAbort: @escaping @Sendable () -> Bool = { false }
    ) async throws -> BoundarySnapshotRecord {
        try throwIfTextRuntimeCancellationRequested(shouldAbort)
        guard let restored = await cacheStore.restoreBoundarySnapshot(snapshotID: snapshotID) else {
            throw WorkerRuntimeRegistryError.unknownSnapshotID
        }
        try throwIfTextRuntimeCancellationRequested(shouldAbort)

        let restoredScopeID = if !restored.blockTable.scopeID.isEmpty {
            restored.blockTable.scopeID
        } else if !restored.blockTable.cacheKey.scopeID.isEmpty {
            restored.blockTable.cacheKey.scopeID
        } else {
            resolveCacheScope(Melix_Worker_V1_CacheScope(), fallback: restored.model).scopeID
        }

        if loadedModels.values.contains(where: { $0.spec.modelID == restored.model.modelID }),
           !loadedModels.values.contains(where: {
               $0.spec.modelID == restored.model.modelID &&
                   resolveCacheScope(Melix_Worker_V1_CacheScope(), fallback: $0.spec).scopeID == restoredScopeID
           }) {
            throw WorkerRuntimeRegistryError.snapshotScopeMismatch
        }

        guard let loaded = loadedModels.values.first(where: {
            $0.spec.modelID == restored.model.modelID &&
                resolveCacheScope(Melix_Worker_V1_CacheScope(), fallback: $0.spec).scopeID == restoredScopeID
        }) else {
            throw WorkerRuntimeRegistryError.snapshotModelNotLoaded
        }

        let runtimePrefill = try await runtime.prefill(
            model: loaded.runtimeModel,
            messages: restored.messages,
            prefillStepSize: 0,
            resumeHint: restored.resumeHint,
            acceleration: restored.acceleration,
            shouldAbort: shouldAbort
        )
        try throwIfTextRuntimeCancellationRequested(shouldAbort)

        let decodeHandle = "\(loaded.handle)::decode::\(nextDecodeHandle)"
        nextDecodeHandle += 1
        let restoredPrefix = await cacheStore.lookupPrefix(for: restored.blockTable.cacheKey)
        try throwIfTextRuntimeCancellationRequested(shouldAbort)
        prefillContexts[decodeHandle] = StoredPrefillContext(
            decodeHandle: decodeHandle,
            modelHandle: loaded.handle,
            requestID: restored.snapshot.requestID,
            promptTokens: restored.promptTokens,
            messages: restored.messages,
            resumeHint: restored.resumeHint,
            acceleration: restored.acceleration,
            activeKVQuantizationRatio: activeKVQuantizationRatio(from: restored.acceleration),
            blockTableID: restored.blockTableID,
            blockTable: restored.blockTable,
            restoredSnapshotID: restored.snapshot.snapshotID,
            prefix: restoredPrefix,
            context: runtimePrefill.context
        )

        return (
            snapshot: restored.snapshot,
            model: restored.model,
            messages: restored.messages,
            resumeHint: restored.resumeHint,
            acceleration: restored.acceleration,
            promptTokens: restored.promptTokens,
            blockTableID: restored.blockTableID,
            blockTable: restored.blockTable,
            decodeHandle: decodeHandle
        )
    }

    private func enforcePrefillGuards(
        loaded: LoadedModelRecord,
        messages: [Melix_Worker_V1_ChatMessage],
        acceleration: Melix_Worker_V1_AccelerationPolicy
    ) throws {
        let promptTokens = estimatedPromptTokens(for: messages)
        if loaded.spec.maxContext > 0, promptTokens > Int(loaded.spec.maxContext) {
            throw WorkerRuntimeRegistryError.contextLimitExceeded(
                maxContext: loaded.spec.maxContext,
                promptTokens: promptTokens
            )
        }

        if configuration.prefillQuadraticGuardTokenThreshold > 0,
           promptTokens > Int(configuration.prefillQuadraticGuardTokenThreshold),
           usesQuadraticPrefillPath(acceleration) {
            throw WorkerRuntimeRegistryError.quadraticPrefillGuardExceeded(
                promptTokens: promptTokens,
                tokenLimit: configuration.prefillQuadraticGuardTokenThreshold,
                accelerationMode: accelerationModeName(acceleration.mode)
            )
        }

        let estimatedPrefillBytes = estimatedPrefillResidentBytes(forPromptTokens: promptTokens)
        let existingResidentBytes = loadedModels.values.reduce(0) { $0 + $1.estimatedResidentBytes }
        let projectedResidentBytes = existingResidentBytes &+ estimatedPrefillBytes
        let requiredBytes = projectedResidentBytes &+ configuration.prefillMemoryHeadroomBytes
        if configuration.memoryEnforcementEnabled,
           configuration.processMemoryBudgetBytes > 0,
           requiredBytes > configuration.processMemoryBudgetBytes {
            throw WorkerRuntimeRegistryError.prefillMemoryGuardExceeded(
                budgetBytes: configuration.processMemoryBudgetBytes,
                headroomBytes: configuration.prefillMemoryHeadroomBytes,
                projectedResidentBytes: projectedResidentBytes,
                promptTokens: promptTokens,
                estimatedPrefillBytes: estimatedPrefillBytes,
                requiredBytes: requiredBytes
            )
        }
    }

    private func cacheStatsWithRuntimeContext(
        _ cacheStats: Melix_Worker_V1_CacheStats,
        modelResidentBytes: UInt64? = nil
    ) -> Melix_Worker_V1_CacheStats {
        var stats = cacheStats
        let resolvedModelResidentBytes = modelResidentBytes
            ?? loadedModels.values.reduce(UInt64(0)) { $0 + $1.estimatedResidentBytes }
        let activeMemoryBytes = resolvedModelResidentBytes &+ stats.l1Bytes
        stats.runtimeCacheFingerprint = configuration.runtimeCacheFingerprint
        stats.activeMemoryBytes = activeMemoryBytes
        stats.maxWorkingSetBytes = configuration.processMemoryBudgetBytes
        stats.effectiveCacheBudgetBytes = effectiveCacheBudgetBytes(
            modelResidentBytes: resolvedModelResidentBytes
        )
        return stats
    }

    private func effectiveCacheBudgetBytes(modelResidentBytes: UInt64) -> UInt64 {
        guard configuration.memoryEnforcementEnabled,
              configuration.processMemoryBudgetBytes > 0 else {
            return 0
        }
        let protectedBytes = modelResidentBytes &+ configuration.prefillMemoryHeadroomBytes
        guard configuration.processMemoryBudgetBytes > protectedBytes else {
            return 0
        }
        return configuration.processMemoryBudgetBytes - protectedBytes
    }

    private func estimatedPrefillResidentBytes(forPromptTokens promptTokens: Int) -> UInt64 {
        UInt64(max(promptTokens, 1)) * Self.estimatedPrefillResidentBytesPerToken
    }

    private func estimatedPromptTokens(for messages: [Melix_Worker_V1_ChatMessage]) -> Int {
        let total = messages.reduce(0) { partialResult, message in
            partialResult + estimatedPromptTokens(for: message)
        }
        return max(total, 1)
    }

    private func estimatedPromptTokens(for message: Melix_Worker_V1_ChatMessage) -> Int {
        let partTokens = message.parts.reduce(0) { partialResult, part in
            partialResult + estimatedPromptTokens(for: part)
        }
        if partTokens > 0 {
            return partTokens
        }

        let nameTokens = estimatedPromptTokens(in: message.name)
        return max(nameTokens, 1)
    }

    private func estimatedPromptTokens(for part: Melix_Worker_V1_MessagePart) -> Int {
        switch part.part {
        case .text(let text):
            return estimatedPromptTokens(in: text)
        case .imageUri, .imageBytes, .audioUri, .audioBytes, .videoUri, .videoBytes:
            return Self.estimatedMediaPartTokens
        case nil:
            return 0
        }
    }

    private func estimatedPromptTokens(in text: String) -> Int {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            return 0
        }
        return max(1, trimmed.split(whereSeparator: \.isWhitespace).count)
    }

    private func usesQuadraticPrefillPath(_ acceleration: Melix_Worker_V1_AccelerationPolicy) -> Bool {
        acceleration.mode != .acceleratedPrefill && acceleration.mode != .sparsePrefill
    }
}

enum WorkerRuntimeRegistryError: Error, LocalizedError, Equatable {
    case unknownModelHandle
    case unknownDecodeHandle
    case unknownSnapshotID
    case snapshotModelNotLoaded
    case snapshotScopeMismatch
    case contextLimitExceeded(maxContext: UInt32, promptTokens: Int)
    case diskStreamingUnsupported(
        requestedMode: Melix_Worker_V1_DiskStreamingMode,
        modelID: String
    )
    case memoryBudgetExceeded(
        budgetBytes: UInt64,
        headroomBytes: UInt64,
        projectedResidentBytes: UInt64,
        requiredBytes: UInt64
    )
    case prefillMemoryGuardExceeded(
        budgetBytes: UInt64,
        headroomBytes: UInt64,
        projectedResidentBytes: UInt64,
        promptTokens: Int,
        estimatedPrefillBytes: UInt64,
        requiredBytes: UInt64
    )
    case quadraticPrefillGuardExceeded(
        promptTokens: Int,
        tokenLimit: UInt32,
        accelerationMode: String
    )
    case requestRouteUnsupported(
        modelID: String,
        workerFamily: Melix_Worker_V1_WorkerFamily,
        reason: String
    )

    var errorDescription: String? {
        switch self {
        case .unknownModelHandle:
            return "Unknown model handle."
        case .unknownDecodeHandle:
            return "Unknown decode handle."
        case .unknownSnapshotID:
            return "Unknown snapshot ID."
        case .snapshotModelNotLoaded:
            return "The model required for this snapshot is not currently loaded."
        case .snapshotScopeMismatch:
            return "The loaded model configuration is incompatible with this snapshot."
        case .diskStreamingUnsupported:
            return "The selected runtime does not support disk-streaming mode."
        case .memoryBudgetExceeded:
            return "Projected resident memory would exceed the process budget."
        case .contextLimitExceeded:
            return "Prefill prompt exceeds the model context limit."
        case .prefillMemoryGuardExceeded:
            return "Projected prefill memory would exceed the process budget."
        case .quadraticPrefillGuardExceeded:
            return "Prefill request exceeds the configured quadratic fallback threshold."
        case .requestRouteUnsupported:
            return "Worker defensive validation rejected the request route declaration."
        }
    }

    var explicitPrefillErrorCode: String? {
        switch self {
        case .contextLimitExceeded:
            return "context_limit_exceeded"
        case .prefillMemoryGuardExceeded:
            return "prefill_memory_guard_exceeded"
        case .quadraticPrefillGuardExceeded:
            return "quadratic_prefill_guard_exceeded"
        default:
            return nil
        }
    }

    var explicitPrefillErrorDetails: [String: String] {
        switch self {
        case let .diskStreamingUnsupported(requestedMode, modelID):
            return [
                "requested_mode": requestedMode.rawValue.description,
                "model_id": modelID,
            ]
        case let .contextLimitExceeded(maxContext, promptTokens):
            return [
                "max_context": String(maxContext),
                "prompt_tokens": String(promptTokens),
            ]
        case let .prefillMemoryGuardExceeded(
            budgetBytes,
            headroomBytes,
            projectedResidentBytes,
            promptTokens,
            estimatedPrefillBytes,
            requiredBytes
        ):
            return [
                "budget_bytes": String(budgetBytes),
                "headroom_bytes": String(headroomBytes),
                "projected_resident_bytes": String(projectedResidentBytes),
                "prompt_tokens": String(promptTokens),
                "estimated_prefill_bytes": String(estimatedPrefillBytes),
                "required_bytes": String(requiredBytes),
            ]
        case let .quadraticPrefillGuardExceeded(promptTokens, tokenLimit, accelerationMode):
            return [
                "prompt_tokens": String(promptTokens),
                "token_limit": String(tokenLimit),
                "acceleration_mode": accelerationMode,
            ]
        default:
            return [:]
        }
    }

    var saveRestoreErrorCode: String {
        switch self {
        case .unknownDecodeHandle, .unknownSnapshotID, .unknownModelHandle:
            return "not_found"
        case .requestRouteUnsupported:
            return "request_route_unsupported"
        case .snapshotModelNotLoaded, .snapshotScopeMismatch:
            return "failed_precondition"
        case .diskStreamingUnsupported:
            return "failed_precondition"
        case .memoryBudgetExceeded, .prefillMemoryGuardExceeded, .quadraticPrefillGuardExceeded:
            return "resource_exhausted"
        case .contextLimitExceeded:
            return "out_of_range"
        }
    }

    static func == (lhs: WorkerRuntimeRegistryError, rhs: WorkerRuntimeRegistryError) -> Bool {
        switch (lhs, rhs) {
        case (.unknownModelHandle, .unknownModelHandle),
             (.unknownDecodeHandle, .unknownDecodeHandle),
             (.unknownSnapshotID, .unknownSnapshotID),
             (.snapshotModelNotLoaded, .snapshotModelNotLoaded),
             (.snapshotScopeMismatch, .snapshotScopeMismatch):
            return true
        case let (
            .diskStreamingUnsupported(requestedMode: lhsMode, modelID: lhsModelID),
            .diskStreamingUnsupported(requestedMode: rhsMode, modelID: rhsModelID)
        ):
            return lhsMode == rhsMode && lhsModelID == rhsModelID
        case let (
            .contextLimitExceeded(maxContext: lhsMaxContext, promptTokens: lhsPromptTokens),
            .contextLimitExceeded(maxContext: rhsMaxContext, promptTokens: rhsPromptTokens)
        ):
            return lhsMaxContext == rhsMaxContext &&
                lhsPromptTokens == rhsPromptTokens
        case let (
            .memoryBudgetExceeded(
                budgetBytes: lhsBudgetBytes,
                headroomBytes: lhsHeadroomBytes,
                projectedResidentBytes: lhsProjectedResidentBytes,
                requiredBytes: lhsRequiredBytes
            ),
            .memoryBudgetExceeded(
                budgetBytes: rhsBudgetBytes,
                headroomBytes: rhsHeadroomBytes,
                projectedResidentBytes: rhsProjectedResidentBytes,
                requiredBytes: rhsRequiredBytes
            )
        ):
            return lhsBudgetBytes == rhsBudgetBytes &&
                lhsHeadroomBytes == rhsHeadroomBytes &&
                lhsProjectedResidentBytes == rhsProjectedResidentBytes &&
                lhsRequiredBytes == rhsRequiredBytes
        case let (
            .prefillMemoryGuardExceeded(
                budgetBytes: lhsBudgetBytes,
                headroomBytes: lhsHeadroomBytes,
                projectedResidentBytes: lhsProjectedResidentBytes,
                promptTokens: lhsPromptTokens,
                estimatedPrefillBytes: lhsEstimatedPrefillBytes,
                requiredBytes: lhsRequiredBytes
            ),
            .prefillMemoryGuardExceeded(
                budgetBytes: rhsBudgetBytes,
                headroomBytes: rhsHeadroomBytes,
                projectedResidentBytes: rhsProjectedResidentBytes,
                promptTokens: rhsPromptTokens,
                estimatedPrefillBytes: rhsEstimatedPrefillBytes,
                requiredBytes: rhsRequiredBytes
            )
        ):
            return lhsBudgetBytes == rhsBudgetBytes &&
                lhsHeadroomBytes == rhsHeadroomBytes &&
                lhsProjectedResidentBytes == rhsProjectedResidentBytes &&
                lhsPromptTokens == rhsPromptTokens &&
                lhsEstimatedPrefillBytes == rhsEstimatedPrefillBytes &&
                lhsRequiredBytes == rhsRequiredBytes
        case let (
            .quadraticPrefillGuardExceeded(
                promptTokens: lhsPromptTokens,
                tokenLimit: lhsTokenLimit,
                accelerationMode: lhsAccelerationMode
            ),
            .quadraticPrefillGuardExceeded(
                promptTokens: rhsPromptTokens,
                tokenLimit: rhsTokenLimit,
                accelerationMode: rhsAccelerationMode
            )
        ):
            return lhsPromptTokens == rhsPromptTokens &&
                lhsTokenLimit == rhsTokenLimit &&
                lhsAccelerationMode == rhsAccelerationMode
        case let (
            .requestRouteUnsupported(
                modelID: lhsModelID,
                workerFamily: lhsWorkerFamily,
                reason: lhsReason
            ),
            .requestRouteUnsupported(
                modelID: rhsModelID,
                workerFamily: rhsWorkerFamily,
                reason: rhsReason
            )
        ):
            return lhsModelID == rhsModelID &&
                lhsWorkerFamily == rhsWorkerFamily &&
                lhsReason == rhsReason
        default:
            return false
        }
    }
}

func restoreResumeHint(
    snapshotID: String,
    restorePlan: Melix_Worker_V1_CacheRestorePlan,
    fallback: String
) -> String {
    guard !snapshotID.isEmpty else {
        return fallback
    }
    if restorePlan.partial {
        return "snapshot-restore:\(snapshotID):partial:\(restorePlan.restoredTokenCount)"
    }
    return "snapshot-restore:\(snapshotID)"
}

func accelerationModeName(_ mode: Melix_Worker_V1_AccelerationMode) -> String {
    switch mode {
    case .baseline:
        return "baseline"
    case .acceleratedPrefill:
        return "accelerated_prefill"
    case .sparsePrefill:
        return "sparse_prefill"
    case .speculativeDecode:
        return "speculative_decode"
    case .activeKvQuantized:
        return "active_kv_quantized"
    default:
        return "unspecified"
    }
}

private func mergeModelSpec(
    _ requested: Melix_Worker_V1_ModelSpec,
    fallback: Melix_Worker_V1_ModelSpec
) -> Melix_Worker_V1_ModelSpec {
    var resolved = requested

    if resolved.modelPath.isEmpty {
        resolved.modelPath = fallback.modelPath
    }
    if resolved.modelKind.isEmpty {
        resolved.modelKind = fallback.modelKind
    }
    if resolved.revision.isEmpty {
        resolved.revision = fallback.revision
    }
    if resolved.tokenizerHash.isEmpty {
        resolved.tokenizerHash = fallback.tokenizerHash
    }
    if resolved.quantProfileID.isEmpty {
        resolved.quantProfileID = fallback.quantProfileID
    }
    if resolved.parserMode.isEmpty {
        resolved.parserMode = fallback.parserMode
    }
    if resolved.reasoningMode.isEmpty {
        resolved.reasoningMode = fallback.reasoningMode
    }
    if resolved.maxContext == 0 {
        resolved.maxContext = fallback.maxContext
    }
    if resolved.modelID.isEmpty {
        resolved.modelID = fallback.modelID
    }
    if resolved.requestRoutes.isEmpty {
        resolved.requestRoutes = fallback.requestRoutes
    }
    for (key, value) in fallback.ext where resolved.ext[key] == nil {
        resolved.ext[key] = value
    }
    return resolved
}

private func validateRequestRoutes(
    for spec: Melix_Worker_V1_ModelSpec,
    workerFamily: Melix_Worker_V1_WorkerFamily
) throws {
    let matchingRoutes = spec.requestRoutes.filter { route in
        route.workerFamily == workerFamily
    }
    guard !matchingRoutes.isEmpty else {
        throw WorkerRuntimeRegistryError.requestRouteUnsupported(
            modelID: spec.modelID,
            workerFamily: workerFamily,
            reason: "worker_family_mismatch"
        )
    }
    if workerFamily == .text {
        guard matchingRoutes.contains(where: { route in
            route.task == .generateText
                && Set(route.supportedModalities) == [.text]
                && route.requiresAnyModality.isEmpty
                && !route.supportsNativeVideo
        }) else {
            throw WorkerRuntimeRegistryError.requestRouteUnsupported(
                modelID: spec.modelID,
                workerFamily: workerFamily,
                reason: "no_route_for_modalities"
            )
        }
    }
    if workerFamily == .vision {
        guard matchingRoutes.contains(where: { route in
            route.task == .generateMultimodal
                && route.supportedModalities.contains(where: { $0 == .image || $0 == .video })
                && route.requiresAnyModality.contains(where: { $0 == .image || $0 == .video })
                && (!route.requiresAnyModality.contains(.video) || route.supportsNativeVideo)
        }) else {
            throw WorkerRuntimeRegistryError.requestRouteUnsupported(
                modelID: spec.modelID,
                workerFamily: workerFamily,
                reason: "no_route_for_modalities"
            )
        }
    }
}

private func speculativeDraftCompatibilityIssue(
    target: Melix_Worker_V1_ModelSpec,
    draft: Melix_Worker_V1_ModelSpec
) -> (reason: String, message: String)? {
    let targetTokenizer = target.tokenizerHash.trimmingCharacters(in: .whitespacesAndNewlines)
    let draftTokenizer = draft.tokenizerHash.trimmingCharacters(in: .whitespacesAndNewlines)
    if targetTokenizer.isEmpty || draftTokenizer.isEmpty {
        return (
            "draft_tokenizer_missing",
            "Speculative decode requires non-empty target and draft tokenizer hashes."
        )
    }
    if targetTokenizer != draftTokenizer {
        return (
            "draft_tokenizer_mismatch",
            "Speculative decode requires target and draft tokenizer hashes to match."
        )
    }

    let targetKind = target.modelKind.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    let draftKind = draft.modelKind.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    if !targetKind.isEmpty, !draftKind.isEmpty, targetKind != draftKind {
        return (
            "draft_model_kind_mismatch",
            "Speculative decode requires target and draft model kinds to match."
        )
    }

    let targetFamily = speculativeFamilyID(target)
    let draftFamily = speculativeFamilyID(draft)
    if !targetFamily.isEmpty, !draftFamily.isEmpty, targetFamily != draftFamily {
        return (
            "draft_family_mismatch",
            "Speculative decode requires target and draft text families to match."
        )
    }

    return nil
}

private func speculativeFamilyID(_ spec: Melix_Worker_V1_ModelSpec) -> String {
    (
        spec.ext["text_family_id"]
            ?? spec.ext["melix.text.family_id"]
            ?? spec.ext["detected_family_id"]
            ?? ""
    )
    .trimmingCharacters(in: .whitespacesAndNewlines)
    .lowercased()
}

private func makeModelHandle(
    for spec: Melix_Worker_V1_ModelSpec,
    ordinal: UInt64
) -> String {
    let adapterSetHash = cacheAdapterSetHash(from: spec)
    guard !adapterSetHash.isEmpty else {
        return "\(spec.modelID)::\(ordinal)"
    }
    return "\(spec.modelID)::adapter::\(sanitizeHandleComponent(adapterSetHash))::\(ordinal)"
}

private func resolveCacheScope(
    _ requested: Melix_Worker_V1_CacheScope,
    fallback model: Melix_Worker_V1_ModelSpec
) -> Melix_Worker_V1_CacheScope {
    var scope = requested
    if scope.modelID.isEmpty {
        scope.modelID = model.modelID
    }
    if scope.revision.isEmpty {
        scope.revision = model.revision
    }
    if scope.tokenizerHash.isEmpty {
        scope.tokenizerHash = model.tokenizerHash
    }
    if scope.quantProfileID.isEmpty {
        scope.quantProfileID = model.quantProfileID
    }
    if scope.parserMode.isEmpty {
        scope.parserMode = model.parserMode
    }
    if scope.reasoningMode.isEmpty {
        scope.reasoningMode = model.reasoningMode
    }
    if scope.multimodalAdapterHash.isEmpty {
        scope.multimodalAdapterHash = cacheAdapterSetHash(from: model)
    }
    if scope.scopeID.isEmpty {
        scope.scopeID = makeCacheScopeID(scope)
    }
    return scope
}

private func makeCacheScopeID(_ scope: Melix_Worker_V1_CacheScope) -> String {
    [
        scope.modelID,
        scope.revision,
        scope.tokenizerHash,
        scope.quantProfileID,
        scope.promptTemplateHash,
        scope.parserMode,
        scope.reasoningMode,
        scope.multimodalAdapterHash,
    ].joined(separator: "::")
}

private func cacheAdapterSetHash(from model: Melix_Worker_V1_ModelSpec) -> String {
    if let explicit = model.ext["melix.adapter_set_hash"], !explicit.isEmpty {
        return explicit
    }
    if let legacy = model.ext["adapter_set_hash"], !legacy.isEmpty {
        return legacy
    }
    return ""
}

private func sanitizeHandleComponent(_ raw: String) -> String {
    let normalized = raw.lowercased().map { character in
        switch character {
        case "a"..."z", "0"..."9":
            return character
        default:
            return "_"
        }
    }
    return String(normalized.prefix(24))
}

private func applyRuntimeStatsOverlay(
    _ overlay: Melix_Worker_V1_RuntimeStats,
    to stats: inout Melix_Worker_V1_RuntimeStats
) {
    if !overlay.lastProbeKind.isEmpty {
        stats.lastProbeKind = overlay.lastProbeKind
    }
    if overlay.lastPreprocessLatencyMs > 0 {
        stats.lastPreprocessLatencyMs = overlay.lastPreprocessLatencyMs
    }
    if overlay.lastPreprocessInputBytes > 0 {
        stats.lastPreprocessInputBytes = overlay.lastPreprocessInputBytes
    }
    if overlay.lastPreprocessPeakMemoryBytes > 0 {
        stats.lastPreprocessPeakMemoryBytes = overlay.lastPreprocessPeakMemoryBytes
    }
    if overlay.lastFirstTokenLatencyMs > 0 {
        stats.lastFirstTokenLatencyMs = overlay.lastFirstTokenLatencyMs
    }
    if overlay.lastVideoEffectiveFrameCount > 0 {
        stats.lastVideoEffectiveFrameCount = overlay.lastVideoEffectiveFrameCount
    }
    if overlay.lastVideoRequestedFrameBudget > 0 {
        stats.lastVideoRequestedFrameBudget = overlay.lastVideoRequestedFrameBudget
    }
    if overlay.lastVideoWindowMs > 0 {
        stats.lastVideoWindowMs = overlay.lastVideoWindowMs
    }
    if overlay.lastTempMediaArtifactCount > 0 {
        stats.lastTempMediaArtifactCount = overlay.lastTempMediaArtifactCount
    }
    if overlay.lastTempMediaArtifactBytes > 0 {
        stats.lastTempMediaArtifactBytes = overlay.lastTempMediaArtifactBytes
    }
    stats.lastTempMediaCleanupLatencyMs = overlay.lastTempMediaCleanupLatencyMs
    stats.lastTempMediaCleanupFailureCount = overlay.lastTempMediaCleanupFailureCount
    if !overlay.lastMultimodalDecodeMode.isEmpty {
        stats.lastMultimodalDecodeMode = overlay.lastMultimodalDecodeMode
    }
    if !overlay.lastMultimodalFallbackReason.isEmpty {
        stats.lastMultimodalFallbackReason = overlay.lastMultimodalFallbackReason
    }
    if !overlay.lastMultimodalDecodeSyncMode.isEmpty {
        stats.lastMultimodalDecodeSyncMode = overlay.lastMultimodalDecodeSyncMode
    }
}
