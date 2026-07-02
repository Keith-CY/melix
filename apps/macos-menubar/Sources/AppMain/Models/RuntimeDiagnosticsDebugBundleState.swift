import Foundation
import MelixControlPlaneCore

public struct RuntimeDiagnosticsDebugBundleArtifactRow: Equatable, Identifiable, Sendable {
    public let id: String
    public let kind: String
    public let kindText: String
    public let path: String

    public init(kind: String, kindText: String, path: String) {
        self.kind = RichOutputSanitizer.sanitized(kind)
        self.kindText = RichOutputSanitizer.sanitized(kindText)
        self.path = RichOutputSanitizer.sanitized(path)
        id = "\(kind)::\(path)"
    }
}

public struct RuntimeDiagnosticsServingDiagnosticsSummary: Equatable, Sendable, Decodable {
    public let schemaVersion: String
    public let diagnosticsMode: String
    public let eventCount: Int
    public let droppedEventCount: Int

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = RichOutputSanitizer.sanitized(
            try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        )
        diagnosticsMode = RichOutputSanitizer.sanitized(
            try container.decodeIfPresent(String.self, forKey: .diagnosticsMode) ?? ""
        )
        eventCount = max(0, try container.decodeIfPresent(Int.self, forKey: .eventCount) ?? 0)
        droppedEventCount = max(0, try container.decodeIfPresent(Int.self, forKey: .droppedEventCount) ?? 0)
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case diagnosticsMode = "diagnostics_mode"
        case eventCount = "event_count"
        case droppedEventCount = "dropped_event_count"
    }
}

public struct RuntimeEnvironmentDiagnosticSummaryState: Equatable, Sendable, Decodable {
    public let schemaVersion: String
    public let status: String
    public let checkCount: Int
    public let failedCheckCount: Int
    public let warningCheckCount: Int
    public let redactedFieldCount: Int
    public let diagnosticLatencyMS: Int

    public var summaryText: String {
        let normalizedStatus = status.isEmpty ? "unknown" : status
        return "\(normalizedStatus) • \(checkCount) checks • \(failedCheckCount) failed • \(warningCheckCount) warnings"
    }

    public var redactionText: String {
        "\(redactedFieldCount) fields redacted"
    }

    public var latencyText: String {
        "\(diagnosticLatencyMS) ms"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = RichOutputSanitizer.sanitized(
            try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        )
        let summary = try container.decodeIfPresent(SummaryPayload.self, forKey: .summary)
        let redactionSummary = try container.decodeIfPresent(RedactionSummaryPayload.self, forKey: .redactionSummary)
        let metrics = try container.decodeIfPresent(MetricsPayload.self, forKey: .metrics)
        status = RichOutputSanitizer.sanitized(summary?.status ?? "")
        checkCount = max(0, summary?.checkCount ?? 0)
        failedCheckCount = max(0, summary?.failedCheckCount ?? 0)
        warningCheckCount = max(0, summary?.warningCheckCount ?? 0)
        redactedFieldCount = max(0, redactionSummary?.redactedFieldCount ?? 0)
        diagnosticLatencyMS = max(0, metrics?.diagnosticLatencyMS ?? 0)
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case summary
        case redactionSummary = "redaction_summary"
        case metrics
    }

    private struct SummaryPayload: Decodable {
        let status: String?
        let checkCount: Int?
        let failedCheckCount: Int?
        let warningCheckCount: Int?

        private enum CodingKeys: String, CodingKey {
            case status
            case checkCount = "check_count"
            case failedCheckCount = "failed_check_count"
            case warningCheckCount = "warning_check_count"
        }
    }

    private struct RedactionSummaryPayload: Decodable {
        let redactedFieldCount: Int?

        private enum CodingKeys: String, CodingKey {
            case redactedFieldCount = "redacted_field_count"
        }
    }

    private struct MetricsPayload: Decodable {
        let diagnosticLatencyMS: Int?

        private enum CodingKeys: String, CodingKey {
            case diagnosticLatencyMS = "diagnostic_latency_ms"
        }
    }
}

public struct RuntimeStorageInventorySummaryState: Equatable, Sendable, Decodable {
    public let artifactCount: Int
    public let cleanableByteSize: Int
    public let protectedByteSize: Int

