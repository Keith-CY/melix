import Dispatch
import Foundation

private enum MelixCookbookHostPlatformSource: String {
    case hardwareProbe = "hardware_probe"
    case explicitOperatorSetting = "explicit_operator_setting"
    case browserFallback = "browser_fallback"
    case unavailable
}

private struct MelixCookbookHostSelection {
    let platform: String
    let arch: String
    let source: MelixCookbookHostPlatformSource
    let warnings: [String]
}

private struct MelixCookbookBackendRecommendation {
    let selectedBackend: String
    let commandFamily: String
}

private struct MelixCookbookStateReceipt {
    let dataRoot: String
    let statePath: String
    let cacheEnabled: Bool
    let disabledReason: String

    var payload: [String: Any] {
        [
            "data_root": dataRoot,
            "state_path": statePath,
            "cache_enabled": cacheEnabled,
            "disabled_reason": disabledReason,
        ]
    }
}

private struct MelixCookbookEvidenceReceipt {
    let fitReceiptSchemaVersion: String
    let fitReceiptSource: String
    let profileReceiptSchemaVersion: String
    let profileReceiptSource: String
    let benchmarkReceipts: [String]
    let missingReceipts: [String]
    let effectiveConfigPath: String

    var payload: [String: Any] {
        [
            "fit_receipt_schema_version": fitReceiptSchemaVersion,
            "fit_receipt_source": fitReceiptSource,
            "profile_receipt_schema_version": profileReceiptSchemaVersion,
            "profile_receipt_source": profileReceiptSource,
            "benchmark_receipts": benchmarkReceipts,
            "missing_receipts": missingReceipts,
            "effective_config_path": effectiveConfigPath,
        ]
    }
}

private enum MelixCookbookRecommendationPlanner {
    static let browserFallbackWarning =
        "Browser platform hints may describe the UI client rather than the Melix serving host."
    static let unavailableWarning =
        "No host platform source was available; run a Melix hardware probe before relying on this recommendation."

    static func makePayload(options: CookbookRecommendOptions, melixHome: MelixHome, planMS: Double) -> [String: Any] {
        let host = selectHost(options)
        let backend = recommendBackend(for: host)
        let state = makeStateReceipt(melixHome: melixHome)
        let evidence = makeEvidenceReceipt(options: options, host: host, melixHome: melixHome)
        return [
            "schema_version": "melix.cookbook.recommendation.v1",
            "model_id": trimmedString(options.modelID),
            "workload": trimmedString(options.workload),
            "host": [
                "platform": host.platform,
                "arch": host.arch,
                "host_platform_source": host.source.rawValue,
            ],
            "recommendation": [
                "selected_backend": backend.selectedBackend,
                "command_family": backend.commandFamily,
            ],
            "state": state.payload,
            "evidence": evidence.payload,
            "warnings": host.warnings,
            "probe": [
                "name": "cookbook.host_source_selection",
                "cookbook.plan_ms": NSNumber(value: planMS),
            ],
        ]
    }

    static func makeText(options: CookbookRecommendOptions, melixHome: MelixHome, planMS: Double) -> String {
        let host = selectHost(options)
        let backend = recommendBackend(for: host)
        let state = makeStateReceipt(melixHome: melixHome)
        let evidence = makeEvidenceReceipt(options: options, host: host, melixHome: melixHome)
        let hostDisplay = host.platform.isEmpty
            ? "unavailable (\(host.source.rawValue))"
            : "\(host.platform)/\(host.arch) (\(host.source.rawValue))"
        var lines = [
            "Melix cookbook recommendation",
            "Model: \(trimmedString(options.modelID))",
            "Workload: \(trimmedString(options.workload))",
            "Host: \(hostDisplay)",
            "Backend: \(backend.selectedBackend)",
            "Command family: \(backend.commandFamily)",
            "Data root: \(state.dataRoot)",
            "State path: \(state.statePath)",
            "Cache enabled: \(state.cacheEnabled)",
            "Fit evidence: \(evidence.fitReceiptSource) (\(evidence.fitReceiptSchemaVersion))",
            "Profile evidence: \(evidence.profileReceiptSource) (\(evidence.profileReceiptSchemaVersion))",
            "Effective config: \(displayPath(evidence.effectiveConfigPath))",
            "Benchmark receipts: \(displayList(evidence.benchmarkReceipts))",
            "Missing receipts: \(displayList(evidence.missingReceipts))",
        ]
        if state.disabledReason.isEmpty == false {
            lines.append("Cache disabled reason: \(state.disabledReason)")
        }
        for warning in host.warnings {
            lines.append("Warning: \(warning)")
        }
        return lines.joined(separator: "\n") + "\n"
    }

