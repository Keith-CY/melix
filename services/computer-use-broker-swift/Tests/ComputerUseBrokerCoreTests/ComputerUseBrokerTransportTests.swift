import ComputerUseBrokerCore
@testable import ComputerUseBrokerTransport
import CryptoKit
import Darwin
import Foundation
import GRPCCore
import GRPCNIOTransportHTTP2Posix
import MelixComputerProtocol
import Testing

private let testVerificationCapability = Data(repeating: 0xA5, count: 32)

@Suite("Computer Use Broker gRPC transport", .serialized)
struct ComputerUseBrokerTransportTests {
    @Test("transport error taxonomy and bounded evidence remain stable")
    func transportErrorTaxonomyAndEvidenceBounds() throws {
        let passthrough = RPCError(code: .aborted, message: "passthrough")
        #expect(mapRPCError(passthrough).code == .aborted)

        let contractCases: [(TransportContractError, RPCError.Code)] = [
            (.invalidRequest("invalid"), .invalidArgument),
            (.unsupported("unsupported"), .unimplemented),
            (.permissionDenied("denied"), .permissionDenied),
            (.internalFailure("internal"), .internalError),
            (.idempotencyConflict, .alreadyExists),
            (.sessionNotFound, .notFound),
            (.sessionClosed, .failedPrecondition),
            (.scopeMismatch, .permissionDenied),
            (.staleFrame, .failedPrecondition),
        ]
        for (error, expectedCode) in contractCases {
            #expect(mapRPCError(error).code == expectedCode)
        }

        let authorizationCases: [(BrokerToolAuthorizationError, RPCError.Code)] = [
            (.invalidConfiguration("invalid"), .internalError),
            (.missing, .unauthenticated),
            (.malformed, .permissionDenied),
            (.invalidSignature, .permissionDenied),
            (.expired, .permissionDenied),
            (.bindingMismatch, .permissionDenied),
        ]
        for (error, expectedCode) in authorizationCases {
            #expect(mapRPCError(error).code == expectedCode)
        }

        let brokerCases: [(ComputerUseBrokerError, RPCError.Code)] = [
            (.invalidRequest("invalid"), .invalidArgument),
            (.sessionNotFound, .notFound),
            (.invalidSessionCapability, .unauthenticated),
            (.sessionClosed, .failedPrecondition),
            (.sessionExpired, .failedPrecondition),
            (.sessionIdleExpired, .failedPrecondition),
            (.frameRequired, .failedPrecondition),
            (.staleFrame, .failedPrecondition),
            (.idempotencyConflict, .failedPrecondition),
            (.targetOutOfScope, .permissionDenied),
            (.approvalDigestMismatch, .permissionDenied),
            (.approvalExpired, .permissionDenied),
            (.approvalReplay, .permissionDenied),
            (.secureFieldRefused, .permissionDenied),
            (.permissionDenied("accessibility"), .permissionDenied),
            (.frameBudgetExceeded, .resourceExhausted),
            (.actionBudgetExceeded, .resourceExhausted),
            (.artifactBudgetExceeded, .resourceExhausted),
            (.adapterFailure("offline"), .unavailable),
            (.evidenceFailure("write failed"), .internalError),
        ]
        for (error, expectedCode) in brokerCases {
            #expect(mapRPCError(error).code == expectedCode)
        }

        struct UnknownTransportFailure: Error {}
        #expect(mapRPCError(UnknownTransportFailure()).code == .internalError)
        #expect(try optionalFutureDate(0, field: "optional") == nil)
        #expect(throws: TransportContractError.self) {
            _ = try requiredDate(0, field: "required")
        }
        #expect(throws: TransportContractError.self) {
            _ = try encodeEvidence([
                "payload": String(repeating: "x", count: 65 * 1_024),
            ])
        }
    }

    @Test("private UDS lists bounded authoritative window identities")
    func realUnixDomainSocketListsTargets() async throws {
        let expected = ComputerWindowTarget(
            bundleIdentifier: "io.melix.fixture",
            processIdentifier: 4242,
            processLaunchIdentity: "fixture-launch-target-list-1",
            windowID: 77,
            windowTitle: "Computer Use Fixture",
            applicationName: "Fixture App"
        )
        let fixture = try await LiveComputerBrokerFixture.start(
            frameCapture: TargetInventoryFrameCaptureAdapter(targets: [expected])
        )
        do {
            let transport = try HTTP2ClientTransport.Posix(
                target: .unixDomainSocket(path: fixture.socketPath),
                transportSecurity: .plaintext
            )
            try await withGRPCClient(transport: transport) { client in
                let rpc = Melix_Computer_V1_ComputerUseBrokerService.Client(
                    wrapping: client
                )
                _ = try await rpc.handshake(
                    makeHandshake(capability: fixture.verificationCapability)
                )
                await expectRPCError(.unauthenticated) {
                    try await rpc.listTargets(
                        Melix_Computer_V1_ListComputerTargetsRequest()
                    )
                }
                var request = Melix_Computer_V1_ListComputerTargetsRequest()
                request.callerVerificationCapability = fixture.verificationCapability
                request.authorization = try fixture.authorization(
                    callID: "list-targets-transport-1",
                    arguments: ["operation": "list_targets"]
                )
                let response = try await rpc.listTargets(request)
                let target = try #require(response.targets.first)
                #expect(response.targets.count == 1)
                #expect(response.observedAtUnixMs > 0)
                #expect(target.bundleID == expected.bundleIdentifier)
                #expect(target.processID == expected.processIdentifier)
                #expect(
                    target.processLaunchIdentity
                        == expected.processLaunchIdentity
                )
                #expect(target.windowID == expected.windowID)
                #expect(target.windowTitle == expected.windowTitle)
                #expect(target.applicationName == expected.applicationName)

                var wrongOperation = request
                wrongOperation.authorization = try fixture.authorization(
                    callID: "list-targets-transport-2",
                    arguments: ["operation": "get_permissions"]
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.listTargets(wrongOperation)
                }
            }
        } catch {
            await fixture.stop()
            fixture.removeFiles()
            throw error
        }
        await fixture.stop()
        fixture.removeFiles()
    }

    @Test("private UDS rejects oversized and duplicate target inventories")
    func realUnixDomainSocketRejectsInvalidTargetInventories() async throws {
        let base = ComputerWindowTarget(
            bundleIdentifier: "io.melix.fixture",
            processIdentifier: 4242,
            processLaunchIdentity: "fixture-launch-target-list-1",
            windowID: 77,
            windowTitle: "Computer Use Fixture",
            applicationName: "Fixture App"
        )
        var oversized: [ComputerWindowTarget] = []
        for windowID in 1...129 {
            oversized.append(
                ComputerWindowTarget(
                    bundleIdentifier: base.bundleIdentifier,
                    processIdentifier: base.processIdentifier,
                    processLaunchIdentity: base.processLaunchIdentity,
                    windowID: UInt32(windowID),
                    windowTitle: "Window \(windowID)",
                    applicationName: base.applicationName
                )
            )
        }

        for targets in [oversized, [base, base]] {
            let fixture = try await LiveComputerBrokerFixture.start(
                frameCapture: TargetInventoryFrameCaptureAdapter(targets: targets)
            )
            do {
                let transport = try HTTP2ClientTransport.Posix(
                    target: .unixDomainSocket(path: fixture.socketPath),
                    transportSecurity: .plaintext
                )
                try await withGRPCClient(transport: transport) { client in
                    let rpc = Melix_Computer_V1_ComputerUseBrokerService.Client(
                        wrapping: client
                    )
                    var request = Melix_Computer_V1_ListComputerTargetsRequest()
                    request.callerVerificationCapability =
                        fixture.verificationCapability
                    request.authorization = try fixture.authorization(
                        callID: "list-targets-invalid-inventory",
                        arguments: ["operation": "list_targets"]
                    )
                    await expectRPCError(.internalError) {
                        try await rpc.listTargets(request)
                    }
                }
            } catch {
                await fixture.stop()
                fixture.removeFiles()
                throw error
            }
            await fixture.stop()
            fixture.removeFiles()
        }
    }

    @Test("one UDS client handshake never admits another client")
    func handshakeCannotBeBorrowedAcrossUDSConnections() async throws {
        let fixture = try await LiveComputerBrokerFixture.start()
        do {
            let transportA = try HTTP2ClientTransport.Posix(
                target: .unixDomainSocket(path: fixture.socketPath),
                transportSecurity: .plaintext
            )
            try await withGRPCClient(transport: transportA) { clientA in
                let rpcA = Melix_Computer_V1_ComputerUseBrokerService.Client(
                    wrapping: clientA
                )
                _ = try await rpcA.handshake(
                    makeHandshake(capability: fixture.verificationCapability)
                )

                let transportB = try HTTP2ClientTransport.Posix(
                    target: .unixDomainSocket(path: fixture.socketPath),
                    transportSecurity: .plaintext
                )
                try await withGRPCClient(transport: transportB) { clientB in
                    let rpcB = Melix_Computer_V1_ComputerUseBrokerService.Client(
                        wrapping: clientB
                    )
                    var request = Melix_Computer_V1_PermissionPromptRequest()
                    request.kind = .permissionAccessibility
                    request.actorID = "operator-second-client"
                    request.operatorGestureID = "unverified-gesture"
                    request.authorization = try fixture.authorization(
                        callID: "permission-second-client",
                        arguments: [
                            "operation": "request_permission",
                            "kind": "accessibility",
                            "actor_id": request.actorID,
                            "operator_gesture_id": request.operatorGestureID,
                        ],
                        actorID: request.actorID
                    )

                    await expectRPCError(.unauthenticated) {
                        try await rpcB.requestPermission(request)
                    }
                    request.callerVerificationCapability = Data(
                        repeating: 0x5A,
                        count: 32
                    )
                    await expectRPCError(.unauthenticated) {
                        try await rpcB.requestPermission(request)
                    }

                    request.callerVerificationCapability =
                        fixture.verificationCapability
                    let receipt = try await rpcB.requestPermission(request)
                    #expect(!receipt.promptRequested)
                    #expect(
                        receipt.disposition
                            == "refused_no_verified_operator_gesture_seam"
                    )
                }
            }
        } catch {
            await fixture.stop()
            fixture.removeFiles()
            throw error
        }
        await fixture.stop()
        fixture.removeFiles()
    }

    @Test("omitted capture generation authorizes only the first frame over the real UDS")
    func omittedCaptureGenerationCannotBeReplayed() async throws {
        let frames = FakeFrameCaptureAdapter()
        let fixture = try await LiveComputerBrokerFixture.start(
            frameCapture: frames
        )
        do {
            let transport = try HTTP2ClientTransport.Posix(
                target: .unixDomainSocket(path: fixture.socketPath),
                transportSecurity: .plaintext
            )
            try await withGRPCClient(transport: transport) { client in
                let rpc = Melix_Computer_V1_ComputerUseBrokerService.Client(
                    wrapping: client
                )
                _ = try await rpc.handshake(
                    makeHandshake(capability: fixture.verificationCapability)
                )
                var open = makeOpenRequest()
                open.limits.maximumFrames = 2
                open = try authorizeOpen(open, fixture: fixture)
                let lease = try await rpc.openSession(open)
                let target = try #require(open.allowedTargets.first)

                var first = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "omitted-generation-replay"
                )
                first.deadlineUnixMs = Int64(
                    fixture.clock.now().addingTimeInterval(30)
                        .timeIntervalSince1970 * 1_000
                )
                first.authorization = try fixture.authorization(
                    callID: "omitted-generation-replay",
                    arguments: [
                        "operation": "capture_frame",
                        "session_id": lease.identity.sessionID,
                        "target": targetPayload(target),
                    ],
                    runID: first.identity.agentRunID,
                    sessionID: first.identity.sessionID,
                    branchID: first.identity.branchID,
                    actorID: first.identity.actorID
                )
                _ = try await rpc.captureFrame(first)

                var replay = first
                replay.expectedPreviousGeneration = 1
                await expectRPCError(.permissionDenied) {
                    try await rpc.captureFrame(replay)
                }
                #expect(await frames.captureCount() == 1)
            }
        } catch {
            await fixture.stop()
            fixture.removeFiles()
            throw error
        }
        await fixture.stop()
        fixture.removeFiles()
    }

    @Test("real private UDS maps handshake, session, capture, execute cancellation, and close")
    func realUnixDomainSocketContract() async throws {
        let fixture = try await LiveComputerBrokerFixture.start()
        do {
            let attributes = try FileManager.default.attributesOfItem(atPath: fixture.socketPath)
            let permissions = try #require(attributes[.posixPermissions] as? NSNumber)
            #expect(permissions.intValue & 0o077 == 0)

            let transport = try HTTP2ClientTransport.Posix(
                target: .unixDomainSocket(path: fixture.socketPath),
                transportSecurity: .plaintext
            )
            try await withGRPCClient(transport: transport) { client in
                let rpc = Melix_Computer_V1_ComputerUseBrokerService.Client(wrapping: client)

                await expectRPCError(.unauthenticated) {
                    try await rpc.openSession(makeOpenRequest())
                }

                var invalidHandshake = makeHandshake(capability: Data(repeating: 0x00, count: 32))
                invalidHandshake.callerTeamID = "WRONGTEAM"
                await expectRPCError(.unauthenticated) {
                    try await rpc.handshake(invalidHandshake)
                }
                var missingInstance = makeHandshake(
                    capability: fixture.verificationCapability
                )
                missingInstance.controlPlaneInstanceID = " "
                await expectRPCError(.invalidArgument) {
                    try await rpc.handshake(missingInstance)
                }
                var wrongVersion = makeHandshake(
                    capability: fixture.verificationCapability
                )
                wrongVersion.protocolVersion = "2"
                await expectRPCError(.failedPrecondition) {
                    try await rpc.handshake(wrongVersion)
                }
                await expectRPCError(.unauthenticated) {
                    try await rpc.handshake(
                        makeHandshake(capability: Data(repeating: 0xA5, count: 31))
                    )
                }

                let handshake = try await rpc.handshake(
                    makeHandshake(capability: fixture.verificationCapability)
                )
                #expect(handshake.protocolVersion == "1")
                #expect(handshake.brokerInstanceID == "broker-uds-test")
                #expect(handshake.features.contains("ax_semantic_press"))
                #expect(handshake.features.contains("action_surface_semantic_press_only"))
                #expect(handshake.features.contains("transport_peer_code_identity_unavailable"))

                await expectRPCError(.unauthenticated) {
                    try await rpc.getPermissions(
                        Melix_Computer_V1_GetPermissionsRequest()
                    )
                }
                var permissionsRequest = Melix_Computer_V1_GetPermissionsRequest()
                permissionsRequest.callerVerificationCapability =
                    fixture.verificationCapability
                permissionsRequest.authorization = try fixture.authorization(
                    callID: "permissions-transport-1",
                    arguments: ["operation": "get_permissions"]
                )
                let permissions = try await rpc.getPermissions(permissionsRequest)
                #expect(permissions.screenRecording == .permissionGranted)
                #expect(permissions.accessibility == .permissionGranted)
                #expect(!permissions.coordinateFallbackEnabled)
                #expect(!permissions.secureFieldActionsAllowed)

                var missingPermissionKind =
                    Melix_Computer_V1_PermissionPromptRequest()
                missingPermissionKind.callerVerificationCapability =
                    fixture.verificationCapability
                missingPermissionKind.authorization = try fixture.authorization(
                    callID: "permission-missing-kind",
                    arguments: ["operation": "request_permission"]
                )
                await expectRPCError(.invalidArgument) {
                    try await rpc.requestPermission(missingPermissionKind)
                }
                var missingGesture = Melix_Computer_V1_PermissionPromptRequest()
                missingGesture.kind = .permissionAccessibility
                missingGesture.callerVerificationCapability =
                    fixture.verificationCapability
                missingGesture.authorization = try fixture.authorization(
                    callID: "permission-missing-gesture",
                    arguments: ["operation": "request_permission"]
                )
                await expectRPCError(.invalidArgument) {
                    try await rpc.requestPermission(missingGesture)
                }

                var prompt = Melix_Computer_V1_PermissionPromptRequest()
                prompt.kind = .permissionAccessibility
                prompt.actorID = "operator-transport"
                prompt.operatorGestureID = "unverified-gesture"
                prompt.callerVerificationCapability = fixture.verificationCapability
                prompt.authorization = try fixture.authorization(
                    callID: "permission-refused",
                    arguments: [
                        "operation": "request_permission",
                        "kind": "accessibility",
                        "actor_id": prompt.actorID,
                        "operator_gesture_id": prompt.operatorGestureID,
                    ]
                )
                let promptReceipt = try await rpc.requestPermission(prompt)
                #expect(!promptReceipt.promptRequested)
                #expect(promptReceipt.disposition == "refused_no_verified_operator_gesture_seam")
                var reboundPrompt = prompt
                reboundPrompt.operatorGestureID = "different-gesture"
                await expectRPCError(.permissionDenied) {
                    try await rpc.requestPermission(reboundPrompt)
                }

                var openRequest = makeOpenRequest()
                openRequest.authorization = try fixture.authorization(
                    callID: openRequest.identity.toolCallID,
                    arguments: [
                        "operation": "open_session",
                        "allowed_targets": openRequest.allowedTargets.map(targetPayload),
                    ],
                    approvalGrantDigest: openRequest.idempotencyKey
                )
                var forgedOpen = openRequest
                forgedOpen.allowedTargets[0].windowTitle = "Forged Window"
                await expectRPCError(.permissionDenied) {
                    try await rpc.openSession(forgedOpen)
                }
                let lease = try await rpc.openSession(openRequest)
                #expect(!lease.identity.sessionID.isEmpty)
                #expect(!lease.sessionCapability.isEmpty)
                #expect(lease.allowedTargets == openRequest.allowedTargets)

                let replayedLease = try await rpc.openSession(openRequest)
                #expect(replayedLease.identity.sessionID == lease.identity.sessionID)
                var conflictingOpen = openRequest
                conflictingOpen.artifactRoot = "different-namespace"
                conflictingOpen.authorization = try fixture.authorization(
                    callID: conflictingOpen.identity.toolCallID,
                    arguments: [
                        "operation": "open_session",
                        "allowed_targets": conflictingOpen.allowedTargets.map(
                            targetPayload
                        ),
                    ],
                    approvalGrantDigest: conflictingOpen.idempotencyKey,
                    artifactRoot: conflictingOpen.artifactRoot
                )
                await expectRPCError(.alreadyExists) {
                    try await rpc.openSession(conflictingOpen)
                }

                var capture = Melix_Computer_V1_CaptureFrameRequest()
                capture.identity = lease.identity
                capture.sessionCapability = lease.sessionCapability
                capture.target = try #require(openRequest.allowedTargets.first)
                capture.captureID = "capture-transport-1"
                capture.expectedPreviousGeneration = 0
                capture.deadlineUnixMs = 1_800_000_030_000
                capture.callerVerificationCapability = fixture.verificationCapability
                capture.authorization = try fixture.authorization(
                    callID: "transport-1",
                    arguments: [
                        "operation": "capture_frame",
                        "session_id": lease.identity.sessionID,
                        "target": targetPayload(capture.target),
                        "expected_previous_generation": 0,
                    ]
                )
                let frame = try await rpc.captureFrame(capture)
                #expect(frame.frameGeneration == 1)
                #expect(!frame.observationID.isEmpty)
                #expect(!frame.frame.relativePath.hasPrefix("/"))
                #expect(frame.elements.count == 1)
                #expect(frame.elements.first?.handleID == "fixture-button")
                #expect(frame.elements.first?.frameGeneration == frame.frameGeneration)
                #expect(frame.elements.first?.title == "Continue")
                #expect(frame.actualTarget.windowTitle == "Computer Use Fixture")

                let action = try makeActionRequest(
                    lease: lease,
                    target: capture.target,
                    frame: frame,
                    now: fixture.clock.now(),
                    authorization: try fixture.authorization(
                        callID: "action-transport-1",
                        arguments: [
                            "operation": "press_element",
                            "session_id": lease.identity.sessionID,
                            "target": targetPayload(capture.target),
                            "expected_observation_id": frame.observationID,
                            "expected_frame_generation": frame.frameGeneration,
                            "element": [
                                "handle_id": "fixture-button",
                                "title": "Continue",
                                "role": "AXButton",
                            ],
                            "attempt": 1,
                        ],
                        approvalGrantDigest: "approval-transport-1",
                        policyRevision: "policy-transport-v1"
                    )
                )
                let executeTask = Task<[Melix_Computer_V1_ComputerActionEvent], Error> {
                    try await rpc.executeAction(action) { response in
                        var events: [Melix_Computer_V1_ComputerActionEvent] = []
                        for try await event in response.messages {
                            events.append(event)
                        }
                        return events
                    }
                }

                await fixture.accessibility.inspectionStarted.wait()
                var cancellation = Melix_Computer_V1_CancelComputerActionRequest()
                cancellation.identity = lease.identity
                cancellation.sessionCapability = lease.sessionCapability
                cancellation.actionID = action.actionID
                cancellation.attempt = action.attempt
                cancellation.cancellationID = "cancel-transport-1"
                cancellation.callerVerificationCapability =
                    fixture.verificationCapability
                cancellation.authorization = try fixture.authorization(
                    callID: action.actionID,
                    arguments: ["operation": "press_element"],
                    approvalGrantDigest: action.idempotencyKey,
                    policyRevision: action.approval.policyHash
                )
                let cancellationReceipt = try await rpc.cancelAction(cancellation)
                #expect(cancellationReceipt.disposition == .computerCancellationAccepted)
                #expect(!cancellationReceipt.sideEffectCommitted)
                await fixture.inspectionRelease.signal()

                let events = try await executeTask.value
                #expect(events.first?.phase == .computerActionQueued)
                #expect(events.last?.phase == .computerActionCancelled)
                #expect(events.allSatisfy { $0.actionID == action.actionID })
                #expect(await fixture.accessibility.pressCount() == 0)

                let replayedCancellation = try await rpc.cancelAction(cancellation)
                #expect(replayedCancellation.disposition == .computerCancellationAccepted)

                var sessionCancellation = Melix_Computer_V1_CancelComputerSessionRequest()
                sessionCancellation.identity = lease.identity
                sessionCancellation.sessionCapability = lease.sessionCapability
                sessionCancellation.cancellationID = "cancel-session-transport-1"
                sessionCancellation.reason = "operator stopped the run"
                sessionCancellation.callerVerificationCapability =
                    fixture.verificationCapability
                sessionCancellation.authorization = openRequest.authorization
                let sessionCancellationReceipt = try await rpc.cancelSession(
                    sessionCancellation
                )
                #expect(
                    sessionCancellationReceipt.disposition
                        == .computerSessionCancellationAccepted
                )
                #expect(sessionCancellationReceipt.sessionID == lease.identity.sessionID)
                let repeatedSessionCancellation = try await rpc.cancelSession(
                    sessionCancellation
                )
                #expect(
                    repeatedSessionCancellation.disposition
                        == .computerSessionCancellationAccepted
                )

                var close = Melix_Computer_V1_CloseComputerSessionRequest()
                close.identity = lease.identity
                close.sessionCapability = lease.sessionCapability
                close.reason = "contract_complete"
                close.closeID = "close-tool-close-transport-1"
                close.callerVerificationCapability = fixture.verificationCapability
                close.authorization = try fixture.authorization(
                    callID: "tool-close-transport-1",
                    arguments: [
                        "operation": "close_session",
                        "session_id": lease.identity.sessionID,
                        "reason": close.reason,
                    ]
                )
                let closeReceipt = try await rpc.closeSession(close)
                #expect(closeReceipt.closed)
                #expect(closeReceipt.sessionID == lease.identity.sessionID)
            }
        } catch {
            await fixture.inspectionRelease.signal()
            await fixture.stop()
            fixture.removeFiles()
            throw error
        }
        await fixture.stop()
        fixture.removeFiles()
    }

    @Test("aged authorization is cleanup-only through the real private UDS")
    func agedAuthorizationOnlyCancelsSessionOverRealUDS() async throws {
        let fixture = try await LiveComputerBrokerFixture.start()
        do {
            let transport = try HTTP2ClientTransport.Posix(
                target: .unixDomainSocket(path: fixture.socketPath),
                transportSecurity: .plaintext
            )
            try await withGRPCClient(transport: transport) { client in
                let rpc = Melix_Computer_V1_ComputerUseBrokerService.Client(
                    wrapping: client
                )
                _ = try await rpc.handshake(
                    makeHandshake(capability: fixture.verificationCapability)
                )
                let open = try authorizeOpen(
                    makeOpenRequest(),
                    fixture: fixture
                )
                let lease = try await rpc.openSession(open)
                let target = try #require(open.allowedTargets.first)
                var capture = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "aged-capture"
                )
                capture = try authorizeCapture(
                    capture,
                    callID: "aged-capture",
                    fixture: fixture
                )

                fixture.clock.advance(by: 959)

                await expectRPCError(.permissionDenied) {
                    try await rpc.captureFrame(capture)
                }

                var cancellation =
                    Melix_Computer_V1_CancelComputerSessionRequest()
                cancellation.identity = lease.identity
                cancellation.sessionCapability = lease.sessionCapability
                cancellation.cancellationID = "cancel-session-aged-session"
                cancellation.reason = "operator stopped the aged run"
                cancellation.callerVerificationCapability =
                    fixture.verificationCapability
                cancellation.authorization = open.authorization
                let receipt = try await rpc.cancelSession(cancellation)
                #expect(
                    receipt.disposition
                        == .computerSessionCancellationAccepted
                )
            }
        } catch {
            await fixture.stop()
            fixture.removeFiles()
            throw error
        }
        await fixture.stop()
        fixture.removeFiles()
    }

    @Test("completed semantic action maps bounded result and evidence artifacts")
    func completedSemanticActionMapsEvidence() async throws {
        let fixture = try await LiveComputerBrokerFixture.start()
        do {
            let transport = try HTTP2ClientTransport.Posix(
                target: .unixDomainSocket(path: fixture.socketPath),
                transportSecurity: .plaintext
            )
            try await withGRPCClient(transport: transport) { client in
                let rpc = Melix_Computer_V1_ComputerUseBrokerService.Client(
                    wrapping: client
                )
                _ = try await rpc.handshake(
                    makeHandshake(capability: fixture.verificationCapability)
                )
                var open = makeOpenRequest()
                open.authorization = try fixture.authorization(
                    callID: open.identity.toolCallID,
                    arguments: [
                        "operation": "open_session",
                        "allowed_targets": open.allowedTargets.map(targetPayload),
                    ],
                    approvalGrantDigest: open.idempotencyKey
                )
                let lease = try await rpc.openSession(open)
                var capture = Melix_Computer_V1_CaptureFrameRequest()
                capture.identity = lease.identity
                capture.sessionCapability = lease.sessionCapability
                capture.target = try #require(open.allowedTargets.first)
                capture.captureID = "capture-success-transport"
                capture.deadlineUnixMs = Int64(
                    fixture.clock.now().addingTimeInterval(30)
                        .timeIntervalSince1970 * 1_000
                )
                capture.callerVerificationCapability = fixture.verificationCapability
                capture.authorization = try fixture.authorization(
                    callID: "success-transport",
                    arguments: [
                        "operation": "capture_frame",
                        "session_id": lease.identity.sessionID,
                        "target": targetPayload(capture.target),
                        "expected_previous_generation": 0,
                    ]
                )
                let frame = try await rpc.captureFrame(capture)
                let action = try makeActionRequest(
                    lease: lease,
                    target: capture.target,
                    frame: frame,
                    now: fixture.clock.now(),
                    authorization: try fixture.authorization(
                        callID: "action-transport-1",
                        arguments: [
                            "operation": "press_element",
                            "session_id": lease.identity.sessionID,
                            "target": targetPayload(capture.target),
                            "expected_observation_id": frame.observationID,
                            "expected_frame_generation": frame.frameGeneration,
                            "element": [
                                "handle_id": "fixture-button",
                                "title": "Continue",
                                "role": "AXButton",
                            ],
                            "attempt": 1,
                        ],
                        approvalGrantDigest: "approval-transport-1",
                        policyRevision: "policy-transport-v1"
                    )
                )
                await fixture.inspectionRelease.signal()
                let events = try await rpc.executeAction(action) { response in
                    var events: [Melix_Computer_V1_ComputerActionEvent] = []
                    for try await event in response.messages {
                        events.append(event)
                    }
                    return events
                }
                let result = try #require(events.last?.result)
                #expect(events.last?.phase == .computerActionCompleted)
                #expect(result.status == "completed")
                #expect(result.actionMode == "ax_semantic_press")
                #expect(result.artifacts.count == 3)
                #expect(result.artifacts.allSatisfy { !$0.relativePath.hasPrefix("/") })
                #expect(!result.evidenceReceiptJson.isEmpty)
                #expect(await fixture.accessibility.pressCount() == 1)
            }
        } catch {
            await fixture.inspectionRelease.signal()
            await fixture.stop()
            fixture.removeFiles()
            throw error
        }
        await fixture.stop()
        fixture.removeFiles()
    }

    @Test("capture generation reservation serializes concurrent requests and rolls back failures")
    func captureGenerationReservationIsAtomic() async throws {
        let captureRelease = TestLatch()
        let blockedFrames = FakeFrameCaptureAdapter(captureRelease: captureRelease)
        let fixture = try await LiveComputerBrokerFixture.start(
            frameCapture: blockedFrames
        )
        do {
            let transport = try HTTP2ClientTransport.Posix(
                target: .unixDomainSocket(path: fixture.socketPath),
                transportSecurity: .plaintext
            )
            try await withGRPCClient(transport: transport) { client in
                let rpc = Melix_Computer_V1_ComputerUseBrokerService.Client(
                    wrapping: client
                )
                _ = try await rpc.handshake(
                    makeHandshake(capability: fixture.verificationCapability)
                )
                let open = try authorizeOpen(makeOpenRequest(), fixture: fixture)
                let lease = try await rpc.openSession(open)
                let target = try #require(open.allowedTargets.first)
                var first = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "reservation-first"
                )
                first = try authorizeCapture(
                    first,
                    callID: "reservation-first",
                    fixture: fixture
                )
                var concurrent = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "reservation-concurrent"
                )
                concurrent = try authorizeCapture(
                    concurrent,
                    callID: "reservation-concurrent",
                    fixture: fixture
                )

                let firstTask = Task {
                    try await rpc.captureFrame(first)
                }
                await blockedFrames.captureStarted.wait()
                let concurrentTask = Task {
                    try await rpc.captureFrame(concurrent)
                }
                try await Task.sleep(for: .milliseconds(50))
                #expect(await blockedFrames.captureCount() == 1)
                await captureRelease.signal()

                let firstFrame = try await firstTask.value
                #expect(firstFrame.frameGeneration == 1)
                do {
                    _ = try await concurrentTask.value
                    Issue.record("Expected the concurrent generation reservation to fail")
                } catch let error as RPCError {
                    #expect(error.code == .failedPrecondition)
                }
            }
        } catch {
            await captureRelease.signal()
            await fixture.stop()
            fixture.removeFiles()
            throw error
        }
        await fixture.stop()
        fixture.removeFiles()

        let failingFrames = FakeFrameCaptureAdapter(failOnCaptureNumber: 1)
        let rollbackFixture = try await LiveComputerBrokerFixture.start(
            frameCapture: failingFrames
        )
        do {
            let transport = try HTTP2ClientTransport.Posix(
                target: .unixDomainSocket(path: rollbackFixture.socketPath),
                transportSecurity: .plaintext
            )
            try await withGRPCClient(transport: transport) { client in
                let rpc = Melix_Computer_V1_ComputerUseBrokerService.Client(
                    wrapping: client
                )
                _ = try await rpc.handshake(
                    makeHandshake(capability: rollbackFixture.verificationCapability)
                )
                let open = try authorizeOpen(
                    makeOpenRequest(),
                    fixture: rollbackFixture
                )
                let lease = try await rpc.openSession(open)
                let target = try #require(open.allowedTargets.first)
                var failed = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "reservation-failure"
                )
                failed = try authorizeCapture(
                    failed,
                    callID: "reservation-failure",
                    fixture: rollbackFixture
                )
                await expectRPCError(.unavailable) {
                    try await rpc.captureFrame(failed)
                }

                var retry = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "reservation-retry"
                )
                retry = try authorizeCapture(
                    retry,
                    callID: "reservation-retry",
                    fixture: rollbackFixture
                )
                let retriedFrame = try await rpc.captureFrame(retry)
                #expect(retriedFrame.frameGeneration == 2)
                #expect(await failingFrames.captureCount() == 2)
            }
        } catch {
            await rollbackFixture.stop()
            rollbackFixture.removeFiles()
            throw error
        }
        await rollbackFixture.stop()
        rollbackFixture.removeFiles()
    }

    @Test("authenticated transport rejects invalid bindings and lifecycle transitions")
    func authenticatedTransportBoundaryMatrix() async throws {
        let fixture = try await LiveComputerBrokerFixture.start()
        do {
            let transport = try HTTP2ClientTransport.Posix(
                target: .unixDomainSocket(path: fixture.socketPath),
                transportSecurity: .plaintext
            )
            try await withGRPCClient(transport: transport) { client in
                let rpc = Melix_Computer_V1_ComputerUseBrokerService.Client(
                    wrapping: client
                )
                _ = try await rpc.handshake(
                    makeHandshake(capability: fixture.verificationCapability)
                )

                var wrongOperation = Melix_Computer_V1_GetPermissionsRequest()
                wrongOperation.callerVerificationCapability =
                    fixture.verificationCapability
                wrongOperation.authorization = try fixture.authorization(
                    callID: "permissions-wrong-operation",
                    arguments: ["operation": "open_session"]
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.getPermissions(wrongOperation)
                }

                var preselected = makeOpenRequest()
                preselected.identity.sessionID = "caller-selected-session"
                preselected = try authorizeOpen(preselected, fixture: fixture)
                await expectRPCError(.invalidArgument) {
                    try await rpc.openSession(preselected)
                }

                var oversizedIdentity = makeOpenRequest()
                oversizedIdentity.identity.actorID = String(repeating: "a", count: 257)
                oversizedIdentity = try authorizeOpen(
                    oversizedIdentity,
                    fixture: fixture
                )
                await expectRPCError(.invalidArgument) {
                    try await rpc.openSession(oversizedIdentity)
                }

                var missingTargets = makeOpenRequest()
                missingTargets.allowedTargets = []
                missingTargets = try authorizeOpen(missingTargets, fixture: fixture)
                await expectRPCError(.invalidArgument) {
                    try await rpc.openSession(missingTargets)
                }

                var multipleTargets = makeOpenRequest()
                var secondTarget = multipleTargets.allowedTargets[0]
                secondTarget.bundleID = "io.melix.fixture.secondary"
                secondTarget.processID = 4343
                secondTarget.processLaunchIdentity = "fixture-launch-transport-2"
                secondTarget.windowID = 78
                secondTarget.windowTitle = "Computer Use Secondary Fixture"
                multipleTargets.allowedTargets.append(secondTarget)
                multipleTargets = try authorizeOpen(
                    multipleTargets,
                    fixture: fixture
                )
                await expectRPCError(.invalidArgument) {
                    try await rpc.openSession(multipleTargets)
                }

                var malformedAuthorizedTarget = makeOpenRequest()
                malformedAuthorizedTarget.authorization = try fixture.authorization(
                    callID: malformedAuthorizedTarget.identity.toolCallID,
                    arguments: [
                        "operation": "open_session",
                        "allowed_targets": [["bundle_id": "io.melix.fixture"]],
                    ],
                    approvalGrantDigest: malformedAuthorizedTarget.idempotencyKey
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.openSession(malformedAuthorizedTarget)
                }

                var mismatchedOpenBinding = makeOpenRequest()
                mismatchedOpenBinding.authorization = try fixture.authorization(
                    callID: mismatchedOpenBinding.identity.toolCallID,
                    arguments: [
                        "operation": "open_session",
                        "allowed_targets": [],
                    ],
                    approvalGrantDigest: mismatchedOpenBinding.idempotencyKey
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.openSession(mismatchedOpenBinding)
                }

                var invalidTarget = makeOpenRequest()
                invalidTarget.allowedTargets[0].processID = 0
                invalidTarget = try authorizeOpen(invalidTarget, fixture: fixture)
                await expectRPCError(.invalidArgument) {
                    try await rpc.openSession(invalidTarget)
                }

                var invalidFrames = makeOpenRequest()
                invalidFrames.limits.maximumFrames = 0
                invalidFrames = try authorizeOpen(invalidFrames, fixture: fixture)
                await expectRPCError(.invalidArgument) {
                    try await rpc.openSession(invalidFrames)
                }

                var invalidArtifacts = makeOpenRequest()
                invalidArtifacts.limits.maximumArtifactBytes = 0
                invalidArtifacts = try authorizeOpen(invalidArtifacts, fixture: fixture)
                await expectRPCError(.invalidArgument) {
                    try await rpc.openSession(invalidArtifacts)
                }

                var invalidIdle = makeOpenRequest()
                invalidIdle.limits.idleDeadlineUnixMs = 1_800_000_000_500
                invalidIdle = try authorizeOpen(invalidIdle, fixture: fixture)
                await expectRPCError(.invalidArgument) {
                    try await rpc.openSession(invalidIdle)
                }

                var invalidAbsolute = makeOpenRequest()
                invalidAbsolute.limits.absoluteDeadlineUnixMs =
                    invalidAbsolute.limits.idleDeadlineUnixMs - 1
                invalidAbsolute = try authorizeOpen(
                    invalidAbsolute,
                    fixture: fixture
                )
                await expectRPCError(.invalidArgument) {
                    try await rpc.openSession(invalidAbsolute)
                }

                var open = makeOpenRequest()
                open.limits.maximumFrames = 2
                open.limits.maximumActions = 1
                open = try authorizeOpen(open, fixture: fixture)
                let lease = try await rpc.openSession(open)
                let target = try #require(open.allowedTargets.first)

                var missingSession = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "missing-session"
                )
                missingSession.identity.sessionID = "missing-session"
                missingSession = try authorizeCapture(
                    missingSession,
                    callID: "missing-session",
                    fixture: fixture
                )
                await expectRPCError(.notFound) {
                    try await rpc.captureFrame(missingSession)
                }

                var wrongIdentity = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "wrong-identity"
                )
                wrongIdentity.identity.actorID = "different-operator"
                wrongIdentity = try authorizeCapture(
                    wrongIdentity,
                    callID: "wrong-identity",
                    fixture: fixture
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.captureFrame(wrongIdentity)
                }

                var authorizationIdentityMismatch = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "authorization-identity-mismatch"
                )
                authorizationIdentityMismatch.identity.actorID = "different-operator"
                authorizationIdentityMismatch.authorization = try fixture.authorization(
                    callID: "authorization-identity-mismatch",
                    arguments: [
                        "operation": "capture_frame",
                        "session_id": lease.identity.sessionID,
                        "target": targetPayload(target),
                        "expected_previous_generation": 0,
                    ]
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.captureFrame(authorizationIdentityMismatch)
                }

                var captureBindingMismatch = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "capture-binding-mismatch"
                )
                captureBindingMismatch = try authorizeCapture(
                    captureBindingMismatch,
                    callID: "capture-binding-mismatch",
                    fixture: fixture
                )
                captureBindingMismatch.captureID = "different-capture-id"
                await expectRPCError(.permissionDenied) {
                    try await rpc.captureFrame(captureBindingMismatch)
                }

                var previousGenerationMismatch = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "previous-generation-mismatch"
                )
                previousGenerationMismatch = try authorizeCapture(
                    previousGenerationMismatch,
                    callID: "previous-generation-mismatch",
                    fixture: fixture
                )
                previousGenerationMismatch.expectedPreviousGeneration = 1
                await expectRPCError(.permissionDenied) {
                    try await rpc.captureFrame(previousGenerationMismatch)
                }

                var outsideTarget = target
                outsideTarget.bundleID = "io.melix.fixture.secondary"
                outsideTarget.processID = 4343
                outsideTarget.processLaunchIdentity =
                    "fixture-launch-transport-2"
                outsideTarget.windowID = 999
                outsideTarget.windowTitle = "Not Allowed"
                var outsideCapture = makeCaptureRequest(
                    lease: lease,
                    target: outsideTarget,
                    callID: "outside-target"
                )
                outsideCapture = try authorizeCapture(
                    outsideCapture,
                    callID: "outside-target",
                    fixture: fixture
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.captureFrame(outsideCapture)
                }

                var staleCapture = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "stale-capture",
                    expectedPreviousGeneration: 1
                )
                staleCapture = try authorizeCapture(
                    staleCapture,
                    callID: "stale-capture",
                    fixture: fixture
                )
                await expectRPCError(.failedPrecondition) {
                    try await rpc.captureFrame(staleCapture)
                }

                var invalidDeadline = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "invalid-deadline"
                )
                invalidDeadline.deadlineUnixMs = -1
                invalidDeadline = try authorizeCapture(
                    invalidDeadline,
                    callID: "invalid-deadline",
                    fixture: fixture
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.captureFrame(invalidDeadline)
                }

                var expiredDeadline = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "expired-deadline"
                )
                expiredDeadline.deadlineUnixMs = 1
                expiredDeadline = try authorizeCapture(
                    expiredDeadline,
                    callID: "expired-deadline",
                    fixture: fixture
                )
                await expectRPCError(.invalidArgument) {
                    try await rpc.captureFrame(expiredDeadline)
                }

                var unauthorizedDeadline = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "unauthorized-deadline"
                )
                unauthorizedDeadline.deadlineUnixMs = 1_800_000_061_000
                unauthorizedDeadline = try authorizeCapture(
                    unauthorizedDeadline,
                    callID: "unauthorized-deadline",
                    fixture: fixture
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.captureFrame(unauthorizedDeadline)
                }

                var invalidCapability = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "invalid-capability"
                )
                invalidCapability.sessionCapability = Data([0xFF])
                invalidCapability = try authorizeCapture(
                    invalidCapability,
                    callID: "invalid-capability",
                    fixture: fixture
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.captureFrame(invalidCapability)
                }

                var wrongCapability = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "wrong-capability"
                )
                wrongCapability.sessionCapability = Data("wrong-capability".utf8)
                wrongCapability = try authorizeCapture(
                    wrongCapability,
                    callID: "wrong-capability",
                    fixture: fixture
                )
                await expectRPCError(.unauthenticated) {
                    try await rpc.captureFrame(wrongCapability)
                }

                var capture = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "boundary-success"
                )
                capture.deadlineUnixMs = 1_800_000_030_000
                capture = try authorizeCapture(
                    capture,
                    callID: "boundary-success",
                    fixture: fixture
                )
                let frame = try await rpc.captureFrame(capture)

                let placeholderAuthorization = try fixture.authorization(
                    callID: "action-transport-1",
                    arguments: ["operation": "press_element"],
                    approvalGrantDigest: "approval-transport-1",
                    policyRevision: "policy-transport-v1"
                )
                let baseAction = try makeActionRequest(
                    lease: lease,
                    target: target,
                    frame: frame,
                    now: fixture.clock.now(),
                    authorization: placeholderAuthorization
                )

                var zeroAttempt = baseAction
                zeroAttempt.attempt = 0
                zeroAttempt = try authorizeAction(zeroAttempt, fixture: fixture)
                await expectExecuteError(.invalidArgument, rpc: rpc, request: zeroAttempt)

                var blankScope = baseAction
                blankScope.approval.scope = " "
                blankScope = try authorizeAction(blankScope, fixture: fixture)
                await expectExecuteError(.permissionDenied, rpc: rpc, request: blankScope)

                var disabledElement = baseAction
                disabledElement.pressElement.element.enabled = false
                disabledElement = try authorizeAction(
                    disabledElement,
                    fixture: fixture
                )
                await expectExecuteError(
                    .permissionDenied,
                    rpc: rpc,
                    request: disabledElement
                )

                var unnamedElement = baseAction
                unnamedElement.pressElement.element.handleID = ""
                unnamedElement.pressElement.element.title = ""
                unnamedElement = try authorizeAction(
                    unnamedElement,
                    fixture: fixture
                )
                await expectExecuteError(.invalidArgument, rpc: rpc, request: unnamedElement)

                for field in ["handle_id", "title", "role"] {
                    var mismatchedArguments = actionArguments(baseAction)
                    var element = try #require(
                        mismatchedArguments["element"] as? [String: Any]
                    )
                    element[field] = "mismatch"
                    mismatchedArguments["element"] = element
                    let mismatched = try authorizeAction(
                        baseAction,
                        fixture: fixture,
                        arguments: mismatchedArguments
                    )
                    await expectExecuteError(
                        .permissionDenied,
                        rpc: rpc,
                        request: mismatched
                    )
                }

                var wrongActionAttempt = baseAction
                var wrongAttemptArguments = actionArguments(wrongActionAttempt)
                wrongAttemptArguments["attempt"] = 2
                wrongActionAttempt = try authorizeAction(
                    wrongActionAttempt,
                    fixture: fixture,
                    arguments: wrongAttemptArguments
                )
                await expectExecuteError(
                    .permissionDenied,
                    rpc: rpc,
                    request: wrongActionAttempt
                )

                var wrongActionCall = try authorizeAction(
                    baseAction,
                    fixture: fixture,
                    callID: "different-action"
                )
                wrongActionCall.actionID = baseAction.actionID
                await expectExecuteError(
                    .permissionDenied,
                    rpc: rpc,
                    request: wrongActionCall
                )

                var invalidActionTarget = baseAction
                invalidActionTarget.target.processID = 0
                invalidActionTarget = try authorizeAction(
                    invalidActionTarget,
                    fixture: fixture
                )
                await expectExecuteError(
                    .invalidArgument,
                    rpc: rpc,
                    request: invalidActionTarget
                )

                var outsideAction = baseAction
                outsideAction.target = outsideTarget
                outsideAction = try authorizeAction(outsideAction, fixture: fixture)
                await expectExecuteError(
                    .permissionDenied,
                    rpc: rpc,
                    request: outsideAction
                )

                var expiredAction = baseAction
                expiredAction.deadlineUnixMs = 1
                expiredAction = try authorizeAction(expiredAction, fixture: fixture)
                await expectExecuteError(
                    .invalidArgument,
                    rpc: rpc,
                    request: expiredAction
                )

                var wrongActionCapability = baseAction
                wrongActionCapability.sessionCapability = Data("wrong-capability".utf8)
                wrongActionCapability = try authorizeAction(
                    wrongActionCapability,
                    fixture: fixture
                )
                await expectExecuteError(
                    .unauthenticated,
                    rpc: rpc,
                    request: wrongActionCapability
                )

                let action = try authorizeAction(baseAction, fixture: fixture)
                await fixture.inspectionRelease.signal()
                let completed = try await rpc.executeAction(action) { response in
                    var events: [Melix_Computer_V1_ComputerActionEvent] = []
                    for try await event in response.messages {
                        events.append(event)
                    }
                    return events
                }
                #expect(completed.last?.phase == .computerActionCompleted)

                var overBudgetCapture = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "over-frame-budget",
                    expectedPreviousGeneration: frame.frameGeneration
                )
                overBudgetCapture = try authorizeCapture(
                    overBudgetCapture,
                    callID: "over-frame-budget",
                    fixture: fixture
                )
                await expectRPCError(.resourceExhausted) {
                    try await rpc.captureFrame(overBudgetCapture)
                }

                var conflictingAttempt = action
                conflictingAttempt.attempt = 2
                conflictingAttempt = try authorizeAction(
                    conflictingAttempt,
                    fixture: fixture
                )
                await expectExecuteError(
                    .alreadyExists,
                    rpc: rpc,
                    request: conflictingAttempt
                )

                var unknownCancellation = makeCancelActionRequest(
                    lease: lease,
                    actionID: "unknown-action",
                    attempt: 1,
                    cancellationID: "cancel-unknown-action"
                )
                unknownCancellation.authorization = try fixture.authorization(
                    callID: unknownCancellation.actionID,
                    arguments: ["operation": "press_element"]
                )
                let unknownReceipt = try await rpc.cancelAction(unknownCancellation)
                #expect(
                    unknownReceipt.disposition == .computerCancellationNotFound
                )

                var invalidNamespace = makeCancelActionRequest(
                    lease: lease,
                    actionID: action.actionID,
                    attempt: action.attempt,
                    cancellationID: "invalid-namespace"
                )
                invalidNamespace.authorization = try fixture.authorization(
                    callID: invalidNamespace.actionID,
                    arguments: ["operation": "press_element"]
                )
                await expectRPCError(.invalidArgument) {
                    try await rpc.cancelAction(invalidNamespace)
                }

                var zeroCancellationAttempt = invalidNamespace
                zeroCancellationAttempt.cancellationID = "cancel-zero-attempt"
                zeroCancellationAttempt.attempt = 0
                await expectRPCError(.invalidArgument) {
                    try await rpc.cancelAction(zeroCancellationAttempt)
                }

                var wrongCancellationAttempt = invalidNamespace
                wrongCancellationAttempt.cancellationID = "cancel-wrong-attempt"
                wrongCancellationAttempt.attempt = 2
                await expectRPCError(.permissionDenied) {
                    try await rpc.cancelAction(wrongCancellationAttempt)
                }

                var completedCancellation = invalidNamespace
                completedCancellation.cancellationID = "cancel-completed-action"
                let completedReceipt = try await rpc.cancelAction(
                    completedCancellation
                )
                #expect(
                    completedReceipt.disposition
                        == .computerCancellationAlreadyTerminal
                )

                var invalidSessionCancellation =
                    Melix_Computer_V1_CancelComputerSessionRequest()
                invalidSessionCancellation.identity = lease.identity
                invalidSessionCancellation.sessionCapability = lease.sessionCapability
                invalidSessionCancellation.cancellationID = "cancel-session-invalid"
                invalidSessionCancellation.reason = " "
                invalidSessionCancellation.callerVerificationCapability =
                    fixture.verificationCapability
                invalidSessionCancellation.authorization = open.authorization
                await expectRPCError(.invalidArgument) {
                    try await rpc.cancelSession(invalidSessionCancellation)
                }

                var wrongSessionOperation = invalidSessionCancellation
                wrongSessionOperation.reason = "operator requested cancellation"
                wrongSessionOperation.authorization = try fixture.authorization(
                    callID: "cancel-session-wrong-operation",
                    arguments: ["operation": "delete_session"]
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.cancelSession(wrongSessionOperation)
                }

                var wrongAuthorizedSession = invalidSessionCancellation
                wrongAuthorizedSession.reason = "operator requested cancellation"
                wrongAuthorizedSession.authorization = try fixture.authorization(
                    callID: "cancel-session-wrong-session",
                    arguments: [
                        "operation": "capture_frame",
                        "session_id": "different-session",
                    ]
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.cancelSession(wrongAuthorizedSession)
                }

                var close = Melix_Computer_V1_CloseComputerSessionRequest()
                close.identity = lease.identity
                close.sessionCapability = lease.sessionCapability
                close.reason = "boundary_complete"
                close.closeID = "wrong-close-id"
                close.callerVerificationCapability = fixture.verificationCapability
                close.authorization = try fixture.authorization(
                    callID: "boundary-close",
                    arguments: [
                        "operation": "close_session",
                        "session_id": lease.identity.sessionID,
                        "reason": close.reason,
                    ]
                )
                await expectRPCError(.permissionDenied) {
                    try await rpc.closeSession(close)
                }

                close.closeID = "close-boundary-close"
                close.reason = "different-reason"
                await expectRPCError(.permissionDenied) {
                    try await rpc.closeSession(close)
                }

                var cancelSession = invalidSessionCancellation
                cancelSession.reason = "operator requested cancellation"
                let cancelReceipt = try await rpc.cancelSession(cancelSession)
                #expect(
                    cancelReceipt.disposition
                        == .computerSessionCancellationAccepted
                )

                var closedCapture = makeCaptureRequest(
                    lease: lease,
                    target: target,
                    callID: "closed-session",
                    expectedPreviousGeneration: frame.frameGeneration
                )
                closedCapture = try authorizeCapture(
                    closedCapture,
                    callID: "closed-session",
                    fixture: fixture
                )
                await expectRPCError(.failedPrecondition) {
                    try await rpc.captureFrame(closedCapture)
                }

                var closedAction = baseAction
                closedAction.actionID = "action-closed-session"
                closedAction.idempotencyKey = "approval-closed-session"
                closedAction.approval.approvalID = "approval-closed-session"
                closedAction = try authorizeAction(closedAction, fixture: fixture)
                await expectExecuteError(
                    .failedPrecondition,
                    rpc: rpc,
                    request: closedAction
                )
            }
        } catch {
            await fixture.inspectionRelease.signal()
            await fixture.stop()
            fixture.removeFiles()
            throw error
        }
        await fixture.stop()
        fixture.removeFiles()
    }

    @Test("transport maps adapter and evidence failures to stable RPC codes")
    func transportFailureMapping() async throws {
        let scenarios: [(any FrameCaptureAdapter, RPCError.Code)] = [
            (FakeFrameCaptureAdapter(failOnCaptureNumber: 1), .unavailable),
            (EscapingFrameCaptureAdapter(), .internalError),
        ]
        for (frameCapture, expectedCode) in scenarios {
            let fixture = try await LiveComputerBrokerFixture.start(
                frameCapture: frameCapture
            )
            do {
                let transport = try HTTP2ClientTransport.Posix(
                    target: .unixDomainSocket(path: fixture.socketPath),
                    transportSecurity: .plaintext
                )
                try await withGRPCClient(transport: transport) { client in
                    let rpc = Melix_Computer_V1_ComputerUseBrokerService.Client(
                        wrapping: client
                    )
                    _ = try await rpc.handshake(
                        makeHandshake(capability: fixture.verificationCapability)
                    )
                    var open = try authorizeOpen(
                        makeOpenRequest(),
                        fixture: fixture
                    )
                    open.idempotencyKey += "-\(expectedCode)"
                    open.identity.requestID = open.idempotencyKey
                    open.identity.toolCallID = open.idempotencyKey
                    open = try authorizeOpen(open, fixture: fixture)
                    let lease = try await rpc.openSession(open)
                    let target = try #require(open.allowedTargets.first)
                    var capture = makeCaptureRequest(
                        lease: lease,
                        target: target,
                        callID: "failure-\(expectedCode)"
                    )
                    capture = try authorizeCapture(
                        capture,
                        callID: "failure-\(expectedCode)",
                        fixture: fixture
                    )
                    await expectRPCError(expectedCode) {
                        try await rpc.captureFrame(capture)
                    }
                }
            } catch {
                await fixture.stop()
                fixture.removeFiles()
                throw error
            }
            await fixture.stop()
            fixture.removeFiles()
        }
    }

    @Test("UDS lifecycle rejects live contention, preserves replacements, and recovers stale sockets")
    func secureUnixDomainSocketLifecycle() async throws {
        let notStartedFixture = try LiveComputerBrokerFixture.makeUnstarted()
        await expectSecureSocketError {
            try await notStartedFixture.waitForTermination()
        }
        await notStartedFixture.stop()
        notStartedFixture.removeFiles()

        let liveFixture = try await LiveComputerBrokerFixture.start()
        do {
            await expectSecureSocketError {
                try await liveFixture.startAgain()
            }
            let originalIdentity = try testSocketIdentity(at: liveFixture.socketPath)
            let competitor = try liveFixture.competingServer()
            await expectSecureSocketError {
                try await competitor.start()
            }
            #expect(try testSocketIdentity(at: liveFixture.socketPath) == originalIdentity)
            await competitor.stop()
        } catch {
            await liveFixture.stop()
            liveFixture.removeFiles()
            throw error
        }
        await liveFixture.stop()
        liveFixture.removeFiles()

        let externallyLiveFixture = try LiveComputerBrokerFixture.makeUnstarted()
        var externallyLiveDescriptor: Int32 = -1
        do {
            let parent = URL(fileURLWithPath: externallyLiveFixture.socketPath)
                .deletingLastPathComponent()
            try FileManager.default.createDirectory(
                at: parent,
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: NSNumber(value: 0o700)]
            )
            externallyLiveDescriptor = try bindTestUnixSocket(
                at: externallyLiveFixture.socketPath,
                listening: true
            )
            let externallyLiveIdentity = try testSocketIdentity(
                at: externallyLiveFixture.socketPath
            )

            await expectSecureSocketError {
                try await externallyLiveFixture.startAgain()
            }
            #expect(
                try testSocketIdentity(at: externallyLiveFixture.socketPath)
                    == externallyLiveIdentity
            )
        } catch {
            if externallyLiveDescriptor >= 0 {
                _ = Darwin.close(externallyLiveDescriptor)
            }
            _ = Darwin.unlink(externallyLiveFixture.socketPath)
            await externallyLiveFixture.stop()
            externallyLiveFixture.removeFiles()
            throw error
        }
        if externallyLiveDescriptor >= 0 {
            _ = Darwin.close(externallyLiveDescriptor)
        }
        _ = Darwin.unlink(externallyLiveFixture.socketPath)
        await externallyLiveFixture.stop()
        externallyLiveFixture.removeFiles()

        let replacementFixture = try await LiveComputerBrokerFixture.start()
        var replacementDescriptor: Int32 = -1
        do {
            #expect(Darwin.unlink(replacementFixture.socketPath) == 0)
            replacementDescriptor = try bindTestUnixSocket(
                at: replacementFixture.socketPath,
                listening: true
            )
            let replacementIdentity = try testSocketIdentity(
                at: replacementFixture.socketPath
            )

            await replacementFixture.stop()

            #expect(FileManager.default.fileExists(atPath: replacementFixture.socketPath))
            #expect(
                try testSocketIdentity(at: replacementFixture.socketPath)
                    == replacementIdentity
            )
        } catch {
            if replacementDescriptor >= 0 { _ = Darwin.close(replacementDescriptor) }
            _ = Darwin.unlink(replacementFixture.socketPath)
            await replacementFixture.stop()
            replacementFixture.removeFiles()
            throw error
        }
        if replacementDescriptor >= 0 { _ = Darwin.close(replacementDescriptor) }
        _ = Darwin.unlink(replacementFixture.socketPath)
        replacementFixture.removeFiles()

        let stagingFailureFixture = try await LiveComputerBrokerFixture.start()
        let stagingFailureParent = URL(fileURLWithPath: stagingFailureFixture.socketPath)
            .deletingLastPathComponent().path
        var stagingFailureDescriptor: Int32 = -1
        do {
            #expect(Darwin.unlink(stagingFailureFixture.socketPath) == 0)
            stagingFailureDescriptor = try bindTestUnixSocket(
                at: stagingFailureFixture.socketPath,
                listening: true
            )
            #expect(Darwin.chmod(stagingFailureParent, 0o500) == 0)

            await stagingFailureFixture.stop()

            #expect(await stagingFailureFixture.isRunning() == false)
        } catch {
            _ = Darwin.chmod(stagingFailureParent, 0o700)
            _ = Darwin.unlink(stagingFailureFixture.socketPath)
            await stagingFailureFixture.stop()
            stagingFailureFixture.removeFiles()
            throw error
        }
        #expect(Darwin.chmod(stagingFailureParent, 0o700) == 0)
        if stagingFailureDescriptor >= 0 {
            _ = Darwin.close(stagingFailureDescriptor)
        }
        _ = Darwin.unlink(stagingFailureFixture.socketPath)
        stagingFailureFixture.removeFiles()

        let staleFixture = try LiveComputerBrokerFixture.makeUnstarted()
        var staleDescriptor: Int32 = -1
        do {
            let parent = URL(fileURLWithPath: staleFixture.socketPath)
                .deletingLastPathComponent()
            try FileManager.default.createDirectory(
                at: parent,
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: NSNumber(value: 0o700)]
            )
            staleDescriptor = try bindTestUnixSocket(
                at: staleFixture.socketPath,
                listening: false
            )
            let staleIdentity = try testSocketIdentity(at: staleFixture.socketPath)
            _ = Darwin.close(staleDescriptor)
            staleDescriptor = -1

            try await staleFixture.startAgain()

            #expect(try testSocketIdentity(at: staleFixture.socketPath) != staleIdentity)
            await staleFixture.stop()
            #expect(!FileManager.default.fileExists(atPath: staleFixture.socketPath))
        } catch {
            if staleDescriptor >= 0 { _ = Darwin.close(staleDescriptor) }
            await staleFixture.stop()
            staleFixture.removeFiles()
            throw error
        }
        staleFixture.removeFiles()

        let waitFixture = try await LiveComputerBrokerFixture.start()
        do {
            let waiter = Task { try await waitFixture.waitForTermination() }
            try await Task.sleep(for: .milliseconds(20))
            await waitFixture.stop()
            try await waiter.value
        } catch {
            await waitFixture.stop()
            waitFixture.removeFiles()
            throw error
        }
        waitFixture.removeFiles()
    }

    @Test("socket and capability helpers reject broad or non-private paths")
    func privatePathValidation() throws {
        let root = URL(fileURLWithPath: "/private/tmp", isDirectory: true).appendingPathComponent(
            "mcb-perm-\(UUID().uuidString.prefix(8))",
            isDirectory: true
        )
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o755)]
        )
        let socket = try SecureUnixDomainSocketPath(
            path: root.appendingPathComponent("broker.sock")
                .standardizedFileURL.path
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try socket.prepareForBinding()
        }

        let capabilityURL = root.appendingPathComponent("capability.bin")
        try Data(repeating: 0xAB, count: 32).write(to: capabilityURL)
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o644)],
            ofItemAtPath: capabilityURL.path
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try PrivateCapabilityFile.read(path: capabilityURL.path)
        }

        for error in [
            SecureUnixDomainSocketError.invalidPath("invalid"),
            .unsafePermissions("permissions"),
            .invalidOwner("owner"),
            .unexpectedFileType("type"),
            .alreadyInUse("in-use"),
            .systemCall("system"),
        ] {
            #expect(error.errorDescription != nil)
        }
        #expect(throws: SecureUnixDomainSocketError.self) {
            try SecureUnixDomainSocketPath(path: "relative.sock")
        }
        #expect(throws: SecureUnixDomainSocketError.self) {
            try SecureUnixDomainSocketPath(path: "/")
        }
        #expect(throws: SecureUnixDomainSocketError.self) {
            try SecureUnixDomainSocketPath(path: "/private/tmp/../tmp/nonstandard.sock")
        }
        #expect(throws: SecureUnixDomainSocketError.self) {
            try SecureUnixDomainSocketPath(
                path: "/private/tmp/\(String(repeating: "x", count: 110)).sock"
            )
        }

        let privateRoot = root.appendingPathComponent("private", isDirectory: true)
        try FileManager.default.createDirectory(
            at: privateRoot,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o700)]
        )
        let lifecyclePath = privateRoot.appendingPathComponent("lifecycle.sock")
        let lifecycle = try SecureUnixDomainSocketPath(
            path: lifecyclePath.standardizedFileURL.path
        )
        let equalLifecycle = try SecureUnixDomainSocketPath(
            path: lifecyclePath.standardizedFileURL.path
        )
        #expect(lifecycle == equalLifecycle)
        try lifecycle.prepareForBinding()
        #expect(throws: SecureUnixDomainSocketError.self) {
            try lifecycle.prepareForBinding()
        }
        try lifecycle.removeOwnedSocket()
        let validCapability = privateRoot.appendingPathComponent("valid.bin")
        let validCapabilityData = Data(repeating: 0xCC, count: 32)
        try validCapabilityData.write(to: validCapability)
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o600)],
            ofItemAtPath: validCapability.path
        )
        #expect(
            try PrivateCapabilityFile.read(
                path: validCapability.standardizedFileURL.path
            ) == validCapabilityData
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try PrivateCapabilityFile.read(
                path: privateRoot.standardizedFileURL.path
            )
        }
        let symlinkCapability = privateRoot.appendingPathComponent("symlink.bin")
        try FileManager.default.createSymbolicLink(
            at: symlinkCapability,
            withDestinationURL: validCapability
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try PrivateCapabilityFile.read(
                path: symlinkCapability.standardizedFileURL.path
            )
        }
        let oversizedCapability = privateRoot.appendingPathComponent("oversized.bin")
        try Data(repeating: 0x02, count: 4_097).write(to: oversizedCapability)
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o600)],
            ofItemAtPath: oversizedCapability.path
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try PrivateCapabilityFile.read(
                path: oversizedCapability.standardizedFileURL.path
            )
        }
        let shortCapability = privateRoot.appendingPathComponent("short.bin")
        try Data(repeating: 0x01, count: 31).write(to: shortCapability)
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o600)],
            ofItemAtPath: shortCapability.path
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try PrivateCapabilityFile.read(
                path: shortCapability.standardizedFileURL.path
            )
        }
        let unreadableCapability = privateRoot.appendingPathComponent("unreadable.bin")
        try Data(repeating: 0x03, count: 32).write(to: unreadableCapability)
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o000)],
            ofItemAtPath: unreadableCapability.path
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try PrivateCapabilityFile.read(
                path: unreadableCapability.standardizedFileURL.path
            )
        }
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o600)],
            ofItemAtPath: unreadableCapability.path
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try PrivateCapabilityFile.read(
                path: privateRoot.appendingPathComponent("missing.bin").path
            )
        }

        let regularSocketURL = privateRoot.appendingPathComponent("regular.sock")
        try Data("not-a-socket".utf8).write(to: regularSocketURL)
        let regularSocket = try SecureUnixDomainSocketPath(
            path: regularSocketURL.standardizedFileURL.path
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try regularSocket.prepareForBinding()
        }
        #expect(throws: SecureUnixDomainSocketError.self) {
            try regularSocket.sealBoundSocket()
        }
        try regularSocket.removeOwnedSocket()

        let parentFile = privateRoot.appendingPathComponent("parent-file")
        try Data("parent".utf8).write(to: parentFile)
        let invalidParent = try SecureUnixDomainSocketPath(
            path: parentFile.appendingPathComponent("broker.sock")
                .standardizedFileURL.path
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try invalidParent.prepareForBinding()
        }

        let noWriteRoot = privateRoot.appendingPathComponent(
            "no-write",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: noWriteRoot,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o500)]
        )
        let creationDenied = try SecureUnixDomainSocketPath(
            path: noWriteRoot
                .appendingPathComponent("missing", isDirectory: true)
                .appendingPathComponent("broker.sock")
                .standardizedFileURL.path
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try creationDenied.prepareForBinding()
        }
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o700)],
            ofItemAtPath: noWriteRoot.path
        )

        let noTraverseRoot = privateRoot.appendingPathComponent(
            "no-traverse",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: noTraverseRoot,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o600)]
        )
        let inspectionDenied = try SecureUnixDomainSocketPath(
            path: noTraverseRoot.appendingPathComponent("broker.sock")
                .standardizedFileURL.path
        )
        #expect(throws: SecureUnixDomainSocketError.self) {
            try inspectionDenied.prepareForBinding()
        }
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o700)],
            ofItemAtPath: noTraverseRoot.path
        )
    }

    @Test("transport configuration rejects empty trust, identity, and feature inputs")
    func transportConfigurationBoundaries() throws {
        #expect(
            BrokerTransportConfigurationError.invalidValue("configuration")
                .errorDescription == "configuration"
        )
        let capability = Data(repeating: 0xA5, count: 32)
        #expect(throws: BrokerTransportConfigurationError.self) {
            try BrokerHandshakePolicy(
                protocolVersion: " ",
                expectedCallerBundleID: "bundle",
                expectedCallerTeamID: "team",
                verificationCapability: capability
            )
        }
        #expect(throws: BrokerTransportConfigurationError.self) {
            try BrokerHandshakePolicy(
                protocolVersion: "1",
                expectedCallerBundleID: " ",
                expectedCallerTeamID: "team",
                verificationCapability: capability
            )
        }
        #expect(throws: BrokerTransportConfigurationError.self) {
            try BrokerHandshakePolicy(
                protocolVersion: "1",
                expectedCallerBundleID: "bundle",
                expectedCallerTeamID: "team",
                verificationCapability: Data(repeating: 0, count: 31)
            )
        }
        let handshake = try BrokerHandshakePolicy(
            protocolVersion: " 1 ",
            expectedCallerBundleID: " bundle ",
            expectedCallerTeamID: " team ",
            verificationCapability: capability
        )
        #expect(handshake.protocolVersion == "1")
        #expect(handshake.expectedCallerBundleID == "bundle")

        let key = Curve25519.Signing.PrivateKey()
        let verifier = try BrokerToolAuthorizationVerifier(
            publicKeyRawRepresentation: key.publicKey.rawRepresentation
        )
        let artifactRoot = URL(fileURLWithPath: "/private/tmp/config-artifacts")
        #expect(throws: BrokerTransportConfigurationError.self) {
            try BrokerTransportConfiguration(
                handshake: handshake,
                toolAuthorizationVerifier: verifier,
                brokerVersion: " ",
                brokerInstanceID: "instance",
                artifactRoot: artifactRoot
            )
        }
        #expect(throws: BrokerTransportConfigurationError.self) {
            try BrokerTransportConfiguration(
                handshake: handshake,
                toolAuthorizationVerifier: verifier,
                brokerVersion: "1",
                brokerInstanceID: "instance",
                artifactRoot: try #require(URL(string: "relative-artifacts"))
            )
        }
        #expect(throws: BrokerTransportConfigurationError.self) {
            try BrokerTransportConfiguration(
                handshake: handshake,
                toolAuthorizationVerifier: verifier,
                brokerVersion: "1",
                brokerInstanceID: "instance",
                artifactRoot: artifactRoot,
                features: []
            )
        }
        #expect(throws: BrokerTransportConfigurationError.self) {
            try BrokerTransportConfiguration(
                handshake: handshake,
                toolAuthorizationVerifier: verifier,
                brokerVersion: "1",
                brokerInstanceID: "instance",
                artifactRoot: artifactRoot,
                features: [" "]
            )
        }
        let configuration = try BrokerTransportConfiguration(
            handshake: handshake,
            toolAuthorizationVerifier: verifier,
            brokerVersion: " 1 ",
            brokerInstanceID: " instance ",
            artifactRoot: artifactRoot
        )
        #expect(configuration.brokerVersion == "1")
        #expect(configuration.brokerInstanceID == "instance")
        #expect(configuration.features.contains("cancel_session"))
        #expect(configuration.features.contains("transport_peer_code_identity_unavailable"))
    }

    @Test("authorization verifier rejects forgery, expiry, and key substitution")
    func signedAuthorizationVerifierFailsClosed() throws {
        let trustedKey = Curve25519.Signing.PrivateKey()
        let attackerKey = Curve25519.Signing.PrivateKey()
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let verifier = try BrokerToolAuthorizationVerifier(
            publicKeyRawRepresentation: trustedKey.publicKey.rawRepresentation,
            now: { now }
        )
        let valid = try makeAuthorization(
            privateKey: trustedKey,
            now: now,
            callID: "call-signed-1",
            arguments: ["operation": "get_permissions"],
            approvalGrantDigest: "grant-signed-1",
            policyRevision: "policy-signed-v1"
        )
        #expect(try verifier.verify(valid).callID == "call-signed-1")
        #expect(verifier == verifier)
        for invalidNamespace in ["", "bad/namespace"] {
            let invalid = try makeAuthorization(
                privateKey: trustedKey,
                now: now,
                callID: "call-invalid-namespace",
                arguments: ["operation": "get_permissions"],
                approvalGrantDigest: "grant-invalid-namespace",
                policyRevision: "policy-signed-v1",
                artifactRoot: invalidNamespace
            )
            #expect(throws: BrokerToolAuthorizationError.malformed) {
                try verifier.verify(invalid)
            }
        }
        #expect(throws: BrokerToolAuthorizationError.invalidConfiguration(
            "Computer Use authorization public key must contain exactly 32 bytes."
        )) {
            try BrokerToolAuthorizationVerifier(publicKeyRawRepresentation: Data())
        }
        for error in [
            BrokerToolAuthorizationError.invalidConfiguration("configuration"),
            .missing,
            .malformed,
            .invalidSignature,
            .expired,
            .bindingMismatch,
        ] {
            #expect(error.errorDescription != nil)
        }

        var malformedEnvelope = valid
        malformedEnvelope.algorithm = "rsa"
        #expect(throws: BrokerToolAuthorizationError.malformed) {
            try verifier.verify(malformedEnvelope)
        }
        var malformedPayload = valid
        malformedPayload.signedPayload = Data("{}".utf8)
        malformedPayload.signature = try trustedKey.signature(
            for: malformedPayload.signedPayload
        )
        #expect(throws: BrokerToolAuthorizationError.malformed) {
            try verifier.verify(malformedPayload)
        }

        let emptySession = try makeAuthorization(
            privateKey: trustedKey,
            now: now,
            callID: "call-empty-session",
            arguments: ["operation": "get_permissions"],
            approvalGrantDigest: "grant-empty-session",
            policyRevision: "policy-signed-v1",
            sessionID: ""
        )
        #expect(throws: BrokerToolAuthorizationError.malformed) {
            try verifier.verify(emptySession)
        }

        var inconsistentDigest = valid
        var inconsistentPayload = try #require(
            JSONSerialization.jsonObject(with: valid.signedPayload)
                as? [String: Any]
        )
        inconsistentPayload["argument_digest"] = "substituted-argument-digest"
        inconsistentDigest.signedPayload = try JSONSerialization.data(
            withJSONObject: inconsistentPayload,
            options: [.sortedKeys, .withoutEscapingSlashes]
        )
        inconsistentDigest.signature = try trustedKey.signature(
            for: inconsistentDigest.signedPayload
        )
        #expect(throws: BrokerToolAuthorizationError.malformed) {
            try verifier.verify(inconsistentDigest)
        }

        var forged = valid
        forged.signature = try attackerKey.signature(
            for: valid.signedPayload
        )
        #expect(throws: BrokerToolAuthorizationError.invalidSignature) {
            try verifier.verify(forged)
        }

        var substituted = try makeAuthorization(
            privateKey: attackerKey,
            now: now,
            callID: "call-signed-1",
            arguments: ["operation": "get_permissions"],
            approvalGrantDigest: "grant-signed-1",
            policyRevision: "policy-signed-v1"
        )
        substituted.keyID = valid.keyID
        #expect(throws: BrokerToolAuthorizationError.invalidSignature) {
            try verifier.verify(substituted)
        }

        let expiredVerifier = try BrokerToolAuthorizationVerifier(
            publicKeyRawRepresentation: trustedKey.publicKey.rawRepresentation,
            now: { now.addingTimeInterval(61) }
        )
        #expect(throws: BrokerToolAuthorizationError.expired) {
            try expiredVerifier.verify(valid)
        }
        #expect(
            try expiredVerifier.verifyForSessionCancellation(valid).callID
                == "call-signed-1"
        )

        let withinCancellationGraceVerifier = try BrokerToolAuthorizationVerifier(
            publicKeyRawRepresentation: trustedKey.publicKey.rawRepresentation,
            now: { now.addingTimeInterval(959) }
        )
        #expect(
            try withinCancellationGraceVerifier
                .verifyForSessionCancellation(valid).callID == "call-signed-1"
        )

        let beyondCancellationGraceVerifier = try BrokerToolAuthorizationVerifier(
            publicKeyRawRepresentation: trustedKey.publicKey.rawRepresentation,
            now: { now.addingTimeInterval(961) }
        )
        #expect(throws: BrokerToolAuthorizationError.expired) {
            try beyondCancellationGraceVerifier
                .verifyForSessionCancellation(valid)
        }
        #expect(throws: BrokerToolAuthorizationError.invalidConfiguration(
            "Computer Use cancellation authorization grace is out of bounds."
        )) {
            try verifier.verifyForSessionCancellation(
                valid,
                graceMilliseconds: 0
            )
        }
        #expect(throws: BrokerToolAuthorizationError.invalidConfiguration(
            "Computer Use cancellation authorization grace is out of bounds."
        )) {
            try verifier.verifyForSessionCancellation(
                valid,
                graceMilliseconds: 900_001
            )
        }
    }
}

