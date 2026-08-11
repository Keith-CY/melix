import ComputerUseBrokerCore
import Foundation
import GRPCCore
import MelixComputerProtocol

public final class ComputerUseBrokerGRPCProvider:
    Melix_Computer_V1_ComputerUseBrokerService.SimpleServiceProtocol,
    @unchecked Sendable
{
    private let broker: any ComputerUseBroker
    private let configuration: BrokerTransportConfiguration
    private let admissionVerifier = BrokerAdmissionVerifier()
    private let sessions = TransportSessionRegistry()

    public init(
        broker: any ComputerUseBroker,
        configuration: BrokerTransportConfiguration
    ) {
        self.broker = broker
        self.configuration = configuration
    }

    public func handshake(
        request: Melix_Computer_V1_BrokerHandshakeRequest,
        context: ServerContext
    ) async throws -> Melix_Computer_V1_BrokerHandshakeResponse {
        try admissionVerifier.validateHandshake(
            request: request,
            policy: configuration.handshake
        )
        let permissions = await broker.permissions()
        var response = Melix_Computer_V1_BrokerHandshakeResponse()
        response.protocolVersion = configuration.handshake.protocolVersion
        response.brokerVersion = configuration.brokerVersion
        response.brokerInstanceID = configuration.brokerInstanceID
        response.features = configuration.features
        response.permissions = permissionSnapshot(permissions)
        return response
    }

    public func getPermissions(
        request: Melix_Computer_V1_GetPermissionsRequest,
        context: ServerContext
    ) async throws -> Melix_Computer_V1_PermissionSnapshot {
        try requireAdmission(request.callerVerificationCapability)
        do {
            _ = try verifyAuthorization(
                request.authorization,
                operation: "get_permissions"
            )
        } catch {
            throw mapRPCError(error)
        }
        return permissionSnapshot(await broker.permissions())
    }

    public func listTargets(
        request: Melix_Computer_V1_ListComputerTargetsRequest,
        context: ServerContext
    ) async throws -> Melix_Computer_V1_ListComputerTargetsResponse {
        try requireAdmission(request.callerVerificationCapability)
        do {
            _ = try verifyAuthorization(
                request.authorization,
                operation: "list_targets"
            )
            let discovered = try await broker.listTargets()
            guard discovered.count <= 128 else {
                throw TransportContractError.internalFailure(
                    "Computer target inventory exceeded its bounded cardinality."
                )
            }
            var seen = Set<Data>()
            var response = Melix_Computer_V1_ListComputerTargetsResponse()
            response.targets = try discovered.map { target in
                let mapped = mapTarget(target)
                _ = try mapTarget(mapped)
                guard seen.insert(try mapped.serializedData()).inserted else {
                    throw TransportContractError.internalFailure(
                        "Computer target inventory contained duplicate identities."
                    )
                }
                return mapped
            }
            response.observedAtUnixMs = Int64(Date().timeIntervalSince1970 * 1_000)
            return response
        } catch {
            throw mapRPCError(error)
        }
    }

    public func requestPermission(
        request: Melix_Computer_V1_PermissionPromptRequest,
        context: ServerContext
    ) async throws -> Melix_Computer_V1_PermissionPromptReceipt {
        try requireAdmission(request.callerVerificationCapability)
        guard request.kind == .permissionScreenRecording
            || request.kind == .permissionAccessibility
        else {
            throw RPCError(code: .invalidArgument, message: "Permission kind must be explicit.")
        }
        guard !request.actorID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !request.operatorGestureID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw RPCError(
                code: .invalidArgument,
                message: "Permission requests require actor and operator gesture identifiers."
            )
        }
        do {
            let authorization = try verifyAuthorization(
                request.authorization,
                operation: "request_permission"
            )
            try validatePermissionAuthorization(
                authorization,
                request: request
            )
        } catch {
            throw mapRPCError(error)
        }
        // This slice has no trusted operator-gesture verifier. Never call a TCC
        // prompt API based only on caller-provided gesture text.
        var receipt = Melix_Computer_V1_PermissionPromptReceipt()
        receipt.kind = request.kind
        receipt.promptRequested = false
        receipt.disposition = "refused_no_verified_operator_gesture_seam"
        receipt.permissions = permissionSnapshot(await broker.permissions())
        return receipt
    }

    public func openSession(
        request: Melix_Computer_V1_OpenComputerSessionRequest,
        context: ServerContext
    ) async throws -> Melix_Computer_V1_ComputerSessionLease {
        try requireAdmission(request.callerVerificationCapability)
        do {
            let authorization = try verifyAuthorization(
                request.authorization,
                operation: "open_session",
                identity: request.identity,
                callID: request.identity.toolCallID
            )
            try validateOpenAuthorization(
                authorization,
                request: request
            )
            let mapped = try mapOpenSessionRequest(
                request,
                authorization: authorization
            )
            let registration = try await sessions.open(
                key: mapped.idempotencyScope,
                fingerprint: mapped.fingerprint,
                broker: broker,
                request: mapped.coreRequest,
                protocolIdentity: mapped.protocolIdentity,
                allowedTargets: request.allowedTargets,
                limits: request.limits
            )
            return makeLease(registration)
        } catch {
            throw mapRPCError(error)
        }
    }

    public func captureFrame(
        request: Melix_Computer_V1_CaptureFrameRequest,
        context: ServerContext
    ) async throws -> Melix_Computer_V1_CaptureFrameResponse {
        try requireAdmission(request.callerVerificationCapability)
        do {
            let authorization = try verifyAuthorization(
                request.authorization,
                operation: "capture_frame",
                identity: request.identity
            )
            try validateCaptureAuthorization(
                authorization,
                request: request
            )
            try validateFutureDeadline(request.deadlineUnixMs, field: "capture deadline")
            let target = try mapTarget(request.target)
            let reservation = try await sessions.reserveCapture(
                identity: request.identity,
                target: request.target,
                expectedPreviousGeneration: request.expectedPreviousGeneration
            )
            let observation: ComputerFrameObservation
            do {
                observation = try await broker.captureFrame(
                    CaptureComputerFrameRequest(
                        sessionID: reservation.registration.identity.sessionID,
                        capability: try mapCapability(request.sessionCapability),
                        target: target
                    )
                )
                try await sessions.commitCapture(
                    reservation,
                    generation: observation.generation
                )
            } catch {
                await sessions.rollbackCapture(reservation)
                throw error
            }
            var response = Melix_Computer_V1_CaptureFrameResponse()
            response.identity = reservation.registration.identity
            response.actualTarget = mapTarget(observation.target)
            response.observationID = observation.frameID
            response.frameGeneration = observation.generation
            response.frame = try mapArtifact(observation.artifact)
            response.elements = observation.elements.map { element in
                var mapped = Melix_Computer_V1_ElementHandle()
                mapped.handleID = element.handleID
                mapped.frameGeneration = element.frameGeneration
                mapped.role = element.role
                mapped.title = element.title
                mapped.secure = element.isSecure
                mapped.enabled = element.isEnabled
                return mapped
            }
            response.evidenceReceiptJson = try encodeEvidence(observation)
            return response
        } catch {
            throw mapRPCError(error)
        }
    }

    public func executeAction(
        request: Melix_Computer_V1_ExecuteComputerActionRequest,
        response: RPCWriter<Melix_Computer_V1_ComputerActionEvent>,
        context: ServerContext
    ) async throws {
        try requireAdmission(request.callerVerificationCapability)
        do {
            let authorization = try verifyAuthorization(
                request.authorization,
                operation: "press_element",
                identity: request.identity,
                callID: request.actionID
            )
            let press = try validateActionAuthorization(
                authorization,
                request: request
            )
            let mapped = try mapActionRequest(request, press: press)
            let registration = try await sessions.registerAction(
                identity: request.identity,
                target: request.target,
                actionID: request.actionID,
                attempt: request.attempt
            )
            let execution = try await broker.performAction(mapped)
            for await event in execution.events {
                try await response.write(
                    try mapActionEvent(
                        event,
                        identity: registration.identity,
                        actionID: request.actionID,
                        attempt: request.attempt
                    )
                )
            }
        } catch {
            throw mapRPCError(error)
        }
    }

    public func cancelAction(
        request: Melix_Computer_V1_CancelComputerActionRequest,
        context: ServerContext
    ) async throws -> Melix_Computer_V1_CancelComputerActionResponse {
        try requireAdmission(request.callerVerificationCapability)
        do {
            _ = try verifyAuthorization(
                request.authorization,
                operation: "press_element",
                identity: request.identity,
                callID: request.actionID
            )
            guard request.cancellationID.hasPrefix("cancel-") else {
                throw TransportContractError.invalidRequest(
                    "Cancellation identifier must use the broker cancellation namespace."
                )
            }
            guard !request.actionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  request.attempt > 0,
                  !request.cancellationID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            else {
                throw TransportContractError.invalidRequest(
                    "Cancellation requires action, attempt, and cancellation identifiers."
                )
            }
            let registration = try await sessions.validateActionAttempt(
                identity: request.identity,
                actionID: request.actionID,
                attempt: request.attempt
            )
            let receipt = await broker.cancelAction(
                CancelComputerActionRequest(
                    sessionID: registration.identity.sessionID,
                    capability: try mapCapability(request.sessionCapability),
                    actionID: request.actionID,
                    cancellationID: request.cancellationID,
                    reason: "Cancellation requested through the authenticated broker transport."
                )
            )
            var result = Melix_Computer_V1_CancelComputerActionResponse()
            result.actionID = request.actionID
            result.attempt = request.attempt
            result.cancellationID = request.cancellationID
            result.disposition = mapCancellationDisposition(receipt.disposition)
            result.sideEffectCommitted = receipt.terminalReceipt?.sideEffectCommitted ?? false
            return result
        } catch {
            throw mapRPCError(error)
        }
    }

    public func cancelSession(
        request: Melix_Computer_V1_CancelComputerSessionRequest,
        context: ServerContext
    ) async throws -> Melix_Computer_V1_CancelComputerSessionResponse {
        try requireAdmission(request.callerVerificationCapability)
        do {
            let authorization = try configuration.toolAuthorizationVerifier
                .verifyForSessionCancellation(request.authorization)
            try validateSessionCancellationAuthorization(
                authorization,
                request: request
            )
            guard request.cancellationID.hasPrefix("cancel-session-"),
                  request.cancellationID.count <= 256,
                  !request.reason.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  request.reason.utf8.count <= 256
            else {
                throw TransportContractError.invalidRequest(
                    "Session cancellation requires a bounded cancellation identifier and reason."
                )
            }
            _ = try await sessions.validateSession(identity: request.identity)
            let receipt = await broker.cancelSession(
                CancelComputerUseSessionRequest(
                    sessionID: request.identity.sessionID,
                    capability: try mapCapability(request.sessionCapability),
                    cancellationID: request.cancellationID,
                    reason: request.reason
                )
            )
            if receipt.disposition == .accepted || receipt.disposition == .alreadyTerminal {
                await sessions.markClosed(sessionID: request.identity.sessionID)
            }
            var result = Melix_Computer_V1_CancelComputerSessionResponse()
            result.sessionID = receipt.sessionID
            result.cancellationID = receipt.cancellationID
            result.disposition = mapSessionCancellationDisposition(
                receipt.disposition
            )
            result.cancelledActionIds = receipt.cancelledActionIDs
            result.tooLateActionIds = receipt.tooLateActionIDs
            result.cancelledAtUnixMs = unixMilliseconds(receipt.cancelledAt)
            return result
        } catch {
            throw mapRPCError(error)
        }
    }

    public func closeSession(
        request: Melix_Computer_V1_CloseComputerSessionRequest,
        context: ServerContext
    ) async throws -> Melix_Computer_V1_CloseComputerSessionResponse {
        try requireAdmission(request.callerVerificationCapability)
        do {
            let authorization = try verifyAuthorization(
                request.authorization,
                operation: "close_session",
                identity: request.identity
            )
            try validateCloseAuthorization(
                authorization,
                request: request
            )
            let registration = try await sessions.validateSession(identity: request.identity)
            let receipt = try await broker.closeSession(
                CloseComputerUseSessionRequest(
                    sessionID: registration.identity.sessionID,
                    capability: try mapCapability(request.sessionCapability)
                )
            )
            await sessions.markClosed(sessionID: registration.identity.sessionID)
            var result = Melix_Computer_V1_CloseComputerSessionResponse()
            result.sessionID = receipt.sessionID
            result.closed = true
            result.invalidatedHandleCount = 0
            result.closedAtUnixMs = unixMilliseconds(receipt.closedAt)
            return result
        } catch {
            throw mapRPCError(error)
        }
    }
}

