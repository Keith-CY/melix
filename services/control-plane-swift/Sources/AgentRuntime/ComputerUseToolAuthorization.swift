import CryptoKit
import Foundation

public enum ComputerUseToolAuthorizationError: Error, Sendable, Equatable {
    case invalidArguments
    case incompleteBinding
    case bindingMismatch
    case unsupportedTool
    case expired
    case signingFailed
}

public struct ControlPlaneToolAuthorization: Sendable, Equatable {
    public static let algorithm = "ed25519"

    public let keyID: String
    public let payload: Data
    public let signature: Data

    public init(keyID: String, payload: Data, signature: Data) {
        self.keyID = keyID
        self.payload = payload
        self.signature = signature
    }
}

/// Issues short-lived, exact tool-call authorizations for the Computer Use
/// broker. The private key remains in the control-plane process; workers only
/// receive a signed envelope that they can relay but cannot widen or forge.
public struct ComputerUseToolAuthorizationSigner:
    @unchecked Sendable,
    Equatable
{
    private struct Payload: Codable, Sendable, Equatable {
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

    private let privateKey: Curve25519.Signing.PrivateKey
    private let now: @Sendable () -> Date

    public init(now: @escaping @Sendable () -> Date = Date.init) {
        privateKey = Curve25519.Signing.PrivateKey()
        self.now = now
    }

    public init(
        privateKeyRawRepresentation: Data,
        now: @escaping @Sendable () -> Date = Date.init
    ) throws {
        privateKey = try Curve25519.Signing.PrivateKey(
            rawRepresentation: privateKeyRawRepresentation
        )
        self.now = now
    }

    public var publicKeyRawRepresentation: Data {
        privateKey.publicKey.rawRepresentation
    }

    public var keyID: String {
        Self.sha256Hex(publicKeyRawRepresentation)
    }

    public static func == (
        lhs: ComputerUseToolAuthorizationSigner,
        rhs: ComputerUseToolAuthorizationSigner
    ) -> Bool {
        lhs.publicKeyRawRepresentation == rhs.publicKeyRawRepresentation
    }

    public func authorize(
        request: AgentToolExecutionRequest,
        context: WorkerAgentToolExecutionContext
    ) throws -> ControlPlaneToolAuthorization {
        guard request.call.sourceID == "computer",
              request.call.toolName == "computer_use"
        else {
            throw ComputerUseToolAuthorizationError.unsupportedTool
        }
        guard
            let argumentsData = request.call.argumentsJSON.data(using: .utf8),
            let arguments = try? JSONSerialization.jsonObject(with: argumentsData)
                as? [String: Any]
        else {
            throw ComputerUseToolAuthorizationError.invalidArguments
        }
        try Self.validateTrustedTargetBinding(
            arguments: arguments,
            context: context
        )
        let binding = request.admission.binding
        guard
            !request.runID.isEmpty,
            !context.sessionID.isEmpty,
            !context.branchID.isEmpty,
            !context.actorID.isEmpty,
            !request.call.callID.isEmpty,
            !request.call.sourceID.isEmpty,
            !request.call.toolName.isEmpty,
            !request.call.schemaDigest.isEmpty,
            !binding.argumentDigest.isEmpty,
            !binding.bindingDigest.isEmpty,
            !request.admission.grantDigest.isEmpty,
            !binding.policyRevision.isEmpty
        else {
            throw ComputerUseToolAuthorizationError.incompleteBinding
        }
        guard binding.runID == request.runID,
              binding.callID == request.call.callID,
              binding.schemaDigest == request.call.schemaDigest,
              binding.argumentDigest == Self.sha256Hex(argumentsData),
              request.admission.grantDigest
                == Self.expectedAdmissionGrantDigest(request.admission)
        else {
            throw ComputerUseToolAuthorizationError.bindingMismatch
        }

        let issuedAt = Int64(now().timeIntervalSince1970 * 1_000)
        let defaultExpiry = issuedAt + 60_000
        let expiresAt = context.deadlineUnixMs > 0
            ? min(defaultExpiry, context.deadlineUnixMs)
            : defaultExpiry
        let absoluteDeadline = context.deadlineUnixMs > 0
            ? min(issuedAt + 300_000, context.deadlineUnixMs)
            : issuedAt + 300_000
        let idleDeadline = min(issuedAt + 60_000, absoluteDeadline)
        guard expiresAt >= issuedAt + 1_000,
              idleDeadline >= issuedAt + 1_000,
              absoluteDeadline >= idleDeadline
        else {
            throw ComputerUseToolAuthorizationError.expired
        }
        let payload = Payload(
            schemaVersion: "melix.computer.tool-authorization.v2",
            keyID: keyID,
            runID: request.runID,
            sessionID: context.sessionID,
            branchID: context.branchID,
            actorID: context.actorID,
            callID: request.call.callID,
            sourceID: request.call.sourceID,
            toolName: request.call.toolName,
            argumentsJSON: request.call.argumentsJSON,
            schemaDigest: request.call.schemaDigest,
            argumentDigest: binding.argumentDigest,
            bindingDigest: binding.bindingDigest,
            approvalGrantDigest: request.admission.grantDigest,
            policyRevision: binding.policyRevision,
            idempotencyKey: request.admission.grantDigest,
            artifactRoot: Self.artifactNamespace(runID: request.runID),
            maximumFrames: 16,
            maximumActions: 8,
            maximumArtifactBytes: 16 * 1_024 * 1_024,
            idleDeadlineUnixMs: idleDeadline,
            absoluteDeadlineUnixMs: absoluteDeadline,
            requestDeadlineUnixMs: expiresAt,
            issuedAtUnixMs: issuedAt,
            expiresAtUnixMs: expiresAt
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        guard let encoded = try? encoder.encode(payload),
              let signature = try? privateKey.signature(for: encoded)
        else {
            throw ComputerUseToolAuthorizationError.signingFailed
        }
        return ControlPlaneToolAuthorization(
            keyID: keyID,
            payload: encoded,
            signature: signature
        )
    }

    private static func sha256Hex(_ data: Data) -> String {
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }

    private static func artifactNamespace(runID: String) -> String {
        let safePrefix = String(runID.unicodeScalars.map { scalar in
            switch scalar.value {
            case 45, 48...57, 65...90, 95, 97...122:
                Character(String(scalar))
            default:
                "_"
            }
        }.prefix(32)).trimmingCharacters(in: CharacterSet(charactersIn: "_"))
        let digest = String(sha256Hex(Data(runID.utf8)).prefix(16))
        return "agent-\(safePrefix.isEmpty ? "run" : safePrefix)-\(digest)"
    }

    private static func expectedAdmissionGrantDigest(
        _ admission: AgentToolAdmission
    ) -> String? {
        let kind: String
        let choice: String
        switch (admission.kind, admission.approvalChoice) {
        case (.allow, nil):
            kind = "allow"
            choice = "policy-allow"
        case (.approved, .allowOnce):
            kind = "approved"
            choice = "allow-once"
        case (.approved, .alwaysAllow):
            kind = "approved"
            choice = "always-allow"
        case (.allow, .allowOnce),
             (.allow, .alwaysAllow),
             (.allow, .deny),
             (.approved, .deny),
             (.approved, nil):
            return nil
        }
        let input = canonicalDigestInput([
            "melix.agent-tool-admission.v1",
            admission.binding.bindingDigest,
            kind,
            choice,
        ])
        return sha256Hex(Data(input.utf8))
    }

    private static func canonicalDigestInput(_ fields: [String]) -> String {
        fields.map { field in
            "\(field.utf8.count):\(field)"
        }.joined(separator: "|")
    }

    private static func validateTrustedTargetBinding(
        arguments: [String: Any],
        context: WorkerAgentToolExecutionContext
    ) throws {
        guard let operation = arguments["operation"] as? String else {
            throw ComputerUseToolAuthorizationError.invalidArguments
        }
        switch operation {
        case "get_permissions":
            return
        case "list_targets":
            guard context.sessionID == "agent-operations",
                  context.branchID == "operator-read-model",
                  context.trustedComputerUseTargets.isEmpty else {
                throw ComputerUseToolAuthorizationError.invalidArguments
            }
        case "open_session":
            guard context.trustedComputerUseTargets.count == 1,
                  let rawTargets = arguments["allowed_targets"] as? [[String: Any]],
                  rawTargets.count == 1
            else {
                throw ComputerUseToolAuthorizationError.invalidArguments
            }
            let matchedIDs = rawTargets.compactMap { rawTarget in
                context.trustedComputerUseTargets.first(where: {
                    $0.matchesAuthoritativeIdentity(rawTarget)
                        && (rawTarget["window_title"] as? String) == $0.windowTitle
                        && (rawTarget["application_name"] as? String)
                            == $0.applicationName
                })?.targetID
            }
            guard Set(matchedIDs).count == rawTargets.count else {
                throw ComputerUseToolAuthorizationError.invalidArguments
            }
        case "capture_frame", "press_element":
            guard context.trustedComputerUseTargets.count == 1,
                  let sessionID = arguments["session_id"] as? String,
                  !sessionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  let rawTarget = arguments["target"] as? [String: Any],
                  context.trustedComputerUseTargets.contains(where: {
                      $0.matchesAuthoritativeIdentity(rawTarget)
                          && (rawTarget["window_title"] as? String) == $0.windowTitle
                          && (rawTarget["application_name"] as? String)
                              == $0.applicationName
                  }) else {
                throw ComputerUseToolAuthorizationError.invalidArguments
            }
        case "close_session":
            guard context.trustedComputerUseTargets.count == 1,
                  let sessionID = arguments["session_id"] as? String,
                  !sessionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            else {
                throw ComputerUseToolAuthorizationError.invalidArguments
            }
        default:
            throw ComputerUseToolAuthorizationError.unsupportedTool
        }
    }
}
