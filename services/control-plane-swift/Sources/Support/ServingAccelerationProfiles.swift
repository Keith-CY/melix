import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

public struct ServingAccelerationProfile: Equatable, Sendable {
    public let id: String
    public let label: String
    public let intent: String
    public let accelerationMode: Melix_Controlplane_V1_AccelerationMode
    public let draftModelID: String
    public let numDraftTokens: UInt32
    public let concurrentProcessingEnabled: Bool
    public let maxConcurrentRequests: UInt32
    public let prefillBatchSize: UInt32
    public let completionBatchSize: UInt32

    public init(
        id: String,
        label: String,
        intent: String,
        accelerationMode: Melix_Controlplane_V1_AccelerationMode,
        draftModelID: String,
        numDraftTokens: UInt32,
        concurrentProcessingEnabled: Bool,
        maxConcurrentRequests: UInt32,
        prefillBatchSize: UInt32,
        completionBatchSize: UInt32
    ) {
        self.id = id
        self.label = label
        self.intent = intent
        self.accelerationMode = accelerationMode
        self.draftModelID = draftModelID
        self.numDraftTokens = numDraftTokens
        self.concurrentProcessingEnabled = concurrentProcessingEnabled
        self.maxConcurrentRequests = maxConcurrentRequests
        self.prefillBatchSize = prefillBatchSize
        self.completionBatchSize = completionBatchSize
    }
}

public enum ServingAccelerationProfiles {
    public static let defaultProfileID = "balanced"

    public static let all: [ServingAccelerationProfile] = [
        ServingAccelerationProfile(
            id: "balanced",
            label: "Balanced",
            intent: "Default serving with baseline decode and moderate batching.",
            accelerationMode: .baseline,
            draftModelID: "",
            numDraftTokens: 0,
            concurrentProcessingEnabled: true,
            maxConcurrentRequests: 4,
            prefillBatchSize: 2,
            completionBatchSize: 2
        ),
        ServingAccelerationProfile(
            id: "throughput",
            label: "Throughput",
            intent: "Throughput-first serving with speculative decode when a draft model is supplied.",
            accelerationMode: .speculativeDecode,
            draftModelID: "",
            numDraftTokens: 6,
            concurrentProcessingEnabled: true,
            maxConcurrentRequests: 8,
            prefillBatchSize: 4,
            completionBatchSize: 4
        ),
        ServingAccelerationProfile(
            id: "low-memory",
            label: "Low Memory",
            intent: "Conservative single-request serving for constrained local memory.",
            accelerationMode: .baseline,
            draftModelID: "",
            numDraftTokens: 0,
            concurrentProcessingEnabled: false,
            maxConcurrentRequests: 1,
            prefillBatchSize: 1,
            completionBatchSize: 1
        ),
        ServingAccelerationProfile(
            id: "long-session",
            label: "Long Session",
            intent: "Repeated-session serving with bounded batching and baseline decode.",
            accelerationMode: .baseline,
            draftModelID: "",
            numDraftTokens: 0,
            concurrentProcessingEnabled: true,
            maxConcurrentRequests: 2,
            prefillBatchSize: 2,
            completionBatchSize: 1
        ),
    ]

    private static let profilesByID: [String: ServingAccelerationProfile] =
        Dictionary(uniqueKeysWithValues: all.map { ($0.id, $0) })

    public static var allowedProfileList: String {
        all.map(\.id).joined(separator: ", ")
    }

    public static func normalizeProfileID(_ rawValue: String?) -> String? {
        let normalized = rawValue?
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "_", with: "-") ?? ""
        guard normalized.isEmpty == false else {
            return nil
        }
        return profilesByID[normalized] == nil ? nil : normalized
    }

    public static func profile(id rawValue: String?) -> ServingAccelerationProfile {
        if let normalized = normalizeProfileID(rawValue),
           let profile = profilesByID[normalized] {
            return profile
        }
        return profilesByID[defaultProfileID]!
    }

    public static func controlPlaneAccelerationMode(rawValue: String) -> Melix_Controlplane_V1_AccelerationMode {
        switch rawValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
        case "speculative_decode":
            return .speculativeDecode
        case "accelerated_prefill":
            return .acceleratedPrefill
        case "active_kv_quantized":
            return .activeKvQuantized
        case "sparse_prefill":
            return .sparsePrefill
        case "baseline", "":
            return .baseline
        default:
            return .unspecified
        }
    }

    public static func controlPlaneRawValue(
        _ mode: Melix_Controlplane_V1_AccelerationMode
    ) -> String {
        switch mode {
        case .speculativeDecode:
            return "speculative_decode"
        case .acceleratedPrefill:
            return "accelerated_prefill"
        case .activeKvQuantized:
            return "active_kv_quantized"
        case .sparsePrefill:
            return "sparse_prefill"
        default:
            return "baseline"
        }
    }

    public static func workerRawValue(
        _ mode: Melix_Worker_V1_AccelerationMode
    ) -> String {
        switch mode {
        case .speculativeDecode:
            return "speculative_decode"
        case .acceleratedPrefill:
            return "accelerated_prefill"
        case .activeKvQuantized:
            return "active_kv_quantized"
        case .sparsePrefill:
            return "sparse_prefill"
        default:
            return "baseline"
        }
    }
}