private struct EscapingFrameCaptureAdapter: FrameCaptureAdapter {
    let adapterKind = "test.escape"

    func permissionState() async -> ComputerUsePermissionState {
        .granted
    }

    func capture(
        _ request: AdapterFrameCaptureRequest
    ) async throws -> ComputerFrameObservation {
        ComputerFrameObservation(
            frameID: request.frameID,
            generation: request.generation,
            target: request.target,
            artifact: ComputerArtifactReference(
                artifactID: "escaping-artifact",
                path: "/private/tmp/escaping-artifact.bin",
                sha256: String(repeating: "0", count: 64),
                byteCount: 1,
                mediaType: "application/octet-stream",
                width: 1,
                height: 1,
                adapterKind: adapterKind
            ),
            capturedAt: request.capturedAt
        )
    }
}

private struct TargetInventoryFrameCaptureAdapter: FrameCaptureAdapter {
    let adapterKind = "test.target-inventory"
    let targets: [ComputerWindowTarget]

    func permissionState() async -> ComputerUsePermissionState {
        .granted
    }

    func listTargets() async throws -> [ComputerWindowTarget] {
        targets
    }

    func capture(
        _: AdapterFrameCaptureRequest
    ) async throws -> ComputerFrameObservation {
        throw TestAdapterError(message: "capture is outside this fixture")
    }
}

