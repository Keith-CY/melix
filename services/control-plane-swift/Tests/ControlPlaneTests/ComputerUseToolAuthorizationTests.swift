import CryptoKit
import Foundation
import Testing

@testable import MelixControlPlaneCore

@Suite("Computer Use tool authorization")
struct ComputerUseToolAuthorizationTests {
    @Test("signer binds the exact admitted tool call and deadline")
    func exactBinding() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let signer = try ComputerUseToolAuthorizationSigner(
            privateKeyRawRepresentation: Data(repeating: 0x2A, count: 32),
            now: { now }
        )
        let request = makeExecutionRequest()
        let authorization = try signer.authorize(
            request: request,
            context: WorkerAgentToolExecutionContext(
                sessionID: "session-authorization-1",
                branchID: "branch-authorization-1",
                actorID: "operator-authorization-1",
                deadlineUnixMs: Int64(
                    now.addingTimeInterval(30).timeIntervalSince1970 * 1_000
                )
            )
        )

        #expect(authorization.keyID == signer.keyID)
        #expect(
            try Curve25519.Signing.PublicKey(
                rawRepresentation: signer.publicKeyRawRepresentation
            ).isValidSignature(
                authorization.signature,
                for: authorization.payload
            )
        )
        let payload = try #require(
            JSONSerialization.jsonObject(with: authorization.payload)
                as? [String: Any]
        )
        #expect(payload["run_id"] as? String == "run-authorization-1")
        #expect(payload["call_id"] as? String == "call-authorization-1")
        #expect(payload["source_id"] as? String == "computer")
        #expect(payload["tool_name"] as? String == "computer_use")
        #expect(
            payload["arguments_json"] as? String
                == #"{"operation":"get_permissions"}"#
        )
        #expect(payload["schema_digest"] as? String == "schema-authorization-1")
        #expect(
            payload["argument_digest"] as? String
                == request.admission.binding.argumentDigest
        )
        #expect(
            payload["binding_digest"] as? String
                == request.admission.binding.bindingDigest
        )
        #expect(
            payload["approval_grant_digest"] as? String
                == request.admission.grantDigest
        )
        #expect(payload["policy_revision"] as? String == "policy-authorization-1")
        #expect(
            payload["idempotency_key"] as? String
                == request.admission.grantDigest
        )
        #expect(
            payload["schema_version"] as? String
                == "melix.computer.tool-authorization.v2"
        )
        #expect(
            payload["artifact_root"] as? String
                == "agent-run-authorization-1-0bfe4b01924fa18d"
        )
        #expect(payload["maximum_frames"] as? Int == 16)
        #expect(payload["maximum_actions"] as? Int == 8)
        #expect(payload["maximum_artifact_bytes"] as? Int == 16 * 1_024 * 1_024)
        #expect(
            payload["expires_at_unix_ms"] as? Int
                == Int(now.addingTimeInterval(30).timeIntervalSince1970 * 1_000)
        )
        #expect(
            payload["request_deadline_unix_ms"] as? Int
                == Int(now.addingTimeInterval(30).timeIntervalSince1970 * 1_000)
        )
        #expect(
            payload["idle_deadline_unix_ms"] as? Int
                == Int(now.addingTimeInterval(30).timeIntervalSince1970 * 1_000)
        )
        #expect(
            payload["absolute_deadline_unix_ms"] as? Int
                == Int(now.addingTimeInterval(30).timeIntervalSince1970 * 1_000)
        )
    }

    @Test("a fifteen-minute run still receives only a short-lived broker request")
    func longRunDeadlineIsCappedPerBrokerRequest() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let signer = try ComputerUseToolAuthorizationSigner(
            privateKeyRawRepresentation: Data(repeating: 0x2B, count: 32),
            now: { now }
        )
        let runDeadlineUnixMs = Int64(
            now.addingTimeInterval(15 * 60).timeIntervalSince1970 * 1_000
        )
        let authorization = try signer.authorize(
            request: makeExecutionRequest(),
            context: WorkerAgentToolExecutionContext(
                sessionID: "session-authorization-1",
                branchID: "branch-authorization-1",
                actorID: "operator-authorization-1",
                deadlineUnixMs: runDeadlineUnixMs
            )
        )
        let payload = try #require(
            JSONSerialization.jsonObject(with: authorization.payload)
                as? [String: Any]
        )
        let issuedAtUnixMs = Int(
            now.timeIntervalSince1970 * 1_000
        )
        let requestDeadline = try #require(
            payload["request_deadline_unix_ms"] as? Int
        )
        #expect(
            payload["expires_at_unix_ms"] as? Int
                == issuedAtUnixMs + 60_000
        )
        #expect(
            requestDeadline == issuedAtUnixMs + 60_000
        )
        #expect(
            payload["idle_deadline_unix_ms"] as? Int
                == issuedAtUnixMs + 60_000
        )
        #expect(
            payload["absolute_deadline_unix_ms"] as? Int
                == issuedAtUnixMs + 300_000
        )
        #expect(requestDeadline < Int(runDeadlineUnixMs))
    }

    @Test("signer rejects non-computer tools, incomplete bindings, and expired deadlines")
    func failClosedInputs() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let signer = try ComputerUseToolAuthorizationSigner(
            privateKeyRawRepresentation: Data(repeating: 0x31, count: 32),
            now: { now }
        )
        let valid = makeExecutionRequest()
        let context = WorkerAgentToolExecutionContext(
            sessionID: "session-authorization-1",
            branchID: "branch-authorization-1",
            actorID: "operator-authorization-1",
            deadlineUnixMs: Int64(now.timeIntervalSince1970 * 1_000)
        )
        #expect(throws: ComputerUseToolAuthorizationError.expired) {
            try signer.authorize(request: valid, context: context)
        }

        let unsupported = AgentToolExecutionRequest(
            runID: valid.runID,
            call: AgentToolCall(
                callID: valid.call.callID,
                sourceID: "mcp",
                toolName: "computer_use",
                schemaDigest: valid.call.schemaDigest,
                argumentsJSON: valid.call.argumentsJSON
            ),
            admission: valid.admission
        )
        #expect(throws: ComputerUseToolAuthorizationError.unsupportedTool) {
            try signer.authorize(
                request: unsupported,
                context: WorkerAgentToolExecutionContext(
                    sessionID: "session-authorization-1",
                    branchID: "branch-authorization-1",
                    actorID: "operator-authorization-1",
                    deadlineUnixMs: 0
                )
            )
        }

        let incomplete = AgentToolExecutionRequest(
            runID: valid.runID,
            call: valid.call,
            admission: AgentToolAdmission(
                kind: .approved,
                binding: AgentApprovalBinding(
                    runID: valid.runID,
                    callID: valid.call.callID,
                    schemaDigest: valid.call.schemaDigest,
                    argumentDigest: "",
                    policyRevision: "policy-authorization-1",
                    bindingDigest: "binding-authorization-1"
                ),
                approvalChoice: .allowOnce,
                grantDigest: "grant-authorization-1"
            )
        )
        #expect(throws: ComputerUseToolAuthorizationError.incompleteBinding) {
            try signer.authorize(
                request: incomplete,
                context: WorkerAgentToolExecutionContext(
                    sessionID: "session-authorization-1",
                    branchID: "branch-authorization-1",
                    actorID: "operator-authorization-1",
                    deadlineUnixMs: 0
                )
            )
        }
    }

    @Test("signer rejects stale or substituted approval bindings")
    func exactApprovalBindingIsRequired() throws {
        let signer = try ComputerUseToolAuthorizationSigner(
            privateKeyRawRepresentation: Data(repeating: 0x32, count: 32)
        )
        let valid = makeExecutionRequest()
        let context = makeAuthorizationContext()

        let substitutions: [AgentToolExecutionRequest] = [
            request(
                valid,
                binding: AgentApprovalBinding(
                    runID: "different-run",
                    callID: valid.call.callID,
                    schemaDigest: valid.call.schemaDigest,
                    argumentDigest: valid.admission.binding.argumentDigest,
                    policyRevision: valid.admission.binding.policyRevision,
                    bindingDigest: valid.admission.binding.bindingDigest
                )
            ),
            request(
                valid,
                binding: AgentApprovalBinding(
                    runID: valid.runID,
                    callID: "different-call",
                    schemaDigest: valid.call.schemaDigest,
                    argumentDigest: valid.admission.binding.argumentDigest,
                    policyRevision: valid.admission.binding.policyRevision,
                    bindingDigest: valid.admission.binding.bindingDigest
                )
            ),
            request(
                valid,
                binding: AgentApprovalBinding(
                    runID: valid.runID,
                    callID: valid.call.callID,
                    schemaDigest: "different-schema",
                    argumentDigest: valid.admission.binding.argumentDigest,
                    policyRevision: valid.admission.binding.policyRevision,
                    bindingDigest: valid.admission.binding.bindingDigest
                )
            ),
            AgentToolExecutionRequest(
                runID: valid.runID,
                call: AgentToolCall(
                    callID: valid.call.callID,
                    sourceID: valid.call.sourceID,
                    toolName: valid.call.toolName,
                    schemaDigest: valid.call.schemaDigest,
                    argumentsJSON: #"{"operation":"get_permissions","replayed":true}"#
                ),
                admission: valid.admission
            ),
            AgentToolExecutionRequest(
                runID: valid.runID,
                call: valid.call,
                admission: AgentToolAdmission(
                    kind: valid.admission.kind,
                    binding: valid.admission.binding,
                    approvalChoice: valid.admission.approvalChoice,
                    grantDigest: "substituted-grant"
                )
            ),
        ]

        for substituted in substitutions {
            #expect(throws: ComputerUseToolAuthorizationError.bindingMismatch) {
                try signer.authorize(request: substituted, context: context)
            }
        }

        let missingDecision = AgentToolExecutionRequest(
            runID: valid.runID,
            call: valid.call,
            admission: AgentToolAdmission(
                kind: .approved,
                binding: valid.admission.binding,
                approvalChoice: nil,
                grantDigest: valid.admission.grantDigest
            )
        )
        #expect(throws: ComputerUseToolAuthorizationError.bindingMismatch) {
            try signer.authorize(request: missingDecision, context: context)
        }
    }

    @Test("signer freezes exactly one trusted Computer Use window")
    func exactSingleTargetBindingIsRequired() throws {
        let signer = try ComputerUseToolAuthorizationSigner(
            privateKeyRawRepresentation: Data(repeating: 0x33, count: 32)
        )
        let first = try trustedTarget(windowID: 7)
        let second = try trustedTarget(windowID: 8)
        let twoTargetArguments = try jsonString([
            "operation": "open_session",
            "allowed_targets": [first.jsonObject, second.jsonObject],
        ])
        let twoTargetRequest = makeExecutionRequest(
            argumentsJSON: twoTargetArguments
        )

        #expect(throws: ComputerUseToolAuthorizationError.invalidArguments) {
            try signer.authorize(
                request: twoTargetRequest,
                context: makeAuthorizationContext(
                    trustedComputerUseTargets: [first, second]
                )
            )
        }

        let oneTargetArguments = try jsonString([
            "operation": "open_session",
            "allowed_targets": [first.jsonObject],
        ])
        let authorization = try signer.authorize(
            request: makeExecutionRequest(argumentsJSON: oneTargetArguments),
            context: makeAuthorizationContext(
                trustedComputerUseTargets: [first]
            )
        )
        #expect(!authorization.signature.isEmpty)

        let missingSessionArguments = try jsonString([
            "operation": "capture_frame",
            "session_id": "",
            "target": first.jsonObject,
        ])
        #expect(throws: ComputerUseToolAuthorizationError.invalidArguments) {
            try signer.authorize(
                request: makeExecutionRequest(
                    argumentsJSON: missingSessionArguments
                ),
                context: makeAuthorizationContext(
                    trustedComputerUseTargets: [first]
                )
            )
        }
    }

    @Test("every Computer operation keeps its authoritative target boundary")
    func operationTargetBindingMatrix() throws {
        let signer = try ComputerUseToolAuthorizationSigner(
            privateKeyRawRepresentation: Data(repeating: 0x34, count: 32)
        )
        let target = try trustedTarget(windowID: 7)
        let operatorReadContext = WorkerAgentToolExecutionContext(
            sessionID: "agent-operations",
            branchID: "operator-read-model",
            actorID: "operator-authorization-1",
            deadlineUnixMs: 0
        )
        let runContext = makeAuthorizationContext(
            trustedComputerUseTargets: [target]
        )

        let validRequests: [(
            AgentToolExecutionRequest,
            WorkerAgentToolExecutionContext
        )] = [
            (
                makeExecutionRequest(
                    argumentsJSON: try jsonString([
                        "operation": "list_targets",
                    ])
                ),
                operatorReadContext
            ),
            (
                makeExecutionRequest(
                    argumentsJSON: try jsonString([
                        "operation": "capture_frame",
                        "session_id": "computer-session-1",
                        "target": target.jsonObject,
                    ])
                ),
                runContext
            ),
            (
                makeExecutionRequest(
                    argumentsJSON: try jsonString([
                        "operation": "press_element",
                        "session_id": "computer-session-1",
                        "target": target.jsonObject,
                    ])
                ),
                runContext
            ),
            (
                makeExecutionRequest(
                    argumentsJSON: try jsonString([
                        "operation": "close_session",
                        "session_id": "computer-session-1",
                    ])
                ),
                runContext
            ),
        ]
        for (request, context) in validRequests {
            #expect(
                try signer.authorize(request: request, context: context)
                    .signature.isEmpty == false
            )
        }

        #expect(throws: ComputerUseToolAuthorizationError.invalidArguments) {
            try signer.authorize(
                request: makeExecutionRequest(
                    argumentsJSON: try jsonString([
                        "operation": "list_targets",
                    ])
                ),
                context: makeAuthorizationContext()
            )
        }
        #expect(throws: ComputerUseToolAuthorizationError.invalidArguments) {
            var substituted = target.jsonObject
            substituted["window_title"] = "Substituted"
            _ = try signer.authorize(
                request: makeExecutionRequest(
                    argumentsJSON: try jsonString([
                        "operation": "open_session",
                        "allowed_targets": [substituted],
                    ])
                ),
                context: runContext
            )
        }
        #expect(throws: ComputerUseToolAuthorizationError.invalidArguments) {
            try signer.authorize(
                request: makeExecutionRequest(argumentsJSON: "{}"),
                context: runContext
            )
        }
        #expect(throws: ComputerUseToolAuthorizationError.invalidArguments) {
            try signer.authorize(
                request: makeExecutionRequest(
                    argumentsJSON: #"{"operation":"close_session","session_id":" "}"#
                ),
                context: runContext
            )
        }
        #expect(throws: ComputerUseToolAuthorizationError.unsupportedTool) {
            try signer.authorize(
                request: makeExecutionRequest(
                    argumentsJSON: #"{"operation":"future_operation"}"#
                ),
                context: runContext
            )
        }
    }

    @Test("always allow signing and signer identity remain exact")
    func alwaysAllowAndSignerIdentity() throws {
        let key = Data(repeating: 0x35, count: 32)
        let signer = try ComputerUseToolAuthorizationSigner(
            privateKeyRawRepresentation: key
        )
        let sameSigner = try ComputerUseToolAuthorizationSigner(
            privateKeyRawRepresentation: key
        )
        let otherSigner = try ComputerUseToolAuthorizationSigner(
            privateKeyRawRepresentation: Data(repeating: 0x36, count: 32)
        )
        #expect(signer == sameSigner)
        #expect(signer != otherSigner)

        let base = makeExecutionRequest(runID: "•••")
        let alwaysAllow = AgentToolExecutionRequest(
            runID: base.runID,
            call: base.call,
            admission: AgentToolAdmission(
                kind: .approved,
                binding: base.admission.binding,
                approvalChoice: .alwaysAllow,
                grantDigest: admissionGrantDigest(
                    kind: .approved,
                    binding: base.admission.binding,
                    choice: .alwaysAllow
                )
            )
        )
        let authorization = try signer.authorize(
            request: alwaysAllow,
            context: makeAuthorizationContext()
        )
        let payload = try #require(
            JSONSerialization.jsonObject(with: authorization.payload)
                as? [String: Any]
        )
        #expect((payload["artifact_root"] as? String)?.hasPrefix("agent-run-") == true)
    }
}

