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

        return metadata.isEmpty ? nil : metadata
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
}