private final class LiveComputerBrokerFixture: @unchecked Sendable {
    let socketPath: String
    let verificationCapability: Data
    let authorizationPrivateKey: Curve25519.Signing.PrivateKey
    let clock: TestComputerUseClock
    let accessibility: FakeAccessibilityAdapter
    let inspectionRelease: TestLatch

    private let root: URL
    private let server: ComputerUseBrokerUDSServer
    private let provider: ComputerUseBrokerGRPCProvider

    private init(
        socketPath: String,
        verificationCapability: Data,
        authorizationPrivateKey: Curve25519.Signing.PrivateKey,
        clock: TestComputerUseClock,
        accessibility: FakeAccessibilityAdapter,
        inspectionRelease: TestLatch,
        root: URL,
        server: ComputerUseBrokerUDSServer,
        provider: ComputerUseBrokerGRPCProvider
    ) {
        self.socketPath = socketPath
        self.verificationCapability = verificationCapability
        self.authorizationPrivateKey = authorizationPrivateKey
        self.clock = clock
        self.accessibility = accessibility
        self.inspectionRelease = inspectionRelease
        self.root = root
        self.server = server
        self.provider = provider
    }

    static func makeUnstarted(
        frameCapture: any FrameCaptureAdapter = FakeFrameCaptureAdapter()
    ) throws -> LiveComputerBrokerFixture {
        let root = URL(fileURLWithPath: "/private/tmp", isDirectory: true).appendingPathComponent(
            "mcb-uds-\(UUID().uuidString.prefix(8))",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: NSNumber(value: 0o700)]
        )
        let artifactRoot = root.appendingPathComponent("artifacts", isDirectory: true)
        let socketPath = root
            .appendingPathComponent("private-runtime", isDirectory: true)
            .appendingPathComponent("broker.sock")
            .path
        let clock = TestComputerUseClock(now: Date(timeIntervalSince1970: 1_800_000_000))
        let inspectionRelease = TestLatch()
        let accessibility = FakeAccessibilityAdapter(
            inspectionRelease: inspectionRelease,
            discoveredElements: [
                ComputerFrameElement(
                    handleID: "fixture-button",
                    frameGeneration: 0,
                    role: "AXButton",
                    title: "Continue",
                    isSecure: false,
                    isEnabled: true
                ),
            ]
        )
        let broker = DefaultComputerUseBroker(
            frameCapture: frameCapture,
            accessibility: accessibility,
            clock: clock,
            identityGenerator: TestComputerUseIdentityGenerator(),
            artifactRoot: artifactRoot
        )
        let verificationCapability = testVerificationCapability
        let authorizationPrivateKey = Curve25519.Signing.PrivateKey()
        let provider = ComputerUseBrokerGRPCProvider(
            broker: broker,
            configuration: try BrokerTransportConfiguration(
                handshake: BrokerHandshakePolicy(
                    protocolVersion: "1",
                    expectedCallerBundleID: "io.melix.control-plane",
                    expectedCallerTeamID: "MELIXTEAM1",
                    verificationCapability: verificationCapability
                ),
                toolAuthorizationVerifier: try BrokerToolAuthorizationVerifier(
                    publicKeyRawRepresentation:
                        authorizationPrivateKey.publicKey.rawRepresentation,
                    now: { clock.now() }
                ),
                brokerVersion: "0.2.0-test",
                brokerInstanceID: "broker-uds-test",
                artifactRoot: artifactRoot
            )
        )
        let server = ComputerUseBrokerUDSServer(
            socket: try SecureUnixDomainSocketPath(path: socketPath),
            service: provider
        )
        return LiveComputerBrokerFixture(
            socketPath: socketPath,
            verificationCapability: verificationCapability,
            authorizationPrivateKey: authorizationPrivateKey,
            clock: clock,
            accessibility: accessibility,
            inspectionRelease: inspectionRelease,
            root: root,
            server: server,
            provider: provider
        )
    }

    static func start(
        frameCapture: any FrameCaptureAdapter = FakeFrameCaptureAdapter()
    ) async throws -> LiveComputerBrokerFixture {
        let fixture = try makeUnstarted(frameCapture: frameCapture)
        do {
            try await fixture.server.start()
            return fixture
        } catch {
            await fixture.server.stop()
            fixture.removeFiles()
            throw error
        }
    }

    func stop() async {
        await server.stop()
    }

    func isRunning() async -> Bool {
        await server.isRunning
    }

    func startAgain() async throws {
        try await server.start()
    }

    func competingServer() throws -> ComputerUseBrokerUDSServer {
        ComputerUseBrokerUDSServer(
            socket: try SecureUnixDomainSocketPath(
                path: URL(fileURLWithPath: socketPath).standardizedFileURL.path
            ),
            service: provider
        )
    }

    func waitForTermination() async throws {
        try await server.wait()
    }

    func removeFiles() {
        try? FileManager.default.removeItem(at: root)
    }

    func authorization(
        callID: String,
        arguments: [String: Any],
        approvalGrantDigest: String = "grant-transport-1",
        policyRevision: String = "policy-transport-v1",
        runID: String = "run-transport-1",
        sessionID: String = "session-transport-1",
        branchID: String = "branch-transport-1",
        actorID: String = "operator-transport",
        artifactRoot: String = "uds-contract"
    ) throws -> Melix_Computer_V1_ControlPlaneToolAuthorization {
        try makeAuthorization(
            privateKey: authorizationPrivateKey,
            now: clock.now(),
            callID: callID,
            arguments: arguments,
            approvalGrantDigest: approvalGrantDigest,
            policyRevision: policyRevision,
            runID: runID,
            sessionID: sessionID,
            branchID: branchID,
            actorID: actorID,
            artifactRoot: artifactRoot
        )
    }
}