    private static func makeStateReceipt(melixHome: MelixHome) -> MelixCookbookStateReceipt {
        let cookbookURL = melixHome.stateDirectoryURL.appendingPathComponent("cookbook", isDirectory: true)
        let statePath = cookbookURL.appendingPathComponent("recommendations.json")
        var isDirectory = ObjCBool(false)
        let exists = FileManager.default.fileExists(atPath: melixHome.stateDirectoryURL.path, isDirectory: &isDirectory)
        let disabledReason: String
        if exists == false {
            disabledReason = "state_root_missing"
        } else if isDirectory.boolValue == false {
            disabledReason = "state_root_not_directory"
        } else if FileManager.default.isWritableFile(atPath: melixHome.stateDirectoryURL.path) == false {
            disabledReason = "state_root_not_writable"
        } else {
            var cookbookIsDirectory = ObjCBool(false)
            let cookbookExists = FileManager.default.fileExists(atPath: cookbookURL.path, isDirectory: &cookbookIsDirectory)
            if cookbookExists == false {
                disabledReason = ""
            } else if cookbookIsDirectory.boolValue == false {
                disabledReason = "state_path_not_directory"
            } else if FileManager.default.isWritableFile(atPath: cookbookURL.path) == false {
                disabledReason = "state_path_not_writable"
            } else {
                disabledReason = ""
            }
        }
        return MelixCookbookStateReceipt(
            dataRoot: melixHome.rootURL.path,
            statePath: statePath.path,
            cacheEnabled: disabledReason.isEmpty,
            disabledReason: disabledReason
        )
    }

    private static func makeEvidenceReceipt(
        options: CookbookRecommendOptions,
        host: MelixCookbookHostSelection,
        melixHome: MelixHome
    ) -> MelixCookbookEvidenceReceipt {
        let effectiveConfigPath = matchingEffectiveConfigURL(
            options: options,
            host: host,
            melixHome: melixHome
        )?.path ?? ""
        var missingReceipts = ["effective_config", "benchmark_receipt", "model_fit_receipt"]
        if effectiveConfigPath.isEmpty == false {
            missingReceipts.removeAll { $0 == "effective_config" }
        }
        return MelixCookbookEvidenceReceipt(
            fitReceiptSchemaVersion: "melix.memory_fit_receipt.v1",
            fitReceiptSource: "cookbook.host_selection",
            profileReceiptSchemaVersion: "melix.cookbook.profile_receipt.v1",
            profileReceiptSource: "cookbook.backend_selection",
            benchmarkReceipts: [],
            missingReceipts: missingReceipts,
            effectiveConfigPath: effectiveConfigPath
        )
    }

    private static func matchingEffectiveConfigURL(
        options: CookbookRecommendOptions,
        host: MelixCookbookHostSelection,
        melixHome: MelixHome
    ) -> URL? {
        let root = melixHome.stateDirectoryURL
            .appendingPathComponent("cookbook", isDirectory: true)
            .appendingPathComponent("evidence", isDirectory: true)
            .appendingPathComponent("effective-configs", isDirectory: true)
        let urls = (try? FileManager.default.contentsOfDirectory(
            at: root,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        )) ?? []
        return urls
            .filter { $0.pathExtension.lowercased() == "json" }
            .sorted { $0.path < $1.path }
            .first { effectiveConfig(at: $0, matches: options, host: host) }
            // Preserve MELIX_HOME spelling instead of FileManager's resolved /private/var paths.
            .map { root.appendingPathComponent($0.lastPathComponent) }
    }

