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

private enum MelixCookbookRecommendationPlanner {
    static let browserFallbackWarning =
        "Browser platform hints may describe the UI client rather than the Melix serving host."
    static let unavailableWarning =
        "No host platform source was available; run a Melix hardware probe before relying on this recommendation."

    static func makePayload(options: CookbookRecommendOptions, planMS: Double) -> [String: Any] {
        let host = selectHost(options)
        let backend = recommendBackend(for: host)
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
            "warnings": host.warnings,
            "probe": [
                "name": "cookbook.host_source_selection",
                "cookbook.plan_ms": NSNumber(value: planMS),
            ],
        ]
    }

    static func makeText(options: CookbookRecommendOptions, planMS: Double) -> String {
        let host = selectHost(options)
        let backend = recommendBackend(for: host)
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
        ]
        for warning in host.warnings {
            lines.append("Warning: \(warning)")
        }
        return lines.joined(separator: "\n") + "\n"
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
}

extension MelixCLIRunner {
    func runCookbookRecommend(_ options: CookbookRecommendOptions) throws -> String {
        let startedAt = DispatchTime.now()
        let planMS = elapsedMilliseconds(since: startedAt)
        if options.json {
            let payload = MelixCookbookRecommendationPlanner.makePayload(options: options, planMS: planMS)
            return try MelixCLIJSON.prettyString(payload)
        }
        return MelixCookbookRecommendationPlanner.makeText(options: options, planMS: planMS)
    }
}