private func makeHandshake(capability: Data) -> Melix_Computer_V1_BrokerHandshakeRequest {
    var request = Melix_Computer_V1_BrokerHandshakeRequest()
    request.protocolVersion = "1"
    request.controlPlaneInstanceID = "control-plane-uds-test"
    request.callerBundleID = "io.melix.control-plane"
    request.callerTeamID = "MELIXTEAM1"
    request.callerVerificationCapability = capability
    return request
}

private func makeOpenRequest() -> Melix_Computer_V1_OpenComputerSessionRequest {
    var identity = Melix_Computer_V1_ComputerSessionIdentity()
    identity.agentRunID = "run-transport-1"
    identity.requestID = "tool-transport-1"
    identity.toolCallID = "tool-transport-1"
    identity.branchID = "branch-transport-1"
    identity.actorID = "operator-transport"

    var target = Melix_Computer_V1_TargetIdentity()
    target.bundleID = "io.melix.fixture"
    target.processID = 4242
    target.processLaunchIdentity = "fixture-launch-transport-1"
    target.windowID = 77
    target.windowTitle = "Computer Use Fixture"

    var limits = Melix_Computer_V1_ComputerSessionLimits()
    limits.maximumFrames = 4
    limits.maximumActions = 2
    limits.maximumArtifactBytes = 1_024 * 1_024
    limits.idleDeadlineUnixMs = 1_800_000_060_000
    limits.absoluteDeadlineUnixMs = 1_800_000_300_000

    var request = Melix_Computer_V1_OpenComputerSessionRequest()
    request.identity = identity
    request.allowedTargets = [target]
    request.artifactRoot = "uds-contract"
    request.limits = limits
    request.idempotencyKey = "grant-open-transport-1"
    request.callerVerificationCapability = testVerificationCapability
    return request
}

