import Foundation
import MelixControlPlaneProtocol

public enum ServingDefaultsValidationError: Error, Equatable, Sendable {
    case missingServerSessionID
    case invalidTemperature
    case invalidTopP
    case invalidMaxTokens
    case invalidStreamIntervalTokens
    case invalidMaxConcurrentRequests
    case invalidPrefillBatchSize
    case invalidCompletionBatchSize
    case invalidAccelerationProfile
    case invalidAccelerationMode
    case invalidRoutePolicy
    case unsupportedMultimodalRoutePolicy
    case missingDraftModelID
    case invalidNumDraftTokens
    case speculativeServedModelUnsupported
    case speculativeDraftModelUnsupported
    case speculativeBackendUnsupported

    public var code: String {
        switch self {
        case .missingServerSessionID:
            return "missing_server_session_id"
        case .invalidTemperature:
            return "invalid_temperature"
        case .invalidTopP:
            return "invalid_top_p"
        case .invalidMaxTokens:
            return "invalid_max_tokens"
        case .invalidStreamIntervalTokens:
            return "invalid_stream_interval_tokens"
        case .invalidMaxConcurrentRequests:
            return "invalid_max_concurrent_requests"
        case .invalidPrefillBatchSize:
            return "invalid_prefill_batch_size"
        case .invalidCompletionBatchSize:
            return "invalid_completion_batch_size"
        case .invalidAccelerationProfile:
            return "invalid_acceleration_profile"
        case .invalidAccelerationMode:
            return "invalid_acceleration_mode"
        case .invalidRoutePolicy:
            return "invalid_route_policy"
        case .unsupportedMultimodalRoutePolicy:
            return "unsupported_multimodal_route_policy"
        case .missingDraftModelID:
            return "missing_draft_model_id"
        case .invalidNumDraftTokens:
            return "invalid_num_draft_tokens"
        case .speculativeServedModelUnsupported:
            return "speculative_served_model_unsupported"
        case .speculativeDraftModelUnsupported:
            return "speculative_draft_model_unsupported"
        case .speculativeBackendUnsupported:
            return "speculative_backend_unsupported"
        }
    }

    public var message: String {
        switch self {
        case .missingServerSessionID:
            return "Serving defaults require a server session identifier."
        case .invalidTemperature:
            return "Serving defaults require a non-negative temperature."
        case .invalidTopP:
            return "Serving defaults require top_p to be greater than 0 and at most 1."
        case .invalidMaxTokens:
            return "Serving defaults require a positive max_tokens value."
        case .invalidStreamIntervalTokens:
            return "Serving defaults require a positive stream interval token count."
        case .invalidMaxConcurrentRequests:
            return "Serving defaults require a positive max concurrent request count."
        case .invalidPrefillBatchSize:
            return "Serving defaults require a positive prefill batch size."
        case .invalidCompletionBatchSize:
            return "Serving defaults require a positive completion batch size."
        case .invalidAccelerationProfile:
            return "Serving defaults only support acceleration profiles: \(ServingAccelerationProfiles.allowedProfileList)."
        case .invalidAccelerationMode:
            return "Serving defaults only support baseline or speculative decode acceleration."
        case .invalidRoutePolicy:
            return "Serving defaults route policies only support auto, off, or force."
        case .unsupportedMultimodalRoutePolicy:
            return "Forced multimodal routing is disabled because the active route is not a native multimodal route."
        case .missingDraftModelID:
            return "Speculative serving defaults require a draft model identifier."
        case .invalidNumDraftTokens:
            return "Speculative serving defaults require a positive num_draft_tokens value."
        case .speculativeServedModelUnsupported:
            return "The served model does not support speculative serving defaults."
        case .speculativeDraftModelUnsupported:
            return "The draft model does not support speculative serving defaults."
        case .speculativeBackendUnsupported:
            return "Speculative serving defaults are not supported by the active Swift text backend."
        }
    }
}

public struct GatewayServingDefaultsPolicy: Sendable, Equatable {
    public let temperature: Double?
    public let topP: Double?
    public let maxTokens: UInt32?
    public let streamIntervalTokens: UInt32?
    public let maxConcurrentRequests: UInt32?
    public let concurrentProcessingEnabled: Bool?
    public let prefillBatchSize: UInt32?
    public let completionBatchSize: UInt32?
    public let accelerationMode: Melix_Controlplane_V1_AccelerationMode?
    public let draftModelID: String?
    public let numDraftTokens: UInt32?
    public let accelerationProfile: String?
    public let multimodalRoutePolicy: String
    public let speculativeRoutePolicy: String
    public let overrideReceiptExt: [String: String]

    public init(
        temperature: Double?,
        topP: Double?,
        maxTokens: UInt32?,
        streamIntervalTokens: UInt32?,
        maxConcurrentRequests: UInt32?,
        concurrentProcessingEnabled: Bool? = nil,
        prefillBatchSize: UInt32? = nil,
        completionBatchSize: UInt32? = nil,
        accelerationMode: Melix_Controlplane_V1_AccelerationMode? = nil,
        draftModelID: String? = nil,
        numDraftTokens: UInt32? = nil,
        accelerationProfile: String? = nil,
        multimodalRoutePolicy: String = "auto",
        speculativeRoutePolicy: String = "auto",
        overrideReceiptExt: [String: String] = [:]
    ) {
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.streamIntervalTokens = streamIntervalTokens
        self.maxConcurrentRequests = maxConcurrentRequests
        self.concurrentProcessingEnabled = concurrentProcessingEnabled
        self.prefillBatchSize = prefillBatchSize
        self.completionBatchSize = completionBatchSize
        self.accelerationMode = accelerationMode
        self.draftModelID = draftModelID
        self.numDraftTokens = numDraftTokens
        self.accelerationProfile = accelerationProfile
        self.multimodalRoutePolicy = Self.normalizedRoutePolicy(multimodalRoutePolicy)
        self.speculativeRoutePolicy = Self.normalizedRoutePolicy(speculativeRoutePolicy)
        self.overrideReceiptExt = overrideReceiptExt
    }

