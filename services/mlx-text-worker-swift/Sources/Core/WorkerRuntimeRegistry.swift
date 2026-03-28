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
    let resumeHint: String
    let acceleration: Melix_Worker_V1_AccelerationPolicy
    let context: TextPrefillContext
}

struct WorkerPrefillResult: Sendable {
    let decodeHandle: String
    let promptTokens: Int
}

struct WorkerDecodeSession: @unchecked Sendable {
    let loadedModel: LoadedModelRecord
    let prefill: StoredPrefillContext
}

actor WorkerRuntimeRegistry {
    private let configuration: WorkerConfiguration
    private let modelCatalog: WorkerModelCatalog
    private let runtime: TextRuntime

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
        runtime: TextRuntime = TextRuntime()
    ) {
        self.configuration = configuration
        self.modelCatalog = modelCatalog
        self.runtime = runtime
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
        cache.supportsPagedCache = false
        cache.supportsDiskCache = false
        cache.kvQuantProfiles = ["q4"]
        cache.supportsBoundarySnapshots = false
        capabilities.cache = cache

        var execution = Melix_Worker_V1_ExecutionCapabilities()
        execution.supportsContinuousBatching = false
        execution.supportsSpeculativeDecoding = supportsSpeculativeDecoding()
        capabilities.execution = execution

        var ext = Melix_Worker_V1_Capability()
        ext.name = "engine_family"
        ext.metadata = ["value": configuration.backendMode]
        capabilities.ext = [ext]

        return capabilities
    }

    func loadModel(_ requested: Melix_Worker_V1_ModelSpec) async throws -> LoadedModelRecord {
        let resolved = modelCatalog.get(requested.modelID).map { catalogModel in
            mergeModelSpec(requested, fallback: catalogModel)
        } ?? requested

        let loaded = try await runtime.loadModel(spec: resolved)
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
        requestID: String,
        modelHandle: String,
        messages: [Melix_Worker_V1_ChatMessage],
        prefillStepSize: UInt32,
        returnDecodeHandle: Bool,
        resumeHint: String,
        acceleration: Melix_Worker_V1_AccelerationPolicy,
        shouldAbort: @escaping @Sendable () -> Bool
    ) async throws -> WorkerPrefillResult {
        guard let loaded = loadedModels[modelHandle] else {
            throw WorkerRuntimeRegistryError.unknownModelHandle
        }

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

        let result = try await runtime.prefill(
            model: loaded.runtimeModel,
            messages: messages,
            prefillStepSize: prefillStepSize,
            resumeHint: resumeHint,
            shouldAbort: shouldAbort
        )

        var decodeHandle = ""
        if returnDecodeHandle {
            decodeHandle = "\(modelHandle)::decode::\(nextDecodeHandle)"
            nextDecodeHandle += 1
            prefillContexts[decodeHandle] = StoredPrefillContext(
                decodeHandle: decodeHandle,
                modelHandle: modelHandle,
                requestID: requestID,
                promptTokens: result.promptTokens,
                resumeHint: resumeHint,
                acceleration: acceleration,
                context: result.context
            )
        }

        return WorkerPrefillResult(
            decodeHandle: decodeHandle,
            promptTokens: result.promptTokens
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

    func runtimeStats() -> Melix_Worker_V1_RuntimeStats {
        var stats = Melix_Worker_V1_RuntimeStats()
        if draining {
            stats.workerState = "draining"
        } else if activeRequests > 0 {
            stats.workerState = "busy"
        } else {
            stats.workerState = "idle"
        }
        stats.residentBytes = loadedModels.values.reduce(0) { $0 + $1.estimatedResidentBytes }
        stats.activeRequests = activeRequests
        stats.activePrefills = activePrefills
        stats.activeDecodes = activeDecodes
        stats.l1CacheBytes = 0
        stats.l2CacheBytes = 0
        stats.l1HitRate = 0
        stats.l2HitRate = 0
        return stats
    }

    func setDraining(_ draining: Bool) {
        self.draining = draining
    }
}

enum WorkerRuntimeRegistryError: Error, LocalizedError {
    case unknownModelHandle
    case unknownDecodeHandle

    var errorDescription: String? {
        switch self {
        case .unknownModelHandle:
            return "Unknown model handle."
        case .unknownDecodeHandle:
            return "Unknown decode handle."
        }
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