private func makeActionRequest(
    lease: Melix_Computer_V1_ComputerSessionLease,
    target: Melix_Computer_V1_TargetIdentity,
    frame: Melix_Computer_V1_CaptureFrameResponse,
    now: Date,
    authorization: Melix_Computer_V1_ControlPlaneToolAuthorization
) throws -> Melix_Computer_V1_ExecuteComputerActionRequest {
    let actionID = "action-transport-1"
    let idempotencyKey = "approval-transport-1"
    let coreTarget = ComputerWindowTarget(
        bundleIdentifier: target.bundleID,
        processIdentifier: target.processID,
        processLaunchIdentity: target.processLaunchIdentity,
        windowID: target.windowID,
        windowTitle: target.windowTitle
    )
    let coreAction = ComputerAction.press(
        PressAccessibilityElementAction(
            element: AccessibilityElementTarget(
                accessibilityIdentifier: "fixture-button",
                title: "Continue",
                role: "AXButton"
            )
        )
    )
    let digest = try ComputerActionDigest.compute(
        sessionID: lease.identity.sessionID,
        actionID: actionID,
        idempotencyKey: idempotencyKey,
        target: coreTarget,
        expectedFrameID: frame.observationID,
        expectedFrameGeneration: frame.frameGeneration,
        action: coreAction
    )

    var element = Melix_Computer_V1_ElementHandle()
    element.handleID = "fixture-button"
    element.frameGeneration = frame.frameGeneration
    element.role = "AXButton"
    element.title = "Continue"
    element.enabled = true

    var press = Melix_Computer_V1_PressElementAction()
    press.element = element

    var approval = Melix_Computer_V1_ApprovalGrant()
    approval.approvalID = "approval-transport-1"
    approval.actionDigest = digest
    approval.policyHash = "policy-transport-v1"
    approval.approvedAtUnixMs = Int64(now.timeIntervalSince1970 * 1_000)
    approval.expiresAtUnixMs = Int64(now.addingTimeInterval(60).timeIntervalSince1970 * 1_000)
    approval.actorID = lease.identity.actorID
    approval.scope = "computer.press"

    var request = Melix_Computer_V1_ExecuteComputerActionRequest()
    request.identity = lease.identity
    request.sessionCapability = lease.sessionCapability
    request.target = target
    request.actionID = actionID
    request.attempt = 1
    request.idempotencyKey = idempotencyKey
    request.expectedObservationID = frame.observationID
    request.expectedFrameGeneration = frame.frameGeneration
    request.deadlineUnixMs = Int64(
        now.addingTimeInterval(30).timeIntervalSince1970 * 1_000
    )
    request.approval = approval
    request.authorization = authorization
    request.callerVerificationCapability = testVerificationCapability
    request.pressElement = press
    return request
}

