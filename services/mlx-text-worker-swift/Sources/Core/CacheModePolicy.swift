import Foundation
import MelixWorkerProtocol

enum CacheModePolicy {
    static func resolve(from hints: Melix_Worker_V1_CacheHints) -> Melix_Worker_V1_CacheMode {
        if hints.cacheMode != .unspecified {
            return hints.cacheMode
        }

        let policy = hints.cachePolicy.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if policy.contains("rotating") {
            return .rotating
        }
        if policy.contains("hybrid") {
            return .hybrid
        }
        return .tiered
    }

    static func metricValue(for mode: Melix_Worker_V1_CacheMode) -> Int {
        switch mode {
        case .tiered:
            return 1
        case .rotating:
            return 2
        case .hybrid:
            return 3
        case .unspecified:
            fallthrough
        case .UNRECOGNIZED:
            fallthrough
        @unknown default:
            return 0
        }
    }

    static var supportedModes: [Melix_Worker_V1_CacheMode] {
        [.tiered, .rotating, .hybrid]
    }

    static var experimentalModes: [Melix_Worker_V1_CacheMode] {
        [.rotating, .hybrid]
    }
}