private func makeExecutionRequest(
    runID: String = "run-authorization-1",
    argumentsJSON: String = #"{"operation":"get_permissions"}"#
) -> AgentToolExecutionRequest {
    let call = AgentToolCall(
        callID: "call-authorization-1",
        sourceID: "computer",
        toolName: "computer_use",
        schemaDigest: "schema-authorization-1",
        argumentsJSON: argumentsJSON
    )
    let binding = AgentApprovalBinding.make(
        runID: runID,
        call: call,
        policyRevision: "policy-authorization-1",
        scopeDigest: "scope-authorization-1"
    )
    return AgentToolExecutionRequest(
        runID: runID,
        call: call,
        admission: AgentToolAdmission(
            kind: .approved,
            binding: binding,
            approvalChoice: .allowOnce,
            grantDigest: admissionGrantDigest(
                kind: .approved,
                binding: binding,
                choice: .allowOnce
            )
        )
    )
}

private func request(
    _ base: AgentToolExecutionRequest,
    binding: AgentApprovalBinding
) -> AgentToolExecutionRequest {
    AgentToolExecutionRequest(
        runID: base.runID,
        call: base.call,
        admission: AgentToolAdmission(
            kind: base.admission.kind,
            binding: binding,
            approvalChoice: base.admission.approvalChoice,
            grantDigest: base.admission.grantDigest
        )
    )
}

