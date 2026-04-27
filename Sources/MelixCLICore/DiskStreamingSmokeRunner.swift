import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol

public enum DiskStreamingSmokeRunnerError: Error, Equatable {
    case missingModel(String)
}

public struct DiskStreamingSmokeBaselineReport: Encodable, Equatable, Sendable {
    public let reportPath: String
    public let metrics: [String: Double]

    public init(reportPath: String, metrics: [String: Double]) {
        self.reportPath = reportPath
        self.metrics = metrics
    }
}

public struct DiskStreamingSmokeScenarioReport: Encodable, Equatable, Sendable {
    public let requestedMode: String
    public let effectiveMode: String
    public let errorCode: String
    public let transitionReason: String
    public let cacheCompatibility: String
    public let cacheCompatibilityReason: String

    public init(
        requestedMode: String,
        effectiveMode: String,
        errorCode: String,
        transitionReason: String,
        cacheCompatibility: String,
        cacheCompatibilityReason: String
    ) {
        self.requestedMode = requestedMode
        self.effectiveMode = effectiveMode
        self.errorCode = errorCode
        self.transitionReason = transitionReason
        self.cacheCompatibility = cacheCompatibility
        self.cacheCompatibilityReason = cacheCompatibilityReason
    }
}

public struct DiskStreamingSmokeCapabilityReport: Encodable, Equatable, Sendable {
    public let runtimeSupportsDiskStreaming: Bool
    public let cacheCompatibility: String
    public let cacheCompatibilityReason: String

    public init(
        runtimeSupportsDiskStreaming: Bool,
        cacheCompatibility: String,
        cacheCompatibilityReason: String
    ) {
        self.runtimeSupportsDiskStreaming = runtimeSupportsDiskStreaming
        self.cacheCompatibility = cacheCompatibility
        self.cacheCompatibilityReason = cacheCompatibilityReason
    }
}

public struct DiskStreamingSmokeReport: Encodable, Equatable, Sendable {
    public let ok: Bool
    public let modelID: String
    public let baseline: DiskStreamingSmokeBaselineReport
    public let streamingPreferDisk: DiskStreamingSmokeScenarioReport
    public let streamingRequireDisk: DiskStreamingSmokeScenarioReport
    public let capability: DiskStreamingSmokeCapabilityReport
    public let futureMetrics: [String: String]

    public init(
        ok: Bool,
        modelID: String,
        baseline: DiskStreamingSmokeBaselineReport,
        streamingPreferDisk: DiskStreamingSmokeScenarioReport,
        streamingRequireDisk: DiskStreamingSmokeScenarioReport,
        capability: DiskStreamingSmokeCapabilityReport,
        futureMetrics: [String: String]
    ) {
        self.ok = ok
        self.modelID = modelID
        self.baseline = baseline
        self.streamingPreferDisk = streamingPreferDisk
        self.streamingRequireDisk = streamingRequireDisk
        self.capability = capability
        self.futureMetrics = futureMetrics
    }
}

public struct DiskStreamingSmokeRunner: Sendable {
    public let client: any ControlPlaneXPCClient

    public init(client: any ControlPlaneXPCClient) {
        self.client = client
    }

    public func run(modelID: String = "melix-dev-text") async throws -> DiskStreamingSmokeReport {
        let originalModel = try await fetchModel(modelID: modelID)
        let originalMode = diskStreamingModeLabel(originalModel.settings.diskStreamingMode)

        do {
            _ = try? await client.unloadModel(modelID: modelID)
            _ = try await client.updateModelSettings(
                modelID: modelID,
                values: ["disk_streaming_mode": "disabled"]
            )
            let baselineBench = try await client.runBench(
                ControlPlaneBenchRequest(
                    modelID: modelID,
                    suites: ["smoke"],
                    contextLengths: [128],
                    generationLength: 8,
                    batchSizes: [1],
                    repeats: 1,
                    cacheProfile: "cold",
                    reasoningMode: "off",
                    structuredOutputMode: "off",
                    parameters: baselineBenchParameters(modelID: modelID)
                )
            )

            let preferDisk = try await runUnsupportedScenario(modelID: modelID, requestedMode: "prefer_disk")
            let requireDisk = try await runUnsupportedScenario(modelID: modelID, requestedMode: "require_disk")
            let capability = DiskStreamingSmokeCapabilityReport(
                runtimeSupportsDiskStreaming: preferDisk.errorCode != "disk_streaming_unsupported"
                    || requireDisk.errorCode != "disk_streaming_unsupported",
                cacheCompatibility: preferDisk.cacheCompatibility,
                cacheCompatibilityReason: preferDisk.cacheCompatibilityReason
            )

            _ = try? await client.updateModelSettings(
                modelID: modelID,
                values: ["disk_streaming_mode": originalMode]
            )

            return DiskStreamingSmokeReport(
                ok: true,
                modelID: modelID,
                baseline: DiskStreamingSmokeBaselineReport(
                    reportPath: baselineBench.reportPath,
                    metrics: baselineBench.metrics
                ),
                streamingPreferDisk: preferDisk,
                streamingRequireDisk: requireDisk,
                capability: capability,
                futureMetrics: [
                    "ssd_restore_latency_ms": "unavailable_until_runtime_support",
                    "disk_streaming_throughput_delta": "unavailable_until_runtime_support",
                    "ssd_footprint_bytes": "unavailable_until_runtime_support",
                ]
            )
        } catch {
            _ = try? await client.updateModelSettings(
                modelID: modelID,
                values: ["disk_streaming_mode": originalMode]
            )
            throw error
        }
    }

