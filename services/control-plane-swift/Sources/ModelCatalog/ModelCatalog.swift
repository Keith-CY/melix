import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

private extension UInt32 {
    func saturatingAdd(_ value: UInt32) -> UInt32 {
        let (result, overflow) = addingReportingOverflow(value)
        return overflow ? UInt32.max : result
    }
}

public actor ModelCatalog {
    public struct EvictionDecision: Equatable, Sendable {
        public let modelID: String
        public let reason: String

        public init(modelID: String, reason: String) {
            self.modelID = modelID
            self.reason = reason
        }
    }

    public struct EvictionPlan: Equatable, Sendable {
        public let decisions: [EvictionDecision]
        public let pinnedProtectedModelIDs: [String]

        public init(
            decisions: [EvictionDecision] = [],
            pinnedProtectedModelIDs: [String] = []
        ) {
            self.decisions = decisions
            self.pinnedProtectedModelIDs = pinnedProtectedModelIDs
        }
    }

    public struct IdleSweepPlan: Equatable, Sendable {
        public let decisions: [EvictionDecision]
        public let activeProtectedModelIDs: [String]
        public let pinnedProtectedModelIDs: [String]

        public init(
            decisions: [EvictionDecision] = [],
            activeProtectedModelIDs: [String] = [],
            pinnedProtectedModelIDs: [String] = []
        ) {
            self.decisions = decisions
            self.activeProtectedModelIDs = activeProtectedModelIDs
            self.pinnedProtectedModelIDs = pinnedProtectedModelIDs
        }
    }

    private struct ResidencyLedger: Sendable {
        var lastAccessOrdinal: UInt64
        var lastAccessUnixMs: Int64
        var transitionReason: String
        var memoryBudgetBytes: UInt64
        var memoryHeadroomBytes: UInt64
        var requiredBytes: UInt64
    }

    public struct MemoryBudgetEvidence: Equatable, Sendable {
        public let memoryBudgetBytes: UInt64
        public let memoryHeadroomBytes: UInt64
        public let requiredBytes: UInt64

        public init(
            memoryBudgetBytes: UInt64 = 0,
            memoryHeadroomBytes: UInt64 = 0,
            requiredBytes: UInt64 = 0
        ) {
            self.memoryBudgetBytes = memoryBudgetBytes
            self.memoryHeadroomBytes = memoryHeadroomBytes
            self.requiredBytes = requiredBytes
        }

        public var isEmpty: Bool {
            memoryBudgetBytes == 0 && memoryHeadroomBytes == 0 && requiredBytes == 0
        }
    }

    public struct RegistryRootState: Equatable, Sendable {
        public let rootID: String
        public let rootPath: String
        public let rootOrder: Int
        public let accessible: Bool
        public let errorCode: String
        public let errorMessage: String
        public let discoveredModelIDs: [String]

        public init(
            rootID: String,
            rootPath: String,
            rootOrder: Int,
            accessible: Bool,
            errorCode: String = "",
            errorMessage: String = "",
            discoveredModelIDs: [String] = []
        ) {
            self.rootID = rootID
            self.rootPath = rootPath
            self.rootOrder = rootOrder
            self.accessible = accessible
            self.errorCode = errorCode
            self.errorMessage = errorMessage
            self.discoveredModelIDs = discoveredModelIDs
        }
    }

    public struct RegistryState: Equatable, Sendable {
        public let hasConfiguredRootOverride: Bool
        public let configuredRootPaths: [String]
        public let roots: [RegistryRootState]
        public let scannedAtUnixMs: Int64

        public init(
            hasConfiguredRootOverride: Bool = false,
            configuredRootPaths: [String] = [],
            roots: [RegistryRootState] = [],
            scannedAtUnixMs: Int64 = 0
        ) {
            self.hasConfiguredRootOverride = hasConfiguredRootOverride
            self.configuredRootPaths = configuredRootPaths
            self.roots = roots
            self.scannedAtUnixMs = scannedAtUnixMs
        }
    }

    private var models: [String: Melix_Controlplane_V1_ModelSummary]
    private var dispatchHandles: [String: String]
    private var residencyLedger: [String: ResidencyLedger]
    private var activeRequestCountByModelID: [String: UInt32]
    private let seedModelIDs: Set<String>
    private var registryModelIDs: Set<String>
    private var registryState: RegistryState
    private var nextAccessOrdinal: UInt64
    private let nowUnixMs: @Sendable () -> Int64

    public init(
        seedModels: [Melix_Controlplane_V1_ModelSummary] = [ModelCatalog.devTextModel()],
        nowUnixMs: @escaping @Sendable () -> Int64 = {
            Int64(Date().timeIntervalSince1970 * 1_000)
        }
    ) {
        let normalizedSeedModels = seedModels.map { ModelCatalog.withSynchronizedResidency($0) }
        let seededNow = nowUnixMs()
        var ledger: [String: ResidencyLedger] = [:]
        var accessOrdinal: UInt64 = 0
        for model in normalizedSeedModels {
            accessOrdinal += 1
            ledger[model.modelID] = ResidencyLedger(
                lastAccessOrdinal: accessOrdinal,
                lastAccessUnixMs: seededNow,
                transitionReason: "",
                memoryBudgetBytes: model.settings.memoryBudgetBytes,
                memoryHeadroomBytes: 0,
                requiredBytes: 0
            )
        }
        self.models = Dictionary(uniqueKeysWithValues: normalizedSeedModels.map { ($0.modelID, $0) })
        self.dispatchHandles = Dictionary(
            uniqueKeysWithValues: normalizedSeedModels.compactMap { model in
                guard model.state == .modelWarm || model.state == .modelPinned else {
                    return nil
                }
                return (model.modelID, ModelCatalog.defaultDispatchHandle(for: model.modelID))
            }
        )
        self.residencyLedger = ledger
        self.activeRequestCountByModelID = [:]
        self.seedModelIDs = Set(normalizedSeedModels.map(\.modelID))
        self.registryModelIDs = []
        self.registryState = RegistryState()
        self.nextAccessOrdinal = accessOrdinal
        self.nowUnixMs = nowUnixMs
    }

    public func listModels() -> [Melix_Controlplane_V1_ModelSummary] {
        models.values.sorted { $0.modelID < $1.modelID }
    }

    public func model(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        models[id]
    }

    public func beginLoad(
        id: String,
        reason: String = "load_requested"
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(id: id, transitionReason: reason, clearMemoryBudgetEvidence: true)
        model.state = .modelLoading
        model.pinned = false
        model = synchronized(model)
        models[id] = model
        return model
    }

    public func recordLoadSucceeded(
        id: String,
        dispatchHandle: String,
        pinRequested: Bool = false,
        workerResidency: Melix_Worker_V1_ResidencyInfo? = nil,
        loadTrust: Melix_Controlplane_V1_ModelLoadTrustPolicy? = nil,
        reason: String? = nil
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }

        let loadedState = ModelCatalog.loadedState(
            for: model.settings,
            pinRequested: pinRequested,
            workerResidency: workerResidency
        )
        model.state = loadedState
        model.pinned = loadedState == .modelPinned || workerResidency?.pinned == true
        touchModel(
            id: id,
            transitionReason: resolvedLoadTransitionReason(
                explicitReason: reason,
                workerResidency: workerResidency
            ),
            memoryBudgetEvidence: nil,
            clearMemoryBudgetEvidence: true
        )
        model = synchronized(model)
        if let workerResidency {
            model.residency.effectiveDiskStreamingMode = Self.controlPlaneDiskStreamingMode(
                for: workerResidency.effectiveDiskStreamingMode
            )
        }
        if let loadTrust {
            model.loadTrust = loadTrust
            model.loadTrust.requiresReloadForTrustChange = false
        }
        models[id] = model

        if loadedState == .modelWarm || loadedState == .modelPinned {
            dispatchHandles[id] = dispatchHandle
        } else {
            dispatchHandles.removeValue(forKey: id)
        }

        return model
    }

    public func recordLoadFailed(
        id: String,
        reason: String = "load_failed",
        memoryBudgetEvidence: MemoryBudgetEvidence? = nil,
        loadTrust: Melix_Controlplane_V1_ModelLoadTrustPolicy? = nil
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(
            id: id,
            transitionReason: reason,
            memoryBudgetEvidence: memoryBudgetEvidence,
            clearMemoryBudgetEvidence: memoryBudgetEvidence == nil
        )
        model.state = .modelFailed
        model.pinned = false
        model = synchronized(model)
        if let loadTrust {
            model.loadTrust = loadTrust
        }
        models[id] = model
        dispatchHandles.removeValue(forKey: id)
        return model
    }

    public func beginUnload(
        id: String,
        reason: String = "operator_unload"
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(id: id, transitionReason: reason, clearMemoryBudgetEvidence: true)
        model.state = .modelEvicting
        model.pinned = false
        model = synchronized(model)
        models[id] = model
        return model
    }

    public func recordUnloadSucceeded(
        id: String,
        reason: String? = nil
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(
            id: id,
            transitionReason: resolvedUnloadTransitionReason(for: id, fallback: reason),
            clearMemoryBudgetEvidence: true
        )
        model.state = .modelUnloaded
        model.pinned = false
        model = synchronized(model)
        models[id] = model
        dispatchHandles.removeValue(forKey: id)
        return model
    }

    public func recordUnloadFailed(
        id: String,
        reason: String? = nil
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(
            id: id,
            transitionReason: failedUnloadTransitionReason(for: id, fallback: reason),
            clearMemoryBudgetEvidence: true
        )
        model.state = .modelFailed
        model.pinned = false
        model = synchronized(model)
        models[id] = model
        dispatchHandles.removeValue(forKey: id)
        return model
    }

    public func loadModel(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        _ = beginLoad(id: id, reason: "operator_load")
        return recordLoadSucceeded(
            id: id,
            dispatchHandle: ModelCatalog.defaultDispatchHandle(for: id),
            reason: "operator_load"
        )
    }

    public func loadModel(id: String, dispatchHandle: String) -> Melix_Controlplane_V1_ModelSummary? {
        _ = beginLoad(id: id, reason: "operator_load")
        return recordLoadSucceeded(id: id, dispatchHandle: dispatchHandle, reason: "operator_load")
    }

    public func unloadModel(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        _ = beginUnload(id: id, reason: "operator_unload")
        return recordUnloadSucceeded(id: id, reason: "operator_unload")
    }

    public func updateSettings(
        id: String,
        settings: Melix_Controlplane_V1_ModelSettings
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        let isLoaded = dispatchHandles[id] != nil
        model.settings = settings
        model.loadTrust = ModelLoadTrustPolicyResolver.reloadAwarePolicy(
            current: model.loadTrust,
            settings: settings,
            isLoaded: isLoaded
        )
        touchModel(id: id, transitionReason: "settings_updated")
        model = synchronized(model)
        models[id] = model
        return model
    }

    public func markModelUsed(id: String) -> Melix_Controlplane_V1_ModelSummary? {
        guard var model = models[id] else {
            return nil
        }
        touchModel(id: id)
        model = synchronized(model)
        models[id] = model
        return model
    }

    public func beginRequest(modelID: String) {
        // Every beginRequest call must be paired with exactly one finishRequest
        // call, either via non-streaming defer cleanup or the SSE onComplete hook.
        let current = activeRequestCountByModelID[modelID] ?? 0
        activeRequestCountByModelID[modelID] = current.saturatingAdd(1)
        touchModel(id: modelID)
    }

    public func finishRequest(modelID: String) {
        let current = activeRequestCountByModelID[modelID] ?? 0
        if current <= 1 {
            activeRequestCountByModelID.removeValue(forKey: modelID)
        } else {
            activeRequestCountByModelID[modelID] = current - 1
        }
        touchModel(id: modelID)
    }

    public func idleSweepPlan(
        servedModelIDs: [String],
        idleTimeoutSeconds: UInt32
    ) -> IdleSweepPlan {
        guard idleTimeoutSeconds > 0 else {
            return IdleSweepPlan()
        }
        let currentNowUnixMs = nowUnixMs()
        var decisions: [EvictionDecision] = []
        var activeProtected: [String] = []
        var pinnedProtected: [String] = []

        let servedModels = servedModelIDs.compactMap { models[$0] }.filter(Self.isResident)
        for model in servedModels.sorted(by: compareRecency) {
            if activeRequestCountByModelID[model.modelID, default: 0] > 0 {
                activeProtected.append(model.modelID)
                continue
            }
            if Self.isPinProtected(model) {
                pinnedProtected.append(model.modelID)
                continue
            }
            let idleDeadline = lastAccessUnixMs(for: model.modelID) + Int64(idleTimeoutSeconds) * 1_000
            if idleDeadline <= currentNowUnixMs {
                decisions.append(EvictionDecision(modelID: model.modelID, reason: "idle_timeout"))
            }
        }

        return IdleSweepPlan(
            decisions: decisions,
            activeProtectedModelIDs: activeProtected.sorted(),
            pinnedProtectedModelIDs: pinnedProtected.sorted()
        )
    }

    public func syncRegistryModels(
        _ discoveredModels: [Melix_Controlplane_V1_ModelSummary],
        reason: String = "worker_registry_sync"
    ) {
        let discoveredByID = Dictionary(uniqueKeysWithValues: discoveredModels.map { ($0.modelID, $0) })
        let discoveredIDs = Set(discoveredByID.keys).subtracting(seedModelIDs)

        for staleID in registryModelIDs.subtracting(discoveredIDs) {
            models.removeValue(forKey: staleID)
            dispatchHandles.removeValue(forKey: staleID)
            residencyLedger.removeValue(forKey: staleID)
        }

        for modelID in discoveredIDs.sorted() {
            guard let source = discoveredByID[modelID] else {
                continue
            }
            let merged = mergedRegistryModel(existing: models[modelID], source: source)
            _ = registerModel(merged, reason: reason)
        }

        registryModelIDs = discoveredIDs
    }

    public func configuredRegistryRootOverride() -> [String]? {
        registryState.hasConfiguredRootOverride ? registryState.configuredRootPaths : nil
    }

    public func updateConfiguredRegistryRoots(_ roots: [String]?) {
        registryState = RegistryState(
            hasConfiguredRootOverride: roots != nil,
            configuredRootPaths: Self.normalizedRegistryRootPaths(roots ?? []),
            roots: registryState.roots,
            scannedAtUnixMs: registryState.scannedAtUnixMs
        )
    }

    public func recordRegistrySnapshot(
        roots: [RegistryRootState],
        scannedAtUnixMs: Int64,
        configuredRootPaths: [String]? = nil
    ) {
        let normalizedConfiguredRoots = configuredRootPaths.map(Self.normalizedRegistryRootPaths) ?? registryState.configuredRootPaths
        registryState = RegistryState(
            hasConfiguredRootOverride: configuredRootPaths != nil ? true : registryState.hasConfiguredRootOverride,
            configuredRootPaths: normalizedConfiguredRoots,
            roots: roots.sorted { lhs, rhs in
                if lhs.rootOrder == rhs.rootOrder {
                    return lhs.rootPath < rhs.rootPath
                }
                return lhs.rootOrder < rhs.rootOrder
            },
            scannedAtUnixMs: scannedAtUnixMs
        )
    }

    public func registrySnapshotState() -> RegistryState {
        registryState
    }

    @discardableResult
    public func registerModel(
        _ source: Melix_Controlplane_V1_ModelSummary,
        reason: String = "catalog_registered"
    ) -> Melix_Controlplane_V1_ModelSummary {
        let now = nowUnixMs()
        if residencyLedger[source.modelID] == nil {
            nextAccessOrdinal += 1
            residencyLedger[source.modelID] = ResidencyLedger(
                lastAccessOrdinal: nextAccessOrdinal,
                lastAccessUnixMs: now,
                transitionReason: reason,
                memoryBudgetBytes: source.settings.memoryBudgetBytes,
                memoryHeadroomBytes: 0,
                requiredBytes: 0
            )
        } else {
            touchModel(id: source.modelID, transitionReason: reason)
        }

        let model = synchronized(source)
        models[source.modelID] = model
        if model.state == .modelWarm || model.state == .modelPinned {
            dispatchHandles[source.modelID] = dispatchHandles[source.modelID] ?? ModelCatalog.defaultDispatchHandle(for: source.modelID)
        } else {
            dispatchHandles.removeValue(forKey: source.modelID)
        }
        return model
    }

    @discardableResult
    public func removeModel(
        id: String,
        reason: String = "catalog_removed"
    ) -> Bool {
        guard seedModelIDs.contains(id) == false, models[id] != nil else {
            return false
        }

        models.removeValue(forKey: id)
        dispatchHandles.removeValue(forKey: id)
        residencyLedger.removeValue(forKey: id)
        registryModelIDs.remove(id)
        _ = reason
        return true
    }

    public func evictionPlanForLoad(id targetID: String) -> EvictionPlan {
        guard let targetModel = models[targetID] else {
            return EvictionPlan()
        }

        let loadedModels = models.values.filter { model in
            model.modelID != targetID && ModelCatalog.isResident(model)
        }
        let currentNowUnixMs = nowUnixMs()

        let ttlExpiredModels = loadedModels
            .filter { model in
                ModelCatalog.isAutomaticallyEvictable(model)
                    && ModelCatalog.isTTLExpired(
                        model,
                        lastAccessUnixMs: lastAccessUnixMs(for: model.modelID),
                        nowUnixMs: currentNowUnixMs
                    )
            }
            .sorted(by: compareRecency)

        let ttlExpiredIDs = Set(ttlExpiredModels.map(\.modelID))
        var decisions = ttlExpiredModels.map { EvictionDecision(modelID: $0.modelID, reason: "ttl_expired") }

        let pinnedProtectedModelIDs = loadedModels
            .filter { model in
                !ttlExpiredIDs.contains(model.modelID)
                    && ModelCatalog.sameEvictionFamily(model, targetModel)
                    && ModelCatalog.isPinProtected(model)
            }
            .map(\.modelID)
            .sorted()

        let lruCandidate = loadedModels
            .filter { model in
                !ttlExpiredIDs.contains(model.modelID)
                    && ModelCatalog.sameEvictionFamily(model, targetModel)
                    && ModelCatalog.isAutomaticallyEvictable(model)
            }
            .sorted(by: compareRecency)
            .first
        if !ModelCatalog.isResident(targetModel),
           let lruCandidate {
            decisions.append(EvictionDecision(modelID: lruCandidate.modelID, reason: "lru_same_capability"))
        }

        return EvictionPlan(
            decisions: decisions,
            pinnedProtectedModelIDs: pinnedProtectedModelIDs
        )
    }

    public func dispatchHandle(for id: String) -> String? {
        guard let model = models[id] else {
            return nil
        }
        guard model.state == .modelWarm || model.state == .modelPinned else {
            return nil
        }
        return dispatchHandles[id]
    }

    public func storedDispatchHandle(for id: String) -> String? {
        dispatchHandles[id]
    }

    private struct CapabilityAdapterMetadata: Sendable {
        let adapterSetHash: String
        let routeKind: WorkerRouteKind
        let capabilityIdentifier: String
        let supportedModalities: [String]
        let supportedTasks: [String]
        let supportedParsers: [String]
        let toolParserMode: ToolParserMode?
        let toolParserNamespaces: [String]
        let toolParserXMLFallback: Bool

        init(
            adapterSetHash: String,
            routeKind: WorkerRouteKind,
            capabilityIdentifier: String,
            supportedModalities: [String],
            supportedTasks: [String],
            supportedParsers: [String],
            toolParserMode: ToolParserMode? = nil,
            toolParserNamespaces: [String] = [],
            toolParserXMLFallback: Bool = false
        ) {
            self.adapterSetHash = adapterSetHash
            self.routeKind = routeKind
            self.capabilityIdentifier = capabilityIdentifier
            self.supportedModalities = supportedModalities
            self.supportedTasks = supportedTasks
            self.supportedParsers = supportedParsers
            self.toolParserMode = toolParserMode
            self.toolParserNamespaces = toolParserNamespaces
            self.toolParserXMLFallback = toolParserXMLFallback
        }

        var ext: [String: String] {
            var ext = [
                "melix.adapter_set_hash": adapterSetHash,
                "melix.capability.route_kind": routeKind.metadataIdentifier,
                "melix.capability.class": capabilityIdentifier,
                "melix.capability.supported_modalities": supportedModalities.joined(separator: ","),
                "melix.capability.supported_tasks": supportedTasks.joined(separator: ","),
                "melix.capability.supported_parsers": supportedParsers.joined(separator: ","),
            ]
            if let toolParserMode {
                ext["tool_parser_mode"] = toolParserMode.rawValue
            }
            if !toolParserNamespaces.isEmpty {
                ext["tool_parser_namespaces"] = toolParserNamespaces.joined(separator: ",")
            }
            if toolParserXMLFallback {
                ext["tool_parser_xml_fallback"] = "true"
            }
            return ext
        }
    }

    private struct DetectedTextIdentity: Sendable {
        let architecture: String
        let familyID: String
        let source: String
    }

    private struct DetectedImageIdentity: Sendable {
        let familyID: String
        let taskKind: String
        let source: String
    }

    private static func textCapabilityAdapter(
        familyID: String,
        defaultRouteKind: WorkerRouteKind
    ) -> CapabilityAdapterMetadata {
        let routeKind = preferredTextRouteKind(for: familyID, defaultRouteKind: defaultRouteKind)
        let supportedParsers = textSupportedParsers(for: familyID)
        return CapabilityAdapterMetadata(
            adapterSetHash: "text-family-\(familyID)",
            routeKind: routeKind,
            capabilityIdentifier: "text",
            supportedModalities: ["text"],
            supportedTasks: ["generate"],
            supportedParsers: supportedParsers,
            toolParserMode: familyID == "qwen3moe" ? .qwen : nil,
            toolParserNamespaces: familyID == "qwen3moe" ? ["tools.text"] : [],
            toolParserXMLFallback: familyID == "qwen3moe"
        )
    }

    private static func embeddingCapabilityAdapter(
        familyID: String
    ) -> CapabilityAdapterMetadata {
        CapabilityAdapterMetadata(
            adapterSetHash: "embedding-family-\(familyID)",
            routeKind: .pythonEmbedding,
            capabilityIdentifier: "embedding",
            supportedModalities: ["text"],
            supportedTasks: ["embed"],
            supportedParsers: ["text"]
        )
    }

    private static func rerankCapabilityAdapter(
        familyID: String
    ) -> CapabilityAdapterMetadata {
        CapabilityAdapterMetadata(
            adapterSetHash: "rerank-family-\(familyID)",
            routeKind: .pythonRerank,
            capabilityIdentifier: "rerank",
            supportedModalities: ["text"],
            supportedTasks: ["rerank"],
            supportedParsers: ["text"]
        )
    }

    private static func visionCapabilityAdapter(
        familyID: String
    ) -> CapabilityAdapterMetadata {
        switch familyID {
        case "paligemma-v1":
            return CapabilityAdapterMetadata(
                adapterSetHash: "vision-family-paligemma-v1",
                routeKind: .pythonVLM,
                capabilityIdentifier: "vlm",
                supportedModalities: ["text", "image"],
                supportedTasks: ["vlm", "generate"],
                supportedParsers: ["text"]
            )
        default:
            return CapabilityAdapterMetadata(
                adapterSetHash: "vision-family-llava-v1",
                routeKind: .pythonVLM,
                capabilityIdentifier: "vlm",
                supportedModalities: ["text", "image"],
                supportedTasks: ["vlm", "generate"],
                supportedParsers: ["text", "qwen"],
                toolParserMode: .qwen,
                toolParserNamespaces: ["tools.vision"],
                toolParserXMLFallback: true
            )
        }
    }

    private static func audioCapabilityAdapter(
        familyID: String,
        modelKind: String
    ) -> CapabilityAdapterMetadata {
        if modelKind == "transcription" {
            return CapabilityAdapterMetadata(
                adapterSetHash: "audio-family-\(familyID)",
                routeKind: .pythonTranscription,
                capabilityIdentifier: "transcription",
                supportedModalities: ["audio", "text"],
                supportedTasks: ["transcribe"],
                supportedParsers: ["text"]
            )
        }
        return CapabilityAdapterMetadata(
            adapterSetHash: "audio-family-\(familyID)",
            routeKind: .pythonSpeech,
            capabilityIdentifier: "speech",
            supportedModalities: ["text", "audio"],
            supportedTasks: ["speak"],
            supportedParsers: ["text"]
        )
    }

    private static func imageCapabilityAdapter(
        familyID: String,
        supportsGeneration: Bool,
        supportsEdit: Bool
    ) -> CapabilityAdapterMetadata {
        var supportedTasks: [String] = []
        if supportsGeneration {
            supportedTasks.append("image_generate")
        }
        if supportsEdit {
            supportedTasks.append("image_edit")
        }
        return CapabilityAdapterMetadata(
            adapterSetHash: "image-family-\(familyID)",
            routeKind: .pythonImage,
            capabilityIdentifier: "image_generation",
            supportedModalities: ["text", "image"],
            supportedTasks: supportedTasks,
            supportedParsers: ["text"]
        )
    }

    private static func audioMetadata(
        backendID: String,
        familyID: String,
        installProfile: String,
        languages: [String] = [],
        voiceMode: String = "",
        outputFormats: [String] = [],
        supportsInstructions: Bool = false,
        voiceCatalogSummary: String = "",
        voiceLocales: [String] = [],
        defaultLocale: String = "",
        packagedDefaultLocale: String = "",
        localePolicy: String = ""
    ) -> [String: String] {
        var metadata = [
            "melix.audio.backend_id": backendID,
            "melix.audio.family_id": familyID,
            "melix.audio.install_profile": installProfile,
            "melix.audio.languages": languages.joined(separator: ","),
            "melix.audio.voice_mode": voiceMode,
            "melix.audio.output_formats": outputFormats.joined(separator: ","),
            "melix.audio.supports_instructions": supportsInstructions ? "true" : "false",
        ]
        metadata["melix.audio.voice_catalog_summary"] = voiceCatalogSummary
        metadata["melix.audio.voice_locales"] = voiceLocales.joined(separator: ",")
        metadata["melix.audio.default_locale"] = defaultLocale
        metadata["melix.audio.packaged_default_locale"] = packagedDefaultLocale
        metadata["melix.audio.locale_policy"] = localePolicy
        return metadata
    }

    private static func applyCapabilityAdapter(
        _ adapter: CapabilityAdapterMetadata,
        to model: inout Melix_Controlplane_V1_ModelSummary
    ) {
        model.routeClass = workerRouteClass(for: adapter.routeKind)
        if let capabilityClass = capabilityClass(for: adapter.capabilityIdentifier) {
            model.capabilityClass = capabilityClass
        }
        model.supportedModalities = adapter.supportedModalities
        model.supportedTasks = adapter.supportedTasks
        model.settings.ext.merge(adapter.ext) { _, new in new }
    }

    private static func workerRouteClass(
        for routeKind: WorkerRouteKind
    ) -> Melix_Controlplane_V1_WorkerRouteClass {
        routeKind.routeClass
    }

    private static func capabilityClass(
        for identifier: String
    ) -> Melix_Controlplane_V1_ModelCapabilityClass? {
        switch identifier {
        case "text":
            return .modelCapabilityText
        case "embedding":
            return .modelCapabilityEmbedding
        case "rerank":
            return .modelCapabilityRerank
        case "model_operations":
            return .modelCapabilityModelOperations
        case "ocr":
            return .modelCapabilityOcr
        case "vlm":
            return .modelCapabilityVlm
        case "transcription":
            return .modelCapabilityTranscription
        case "speech":
            return .modelCapabilitySpeech
        case "image_generation":
            return .modelCapabilityImageGeneration
        default:
            return nil
        }
    }

    private static func inferTextIdentity(
        from modelPath: String,
        explicitFamilyID: String?
    ) -> DetectedTextIdentity {
        let normalizedPath = modelPath.lowercased()
        if let explicitFamilyID, !explicitFamilyID.isEmpty {
            return DetectedTextIdentity(
                architecture: textArchitecture(for: explicitFamilyID),
                familyID: explicitFamilyID,
                source: "explicit_override"
            )
        }
        if normalizedPath.contains("mistral4") || normalizedPath.contains("mistral-small-4") {
            return DetectedTextIdentity(
                architecture: "mistral4",
                familyID: "mistral4",
                source: "directory_name"
            )
        }
        if normalizedPath.contains("mixtral") {
            return DetectedTextIdentity(
                architecture: "mixtral",
                familyID: "mixtral",
                source: "directory_name"
            )
        }
        if normalizedPath.contains("qwen3") && normalizedPath.contains("moe") {
            return DetectedTextIdentity(
                architecture: "qwen3_moe",
                familyID: "qwen3moe",
                source: "directory_name"
            )
        }
        if normalizedPath.contains("deepseek") || normalizedPath.contains("mla") {
            return DetectedTextIdentity(
                architecture: "deepseek_v3",
                familyID: "deepseek-mla",
                source: "directory_name"
            )
        }
        if normalizedPath.contains("nemotron-h") || normalizedPath.contains("nemotron_h") {
            return DetectedTextIdentity(
                architecture: "nemotron_h",
                familyID: "nemotron-h",
                source: "directory_name"
            )
        }
        return DetectedTextIdentity(
            architecture: "llama",
            familyID: "llama",
            source: "default"
        )
    }

    private static func preferredTextRouteKind(
        for familyID: String,
        defaultRouteKind: WorkerRouteKind
    ) -> WorkerRouteKind {
        switch familyID {
        case "mistral4", "mixtral", "qwen3moe", "deepseek-mla", "nemotron-h":
            return .pythonCompatibility
        default:
            return defaultRouteKind
        }
    }

    private static func textSupportedParsers(for familyID: String) -> [String] {
        familyID == "qwen3moe" ? ["text", "qwen"] : ["text"]
    }

    private static func textArchitecture(for familyID: String) -> String {
        switch familyID {
        case "mistral4":
            return "mistral4"
        case "mixtral":
            return "mixtral"
        case "qwen3moe":
            return "qwen3_moe"
        case "deepseek-mla":
            return "deepseek_v3"
        case "nemotron-h":
            return "nemotron_h"
        default:
            return "llama"
        }
    }

    private static func textAttentionProfile(for familyID: String) -> String {
        familyID == "deepseek-mla" ? "mla" : "gqa"
    }

    private static func textRoPEProfile(for familyID: String) -> String {
        switch familyID {
        case "mistral4", "qwen3moe":
            return "yarn_interleaved"
        default:
            return "standard"
        }
    }

    private static func textMOEEnabled(for familyID: String) -> Bool {
        switch familyID {
        case "mistral4", "mixtral", "qwen3moe", "deepseek-mla":
            return true
        default:
            return false
        }
    }

    private static func textExpertCount(for familyID: String) -> Int {
        switch familyID {
        case "mistral4", "mixtral":
            return 8
        case "qwen3moe":
            return 128
        case "deepseek-mla":
            return 64
        default:
            return 0
        }
    }

    private static func textMOEGateDequant(for familyID: String) -> Bool {
        switch familyID {
        case "mistral4", "qwen3moe", "deepseek-mla":
            return true
        default:
            return false
        }
    }

    private static func inferImageIdentity(
        from modelPath: String,
        explicitFamilyID: String?,
        explicitTaskKind: String?
    ) -> DetectedImageIdentity {
        let normalizedTaskKind = normalizedImageTaskKind(explicitTaskKind) ?? "text-to-image"
        if let explicitFamilyID, !explicitFamilyID.isEmpty {
            return DetectedImageIdentity(
                familyID: explicitFamilyID,
                taskKind: normalizedTaskKind,
                source: "explicit_override"
            )
        }

        let normalizedPath = modelPath.lowercased()
        if normalizedPath.contains("kontext") {
            return DetectedImageIdentity(
                familyID: "kontext-v1",
                taskKind: normalizedTaskKind == "text-to-image" ? "image-text-to-image" : normalizedTaskKind,
                source: "directory_name"
            )
        }
        if normalizedPath.contains("fill") || normalizedPath.contains("inpaint") {
            return DetectedImageIdentity(
                familyID: "fill-v1",
                taskKind: "image-text-to-image",
                source: "directory_name"
            )
        }
        if normalizedPath.contains("qwenimage") || normalizedPath.contains("qwen-image") {
            return DetectedImageIdentity(
                familyID: "qwenimage-v1",
                taskKind: "text-to-image",
                source: "directory_name"
            )
        }
        if normalizedPath.contains("fibo") {
            return DetectedImageIdentity(
                familyID: "fibo-v1",
                taskKind: "text-to-image",
                source: "directory_name"
            )
        }
        if normalizedPath.contains("klein") {
            return DetectedImageIdentity(
                familyID: "klein-v1",
                taskKind: "image-text-to-image",
                source: "directory_name"
            )
        }
        if normalizedTaskKind == "image-text-to-image" {
            return DetectedImageIdentity(
                familyID: "kontext-v1",
                taskKind: normalizedTaskKind,
                source: "task_kind"
            )
        }
        return DetectedImageIdentity(
            familyID: "deterministic-v1",
            taskKind: normalizedTaskKind,
            source: "default"
        )
    }

    private static func normalizedImageTaskKind(_ value: String?) -> String? {
        guard let value else {
            return nil
        }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        switch trimmed {
        case "":
            return nil
        case "text-to-image", "image-text-to-image":
            return trimmed
        default:
            return nil
        }
    }

    private static func imageSupportsGeneration(for familyID: String) -> Bool {
        switch familyID {
        case "fill-v1", "klein-v1":
            return false
        default:
            return true
        }
    }

    private static func imageSupportsEdit(for familyID: String) -> Bool {
        switch familyID {
        case "qwenimage-v1", "fibo-v1":
            return false
        default:
            return true
        }
    }

    private static func imageDefaultWorkflowRole(for familyID: String) -> String {
        switch familyID {
        case "fill-v1", "klein-v1", "kontext-v1":
            return "edit"
        default:
            return "generate"
        }
    }

    private static func imageDefaultSteps(for familyID: String) -> String {
        switch familyID {
        case "qwenimage-v1":
            return "32"
        case "fill-v1", "klein-v1":
            return "24"
        default:
            return "28"
        }
    }

    private static func imageDefaultGuidance(for familyID: String) -> String {
        switch familyID {
        case "qwenimage-v1":
            return "4.0"
        case "fill-v1", "kontext-v1", "klein-v1":
            return "6.5"
        default:
            return "7.5"
        }
    }

    private static func imageDefaultStrength(for familyID: String) -> String {
        switch familyID {
        case "fill-v1", "kontext-v1", "klein-v1":
            return "0.8"
        default:
            return "1.0"
        }
    }

    public static func devTextModel(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Melix_Controlplane_V1_ModelSummary {
        let modelPath = normalizedEnvironmentValue(
            "MELIX_DEV_TEXT_MODEL_PATH",
            environment: environment
        ) ?? "models/melix-dev-text"
        let explicitFamilyID = normalizedEnvironmentValue(
            "MELIX_DEV_TEXT_FAMILY_ID",
            environment: environment
        )
        let detected = inferTextIdentity(from: modelPath, explicitFamilyID: explicitFamilyID)
        let capabilityAdapter = textCapabilityAdapter(
            familyID: detected.familyID,
            defaultRouteKind: .swiftText
        )
        let identityOverride = explicitFamilyID?.isEmpty == false ? "true" : "false"

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-text"
        model.kind = "text"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityText
        model.routeClass = workerRouteClass(for: capabilityAdapter.routeKind)
        model.quantProfileID = "dev-q4"
        model.maxContext = 8192
        model.features = ["chat", "adaptive_thinking"]
        model.settings.alias = "Melix Text"
        model.settings.pinOnLoad = false
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.defaultAccelerationMode = .baseline
        model.settings.adaptiveThinking.mode = "adaptive"
        model.settings.adaptiveThinking.budgetTokens = 192
        model.settings.ext["text_backend_id"] = "mlx_lm"
        model.settings.ext["text_family_id"] = detected.familyID
        model.settings.ext["model_architecture"] = detected.architecture
        model.settings.ext["detected_architecture"] = detected.architecture
        model.settings.ext["detected_family_id"] = detected.familyID
        model.settings.ext["detected_identity_source"] = detected.source
        model.settings.ext["identity_override"] = identityOverride
        model.settings.ext["melix.text.attention_profile"] = textAttentionProfile(for: detected.familyID)
        model.settings.ext["melix.text.rope_profile"] = textRoPEProfile(for: detected.familyID)
        model.settings.ext["melix.text.moe.enabled"] = textMOEEnabled(for: detected.familyID) ? "true" : "false"
        model.settings.ext["melix.text.moe.gate_dequant"] = textMOEGateDequant(for: detected.familyID) ? "true" : "false"
        let expertCount = textExpertCount(for: detected.familyID)
        if expertCount > 0 {
            model.settings.ext["melix.text.moe.expert_count"] = String(expertCount)
        }
        model.settings.ext["melix.model_path"] = modelPath
        model.settings.ext["melix.model_revision"] = "dev"
        model.settings.ext["melix.tokenizer_hash"] = "tok-dev"
        applyCapabilityAdapter(capabilityAdapter, to: &model)
        model.settings.ext["melix.capability.route_kind"] = capabilityAdapter.routeKind.metadataIdentifier
        return withSynchronizedResidency(model)
    }

    public static func devEmbeddingModel(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Melix_Controlplane_V1_ModelSummary {
        let modelPath = normalizedEnvironmentValue(
            "MELIX_DEV_EMBED_MODEL_PATH",
            environment: environment
        ) ?? "models/melix-dev-embed"
        let detected = inferEmbeddingIdentity(from: modelPath)
        let configuredFamilyID = normalizedEnvironmentValue(
            "MELIX_DEV_EMBED_FAMILY_ID",
            environment: environment
        )
        let configuredBackendID = normalizedEnvironmentValue(
            "MELIX_DEV_EMBED_BACKEND_ID",
            environment: environment
        )
        let resolvedFamilyID: String
        let resolvedBackendID: String
        if let configuredFamilyID, !configuredFamilyID.isEmpty {
            resolvedFamilyID = configuredFamilyID
            resolvedBackendID = configuredBackendID ?? embeddingBackendID(for: resolvedFamilyID)
        } else {
            resolvedBackendID = configuredBackendID ?? detected.backendID
            resolvedFamilyID = defaultEmbeddingFamilyID(
                for: resolvedBackendID,
                detectedFamilyID: detected.familyID
            )
        }
        let resolvedArchitecture = embeddingArchitecture(for: resolvedFamilyID)
        let resolvedPoolingMode = normalizedEnvironmentValue(
            "MELIX_DEV_EMBED_POOLING_MODE",
            environment: environment
        ) ?? embeddingPoolingMode(for: resolvedFamilyID)
        let resolvedNormalization = normalizedEnvironmentValue(
            "MELIX_DEV_EMBED_NORMALIZATION",
            environment: environment
        ) ?? "l2"
        let resolvedDimensions = normalizedEnvironmentValue(
            "MELIX_DEV_EMBED_DIMENSIONS",
            environment: environment
        ) ?? embeddingDimensions(for: resolvedFamilyID)
        let identityOverride = (
            resolvedArchitecture != detected.architecture
                || resolvedFamilyID != detected.familyID
        ) ? "true" : "false"

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-embed"
        model.kind = "embedding"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityEmbedding
        model.routeClass = .workerRoutePythonEmbedding
        model.quantProfileID = "dev-f16"
        model.maxContext = 8192
        model.features = ["embeddings"]
        model.settings.alias = "Melix Embed"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext["embedding_backend_id"] = resolvedBackendID
        model.settings.ext["embedding_family_id"] = resolvedFamilyID
        model.settings.ext["embedding_pooling_mode"] = resolvedPoolingMode
        model.settings.ext["embedding_normalization"] = resolvedNormalization
        model.settings.ext["embedding_dimensions"] = resolvedDimensions
        model.settings.ext["model_architecture"] = resolvedArchitecture
        model.settings.ext["detected_architecture"] = detected.architecture
        model.settings.ext["detected_family_id"] = detected.familyID
        model.settings.ext["detected_identity_source"] = detected.source
        model.settings.ext["identity_override"] = identityOverride
        applyCapabilityAdapter(embeddingCapabilityAdapter(familyID: resolvedFamilyID), to: &model)
        return withSynchronizedResidency(model)
    }

    public static func devRerankModel(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Melix_Controlplane_V1_ModelSummary {
        let backendID = environment["MELIX_DEV_RERANK_BACKEND_ID"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let detected = inferRerankIdentity(
            from: normalizedEnvironmentValue(
                "MELIX_DEV_RERANK_MODEL_PATH",
                environment: environment
            ) ?? "models/melix-dev-rerank"
        )
        let familyID = normalizedEnvironmentValue(
            "MELIX_DEV_RERANK_FAMILY_ID",
            environment: environment
        )
        let resolvedBackendID = (backendID?.isEmpty == false) ? backendID! : "token-overlap-v1"
        let resolvedFamilyID = (familyID?.isEmpty == false) ? familyID! : detected.familyID
        let resolvedArchitecture = rerankArchitecture(for: resolvedFamilyID)
        let defaultScoringMode = rerankScoringMode(for: resolvedFamilyID)
        let configuredScoringMode = environment["MELIX_DEV_RERANK_SCORING_MODE"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedScoringMode = (configuredScoringMode?.isEmpty == false) ? configuredScoringMode! : defaultScoringMode
        let configuredYesNoLabels = environment["MELIX_DEV_RERANK_YES_NO_LABELS"]?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let resolvedYesNoLabels = if resolvedFamilyID == "causal-lm" {
            (configuredYesNoLabels?.isEmpty == false) ? configuredYesNoLabels! : "yes,no"
        } else {
            ""
        }
        let identityOverride = (
            resolvedArchitecture != detected.architecture
                || resolvedFamilyID != detected.familyID
        ) ? "true" : "false"

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-rerank"
        model.kind = "rerank"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityRerank
        model.routeClass = .workerRoutePythonRerank
        model.quantProfileID = "dev-f16"
        model.maxContext = 8192
        model.features = ["rerank"]
        model.settings.alias = "Melix Rerank"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext["rerank_backend_id"] = resolvedBackendID
        model.settings.ext["rerank_family_id"] = resolvedFamilyID
        model.settings.ext["rerank_scoring_mode"] = resolvedScoringMode
        model.settings.ext["model_architecture"] = resolvedArchitecture
        model.settings.ext["detected_architecture"] = detected.architecture
        model.settings.ext["detected_family_id"] = detected.familyID
        model.settings.ext["detected_identity_source"] = detected.source
        model.settings.ext["identity_override"] = identityOverride
        if !resolvedYesNoLabels.isEmpty {
            model.settings.ext["rerank_yes_no_labels"] = resolvedYesNoLabels
        }
        applyCapabilityAdapter(rerankCapabilityAdapter(familyID: resolvedFamilyID), to: &model)
        return withSynchronizedResidency(model)
    }

    public static func devModelOpsModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-model-ops"
        model.kind = "model_ops"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityModelOperations
        model.routeClass = .workerRoutePythonModelOperations
        model.quantProfileID = "dev-ops"
        model.maxContext = 0
        model.features = ["quantize", "download", "upload"]
        model.settings.alias = "Melix Model Operations"
        model.settings.ext["melix.visibility"] = "internal"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        return withSynchronizedResidency(model)
    }

    public static func devOCRModel() -> Melix_Controlplane_V1_ModelSummary {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-ocr"
        model.kind = "ocr"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityOcr
        model.routeClass = .workerRoutePythonOcr
        model.features = ["ocr", "vision"]
        model.supportedModalities = ["image"]
        model.supportedTasks = ["ocr"]
        model.settings.alias = "Melix OCR"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext["ocr_prompt_profile_id"] = "ocr-default-v1"
        model.settings.ext["ocr_prompt_template"] = "OCR instruction: {prompt}"
        model.settings.ext["ocr_auto_prompt"] = "Extract the text from the image exactly as written."
        model.settings.ext["ocr_stop_sequences"] = "<ocr:end>"
        model.settings.ext["ocr_sampling_profile_id"] = "ocr-deterministic"
        model.settings.ext["ocr_default_temperature"] = "0.0"
        model.settings.ext["ocr_default_top_p"] = "1.0"
        model.settings.ext["ocr_default_max_tokens"] = "256"
        return withSynchronizedResidency(model)
    }

    public static func devVLMModel() -> Melix_Controlplane_V1_ModelSummary {
        let familyID = "llava-v1"
        let capabilityAdapter = visionCapabilityAdapter(familyID: familyID)
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-vlm"
        model.kind = "vlm"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityVlm
        model.routeClass = .workerRoutePythonVlm
        model.features = ["vision", "chat"]
        model.settings.alias = "Melix Vision"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext["vision_family_id"] = familyID
        model.settings.ext["vision_prompt_profile_id"] = "llava-chatml-v1"
        model.settings.ext["vision_tokenization_mode"] = "interleaved"
        model.settings.ext["vision_max_images_per_prompt"] = "8"
        model.settings.ext["vision_supports_tool_calls"] = "true"
        model.settings.ext["melix.multimodal_adapter_hash"] = capabilityAdapter.adapterSetHash
        applyCapabilityAdapter(capabilityAdapter, to: &model)
        return withSynchronizedResidency(model)
    }

    public static func devTranscriptionModel() -> Melix_Controlplane_V1_ModelSummary {
        let familyID = "deterministic-transcription"
        let capabilityAdapter = audioCapabilityAdapter(familyID: familyID, modelKind: "transcription")
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-transcribe"
        model.kind = "transcription"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityTranscription
        model.routeClass = .workerRoutePythonTranscription
        model.features = ["audio", "transcription"]
        model.supportedModalities = ["audio"]
        model.supportedTasks = ["transcribe"]
        model.settings.alias = "Melix Whisper"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext.merge(
            audioMetadata(
                backendID: "deterministic",
                familyID: familyID,
                installProfile: "",
                languages: ["und"]
            )
        ) { _, new in new }
        applyCapabilityAdapter(capabilityAdapter, to: &model)
        return withSynchronizedResidency(model)
    }

    public static func devSpeechModel() -> Melix_Controlplane_V1_ModelSummary {
        let familyID = "deterministic-speech"
        let capabilityAdapter = audioCapabilityAdapter(familyID: familyID, modelKind: "speech")
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-speech"
        model.kind = "speech"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilitySpeech
        model.routeClass = .workerRoutePythonSpeech
        model.features = ["audio", "speech"]
        model.supportedModalities = ["text", "audio"]
        model.supportedTasks = ["speak"]
        model.settings.alias = "Melix Voice"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext.merge(
            audioMetadata(
                backendID: "deterministic",
                familyID: familyID,
                installProfile: "",
                languages: ["und"],
                voiceMode: "named",
                outputFormats: ["wav", "mp3"],
                supportsInstructions: false,
                voiceCatalogSummary: "Deterministic synthetic default voice.",
                voiceLocales: ["und"],
                defaultLocale: "und",
                packagedDefaultLocale: "und",
                localePolicy: "request>model_default>packaged_default"
            )
        ) { _, new in new }
        applyCapabilityAdapter(capabilityAdapter, to: &model)
        return withSynchronizedResidency(model)
    }

    public static func mlxWhisperModel() -> Melix_Controlplane_V1_ModelSummary {
        let familyID = "whisper"
        let capabilityAdapter = audioCapabilityAdapter(familyID: familyID, modelKind: "transcription")
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-whisper-mlx"
        model.kind = "transcription"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityTranscription
        model.routeClass = .workerRoutePythonTranscription
        model.quantProfileID = "fp16"
        model.maxContext = 4096
        model.features = ["audio", "transcription"]
        model.settings.alias = "Melix Whisper MLX"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext.merge(
            audioMetadata(
                backendID: "mlx_audio.stt",
                familyID: familyID,
                installProfile: "audio-stt",
                languages: ["auto"]
            )
        ) { _, new in new }
        applyCapabilityAdapter(capabilityAdapter, to: &model)
        return withSynchronizedResidency(model)
    }

    public static func mlxParakeetModel() -> Melix_Controlplane_V1_ModelSummary {
        let familyID = "parakeet"
        let capabilityAdapter = audioCapabilityAdapter(familyID: familyID, modelKind: "transcription")
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-parakeet-mlx"
        model.kind = "transcription"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityTranscription
        model.routeClass = .workerRoutePythonTranscription
        model.quantProfileID = "fp16"
        model.maxContext = 4096
        model.features = ["audio", "transcription"]
        model.settings.alias = "Melix Parakeet MLX"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext.merge(
            audioMetadata(
                backendID: "mlx_audio.stt",
                familyID: familyID,
                installProfile: "audio-stt",
                languages: ["auto"]
            )
        ) { _, new in new }
        applyCapabilityAdapter(capabilityAdapter, to: &model)
        return withSynchronizedResidency(model)
    }

    public static func mlxKokoroModel() -> Melix_Controlplane_V1_ModelSummary {
        let familyID = "kokoro"
        let capabilityAdapter = audioCapabilityAdapter(familyID: familyID, modelKind: "speech")
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-kokoro-mlx"
        model.kind = "speech"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilitySpeech
        model.routeClass = .workerRoutePythonSpeech
        model.quantProfileID = "bf16"
        model.maxContext = 4096
        model.features = ["audio", "speech"]
        model.settings.alias = "Melix Kokoro MLX"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext.merge(
            audioMetadata(
                backendID: "mlx_audio.tts",
                familyID: familyID,
                installProfile: "audio-tts",
                languages: ["en"],
                voiceMode: "named",
                outputFormats: ["wav"],
                supportsInstructions: false,
                voiceCatalogSummary: "Named English voices exposed by the Kokoro speaker catalog.",
                voiceLocales: ["en"],
                defaultLocale: "en",
                packagedDefaultLocale: "en",
                localePolicy: "request>model_default>packaged_default"
            )
        ) { _, new in new }
        applyCapabilityAdapter(capabilityAdapter, to: &model)
        return withSynchronizedResidency(model)
    }

    public static func mlxQwen3TTSModel() -> Melix_Controlplane_V1_ModelSummary {
        let familyID = "qwen3-tts"
        let capabilityAdapter = audioCapabilityAdapter(familyID: familyID, modelKind: "speech")
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-qwen3-tts-mlx"
        model.kind = "speech"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilitySpeech
        model.routeClass = .workerRoutePythonSpeech
        model.quantProfileID = "4bit"
        model.maxContext = 4096
        model.features = ["audio", "speech"]
        model.settings.alias = "Melix Qwen3 TTS MLX"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext.merge(
            audioMetadata(
                backendID: "mlx_audio.tts",
                familyID: familyID,
                installProfile: "audio-tts",
                languages: ["zh", "en"],
                voiceMode: "hybrid",
                outputFormats: ["wav"],
                supportsInstructions: true,
                voiceCatalogSummary: (
                    "Hybrid named and instruction-conditioned multilingual voices "
                    + "for Chinese and English synthesis."
                ),
                voiceLocales: ["zh", "en"],
                defaultLocale: "zh",
                packagedDefaultLocale: "zh",
                localePolicy: "request>model_default>packaged_default"
            )
        ) { _, new in new }
        applyCapabilityAdapter(capabilityAdapter, to: &model)
        return withSynchronizedResidency(model)
    }

    public static func devImageModel(
        environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> Melix_Controlplane_V1_ModelSummary {
        let modelPath = normalizedEnvironmentValue(
            "MELIX_DEV_IMAGE_MODEL_PATH",
            environment: environment
        ) ?? "models/melix-dev-image"
        let explicitFamilyID = normalizedEnvironmentValue(
            "MELIX_DEV_IMAGE_FAMILY_ID",
            environment: environment
        )
        let explicitTaskKind = normalizedEnvironmentValue(
            "MELIX_DEV_IMAGE_TASK_KIND",
            environment: environment
        )
        let detected = inferImageIdentity(
            from: modelPath,
            explicitFamilyID: explicitFamilyID,
            explicitTaskKind: explicitTaskKind
        )
        let supportsGeneration = imageSupportsGeneration(for: detected.familyID)
        let supportsEdit = imageSupportsEdit(for: detected.familyID)
        let capabilityAdapter = imageCapabilityAdapter(
            familyID: detected.familyID,
            supportsGeneration: supportsGeneration,
            supportsEdit: supportsEdit
        )
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-image"
        model.kind = "image"
        model.state = .modelDiscovered
        model.capabilityClass = .modelCapabilityImageGeneration
        model.routeClass = workerRouteClass(for: capabilityAdapter.routeKind)
        model.features = capabilityAdapter.supportedTasks + ["artifact_jobs"]
        model.settings.alias = "Melix Image"
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext["melix.image.backend_id"] = "deterministic"
        model.settings.ext["melix.image.family_id"] = detected.familyID
        model.settings.ext["melix.image.task_kind"] = detected.taskKind
        model.settings.ext["melix.image.default_workflow_role"] = imageDefaultWorkflowRole(for: detected.familyID)
        model.settings.ext["melix.image.supports_generation"] = supportsGeneration ? "true" : "false"
        model.settings.ext["melix.image.supports_edit"] = supportsEdit ? "true" : "false"
        model.settings.ext["melix.image.default_size"] = "1024x1024"
        model.settings.ext["melix.image.default_steps"] = imageDefaultSteps(for: detected.familyID)
        model.settings.ext["melix.image.default_guidance"] = imageDefaultGuidance(for: detected.familyID)
        model.settings.ext["melix.image.default_strength"] = imageDefaultStrength(for: detected.familyID)
        model.settings.ext["melix.image.default_negative_prompt"] = ""
        model.settings.ext["detected_family_id"] = detected.familyID
        model.settings.ext["detected_task_kind"] = detected.taskKind
        model.settings.ext["detected_identity_source"] = detected.source
        model.settings.ext["identity_override"] = explicitFamilyID?.isEmpty == false ? "true" : "false"
        model.settings.ext["task_override"] = explicitTaskKind?.isEmpty == false ? "true" : "false"
        model.settings.ext["melix.model_path"] = modelPath
        model.settings.ext["melix.model_revision"] = "dev"
        model.settings.ext["melix.tokenizer_hash"] = "tok-image-dev"
        applyCapabilityAdapter(capabilityAdapter, to: &model)
        return withSynchronizedResidency(model)
    }

    public static func phaseFiveSeedModels() -> [Melix_Controlplane_V1_ModelSummary] {
        [
            devTextModel(),
            devEmbeddingModel(),
            devRerankModel(),
            devModelOpsModel(),
        ]
    }

    public static func phaseSixContractSeedModels() -> [Melix_Controlplane_V1_ModelSummary] {
        phaseFiveSeedModels() + [
            devOCRModel(),
            devVLMModel(),
            devTranscriptionModel(),
            mlxWhisperModel(),
            mlxParakeetModel(),
            devSpeechModel(),
            mlxKokoroModel(),
            mlxQwen3TTSModel(),
        ]
    }

    public static func phaseSevenContractSeedModels() -> [Melix_Controlplane_V1_ModelSummary] {
        phaseSixContractSeedModels() + [
            devImageModel(),
        ]
    }

    private static func normalizedEnvironmentValue(
        _ key: String,
        environment: [String: String]
    ) -> String? {
        let value = environment[key]?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let value, !value.isEmpty {
            return value
        }
        return nil
    }

    private static func normalizedRegistryRootPaths(_ roots: [String]) -> [String] {
        var normalized: [String] = []
        var seen: Set<String> = []
        for root in roots {
            let trimmed = root.trimmingCharacters(in: .whitespacesAndNewlines)
            guard trimmed.isEmpty == false else {
                continue
            }
            let standardized = URL(fileURLWithPath: trimmed).standardizedFileURL.path
            guard seen.insert(standardized).inserted else {
                continue
            }
            normalized.append(standardized)
        }
        return normalized
    }

    private static func inferEmbeddingIdentity(from modelPath: String) -> (
        architecture: String,
        familyID: String,
        backendID: String,
        source: String
    ) {
        let normalizedPath = modelPath.lowercased()
        if normalizedPath.contains("mxbai") {
            return ("bert", "mxbai-embed", "bert-v1", "directory_name")
        }
        if normalizedPath.contains("bge") {
            return ("bert", "bge-m3", "bert-v1", "directory_name")
        }
        if normalizedPath.contains("xlmr") || normalizedPath.contains("xlm-r") {
            return ("xlmr", "xlmr", "xlmr-v1", "directory_name")
        }
        if normalizedPath.contains("bert") {
            return ("bert", "bert", "bert-v1", "directory_name")
        }
        return ("bert", "bert", "bert-v1", "default")
    }

    private static func embeddingBackendID(for familyID: String) -> String {
        familyID == "xlmr" ? "xlmr-v1" : "bert-v1"
    }

    private static func embeddingArchitecture(for familyID: String) -> String {
        familyID == "xlmr" ? "xlmr" : "bert"
    }

    private static func defaultEmbeddingFamilyID(
        for backendID: String,
        detectedFamilyID: String
    ) -> String {
        if backendID == "xlmr-v1" {
            return "xlmr"
        }
        if ["bert", "bge-m3", "mxbai-embed"].contains(detectedFamilyID) {
            return detectedFamilyID
        }
        return "bert"
    }

    private static func embeddingPoolingMode(for familyID: String) -> String {
        switch familyID {
        case "xlmr", "mxbai-embed":
            return "mean"
        default:
            return "cls"
        }
    }

    private static func embeddingDimensions(for familyID: String) -> String {
        familyID == "mxbai-embed" ? "10" : "8"
    }

    private static func inferRerankIdentity(from modelPath: String) -> (
        architecture: String,
        familyID: String,
        source: String
    ) {
        let normalizedPath = modelPath.lowercased()
        if normalizedPath.contains("causal-lm") || normalizedPath.contains("causallm") {
            return ("causal-lm", "causal-lm", "directory_name")
        }
        if normalizedPath.contains("basic") {
            return ("cross-encoder", "basic", "directory_name")
        }
        if normalizedPath.contains("jina") {
            return ("cross-encoder", "jina-v3", "directory_name")
        }
        return ("cross-encoder", "jina-v3", "default")
    }

    private static func rerankArchitecture(for familyID: String) -> String {
        familyID == "causal-lm" ? "causal-lm" : "cross-encoder"
    }

    private static func rerankScoringMode(for familyID: String) -> String {
        switch familyID {
        case "basic":
            return "set-overlap"
        case "causal-lm":
            return "yes-no-logits"
        default:
            return "order-aware-overlap"
        }
    }

    private static func defaultDispatchHandle(for id: String) -> String {
        "\(id)::local"
    }

    private func mergedRegistryModel(
        existing: Melix_Controlplane_V1_ModelSummary?,
        source: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_ModelSummary {
        guard let existing else {
            return source
        }

        var merged = existing
        if !source.kind.isEmpty {
            merged.kind = source.kind
        }
        if !source.quantProfileID.isEmpty {
            merged.quantProfileID = source.quantProfileID
        }
        if source.maxContext > 0 {
            merged.maxContext = source.maxContext
        }
        if !source.features.isEmpty {
            merged.features = source.features
        }
        if source.capabilityClass != .unspecified {
            merged.capabilityClass = source.capabilityClass
        }
        if source.routeClass != .unspecified {
            merged.routeClass = source.routeClass
        }
        if !source.supportedModalities.isEmpty {
            merged.supportedModalities = source.supportedModalities
        }
        if !source.supportedTasks.isEmpty {
            merged.supportedTasks = source.supportedTasks
        }
        if !source.settings.alias.isEmpty {
            merged.settings.alias = source.settings.alias
        }
        if !source.settings.typeOverride.isEmpty {
            merged.settings.typeOverride = source.settings.typeOverride
        }
        if source.settings.ttlSeconds > 0 {
            merged.settings.ttlSeconds = source.settings.ttlSeconds
        }
        if source.settings.pinOnLoad {
            merged.settings.pinOnLoad = true
        }
        if source.settings.memoryPolicy != .unspecified {
            merged.settings.memoryPolicy = source.settings.memoryPolicy
        }
        if source.settings.defaultAccelerationMode != .unspecified {
            merged.settings.defaultAccelerationMode = source.settings.defaultAccelerationMode
        }
        if !source.settings.accelerationProfileID.isEmpty {
            merged.settings.accelerationProfileID = source.settings.accelerationProfileID
        }
        if !source.settings.adaptiveThinking.mode.isEmpty || source.settings.adaptiveThinking.budgetTokens > 0 {
            merged.settings.adaptiveThinking = source.settings.adaptiveThinking
        }
        if source.settings.diskStreamingMode != .unspecified {
            merged.settings.diskStreamingMode = source.settings.diskStreamingMode
        }
        if source.settings.cacheMode != .unspecified {
            merged.settings.cacheMode = source.settings.cacheMode
        }
        if source.settings.cacheMemoryBudgetBytes > 0 {
            merged.settings.cacheMemoryBudgetBytes = source.settings.cacheMemoryBudgetBytes
        }
        if source.settings.cacheMemoryBudgetPct > 0 {
            merged.settings.cacheMemoryBudgetPct = source.settings.cacheMemoryBudgetPct
        }
        if source.settings.cacheBlockSizeTokens > 0 {
            merged.settings.cacheBlockSizeTokens = source.settings.cacheBlockSizeTokens
        }
        if !source.settings.cacheDirectory.isEmpty {
            merged.settings.cacheDirectory = source.settings.cacheDirectory
        }
        if source.settings.multimodalCacheBudgetBytes > 0 {
            merged.settings.multimodalCacheBudgetBytes = source.settings.multimodalCacheBudgetBytes
        }
        if source.settings.loadTrustMode != .unspecified {
            merged.settings.loadTrustMode = source.settings.loadTrustMode
        }
        merged.settings.ext.merge(source.settings.ext) { _, new in new }
        return merged
    }

    private func synchronized(
        _ source: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_ModelSummary {
        ModelCatalog.withSynchronizedResidency(
            source,
            transitionReason: residencyLedger[source.modelID]?.transitionReason ?? "",
            memoryBudgetEvidence: memoryBudgetEvidence(for: source.modelID)
        )
    }

    private static func withSynchronizedResidency(
        _ source: Melix_Controlplane_V1_ModelSummary,
        transitionReason: String = "",
        memoryBudgetEvidence: MemoryBudgetEvidence = MemoryBudgetEvidence()
    ) -> Melix_Controlplane_V1_ModelSummary {
        var model = source
        model.pinned = effectivePinnedFlag(for: model)
        model.residency = residencySummary(
            for: model,
            transitionReason: transitionReason,
            memoryBudgetEvidence: memoryBudgetEvidence
        )
        return model
    }

    private static func residencySummary(
        for model: Melix_Controlplane_V1_ModelSummary,
        transitionReason: String,
        memoryBudgetEvidence: MemoryBudgetEvidence
    ) -> Melix_Controlplane_V1_ResidencySummary {
        var residency = Melix_Controlplane_V1_ResidencySummary()
        residency.state = residencyState(for: model.state)
        residency.policy = effectivePolicy(for: model.settings)
        residency.pinRequested = model.settings.pinOnLoad
        residency.pinned = model.state == .modelPinned || model.pinned
        residency.ttlSeconds = model.settings.ttlSeconds
        residency.transitionReason = transitionReason
        residency.effectiveDiskStreamingMode = effectiveDiskStreamingMode(for: model)
        residency.memoryBudgetBytes = max(model.settings.memoryBudgetBytes, memoryBudgetEvidence.memoryBudgetBytes)
        residency.memoryHeadroomBytes = memoryBudgetEvidence.memoryHeadroomBytes
        residency.requiredBytes = memoryBudgetEvidence.requiredBytes
        return residency
    }

    private static func effectiveDiskStreamingMode(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_DiskStreamingMode {
        switch model.state {
        case .modelWarm, .modelPinned:
            switch model.settings.diskStreamingMode {
            case .diskStreamingPreferDisk:
                return .diskStreamingPreferDisk
            case .diskStreamingRequireDisk:
                return .diskStreamingRequireDisk
            default:
                return .diskStreamingDisabled
            }
        default:
            return .diskStreamingDisabled
        }
    }

    private static func controlPlaneDiskStreamingMode(
        for mode: Melix_Worker_V1_DiskStreamingMode
    ) -> Melix_Controlplane_V1_DiskStreamingMode {
        switch mode {
        case .diskStreamingDisabled:
            return .diskStreamingDisabled
        case .diskStreamingPreferDisk:
            return .diskStreamingPreferDisk
        case .diskStreamingRequireDisk:
            return .diskStreamingRequireDisk
        default:
            return .diskStreamingDisabled
        }
    }

    private static func effectivePolicy(
        for settings: Melix_Controlplane_V1_ModelSettings
    ) -> Melix_Controlplane_V1_MemoryResidencyPolicy {
        if settings.pinOnLoad {
            return .memoryResidencyPinned
        }
        if settings.memoryPolicy != .unspecified {
            return settings.memoryPolicy
        }
        if settings.ttlSeconds > 0 {
            return .memoryResidencyTtl
        }
        return .memoryResidencyEvictable
    }

    private static func loadState(
        for settings: Melix_Controlplane_V1_ModelSettings
    ) -> Melix_Controlplane_V1_ModelState {
        effectivePolicy(for: settings) == .memoryResidencyPinned ? .modelPinned : .modelWarm
    }

    private static func loadedState(
        for settings: Melix_Controlplane_V1_ModelSettings,
        pinRequested: Bool,
        workerResidency: Melix_Worker_V1_ResidencyInfo?
    ) -> Melix_Controlplane_V1_ModelState {
        guard let workerResidency else {
            if pinRequested {
                return .modelPinned
            }
            return loadState(for: settings)
        }

        switch workerResidency.state {
        case .pinned:
            return .modelPinned
        case .warm:
            return .modelWarm
        case .loading:
            return .modelLoading
        case .evicting:
            return .modelEvicting
        case .unloaded:
            return .modelUnloaded
        case .failed:
            return .modelFailed
        default:
            return loadState(for: settings)
        }
    }

    private static func effectivePinnedFlag(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        switch model.state {
        case .modelPinned:
            return true
        case .modelWarm:
            return model.pinned
        default:
            return false
        }
    }

    private static func residencyState(
        for state: Melix_Controlplane_V1_ModelState
    ) -> Melix_Controlplane_V1_ResidencyState {
        switch state {
        case .modelDiscovered:
            return .discovered
        case .modelLoading:
            return .loading
        case .modelWarm:
            return .warm
        case .modelPinned:
            return .pinned
        case .modelEvicting:
            return .evicting
        case .modelUnloaded:
            return .unloaded
        case .modelFailed:
            return .failed
        default:
            return .unspecified
        }
    }

    private func touchModel(
        id: String,
        transitionReason: String? = nil,
        memoryBudgetEvidence: MemoryBudgetEvidence? = nil,
        clearMemoryBudgetEvidence: Bool = false
    ) {
        nextAccessOrdinal += 1
        var ledger = residencyLedger[id] ?? ResidencyLedger(
            lastAccessOrdinal: 0,
            lastAccessUnixMs: nowUnixMs(),
            transitionReason: "",
            memoryBudgetBytes: models[id]?.settings.memoryBudgetBytes ?? 0,
            memoryHeadroomBytes: 0,
            requiredBytes: 0
        )
        ledger.lastAccessOrdinal = nextAccessOrdinal
        ledger.lastAccessUnixMs = nowUnixMs()
        ledger.memoryBudgetBytes = models[id]?.settings.memoryBudgetBytes ?? ledger.memoryBudgetBytes
        if let transitionReason, !transitionReason.isEmpty {
            ledger.transitionReason = transitionReason
        }
        if clearMemoryBudgetEvidence {
            ledger.memoryBudgetBytes = models[id]?.settings.memoryBudgetBytes ?? ledger.memoryBudgetBytes
            ledger.memoryHeadroomBytes = 0
            ledger.requiredBytes = 0
        }
        if let memoryBudgetEvidence {
            ledger.memoryBudgetBytes = max(
                models[id]?.settings.memoryBudgetBytes ?? 0,
                memoryBudgetEvidence.memoryBudgetBytes
            )
            ledger.memoryHeadroomBytes = memoryBudgetEvidence.memoryHeadroomBytes
            ledger.requiredBytes = memoryBudgetEvidence.requiredBytes
        }
        residencyLedger[id] = ledger
    }

    private func memoryBudgetEvidence(for modelID: String) -> MemoryBudgetEvidence {
        guard let ledger = residencyLedger[modelID] else {
            return MemoryBudgetEvidence()
        }
        return MemoryBudgetEvidence(
            memoryBudgetBytes: ledger.memoryBudgetBytes,
            memoryHeadroomBytes: ledger.memoryHeadroomBytes,
            requiredBytes: ledger.requiredBytes
        )
    }

    private func lastAccessUnixMs(for modelID: String) -> Int64 {
        residencyLedger[modelID]?.lastAccessUnixMs ?? 0
    }

    private func compareRecency(
        _ lhs: Melix_Controlplane_V1_ModelSummary,
        _ rhs: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        let lhsOrdinal = residencyLedger[lhs.modelID]?.lastAccessOrdinal ?? 0
        let rhsOrdinal = residencyLedger[rhs.modelID]?.lastAccessOrdinal ?? 0
        if lhsOrdinal != rhsOrdinal {
            return lhsOrdinal < rhsOrdinal
        }
        return lhs.modelID < rhs.modelID
    }

    private func resolvedLoadTransitionReason(
        explicitReason: String?,
        workerResidency: Melix_Worker_V1_ResidencyInfo?
    ) -> String {
        if let explicitReason, !explicitReason.isEmpty {
            return explicitReason
        }
        if let workerResidency, !workerResidency.transitionReason.isEmpty {
            return workerResidency.transitionReason
        }
        return "load_succeeded"
    }

    private func resolvedUnloadTransitionReason(
        for modelID: String,
        fallback: String?
    ) -> String {
        if let fallback, !fallback.isEmpty {
            return fallback
        }
        if let existing = residencyLedger[modelID]?.transitionReason, !existing.isEmpty {
            return existing
        }
        return "operator_unload"
    }

    private func failedUnloadTransitionReason(
        for modelID: String,
        fallback: String?
    ) -> String {
        let baseReason = resolvedUnloadTransitionReason(for: modelID, fallback: fallback)
        if baseReason.hasSuffix("_failed") {
            return baseReason
        }
        return "\(baseReason)_failed"
    }

    private static func isResident(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        switch model.state {
        case .modelWarm, .modelPinned:
            return true
        default:
            return false
        }
    }

    private static func isPinProtected(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        if model.state == .modelPinned || model.pinned || model.settings.pinOnLoad {
            return true
        }
        return effectivePolicy(for: model.settings) == .memoryResidencyPinned
    }

    private static func isAutomaticallyEvictable(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        isResident(model) && !isPinProtected(model)
    }

    private static func isTTLExpired(
        _ model: Melix_Controlplane_V1_ModelSummary,
        lastAccessUnixMs: Int64,
        nowUnixMs: Int64
    ) -> Bool {
        guard effectivePolicy(for: model.settings) == .memoryResidencyTtl,
              model.settings.ttlSeconds > 0 else {
            return false
        }
        let ttlMilliseconds = Int64(model.settings.ttlSeconds) * 1_000
        return lastAccessUnixMs + ttlMilliseconds <= nowUnixMs
    }

    private static func sameEvictionFamily(
        _ lhs: Melix_Controlplane_V1_ModelSummary,
        _ rhs: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        if lhs.capabilityClass != .unspecified,
           rhs.capabilityClass != .unspecified {
            return lhs.capabilityClass == rhs.capabilityClass
        }
        if lhs.routeClass != .unspecified,
           rhs.routeClass != .unspecified {
            return lhs.routeClass == rhs.routeClass
        }
        return !lhs.kind.isEmpty && lhs.kind == rhs.kind
    }
}

public enum ModelRuntimeAvailability {
    public static let missingRuntimeCacheCode = "model_runtime_missing"
    public static let missingRuntimeCacheMessage = "Hugging Face cache files are missing. Re-download this model to restore it."
    public static let missingRuntimeCacheStatus = "missing-cache"
    public static let readyRuntimeStatus = "ok"
    public static let missingRuntimeCacheBadge = "Missing cache"

    public static func isRuntimeCacheMissing(_ model: Melix_Controlplane_V1_ModelSummary) -> Bool {
        truthy(model.settings.ext["melix.model_path_missing"])
    }

    public static func runtimeStatus(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        isRuntimeCacheMissing(model) ? missingRuntimeCacheStatus : readyRuntimeStatus
    }

    public static func runtimePath(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        trimmed(model.settings.ext["melix.model_path"])
    }

    public static func descriptorPath(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        trimmed(model.settings.ext["melix.registry_descriptor_path"])
    }

    public static func restoreRepoID(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        let ext = model.settings.ext
        let explicitRepoID = trimmed(ext["melix.hf_repo_id"])
        if !explicitRepoID.isEmpty {
            return explicitRepoID
        }
        let sourceKind = trimmed(ext["melix.source_kind"]).lowercased()
        let sourceLocator = trimmed(ext["melix.source_locator"])
        if sourceKind == "hf_repo" || sourceKind == "hub_repo" {
            return sourceLocator
        }
        return model.modelID.contains("/") ? model.modelID : ""
    }

    public static func restoreRevision(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        let ext = model.settings.ext
        let revision = trimmed(ext["melix.hf_revision"])
        if !revision.isEmpty {
            return revision
        }
        let genericRevision = trimmed(ext["melix.revision"])
        return genericRevision.isEmpty ? "main" : genericRevision
    }

    public static func restoreCommand(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        let repoID = restoreRepoID(for: model)
        guard !repoID.isEmpty else {
            return ""
        }
        return "melix model hub download --repo-id \(repoID) --revision \(restoreRevision(for: model))"
    }

    public static func missingRuntimeCacheErrorStatus(
        modelID: String
    ) -> Melix_Controlplane_V1_ErrorStatus {
        var error = Melix_Controlplane_V1_ErrorStatus()
        error.code = missingRuntimeCacheCode
        error.message = missingRuntimeCacheMessage
        error.details = ["model_id": modelID]
        return error
    }

    public static func publicMetadata(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> [String: Any] {
        var payload: [String: Any] = [
            "runtime_status": runtimeStatus(for: model),
            "model_path_missing": isRuntimeCacheMissing(model),
        ]
        let modelPath = runtimePath(for: model)
        if !modelPath.isEmpty {
            payload["model_path"] = modelPath
        }
        let descriptorPath = descriptorPath(for: model)
        if !descriptorPath.isEmpty {
            payload["registry_descriptor_path"] = descriptorPath
        }
        let restoreCommand = restoreCommand(for: model)
        if !restoreCommand.isEmpty {
            payload["restore_command"] = restoreCommand
        }
        return payload
    }

    private static func truthy(_ value: String?) -> Bool {
        switch trimmed(value).lowercased() {
        case "true", "1", "yes", "on":
            return true
        default:
            return false
        }
    }

    private static func trimmed(_ value: String?) -> String {
        (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