private func makeAuthorizationContext(
    trustedComputerUseTargets: [TrustedComputerUseTarget] = []
) -> WorkerAgentToolExecutionContext {
    WorkerAgentToolExecutionContext(
        sessionID: "session-authorization-1",
        branchID: "branch-authorization-1",
        actorID: "operator-authorization-1",
        deadlineUnixMs: 0,
        trustedComputerUseTargets: trustedComputerUseTargets
    )
}

private func admissionGrantDigest(
    kind: AgentToolAdmissionKind,
    binding: AgentApprovalBinding,
    choice: AgentApprovalChoice?
) -> String {
    let kindValue = kind == .allow ? "allow" : "approved"
    let choiceValue: String = switch choice {
    case .allowOnce: "allow-once"
    case .alwaysAllow: "always-allow"
    case .deny: "deny"
    case nil: "policy-allow"
    }
    return sha256Hex(
        canonicalDigestInput([
            "melix.agent-tool-admission.v1",
            binding.bindingDigest,
            kindValue,
            choiceValue,
        ])
    )
}

private func canonicalDigestInput(_ fields: [String]) -> String {
    fields.map { field in
        "\(field.utf8.count):\(field)"
    }.joined(separator: "|")
}

private func sha256Hex(_ value: String) -> String {
    SHA256.hash(data: Data(value.utf8)).map { byte in
        String(format: "%02x", byte)
    }.joined()
}

private func jsonString(_ value: [String: Any]) throws -> String {
    let data = try JSONSerialization.data(
        withJSONObject: value,
        options: [.sortedKeys, .withoutEscapingSlashes]
    )
    return try #require(String(data: data, encoding: .utf8))
}

private func trustedTarget(windowID: UInt32) throws -> TrustedComputerUseTarget {
    try TrustedComputerUseTarget(
        bundleID: "io.melix.fixture",
        processID: 42,
        processLaunchIdentity: "launch-42",
        windowID: windowID,
        windowTitle: "Fixture \(windowID)",
        applicationName: "Fixture"
    )
}