    private func runUnsupportedScenario(
        modelID: String,
        requestedMode: String
    ) async throws -> DiskStreamingSmokeScenarioReport {
        _ = try? await client.unloadModel(modelID: modelID)
        _ = try await client.updateModelSettings(
            modelID: modelID,
            values: ["disk_streaming_mode": requestedMode]
        )

        var errorCode = ""
        var transitionReason = ""
        do {
            _ = try await client.loadModel(modelID: modelID)
        } catch let error as ControlPlaneXPCClientError {
            switch error {
            case let .requestFailed(code, _):
                errorCode = code
            }
        }

        let model = try await fetchModel(modelID: modelID)
        transitionReason = model.residency.transitionReason
        if transitionReason.isEmpty, errorCode == "disk_streaming_unsupported" {
            transitionReason = "operator_load_disk_streaming_unsupported"
        }
        let cacheCompatibility = resolvedUnsupportedCacheCompatibility(
            requestedMode: requestedMode,
            observedCompatibility: cacheCompatibilityLabel(model.cachePolicy.compatibility),
            errorCode: errorCode
        )
        let cacheCompatibilityReason = resolvedUnsupportedCacheCompatibilityReason(
            observedReason: model.cachePolicy.compatibilityReason,
            errorCode: errorCode
        )

        return DiskStreamingSmokeScenarioReport(
            requestedMode: requestedMode,
            effectiveMode: diskStreamingModeLabel(model.residency.effectiveDiskStreamingMode),
            errorCode: errorCode,
            transitionReason: transitionReason,
            cacheCompatibility: cacheCompatibility,
            cacheCompatibilityReason: cacheCompatibilityReason
        )
    }

    private func fetchModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        let snapshot = try await client.serverSnapshot()
        if let model = snapshot.models.first(where: { $0.modelID == modelID }) {
            return model
        }
        throw DiskStreamingSmokeRunnerError.missingModel(modelID)
    }
}

private func baselineBenchParameters(modelID: String) -> [String: String] {
    // Melix dev aliases are repository-owned deterministic fixtures for smoke tests.
    // User-imported and external models should keep the real runtime path unless explicitly opted in.
    guard modelID.hasPrefix("melix-dev-") else {
        return [:]
    }
    return ["allow_deterministic_runtime": "true"]
}

func resolvedUnsupportedCacheCompatibility(
    requestedMode: String,
    observedCompatibility: String,
    errorCode: String
) -> String {
    guard errorCode == "disk_streaming_unsupported", observedCompatibility == "unknown" else {
        return observedCompatibility
    }

    switch requestedMode {
    case "require_disk":
        return "disabled"
    case "prefer_disk":
        return "limited"
    default:
        return observedCompatibility
    }
}

func resolvedUnsupportedCacheCompatibilityReason(
    observedReason: String,
    errorCode: String
) -> String {
    guard errorCode == "disk_streaming_unsupported" else {
        return observedReason
    }

    let trimmedReason = observedReason.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmedReason.isEmpty || trimmedReason == "worker cache compatibility evidence is unavailable"
        ? "disk_streaming_unsupported"
        : trimmedReason
}

func diskStreamingModeLabel(_ mode: Melix_Controlplane_V1_DiskStreamingMode) -> String {
    switch mode {
    case .diskStreamingPreferDisk:
        return "prefer_disk"
    case .diskStreamingRequireDisk:
        return "require_disk"
    default:
        return "disabled"
    }
}

func cacheCompatibilityLabel(_ value: Melix_Controlplane_V1_CacheCompatibilityState) -> String {
    switch value {
    case .cacheCompatibilityCompatible:
        return "compatible"
    case .cacheCompatibilityLimited:
        return "limited"
    case .cacheCompatibilityDisabled:
        return "disabled"
    default:
        return "unknown"
    }
}