    public var summaryText: String {
        "\(artifactCount) artifacts • \(cleanableByteSize) B cleanable • \(protectedByteSize) B protected"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let summary = try container.decodeIfPresent(SummaryPayload.self, forKey: .summary)
        artifactCount = max(0, summary?.artifactCount ?? 0)
        cleanableByteSize = max(0, summary?.cleanableByteSize ?? 0)
        protectedByteSize = max(0, summary?.protectedByteSize ?? 0)
    }

    private enum CodingKeys: String, CodingKey {
        case summary
    }

    private struct SummaryPayload: Decodable {
        let artifactCount: Int?
        let cleanableByteSize: Int?
        let protectedByteSize: Int?

        private enum CodingKeys: String, CodingKey {
            case artifactCount = "artifact_count"
            case cleanableByteSize = "cleanable_byte_size"
            case protectedByteSize = "protected_byte_size"
        }
    }
}

public struct RuntimeStorageCleanupPlanSummaryState: Equatable, Sendable, Decodable {
    public let mode: String
    public let cleanableEntryCount: Int
    public let retainedEntryCount: Int
    public let protectedEntryCount: Int
    public let blockedEntryCount: Int

    public var summaryText: String {
        let normalizedMode = mode.isEmpty ? "dry_run" : mode
        return "\(normalizedMode) • \(cleanableEntryCount) cleanable • \(retainedEntryCount) retained • \(protectedEntryCount) protected • \(blockedEntryCount) blocked"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        mode = RichOutputSanitizer.sanitized(try container.decodeIfPresent(String.self, forKey: .mode) ?? "")
        let summary = try container.decodeIfPresent(SummaryPayload.self, forKey: .summary)
        cleanableEntryCount = max(0, summary?.cleanableEntryCount ?? 0)
        retainedEntryCount = max(0, summary?.retainedEntryCount ?? 0)
        protectedEntryCount = max(0, summary?.protectedEntryCount ?? 0)
        blockedEntryCount = max(0, summary?.blockedEntryCount ?? 0)
    }

    private enum CodingKeys: String, CodingKey {
        case mode
        case summary
    }

    private struct SummaryPayload: Decodable {
        let cleanableEntryCount: Int?
        let retainedEntryCount: Int?
        let protectedEntryCount: Int?
        let blockedEntryCount: Int?

        private enum CodingKeys: String, CodingKey {
            case cleanableEntryCount = "cleanable_entry_count"
            case retainedEntryCount = "retained_entry_count"
            case protectedEntryCount = "protected_entry_count"
            case blockedEntryCount = "blocked_entry_count"
        }
    }
}

public struct RuntimeStorageCleanupReceiptSummaryState: Equatable, Sendable, Decodable {
    public let safeDeleteCount: Int
    public let deletedByteSize: Int
    public let protectedEntryCount: Int
    public let failedEntryCount: Int

    public var summaryText: String {
        "\(safeDeleteCount) deleted • \(deletedByteSize) B reclaimed • \(protectedEntryCount) protected • \(failedEntryCount) failed"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let summary = try container.decodeIfPresent(SummaryPayload.self, forKey: .summary)
        safeDeleteCount = max(0, summary?.safeDeleteCount ?? 0)
        deletedByteSize = max(0, summary?.deletedByteSize ?? 0)
        protectedEntryCount = max(0, summary?.protectedEntryCount ?? 0)
        failedEntryCount = max(0, summary?.failedEntryCount ?? 0)
    }

    private enum CodingKeys: String, CodingKey {
        case summary
    }

    private struct SummaryPayload: Decodable {
        let safeDeleteCount: Int?
        let deletedByteSize: Int?
        let protectedEntryCount: Int?
        let failedEntryCount: Int?

        private enum CodingKeys: String, CodingKey {
            case safeDeleteCount = "safe_delete_count"
            case deletedByteSize = "deleted_byte_size"
            case protectedEntryCount = "protected_entry_count"
            case failedEntryCount = "failed_entry_count"
        }
    }
}

