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
    case invalidAccelerationMode
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
        case .invalidAccelerationMode:
            return "invalid_acceleration_mode"
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
        case .invalidAccelerationMode:
            return "Serving defaults only support baseline or speculative decode acceleration."
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
        numDraftTokens: UInt32? = nil
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
        case sourceRawValue = "source"
        case updatedAtUnixMS = "updated_at_unix_ms"
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
            numDraftTokens: record?.numDraftTokens ?? defaults.numDraftTokens
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
            sourceRawValue: Melix_Controlplane_V1_ServingDefaultsSource.operatorOverride.rawValue,
            updatedAtUnixMS: nowUnixMS()
        )
        recordsByServerSessionID[serverSessionID] = record
        try writeRecords()
    }

    public func summary(
        serverSessionIDs: [String],
        servedModelIDs: [String: String],
        modelSettingsByModelID: [String: Melix_Controlplane_V1_ModelSettings]
    ) -> Melix_Controlplane_V1_ServingDefaultsSummary {
        var summary = Melix_Controlplane_V1_ServingDefaultsSummary()
        let allServerSessionIDs = Set(
            serverSessionIDs.map(Self.trimmed).filter { !$0.isEmpty }
            + recordsByServerSessionID.keys
            + servedModelIDs.keys
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
            let servedModelID = Self.trimmed(servedModelIDs[serverSessionID] ?? "")
            let modelSamplingPolicy = modelSettingsByModelID[servedModelID].flatMap(ModelSamplingPolicy.init)
            let modelSettings = modelSettingsByModelID[servedModelID]
            let effectiveBatchingDefaults = Self.effectiveBatchingDefaults(
                concurrentProcessingEnabled: requestedConcurrentProcessingEnabled,
                maxConcurrentRequests: requestedMaxConcurrentRequests,
                prefillBatchSize: requestedPrefillBatchSize,
                completionBatchSize: requestedCompletionBatchSize
            )
            let effectiveSpeculativeDefaults = Self.effectiveSpeculativeDefaults(
                requestedAccelerationMode: requestedAccelerationMode,
                requestedDraftModelID: requestedDraftModelID,
                requestedNumDraftTokens: requestedNumDraftTokens,
                modelSettings: modelSettings
            )

            var session = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
            session.serverSessionID = serverSessionID
            session.servedModelID = servedModelID
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
            fallback: 4
        )
        let concurrentProcessingEnabled = parseBool(
            environment["MELIX_GATEWAY_CONCURRENT_PROCESSING_ENABLED"],
            fallback: true
        )
        let prefillBatchSize = parseUInt32(
            environment["MELIX_GATEWAY_PREFILL_BATCH_SIZE"],
            fallback: 2
        )
        let completionBatchSize = parseUInt32(
            environment["MELIX_GATEWAY_COMPLETION_BATCH_SIZE"],
            fallback: 2
        )
        let accelerationMode = parseAccelerationMode(
            environment["MELIX_GATEWAY_ACCELERATION_MODE"],
            fallback: .baseline
        )
        let draftModelID = (environment["MELIX_GATEWAY_DRAFT_MODEL_ID"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let numDraftTokens = parseNonNegativeUInt32(
            environment["MELIX_GATEWAY_NUM_DRAFT_TOKENS"],
            fallback: 0
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
            source: usesEnvironmentDefaults ? .environmentDefaults : .builtInDefaults
        )
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

    private static func effectiveSpeculativeDefaults(
        requestedAccelerationMode: Melix_Controlplane_V1_AccelerationMode,
        requestedDraftModelID: String,
        requestedNumDraftTokens: UInt32,
        modelSettings: Melix_Controlplane_V1_ModelSettings?
    ) -> (
        accelerationMode: Melix_Controlplane_V1_AccelerationMode,
        draftModelID: String,
        numDraftTokens: UInt32,
        modelOverrideApplied: Bool
    ) {
        let normalizedRequestedMode = normalizeRequestedAccelerationMode(requestedAccelerationMode)
        let modelAccelerationMode = normalizeRequestedAccelerationMode(
            modelSettings?.defaultAccelerationMode ?? .baseline
        )
        let hasModelAccelerationOverride = modelSettings?.defaultAccelerationMode != .unspecified
        let effectiveAccelerationMode = hasModelAccelerationOverride
            ? modelAccelerationMode
            : normalizedRequestedMode
        guard effectiveAccelerationMode == .speculativeDecode else {
            return (
                effectiveAccelerationMode,
                "",
                0,
                hasModelAccelerationOverride && modelAccelerationMode != normalizedRequestedMode
            )
        }
        return (
            effectiveAccelerationMode,
            requestedDraftModelID,
            requestedNumDraftTokens,
            hasModelAccelerationOverride && modelAccelerationMode != normalizedRequestedMode
        )
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
