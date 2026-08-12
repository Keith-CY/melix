import Foundation

public enum BrokerTransportConfigurationError: Error, Sendable, Equatable {
    case invalidValue(String)
}

extension BrokerTransportConfigurationError: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case let .invalidValue(message): message
        }
    }
}

/// A shared-secret bootstrap check for the first transport slice.
///
/// This verifies configured protocol, bundle, team, and capability values. It
/// is intentionally not described as a code-signing identity check: gRPC Swift
/// does not expose the Unix peer's macOS audit token through `ServerContext`.
/// The final broker must additionally verify that audit token before treating a
/// peer as the configured signed control-plane process.
public struct BrokerHandshakePolicy: Sendable, Equatable {
    public let protocolVersion: String
    public let expectedCallerBundleID: String
    public let expectedCallerTeamID: String
    public let verificationCapability: Data

    public init(
        protocolVersion: String,
        expectedCallerBundleID: String,
        expectedCallerTeamID: String,
        verificationCapability: Data
    ) throws {
        let protocolVersion = protocolVersion.trimmingCharacters(in: .whitespacesAndNewlines)
        let bundleID = expectedCallerBundleID.trimmingCharacters(in: .whitespacesAndNewlines)
        let teamID = expectedCallerTeamID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !protocolVersion.isEmpty else {
            throw BrokerTransportConfigurationError.invalidValue(
                "Computer Use protocol version must be non-empty."
            )
        }
        guard !bundleID.isEmpty, !teamID.isEmpty else {
            throw BrokerTransportConfigurationError.invalidValue(
                "Computer Use caller bundle and team identifiers must be non-empty."
            )
        }
        guard verificationCapability.count >= 32, verificationCapability.count <= 4_096 else {
            throw BrokerTransportConfigurationError.invalidValue(
                "Computer Use verification capability must contain between 32 and 4096 bytes."
            )
        }
        self.protocolVersion = protocolVersion
        self.expectedCallerBundleID = bundleID
        self.expectedCallerTeamID = teamID
        self.verificationCapability = verificationCapability
    }
}

public struct BrokerTransportConfiguration: Sendable, Equatable {
    public let handshake: BrokerHandshakePolicy
    public let toolAuthorizationVerifier: BrokerToolAuthorizationVerifier
    public let brokerVersion: String
    public let brokerInstanceID: String
    public let artifactRoot: URL
    public let features: [String]

    public init(
        handshake: BrokerHandshakePolicy,
        toolAuthorizationVerifier: BrokerToolAuthorizationVerifier,
        brokerVersion: String,
        brokerInstanceID: String,
        artifactRoot: URL,
        features: [String] = [
            "trusted_window_discovery",
            "screen_capture_window",
            "ax_semantic_press",
            "action_surface_semantic_press_only",
            "set_text_unsupported",
            "key_press_unsupported",
            "scroll_unsupported",
            "pointer_unsupported",
            "coordinate_fallback_disabled",
            "cancel_commit_boundary",
            "cancel_session",
            "evidence_receipts",
            "transport_private_uds",
            "transport_peer_code_identity_unavailable",
            "signed_tool_authorization",
        ]
    ) throws {
        let brokerVersion = brokerVersion.trimmingCharacters(in: .whitespacesAndNewlines)
        let brokerInstanceID = brokerInstanceID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !brokerVersion.isEmpty, !brokerInstanceID.isEmpty else {
            throw BrokerTransportConfigurationError.invalidValue(
                "Computer Use broker version and instance identifier must be non-empty."
            )
        }
        guard artifactRoot.path.hasPrefix("/") else {
            throw BrokerTransportConfigurationError.invalidValue(
                "Computer Use artifact root must be absolute."
            )
        }
        let artifactRoot = artifactRoot.standardizedFileURL
        guard !features.isEmpty,
              features.allSatisfy({ !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty })
        else {
            throw BrokerTransportConfigurationError.invalidValue(
                "Computer Use feature names must be non-empty."
            )
        }
        self.handshake = handshake
        self.toolAuthorizationVerifier = toolAuthorizationVerifier
        self.brokerVersion = brokerVersion
        self.brokerInstanceID = brokerInstanceID
        self.artifactRoot = artifactRoot
        self.features = features
    }
}

func constantTimeEqual(_ lhs: Data, _ rhs: Data) -> Bool {
    guard lhs.count == rhs.count else {
        return false
    }
    var difference: UInt8 = 0
    for (left, right) in zip(lhs, rhs) {
        difference |= left ^ right
    }
    return difference == 0
}
