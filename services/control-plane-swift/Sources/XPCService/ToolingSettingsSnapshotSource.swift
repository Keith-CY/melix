import Foundation
import MelixControlPlaneProtocol

struct ToolingSettingsSnapshotSource: Sendable {
    let additionalArguments: [String]
    let controlPlaneMetricsPath: String

    init(
        environment: [String: String],
        launchArguments: [String]
    ) {
        self.additionalArguments = Array(launchArguments.dropFirst()).map {
            $0.trimmingCharacters(in: .whitespacesAndNewlines)
        }.filter { !$0.isEmpty }
        self.controlPlaneMetricsPath = (environment["MELIX_CONTROL_PLANE_METRICS_PATH"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func summary(
        models: [Melix_Controlplane_V1_ModelSummary],
        mcpToolCatalog: MCPToolCatalog,
        gatewayConfigStorePath: String,
        gatewayServingDefaultsStorePath: String
    ) -> Melix_Controlplane_V1_ToolingSettingsSummary {
        var summary = Melix_Controlplane_V1_ToolingSettingsSummary()
        summary.embedding = resolvedEmbeddingSummary(from: models)
        summary.builtinToolParserModes = ToolParserRegistry().supportedModes().map(\.rawValue)
        summary.mcpDefaultParserMode = mcpToolCatalog.defaultParserMode.rawValue
        summary.mcpConfigPath = mcpToolCatalog.configPath
        summary.mcpEnabledSourceCount = mcpToolCatalog.enabledSourceCount
        summary.mcpResolvedToolCount = mcpToolCatalog.resolvedToolCount
        summary.configPaths = resolvedConfigPaths(
            gatewayConfigStorePath: gatewayConfigStorePath,
            gatewayServingDefaultsStorePath: gatewayServingDefaultsStorePath
        )
        summary.additionalArguments = additionalArguments
        return summary
    }

    private func resolvedEmbeddingSummary(
        from models: [Melix_Controlplane_V1_ModelSummary]
    ) -> Melix_Controlplane_V1_EmbeddingToolingSummary {
        let embeddingModels = models
            .filter { $0.kind == "embedding" || $0.capabilityClass == .modelCapabilityEmbedding }
            .sorted { lhs, rhs in
                let lhsLoaded = isLoaded(lhs)
                let rhsLoaded = isLoaded(rhs)
                if lhsLoaded != rhsLoaded {
                    return lhsLoaded && !rhsLoaded
                }
                let lhsPinned = lhs.pinned || lhs.residency.pinned
                let rhsPinned = rhs.pinned || rhs.residency.pinned
                if lhsPinned != rhsPinned {
                    return lhsPinned && !rhsPinned
                }
                return lhs.modelID < rhs.modelID
            }

        guard let model = embeddingModels.first else {
            return Melix_Controlplane_V1_EmbeddingToolingSummary()
        }

        var summary = Melix_Controlplane_V1_EmbeddingToolingSummary()
        summary.modelID = model.modelID
        summary.backendID = model.settings.ext["embedding_backend_id"] ?? ""
        summary.familyID = model.settings.ext["embedding_family_id"] ?? ""
        summary.routeClass = model.routeClass
        summary.modelState = model.state
        summary.loaded = isLoaded(model)
        summary.preloaded = summary.loaded
        summary.pinned = model.pinned || model.residency.pinned
        return summary
    }

    private func resolvedConfigPaths(
        gatewayConfigStorePath: String,
        gatewayServingDefaultsStorePath: String
    ) -> [Melix_Controlplane_V1_ToolingConfigPathSummary] {
        [
            configPath(id: "gateway_config_store_path", path: gatewayConfigStorePath),
            configPath(id: "gateway_serving_defaults_store_path", path: gatewayServingDefaultsStorePath),
            configPath(id: "control_plane_metrics_path", path: controlPlaneMetricsPath),
        ].filter { !$0.path.isEmpty }
    }

    private func configPath(
        id: String,
        path: String
    ) -> Melix_Controlplane_V1_ToolingConfigPathSummary {
        var summary = Melix_Controlplane_V1_ToolingConfigPathSummary()
        summary.pathID = id
        summary.path = path
        return summary
    }

    private func isLoaded(
        _ model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        switch model.state {
        case .modelWarm, .modelPinned:
            return true
        default:
            return false
        }
    }
}
