import CryptoKit
import Foundation
import MelixComputerProtocol

public enum BrokerToolAuthorizationError: Error, Sendable, Equatable {
    case invalidConfiguration(String)
    case missing
    case malformed
    case invalidSignature
    case expired
    case bindingMismatch
}

extension BrokerToolAuthorizationError: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case let .invalidConfiguration(message):
            message
        case .missing:
            "A control-plane tool authorization is required."
        case .malformed:
            "The control-plane tool authorization is malformed."
        case .invalidSignature:
            "The control-plane tool authorization signature was rejected."
        case .expired:
            "The control-plane tool authorization has expired."
        case .bindingMismatch:
            "The control-plane tool authorization does not match this request."
        }
    }
}

public struct VerifiedControlPlaneToolAuthorization: Sendable, Equatable {
    public let runID: String
    public let sessionID: String
    public let branchID: String
    public let actorID: String
    public let callID: String
    public let sourceID: String
    public let toolName: String
    public let argumentsJSON: String
    public let schemaDigest: String
    public let argumentDigest: String
    public let bindingDigest: String
    public let approvalGrantDigest: String
    public let policyRevision: String
    public let idempotencyKey: String
    public let artifactRoot: String
    public let maximumFrames: UInt32
    public let maximumActions: UInt32
    public let maximumArtifactBytes: UInt64
    public let idleDeadlineUnixMs: Int64
    public let absoluteDeadlineUnixMs: Int64
    public let requestDeadlineUnixMs: Int64
    public let issuedAtUnixMs: Int64
    public let expiresAtUnixMs: Int64
}