    private static func effectiveConfig(
        at url: URL,
        matches options: CookbookRecommendOptions,
        host: MelixCookbookHostSelection
    ) -> Bool {
        guard let resourceValues = try? url.resourceValues(forKeys: [.isRegularFileKey]),
              resourceValues.isRegularFile == true,
              let data = try? Data(contentsOf: url)
        else {
            return false
        }
        let jsonObject = try? JSONSerialization.jsonObject(with: data)
        guard let payload = jsonObject as? [String: Any],
              nonEmpty(payload["schema_version"] as? String ?? "") != nil,
              let modelID = payload["model_id"] as? String,
              !trimmedString(modelID).isEmpty,
              trimmedString(modelID) == trimmedString(options.modelID),
              let workload = payload["workload"] as? String,
              !trimmedString(workload).isEmpty,
              trimmedString(workload) == trimmedString(options.workload),
              let hostPayload = payload["host"] as? [String: Any]
        else {
            return false
        }
        return trimmedString(hostPayload["platform"] as? String ?? "") == host.platform
            && trimmedString(hostPayload["arch"] as? String ?? "") == host.arch
            && trimmedString(hostPayload["host_platform_source"] as? String ?? "") == host.source.rawValue
    }

    private static func selectHost(_ options: CookbookRecommendOptions) -> MelixCookbookHostSelection {
        if let platform = nonEmpty(options.serverPlatform) {
            return MelixCookbookHostSelection(
                platform: normalizePlatform(platform),
                arch: normalizeArch(options.serverArch),
                source: .hardwareProbe,
                warnings: []
            )
        }
        if let platform = nonEmpty(options.operatorPlatform) {
            return MelixCookbookHostSelection(
                platform: normalizePlatform(platform),
                arch: normalizeArch(options.operatorArch),
                source: .explicitOperatorSetting,
                warnings: []
            )
        }
        if let platform = nonEmpty(options.browserPlatform) {
            return MelixCookbookHostSelection(
                platform: normalizePlatform(platform),
                arch: normalizeArch(options.browserArch),
                source: .browserFallback,
                warnings: [browserFallbackWarning]
            )
        }
        return MelixCookbookHostSelection(
            platform: "",
            arch: "",
            source: .unavailable,
            warnings: [unavailableWarning]
        )
    }

    private static func recommendBackend(for host: MelixCookbookHostSelection) -> MelixCookbookBackendRecommendation {
        if host.platform == "macos", ["arm64", "arm64e"].contains(host.arch) {
            return MelixCookbookBackendRecommendation(
                selectedBackend: "mlx-native",
                commandFamily: "melix server start"
            )
        }
        if host.platform == "linux" {
            return MelixCookbookBackendRecommendation(
                selectedBackend: "python-worker",
                commandFamily: "melix server start"
            )
        }
        return MelixCookbookBackendRecommendation(
            selectedBackend: "generic-local-runtime",
            commandFamily: "melix server start"
        )
    }

    private static func normalizePlatform(_ value: String) -> String {
        switch normalizedString(value) {
        case "darwin", "mac", "macos", "macosx", "osx":
            return "macos"
        case "win", "win32", "windows":
            return "windows"
        default:
            return normalizedString(value)
        }
    }

    private static func normalizeArch(_ value: String) -> String {
        switch normalizedString(value) {
        case "aarch64":
            return "arm64"
        default:
            return normalizedString(value)
        }
    }

    private static func nonEmpty(_ value: String) -> String? {
        let normalized = normalizedString(value)
        return normalized.isEmpty ? nil : normalized
    }

    private static func normalizedString(_ value: String) -> String {
        trimmedString(value).lowercased()
    }

    private static func trimmedString(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func displayList(_ values: [String]) -> String {
        values.isEmpty ? "none" : values.joined(separator: ", ")
    }

    private static func displayPath(_ value: String) -> String {
        value.isEmpty ? "none" : value
    }
}

extension MelixCLIRunner {
    func runCookbookRecommend(_ options: CookbookRecommendOptions) throws -> String {
        let startedAt = DispatchTime.now()
        let melixHome = MelixHome(environment: environment)
        let planMS = elapsedMilliseconds(since: startedAt)
        if options.json {
            let payload = MelixCookbookRecommendationPlanner.makePayload(
                options: options,
                melixHome: melixHome,
                planMS: planMS
            )
            return try MelixCLIJSON.prettyString(payload)
        }
        return MelixCookbookRecommendationPlanner.makeText(options: options, melixHome: melixHome, planMS: planMS)
    }
}