private extension ComputerUseBrokerGRPCProvider {
    func requireAdmission(_ capability: Data) throws {
        try admissionVerifier.requireCapability(
            capability,
            policy: configuration.handshake
        )
    }

    func verifyAuthorization(
        _ authorization:
            Melix_Computer_V1_ControlPlaneToolAuthorization,
        operation: String,
        identity: Melix_Computer_V1_ComputerSessionIdentity? = nil,
        callID: String? = nil
    ) throws -> VerifiedControlPlaneToolAuthorization {
        let verified = try configuration.toolAuthorizationVerifier.verify(
            authorization
        )
        let arguments = try authorizationArguments(verified)
        guard arguments["operation"] as? String == operation else {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
        if let identity {
            guard
                verified.runID == identity.agentRunID,
                verified.branchID == identity.branchID,
                verified.actorID == identity.actorID
            else {
                throw BrokerToolAuthorizationError.bindingMismatch
            }
        }
        if let callID, verified.callID != callID {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
        return verified
    }

    func validateOpenAuthorization(
        _ authorization: VerifiedControlPlaneToolAuthorization,
        request: Melix_Computer_V1_OpenComputerSessionRequest
    ) throws {
        let arguments = try authorizationArguments(authorization)
        guard
            request.idempotencyKey == authorization.idempotencyKey,
            request.identity.requestID == authorization.callID,
            request.identity.toolCallID == authorization.callID,
            request.artifactRoot == authorization.artifactRoot,
            request.limits.maximumFrames <= authorization.maximumFrames,
            request.limits.maximumActions <= authorization.maximumActions,
            request.limits.maximumArtifactBytes
                <= authorization.maximumArtifactBytes,
            request.limits.idleDeadlineUnixMs
                <= authorization.idleDeadlineUnixMs,
            request.limits.absoluteDeadlineUnixMs
                <= authorization.absoluteDeadlineUnixMs,
            let rawTargets = arguments["allowed_targets"] as? [Any],
            rawTargets.count == request.allowedTargets.count
        else {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
        let authorizedTargets = try rawTargets.map(authorizationTarget)
        guard zip(authorizedTargets, request.allowedTargets).allSatisfy({
            targetMatches($0.0, $0.1)
        }) else {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
    }

    func validatePermissionAuthorization(
        _ authorization: VerifiedControlPlaneToolAuthorization,
        request: Melix_Computer_V1_PermissionPromptRequest
    ) throws {
        let arguments = try authorizationArguments(authorization)
        let kind = request.kind == .permissionAccessibility
            ? "accessibility"
            : "screen_recording"
        guard arguments["kind"] as? String == kind,
              arguments["actor_id"] as? String == request.actorID,
              arguments["operator_gesture_id"] as? String
                == request.operatorGestureID,
              authorization.actorID == request.actorID
        else {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
    }

    func validateCaptureAuthorization(
        _ authorization: VerifiedControlPlaneToolAuthorization,
        request: Melix_Computer_V1_CaptureFrameRequest
    ) throws {
        let arguments = try authorizationArguments(authorization)
        guard
            request.captureID == "capture-\(authorization.callID)",
            arguments["session_id"] as? String == request.identity.sessionID,
            let rawTarget = arguments["target"] as? [String: Any],
            targetMatches(try authorizationTarget(rawTarget), request.target)
        else {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
        if let previous = arguments["expected_previous_generation"] as? NSNumber {
            guard previous.uint64Value == request.expectedPreviousGeneration else {
                throw BrokerToolAuthorizationError.bindingMismatch
            }
        } else if request.expectedPreviousGeneration != 0 {
            // An omitted generation is a signed first-capture grant, not a
            // wildcard. Otherwise one envelope could be replayed with a
            // modified protobuf generation until the frame budget is spent.
            throw BrokerToolAuthorizationError.bindingMismatch
        }
        try validateAuthorizedDeadline(
            request.deadlineUnixMs,
            authorization: authorization
        )
    }

    func validateActionAuthorization(
        _ authorization: VerifiedControlPlaneToolAuthorization,
        request: Melix_Computer_V1_ExecuteComputerActionRequest
    ) throws -> Melix_Computer_V1_PressElementAction {
        let arguments = try authorizationArguments(authorization)
        guard
            request.idempotencyKey == authorization.idempotencyKey,
            request.hasApproval,
            request.approval.approvalID
                == authorization.approvalGrantDigest,
            request.approval.policyHash == authorization.policyRevision,
            request.approval.actorID == authorization.actorID,
            request.approval.approvedAtUnixMs
                >= authorization.issuedAtUnixMs,
            request.approval.expiresAtUnixMs
                <= authorization.expiresAtUnixMs,
            arguments["session_id"] as? String
                == request.identity.sessionID,
            arguments["expected_observation_id"] as? String
                == request.expectedObservationID,
            (arguments["expected_frame_generation"] as? NSNumber)?
                .uint64Value == request.expectedFrameGeneration,
            let rawTarget = arguments["target"] as? [String: Any],
            targetMatches(try authorizationTarget(rawTarget), request.target),
            case let .pressElement(press) = request.action,
            press.hasElement,
            let rawElement = arguments["element"] as? [String: Any],
            authorizationElementMatches(rawElement, press.element)
        else {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
        let authorizedAttempt =
            (arguments["attempt"] as? NSNumber)?.uint64Value ?? 1
        guard authorizedAttempt == request.attempt else {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
        try validateAuthorizedDeadline(
            request.deadlineUnixMs,
            authorization: authorization
        )
        return press
    }

    func validateCloseAuthorization(
        _ authorization: VerifiedControlPlaneToolAuthorization,
        request: Melix_Computer_V1_CloseComputerSessionRequest
    ) throws {
        let arguments = try authorizationArguments(authorization)
        guard
            request.closeID == "close-\(authorization.callID)",
            arguments["session_id"] as? String == request.identity.sessionID
        else {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
        let authorizedReason = (
            arguments["reason"] as? String
        )?.trimmingCharacters(in: .whitespacesAndNewlines)
        let expectedReason = authorizedReason?.isEmpty == false
            ? authorizedReason!
            : "tool_requested_close"
        guard request.reason == String(expectedReason.prefix(256)) else {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
    }

    func validateSessionCancellationAuthorization(
        _ authorization: VerifiedControlPlaneToolAuthorization,
        request: Melix_Computer_V1_CancelComputerSessionRequest
    ) throws {
        let arguments = try authorizationArguments(authorization)
        let revocableOperations: Set<String> = [
            "open_session",
            "capture_frame",
            "press_element",
            "close_session",
        ]
        guard
            authorization.runID == request.identity.agentRunID,
            authorization.branchID == request.identity.branchID,
            authorization.actorID == request.identity.actorID,
            let operation = arguments["operation"] as? String,
            revocableOperations.contains(operation)
        else {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
        if let authorizedSessionID = arguments["session_id"] as? String,
           authorizedSessionID != request.identity.sessionID {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
    }

    func authorizationArguments(
        _ authorization: VerifiedControlPlaneToolAuthorization
    ) throws -> [String: Any] {
        guard
            let data = authorization.argumentsJSON.data(using: .utf8),
            let arguments = try JSONSerialization.jsonObject(with: data)
                as? [String: Any]
        else {
            throw BrokerToolAuthorizationError.malformed
        }
        return arguments
    }

    func authorizationTarget(_ raw: Any) throws -> (
        bundleID: String,
        processID: Int32,
        launchIdentity: String,
        windowID: UInt32,
        windowTitle: String
    ) {
        guard
            let target = raw as? [String: Any],
            let bundleID = target["bundle_id"] as? String,
            let processID = target["process_id"] as? NSNumber,
            let launchIdentity =
                target["process_launch_identity"] as? String,
            let windowID = target["window_id"] as? NSNumber,
            let windowTitle = target["window_title"] as? String
        else {
            throw BrokerToolAuthorizationError.malformed
        }
        return (
            bundleID,
            processID.int32Value,
            launchIdentity,
            windowID.uint32Value,
            windowTitle
        )
    }

    func targetMatches(
        _ authorized: (
            bundleID: String,
            processID: Int32,
            launchIdentity: String,
            windowID: UInt32,
            windowTitle: String
        ),
        _ requested: Melix_Computer_V1_TargetIdentity
    ) -> Bool {
        authorized.bundleID == requested.bundleID
            && authorized.processID == requested.processID
            && authorized.launchIdentity
                == requested.processLaunchIdentity
            && authorized.windowID == requested.windowID
            && authorized.windowTitle == requested.windowTitle
    }

    func authorizationElementMatches(
        _ authorized: [String: Any],
        _ requested: Melix_Computer_V1_ElementHandle
    ) -> Bool {
        if let handleID = authorized["handle_id"] as? String,
           handleID != requested.handleID {
            return false
        }
        if let title = authorized["title"] as? String,
           title != requested.title {
            return false
        }
        if let role = authorized["role"] as? String,
           role != requested.role {
            return false
        }
        return authorized["handle_id"] != nil
            || authorized["title"] != nil
    }

    func validateAuthorizedDeadline(
        _ deadlineUnixMs: Int64,
        authorization: VerifiedControlPlaneToolAuthorization
    ) throws {
        guard deadlineUnixMs > 0,
              deadlineUnixMs <= authorization.requestDeadlineUnixMs,
              deadlineUnixMs <= authorization.expiresAtUnixMs
        else {
            throw BrokerToolAuthorizationError.bindingMismatch
        }
    }

    func mapOpenSessionRequest(
        _ request: Melix_Computer_V1_OpenComputerSessionRequest,
        authorization: VerifiedControlPlaneToolAuthorization
    ) throws -> MappedOpenSessionRequest {
        try validateOpenIdentity(request.identity)
        guard request.allowedTargets.count == 1 else {
            throw TransportContractError.invalidRequest("OpenSession requires exactly one target.")
        }
        let targets = try request.allowedTargets.map(mapTarget)
        guard 1...64 ~= request.limits.maximumFrames,
              1...32 ~= request.limits.maximumActions
        else {
            throw TransportContractError.invalidRequest(
                "OpenSession frame and action budgets are outside the supported bounds."
            )
        }
        guard 1...(64 * 1_024 * 1_024) ~= request.limits.maximumArtifactBytes else {
            throw TransportContractError.invalidRequest(
                "OpenSession artifact-byte budget must be between 1 and 67108864 bytes."
            )
        }
        let referenceUnixMs = authorization.issuedAtUnixMs
        let idleMilliseconds = request.limits.idleDeadlineUnixMs - referenceUnixMs
        guard 1_000...300_000 ~= idleMilliseconds else {
            throw TransportContractError.invalidRequest(
                "OpenSession idle deadline must be between 1 and 300 seconds after authorization."
            )
        }
        let absoluteMilliseconds = request.limits.absoluteDeadlineUnixMs - referenceUnixMs
        guard 1_000...600_000 ~= absoluteMilliseconds,
              request.limits.idleDeadlineUnixMs <= request.limits.absoluteDeadlineUnixMs
        else {
            throw TransportContractError.invalidRequest(
                "OpenSession absolute deadline must be between 1 and 600 seconds and not precede the idle deadline."
            )
        }
        let deadline = try requiredDate(
            request.limits.absoluteDeadlineUnixMs,
            field: "absolute session deadline"
        )
        let coreRequest = OpenComputerUseSessionRequest(
            ownerID: request.identity.actorID,
            runID: request.identity.agentRunID,
            allowedBundleIdentifiers: Set(targets.map(\.bundleIdentifier)),
            allowedWindowIDs: Set(targets.map(\.windowID)),
            artifactNamespace: request.artifactRoot,
            limits: ComputerUseSessionLimits(
                maximumFrameCount: Int(request.limits.maximumFrames),
                maximumActionCount: Int(request.limits.maximumActions),
                maximumArtifactBytes: Int(request.limits.maximumArtifactBytes),
                idleTimeoutSeconds: Double(idleMilliseconds) / 1_000,
                absoluteDeadline: deadline
            )
        )
        let scope = "\(request.identity.actorID)\n\(request.identity.agentRunID)\n\(request.idempotencyKey)"
        return MappedOpenSessionRequest(
            idempotencyScope: scope,
            fingerprint: OpenSessionFingerprint(request),
            coreRequest: coreRequest,
            protocolIdentity: request.identity
        )
    }

    func mapActionRequest(
        _ request: Melix_Computer_V1_ExecuteComputerActionRequest,
        press: Melix_Computer_V1_PressElementAction
    ) throws -> PerformComputerActionRequest {
        guard !request.actionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              request.attempt > 0,
              !request.idempotencyKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !request.expectedObservationID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              request.expectedFrameGeneration > 0
        else {
            throw TransportContractError.invalidRequest(
                "ExecuteAction requires action, attempt, idempotency, and frame identifiers."
            )
        }
        try validateFutureDeadline(request.deadlineUnixMs, field: "action deadline")
        let approval = request.approval
        guard approval.actorID == request.identity.actorID,
              !approval.scope.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw TransportContractError.permissionDenied(
                "Approval actor and scope must match the action identity."
            )
        }
        guard press.hasElement,
              press.element.frameGeneration == request.expectedFrameGeneration,
              press.element.enabled,
              !press.element.secure
        else {
            throw TransportContractError.permissionDenied(
                "PressElement requires a current, enabled, non-secure element handle."
            )
        }
        guard !press.element.handleID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || !press.element.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw TransportContractError.invalidRequest(
                "PressElement requires a semantic handle or exact title."
            )
        }
        let action = ComputerAction.press(
            PressAccessibilityElementAction(
                element: AccessibilityElementTarget(
                    accessibilityIdentifier: press.element.handleID,
                    title: press.element.title,
                    role: press.element.role
                )
            )
        )
        return PerformComputerActionRequest(
            sessionID: request.identity.sessionID,
            capability: try mapCapability(request.sessionCapability),
            actionID: request.actionID,
            idempotencyKey: request.idempotencyKey,
            target: try mapTarget(request.target),
            expectedFrameID: request.expectedObservationID,
            expectedFrameGeneration: request.expectedFrameGeneration,
            action: action,
            approval: ComputerUseApprovalGrant(
                approvalID: approval.approvalID,
                actionDigest: approval.actionDigest,
                policyRevision: approval.policyHash,
                approvedByActorID: approval.actorID,
                approvedAt: try requiredDate(approval.approvedAtUnixMs, field: "approval time"),
                expiresAt: try requiredDate(approval.expiresAtUnixMs, field: "approval expiry")
            ),
            deadline: try optionalFutureDate(request.deadlineUnixMs, field: "action deadline")
        )
    }

    func makeLease(
        _ registration: TransportSessionRegistration
    ) -> Melix_Computer_V1_ComputerSessionLease {
        var lease = Melix_Computer_V1_ComputerSessionLease()
        lease.identity = registration.identity
        lease.sessionCapability = Data(registration.session.capability.rawValue.utf8)
        lease.brokerInstanceID = configuration.brokerInstanceID
        lease.allowedTargets = registration.allowedTargets
        lease.limits = registration.limits
        lease.openedAtUnixMs = unixMilliseconds(registration.session.createdAt)
        return lease
    }

    func mapActionEvent(
        _ event: ComputerActionEvent,
        identity: Melix_Computer_V1_ComputerSessionIdentity,
        actionID: String,
        attempt: UInt64
    ) throws -> Melix_Computer_V1_ComputerActionEvent {
        var mapped = Melix_Computer_V1_ComputerActionEvent()
        mapped.identity = identity
        mapped.actionID = actionID
        mapped.attempt = attempt
        mapped.seq = event.sequence
        mapped.phase = mapActionPhase(event)
        mapped.emittedAtUnixMs = unixMilliseconds(event.occurredAt)
        if let receipt = event.receipt {
            mapped.actionID = receipt.actionID
            if let failure = receipt.failure {
                var payload = Melix_Computer_V1_ComputerActionError()
                payload.code = failure.code
                payload.message = failure.message
                payload.retriable = false
                mapped.error = payload
            } else {
                var payload = Melix_Computer_V1_ComputerActionResult()
                payload.actionID = receipt.actionID
                payload.attempt = attempt
                payload.status = receipt.state.rawValue
                payload.requestedTarget = mapTarget(receipt.target)
                payload.actualTarget = mapTarget(receipt.elementSnapshot?.target ?? receipt.target)
                payload.beforeObservationID = receipt.beforeFrame.frameID
                payload.afterObservationID = receipt.afterFrame?.frameID ?? ""
                payload.artifacts = try actionArtifacts(receipt)
                payload.adapterKind = receipt.adapterKind
                payload.actionMode = "ax_semantic_press"
                payload.evidenceReceiptJson = try encodeEvidence(receipt)
                mapped.result = payload
            }
        }
        return mapped
    }

    func actionArtifacts(
        _ receipt: ComputerActionReceipt
    ) throws -> [Melix_Computer_V1_ArtifactReference] {
        var artifacts = [try mapArtifact(receipt.beforeFrame.artifact)]
        if let after = receipt.afterFrame?.artifact {
            artifacts.append(try mapArtifact(after))
        }
        if let evidence = receipt.evidenceArtifact {
            artifacts.append(try mapArtifact(evidence))
        }
        return artifacts
    }

    func mapArtifact(
        _ artifact: ComputerArtifactReference
    ) throws -> Melix_Computer_V1_ArtifactReference {
        let root = configuration.artifactRoot.standardizedFileURL.path
        let path = URL(fileURLWithPath: artifact.path).standardizedFileURL.path
        guard path.hasPrefix(root + "/") else {
            throw TransportContractError.internalFailure(
                "Broker artifact escaped the configured transport root."
            )
        }
        var mapped = Melix_Computer_V1_ArtifactReference()
        mapped.artifactID = artifact.artifactID
        mapped.relativePath = String(path.dropFirst(root.count + 1))
        mapped.sha256 = artifact.sha256
        mapped.mediaType = artifact.mediaType
        mapped.byteLength = UInt64(clamping: max(0, artifact.byteCount))
        mapped.width = UInt32(clamping: max(0, artifact.width))
        mapped.height = UInt32(clamping: max(0, artifact.height))
        mapped.redactionReceiptJson = "{\"applied\":false}"
        return mapped
    }

    func permissionSnapshot(
        _ snapshot: ComputerUsePermissionSnapshot
    ) -> Melix_Computer_V1_PermissionSnapshot {
        var mapped = Melix_Computer_V1_PermissionSnapshot()
        mapped.screenRecording = mapPermission(snapshot.screenCapture)
        mapped.accessibility = mapPermission(snapshot.accessibility)
        mapped.coordinateFallbackEnabled = false
        mapped.secureFieldActionsAllowed = false
        mapped.observedAtUnixMs = unixMilliseconds(Date())
        return mapped
    }
}

private struct BrokerAdmissionVerifier: Sendable {
    func validateHandshake(
        request: Melix_Computer_V1_BrokerHandshakeRequest,
        policy: BrokerHandshakePolicy
    ) throws {
        guard !request.controlPlaneInstanceID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else {
            throw RPCError(
                code: .invalidArgument,
                message: "Handshake requires control-plane instance identity."
            )
        }
        guard request.protocolVersion == policy.protocolVersion else {
            throw RPCError(code: .failedPrecondition, message: "Broker protocol version mismatch.")
        }
        guard request.callerBundleID == policy.expectedCallerBundleID,
              request.callerTeamID == policy.expectedCallerTeamID,
              constantTimeEqual(
                  request.callerVerificationCapability,
                  policy.verificationCapability
              )
        else {
            throw RPCError(code: .unauthenticated, message: "Broker handshake verification failed.")
        }
    }

    func requireCapability(
        _ capability: Data,
        policy: BrokerHandshakePolicy
    ) throws {
        guard constantTimeEqual(capability, policy.verificationCapability) else {
            throw RPCError(
                code: .unauthenticated,
                message: "Broker caller verification capability was rejected."
            )
        }
    }
}

private actor TransportSessionRegistry {
    private enum OpenState {
        case pending(OpenSessionFingerprint, Task<TransportSessionRegistration, Error>)
        case completed(OpenSessionFingerprint, TransportSessionRegistration)
    }

    private var opens: [String: OpenState] = [:]
    private var sessions: [String: TransportSessionRegistration] = [:]

    func open(
        key: String,
        fingerprint: OpenSessionFingerprint,
        broker: any ComputerUseBroker,
        request: OpenComputerUseSessionRequest,
        protocolIdentity: Melix_Computer_V1_ComputerSessionIdentity,
        allowedTargets: [Melix_Computer_V1_TargetIdentity],
        limits: Melix_Computer_V1_ComputerSessionLimits
    ) async throws -> TransportSessionRegistration {
        if let existing = opens[key] {
            switch existing {
            case let .pending(existingFingerprint, task):
                guard existingFingerprint == fingerprint else {
                    throw TransportContractError.idempotencyConflict
                }
                do {
                    let registration = try await task.value
                    opens[key] = .completed(fingerprint, registration)
                    sessions[registration.identity.sessionID] = registration
                    return registration
                } catch {
                    opens.removeValue(forKey: key)
                    throw error
                }
            case let .completed(existingFingerprint, registration):
                guard existingFingerprint == fingerprint else {
                    throw TransportContractError.idempotencyConflict
                }
                return registration
            }
        }

        let task = Task<TransportSessionRegistration, Error> {
            let session = try await broker.openSession(request)
            var identity = protocolIdentity
            identity.sessionID = session.sessionID
            return TransportSessionRegistration(
                session: session,
                identity: identity,
                allowedTargets: allowedTargets,
                allowedTargetKeys: Set(allowedTargets.map(TargetKey.init)),
                limits: limits,
                latestFrameGeneration: 0,
                pendingCapture: nil,
                actionAttempts: [:],
                closed: false
            )
        }
        opens[key] = .pending(fingerprint, task)
        do {
            let registration = try await task.value
            opens[key] = .completed(fingerprint, registration)
            sessions[registration.identity.sessionID] = registration
            return registration
        } catch {
            opens.removeValue(forKey: key)
            throw error
        }
    }

    func validateSession(
        identity: Melix_Computer_V1_ComputerSessionIdentity
    ) throws -> TransportSessionRegistration {
        guard let registration = sessions[identity.sessionID] else {
            throw TransportContractError.sessionNotFound
        }
        guard identitiesMatch(identity, registration.identity) else {
            throw TransportContractError.scopeMismatch
        }
        return registration
    }

    func reserveCapture(
        identity: Melix_Computer_V1_ComputerSessionIdentity,
        target: Melix_Computer_V1_TargetIdentity,
        expectedPreviousGeneration: UInt64
    ) throws -> TransportCaptureReservation {
        var registration = try validateSession(identity: identity)
        guard !registration.closed else {
            throw TransportContractError.sessionClosed
        }
        guard registration.allowedTargetKeys.contains(TargetKey(target)) else {
            throw TransportContractError.scopeMismatch
        }
        guard registration.latestFrameGeneration == expectedPreviousGeneration else {
            throw TransportContractError.staleFrame
        }
        guard registration.pendingCapture == nil else {
            throw TransportContractError.staleFrame
        }
        let reservation = TransportCaptureReservation(
            reservationID: UUID().uuidString.lowercased(),
            expectedPreviousGeneration: expectedPreviousGeneration,
            registration: registration
        )
        registration.pendingCapture = TransportCaptureReservationState(
            reservationID: reservation.reservationID,
            expectedPreviousGeneration: expectedPreviousGeneration
        )
        sessions[identity.sessionID] = registration
        return reservation
    }

    func commitCapture(
        _ reservation: TransportCaptureReservation,
        generation: UInt64
    ) throws {
        let sessionID = reservation.registration.identity.sessionID
        guard var registration = sessions[sessionID] else {
            throw TransportContractError.sessionNotFound
        }
        guard !registration.closed else {
            throw TransportContractError.sessionClosed
        }
        guard registration.pendingCapture?.reservationID == reservation.reservationID,
              registration.pendingCapture?.expectedPreviousGeneration
                == reservation.expectedPreviousGeneration,
              registration.latestFrameGeneration == reservation.expectedPreviousGeneration,
              generation > registration.latestFrameGeneration
        else {
            throw TransportContractError.staleFrame
        }
        registration.latestFrameGeneration = generation
        registration.pendingCapture = nil
        sessions[sessionID] = registration
    }

    func rollbackCapture(_ reservation: TransportCaptureReservation) {
        let sessionID = reservation.registration.identity.sessionID
        guard var registration = sessions[sessionID],
              registration.pendingCapture?.reservationID == reservation.reservationID
        else {
            return
        }
        registration.pendingCapture = nil
        sessions[sessionID] = registration
    }

    func registerAction(
        identity: Melix_Computer_V1_ComputerSessionIdentity,
        target: Melix_Computer_V1_TargetIdentity,
        actionID: String,
        attempt: UInt64
    ) throws -> TransportSessionRegistration {
        var registration = try validateSession(identity: identity)
        guard !registration.closed else {
            throw TransportContractError.sessionClosed
        }
        guard registration.allowedTargetKeys.contains(TargetKey(target)) else {
            throw TransportContractError.scopeMismatch
        }
        if let existing = registration.actionAttempts[actionID], existing != attempt {
            throw TransportContractError.idempotencyConflict
        }
        registration.actionAttempts[actionID] = attempt
        sessions[identity.sessionID] = registration
        return registration
    }

    func validateActionAttempt(
        identity: Melix_Computer_V1_ComputerSessionIdentity,
        actionID: String,
        attempt: UInt64
    ) throws -> TransportSessionRegistration {
        let registration = try validateSession(identity: identity)
        if let existing = registration.actionAttempts[actionID], existing != attempt {
            throw TransportContractError.scopeMismatch
        }
        return registration
    }

    func markClosed(sessionID: String) {
        guard var registration = sessions[sessionID] else {
            return
        }
        registration.closed = true
        sessions[sessionID] = registration
    }
}

private struct MappedOpenSessionRequest: Sendable {
    let idempotencyScope: String
    let fingerprint: OpenSessionFingerprint
    let coreRequest: OpenComputerUseSessionRequest
    let protocolIdentity: Melix_Computer_V1_ComputerSessionIdentity
}

private struct TransportSessionRegistration: Sendable {
    let session: ComputerUseSession
    let identity: Melix_Computer_V1_ComputerSessionIdentity
    let allowedTargets: [Melix_Computer_V1_TargetIdentity]
    let allowedTargetKeys: Set<TargetKey>
    let limits: Melix_Computer_V1_ComputerSessionLimits
    var latestFrameGeneration: UInt64
    var pendingCapture: TransportCaptureReservationState?
    var actionAttempts: [String: UInt64]
    var closed: Bool
}

private struct TransportCaptureReservation: Sendable {
    let reservationID: String
    let expectedPreviousGeneration: UInt64
    let registration: TransportSessionRegistration
}

private struct TransportCaptureReservationState: Sendable {
    let reservationID: String
    let expectedPreviousGeneration: UInt64
}

private struct TargetKey: Sendable, Hashable {
    let bundleID: String
    let processID: Int32
    let processLaunchIdentity: String
    let windowID: UInt32
    let windowTitle: String

    init(_ target: Melix_Computer_V1_TargetIdentity) {
        bundleID = target.bundleID
        processID = target.processID
        processLaunchIdentity = target.processLaunchIdentity
        windowID = target.windowID
        windowTitle = target.windowTitle
    }
}

private struct OpenSessionFingerprint: Sendable, Equatable {
    let identity: IdentityKey
    let allowedTargets: [TargetKey]
    let artifactRoot: String
    let maximumFrames: UInt32
    let maximumActions: UInt32
    let maximumArtifactBytes: UInt32
    let idleDeadlineUnixMs: Int64
    let absoluteDeadlineUnixMs: Int64

    init(_ request: Melix_Computer_V1_OpenComputerSessionRequest) {
        identity = IdentityKey(request.identity)
        // OpenSession admits exactly one target, so protocol order is already
        // canonical and no wider target-ordering surface is required.
        allowedTargets = request.allowedTargets.map(TargetKey.init)
        artifactRoot = request.artifactRoot
        maximumFrames = request.limits.maximumFrames
        maximumActions = request.limits.maximumActions
        maximumArtifactBytes = request.limits.maximumArtifactBytes
        idleDeadlineUnixMs = request.limits.idleDeadlineUnixMs
        absoluteDeadlineUnixMs = request.limits.absoluteDeadlineUnixMs
    }
}

private struct IdentityKey: Sendable, Equatable {
    let agentRunID: String
    let requestID: String
    let toolCallID: String
    let sessionID: String
    let branchID: String
    let actorID: String

    init(_ identity: Melix_Computer_V1_ComputerSessionIdentity) {
        agentRunID = identity.agentRunID
        requestID = identity.requestID
        toolCallID = identity.toolCallID
        sessionID = identity.sessionID
        branchID = identity.branchID
        actorID = identity.actorID
    }
}

enum TransportContractError: Error, Sendable, Equatable {
    case invalidRequest(String)
    case unsupported(String)
    case permissionDenied(String)
    case internalFailure(String)
    case idempotencyConflict
    case sessionNotFound
    case sessionClosed
    case scopeMismatch
    case staleFrame
}

private func validateOpenIdentity(
    _ identity: Melix_Computer_V1_ComputerSessionIdentity
) throws {
    guard identity.sessionID.isEmpty else {
        throw TransportContractError.invalidRequest(
            "OpenSession identity must not contain a preselected session ID."
        )
    }
    let identifiers = [
        identity.agentRunID,
        identity.requestID,
        identity.toolCallID,
        identity.branchID,
        identity.actorID,
    ]
    guard identifiers.allSatisfy({ value in
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return !trimmed.isEmpty && trimmed.count <= 256
    }) else {
        throw TransportContractError.invalidRequest(
            "OpenSession identity fields must be non-empty and bounded."
        )
    }
}

private func identitiesMatch(
    _ lhs: Melix_Computer_V1_ComputerSessionIdentity,
    _ rhs: Melix_Computer_V1_ComputerSessionIdentity
) -> Bool {
    IdentityKey(lhs) == IdentityKey(rhs)
}

private func mapTarget(
    _ target: Melix_Computer_V1_TargetIdentity
) throws -> ComputerWindowTarget {
    guard !target.bundleID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
          target.processID > 0,
          !target.processLaunchIdentity.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
          target.windowID > 0,
          target.windowTitle.utf8.count <= 512,
          target.applicationName.utf8.count <= 256
    else {
        throw TransportContractError.invalidRequest(
            "Computer target requires bounded bundle, process, launch, and window identity."
        )
    }
    return ComputerWindowTarget(
        bundleIdentifier: target.bundleID,
        processIdentifier: target.processID,
        processLaunchIdentity: target.processLaunchIdentity,
        windowID: target.windowID,
        windowTitle: target.windowTitle,
        applicationName: target.applicationName
    )
}

private func mapTarget(
    _ target: ComputerWindowTarget
) -> Melix_Computer_V1_TargetIdentity {
    var mapped = Melix_Computer_V1_TargetIdentity()
    mapped.bundleID = target.bundleIdentifier
    mapped.processID = target.processIdentifier
    mapped.processLaunchIdentity = target.processLaunchIdentity
    mapped.windowID = target.windowID
    mapped.windowTitle = target.windowTitle
    mapped.applicationName = target.applicationName
    return mapped
}

private func mapCapability(_ capability: Data) throws -> ComputerUseSessionCapability {
    guard let value = String(data: capability, encoding: .utf8), !value.isEmpty else {
        throw TransportContractError.permissionDenied("Session capability was rejected.")
    }
    return ComputerUseSessionCapability(rawValue: value)
}

private func mapPermission(
    _ state: ComputerUsePermissionState
) -> Melix_Computer_V1_PermissionState {
    switch state {
    case .granted: .permissionGranted
    case .notGranted: .permissionDenied
    case .unavailable: .permissionUnavailable
    }
}

private func mapCancellationDisposition(
    _ disposition: ComputerActionCancelDisposition
) -> Melix_Computer_V1_ComputerCancellationDisposition {
    switch disposition {
    case .accepted: .computerCancellationAccepted
    case .alreadyTerminal: .computerCancellationAlreadyTerminal
    case .tooLate: .computerCancellationTooLate
    case .notFound: .computerCancellationNotFound
    case .scopeMismatch: .computerCancellationScopeMismatch
    }
}

private func mapSessionCancellationDisposition(
    _ disposition: ComputerSessionCancelDisposition
) -> Melix_Computer_V1_ComputerSessionCancellationDisposition {
    switch disposition {
    case .accepted: .computerSessionCancellationAccepted
    case .alreadyTerminal: .computerSessionCancellationAlreadyTerminal
    case .notFound: .computerSessionCancellationNotFound
    case .scopeMismatch: .computerSessionCancellationScopeMismatch
    }
}

private func mapActionPhase(
    _ event: ComputerActionEvent
) -> Melix_Computer_V1_ComputerActionPhase {
    switch event.state {
    case .queued: .computerActionQueued
    case .preflighting: .computerActionStarted
    case .readyToCommit: .computerActionPreconditionChecked
    case .committing:
        event.message == "Accessibility action committed."
            ? .computerActionCommitted
            : .computerActionCommitStarted
    case .completed: .computerActionCompleted
    case .cancelled: .computerActionCancelled
    case .failed: .computerActionFailed
    }
}

func optionalFutureDate(_ milliseconds: Int64, field: String) throws -> Date? {
    guard milliseconds != 0 else {
        return nil
    }
    let date = try requiredDate(milliseconds, field: field)
    guard date > Date() else {
        throw TransportContractError.invalidRequest("\(field) has expired.")
    }
    return date
}

private func validateFutureDeadline(_ milliseconds: Int64, field: String) throws {
    _ = try optionalFutureDate(milliseconds, field: field)
}

func requiredDate(_ milliseconds: Int64, field: String) throws -> Date {
    guard milliseconds > 0 else {
        throw TransportContractError.invalidRequest("\(field) must be a positive Unix timestamp.")
    }
    return Date(timeIntervalSince1970: Double(milliseconds) / 1_000)
}

private func unixMilliseconds(_ date: Date) -> Int64 {
    Int64((date.timeIntervalSince1970 * 1_000).rounded())
}

func encodeEvidence<T: Encodable>(_ value: T) throws -> String {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    encoder.dateEncodingStrategy = .iso8601
    let data = try encoder.encode(value)
    guard data.count <= 64 * 1_024, let result = String(data: data, encoding: .utf8) else {
        throw TransportContractError.internalFailure(
            "Computer Use evidence receipt exceeded the transport bound."
        )
    }
    return result
}

func mapRPCError(_ error: Error) -> RPCError {
    if let rpcError = error as? RPCError {
        return rpcError
    }
    if let contract = error as? TransportContractError {
        switch contract {
        case let .invalidRequest(message):
            return RPCError(code: .invalidArgument, message: message)
        case let .unsupported(message):
            return RPCError(code: .unimplemented, message: message)
        case let .permissionDenied(message):
            return RPCError(code: .permissionDenied, message: message)
        case let .internalFailure(message):
            return RPCError(code: .internalError, message: message)
        case .idempotencyConflict:
            return RPCError(code: .alreadyExists, message: "Idempotency scope was reused with different input.")
        case .sessionNotFound:
            return RPCError(code: .notFound, message: "Computer Use session was not found.")
        case .sessionClosed:
            return RPCError(code: .failedPrecondition, message: "Computer Use session is closed.")
        case .scopeMismatch:
            return RPCError(code: .permissionDenied, message: "Computer Use identity or target scope mismatch.")
        case .staleFrame:
            return RPCError(code: .failedPrecondition, message: "Computer Use frame generation is stale.")
        }
    }
    if let authorization = error as? BrokerToolAuthorizationError {
        switch authorization {
        case .invalidConfiguration:
            return RPCError(
                code: .internalError,
                message: "Computer Use authorization verifier is unavailable."
            )
        case .missing:
            return RPCError(
                code: .unauthenticated,
                message: authorization.localizedDescription
            )
        case .malformed, .invalidSignature, .expired, .bindingMismatch:
            return RPCError(
                code: .permissionDenied,
                message: authorization.localizedDescription
            )
        }
    }
    if let brokerError = error as? ComputerUseBrokerError {
        let message = brokerError.localizedDescription
        switch brokerError {
        case .invalidRequest:
            return RPCError(code: .invalidArgument, message: message)
        case .sessionNotFound:
            return RPCError(code: .notFound, message: message)
        case .invalidSessionCapability:
            return RPCError(code: .unauthenticated, message: message)
        case .sessionClosed, .sessionExpired, .sessionIdleExpired,
             .frameRequired, .staleFrame, .idempotencyConflict:
            return RPCError(code: .failedPrecondition, message: message)
        case .targetOutOfScope, .approvalDigestMismatch, .approvalExpired, .approvalReplay,
             .secureFieldRefused, .permissionDenied:
            return RPCError(code: .permissionDenied, message: message)
        case .frameBudgetExceeded, .actionBudgetExceeded, .artifactBudgetExceeded:
            return RPCError(code: .resourceExhausted, message: message)
        case .adapterFailure:
            return RPCError(code: .unavailable, message: message)
        case .evidenceFailure:
            return RPCError(code: .internalError, message: message)
        }
    }
    return RPCError(
        code: .internalError,
        message: "Computer Use broker transport failed.",
        cause: error
    )
}
