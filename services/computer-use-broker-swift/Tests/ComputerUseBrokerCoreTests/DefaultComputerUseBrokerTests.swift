import ComputerUseBrokerCore
import CryptoKit
import Darwin
import Foundation
import Testing

@Suite("Computer Use Broker core", .serialized)
struct DefaultComputerUseBrokerTests {
    @Test("evidence names retain colliding readable prefixes without overwrite")
    func evidenceNamesAreCollisionResistantAndExclusive() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-computer-evidence-\(UUID().uuidString)",
            isDirectory: true
        )
        defer { try? FileManager.default.removeItem(at: root) }

        let target = ComputerWindowTarget(
            bundleIdentifier: "io.melix.fixture",
            processIdentifier: 42,
            processLaunchIdentity: "fixture-launch",
            windowID: 7,
            windowTitle: "Fixture"
        )
        let frameArtifact = ComputerArtifactReference(
            artifactID: "frame-1",
            path: root.appendingPathComponent("frame-1.bin").path,
            sha256: String(repeating: "0", count: 64),
            byteCount: 1,
            mediaType: "application/octet-stream",
            adapterKind: "fixture"
        )
        let frame = ComputerFrameObservation(
            frameID: "frame-1",
            generation: 1,
            target: target,
            artifact: frameArtifact,
            capturedAt: Date(timeIntervalSince1970: 1_800_000_000)
        )
        func receipt(actionID: String) -> ComputerActionReceipt {
            ComputerActionReceipt(
                sessionID: "session-1",
                actionID: actionID,
                idempotencyKey: "idempotency-\(actionID)",
                state: .completed,
                target: target,
                actionDigest: String(repeating: "a", count: 64),
                approvalID: "approval-1",
                policyRevision: "policy-1",
                adapterKind: "fixture",
                sideEffectCommitted: true,
                beforeFrame: frame,
                afterFrame: nil,
                elementSnapshot: nil,
                startedAt: Date(timeIntervalSince1970: 1_800_000_000),
                finishedAt: Date(timeIntervalSince1970: 1_800_000_001),
                durationMilliseconds: 1_000,
                failure: nil
            )
        }

        let sink = FileComputerUseEvidenceSink()
        let firstReceipt = receipt(actionID: "same/action")
        let secondReceipt = receipt(actionID: "same?action")
        let first = try sink.record(firstReceipt, in: root)
        let second = try sink.record(secondReceipt, in: root)
        let firstDigest = SHA256.hash(data: Data(firstReceipt.actionID.utf8))
            .map { String(format: "%02x", $0) }
            .joined()
        let secondDigest = SHA256.hash(data: Data(secondReceipt.actionID.utf8))
            .map { String(format: "%02x", $0) }
            .joined()

        #expect(first.path != second.path)
        #expect(first.artifactID == "action-receipt-same_action-\(firstDigest)")
        #expect(second.artifactID == "action-receipt-same_action-\(secondDigest)")
        #expect(FileManager.default.fileExists(atPath: first.path))
        #expect(FileManager.default.fileExists(atPath: second.path))
        let firstData = try Data(contentsOf: URL(fileURLWithPath: first.path))

        do {
            _ = try sink.record(firstReceipt, in: root)
            Issue.record("Expected an existing evidence receipt to reject overwrite")
        } catch let error as NSError {
            #expect(error.domain == NSPOSIXErrorDomain)
            #expect(error.code == Int(EEXIST))
        }
        #expect(try Data(contentsOf: URL(fileURLWithPath: first.path)) == firstData)
    }

    @Test("semantic press emits one terminal receipt with before/after evidence")
    func semanticPressProducesBoundedEvidence() async throws {
        let context = try await makeBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let request = try makeActionRequest(
            context: context,
            actionID: "action-1",
            idempotencyKey: "idem-1",
            approvalID: "approval-1"
        )

        let execution = try await context.broker.performAction(request)
        let events = await collectEvents(execution)
        let terminalEvents = events.filter(\.isTerminal)
        let pressCount = await context.accessibility.pressCount()

        #expect(events.first?.state == .queued)
        #expect(terminalEvents.count == 1)
        #expect(terminalEvents.first?.state == .completed)
        #expect(terminalEvents.first?.receipt?.sideEffectCommitted == true)
        #expect(terminalEvents.first?.receipt?.beforeFrame == context.frame)
        #expect(terminalEvents.first?.receipt?.afterFrame != nil)
        #expect(pressCount == 1)
        let evidencePath = terminalEvents.first?.receipt?.evidenceArtifact?.path ?? ""
        #expect(!evidencePath.isEmpty)
        #expect(FileManager.default.fileExists(atPath: evidencePath))
        #expect(terminalEvents.first?.receipt?.evidenceArtifact?.sha256.count == 64)
        #expect(events.map(\.sequence) == Array(1...UInt64(events.count)))
        let framePermissions = try #require(
            FileManager.default.attributesOfItem(
                atPath: context.frame.artifact.path
            )[.posixPermissions] as? NSNumber
        )
        let evidencePermissions = try #require(
            FileManager.default.attributesOfItem(
                atPath: evidencePath
            )[.posixPermissions] as? NSNumber
        )
        let sessionPermissions = try #require(
            FileManager.default.attributesOfItem(
                atPath: URL(fileURLWithPath: evidencePath)
                    .deletingLastPathComponent().path
            )[.posixPermissions] as? NSNumber
        )
        #expect(framePermissions.intValue & 0o777 == 0o600)
        #expect(evidencePermissions.intValue & 0o777 == 0o600)
        #expect(sessionPermissions.intValue & 0o777 == 0o700)

        let metrics = await context.broker.metricsSnapshot()
        #expect(metrics.values["computer.action_count"] == 1)
        #expect(metrics.values["computer.capture_count"] == 2)
        #expect(metrics.values["computer.terminal_duplicate_event_count"] == 0)

        let closeReceipt = try await context.broker.closeSession(
            CloseComputerUseSessionRequest(
                sessionID: context.session.sessionID,
                capability: context.session.capability
            )
        )
        #expect(closeReceipt.cancelledActionIDs.isEmpty)
        #expect(closeReceipt.tooLateActionIDs.isEmpty)
    }

    @Test("broker rejects mismatched accessibility preparation before commit")
    func mismatchedAccessibilityPreparationFailsClosed() async throws {
        let accessibility = FakeAccessibilityAdapter(preparationID: "")
        let context = try await makeBrokerTestContext(accessibility: accessibility)
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let request = try makeActionRequest(
            context: context,
            actionID: "action-preparation-mismatch",
            idempotencyKey: "idem-preparation-mismatch",
            approvalID: "approval-preparation-mismatch"
        )

        let execution = try await context.broker.performAction(request)
        let terminal = try #require(await collectEvents(execution).last)

        #expect(terminal.state == .failed)
        #expect(
            terminal.receipt?.failure?.code
                == "accessibility_preparation_mismatch"
        )
        #expect(terminal.receipt?.sideEffectCommitted == false)
        #expect(await accessibility.pressCount() == 0)
    }

    @Test("artifact namespaces reject overlong values")
    func overlongArtifactNamespaceFailsClosed() async throws {
        let context = makeBareBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }

        await expectBrokerError(
            .invalidRequest(
                "Computer Use artifact namespace must contain only letters, numbers, underscores, or hyphens."
            )
        ) {
            try await context.broker.openSession(
                OpenComputerUseSessionRequest(
                    ownerID: "operator-namespace",
                    runID: "run-namespace",
                    allowedBundleIdentifiers: ["io.melix.fixture"],
                    artifactNamespace: String(repeating: "a", count: 65)
                )
            )
        }
    }

    @Test("accepted cancellation before commit prevents every side effect and is idempotent")
    func acceptedCancellationPreventsCommit() async throws {
        let inspectionRelease = TestLatch()
        let accessibility = FakeAccessibilityAdapter(inspectionRelease: inspectionRelease)
        let context = try await makeBrokerTestContext(accessibility: accessibility)
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let request = try makeActionRequest(
            context: context,
            actionID: "action-cancel",
            idempotencyKey: "idem-cancel",
            approvalID: "approval-cancel"
        )
        let execution = try await context.broker.performAction(request)
        await accessibility.inspectionStarted.wait()

        let cancellation = CancelComputerActionRequest(
            sessionID: context.session.sessionID,
            capability: context.session.capability,
            actionID: request.actionID,
            cancellationID: "cancel-1",
            reason: "operator stopped the run"
        )
        let firstReceipt = await context.broker.cancelAction(cancellation)
        let repeatedReceipt = await context.broker.cancelAction(cancellation)
        await inspectionRelease.signal()
        let events = await collectEvents(execution)
        let pressCount = await accessibility.pressCount()

        #expect(firstReceipt.disposition == .accepted)
        #expect(repeatedReceipt == firstReceipt)
        #expect(events.filter(\.isTerminal).count == 1)
        #expect(events.last?.state == .cancelled)
        #expect(events.last?.receipt?.sideEffectCommitted == false)
        #expect(pressCount == 0)
        let metrics = await context.broker.metricsSnapshot()
        #expect(metrics.values["computer.cancel_accepted_count"] == 1)
    }

    @Test("cancellation after the actor commit transition is explicitly too late")
    func cancellationAfterCommitIsTooLate() async throws {
        let pressRelease = TestLatch()
        let accessibility = FakeAccessibilityAdapter(pressRelease: pressRelease)
        let context = try await makeBrokerTestContext(accessibility: accessibility)
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let request = try makeActionRequest(
            context: context,
            actionID: "action-late",
            idempotencyKey: "idem-late",
            approvalID: "approval-late"
        )
        let execution = try await context.broker.performAction(request)
        await accessibility.pressStarted.wait()

        let receipt = await context.broker.cancelAction(
            CancelComputerActionRequest(
                sessionID: context.session.sessionID,
                capability: context.session.capability,
                actionID: request.actionID,
                cancellationID: "cancel-late",
                reason: "late stop"
            )
        )
        await pressRelease.signal()
        let events = await collectEvents(execution)
        let pressCount = await accessibility.pressCount()

        #expect(receipt.disposition == .tooLate)
        #expect(events.filter(\.isTerminal).count == 1)
        #expect(events.last?.state == .completed)
        #expect(events.last?.receipt?.sideEffectCommitted == true)
        #expect(pressCount == 1)
    }

    @Test("idempotency returns the same execution and never consumes approval twice")
    func idempotencyReturnsExistingExecution() async throws {
        let pressRelease = TestLatch()
        let accessibility = FakeAccessibilityAdapter(pressRelease: pressRelease)
        let context = try await makeBrokerTestContext(accessibility: accessibility)
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let request = try makeActionRequest(
            context: context,
            actionID: "action-idempotent",
            idempotencyKey: "idem-stable",
            approvalID: "approval-idempotent"
        )
        let firstExecution = try await context.broker.performAction(request)
        let firstCollector = Task { await collectEvents(firstExecution) }
        await accessibility.pressStarted.wait()
        let repeatedExecution = try await context.broker.performAction(request)
        let repeatedCollector = Task { await collectEvents(repeatedExecution) }
        await pressRelease.signal()
        let firstEvents = await firstCollector.value
        let repeatedEvents = await repeatedCollector.value
        let pressCount = await accessibility.pressCount()

        #expect(firstExecution.actionID == repeatedExecution.actionID)
        #expect(firstEvents.filter(\.isTerminal).count == 1)
        #expect(repeatedEvents.filter(\.isTerminal).count == 1)
        #expect(firstEvents.last?.receipt == repeatedEvents.last?.receipt)
        #expect(pressCount == 1)
    }

    @Test("one action identifier cannot be rebound to a different idempotency key")
    func actionIdentifierCannotBeRebound() async throws {
        let pressRelease = TestLatch()
        let accessibility = FakeAccessibilityAdapter(pressRelease: pressRelease)
        let context = try await makeBrokerTestContext(accessibility: accessibility)
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let first = try makeActionRequest(
            context: context,
            actionID: "action-stable",
            idempotencyKey: "idem-first",
            approvalID: "approval-first"
        )
        let execution = try await context.broker.performAction(first)
        await accessibility.pressStarted.wait()

        let rebound = try makeActionRequest(
            context: context,
            actionID: "action-stable",
            idempotencyKey: "idem-second",
            approvalID: "approval-second"
        )
        await expectBrokerError(.idempotencyConflict) {
            try await context.broker.performAction(rebound)
        }

        await pressRelease.signal()
        let events = await collectEvents(execution)
        #expect(events.last?.state == .completed)
        #expect(await accessibility.pressCount() == 1)
    }

    @Test("semantic actions must name one enabled non-secure element from the latest frame")
    func semanticActionsBindToLatestFrameElements() async throws {
        for (label, element, expectedError) in [
            (
                "unobserved",
                ComputerFrameElement(
                    handleID: "other.element",
                    frameGeneration: 0,
                    role: "AXButton",
                    title: "Other",
                    isSecure: false,
                    isEnabled: true
                ),
                ComputerUseBrokerError.targetOutOfScope
            ),
            (
                "secure",
                ComputerFrameElement(
                    handleID: "fixture.increment",
                    frameGeneration: 0,
                    role: "AXButton",
                    title: "Increment",
                    isSecure: true,
                    isEnabled: true
                ),
                ComputerUseBrokerError.secureFieldRefused
            ),
            (
                "disabled",
                ComputerFrameElement(
                    handleID: "fixture.increment",
                    frameGeneration: 0,
                    role: "AXButton",
                    title: "Increment",
                    isSecure: false,
                    isEnabled: false
                ),
                ComputerUseBrokerError.invalidRequest(
                    "Computer Use refuses disabled elements."
                )
            ),
        ] {
            let accessibility = FakeAccessibilityAdapter(
                discoveredElements: [element]
            )
            let context = try await makeBrokerTestContext(
                accessibility: accessibility
            )
            defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
            let request = try makeActionRequest(
                context: context,
                actionID: "action-\(label)",
                idempotencyKey: "idem-\(label)",
                approvalID: "approval-\(label)"
            )

            await expectBrokerError(expectedError) {
                try await context.broker.performAction(request)
            }
            #expect(await accessibility.pressCount() == 0)
        }
    }

    @Test("scope and stale-frame checks fail before adapter execution")
    func scopeAndStaleFrameAreRefused() async throws {
        let context = try await makeBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let outOfScopeTarget = ComputerWindowTarget(
            bundleIdentifier: context.target.bundleIdentifier,
            processIdentifier: context.target.processIdentifier,
            processLaunchIdentity: context.target.processLaunchIdentity,
            windowID: 999,
            windowTitle: "Other"
        )
        await expectBrokerError(.targetOutOfScope) {
            try await context.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: context.session.sessionID,
                    capability: context.session.capability,
                    target: outOfScopeTarget
                )
            )
        }

        _ = try await context.broker.captureFrame(
            CaptureComputerFrameRequest(
                sessionID: context.session.sessionID,
                capability: context.session.capability,
                target: context.target
            )
        )
        let staleRequest = try makeActionRequest(
            context: context,
            frame: context.frame,
            actionID: "action-stale",
            idempotencyKey: "idem-stale",
            approvalID: "approval-stale"
        )
        await expectBrokerError(.staleFrame) {
            try await context.broker.performAction(staleRequest)
        }
        let pressCount = await context.accessibility.pressCount()
        #expect(pressCount == 0)
        let metrics = await context.broker.metricsSnapshot()
        #expect(metrics.values["computer.scope_refusal_count"] == 1)
        #expect(metrics.values["computer.stale_frame_refusal_count"] == 1)
    }

    @Test("approval is single-use even when a new action carries a matching new digest")
    func approvalCannotBeReplayed() async throws {
        let context = try await makeBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let firstRequest = try makeActionRequest(
            context: context,
            actionID: "action-first",
            idempotencyKey: "idem-first",
            approvalID: "approval-single-use"
        )
        let firstExecution = try await context.broker.performAction(firstRequest)
        let firstEvents = await collectEvents(firstExecution)
        let afterFrame = try #require(firstEvents.last?.receipt?.afterFrame)
        let replayRequest = try makeActionRequest(
            context: context,
            frame: afterFrame,
            actionID: "action-replay",
            idempotencyKey: "idem-replay",
            approvalID: "approval-single-use"
        )

        await expectBrokerError(.approvalReplay) {
            try await context.broker.performAction(replayRequest)
        }
        let pressCount = await context.accessibility.pressCount()
        #expect(pressCount == 1)
    }

    @Test("secure fields fail closed with evidence and no AX press")
    func secureFieldsAreRefused() async throws {
        let accessibility = FakeAccessibilityAdapter(secureField: true)
        let context = try await makeBrokerTestContext(accessibility: accessibility)
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let request = try makeActionRequest(
            context: context,
            actionID: "action-secure",
            idempotencyKey: "idem-secure",
            approvalID: "approval-secure"
        )

        let execution = try await context.broker.performAction(request)
        let events = await collectEvents(execution)
        let terminal = try #require(events.last)
        let pressCount = await accessibility.pressCount()

        #expect(terminal.state == .failed)
        #expect(terminal.receipt?.failure?.code == "secure_field_refused")
        #expect(terminal.receipt?.sideEffectCommitted == false)
        #expect(terminal.receipt?.evidenceArtifact != nil)
        #expect(pressCount == 0)
        let metrics = await context.broker.metricsSnapshot()
        #expect(metrics.values["computer.secure_field_refusal_count"] == 1)
    }

    @Test("capability, approval expiry, digest, and closed-session guards fail closed")
    func admissionGuardsFailClosed() async throws {
        let context = try await makeBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        await expectBrokerError(.invalidSessionCapability) {
            try await context.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: context.session.sessionID,
                    capability: ComputerUseSessionCapability(rawValue: "wrong"),
                    target: context.target
                )
            )
        }

        let expired = try makeActionRequest(
            context: context,
            actionID: "action-expired",
            idempotencyKey: "idem-expired",
            approvalID: "approval-expired",
            approvalExpiryOffset: -1
        )
        await expectBrokerError(.approvalExpired) {
            try await context.broker.performAction(expired)
        }

        let valid = try makeActionRequest(
            context: context,
            actionID: "action-digest",
            idempotencyKey: "idem-digest",
            approvalID: "approval-digest"
        )
        let mismatched = PerformComputerActionRequest(
            sessionID: valid.sessionID,
            capability: valid.capability,
            actionID: valid.actionID,
            idempotencyKey: valid.idempotencyKey,
            target: valid.target,
            expectedFrameID: valid.expectedFrameID,
            expectedFrameGeneration: valid.expectedFrameGeneration,
            action: valid.action,
            approval: ComputerUseApprovalGrant(
                approvalID: valid.approval.approvalID,
                actionDigest: "wrong-digest",
                policyRevision: valid.approval.policyRevision,
                approvedByActorID: valid.approval.approvedByActorID,
                approvedAt: valid.approval.approvedAt,
                expiresAt: valid.approval.expiresAt
            )
        )
        await expectBrokerError(.approvalDigestMismatch) {
            try await context.broker.performAction(mismatched)
        }

        _ = try await context.broker.closeSession(
            CloseComputerUseSessionRequest(
                sessionID: context.session.sessionID,
                capability: context.session.capability
            )
        )
        await expectBrokerError(.sessionClosed) {
            try await context.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: context.session.sessionID,
                    capability: context.session.capability,
                    target: context.target
                )
            )
        }
    }

    @Test("session cancellation closes idle sessions and is idempotent")
    func sessionCancellationClosesIdleSession() async throws {
        let context = try await makeBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let request = CancelComputerUseSessionRequest(
            sessionID: context.session.sessionID,
            capability: context.session.capability,
            cancellationID: "cancel-session-idle-1",
            reason: "operator stopped the run"
        )

        let first = await context.broker.cancelSession(request)
        let repeated = await context.broker.cancelSession(request)

        #expect(first.disposition == .accepted)
        #expect(first.cancelledActionIDs.isEmpty)
        #expect(first.tooLateActionIDs.isEmpty)
        #expect(repeated == first)
        await expectBrokerError(.sessionClosed) {
            try await context.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: context.session.sessionID,
                    capability: context.session.capability,
                    target: context.target
                )
            )
        }
    }

    @Test("adapter protocol defaults preserve bounded fail-closed behavior")
    func adapterProtocolDefaultsAreTyped() async throws {
        let frameCapture = DefaultListFrameCaptureAdapter()
        #expect(try await frameCapture.listTargets().isEmpty)

        let target = ComputerWindowTarget(
            bundleIdentifier: "io.melix.fixture",
            processIdentifier: 42,
            processLaunchIdentity: "fixture-launch",
            windowID: 7,
            windowTitle: "Fixture"
        )
        let element = AccessibilityElementTarget(
            accessibilityIdentifier: "fixture.button",
            title: "Continue",
            role: "AXButton"
        )
        let request = AdapterAccessibilityRequest(
            target: target,
            element: element
        )

        let successful = DefaultCommitAccessibilityAdapter(shouldFail: false)
        let successfulPreparation = try await successful.preparePress(request)
        #expect(
            await successful.commitPress(successfulPreparation) == .committed
        )

        let failing = DefaultCommitAccessibilityAdapter(shouldFail: true)
        let failingPreparation = try await failing.preparePress(request)
        #expect(
            await failing.commitPress(failingPreparation)
                == .indeterminate("default commit failed")
        )
    }
}

