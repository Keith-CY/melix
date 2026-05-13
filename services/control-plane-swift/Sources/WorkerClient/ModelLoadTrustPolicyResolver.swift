import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

enum ModelLoadTrustPolicyResolver {
    static let defaultSafeSource = "default_safe"
    static let modelSettingsSource = "model_settings"
    static let notApplicableSource = "not_applicable"

    static func controlPlaneMode(
        from workerMode: Melix_Worker_V1_ModelLoadTrustMode
    ) -> Melix_Controlplane_V1_ModelLoadTrustMode {
        switch workerMode {
        case .modelLoadTrustDefaultSafe:
            return .modelLoadTrustDefaultSafe
        case .modelLoadTrustTrustRemoteCode:
            return .modelLoadTrustTrustRemoteCode
        case .modelLoadTrustNotApplicable:
            return .modelLoadTrustNotApplicable
        default:
            return .unspecified
        }
    }

    static func workerMode(
        from mode: Melix_Controlplane_V1_ModelLoadTrustMode
    ) -> Melix_Worker_V1_ModelLoadTrustMode {
        switch mode {
        case .modelLoadTrustDefaultSafe:
            return .modelLoadTrustDefaultSafe
        case .modelLoadTrustTrustRemoteCode:
            return .modelLoadTrustTrustRemoteCode
        case .modelLoadTrustNotApplicable:
            return .modelLoadTrustNotApplicable
        default:
            return .unspecified
        }
    }

    static func workerRouteClass(
        for route: WorkerRouteKind
    ) -> Melix_Worker_V1_WorkerRouteClass {
        switch route {
        case .swiftText:
            return .workerRouteSwiftText
        case .pythonCompatibility:
            return .workerRoutePythonTextCompatibility
        case .pythonEmbedding:
            return .workerRoutePythonEmbedding
        case .pythonRerank:
            return .workerRoutePythonRerank
        case .pythonModelOperations:
            return .workerRoutePythonModelOperations
        case .pythonOCR:
            return .workerRoutePythonOcr
        case .pythonVLM:
            return .workerRoutePythonVlm
        case .pythonTranscription:
            return .workerRoutePythonTranscription
        case .pythonSpeech:
            return .workerRoutePythonSpeech
        case .pythonImage:
            return .workerRoutePythonImage
        }
    }

    static func workerRouteClass(
        from routeClass: Melix_Controlplane_V1_WorkerRouteClass
    ) -> Melix_Worker_V1_WorkerRouteClass {
        switch routeClass {
        case .workerRouteSwiftText:
            return .workerRouteSwiftText
        case .workerRoutePythonTextCompatibility:
            return .workerRoutePythonTextCompatibility
        case .workerRoutePythonEmbedding:
            return .workerRoutePythonEmbedding
        case .workerRoutePythonRerank:
            return .workerRoutePythonRerank
        case .workerRoutePythonModelOperations:
            return .workerRoutePythonModelOperations
        case .workerRoutePythonOcr:
            return .workerRoutePythonOcr
        case .workerRoutePythonVlm:
            return .workerRoutePythonVlm
        case .workerRoutePythonTranscription:
            return .workerRoutePythonTranscription
        case .workerRoutePythonSpeech:
            return .workerRoutePythonSpeech
        case .workerRoutePythonImage:
            return .workerRoutePythonImage
        default:
            return .unspecified
        }
    }

    static func controlPlaneRouteClass(
        from routeClass: Melix_Worker_V1_WorkerRouteClass
    ) -> Melix_Controlplane_V1_WorkerRouteClass {
        switch routeClass {
        case .workerRouteSwiftText:
            return .workerRouteSwiftText
        case .workerRoutePythonTextCompatibility:
            return .workerRoutePythonTextCompatibility
        case .workerRoutePythonEmbedding:
            return .workerRoutePythonEmbedding
        case .workerRoutePythonRerank:
            return .workerRoutePythonRerank
        case .workerRoutePythonModelOperations:
            return .workerRoutePythonModelOperations
        case .workerRoutePythonOcr:
            return .workerRoutePythonOcr
        case .workerRoutePythonVlm:
            return .workerRoutePythonVlm
        case .workerRoutePythonTranscription:
            return .workerRoutePythonTranscription
        case .workerRoutePythonSpeech:
            return .workerRoutePythonSpeech
        case .workerRoutePythonImage:
            return .workerRoutePythonImage
        default:
            return .unspecified
        }
    }

    static func requestedMode(
        for settings: Melix_Controlplane_V1_ModelSettings
    ) -> Melix_Controlplane_V1_ModelLoadTrustMode {
        switch settings.loadTrustMode {
        case .modelLoadTrustDefaultSafe, .modelLoadTrustTrustRemoteCode:
            return settings.loadTrustMode
        default:
            return .modelLoadTrustDefaultSafe
        }
    }

    static func policySource(
        for settings: Melix_Controlplane_V1_ModelSettings
    ) -> String {
        switch settings.loadTrustMode {
        case .modelLoadTrustDefaultSafe, .modelLoadTrustTrustRemoteCode:
            return modelSettingsSource
        default:
            return defaultSafeSource
        }
    }