    public func resolvingAccelerationCompatibility(
        for model: Melix_Controlplane_V1_ModelSummary?
    ) -> GatewayServingDefaultsPolicy {
        let effectiveBatchingDefaults = Self.effectiveBatchingDefaults(
            concurrentProcessingEnabled: concurrentProcessingEnabled ?? true,
            maxConcurrentRequests: maxConcurrentRequests ?? 4,
            prefillBatchSize: prefillBatchSize ?? 2,
            completionBatchSize: completionBatchSize ?? 2
        )
        var effectivePolicy = GatewayServingDefaultsPolicy(
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            streamIntervalTokens: streamIntervalTokens,
            maxConcurrentRequests: effectiveBatchingDefaults.maxConcurrentRequests,
            concurrentProcessingEnabled: effectiveBatchingDefaults.concurrentProcessingEnabled,
            prefillBatchSize: effectiveBatchingDefaults.prefillBatchSize,
            completionBatchSize: effectiveBatchingDefaults.completionBatchSize,
            accelerationMode: accelerationMode,
            draftModelID: draftModelID,
            numDraftTokens: numDraftTokens,
            accelerationProfile: accelerationProfile,
            multimodalRoutePolicy: multimodalRoutePolicy,
            speculativeRoutePolicy: speculativeRoutePolicy
        )
        var suppressedOverrides = Self.suppressedBatchingOverrides(
            requestedMaxConcurrentRequests: maxConcurrentRequests,
            requestedPrefillBatchSize: prefillBatchSize,
            requestedCompletionBatchSize: completionBatchSize,
            effectiveMaxConcurrentRequests: effectiveBatchingDefaults.maxConcurrentRequests,
            effectivePrefillBatchSize: effectiveBatchingDefaults.prefillBatchSize,
            effectiveCompletionBatchSize: effectiveBatchingDefaults.completionBatchSize
        )
        var receiptExt: [String: String] = [
            "melix.gateway.override_receipt_schema": "melix.gateway_override_receipt.v1",
            "melix.gateway.multimodal_route_policy": multimodalRoutePolicy,
            "melix.gateway.effective_multimodal_route": Self.effectiveMultimodalRoute(
                for: model,
                routePolicy: multimodalRoutePolicy
            ),
            "melix.gateway.speculative_route_policy": speculativeRoutePolicy,
            "melix.gateway.effective_speculative_mode": Self.accelerationModeIdentifier(
                effectivePolicy.accelerationMode ?? .baseline
            ),
            "melix.gateway.cache_quantization.disabled_reason": "not_configurable",
            "melix.gateway.paged_cache.disabled_reason": "not_configurable",
        ]

        if accelerationMode == .speculativeDecode,
           (speculativeRoutePolicy == "off" || !Self.modelSupportsSpeculativeDefaults(model)) {
            effectivePolicy = GatewayServingDefaultsPolicy(
                temperature: temperature,
                topP: topP,
                maxTokens: maxTokens,
                streamIntervalTokens: streamIntervalTokens,
                maxConcurrentRequests: effectiveBatchingDefaults.maxConcurrentRequests,
                concurrentProcessingEnabled: effectiveBatchingDefaults.concurrentProcessingEnabled,
                prefillBatchSize: effectiveBatchingDefaults.prefillBatchSize,
                completionBatchSize: effectiveBatchingDefaults.completionBatchSize,
                accelerationMode: .baseline,
                draftModelID: "",
                numDraftTokens: 0,
                accelerationProfile: accelerationProfile,
                multimodalRoutePolicy: multimodalRoutePolicy,
                speculativeRoutePolicy: speculativeRoutePolicy
            )
            suppressedOverrides.append("speculative_decode")
            receiptExt["melix.gateway.effective_speculative_mode"] = "baseline"
            receiptExt["melix.gateway.speculative.disabled_reason"] = speculativeRoutePolicy == "off"
                ? "operator_disabled"
                : "unsupported_route"
        }
        if !suppressedOverrides.isEmpty {
            receiptExt["melix.gateway.suppressed_overrides"] = suppressedOverrides.joined(separator: ",")
        }
        receiptExt["melix.gateway.batch.disabled_reason"] = suppressedOverrides.contains { $0.hasSuffix("batch_size") || $0 == "max_concurrent_requests" }
            ? "incompatible_batch_size"
            : "none"

        return GatewayServingDefaultsPolicy(
            temperature: effectivePolicy.temperature,
            topP: effectivePolicy.topP,
            maxTokens: effectivePolicy.maxTokens,
            streamIntervalTokens: effectivePolicy.streamIntervalTokens,
            maxConcurrentRequests: effectivePolicy.maxConcurrentRequests,
            concurrentProcessingEnabled: effectivePolicy.concurrentProcessingEnabled,
            prefillBatchSize: effectivePolicy.prefillBatchSize,
            completionBatchSize: effectivePolicy.completionBatchSize,
            accelerationMode: effectivePolicy.accelerationMode,
            draftModelID: effectivePolicy.draftModelID,
            numDraftTokens: effectivePolicy.numDraftTokens,
            accelerationProfile: effectivePolicy.accelerationProfile,
            multimodalRoutePolicy: effectivePolicy.multimodalRoutePolicy,
            speculativeRoutePolicy: effectivePolicy.speculativeRoutePolicy,
            overrideReceiptExt: receiptExt
        )
    }

    private static func modelSupportsSpeculativeDefaults(
        _ model: Melix_Controlplane_V1_ModelSummary?
    ) -> Bool {
        guard let model else {
            return false
        }
        return model.capabilityClass == .modelCapabilityText && model.routeClass == .workerRouteSwiftText
    }

    private static func effectiveBatchingDefaults(
        concurrentProcessingEnabled: Bool,
        maxConcurrentRequests: UInt32,
        prefillBatchSize: UInt32,
        completionBatchSize: UInt32
    ) -> (
        concurrentProcessingEnabled: Bool,
        maxConcurrentRequests: UInt32,
        prefillBatchSize: UInt32,
        completionBatchSize: UInt32
    ) {
        guard concurrentProcessingEnabled else {
            return (false, 1, 1, 1)
        }
        // The effective batch width is bounded by the smallest requested lane.
        let effectiveBatchCapacity = min(
            max(maxConcurrentRequests, 1),
            max(prefillBatchSize, 1),
            max(completionBatchSize, 1)
        )
        guard effectiveBatchCapacity > 1 else {
            return (false, 1, 1, 1)
        }
        return (true, effectiveBatchCapacity, effectiveBatchCapacity, effectiveBatchCapacity)
    }

    private static func suppressedBatchingOverrides(
        requestedMaxConcurrentRequests: UInt32?,
        requestedPrefillBatchSize: UInt32?,
        requestedCompletionBatchSize: UInt32?,
        effectiveMaxConcurrentRequests: UInt32,
        effectivePrefillBatchSize: UInt32,
        effectiveCompletionBatchSize: UInt32
    ) -> [String] {
        var suppressed: [String] = []
        if let requestedMaxConcurrentRequests,
           requestedMaxConcurrentRequests != effectiveMaxConcurrentRequests {
            suppressed.append("max_concurrent_requests")
        }
        if let requestedPrefillBatchSize,
           requestedPrefillBatchSize != effectivePrefillBatchSize {
            suppressed.append("prefill_batch_size")
        }
        if let requestedCompletionBatchSize,
           requestedCompletionBatchSize != effectiveCompletionBatchSize {
            suppressed.append("completion_batch_size")
        }
        return suppressed
    }

