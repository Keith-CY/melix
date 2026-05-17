import Foundation
import MelixControlPlaneProtocol

public enum ModelCatalogPresentation {
    public static func isUserVisible(_ model: Melix_Controlplane_V1_ModelSummary) -> Bool {
        let visibility = normalized(model.settings.ext["melix.visibility"])
        if visibility == "internal" {
            return false
        }

        let kind = normalized(model.kind)
        if kind == "model_ops" || kind == "model_operations" {
            return false
        }

        if model.capabilityClass == .modelCapabilityModelOperations {
            return false
        }

        return true
    }

    public static func displayName(for model: Melix_Controlplane_V1_ModelSummary) -> String {
        let alias = model.settings.alias.trimmingCharacters(in: .whitespacesAndNewlines)
        return alias.isEmpty ? model.modelID : alias
    }

    public static func publicAPIMetadata(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> [String: String]? {
        var metadata = publicRegistryMetadata(from: model.settings.ext)

        let displayName = displayName(for: model).trimmingCharacters(in: .whitespacesAndNewlines)
        if !displayName.isEmpty {
            metadata["melix.display_name"] = displayName
        }

        let kind = model.kind.trimmingCharacters(in: .whitespacesAndNewlines)
        if !kind.isEmpty {
            metadata["melix.kind"] = kind
        }

        let capability = capabilityIdentifier(for: model)
        if !capability.isEmpty {
            metadata["melix.capability.class"] = capability
        }

        let supportedTasks = joinedPublicList(model.supportedTasks)
        if !supportedTasks.isEmpty {
            metadata["melix.capability.supported_tasks"] = supportedTasks
        }

        let supportedModalities = joinedPublicList(model.supportedModalities)
        if !supportedModalities.isEmpty {
            metadata["melix.capability.supported_modalities"] = supportedModalities
        }

        for (key, value) in loadTrustPublicMetadata(for: model) {
            metadata[key] = value
        }

        for (key, value) in capabilityReceiptPublicMetadata(for: model) {
            metadata[key] = value
        }

        return metadata.isEmpty ? nil : metadata
    }

    public static func capabilityReceiptPublicMetadata(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> [String: String] {
        let receipt = ModelCapabilityReceipts.receipt(for: model)
        var metadata: [String: String] = [
            "melix.capability.receipt_present": "true",
            "melix.capability.receipt_schema": receipt.schemaVersion,
            "melix.acceleration.requested_acceleration_mode": ModelCapabilityReceipts.accelerationModeIdentifier(
                receipt.acceleration.requestedAccelerationMode
            ),
            "melix.acceleration.resolved_acceleration_mode": ModelCapabilityReceipts.accelerationModeIdentifier(
                receipt.acceleration.resolvedAccelerationMode
            ),
            "melix.acceleration.supported_modes": receipt.acceleration.supportedModes
                .map(ModelCapabilityReceipts.accelerationModeIdentifier)
                .joined(separator: ","),
            "melix.acceleration.unsupported_reason": ModelCapabilityReceipts.unsupportedReasonIdentifier(
                receipt.acceleration.unsupportedReason
            ),
        ]
        if !receipt.acceleration.validDraftModelIds.isEmpty {
            metadata["melix.acceleration.valid_draft_model_ids"] = receipt.acceleration.validDraftModelIds
                .joined(separator: ",")
        }
        return metadata
    }

    public static func loadTrustPolicy(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Melix_Controlplane_V1_ModelLoadTrustPolicy {
        if model.hasLoadTrust {
            return model.loadTrust
        }

        var policy = Melix_Controlplane_V1_ModelLoadTrustPolicy()
        policy.requestedMode = requestedLoadTrustMode(for: model.settings)
        policy.routeClass = model.routeClass
        policy.loaderFamily = workerRouteIdentifier(for: model.routeClass)
        policy.customLoaderDetectionSource = "not_loaded"

        if routeExecutesCustomPythonLoader(model.routeClass) {
            policy.effectiveMode = policy.requestedMode
            policy.policySource = policySource(for: model.settings)
        } else {
            policy.effectiveMode = .modelLoadTrustNotApplicable
            policy.policySource = "not_applicable"
        }

        return policy
    }

    public static func loadTrustPublicMetadata(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> [String: String] {
        let policy = loadTrustPolicy(for: model)
        var metadata: [String: String] = [
            "melix.load_trust.receipt_present": model.hasLoadTrust ? "true" : "false",
            "melix.load_trust.requested_mode": loadTrustModeIdentifier(policy.requestedMode),
            "melix.load_trust.effective_mode": loadTrustModeIdentifier(policy.effectiveMode),
            "melix.load_trust.policy_source": policy.policySource,
            "melix.load_trust.custom_loader_required": policy.customLoaderRequired ? "true" : "false",
            "melix.load_trust.requires_reload": policy.requiresReloadForTrustChange ? "true" : "false",
        ]

        let route = workerRouteIdentifier(for: policy.routeClass)
        if route != "unspecified" {
            metadata["melix.load_trust.route_class"] = route
        }
        if !policy.loaderFamily.isEmpty {
            metadata["melix.load_trust.loader_family"] = policy.loaderFamily
        }
        if !policy.customLoaderDetectionSource.isEmpty {
            metadata["melix.load_trust.custom_loader_detection_source"] = policy.customLoaderDetectionSource
        }
        if !policy.blockReason.isEmpty {
            metadata["melix.load_trust.block_reason"] = policy.blockReason
        }

        return metadata
    }

    public static func loadTrustModeIdentifier(
        _ mode: Melix_Controlplane_V1_ModelLoadTrustMode
    ) -> String {
        switch mode {
        case .modelLoadTrustDefaultSafe:
            return "default_safe"
        case .modelLoadTrustTrustRemoteCode:
            return "trust_remote_code"
        case .modelLoadTrustNotApplicable:
            return "not_applicable"
        case .unspecified:
            return "unspecified"
        case .UNRECOGNIZED(let rawValue):
            return "unrecognized_\(rawValue)"
        }
    }

    public static func workerRouteIdentifier(
        for routeClass: Melix_Controlplane_V1_WorkerRouteClass
    ) -> String {
        if let route = WorkerRouteKind(routeClass: routeClass) {
            return route.metadataIdentifier
        }
        switch routeClass {
        case .unspecified:
            return "unspecified"
        case .UNRECOGNIZED(let rawValue):
            return "unrecognized_\(rawValue)"
        default:
            return "unspecified"
        }
    }

    public static func publicRegistryMetadata(from metadata: [String: String]) -> [String: String] {
        metadata.reduce(into: [String: String]()) { partial, item in
            let (key, rawValue) = item
            let value = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty else {
                return
            }

            if key.hasPrefix("melix.registry_") || key == "melix.model_path_missing" {
                partial[key] = value
                return
            }

            if key == "melix.model_path", shouldExposeModelPath(value) {
                partial[key] = value
            }
        }
    }

    public static func capabilityIdentifier(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> String {
        let explicit = model.settings.ext["melix.capability.class"]?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !explicit.isEmpty {
            return explicit
        }

        switch model.capabilityClass {
        case .modelCapabilityText:
            return "text"
        case .modelCapabilityEmbedding:
            return "embedding"
        case .modelCapabilityRerank:
            return "rerank"
        case .modelCapabilityModelOperations:
            return "model_operations"
        case .modelCapabilityMultimodal:
            return "multimodal"
        case .modelCapabilityOcr:
            return "ocr"
        case .modelCapabilityVlm:
            return "vlm"
        case .modelCapabilityTranscription:
            return "transcription"
        case .modelCapabilitySpeech:
            return "speech"
        case .modelCapabilityImageGeneration:
            return "image_generation"
        case .unspecified:
            return normalized(model.kind)
        case .UNRECOGNIZED:
            return normalized(model.kind)
        }
    }

    private static func joinedPublicList(_ values: [String]) -> String {
        values
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .joined(separator: ",")
    }

    private static func shouldExposeModelPath(_ value: String) -> Bool {
        !value.hasPrefix("models/melix-dev-")
    }

    private static func normalized(_ value: String?) -> String {
        value?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased() ?? ""
    }

    private static func requestedLoadTrustMode(
        for settings: Melix_Controlplane_V1_ModelSettings
    ) -> Melix_Controlplane_V1_ModelLoadTrustMode {
        switch settings.loadTrustMode {
        case .modelLoadTrustDefaultSafe, .modelLoadTrustTrustRemoteCode:
            return settings.loadTrustMode
        default:
            return .modelLoadTrustDefaultSafe
        }
    }

    private static func policySource(
        for settings: Melix_Controlplane_V1_ModelSettings
    ) -> String {
        switch settings.loadTrustMode {
        case .modelLoadTrustDefaultSafe, .modelLoadTrustTrustRemoteCode:
            return "model_settings"
        default:
            return "default_safe"
        }
    }

    private static func routeExecutesCustomPythonLoader(
        _ routeClass: Melix_Controlplane_V1_WorkerRouteClass
    ) -> Bool {
        switch routeClass {
        case .workerRoutePythonTextCompatibility,
             .workerRoutePythonModelOperations,
             .workerRoutePythonOcr,
             .workerRoutePythonVlm:
            return true
        default:
            return false
        }
    }
}