public struct RuntimeDiagnosticsDebugBundleState: Equatable, Sendable, Decodable {
    public let schemaVersion: String
    public let bundleID: String
    public let bundlePath: String
    public let diagnosticsConsentState: String
    public let debugArtifactPolicy: String
    public let debugJSONLEnabled: Bool
    public let debugJSONLEventLimit: Int
    public let redactionSchemaVersion: String
    public let redactedFieldCount: Int
    public let sourceRunRecordPath: String
    public let artifacts: [String: String]
    public let mediaRouteReceipt: RuntimeDiscoveryMediaRouteReceiptState?
    public let servingDiagnostics: RuntimeDiagnosticsServingDiagnosticsSummary?
    public let environmentDiagnostic: RuntimeEnvironmentDiagnosticSummaryState?
    public let storageInventory: RuntimeStorageInventorySummaryState?
    public let storageCleanupPlan: RuntimeStorageCleanupPlanSummaryState?
    public let storageCleanupReceipt: RuntimeStorageCleanupReceiptSummaryState?

    public var manifestPath: String {
        guard bundlePath.isEmpty == false else {
            return ""
        }
        return URL(fileURLWithPath: bundlePath)
            .appendingPathComponent("manifest.json")
            .path
    }

    public var artifactRows: [RuntimeDiagnosticsDebugBundleArtifactRow] {
        var rows: [RuntimeDiagnosticsDebugBundleArtifactRow] = []
        if manifestPath.isEmpty == false {
            rows.append(
                RuntimeDiagnosticsDebugBundleArtifactRow(
                    kind: "manifest",
                    kindText: "Manifest",
                    path: manifestPath
                )
            )
        }
        rows.append(
            contentsOf: artifacts.keys.sorted().map { key in
                RuntimeDiagnosticsDebugBundleArtifactRow(
                    kind: key,
                    kindText: Self.displayName(for: key),
                    path: artifactPath(artifacts[key] ?? "")
                )
            }
        )
        return rows
    }

    public var redactionSummaryText: String {
        let redaction = redactionSchemaVersion.isEmpty ? "redaction unknown" : redactionSchemaVersion
        return "\(redaction) • \(redactedFieldCount) fields redacted"
    }

    public var debugJSONLSummaryText: String {
        let enabledText = debugJSONLEnabled ? "enabled" : "disabled"
        guard debugJSONLEventLimit > 0 else {
            return "\(enabledText), limit unknown"
        }
        return "\(enabledText), limit \(debugJSONLEventLimit) events"
    }

    public var servingDiagnosticsQueueSummaryText: String {
        guard let servingDiagnostics else {
            return ""
        }
        let observed = servingDiagnostics.eventCount + servingDiagnostics.droppedEventCount
        return "\(servingDiagnostics.eventCount) retained / \(servingDiagnostics.droppedEventCount) dropped / \(observed) observed"
    }

    public var servingDiagnosticsRetentionSummaryText: String {
        guard let servingDiagnostics else {
            return ""
        }
        let mode = servingDiagnostics.diagnosticsMode.isEmpty ? "debug" : servingDiagnostics.diagnosticsMode
        guard debugJSONLEventLimit > 0 else {
            return "\(mode) mode retention limit unknown"
        }
        return "\(mode) mode retains up to \(debugJSONLEventLimit) events"
    }

    public var servingDiagnosticsDropSummaryText: String {
        guard let servingDiagnostics else {
            return ""
        }
        guard servingDiagnostics.droppedEventCount > 0 else {
            return "No debug events were dropped."
        }
        return "\(servingDiagnostics.droppedEventCount) debug events were dropped; diagnosis may be partial."
    }

