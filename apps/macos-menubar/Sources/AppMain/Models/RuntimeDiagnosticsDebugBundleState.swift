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