    static func resolvePolicy(
        for model: Melix_Controlplane_V1_ModelSummary,
        route: WorkerRouteKind
    ) -> Melix_Controlplane_V1_ModelLoadTrustPolicy {
        var policy = Melix_Controlplane_V1_ModelLoadTrustPolicy()
        policy.requestedMode = requestedMode(for: model.settings)
        policy.policySource = policySource(for: model.settings)
        policy.routeClass = route.routeClass
        policy.loaderFamily = route.metadataIdentifier

        if routeExecutesCustomPythonLoader(route) {
            policy.effectiveMode = policy.requestedMode
        } else {
            policy.effectiveMode = .modelLoadTrustNotApplicable
            policy.policySource = notApplicableSource
        }

        policy.customLoaderDetectionSource = "control_plane_route_resolution"
        policy.blockReason = ""
        policy.requiresReloadForTrustChange = false
        policy.customLoaderRequired = false
        policy.loaderFamily = route.metadataIdentifier
        return policy
    }

    static func workerPolicy(
        from policy: Melix_Controlplane_V1_ModelLoadTrustPolicy
    ) -> Melix_Worker_V1_ModelLoadTrustPolicy {
        var workerPolicy = Melix_Worker_V1_ModelLoadTrustPolicy()
        workerPolicy.requestedMode = workerMode(from: policy.requestedMode)
        workerPolicy.effectiveMode = workerMode(from: policy.effectiveMode)
        workerPolicy.policySource = policy.policySource
        workerPolicy.customLoaderRequired = policy.customLoaderRequired
        workerPolicy.customLoaderDetectionSource = policy.customLoaderDetectionSource
        workerPolicy.blockReason = policy.blockReason
        workerPolicy.requiresReloadForTrustChange = policy.requiresReloadForTrustChange
        workerPolicy.routeClass = workerRouteClass(from: policy.routeClass)
        workerPolicy.loaderFamily = policy.loaderFamily
        return workerPolicy
    }

    static func controlPlanePolicy(
        from workerPolicy: Melix_Worker_V1_ModelLoadTrustPolicy,
        fallback: Melix_Controlplane_V1_ModelLoadTrustPolicy
    ) -> Melix_Controlplane_V1_ModelLoadTrustPolicy {
        var policy = fallback
        let requestedMode = controlPlaneMode(from: workerPolicy.requestedMode)
        if requestedMode != .unspecified {
            policy.requestedMode = requestedMode
        }
        let effectiveMode = controlPlaneMode(from: workerPolicy.effectiveMode)
        if effectiveMode != .unspecified {
            policy.effectiveMode = effectiveMode
        }
        if !workerPolicy.policySource.isEmpty {
            policy.policySource = workerPolicy.policySource
        }
        policy.customLoaderRequired = workerPolicy.customLoaderRequired
        if !workerPolicy.customLoaderDetectionSource.isEmpty {
            policy.customLoaderDetectionSource = workerPolicy.customLoaderDetectionSource
        }
        if !workerPolicy.blockReason.isEmpty {
            policy.blockReason = workerPolicy.blockReason
        }
        policy.requiresReloadForTrustChange = workerPolicy.requiresReloadForTrustChange
        let routeClass = controlPlaneRouteClass(from: workerPolicy.routeClass)
        if routeClass != .unspecified {
            policy.routeClass = routeClass
        }
        if !workerPolicy.loaderFamily.isEmpty {
            policy.loaderFamily = workerPolicy.loaderFamily
        }
        return policy
    }

    static func receiptForLoadFailure(
        response: Melix_Worker_V1_LoadModelResponse,
        fallback: Melix_Controlplane_V1_ModelLoadTrustPolicy
    ) -> Melix_Controlplane_V1_ModelLoadTrustPolicy {
        var policy = response.hasLoadTrust
            ? controlPlanePolicy(from: response.loadTrust, fallback: fallback)
            : fallback
        if !response.error.code.isEmpty, policy.blockReason.isEmpty {
            policy.blockReason = response.error.code
        }
        return policy
    }

    static func reloadAwarePolicy(
        current policy: Melix_Controlplane_V1_ModelLoadTrustPolicy,
        settings: Melix_Controlplane_V1_ModelSettings,
        isLoaded: Bool
    ) -> Melix_Controlplane_V1_ModelLoadTrustPolicy {
        var updated = policy
        let requested = requestedMode(for: settings)
        updated.requestedMode = requested
        updated.policySource = policySource(for: settings)
        guard isLoaded else {
            updated.requiresReloadForTrustChange = false
            return updated
        }
        switch updated.effectiveMode {
        case .modelLoadTrustDefaultSafe, .modelLoadTrustTrustRemoteCode:
            updated.requiresReloadForTrustChange = updated.effectiveMode != requested
        default:
            updated.requiresReloadForTrustChange = false
        }
        return updated
    }

    static func mode(
        fromPolicyValue rawValue: String
    ) -> Melix_Controlplane_V1_ModelLoadTrustMode {
        let normalized = rawValue
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
            .replacingOccurrences(of: " ", with: "_")
        switch normalized {
        case "", "clear", "unset", "unspecified", "default":
            return .unspecified
        case "safe", "default_safe", "false", "0", "no", "off":
            return .modelLoadTrustDefaultSafe
        case "trust_remote_code", "remote_code", "trusted", "true", "1", "yes", "on":
            return .modelLoadTrustTrustRemoteCode
        case "not_applicable", "n/a", "na":
            return .modelLoadTrustNotApplicable
        default:
            return .unspecified
        }
    }

    private static func routeExecutesCustomPythonLoader(_ route: WorkerRouteKind) -> Bool {
        switch route {
        case .pythonCompatibility, .pythonModelOperations, .pythonOCR, .pythonVLM:
            return true
        default:
            return false
        }
    }
}
