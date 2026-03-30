import Foundation
import MelixWorkerProtocol

struct LoadedModelRecord: @unchecked Sendable {
    let handle: String
    let spec: Melix_Worker_V1_ModelSpec
    let runtimeModel: LoadedTextModel
    let estimatedResidentBytes: UInt64
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
    let activeKVQuantizationRatio: Int
    let cacheStats: Melix_Worker_V1_CacheStats
    let hotPrefixCount: Int
}

struct WorkerDecodeSession: @unchecked Sendable {
    let loadedModel: LoadedModelRecord
    let prefill: StoredPrefillContext
}

actor WorkerRuntimeRegistry {
    private static let estimatedPrefillResidentBytesPerToken: UInt64 = 2_048
    private static let estimatedMediaPartTokens = 256

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
            diskStore: DiskCacheStore(rootPath: configuration.cacheRootPath)
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
        cache.kvQuantProfiles = ["q4", "q8"]
        cache.supportsBoundarySnapshots = false
        capabilities.cache = cache

        var execution = Melix_Worker_V1_ExecutionCapabilities()
        execution.supportsContinuousBatching = false
        execution.supportsSpeculativeDecoding = supportsSpeculativeDecoding()
        capabilities.execution = execution

        var ext = Melix_Worker_V1_Capability()
        ext.name = "engine_family"
        ext.metadata = ["value": configuration.backendMode]
        var acceleratedPrefill = Melix_Worker_V1_Capability()
        acceleratedPrefill.name = "accelerated_prefill"
        acceleratedPrefill.metadata = ["value": supportsAcceleratedPrefill() ? "yes" : "no"]

        var activeKV = Melix_Worker_V1_Capability()
        activeKV.name = "active_kv_quantized"
        activeKV.metadata = [
            "value": supportsActiveKVQuantization() ? "yes" : "no",
            "profiles": "q4,q8"
        ]

        capabilities.ext = [ext, acceleratedPrefill, activeKV]

        return capabilities
    }

    func loadModel(
        _ requested: Melix_Worker_V1_ModelSpec,
        memoryBudgetBytes: UInt64 = 0
    ) async throws -> LoadedModelRecord {
        let resolved = modelCatalog.get(requested.modelID).map { catalogModel in
            mergeModelSpec(requested, fallback: catalogModel)
        } ?? requested

        let loaded = try await runtime.loadModel(spec: resolved)
        let existingResidentBytes = loadedModels.values.reduce(0) { $0 + $1.estimatedResidentBytes }
        let projectedResidentBytes = existingResidentBytes &+ loaded.estimatedResidentBytes
        let requiredProcessBytes = projectedResidentBytes &+ configuration.modelLoadHeadroomBytes
        if configuration.processMemoryBudgetBytes > 0, requiredProcessBytes > configuration.processMemoryBudgetBytes {
            await runtime.unloadModel(loaded.model)
            throw WorkerRuntimeRegistryError.memoryBudgetExceeded(
                budgetBytes: configuration.processMemoryBudgetBytes,
                headroomBytes: configuration.modelLoadHeadroomBytes,
                projectedResidentBytes: projectedResidentBytes,
                requiredBytes: requiredProcessBytes
            )
        }

        let requiredRequestBytes = loaded.estimatedResidentBytes &+ configuration.modelLoadHeadroomBytes
        if memoryBudgetBytes > 0, requiredRequestBytes > memoryBudgetBytes {
            await runtime.unloadModel(loaded.model)
            throw WorkerRuntimeRegistryError.memoryBudgetExceeded(
                budgetBytes: memoryBudgetBytes,
                headroomBytes: configuration.modelLoadHeadroomBytes,
                projectedResidentBytes: loaded.estimatedResidentBytes,
                requiredBytes: requiredRequestBytes
            )
        }
        let handle = "\(resolved.modelID)::\(nextModelHandle)"
        nextModelHandle += 1

        let record = LoadedModelRecord(
            handle: handle,
            spec: resolved,
            runtimeModel: loaded.model,
            estimatedResidentBytes: loaded.estimatedResidentBytes
        )
        loadedModels[handle] = record
        return record
    }

    func unloadModel(_ handle: String) async -> Bool {
        guard let removed = loadedModels.removeValue(forKey: handle) else {
            return false
        }
        prefillContexts = prefillContexts.filter { $0.value.modelHandle != handle }
        await cacheStore.purgeModel(modelID: removed.spec.modelID)
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

        let resolvedAcceleration = normalizedAccelerationPolicy(acceleration)
        try enforcePrefillGuards(
            loaded: loaded,
            messages: messages,
            acceleration: resolvedAcceleration
        )

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

        if !execution.cacheHints.restoreSnapshotID.isEmpty {
            let restored = try await restoreBoundarySnapshotRecord(snapshotID: execution.cacheHints.restoreSnapshotID)
            let requestMessages = messages.isEmpty ? restored.messages : messages
            let restoreResumeHint = restored.snapshot.snapshotID.isEmpty
                ? restored.resumeHint
                : "snapshot-restore:\(restored.snapshot.snapshotID)"
            let runtimePrefill = try await runtime.prefill(
                model: loaded.runtimeModel,
                messages: requestMessages,
                prefillStepSize: 0,
                resumeHint: restoreResumeHint,
                acceleration: normalizedAccelerationPolicy(restored.acceleration),
                shouldAbort: shouldAbort
            )

            let decodeHandle = "\(modelHandle)::decode::\(nextDecodeHandle)"
            nextDecodeHandle += 1
            prefillContexts[decodeHandle] = StoredPrefillContext(
                decodeHandle: decodeHandle,
                modelHandle: loaded.handle,
                requestID: restored.snapshot.requestID.isEmpty ? requestID : restored.snapshot.requestID,
                promptTokens: restored.promptTokens,
                messages: requestMessages,
                resumeHint: restored.resumeHint,
                acceleration: restored.acceleration,
                activeKVQuantizationRatio: activeKVQuantizationRatio(from: restored.acceleration),
                blockTableID: restored.blockTableID,
                blockTable: restored.blockTable,
                restoredSnapshotID: restored.snapshot.snapshotID,
                prefix: await cacheStore.lookupPrefix(for: restored.blockTable.cacheKey),
                context: runtimePrefill.context
            )

            let cacheSnapshot = await cacheStore.snapshot()
            return WorkerPrefillResult(
                decodeHandle: decodeHandle,
                blockTableID: restored.blockTableID,
                blockTable: restored.blockTable,
                promptTokens: restored.promptTokens,
                restoredSnapshotID: restored.snapshot.snapshotID,
                appliedAcceleration: restored.acceleration,
                acceleratedPrefillGainPct: 0,
                activeKVQuantizationRatio: activeKVQuantizationRatio(from: restored.acceleration),
                cacheStats: cacheSnapshot.stats,
                hotPrefixCount: cacheSnapshot.hotPrefixes.count
            )
        }

        let result = try await runtime.prefill(
            model: loaded.runtimeModel,
            messages: messages,
            prefillStepSize: prefillStepSize,
            resumeHint: resumeHint,
            acceleration: resolvedAcceleration,
            shouldAbort: shouldAbort
        )

        var decodeHandle = ""
        var blockTableID = ""
        var blockTable = Melix_Worker_V1_BlockTable()
        if returnDecodeHandle {
            decodeHandle = "\(modelHandle)::decode::\(nextDecodeHandle)"
            nextDecodeHandle += 1
            let registration = try await cacheStore.registerPrefill(
                execution: execution,
                model: loaded.spec,
                messages: messages,
                promptTokens: result.promptTokens,
                decodeHandle: decodeHandle,
                activeKVQuantizationRatio: result.activeKVQuantizationRatio
            )
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

        return WorkerPrefillResult(
            decodeHandle: decodeHandle,
            blockTableID: blockTableID,
            blockTable: blockTable,
            promptTokens: result.promptTokens,
            restoredSnapshotID: "",
            appliedAcceleration: result.appliedAcceleration,
            acceleratedPrefillGainPct: result.acceleratedPrefillGainPct,
            activeKVQuantizationRatio: result.activeKVQuantizationRatio,
            cacheStats: cacheSnapshot.stats,
            hotPrefixCount: cacheSnapshot.hotPrefixes.count
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
        try await runtime.decodeEvents(
            model: session.loadedModel.runtimeModel,
            context: session.prefill.context,
            sampling: sampling,
            maxOutputTokens: maxOutputTokens,
            decodeStepSize: decodeStepSize,
            prefillToken: prefillToken,
            acceleration: acceleration,
            shouldAbort: shouldAbort
        )
    }

    func supportsSpeculativeDecoding() -> Bool {
        configuration.backendMode.lowercased() == "deterministic"
    }

    func supportsAcceleratedPrefill() -> Bool {
        true
    }

    func supportsActiveKVQuantization() -> Bool {
        true
    }

    func runtimeStats() async -> Melix_Worker_V1_RuntimeStats {
        let cacheStats = await cacheStore.stats()
        let modelResidentBytes = loadedModels.values.reduce(0) { $0 + $1.estimatedResidentBytes }
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
        stats.memoryHeadroomBytes = configuration.modelLoadHeadroomBytes
        stats.residentBytes = modelResidentBytes &+ cacheResidentBytes &+ kvCacheBytes
        stats.activeRequests = activeRequests
        stats.activePrefills = activePrefills
        stats.activeDecodes = activeDecodes
        stats.l1CacheBytes = cacheStats.l1Bytes
        stats.l2CacheBytes = cacheStats.l2Bytes
        stats.l1HitRate = cacheStats.l1HitRate
        stats.l2HitRate = cacheStats.l2HitRate
        return stats
    }

    func setDraining(_ draining: Bool) {
        self.draining = draining
    }

    func cacheStatsResponse() async -> Melix_Worker_V1_GetCacheStatsResponse {
        var response = Melix_Worker_V1_GetCacheStatsResponse()
        response.stats = await cacheStore.stats()
        response.snapshot = await cacheStore.snapshot()
        return response
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
        let snapshot = await cacheStore.saveBoundarySnapshot(
            requestID: effectiveRequestID,
            tokenBoundary: boundary,
            model: loaded.spec,
            prefill: stored
        )

        var response = Melix_Worker_V1_SaveBoundarySnapshotResponse()
        response.ok = true
        response.snapshotID = snapshot.snapshotID
        response.snapshot = snapshot
        return response
    }

    func saveBoundarySnapshot(
        requestID: String,
        session: WorkerDecodeSession,
        tokenBoundary: UInt32
    ) async -> Melix_Worker_V1_SaveBoundarySnapshotResponse {
        let effectiveRequestID = requestID.isEmpty ? session.prefill.requestID : requestID
        let boundary = tokenBoundary > 0 ? tokenBoundary : UInt32(max(0, session.prefill.promptTokens))
        let snapshot = await cacheStore.saveBoundarySnapshot(
            requestID: effectiveRequestID,
            tokenBoundary: boundary,
            model: session.loadedModel.spec,
            prefill: session.prefill
        )

        var response = Melix_Worker_V1_SaveBoundarySnapshotResponse()
        response.ok = true
        response.snapshotID = snapshot.snapshotID
        response.snapshot = snapshot
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
        response.blockTable = restored.blockTable
        response.snapshot = restored.snapshot
        return response
    }

    private func restoreBoundarySnapshotRecord(
        snapshotID: String
    ) async throws -> (
        snapshot: Melix_Worker_V1_SnapshotRef,
        model: Melix_Worker_V1_ModelSpec,
        messages: [Melix_Worker_V1_ChatMessage],
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        promptTokens: Int,
        blockTableID: String,
        blockTable: Melix_Worker_V1_BlockTable,
        decodeHandle: String
    ) {
        guard let restored = await cacheStore.restoreBoundarySnapshot(snapshotID: snapshotID) else {
            throw WorkerRuntimeRegistryError.unknownSnapshotID
        }

        guard let loaded = loadedModels.values.first(where: {
            $0.spec.modelID == restored.model.modelID
        }) else {
            throw WorkerRuntimeRegistryError.snapshotModelNotLoaded
        }

        let runtimePrefill = try await runtime.prefill(
            model: loaded.runtimeModel,
            messages: restored.messages,
            prefillStepSize: 0,
            resumeHint: restored.resumeHint,
            acceleration: restored.acceleration,
            shouldAbort: { false }
        )

        let decodeHandle = "\(loaded.handle)::decode::\(nextDecodeHandle)"
        nextDecodeHandle += 1
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
            prefix: await cacheStore.lookupPrefix(for: restored.blockTable.cacheKey),
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
        if configuration.processMemoryBudgetBytes > 0, requiredBytes > configuration.processMemoryBudgetBytes {
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
        case .imageUri, .imageBytes, .audioUri, .audioBytes:
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
        acceleration.mode != .acceleratedPrefill
    }
}

enum WorkerRuntimeRegistryError: Error, LocalizedError, Equatable {
    case unknownModelHandle
    case unknownDecodeHandle
    case unknownSnapshotID
    case snapshotModelNotLoaded
    case contextLimitExceeded(maxContext: UInt32, promptTokens: Int)
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
        case .memoryBudgetExceeded:
            return "Projected resident memory would exceed the process budget."
        case .contextLimitExceeded:
            return "Prefill prompt exceeds the model context limit."
        case .prefillMemoryGuardExceeded:
            return "Projected prefill memory would exceed the process budget."
        case .quadraticPrefillGuardExceeded:
            return "Prefill request exceeds the configured quadratic fallback threshold."
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
        case .snapshotModelNotLoaded:
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
             (.snapshotModelNotLoaded, .snapshotModelNotLoaded):
            return true
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
        default:
            return false
        }
    }
}

func accelerationModeName(_ mode: Melix_Worker_V1_AccelerationMode) -> String {
    switch mode {
    case .baseline:
        return "baseline"
    case .acceleratedPrefill:
        return "accelerated_prefill"
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
    if resolved.ext.isEmpty {
        resolved.ext = fallback.ext
    }
    return resolved
}