    private static func effectiveMultimodalRoute(
        for model: Melix_Controlplane_V1_ModelSummary?,
        routePolicy: String
    ) -> String {
        if routePolicy == "off" {
            return "off"
        }
        guard let model else {
            return "swift_text"
        }
        if let routeKind = WorkerRouteKind(routeClass: model.routeClass) {
            return routeKind.metadataIdentifier
        }
        switch model.capabilityClass {
        case .modelCapabilityVlm:
            return WorkerRouteKind.pythonVLM.metadataIdentifier
        case .modelCapabilityOcr:
            return WorkerRouteKind.pythonOCR.metadataIdentifier
        default:
            return WorkerRouteKind.swiftText.metadataIdentifier
        }
    }

    private static func accelerationModeIdentifier(
        _ mode: Melix_Controlplane_V1_AccelerationMode
    ) -> String {
        switch mode {
        case .speculativeDecode:
            return "speculative_decode"
        default:
            return "baseline"
        }
    }

    private static func normalizedRoutePolicy(_ rawValue: String) -> String {
        let normalized = rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized.isEmpty ? "auto" : normalized
    }
}

private struct GatewayServingDefaultsResolvedDefaults: Equatable, Sendable {
    let temperature: Double
    let topP: Double
    let maxTokens: UInt32
    let streamIntervalTokens: UInt32
    let maxConcurrentRequests: UInt32
    let concurrentProcessingEnabled: Bool
    let prefillBatchSize: UInt32
    let completionBatchSize: UInt32
    let accelerationMode: Melix_Controlplane_V1_AccelerationMode
    let draftModelID: String
    let numDraftTokens: UInt32
    let accelerationProfile: String
    let multimodalRoutePolicy: String
    let speculativeRoutePolicy: String
    let source: Melix_Controlplane_V1_ServingDefaultsSource
}

private struct PersistedServingDefaultsRecord: Codable, Equatable, Sendable {
    let serverSessionID: String
    let temperature: Double
    let topP: Double
    let maxTokens: UInt32
    let streamIntervalTokens: UInt32
    let maxConcurrentRequests: UInt32
    let concurrentProcessingEnabled: Bool
    let prefillBatchSize: UInt32
    let completionBatchSize: UInt32
    let accelerationModeRawValue: Int
    let draftModelID: String
    let numDraftTokens: UInt32
    let accelerationProfile: String
    let multimodalRoutePolicy: String
    let speculativeRoutePolicy: String
    let sourceRawValue: Int
    let updatedAtUnixMS: Int64

    enum CodingKeys: String, CodingKey {
        case serverSessionID = "server_session_id"
        case temperature
        case topP = "top_p"
        case maxTokens = "max_tokens"
        case streamIntervalTokens = "stream_interval_tokens"
        case maxConcurrentRequests = "max_concurrent_requests"
        case concurrentProcessingEnabled = "concurrent_processing_enabled"
        case prefillBatchSize = "prefill_batch_size"
        case completionBatchSize = "completion_batch_size"
        case accelerationModeRawValue = "acceleration_mode"
        case draftModelID = "draft_model_id"
        case numDraftTokens = "num_draft_tokens"
        case accelerationProfile = "acceleration_profile"
        case multimodalRoutePolicy = "multimodal_route_policy"
        case speculativeRoutePolicy = "speculative_route_policy"
        case sourceRawValue = "source"
        case updatedAtUnixMS = "updated_at_unix_ms"
    }

    init(
        serverSessionID: String,
        temperature: Double,
        topP: Double,
        maxTokens: UInt32,
        streamIntervalTokens: UInt32,
        maxConcurrentRequests: UInt32,
        concurrentProcessingEnabled: Bool,
        prefillBatchSize: UInt32,
        completionBatchSize: UInt32,
        accelerationModeRawValue: Int,
        draftModelID: String,
        numDraftTokens: UInt32,
        accelerationProfile: String,
        multimodalRoutePolicy: String,
        speculativeRoutePolicy: String,
        sourceRawValue: Int,
        updatedAtUnixMS: Int64
    ) {
        self.serverSessionID = serverSessionID
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.streamIntervalTokens = streamIntervalTokens
        self.maxConcurrentRequests = maxConcurrentRequests
        self.concurrentProcessingEnabled = concurrentProcessingEnabled
        self.prefillBatchSize = prefillBatchSize
        self.completionBatchSize = completionBatchSize
        self.accelerationModeRawValue = accelerationModeRawValue
        self.draftModelID = draftModelID
        self.numDraftTokens = numDraftTokens
        self.accelerationProfile = accelerationProfile
        self.multimodalRoutePolicy = multimodalRoutePolicy
        self.speculativeRoutePolicy = speculativeRoutePolicy
        self.sourceRawValue = sourceRawValue
        self.updatedAtUnixMS = updatedAtUnixMS
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.init(
            serverSessionID: try container.decode(String.self, forKey: .serverSessionID),
            temperature: try container.decode(Double.self, forKey: .temperature),
            topP: try container.decode(Double.self, forKey: .topP),
            maxTokens: try container.decode(UInt32.self, forKey: .maxTokens),
            streamIntervalTokens: try container.decode(UInt32.self, forKey: .streamIntervalTokens),
            maxConcurrentRequests: try container.decode(UInt32.self, forKey: .maxConcurrentRequests),
            concurrentProcessingEnabled: try container.decode(Bool.self, forKey: .concurrentProcessingEnabled),
            prefillBatchSize: try container.decode(UInt32.self, forKey: .prefillBatchSize),
            completionBatchSize: try container.decode(UInt32.self, forKey: .completionBatchSize),
            accelerationModeRawValue: try container.decode(Int.self, forKey: .accelerationModeRawValue),
            draftModelID: try container.decode(String.self, forKey: .draftModelID),
            numDraftTokens: try container.decode(UInt32.self, forKey: .numDraftTokens),
            accelerationProfile: try container.decode(String.self, forKey: .accelerationProfile),
            multimodalRoutePolicy: try container.decodeIfPresent(
                String.self,
                forKey: .multimodalRoutePolicy
            ) ?? "auto",
            speculativeRoutePolicy: try container.decodeIfPresent(
                String.self,
                forKey: .speculativeRoutePolicy
            ) ?? "auto",
            sourceRawValue: try container.decode(Int.self, forKey: .sourceRawValue),
            updatedAtUnixMS: try container.decode(Int64.self, forKey: .updatedAtUnixMS)
        )
    }