private func authorizeOpen(
    _ request: Melix_Computer_V1_OpenComputerSessionRequest,
    fixture: LiveComputerBrokerFixture
) throws -> Melix_Computer_V1_OpenComputerSessionRequest {
    var authorized = request
    authorized.authorization = try fixture.authorization(
        callID: request.identity.toolCallID,
        arguments: [
            "operation": "open_session",
            "allowed_targets": request.allowedTargets.map(targetPayload),
        ],
        approvalGrantDigest: request.idempotencyKey,
        runID: request.identity.agentRunID,
        // The signed session is the owning Agent conversation, not the broker
        // session ID (which is intentionally assigned only after OpenSession).
        sessionID: "agent-session-transport-1",
        branchID: request.identity.branchID,
        actorID: request.identity.actorID
    )
    return authorized
}

private func makeCaptureRequest(
    lease: Melix_Computer_V1_ComputerSessionLease,
    target: Melix_Computer_V1_TargetIdentity,
    callID: String,
    expectedPreviousGeneration: UInt64 = 0
) -> Melix_Computer_V1_CaptureFrameRequest {
    var request = Melix_Computer_V1_CaptureFrameRequest()
    request.identity = lease.identity
    request.sessionCapability = lease.sessionCapability
    request.target = target
    request.captureID = "capture-\(callID)"
    request.expectedPreviousGeneration = expectedPreviousGeneration
    request.callerVerificationCapability = testVerificationCapability
    return request
}

