import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public enum MelixProbeMode: String, CaseIterable, Sendable {
    case off
    case minimal
    case sampled
    case evidence
    case debug

    public static let environmentKey = "MELIX_PROBE_MODE"

    public static func fromEnvironment(_ environment: [String: String]) -> MelixProbeMode {
        fromValue(environment[environmentKey])
    }

    public static func fromValue(_ value: String?) -> MelixProbeMode {
        let normalized = (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard normalized.isEmpty == false else {
            return .minimal
        }
        return MelixProbeMode(rawValue: normalized) ?? .minimal
    }

    public var debugArtifactsEnabled: Bool {
        self == .debug
    }

    public var detailedTelemetryEnabled: Bool {
        switch self {
        case .sampled, .evidence, .debug:
            return true
        case .off, .minimal:
            return false
        }
    }
}

public enum MelixDiagnosticsRedaction {
    public static let schemaVersion = "melix.diagnostics.redaction.v1"
    private static let sensitiveKeyFragments = [
        "api_key",
        "apikey",
        "authorization",
        "auth_token",
        "bearer",
        "credential",
        "hf_token",
        "password",
        "private_key",
        "prompt",
        "secret",
        "token",
    ]

    public static func redactMapping(_ payload: [String: Any]) -> (payload: [String: Any], redactedFieldCount: Int) {
        var count = 0
        let redacted = payload.mapValues { value in
            redactValue(value, redactedFieldCount: &count)
        }
        return (redacted, count)
    }

    public static func redactString(_ value: String) -> String {
        var redacted = value
        let replacements = [
            (
                #"(?i)(^|[\\/])([^\\/\s"']*(?:api[-_]?key|authorization|bearer|credential|hf[_-]?token|password|private[_-]?key|prompt|secret|token)[^\\/\s"']*)"#,
                "$1<redacted>"
            ),
            (
                #"(?i)(api[-_ ]?key|authorization|bearer|hf[-_ ]?token|password|prompt|secret|token)(["'\s:=]+)([^"'\s,}]+)"#,
                "$1$2<redacted>"
            ),
            (#"(?i)(sk-[A-Za-z0-9_\-]{8,})"#, "<redacted>"),
            (#"(?i)(hf_[A-Za-z0-9_\-]{8,})"#, "<redacted>"),
        ]
        for (pattern, template) in replacements {
            guard let expression = try? NSRegularExpression(pattern: pattern) else {
                continue
            }
            let range = NSRange(redacted.startIndex..<redacted.endIndex, in: redacted)
            redacted = expression.stringByReplacingMatches(
                in: redacted,
                range: range,
                withTemplate: template
            )
        }
        return redacted
    }

    public static func redactEnvironment(_ environment: [String: String]) -> (payload: [String: Any], redactedFieldCount: Int) {
        var redacted: [String: Any] = [:]
        var count = 0
        for key in environment.keys.sorted() {
            let value = environment[key] ?? ""
            if isSensitiveKey(key) {
                redacted[key] = maskedHint(value)
                count += 1
            } else if value != redactString(value) {
                redacted[key] = redactString(value)
                count += 1
            } else {
                redacted[key] = value
            }
        }
        return (redacted, count)
    }

    public static func isSensitiveKey(_ key: String) -> Bool {
        let normalized = key
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
        return sensitiveKeyFragments.contains { normalized.contains($0) }
    }

    private static func redactValue(_ value: Any, redactedFieldCount: inout Int) -> Any {
        if let dictionary = value as? [String: Any] {
            var redacted: [String: Any] = [:]
            for key in dictionary.keys.sorted() {
                let child = dictionary[key] ?? NSNull()
                if isSensitiveKey(key) {
                    redacted[key] = maskedHint(String(describing: child))
                    redactedFieldCount += 1
                } else {
                    redacted[key] = redactValue(child, redactedFieldCount: &redactedFieldCount)
                }
            }
            return redacted
        }
        if let array = value as? [Any] {
            return array.map { redactValue($0, redactedFieldCount: &redactedFieldCount) }
        }
        if let string = value as? String {
            let redacted = redactString(string)
            if redacted != string {
                redactedFieldCount += 1
            }
            return redacted
        }
        return value
    }

    private static func maskedHint(_ value: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            return "<redacted:empty>"
        }
        let suffix = String(trimmed.suffix(min(4, trimmed.count)))
        return "<redacted:\(trimmed.count):...\(suffix)>"
    }
}

public struct MelixSystemDiagnostics {
    public static let schemaVersion = "melix.system.v1"
    public static let diagnosticsConsentState = "local_only"

    public static func payload(
        melixHome: MelixHome,
        environment: [String: String],
        redactedFieldCount: Int
    ) -> [String: Any] {
        let redactedHome = MelixDiagnosticsRedaction.redactMapping([
            "root": melixHome.rootURL.path,
            "config": melixHome.configDirectoryURL.path,
            "state": melixHome.stateDirectoryURL.path,
            "logs": melixHome.logsDirectoryURL.path,
            "runtime": melixHome.runtimeDirectoryURL.path,
            "model_ops_jobs": melixHome.modelOpsJobsRootURL.path,
            "evaluation_jobs": melixHome.evaluationJobsRootURL.path,
        ])
        let redactedWritability = MelixDiagnosticsRedaction.redactMapping([
            "items": writabilityPayload(melixHome: melixHome),
        ])
        let totalRedactedFieldCount = redactedFieldCount
            + redactedHome.redactedFieldCount
            + redactedWritability.redactedFieldCount
        return [
            "schema_version": schemaVersion,
            "diagnostics_consent_state": diagnosticsConsentState,
            "redaction_schema_version": MelixDiagnosticsRedaction.schemaVersion,
            "redacted_field_count": totalRedactedFieldCount,
            "platform": [
                "operating_system": ProcessInfo.processInfo.operatingSystemVersionString,
                "processor_count": ProcessInfo.processInfo.processorCount,
                "active_processor_count": ProcessInfo.processInfo.activeProcessorCount,
                "physical_memory_bytes": NSNumber(value: ProcessInfo.processInfo.physicalMemory),
            ],
            "melix_home": redactedHome.payload,
            "writability": redactedWritability.payload["items"] as? [[String: Any]] ?? [],
            "environment": [
                "melix_home_set": environment["MELIX_HOME"]?.isEmpty == false,
                "melix_runtime_dir_set": environment["MELIX_RUNTIME_DIR"]?.isEmpty == false,
                "melix_logs_dir_set": environment["MELIX_LOGS_DIR"]?.isEmpty == false,
                "melix_worker_socket_path_set": environment["MELIX_WORKER_SOCKET_PATH"]?.isEmpty == false,
                "melix_swift_text_worker_socket_path_set": environment["MELIX_SWIFT_TEXT_WORKER_SOCKET_PATH"]?.isEmpty == false,
            ],
            "probe_policy": MelixDiagnosticsStore.probePolicyPayload(environment: environment),
        ]
    }

    public static func missingDependencyFindings(melixHome: MelixHome) -> [[String: Any]] {
        let checks: [(String, URL)] = [
            ("melix_home_root_missing", melixHome.rootURL),
            ("melix_config_dir_missing", melixHome.configDirectoryURL),
            ("melix_state_dir_missing", melixHome.stateDirectoryURL),
            ("melix_logs_dir_missing", melixHome.logsDirectoryURL),
            ("melix_runtime_dir_missing", melixHome.runtimeDirectoryURL),
        ]
        return checks.compactMap { code, url in
            guard FileManager.default.fileExists(atPath: url.path) == false else {
                return nil
            }
            return [
                "code": code,
                "severity": "warning",
                "summary": MelixDiagnosticsRedaction.redactString("\(url.path) is not present."),
                "detail": "Melix can create this path on first use, but early diagnostics record it as missing.",
            ]
        }
    }

    private static func writabilityPayload(melixHome: MelixHome) -> [[String: Any]] {
        [
            ("root", melixHome.rootURL),
            ("config", melixHome.configDirectoryURL),
            ("state", melixHome.stateDirectoryURL),
            ("logs", melixHome.logsDirectoryURL),
            ("runtime", melixHome.runtimeDirectoryURL),
        ].map { label, url in
            [
                "name": label,
                "path": url.path,
                "exists": FileManager.default.fileExists(atPath: url.path),
                "writable": FileManager.default.isWritableFile(atPath: url.path),
            ]
        }
    }
}

struct MelixLogSnapshot {
    let runID: String
    let sourcePath: String
    let logPath: String
    let followRequested: Bool
    let activeFollowSupported: Bool
    let text: String

    var payload: [String: Any] {
        let redacted = MelixDiagnosticsRedaction.redactMapping([
            "source_path": sourcePath,
            "log_path": logPath,
            "content": text,
        ])
        return [
            "schema_version": "melix.logs.v1",
            "run_id": runID,
            "source_path": redacted.payload["source_path"] ?? sourcePath,
            "log_path": redacted.payload["log_path"] ?? logPath,
            "follow_requested": followRequested,
            "active_follow_supported": activeFollowSupported,
            "content": redacted.payload["content"] ?? text,
            "redaction_schema_version": MelixDiagnosticsRedaction.schemaVersion,
            "redacted_field_count": redacted.redactedFieldCount,
        ]
    }
}

struct MelixDebugBundleResult {
    let bundleRoot: URL
    let manifest: [String: Any]
}

public struct MelixDiagnosticsStore {
    private let melixHome: MelixHome
    private let environment: [String: String]
    private let fileManager: FileManager

    public init(
        melixHome: MelixHome,
        environment: [String: String],
        fileManager: FileManager = .default
    ) {
        self.melixHome = melixHome
        self.environment = environment
        self.fileManager = fileManager
    }

    public static func probePolicyPayload(environment: [String: String]) -> [String: Any] {
        let rawValue = environment[MelixProbeMode.environmentKey] ?? ""
        let mode = MelixProbeMode.fromEnvironment(environment)
        return [
            "schema_version": "melix.probe_policy.swift.v1",
            "environment_key": MelixProbeMode.environmentKey,
            "mode": mode.rawValue,
            "source_value": rawValue,
            "fallback_applied": rawValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
                && MelixProbeMode(rawValue: rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()) == nil,
            "detailed_telemetry_enabled": mode.detailedTelemetryEnabled,
            "debug_artifacts_enabled": mode.debugArtifactsEnabled,
        ]
    }

    public func writeEarlyFailureBundle(
        commandID: String,
        arguments: [String],
        errorMessage: String,
        traceID: String = ""
    ) throws -> URL {
        let bundleID = traceID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? "cli-failure-\(UUID().uuidString)"
            : traceID
        let root = melixHome.rootURL
            .appendingPathComponent("runs", isDirectory: true)
            .appendingPathComponent(bundleID, isDirectory: true)
            .appendingPathComponent("debug", isDirectory: true)
        try fileManager.createDirectory(
            at: root,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: MelixHome.directoryPermissions]
        )

        try writeText(
            MelixDiagnosticsRedaction.redactString((["melix"] + arguments).joined(separator: " ")) + "\n",
            to: root.appendingPathComponent("command.txt")
        )
        let redactedEnvironment = MelixDiagnosticsRedaction.redactEnvironment(environment)
        try writeJSON(redactedEnvironment.payload, to: root.appendingPathComponent("redacted-env.json"))
        let effectiveConfig: [String: Any] = [
            "schema_version": "melix.diagnostics.effective_config.v1",
            "command_id": commandID,
            "arguments": arguments,
            "early_failure": true,
        ]
        let redactedEffectiveConfig = MelixDiagnosticsRedaction.redactMapping(effectiveConfig)
        try writeJSON(redactedEffectiveConfig.payload, to: root.appendingPathComponent("effective-config.json"))
        var totalRedactedFieldCount = redactedEnvironment.redactedFieldCount
            + redactedEffectiveConfig.redactedFieldCount
        let systemPayload = MelixSystemDiagnostics.payload(
            melixHome: melixHome,
            environment: environment,
            redactedFieldCount: totalRedactedFieldCount
        )
        totalRedactedFieldCount = systemPayload["redacted_field_count"] as? Int ?? totalRedactedFieldCount
        try writeJSON(systemPayload, to: root.appendingPathComponent("system.json"))
        try writeJSON(
            MelixDiagnosticsRedaction.redactMapping([
                "schema_version": "melix.diagnostics.capability_receipts.v1",
                "command_id": commandID,
                "media_route_receipt": Self.defaultMediaRouteReceipt(),
                "artifacts": [],
                "known_gaps": ["Run failed before a persisted run record was available."],
                "probes": [],
            ]).payload,
            to: root.appendingPathComponent("capability-receipts.json")
        )
        try writeJSON(
            MelixDiagnosticsRedaction.redactMapping([
                "schema_version": "melix.diagnostics.memory_estimate.v1",
                "command_id": commandID,
                "resources": [:],
                "metrics": [],
            ]).payload,
            to: root.appendingPathComponent("memory-estimate.json")
        )
        try writeText("", to: root.appendingPathComponent("logs.txt"))
        try writeJSON(
            MelixDiagnosticsRedaction.redactMapping([
                "schema_version": "melix.diagnostics.metrics.v1",
                "command_id": commandID,
                "metrics": [],
            ]).payload,
            to: root.appendingPathComponent("metrics.json")
        )
        let redactedError = MelixDiagnosticsRedaction.redactMapping([
            "schema_version": "melix.diagnostics.error.v1",
            "command_id": commandID,
            "error": [
                "message": errorMessage,
            ],
        ])
        totalRedactedFieldCount += redactedError.redactedFieldCount
        try writeJSON(
            redactedError.payload,
            to: root.appendingPathComponent("error.json")
        )
        let manifest: [String: Any] = [
            "schema_version": "melix.diagnostics.bundle.v1",
            "bundle_id": bundleID,
            "created_at_unix_ms": currentUnixMilliseconds(),
            "diagnostics_consent_state": MelixSystemDiagnostics.diagnosticsConsentState,
            "probe_policy": Self.probePolicyPayload(environment: environment),
            "debug_artifact_policy": "early_failure_capture",
            "debug_jsonl_enabled": false,
            "debug_jsonl_event_limit": 0,
            "redaction_schema_version": MelixDiagnosticsRedaction.schemaVersion,
            "redacted_field_count": totalRedactedFieldCount,
            "command_id": commandID,
            "artifacts": [
                "command": "command.txt",
                "redacted_env": "redacted-env.json",
                "effective_config": "effective-config.json",
                "system": "system.json",
                "capability_receipts": "capability-receipts.json",
                "memory_estimate": "memory-estimate.json",
                "logs": "logs.txt",
                "metrics": "metrics.json",
                "error": "error.json",
            ],
        ]
        try writeJSON(manifest, to: root.appendingPathComponent("manifest.json"))
        return root
    }

    func monitorPayload(records: [MelixRunRecord]) -> [String: Any] {
        let recent = Array(records.prefix(20)).map { $0.summaryPayload() }
        let statusCounts = Dictionary(grouping: records, by: \.status)
            .mapValues(\.count)
        let redacted = MelixDiagnosticsRedaction.redactMapping([
            "recent_runs": recent,
            "logs_directory": melixHome.logsDirectoryURL.path,
        ])
        return [
            "schema_version": "melix.monitor.v1",
            "generated_at_unix_ms": currentUnixMilliseconds(),
            "diagnostics_consent_state": MelixSystemDiagnostics.diagnosticsConsentState,
            "redaction_schema_version": MelixDiagnosticsRedaction.schemaVersion,
            "redacted_field_count": redacted.redactedFieldCount,
            "run_count": records.count,
            "status_counts": statusCounts,
            "recent_runs": redacted.payload["recent_runs"] ?? recent,
            "logs_directory": redacted.payload["logs_directory"] ?? melixHome.logsDirectoryURL.path,
        ]
    }

    func logSnapshot(record: MelixRunRecord, follow: Bool) throws -> MelixLogSnapshot {
        let logURL = try resolveLogURL(record: record)
        let activeFollowSupported = follow && isActiveStatus(record.status)
        let text = try readLogText(from: logURL, follow: activeFollowSupported)
        return MelixLogSnapshot(
            runID: record.runID,
            sourcePath: record.path,
            logPath: logURL.path,
            followRequested: follow,
            activeFollowSupported: activeFollowSupported,
            text: MelixDiagnosticsRedaction.redactString(text)
        )
    }

    func resolvedLogPath(record: MelixRunRecord) -> String? {
        (try? resolveLogURL(record: record).path)
    }

    func writeDebugBundle(
        record: MelixRunRecord,
        outputPath: String = ""
    ) throws -> MelixDebugBundleResult {
        let root = bundleRoot(for: record.runID, outputPath: outputPath)
        try fileManager.createDirectory(
            at: root,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: MelixHome.directoryPermissions]
        )

        let redactedCommandText = MelixDiagnosticsRedaction.redactString(record.commandDisplay)
        try writeText(redactedCommandText + "\n", to: root.appendingPathComponent("command.txt"))

        let redactedEnvironment = MelixDiagnosticsRedaction.redactEnvironment(environment)
        try writeJSON(redactedEnvironment.payload, to: root.appendingPathComponent("redacted-env.json"))

        let redactedEffectiveConfig = MelixDiagnosticsRedaction.redactMapping([
            "schema_version": "melix.diagnostics.effective_config.v1",
            "run_record_path": record.path,
            "run_record": record.payload,
        ])
        try writeJSON(redactedEffectiveConfig.payload, to: root.appendingPathComponent("effective-config.json"))

        var totalRedacted = redactedEnvironment.redactedFieldCount
            + redactedEffectiveConfig.redactedFieldCount
            + (redactedCommandText == record.commandDisplay ? 0 : 1)
        let system = MelixSystemDiagnostics.payload(
            melixHome: melixHome,
            environment: environment,
            redactedFieldCount: totalRedacted
        )
        totalRedacted = system["redacted_field_count"] as? Int ?? totalRedacted
        try writeJSON(system, to: root.appendingPathComponent("system.json"))

        let capabilityReceipts: [String: Any] = [
            "schema_version": "melix.diagnostics.capability_receipts.v1",
            "run_id": record.runID,
            "media_route_receipt": Self.mediaRouteReceipt(for: record),
            "artifacts": record.artifacts,
            "known_gaps": record.knownGaps,
            "probes": record.payload["probes"] as? [[String: Any]] ?? [],
        ]
        let redactedCapabilityReceipts = MelixDiagnosticsRedaction.redactMapping(capabilityReceipts)
        totalRedacted += redactedCapabilityReceipts.redactedFieldCount
        try writeJSON(
            redactedCapabilityReceipts.payload,
            to: root.appendingPathComponent("capability-receipts.json")
        )

        let memoryEstimate: [String: Any] = [
            "schema_version": "melix.diagnostics.memory_estimate.v1",
            "run_id": record.runID,
            "resources": record.payload["resources"] as? [String: Any] ?? [:],
            "metrics": record.metrics.filter { stringField($0, "name").lowercased().contains("memory") },
        ]
        let redactedMemoryEstimate = MelixDiagnosticsRedaction.redactMapping(memoryEstimate)
        totalRedacted += redactedMemoryEstimate.redactedFieldCount
        try writeJSON(redactedMemoryEstimate.payload, to: root.appendingPathComponent("memory-estimate.json"))

        let logsText = (try? logSnapshot(record: record, follow: false).text) ?? ""
        try writeText(logsText, to: root.appendingPathComponent("logs.txt"))

        let metricsPayload: [String: Any] = [
            "schema_version": "melix.diagnostics.metrics.v1",
            "run_id": record.runID,
            "metrics": record.metrics,
        ]
        let redactedMetricsPayload = MelixDiagnosticsRedaction.redactMapping(metricsPayload)
        totalRedacted += redactedMetricsPayload.redactedFieldCount
        try writeJSON(redactedMetricsPayload.payload, to: root.appendingPathComponent("metrics.json"))

        let errorPayload: [String: Any] = [
            "schema_version": "melix.diagnostics.error.v1",
            "run_id": record.runID,
            "status": record.status,
            "error": record.status == "failed" || record.status == "error"
                ? (record.payload["error"] as? [String: Any] ?? ["message": "Run status was \(record.status)."])
                : NSNull(),
        ]
        let redactedErrorPayload = MelixDiagnosticsRedaction.redactMapping(errorPayload)
        totalRedacted += redactedErrorPayload.redactedFieldCount
        try writeJSON(
            redactedErrorPayload.payload,
            to: root.appendingPathComponent("error.json")
        )

        let redactedManifest = MelixDiagnosticsRedaction.redactMapping([
            "schema_version": "melix.diagnostics.bundle.v1",
            "bundle_id": record.runID,
            "created_at_unix_ms": currentUnixMilliseconds(),
            "diagnostics_consent_state": MelixSystemDiagnostics.diagnosticsConsentState,
            "media_route_receipt": Self.mediaRouteReceipt(for: record),
            "probe_policy": Self.probePolicyPayload(environment: environment),
            "debug_artifact_policy": "explicit_cli_command",
            "debug_jsonl_enabled": MelixProbeMode.fromEnvironment(environment).debugArtifactsEnabled,
            "debug_jsonl_event_limit": 256,
            "redaction_schema_version": MelixDiagnosticsRedaction.schemaVersion,
            "redacted_field_count": totalRedacted,
            "source_run_record_path": record.path,
            "artifacts": [
                "command": "command.txt",
                "redacted_env": "redacted-env.json",
                "effective_config": "effective-config.json",
                "system": "system.json",
                "capability_receipts": "capability-receipts.json",
                "memory_estimate": "memory-estimate.json",
                "logs": "logs.txt",
                "metrics": "metrics.json",
                "error": "error.json",
            ],
        ])
        totalRedacted += redactedManifest.redactedFieldCount
        var manifest = redactedManifest.payload
        manifest["redacted_field_count"] = totalRedacted
        try writeJSON(manifest, to: root.appendingPathComponent("manifest.json"))
        return MelixDebugBundleResult(bundleRoot: root, manifest: manifest)
    }

    private func resolveLogURL(record: MelixRunRecord) throws -> URL {
        let candidates = logCandidates(record: record)
        for url in candidates where fileManager.fileExists(atPath: url.path) {
            return url
        }
        throw MelixCLIError.runtime("No logs were found for \(record.runID). Checked: \(candidates.map(\.path).joined(separator: ", ")).")
    }

    private static func mediaRouteReceipt(for record: MelixRunRecord) -> [String: Any] {
        let target = record.payload["target"] as? [String: Any] ?? [:]
        let modelID = stringField(target, "model_id")
        let taskKind = stringField(target, "task_kind").lowercased()
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = modelID.isEmpty ? "melix-dev-text" : modelID
        model.kind = taskKind.contains("image") ? "image" : "text"
        model.supportedModalities = taskKind.contains("image") ? ["text", "image"] : ["text"]
        model.supportedTasks = taskKind.isEmpty ? ["generate"] : [taskKind]
        if taskKind.contains("image") {
            model.capabilityClass = .modelCapabilityImageGeneration
            model.routeClass = .workerRoutePythonImage
        } else {
            model.capabilityClass = .modelCapabilityText
            model.routeClass = .workerRouteSwiftText
        }
        return ModelCatalogPresentation.publicMediaRoutePayload(for: model)
    }

    private static func defaultMediaRouteReceipt() -> [String: Any] {
        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-text"
        model.kind = "text"
        model.capabilityClass = .modelCapabilityText
        model.routeClass = .workerRouteSwiftText
        model.supportedModalities = ["text"]
        model.supportedTasks = ["generate"]
        return ModelCatalogPresentation.publicMediaRoutePayload(for: model)
    }

    private func logCandidates(record: MelixRunRecord) -> [URL] {
        var candidates: [URL] = []
        func appendIfPresent(_ path: String) {
            let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
            guard trimmed.isEmpty == false else {
                return
            }
            candidates.append(URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath))
        }

        for artifact in record.artifacts {
            let kind = stringField(artifact, "kind").lowercased()
            let path = stringField(artifact, "path")
            if kind.contains("log") || path.lowercased().hasSuffix(".log") || path.lowercased().hasSuffix("logs.txt") {
                appendIfPresent(path)
            }
        }

        appendIfPresent(URL(fileURLWithPath: record.path).deletingLastPathComponent().appendingPathComponent("logs.txt").path)
        appendIfPresent(URL(fileURLWithPath: record.path).deletingLastPathComponent().appendingPathComponent("run.log").path)
        appendIfPresent(URL(fileURLWithPath: record.path).deletingLastPathComponent().appendingPathComponent("\(record.runID).log").path)
        appendIfPresent(melixHome.logsDirectoryURL.appendingPathComponent("\(record.runID).log").path)
        appendIfPresent(melixHome.logsDirectoryURL.appendingPathComponent("\(record.runID).txt").path)
        return uniqueURLs(candidates)
    }

    private func readLogText(from url: URL, follow: Bool) throws -> String {
        var data = try Data(contentsOf: url)
        guard follow else {
            return String(decoding: data, as: UTF8.self)
        }

        let deadline = Date().addingTimeInterval(1.0)
        var stablePolls = 0
        while Date() < deadline && stablePolls < 2 {
            Thread.sleep(forTimeInterval: 0.2)
            let next = try Data(contentsOf: url)
            if next.count > data.count {
                data = next
                stablePolls = 0
            } else {
                stablePolls += 1
            }
        }
        return String(decoding: data, as: UTF8.self)
    }

    private func isActiveStatus(_ status: String) -> Bool {
        switch status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "active", "in_progress", "in-progress", "pending", "processing", "queued", "running", "started":
            return true
        default:
            return false
        }
    }

    private func bundleRoot(for runID: String, outputPath: String) -> URL {
        let trimmed = outputPath.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty == false {
            return URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath, isDirectory: true)
        }
        return melixHome.rootURL
            .appendingPathComponent("runs", isDirectory: true)
            .appendingPathComponent(runID, isDirectory: true)
            .appendingPathComponent("debug", isDirectory: true)
    }

    private func writeJSON(_ payload: [String: Any], to url: URL) throws {
        var data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
        data.append(0x0a)
        try writeData(data, to: url)
    }

    private func writeText(_ text: String, to url: URL) throws {
        try writeData(Data(text.utf8), to: url)
    }

    private func writeData(_ data: Data, to url: URL) throws {
        try fileManager.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: MelixHome.directoryPermissions]
        )
        try data.write(to: url, options: [.atomic])
        try? fileManager.setAttributes([.posixPermissions: MelixHome.filePermissions], ofItemAtPath: url.path)
    }
}

private func uniqueURLs(_ urls: [URL]) -> [URL] {
    var seen: Set<String> = []
    var result: [URL] = []
    for url in urls {
        let path = url.standardizedFileURL.path
        if seen.insert(path).inserted {
            result.append(url)
        }
    }
    return result
}

private func currentUnixMilliseconds() -> Int {
    Int(Date().timeIntervalSince1970 * 1000)
}