    var accelerationMode: Melix_Controlplane_V1_AccelerationMode {
        Melix_Controlplane_V1_AccelerationMode(rawValue: accelerationModeRawValue) ?? .baseline
    }

    var source: Melix_Controlplane_V1_ServingDefaultsSource {
        Melix_Controlplane_V1_ServingDefaultsSource(rawValue: sourceRawValue) ?? .operatorOverride
    }
}

private struct GatewayServingDefaultsDocument: Codable, Equatable, Sendable {
    let schemaVersion: Int
    let sessions: [PersistedServingDefaultsRecord]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case sessions
    }
}

public actor GatewayServingDefaultsStore {
    internal static let defaultMaxTokens: UInt32 = 32_768

    private let storeURL: URL
    private let fileManager: FileManager
    private let nowUnixMS: @Sendable () -> Int64
    private let defaults: GatewayServingDefaultsResolvedDefaults
    private var recordsByServerSessionID: [String: PersistedServingDefaultsRecord]

    public init(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        nowUnixMS: @escaping @Sendable () -> Int64 = { Int64(Date().timeIntervalSince1970 * 1000) }
    ) {
        self.fileManager = fileManager
        self.nowUnixMS = nowUnixMS
        self.storeURL = Self.resolveStoreURL(environment: environment)
        self.defaults = Self.resolveDefaults(environment: environment)
        self.recordsByServerSessionID = Self.loadRecords(from: storeURL, fileManager: fileManager)
    }

    public init(
        storeURL: URL,
        defaults: [String: String],
        fileManager: FileManager = .default,
        nowUnixMS: @escaping @Sendable () -> Int64 = { Int64(Date().timeIntervalSince1970 * 1000) }
    ) {
        self.fileManager = fileManager
        self.nowUnixMS = nowUnixMS
        self.storeURL = storeURL
        self.defaults = Self.resolveDefaults(environment: defaults)
        self.recordsByServerSessionID = Self.loadRecords(from: storeURL, fileManager: fileManager)
    }

    public func requestedDefaults(
        serverSessionID: String = ServerSessionRuntimeStore.defaultServerSessionID
    ) -> GatewayServingDefaultsPolicy {
        let resolvedServerSessionID = Self.trimmed(serverSessionID).isEmpty
            ? ServerSessionRuntimeStore.defaultServerSessionID
            : Self.trimmed(serverSessionID)
        let record = recordsByServerSessionID[resolvedServerSessionID]
        return GatewayServingDefaultsPolicy(
            temperature: record?.temperature ?? defaults.temperature,
            topP: record?.topP ?? defaults.topP,
            maxTokens: record?.maxTokens ?? defaults.maxTokens,
            streamIntervalTokens: record?.streamIntervalTokens ?? defaults.streamIntervalTokens,
            maxConcurrentRequests: record?.maxConcurrentRequests ?? defaults.maxConcurrentRequests,
            concurrentProcessingEnabled: record?.concurrentProcessingEnabled ?? defaults.concurrentProcessingEnabled,
            prefillBatchSize: record?.prefillBatchSize ?? defaults.prefillBatchSize,
            completionBatchSize: record?.completionBatchSize ?? defaults.completionBatchSize,
            accelerationMode: record?.accelerationMode ?? defaults.accelerationMode,
            draftModelID: record?.draftModelID ?? defaults.draftModelID,
            numDraftTokens: record?.numDraftTokens ?? defaults.numDraftTokens,
            accelerationProfile: record?.accelerationProfile ?? defaults.accelerationProfile,
            multimodalRoutePolicy: record?.multimodalRoutePolicy ?? defaults.multimodalRoutePolicy,
            speculativeRoutePolicy: record?.speculativeRoutePolicy ?? defaults.speculativeRoutePolicy
        )
    }

    public func storePath() -> String {
        storeURL.path
    }

    func apply(
        command: Melix_Controlplane_V1_ApplyServingDefaults
    ) throws {
        let serverSessionID = Self.trimmed(command.serverSessionID)
        guard !serverSessionID.isEmpty else {
            throw ServingDefaultsValidationError.missingServerSessionID
        }
        guard command.temperature.isFinite, command.temperature >= 0 else {
            throw ServingDefaultsValidationError.invalidTemperature
        }
        guard command.topP > 0, command.topP <= 1 else {
            throw ServingDefaultsValidationError.invalidTopP
        }
        guard command.maxTokens > 0 else {
            throw ServingDefaultsValidationError.invalidMaxTokens
        }
        guard command.streamIntervalTokens > 0 else {
            throw ServingDefaultsValidationError.invalidStreamIntervalTokens
        }
        guard command.maxConcurrentRequests > 0 else {
            throw ServingDefaultsValidationError.invalidMaxConcurrentRequests
        }
        guard command.prefillBatchSize > 0 else {
            throw ServingDefaultsValidationError.invalidPrefillBatchSize
        }
        guard command.completionBatchSize > 0 else {
            throw ServingDefaultsValidationError.invalidCompletionBatchSize
        }
        guard Self.isKnownProfileID(command.accelerationProfile) else {
            throw ServingDefaultsValidationError.invalidAccelerationProfile
        }
        let multimodalRoutePolicy = Self.normalizedRoutePolicy(command.multimodalRoutePolicy)
        let speculativeRoutePolicy = Self.normalizedRoutePolicy(command.speculativeRoutePolicy)
        guard Self.isKnownRoutePolicy(multimodalRoutePolicy),
              Self.isKnownRoutePolicy(speculativeRoutePolicy)
        else {
            throw ServingDefaultsValidationError.invalidRoutePolicy
        }

        let record = PersistedServingDefaultsRecord(
            serverSessionID: serverSessionID,
            temperature: command.temperature,
            topP: command.topP,
            maxTokens: command.maxTokens,
            streamIntervalTokens: command.streamIntervalTokens,
            maxConcurrentRequests: command.maxConcurrentRequests,
            concurrentProcessingEnabled: command.concurrentProcessingEnabled,
            prefillBatchSize: command.prefillBatchSize,
            completionBatchSize: command.completionBatchSize,
            accelerationModeRawValue: command.accelerationMode.rawValue,
            draftModelID: Self.trimmed(command.draftModelID),
            numDraftTokens: command.numDraftTokens,
            accelerationProfile: Self.normalizedProfileID(command.accelerationProfile),
            multimodalRoutePolicy: multimodalRoutePolicy,
            speculativeRoutePolicy: speculativeRoutePolicy,
            sourceRawValue: Melix_Controlplane_V1_ServingDefaultsSource.operatorOverride.rawValue,
            updatedAtUnixMS: nowUnixMS()
        )
        recordsByServerSessionID[serverSessionID] = record
        try writeRecords()
    }

    public func summary(
        serverSessionIDs: [String],
        defaultModelIDs: [String: String],
        modelSettingsByModelID: [String: Melix_Controlplane_V1_ModelSettings]
    ) -> Melix_Controlplane_V1_ServingDefaultsSummary {
        var summary = Melix_Controlplane_V1_ServingDefaultsSummary()
        let allServerSessionIDs = Set(
            serverSessionIDs.map(Self.trimmed).filter { !$0.isEmpty }
            + recordsByServerSessionID.keys
            + defaultModelIDs.keys
        )

        summary.sessions = allServerSessionIDs.sorted().map { serverSessionID in
            let record = recordsByServerSessionID[serverSessionID]
            let requestedTemperature = record?.temperature ?? defaults.temperature
            let requestedTopP = record?.topP ?? defaults.topP
            let requestedMaxTokens = record?.maxTokens ?? defaults.maxTokens
            let requestedStreamIntervalTokens = record?.streamIntervalTokens ?? defaults.streamIntervalTokens
            let requestedMaxConcurrentRequests = record?.maxConcurrentRequests ?? defaults.maxConcurrentRequests
            let requestedConcurrentProcessingEnabled = record?.concurrentProcessingEnabled ?? defaults.concurrentProcessingEnabled
            let requestedPrefillBatchSize = record?.prefillBatchSize ?? defaults.prefillBatchSize
            let requestedCompletionBatchSize = record?.completionBatchSize ?? defaults.completionBatchSize
            let requestedAccelerationMode = record?.accelerationMode ?? defaults.accelerationMode
            let requestedDraftModelID = record?.draftModelID ?? defaults.draftModelID
            let requestedNumDraftTokens = record?.numDraftTokens ?? defaults.numDraftTokens
            let requestedAccelerationProfile = record?.accelerationProfile ?? defaults.accelerationProfile
            let requestedMultimodalRoutePolicy = record?.multimodalRoutePolicy ?? defaults.multimodalRoutePolicy
            let requestedSpeculativeRoutePolicy = record?.speculativeRoutePolicy ?? defaults.speculativeRoutePolicy
            let defaultModelID = Self.trimmed(defaultModelIDs[serverSessionID] ?? "")
            let modelSamplingPolicy = modelSettingsByModelID[defaultModelID].flatMap(ModelSamplingPolicy.init)
            let modelSettings = modelSettingsByModelID[defaultModelID]
            let effectiveBatchingDefaults = Self.effectiveBatchingDefaults(
                concurrentProcessingEnabled: requestedConcurrentProcessingEnabled,
                maxConcurrentRequests: requestedMaxConcurrentRequests,
                prefillBatchSize: requestedPrefillBatchSize,
                completionBatchSize: requestedCompletionBatchSize
            )
            let effectiveSpeculativeDefaults = Self.effectiveSpeculativeDefaults(
                requestedAccelerationProfile: requestedAccelerationProfile,
                requestedAccelerationMode: requestedAccelerationMode,
                requestedDraftModelID: requestedDraftModelID,
                requestedNumDraftTokens: requestedNumDraftTokens,
                modelSettings: modelSettings,
                speculativeRoutePolicy: requestedSpeculativeRoutePolicy
            )
            let effectiveMultimodalRoute = Self.effectiveMultimodalRoute(
                for: modelSettings,
                routePolicy: requestedMultimodalRoutePolicy
            )
            let overrideReceiptExt = Self.overrideReceiptExt(
                requestedMaxConcurrentRequests: requestedMaxConcurrentRequests,
                requestedPrefillBatchSize: requestedPrefillBatchSize,
                requestedCompletionBatchSize: requestedCompletionBatchSize,
                effectiveMaxConcurrentRequests: effectiveBatchingDefaults.maxConcurrentRequests,
                effectivePrefillBatchSize: effectiveBatchingDefaults.prefillBatchSize,
                effectiveCompletionBatchSize: effectiveBatchingDefaults.completionBatchSize,
                requestedAccelerationMode: requestedAccelerationMode,
                effectiveAccelerationMode: effectiveSpeculativeDefaults.accelerationMode,
                multimodalRoutePolicy: requestedMultimodalRoutePolicy,
                effectiveMultimodalRoute: effectiveMultimodalRoute,
                speculativeRoutePolicy: requestedSpeculativeRoutePolicy
            )

            var session = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
            session.serverSessionID = serverSessionID
            session.defaultModelID = defaultModelID
            session.requestedTemperature = requestedTemperature
            session.requestedTopP = requestedTopP
            session.requestedMaxTokens = requestedMaxTokens
            session.requestedStreamIntervalTokens = requestedStreamIntervalTokens
            session.requestedMaxConcurrentRequests = requestedMaxConcurrentRequests
            session.requestedConcurrentProcessingEnabled = requestedConcurrentProcessingEnabled
            session.requestedPrefillBatchSize = requestedPrefillBatchSize
            session.requestedCompletionBatchSize = requestedCompletionBatchSize
            session.requestedAccelerationMode = requestedAccelerationMode
            session.requestedDraftModelID = requestedDraftModelID
            session.requestedNumDraftTokens = requestedNumDraftTokens
            session.requestedAccelerationProfile = requestedAccelerationProfile
            session.effectiveTemperature = modelSamplingPolicy?.temperature ?? requestedTemperature
            session.effectiveTopP = modelSamplingPolicy?.topP ?? requestedTopP
            session.effectiveMaxTokens = modelSamplingPolicy?.maxTokens ?? requestedMaxTokens
            session.effectiveStreamIntervalTokens = requestedStreamIntervalTokens
            session.effectiveMaxConcurrentRequests = effectiveBatchingDefaults.maxConcurrentRequests
            session.effectiveConcurrentProcessingEnabled = effectiveBatchingDefaults.concurrentProcessingEnabled
            session.effectivePrefillBatchSize = effectiveBatchingDefaults.prefillBatchSize
            session.effectiveCompletionBatchSize = effectiveBatchingDefaults.completionBatchSize
            session.effectiveAccelerationMode = effectiveSpeculativeDefaults.accelerationMode
            session.effectiveDraftModelID = effectiveSpeculativeDefaults.draftModelID
            session.effectiveNumDraftTokens = effectiveSpeculativeDefaults.numDraftTokens
            session.effectiveAccelerationProfile = effectiveSpeculativeDefaults.accelerationProfile
            session.accelerationProfileIntent = ServingAccelerationProfiles
                .profile(id: effectiveSpeculativeDefaults.accelerationProfile)
                .intent
            session.overrideReceiptSchema = overrideReceiptExt[
                "melix.gateway.override_receipt_schema"
            ] ?? ""
            session.suppressedOverrides = overrideReceiptExt[
                "melix.gateway.suppressed_overrides"
            ] ?? ""
            session.batchDisabledReason = overrideReceiptExt[
                "melix.gateway.batch.disabled_reason"
            ] ?? "none"
            session.speculativeDisabledReason = overrideReceiptExt[
                "melix.gateway.speculative.disabled_reason"
            ] ?? ""
            session.multimodalRoutePolicy = overrideReceiptExt[
                "melix.gateway.multimodal_route_policy"
            ] ?? "auto"
            session.effectiveMultimodalRoute = overrideReceiptExt[
                "melix.gateway.effective_multimodal_route"
            ] ?? "swift_text"
            session.speculativeRoutePolicy = overrideReceiptExt[
                "melix.gateway.speculative_route_policy"
            ] ?? "auto"
            session.effectiveSpeculativeMode = overrideReceiptExt[
                "melix.gateway.effective_speculative_mode"
            ] ?? "baseline"
            session.cacheQuantizationDisabledReason = overrideReceiptExt[
                "melix.gateway.cache_quantization.disabled_reason"
            ] ?? "not_configurable"
            session.pagedCacheDisabledReason = overrideReceiptExt[
                "melix.gateway.paged_cache.disabled_reason"
            ] ?? "not_configurable"
            session.source = record?.source ?? defaults.source
            session.modelOverrideApplied = modelSamplingPolicy != nil || effectiveSpeculativeDefaults.modelOverrideApplied
            session.updatedAtUnixMs = record?.updatedAtUnixMS ?? 0
            return session
        }
        return summary
    }

    private func writeRecords() throws {
        let document = GatewayServingDefaultsDocument(
            schemaVersion: 1,
            sessions: recordsByServerSessionID.values.sorted { lhs, rhs in
                lhs.serverSessionID < rhs.serverSessionID
            }
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(document)
        try fileManager.createDirectory(
            at: storeURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: storeURL, options: .atomic)
    }

    private static func loadRecords(
        from storeURL: URL,
        fileManager: FileManager
    ) -> [String: PersistedServingDefaultsRecord] {
        guard fileManager.fileExists(atPath: storeURL.path) else {
            return [:]
        }
        guard
            let data = try? Data(contentsOf: storeURL),
            let document = try? JSONDecoder().decode(GatewayServingDefaultsDocument.self, from: data)
        else {
            return [:]
        }
        return Dictionary(uniqueKeysWithValues: document.sessions.map { ($0.serverSessionID, $0) })
    }

    private static func resolveStoreURL(
        environment: [String: String]
    ) -> URL {
        if let override = environment["MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH"]?.nilIfEmpty {
            return URL(fileURLWithPath: override)
        }
        return MelixPathLayout(environment: environment).gatewayServingDefaultsStoreURL
    }

    private static func resolveDefaults(
        environment: [String: String]
    ) -> GatewayServingDefaultsResolvedDefaults {
        let accelerationProfile = normalizedProfileID(environment["MELIX_GATEWAY_ACCELERATION_PROFILE"])
        let profileDefaults = ServingAccelerationProfiles.profile(id: accelerationProfile)
        let temperature = parseDouble(
            environment["MELIX_GATEWAY_DEFAULT_TEMPERATURE"],
            fallback: 0.7
        )
        let topP = parseDouble(
            environment["MELIX_GATEWAY_DEFAULT_TOP_P"],
            fallback: 1.0
        )
        let maxTokens = parseUInt32(
            environment["MELIX_GATEWAY_DEFAULT_MAX_TOKENS"],
            fallback: Self.defaultMaxTokens
        )
        let streamIntervalTokens = parseUInt32(
            environment["MELIX_GATEWAY_STREAM_INTERVAL_TOKENS"],
            fallback: 1
        )
        let maxConcurrentSequencesOverride = environment["MELIX_GATEWAY_MAX_CONCURRENT_SEQUENCES"]
        let maxConcurrentRequests = parseUInt32(
            maxConcurrentSequencesOverride ?? environment["MELIX_GATEWAY_MAX_CONCURRENT_REQUESTS"],
            fallback: profileDefaults.maxConcurrentRequests
        )
        let concurrentProcessingEnabled = parseBool(
            environment["MELIX_GATEWAY_CONCURRENT_PROCESSING_ENABLED"],
            fallback: profileDefaults.concurrentProcessingEnabled
        )
        let prefillBatchSize = parseUInt32(
            environment["MELIX_GATEWAY_PREFILL_BATCH_SIZE"],
            fallback: profileDefaults.prefillBatchSize
        )
        let completionBatchSize = parseUInt32(
            environment["MELIX_GATEWAY_COMPLETION_BATCH_SIZE"],
            fallback: profileDefaults.completionBatchSize
        )
        let accelerationMode = parseAccelerationMode(
            environment["MELIX_GATEWAY_ACCELERATION_MODE"],
            fallback: profileDefaults.accelerationMode
        )
        let draftModelID = (environment["MELIX_GATEWAY_DRAFT_MODEL_ID"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .nilIfEmpty ?? profileDefaults.draftModelID
        let numDraftTokens = parseNonNegativeUInt32(
            environment["MELIX_GATEWAY_NUM_DRAFT_TOKENS"],
            fallback: profileDefaults.numDraftTokens
        )
        let multimodalRoutePolicy = normalizedRoutePolicy(
            environment["MELIX_GATEWAY_MULTIMODAL_ROUTE_POLICY"] ?? "auto"
        )
        let speculativeRoutePolicy = normalizedRoutePolicy(
            environment["MELIX_GATEWAY_SPECULATIVE_ROUTE_POLICY"] ?? "auto"
        )

        let usesEnvironmentDefaults =
            environment["MELIX_GATEWAY_DEFAULT_TEMPERATURE"] != nil
            || environment["MELIX_GATEWAY_DEFAULT_TOP_P"] != nil
            || environment["MELIX_GATEWAY_DEFAULT_MAX_TOKENS"] != nil
            || environment["MELIX_GATEWAY_STREAM_INTERVAL_TOKENS"] != nil
            || environment["MELIX_GATEWAY_CONCURRENT_PROCESSING_ENABLED"] != nil
            || environment["MELIX_GATEWAY_PREFILL_BATCH_SIZE"] != nil
            || environment["MELIX_GATEWAY_COMPLETION_BATCH_SIZE"] != nil
            || environment["MELIX_GATEWAY_MAX_CONCURRENT_SEQUENCES"] != nil
            || environment["MELIX_GATEWAY_MAX_CONCURRENT_REQUESTS"] != nil
            || environment["MELIX_GATEWAY_ACCELERATION_MODE"] != nil
            || environment["MELIX_GATEWAY_DRAFT_MODEL_ID"] != nil
            || environment["MELIX_GATEWAY_NUM_DRAFT_TOKENS"] != nil
            || environment["MELIX_GATEWAY_ACCELERATION_PROFILE"] != nil
            || environment["MELIX_GATEWAY_MULTIMODAL_ROUTE_POLICY"] != nil
            || environment["MELIX_GATEWAY_SPECULATIVE_ROUTE_POLICY"] != nil

        return GatewayServingDefaultsResolvedDefaults(
            temperature: temperature,
            topP: topP,
            maxTokens: maxTokens,
            streamIntervalTokens: streamIntervalTokens,
            maxConcurrentRequests: maxConcurrentRequests,
            concurrentProcessingEnabled: concurrentProcessingEnabled,
            prefillBatchSize: prefillBatchSize,
            completionBatchSize: completionBatchSize,
            accelerationMode: accelerationMode,
            draftModelID: draftModelID,
            numDraftTokens: numDraftTokens,
            accelerationProfile: accelerationProfile,
            multimodalRoutePolicy: isKnownRoutePolicy(multimodalRoutePolicy) ? multimodalRoutePolicy : "auto",
            speculativeRoutePolicy: isKnownRoutePolicy(speculativeRoutePolicy) ? speculativeRoutePolicy : "auto",
            source: usesEnvironmentDefaults ? .environmentDefaults : .builtInDefaults
        )
    }

    private static func normalizedProfileID(_ rawValue: String?) -> String {
        ServingAccelerationProfiles.normalizeProfileID(rawValue)
            ?? ServingAccelerationProfiles.defaultProfileID
    }

    private static func isKnownProfileID(_ rawValue: String?) -> Bool {
        guard let rawValue = rawValue?.trimmingCharacters(in: .whitespacesAndNewlines),
              rawValue.isEmpty == false else {
            return true
        }
        return ServingAccelerationProfiles.normalizeProfileID(rawValue) != nil
    }

    private static func parseDouble(_ rawValue: String?, fallback: Double) -> Double {
        guard let rawValue = rawValue?.nilIfEmpty, let parsed = Double(rawValue), parsed.isFinite else {
            return fallback
        }
        return parsed
    }

    private static func parseUInt32(_ rawValue: String?, fallback: UInt32) -> UInt32 {
        guard let rawValue = rawValue?.nilIfEmpty, let parsed = UInt32(rawValue), parsed > 0 else {
            return fallback
        }
        return parsed
    }

    private static func parseNonNegativeUInt32(_ rawValue: String?, fallback: UInt32) -> UInt32 {
        guard let rawValue = rawValue?.nilIfEmpty, let parsed = UInt32(rawValue) else {
            return fallback
        }
        return parsed
    }

    private static func parseBool(_ rawValue: String?, fallback: Bool) -> Bool {
        guard let rawValue = rawValue?.nilIfEmpty?.lowercased() else {
            return fallback
        }
        switch rawValue {
        case "1", "true", "yes", "on":
            return true
        case "0", "false", "no", "off":
            return false
        default:
            return fallback
        }
    }

    private static func parseAccelerationMode(
        _ rawValue: String?,
        fallback: Melix_Controlplane_V1_AccelerationMode
    ) -> Melix_Controlplane_V1_AccelerationMode {
        switch rawValue?.nilIfEmpty?.lowercased() {
        case "speculative_decode":
            return .speculativeDecode
        case "baseline", nil:
            return fallback
        default:
            return fallback
        }
    }

    private static func normalizeRequestedAccelerationMode(
        _ mode: Melix_Controlplane_V1_AccelerationMode
    ) -> Melix_Controlplane_V1_AccelerationMode {
        switch mode {
        case .speculativeDecode:
            return .speculativeDecode
        default:
            return .baseline
        }
    }

    private static func effectiveBatchingDefaults(
        concurrentProcessingEnabled: Bool,
        maxConcurrentRequests: UInt32,
        prefillBatchSize: UInt32,
        completionBatchSize: UInt32
    ) -> (
        concurrentProcessingEnabled: Bool,
        maxConcurrentRequests: UInt32,
        prefillBatchSize: UInt32,
        completionBatchSize: UInt32
    ) {
        guard concurrentProcessingEnabled else {
            return (false, 1, 1, 1)
        }

        let normalizedMaxConcurrentRequests = max(maxConcurrentRequests, 1)
        let normalizedPrefillBatchSize = max(prefillBatchSize, 1)
        let normalizedCompletionBatchSize = max(completionBatchSize, 1)
        // The effective batch width is bounded by the smallest requested lane.
        let effectiveBatchCapacity = min(
            normalizedMaxConcurrentRequests,
            normalizedPrefillBatchSize,
            normalizedCompletionBatchSize
        )
        guard effectiveBatchCapacity > 1 else {
            return (false, 1, 1, 1)
        }

        return (
            true,
            effectiveBatchCapacity,
            effectiveBatchCapacity,
            effectiveBatchCapacity
        )
    }

    private static func effectiveMultimodalRoute(
        for modelSettings: Melix_Controlplane_V1_ModelSettings?,
        routePolicy: String
    ) -> String {
        if normalizedRoutePolicy(routePolicy) == "off" {
            return "off"
        }
        guard let modelSettings else {
            return WorkerRouteKind.swiftText.metadataIdentifier
        }
        if let routeKind = WorkerRouteKind(metadataIdentifier: modelSettings.ext["melix.capability.route_kind"]) {
            return routeKind.metadataIdentifier
        }
        if let routeKind = WorkerRouteKind(capabilityIdentifier: modelSettings.ext["melix.capability.class"]) {
            return routeKind.metadataIdentifier
        }
        return WorkerRouteKind.swiftText.metadataIdentifier
    }

    private static func overrideReceiptExt(
        requestedMaxConcurrentRequests: UInt32,
        requestedPrefillBatchSize: UInt32,
        requestedCompletionBatchSize: UInt32,
        effectiveMaxConcurrentRequests: UInt32,
        effectivePrefillBatchSize: UInt32,
        effectiveCompletionBatchSize: UInt32,
        requestedAccelerationMode: Melix_Controlplane_V1_AccelerationMode,
        effectiveAccelerationMode: Melix_Controlplane_V1_AccelerationMode,
        multimodalRoutePolicy: String,
        effectiveMultimodalRoute: String,
        speculativeRoutePolicy: String
    ) -> [String: String] {
        var suppressedOverrides: [String] = []
        var batchOverrideSuppressed = false
        if requestedMaxConcurrentRequests != effectiveMaxConcurrentRequests {
            suppressedOverrides.append("max_concurrent_requests")
            batchOverrideSuppressed = true
        }
        if requestedPrefillBatchSize != effectivePrefillBatchSize {
            suppressedOverrides.append("prefill_batch_size")
            batchOverrideSuppressed = true
        }
        if requestedCompletionBatchSize != effectiveCompletionBatchSize {
            suppressedOverrides.append("completion_batch_size")
            batchOverrideSuppressed = true
        }

        let normalizedRequestedAccelerationMode = normalizeRequestedAccelerationMode(requestedAccelerationMode)
        let normalizedMultimodalRoutePolicy = normalizedRoutePolicy(multimodalRoutePolicy)
        let normalizedSpeculativeRoutePolicy = normalizedRoutePolicy(speculativeRoutePolicy)
        let normalizedEffectiveMultimodalRoute = normalizedRouteIdentifier(effectiveMultimodalRoute)
        let normalizedEffectiveAccelerationMode = normalizedSpeculativeRoutePolicy == "off"
            ? Melix_Controlplane_V1_AccelerationMode.baseline
            : normalizeRequestedAccelerationMode(effectiveAccelerationMode)
        var receiptExt: [String: String] = [
            "melix.gateway.override_receipt_schema": "melix.gateway_override_receipt.v1",
            "melix.gateway.multimodal_route_policy": normalizedMultimodalRoutePolicy,
            "melix.gateway.effective_multimodal_route": normalizedEffectiveMultimodalRoute,
            "melix.gateway.speculative_route_policy": normalizedSpeculativeRoutePolicy,
            "melix.gateway.effective_speculative_mode": accelerationModeIdentifier(normalizedEffectiveAccelerationMode),
            "melix.gateway.batch.disabled_reason": batchOverrideSuppressed ? "incompatible_batch_size" : "none",
            "melix.gateway.cache_quantization.disabled_reason": "not_configurable",
            "melix.gateway.paged_cache.disabled_reason": "not_configurable",
        ]

        if normalizedRequestedAccelerationMode == .speculativeDecode,
           normalizedEffectiveAccelerationMode != .speculativeDecode {
            suppressedOverrides.append("speculative_decode")
            receiptExt["melix.gateway.speculative.disabled_reason"] = normalizedSpeculativeRoutePolicy == "off"
                ? "operator_disabled"
                : "unsupported_route"
        }
        if !suppressedOverrides.isEmpty {
            receiptExt["melix.gateway.suppressed_overrides"] = suppressedOverrides.joined(separator: ",")
        }
        return receiptExt
    }

    private static func effectiveSpeculativeDefaults(
        requestedAccelerationProfile: String,
        requestedAccelerationMode: Melix_Controlplane_V1_AccelerationMode,
        requestedDraftModelID: String,
        requestedNumDraftTokens: UInt32,
        modelSettings: Melix_Controlplane_V1_ModelSettings?,
        speculativeRoutePolicy: String = "auto"
    ) -> (
        accelerationMode: Melix_Controlplane_V1_AccelerationMode,
        draftModelID: String,
        numDraftTokens: UInt32,
        accelerationProfile: String,
        modelOverrideApplied: Bool
    ) {
        let normalizedRequestedMode = normalizeRequestedAccelerationMode(requestedAccelerationMode)
        let modelAccelerationMode = normalizeRequestedAccelerationMode(
            modelSettings?.defaultAccelerationMode ?? .baseline
        )
        let hasModelAccelerationOverride = modelSettings?.defaultAccelerationMode != .unspecified
        let requestedProfile = normalizedProfileID(requestedAccelerationProfile)
        let modelProfileRawValue = modelSettings?.accelerationProfileID ?? ""
        let modelProfile = normalizedProfileID(modelProfileRawValue)
        let hasModelProfileOverride = ServingAccelerationProfiles.normalizeProfileID(modelProfileRawValue) != nil
        let effectiveProfile = hasModelProfileOverride ? modelProfile : requestedProfile
        let effectiveAccelerationMode = normalizedRoutePolicy(speculativeRoutePolicy) == "off"
            ? Melix_Controlplane_V1_AccelerationMode.baseline
            : hasModelAccelerationOverride
            ? modelAccelerationMode
            : normalizedRequestedMode
        guard effectiveAccelerationMode == .speculativeDecode else {
            return (
                effectiveAccelerationMode,
                "",
                0,
                effectiveProfile,
                (hasModelAccelerationOverride && modelAccelerationMode != normalizedRequestedMode)
                    || (hasModelProfileOverride && modelProfile != requestedProfile)
            )
        }
        return (
            effectiveAccelerationMode,
            requestedDraftModelID,
            requestedNumDraftTokens,
            effectiveProfile,
            (hasModelAccelerationOverride && modelAccelerationMode != normalizedRequestedMode)
                || (hasModelProfileOverride && modelProfile != requestedProfile)
        )
    }

    private static func accelerationModeIdentifier(
        _ mode: Melix_Controlplane_V1_AccelerationMode
    ) -> String {
        switch mode {
        case .speculativeDecode:
            return "speculative_decode"
        default:
            return "baseline"
        }
    }

    private static func normalizedRoutePolicy(_ rawValue: String) -> String {
        let normalized = rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized.isEmpty ? "auto" : normalized
    }

    private static func normalizedRouteIdentifier(_ rawValue: String) -> String {
        let normalized = rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized.isEmpty ? WorkerRouteKind.swiftText.metadataIdentifier : normalized
    }

    private static func isKnownRoutePolicy(_ rawValue: String) -> Bool {
        switch normalizedRoutePolicy(rawValue) {
        case "auto", "off", "force":
            return true
        default:
            return false
        }
    }

    private static func trimmed(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

private extension String {
    var nilIfEmpty: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