private func authorizeCapture(
    _ request: Melix_Computer_V1_CaptureFrameRequest,
    callID: String,
    fixture: LiveComputerBrokerFixture
) throws -> Melix_Computer_V1_CaptureFrameRequest {
    var authorized = request
    if authorized.deadlineUnixMs == 0 {
        authorized.deadlineUnixMs = Int64(
            fixture.clock.now().addingTimeInterval(30)
                .timeIntervalSince1970 * 1_000
        )
    }
    authorized.authorization = try fixture.authorization(
        callID: callID,
        arguments: [
            "operation": "capture_frame",
            "session_id": request.identity.sessionID,
            "target": targetPayload(request.target),
            "expected_previous_generation": authorized.expectedPreviousGeneration,
        ],
        runID: authorized.identity.agentRunID,
        sessionID: authorized.identity.sessionID,
        branchID: authorized.identity.branchID,
        actorID: authorized.identity.actorID
    )
    return authorized
}

private func actionArguments(
    _ request: Melix_Computer_V1_ExecuteComputerActionRequest
) -> [String: Any] {
    [
        "operation": "press_element",
        "session_id": request.identity.sessionID,
        "target": targetPayload(request.target),
        "expected_observation_id": request.expectedObservationID,
        "expected_frame_generation": request.expectedFrameGeneration,
        "element": [
            "handle_id": request.pressElement.element.handleID,
            "title": request.pressElement.element.title,
            "role": request.pressElement.element.role,
        ],
        "attempt": request.attempt,
    ]
}

