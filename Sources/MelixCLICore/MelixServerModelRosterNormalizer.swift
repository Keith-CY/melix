import Foundation

public enum MelixServerModelRosterNormalizer {
    public static func normalized(
        _ modelIDs: [String],
        defaultModelID: String
    ) -> [String] {
        var ordered: [String] = []
        var seen: Set<String> = []
        for modelID in modelIDs.map(trimmed).filter({ !$0.isEmpty }) {
            guard seen.insert(modelID).inserted else {
                continue
            }
            ordered.append(modelID)
        }
        let defaultModelID = trimmed(defaultModelID)
        if !defaultModelID.isEmpty, !seen.contains(defaultModelID) {
            ordered.insert(defaultModelID, at: 0)
        }
        return ordered
    }

    public static func normalizedOrDefault(
        _ modelIDs: [String],
        defaultModelID: String
    ) -> [String] {
        // If both modelIDs and defaultModelID are empty, normalized() returns [].
        // The GatewayConfigStore strict validator (missingDefaultModelID /
        // missingServedModelIDs) is the authoritative gate that prevents an empty
        // roster from reaching the serving path; callers here are CLI/operator/desktop
        // state initialisation where a blank roster is treated as unconfigured.
        normalized(
            modelIDs.isEmpty ? [defaultModelID] : modelIDs,
            defaultModelID: defaultModelID
        )
    }

    public static func resolvedDefaultModelID(
        _ defaultModelID: String,
        servedModelIDs: [String]
    ) -> String {
        let t = trimmed(defaultModelID)
        guard t.isEmpty else { return t }
        return servedModelIDs.lazy.map(trimmed).first { !$0.isEmpty } ?? ""
    }

    private static func trimmed(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
