import Foundation

public enum MelixServeableModelRules {
    public static func isServeable(
        kind rawKind: String,
        features rawFeatures: [String] = []
    ) -> Bool {
        let kind = rawKind.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if ["ocr", "speech", "transcription", "image", "image_generation"].contains(kind) {
            return false
        }
        if kind == "text" || kind == "vlm" {
            return true
        }

        let features = Set(rawFeatures.map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() })
        let hasServeableFeature = features.contains("text") || features.contains("chat") || features.contains("vlm")
        let hasExcludedFeature = features.contains("ocr")
            || features.contains("speech")
            || features.contains("transcription")
            || features.contains("image_generation")
        return hasServeableFeature && !hasExcludedFeature
    }
}