private struct DefaultListFrameCaptureAdapter: FrameCaptureAdapter {
    let adapterKind = "test.default-list"

    func permissionState() async -> ComputerUsePermissionState { .granted }

    func capture(
        _ request: AdapterFrameCaptureRequest
    ) async throws -> ComputerFrameObservation {
        _ = request
        throw DefaultAdapterTestError.failure
    }
}

private struct DefaultCommitAccessibilityAdapter: AccessibilityAdapter {
    let adapterKind = "test.default-commit"
    let shouldFail: Bool

    func permissionState() async -> ComputerUsePermissionState { .granted }

    func inspect(
        _ request: AdapterAccessibilityRequest
    ) async throws -> AccessibilityElementSnapshot {
        AccessibilityElementSnapshot(
            target: request.target,
            element: request.element,
            resolvedRole: "AXButton",
            resolvedSubrole: "",
            resolvedTitle: request.element.title,
            supportedActions: ["AXPress"],
            isSecureField: false
        )
    }

    func press(_ request: AdapterAccessibilityRequest) async throws {
        _ = request
        if shouldFail {
            throw DefaultAdapterTestError.failure
        }
    }
}

private enum DefaultAdapterTestError: LocalizedError {
    case failure

    var errorDescription: String? { "default commit failed" }
}

func expectBrokerError<T>(
    _ expected: ComputerUseBrokerError,
    operation: () async throws -> T
) async {
    do {
        _ = try await operation()
        Issue.record("Expected ComputerUseBrokerError \(expected), but operation succeeded.")
    } catch let error as ComputerUseBrokerError {
        #expect(error == expected)
    } catch {
        Issue.record("Expected ComputerUseBrokerError, received \(error).")
    }
}