private func authorizeAction(
    _ request: Melix_Computer_V1_ExecuteComputerActionRequest,
    fixture: LiveComputerBrokerFixture,
    callID: String? = nil,
    arguments: [String: Any]? = nil
) throws -> Melix_Computer_V1_ExecuteComputerActionRequest {
    var authorized = request
    authorized.authorization = try fixture.authorization(
        callID: callID ?? request.actionID,
        arguments: arguments ?? actionArguments(request),
        approvalGrantDigest: request.approval.approvalID,
        policyRevision: request.approval.policyHash,
        runID: request.identity.agentRunID,
        sessionID: request.identity.sessionID,
        branchID: request.identity.branchID,
        actorID: request.identity.actorID
    )
    return authorized
}

private func makeCancelActionRequest(
    lease: Melix_Computer_V1_ComputerSessionLease,
    actionID: String,
    attempt: UInt64,
    cancellationID: String
) -> Melix_Computer_V1_CancelComputerActionRequest {
    var request = Melix_Computer_V1_CancelComputerActionRequest()
    request.identity = lease.identity
    request.sessionCapability = lease.sessionCapability
    request.actionID = actionID
    request.attempt = attempt
    request.cancellationID = cancellationID
    request.callerVerificationCapability = testVerificationCapability
    return request
}

private struct TestControlPlaneAuthorizationPayload: Codable {
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
}

private func makeAuthorization(
    privateKey: Curve25519.Signing.PrivateKey,
    now: Date,
    callID: String,
    arguments: [String: Any],
    approvalGrantDigest: String,
    policyRevision: String,
    runID: String = "run-transport-1",
    sessionID: String = "session-transport-1",
    branchID: String = "branch-transport-1",
    actorID: String = "operator-transport",
    artifactRoot: String = "uds-contract"
) throws -> Melix_Computer_V1_ControlPlaneToolAuthorization {
    let argumentsData = try JSONSerialization.data(
        withJSONObject: arguments,
        options: [.sortedKeys, .withoutEscapingSlashes]
    )
    let argumentsJSON = try #require(
        String(data: argumentsData, encoding: .utf8)
    )
    let keyID = SHA256.hash(
        data: privateKey.publicKey.rawRepresentation
    ).map { String(format: "%02x", $0) }.joined()
    let issuedAtUnixMs = Int64(now.timeIntervalSince1970 * 1_000)
    let payload = TestControlPlaneAuthorizationPayload(
        schemaVersion: "melix.computer.tool-authorization.v2",
        keyID: keyID,
        runID: runID,
        sessionID: sessionID,
        branchID: branchID,
        actorID: actorID,
        callID: callID,
        sourceID: "computer",
        toolName: "computer_use",
        argumentsJSON: argumentsJSON,
        schemaDigest: "schema-computer-transport-v1",
        argumentDigest: SHA256.hash(data: argumentsData)
            .map { String(format: "%02x", $0) }.joined(),
        bindingDigest: "binding-transport-v1",
        approvalGrantDigest: approvalGrantDigest,
        policyRevision: policyRevision,
        idempotencyKey: approvalGrantDigest,
        artifactRoot: artifactRoot,
        maximumFrames: 16,
        maximumActions: 8,
        maximumArtifactBytes: 16 * 1_024 * 1_024,
        idleDeadlineUnixMs: issuedAtUnixMs + 60_000,
        absoluteDeadlineUnixMs: issuedAtUnixMs + 300_000,
        requestDeadlineUnixMs: issuedAtUnixMs + 60_000,
        issuedAtUnixMs: issuedAtUnixMs,
        expiresAtUnixMs: issuedAtUnixMs + 60_000
    )
    let encoder = JSONEncoder()
    encoder.keyEncodingStrategy = .convertToSnakeCase
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
    let signedPayload = try encoder.encode(payload)
    var authorization = Melix_Computer_V1_ControlPlaneToolAuthorization()
    authorization.keyID = keyID
    authorization.algorithm = "ed25519"
    authorization.signedPayload = signedPayload
    authorization.signature = try privateKey.signature(for: signedPayload)
    return authorization
}

private func targetPayload(
    _ target: Melix_Computer_V1_TargetIdentity
) -> [String: Any] {
    [
        "bundle_id": target.bundleID,
        "process_id": target.processID,
        "process_launch_identity": target.processLaunchIdentity,
        "window_id": target.windowID,
        "window_title": target.windowTitle,
    ]
}

private struct TestSocketIdentity: Equatable {
    let device: dev_t
    let inode: ino_t
    let generation: UInt32
    let birthSeconds: Int
    let birthNanoseconds: Int
}

private func testSocketIdentity(at path: String) throws -> TestSocketIdentity {
    var status = stat()
    guard Darwin.lstat(path, &status) == 0 else {
        throw NSError(
            domain: NSPOSIXErrorDomain,
            code: Int(errno),
            userInfo: [NSFilePathErrorKey: path]
        )
    }
    return TestSocketIdentity(
        device: status.st_dev,
        inode: status.st_ino,
        generation: status.st_gen,
        birthSeconds: status.st_birthtimespec.tv_sec,
        birthNanoseconds: status.st_birthtimespec.tv_nsec
    )
}

private func bindTestUnixSocket(
    at path: String,
    listening: Bool
) throws -> Int32 {
    let descriptor = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
    guard descriptor >= 0 else {
        throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno))
    }
    do {
        var address = sockaddr_un()
        address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        address.sun_family = sa_family_t(AF_UNIX)
        let pathCapacity = MemoryLayout.size(ofValue: address.sun_path)
        path.withCString { source in
            withUnsafeMutablePointer(to: &address.sun_path) { destination in
                destination.withMemoryRebound(
                    to: CChar.self,
                    capacity: pathCapacity
                ) { bytes in
                    _ = strlcpy(bytes, source, pathCapacity)
                }
            }
        }
        let bindResult = withUnsafePointer(to: &address) { pointer in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { socketAddress in
                Darwin.bind(
                    descriptor,
                    socketAddress,
                    socklen_t(MemoryLayout<sockaddr_un>.size)
                )
            }
        }
        guard bindResult == 0 else {
            throw NSError(
                domain: NSPOSIXErrorDomain,
                code: Int(errno),
                userInfo: [NSFilePathErrorKey: path]
            )
        }
        guard Darwin.chmod(path, 0o600) == 0 else {
            throw NSError(
                domain: NSPOSIXErrorDomain,
                code: Int(errno),
                userInfo: [NSFilePathErrorKey: path]
            )
        }
        if listening {
            guard Darwin.listen(descriptor, 1) == 0 else {
                throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno))
            }
        }
        return descriptor
    } catch {
        _ = Darwin.close(descriptor)
        throw error
    }
}

private func expectRPCError<T: Sendable>(
    _ expectedCode: RPCError.Code,
    fileID: String = #fileID,
    line: Int = #line,
    operation: () async throws -> T
) async {
    do {
        _ = try await operation()
        Issue.record("Expected gRPC error \(expectedCode).")
    } catch let error as RPCError {
        #expect(
            error.code == expectedCode,
            "Expected \(expectedCode) at \(fileID):\(line), received \(error.code)."
        )
    } catch {
        Issue.record("Expected RPCError, received \(error).")
    }
}

private func expectExecuteError(
    _ expectedCode: RPCError.Code,
    rpc: Melix_Computer_V1_ComputerUseBrokerService.Client<HTTP2ClientTransport.Posix>,
    request: Melix_Computer_V1_ExecuteComputerActionRequest,
    fileID: String = #fileID,
    line: Int = #line
) async {
    await expectRPCError(expectedCode, fileID: fileID, line: line) {
        try await rpc.executeAction(request) { response in
            for try await _ in response.messages {}
        }
    }
}

private func expectSecureSocketError(
    operation: () async throws -> Void
) async {
    do {
        try await operation()
        Issue.record("Expected SecureUnixDomainSocketError.")
    } catch is SecureUnixDomainSocketError {
        return
    } catch {
        Issue.record("Expected SecureUnixDomainSocketError, received \(error).")
    }
}

private func expectAnyError(
    operation: () async throws -> Void
) async {
    do {
        try await operation()
        Issue.record("Expected operation to fail.")
    } catch {
        return
    }
}