    public static func decode(json: String) throws -> RuntimeDiagnosticsDebugBundleState {
        try JSONDecoder().decode(Self.self, from: Data(json.utf8))
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        bundleID = try container.decodeIfPresent(String.self, forKey: .bundleID) ?? ""
        bundlePath = try container.decodeIfPresent(String.self, forKey: .bundlePath) ?? ""
        diagnosticsConsentState = try container.decodeIfPresent(String.self, forKey: .diagnosticsConsentState) ?? ""
        debugArtifactPolicy = try container.decodeIfPresent(String.self, forKey: .debugArtifactPolicy) ?? ""
        debugJSONLEnabled = try container.decodeIfPresent(Bool.self, forKey: .debugJSONLEnabled) ?? false
        debugJSONLEventLimit = try container.decodeIfPresent(Int.self, forKey: .debugJSONLEventLimit) ?? 0
        redactionSchemaVersion = try container.decodeIfPresent(String.self, forKey: .redactionSchemaVersion) ?? ""
        redactedFieldCount = try container.decodeIfPresent(Int.self, forKey: .redactedFieldCount) ?? 0
        sourceRunRecordPath = try container.decodeIfPresent(String.self, forKey: .sourceRunRecordPath) ?? ""
        artifacts = try container.decodeIfPresent([String: String].self, forKey: .artifacts) ?? [:]
        mediaRouteReceipt = try container.decodeIfPresent(
            RuntimeDiagnosticsMediaRouteReceiptEnvelope.self,
            forKey: .mediaRouteReceipt
        )?.state
        servingDiagnostics = try container.decodeIfPresent(
            RuntimeDiagnosticsServingDiagnosticsSummary.self,
            forKey: .servingDiagnostics
        )
        environmentDiagnostic = try container.decodeIfPresent(
            RuntimeEnvironmentDiagnosticSummaryState.self,
            forKey: .environmentDiagnostic
        )
        storageInventory = try container.decodeIfPresent(
            RuntimeStorageInventorySummaryState.self,
            forKey: .storageInventory
        )
        storageCleanupPlan = try container.decodeIfPresent(
            RuntimeStorageCleanupPlanSummaryState.self,
            forKey: .storageCleanupPlan
        )
        storageCleanupReceipt = try container.decodeIfPresent(
            RuntimeStorageCleanupReceiptSummaryState.self,
            forKey: .storageCleanupReceipt
        )
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case bundleID = "bundle_id"
        case bundlePath = "bundle_path"
        case diagnosticsConsentState = "diagnostics_consent_state"
        case debugArtifactPolicy = "debug_artifact_policy"
        case debugJSONLEnabled = "debug_jsonl_enabled"
        case debugJSONLEventLimit = "debug_jsonl_event_limit"
        case redactionSchemaVersion = "redaction_schema_version"
        case redactedFieldCount = "redacted_field_count"
        case sourceRunRecordPath = "source_run_record_path"
        case artifacts
        case mediaRouteReceipt = "media_route_receipt"
        case servingDiagnostics = "serving_diagnostics"
        case environmentDiagnostic = "environment_diagnostic"
        case storageInventory = "storage_inventory"
        case storageCleanupPlan = "storage_cleanup_plan"
        case storageCleanupReceipt = "storage_cleanup_receipt"
    }

    private func artifactPath(_ relativePath: String) -> String {
        let trimmed = relativePath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            return ""
        }
        guard trimmed.hasPrefix("/") == false, bundlePath.isEmpty == false else {
            return trimmed
        }
        return URL(fileURLWithPath: bundlePath)
            .appendingPathComponent(trimmed)
            .path
    }

    private static func displayName(for key: String) -> String {
        key.split(separator: "_")
            .map { segment in
                segment.prefix(1).uppercased() + segment.dropFirst()
            }
            .joined(separator: " ")
    }
}

private struct RuntimeDiagnosticsMediaRouteReceiptEnvelope: Decodable {
    let state: RuntimeDiscoveryMediaRouteReceiptState

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        state = RuntimeDiscoveryMediaRouteReceiptState(
            mediaRoute: try container.decodeIfPresent(String.self, forKey: .mediaRoute) ?? "",
            mediaPartsCount: max(0, try container.decodeIfPresent(Int.self, forKey: .mediaPartsCount) ?? 0),
            mediaTurnCount: max(0, try container.decodeIfPresent(Int.self, forKey: .mediaTurnCount) ?? 0),
            cacheHitCount: max(0, try container.decodeIfPresent(Int.self, forKey: .cacheHitCount) ?? 0),
            cacheMissCount: max(0, try container.decodeIfPresent(Int.self, forKey: .cacheMissCount) ?? 0),
            unsupportedReason: try container.decodeIfPresent(String.self, forKey: .unsupportedReason) ?? ""
        )
    }

    private enum CodingKeys: String, CodingKey {
        case mediaRoute = "media_route"
        case mediaPartsCount = "media_parts_count"
        case mediaTurnCount = "media_turn_count"
        case cacheHitCount = "cache_hit_count"
        case cacheMissCount = "cache_miss_count"
        case unsupportedReason = "unsupported_reason"
    }
}