public struct BrokerToolAuthorizationVerifier:
    @unchecked Sendable,
    Equatable
{
    private struct Payload: Codable {
        let schemaVersion: String
        let keyID: String
        let runID: String
        let sessionID: String
        let branchID: String
        let actorID: String
        let callID: String
        let sourceID: String
        let toolName: String
        let argumentsJSON: String
        let schemaDigest: String
        let argumentDigest: String
        let bindingDigest: String
        let approvalGrantDigest: String
        let policyRevision: String
        let idempotencyKey: String
        let artifactRoot: String
        let maximumFrames: UInt32
        let maximumActions: UInt32
        let maximumArtifactBytes: UInt64
        let idleDeadlineUnixMs: Int64
        let absoluteDeadlineUnixMs: Int64
        let requestDeadlineUnixMs: Int64
        let issuedAtUnixMs: Int64
        let expiresAtUnixMs: Int64

        enum CodingKeys: String, CodingKey {
            case schemaVersion = "schema_version"
            case keyID = "key_id"
            case runID = "run_id"
            case sessionID = "session_id"
            case branchID = "branch_id"
            case actorID = "actor_id"
            case callID = "call_id"
            case sourceID = "source_id"
            case toolName = "tool_name"
            case argumentsJSON = "arguments_json"
            case schemaDigest = "schema_digest"
            case argumentDigest = "argument_digest"
            case bindingDigest = "binding_digest"
            case approvalGrantDigest = "approval_grant_digest"
            case policyRevision = "policy_revision"
            case idempotencyKey = "idempotency_key"
            case artifactRoot = "artifact_root"
            case maximumFrames = "maximum_frames"
            case maximumActions = "maximum_actions"
            case maximumArtifactBytes = "maximum_artifact_bytes"
            case idleDeadlineUnixMs = "idle_deadline_unix_ms"
            case absoluteDeadlineUnixMs = "absolute_deadline_unix_ms"
            case requestDeadlineUnixMs = "request_deadline_unix_ms"
            case issuedAtUnixMs = "issued_at_unix_ms"
            case expiresAtUnixMs = "expires_at_unix_ms"
        }
    }

    private let publicKey: Curve25519.Signing.PublicKey
    private let publicKeyBytes: Data
    private let now: @Sendable () -> Date
    public let keyID: String

    public init(
        publicKeyRawRepresentation: Data,
        now: @escaping @Sendable () -> Date = Date.init
    ) throws {
        guard publicKeyRawRepresentation.count == 32 else {
            throw BrokerToolAuthorizationError.invalidConfiguration(
                "Computer Use authorization public key must contain exactly 32 bytes."
            )
        }
        do {
            publicKey = try Curve25519.Signing.PublicKey(
                rawRepresentation: publicKeyRawRepresentation
            )
        } catch {
            throw BrokerToolAuthorizationError.invalidConfiguration(
                "Computer Use authorization public key is invalid."
            )
        }
        publicKeyBytes = publicKeyRawRepresentation
        self.now = now
        keyID = SHA256.hash(data: publicKeyRawRepresentation)
            .map { String(format: "%02x", $0) }
            .joined()
    }

    public static func == (
        lhs: BrokerToolAuthorizationVerifier,
        rhs: BrokerToolAuthorizationVerifier
    ) -> Bool {
        lhs.publicKeyBytes == rhs.publicKeyBytes
    }

    public func verify(
        _ authorization: Melix_Computer_V1_ControlPlaneToolAuthorization
    ) throws -> VerifiedControlPlaneToolAuthorization {
        try verify(authorization, cancellationGraceMilliseconds: 0)
    }

    /// Verifies a previously issued exact tool authorization for the sole
    /// purpose of revoking its run-owned broker session. The narrow grace
    /// window lets cancellation still close a live session after the normal
    /// 60-second execution grant expires; it never authorizes a new action.
    /// The 15-minute bound matches the longest desktop Agent run, so an exact
    /// early-session grant remains usable for cleanup through terminalization.
    public func verifyForSessionCancellation(
        _ authorization: Melix_Computer_V1_ControlPlaneToolAuthorization,
        graceMilliseconds: Int64 = 900_000
    ) throws -> VerifiedControlPlaneToolAuthorization {
        guard graceMilliseconds > 0, graceMilliseconds <= 900_000 else {
            throw BrokerToolAuthorizationError.invalidConfiguration(
                "Computer Use cancellation authorization grace is out of bounds."
            )
        }
        return try verify(
            authorization,
            cancellationGraceMilliseconds: graceMilliseconds
        )
    }

    private func verify(
        _ authorization: Melix_Computer_V1_ControlPlaneToolAuthorization,
        cancellationGraceMilliseconds: Int64
    ) throws -> VerifiedControlPlaneToolAuthorization {
        guard
            !authorization.keyID.isEmpty,
            !authorization.algorithm.isEmpty,
            !authorization.signedPayload.isEmpty,
            !authorization.signature.isEmpty
        else {
            throw BrokerToolAuthorizationError.missing
        }
        guard
            authorization.keyID == keyID,
            authorization.algorithm == "ed25519",
            authorization.signedPayload.count <= 65_536,
            authorization.signature.count == 64
        else {
            throw BrokerToolAuthorizationError.malformed
        }
        guard publicKey.isValidSignature(
            authorization.signature,
            for: authorization.signedPayload
        ) else {
            throw BrokerToolAuthorizationError.invalidSignature
        }
        let decoder = JSONDecoder()
        guard
            let payload = try? decoder.decode(
                Payload.self,
                from: authorization.signedPayload
            ),
            payload.schemaVersion == "melix.computer.tool-authorization.v2",
            payload.keyID == keyID,
            payload.sourceID == "computer",
            payload.toolName == "computer_use",
            !payload.runID.isEmpty,
            !payload.sessionID.isEmpty,
            !payload.branchID.isEmpty,
            !payload.actorID.isEmpty,
            !payload.callID.isEmpty,
            !payload.schemaDigest.isEmpty,
            !payload.argumentDigest.isEmpty,
            !payload.bindingDigest.isEmpty,
            !payload.approvalGrantDigest.isEmpty,
            !payload.policyRevision.isEmpty,
            payload.idempotencyKey == payload.approvalGrantDigest,
            Self.isValidArtifactNamespace(payload.artifactRoot),
            1...64 ~= payload.maximumFrames,
            1...32 ~= payload.maximumActions,
            1...(64 * 1_024 * 1_024) ~= payload.maximumArtifactBytes,
            let arguments = payload.argumentsJSON.data(using: .utf8),
            arguments.count <= 32_768,
            (try? JSONSerialization.jsonObject(with: arguments)) is [String: Any],
            payload.argumentDigest == Self.sha256Hex(arguments)
        else {
            throw BrokerToolAuthorizationError.malformed
        }

        let current = Int64(now().timeIntervalSince1970 * 1_000)
        guard
            payload.issuedAtUnixMs <= current + 5_000,
            payload.expiresAtUnixMs > payload.issuedAtUnixMs,
            payload.expiresAtUnixMs - payload.issuedAtUnixMs <= 60_000,
            payload.requestDeadlineUnixMs == payload.expiresAtUnixMs,
            1_000...300_000 ~= (
                payload.idleDeadlineUnixMs - payload.issuedAtUnixMs
            ),
            1_000...600_000 ~= (
                payload.absoluteDeadlineUnixMs - payload.issuedAtUnixMs
            ),
            payload.idleDeadlineUnixMs <= payload.absoluteDeadlineUnixMs,
            payload.expiresAtUnixMs > current - cancellationGraceMilliseconds
        else {
            throw BrokerToolAuthorizationError.expired
        }
        return VerifiedControlPlaneToolAuthorization(
            runID: payload.runID,
            sessionID: payload.sessionID,
            branchID: payload.branchID,
            actorID: payload.actorID,
            callID: payload.callID,
            sourceID: payload.sourceID,
            toolName: payload.toolName,
            argumentsJSON: payload.argumentsJSON,
            schemaDigest: payload.schemaDigest,
            argumentDigest: payload.argumentDigest,
            bindingDigest: payload.bindingDigest,
            approvalGrantDigest: payload.approvalGrantDigest,
            policyRevision: payload.policyRevision,
            idempotencyKey: payload.idempotencyKey,
            artifactRoot: payload.artifactRoot,
            maximumFrames: payload.maximumFrames,
            maximumActions: payload.maximumActions,
            maximumArtifactBytes: payload.maximumArtifactBytes,
            idleDeadlineUnixMs: payload.idleDeadlineUnixMs,
            absoluteDeadlineUnixMs: payload.absoluteDeadlineUnixMs,
            requestDeadlineUnixMs: payload.requestDeadlineUnixMs,
            issuedAtUnixMs: payload.issuedAtUnixMs,
            expiresAtUnixMs: payload.expiresAtUnixMs
        )
    }

    private static func isValidArtifactNamespace(_ value: String) -> Bool {
        guard !value.isEmpty, value.utf8.count <= 128 else {
            return false
        }
        return value.unicodeScalars.allSatisfy { scalar in
            switch scalar.value {
            case 45, 48...57, 65...90, 95, 97...122:
                true
            default:
                false
            }
        }
    }

    private static func sha256Hex(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
}
