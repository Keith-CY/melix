import ComputerUseBrokerCore
import CryptoKit
import Foundation
import Testing

@Suite("Computer Use Broker failures and boundaries", .serialized)
struct BrokerFailureAndBoundaryTests {
    @Test("permission snapshot comes from production seams rather than broker policy")
    func permissionSnapshotUsesAdapters() async {
        let bare = makeBareBrokerTestContext(
            frames: FakeFrameCaptureAdapter(permission: .notGranted),
            accessibility: FakeAccessibilityAdapter(permission: .unavailable)
        )
        defer { try? FileManager.default.removeItem(at: bare.artifactRoot) }
        let snapshot = await bare.broker.permissions()
        #expect(snapshot.screenCapture == .notGranted)
        #expect(snapshot.accessibility == .unavailable)
    }

    @Test("session creation validates identity, scope, namespace, budget, and deadline")
    func invalidSessionRequestsAreRejected() async {
        let bare = makeBareBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: bare.artifactRoot) }
        let validBundles: Set<String> = ["io.melix.fixture"]

        await expectBrokerError(.invalidRequest("Computer Use ownerID must be non-empty.")) {
            try await bare.broker.openSession(
                OpenComputerUseSessionRequest(
                    ownerID: " ", runID: "run", allowedBundleIdentifiers: validBundles,
                    artifactNamespace: "valid"
                )
            )
        }
        await expectBrokerError(.invalidRequest("Computer Use runID must be non-empty.")) {
            try await bare.broker.openSession(
                OpenComputerUseSessionRequest(
                    ownerID: "owner", runID: " ", allowedBundleIdentifiers: validBundles,
                    artifactNamespace: "valid"
                )
            )
        }
        await expectBrokerError(
            .invalidRequest("Computer Use session requires at least one allowed bundle identifier.")
        ) {
            try await bare.broker.openSession(
                OpenComputerUseSessionRequest(
                    ownerID: "owner", runID: "run", allowedBundleIdentifiers: [],
                    artifactNamespace: "valid"
                )
            )
        }
        await expectBrokerError(
            .invalidRequest(
                "Computer Use artifact namespace must contain only letters, numbers, underscores, or hyphens."
            )
        ) {
            try await bare.broker.openSession(
                OpenComputerUseSessionRequest(
                    ownerID: "owner", runID: "run", allowedBundleIdentifiers: validBundles,
                    artifactNamespace: "../escape"
                )
            )
        }
        await expectBrokerError(
            .invalidRequest("Computer Use frame and action budgets must be positive.")
        ) {
            try await bare.broker.openSession(
                OpenComputerUseSessionRequest(
                    ownerID: "owner", runID: "run", allowedBundleIdentifiers: validBundles,
                    artifactNamespace: "valid",
                    limits: ComputerUseSessionLimits(maximumFrameCount: 0, maximumActionCount: 1)
                )
            )
        }
        await expectBrokerError(.sessionExpired) {
            try await bare.broker.openSession(
                OpenComputerUseSessionRequest(
                    ownerID: "owner", runID: "run", allowedBundleIdentifiers: validBundles,
                    artifactNamespace: "valid",
                    limits: ComputerUseSessionLimits(
                        absoluteDeadline: bare.clock.now().addingTimeInterval(-1)
                    )
                )
            )
        }
        await expectBrokerError(
            .invalidRequest(
                "Computer Use artifact-byte budget must be between 1 and 67108864 bytes."
            )
        ) {
            try await bare.broker.openSession(
                OpenComputerUseSessionRequest(
                    ownerID: "owner", runID: "run", allowedBundleIdentifiers: validBundles,
                    artifactNamespace: "valid",
                    limits: ComputerUseSessionLimits(maximumArtifactBytes: 0)
                )
            )
        }
        await expectBrokerError(
            .invalidRequest(
                "Computer Use idle timeout must be between 1 and 300 seconds."
            )
        ) {
            try await bare.broker.openSession(
                OpenComputerUseSessionRequest(
                    ownerID: "owner", runID: "run", allowedBundleIdentifiers: validBundles,
                    artifactNamespace: "valid",
                    limits: ComputerUseSessionLimits(idleTimeoutSeconds: 0)
                )
            )
        }
    }

    @Test("frame budgets and adapter failures remain typed")
    func captureFailuresRemainTyped() async throws {
        let budgetContext = try await makeBrokerTestContext(
            limits: ComputerUseSessionLimits(maximumFrameCount: 1, maximumActionCount: 1)
        )
        defer { try? FileManager.default.removeItem(at: budgetContext.artifactRoot) }
        await expectBrokerError(.frameBudgetExceeded) {
            try await budgetContext.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: budgetContext.session.sessionID,
                    capability: budgetContext.session.capability,
                    target: budgetContext.target
                )
            )
        }

        let mismatchFrames = FakeFrameCaptureAdapter(mismatchOnCaptureNumber: 2)
        let mismatchContext = try await makeBrokerTestContext(frames: mismatchFrames)
        defer { try? FileManager.default.removeItem(at: mismatchContext.artifactRoot) }
        await expectBrokerError(
            .adapterFailure("Frame adapter returned an observation for a different target or generation.")
        ) {
            try await mismatchContext.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: mismatchContext.session.sessionID,
                    capability: mismatchContext.session.capability,
                    target: mismatchContext.target
                )
            )
        }

        let genericFrames = FakeFrameCaptureAdapter(failOnCaptureNumber: 2)
        let genericContext = try await makeBrokerTestContext(frames: genericFrames)
        defer { try? FileManager.default.removeItem(at: genericContext.artifactRoot) }
        await expectBrokerError(.adapterFailure("fixture frame failure")) {
            try await genericContext.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: genericContext.session.sessionID,
                    capability: genericContext.session.capability,
                    target: genericContext.target
                )
            )
        }

        let typedFrames = FakeFrameCaptureAdapter(
            failOnCaptureNumber: 2,
            throwsBrokerError: true
        )
        let typedContext = try await makeBrokerTestContext(frames: typedFrames)
        defer { try? FileManager.default.removeItem(at: typedContext.artifactRoot) }
        await expectBrokerError(.permissionDenied("screen_capture")) {
            try await typedContext.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: typedContext.session.sessionID,
                    capability: typedContext.session.capability,
                    target: typedContext.target
                )
            )
        }
    }

    @Test("adapter inspection, target, action support, and press errors fail before false success")
    func accessibilityFailuresAreEvidenceBacked() async throws {
        let inspectionContext = try await makeBrokerTestContext(
            accessibility: FakeAccessibilityAdapter(inspectionErrorMessage: "inspect failed")
        )
        defer { try? FileManager.default.removeItem(at: inspectionContext.artifactRoot) }
        let inspectionEvents = await collectEvents(
            try await inspectionContext.broker.performAction(
                makeActionRequest(
                    context: inspectionContext,
                    actionID: "inspect-failure",
                    idempotencyKey: "inspect-failure",
                    approvalID: "inspect-failure"
                )
            )
        )
        #expect(inspectionEvents.last?.receipt?.failure?.code == "accessibility_inspection_failed")

        let unsupportedContext = try await makeBrokerTestContext(
            accessibility: FakeAccessibilityAdapter(actionNames: [])
        )
        defer { try? FileManager.default.removeItem(at: unsupportedContext.artifactRoot) }
        let unsupportedEvents = await collectEvents(
            try await unsupportedContext.broker.performAction(
                makeActionRequest(
                    context: unsupportedContext,
                    actionID: "unsupported",
                    idempotencyKey: "unsupported",
                    approvalID: "unsupported"
                )
            )
        )
        #expect(unsupportedEvents.last?.receipt?.failure?.code == "ax_press_unsupported")

        let mismatchedTarget = ComputerWindowTarget(
            bundleIdentifier: "io.melix.fixture",
            processIdentifier: 4242,
            processLaunchIdentity: "fixture-launch-1",
            windowID: 78,
            windowTitle: "Wrong"
        )
        let mismatchContext = try await makeBrokerTestContext(
            accessibility: FakeAccessibilityAdapter(resolvedTarget: mismatchedTarget)
        )
        defer { try? FileManager.default.removeItem(at: mismatchContext.artifactRoot) }
        let mismatchEvents = await collectEvents(
            try await mismatchContext.broker.performAction(
                makeActionRequest(
                    context: mismatchContext,
                    actionID: "target-mismatch",
                    idempotencyKey: "target-mismatch",
                    approvalID: "target-mismatch"
                )
            )
        )
        #expect(mismatchEvents.last?.receipt?.failure?.code == "accessibility_target_mismatch")

        let pressContext = try await makeBrokerTestContext(
            accessibility: FakeAccessibilityAdapter(pressErrorMessage: "press failed")
        )
        defer { try? FileManager.default.removeItem(at: pressContext.artifactRoot) }
        let pressEvents = await collectEvents(
            try await pressContext.broker.performAction(
                makeActionRequest(
                    context: pressContext,
                    actionID: "press-failure",
                    idempotencyKey: "press-failure",
                    approvalID: "press-failure"
                )
            )
        )
        #expect(pressEvents.last?.receipt?.failure?.code == "accessibility_press_failed")
        #expect(pressEvents.last?.receipt?.sideEffectCommitted == true)
    }

    @Test("accessibility side effects require durable preflight and commit-intent records")
    func accessibilityCommitBoundaryIsDurable() async throws {
        let context = try await makeBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let events = await collectEvents(
            try await context.broker.performAction(
                makeActionRequest(
                    context: context,
                    actionID: "durable-boundary",
                    idempotencyKey: "durable-boundary",
                    approvalID: "durable-boundary"
                )
            )
        )

        let receipt = try #require(events.last?.receipt)
        #expect(receipt.state == .completed)
        #expect(receipt.sideEffectCommitted)
        #expect(await context.accessibility.pressCount() == 1)
        let artifacts = try #require(receipt.boundaryArtifacts)
        #expect(artifacts.count == 2)

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let records = try artifacts.map { artifact in
            let data = try Data(contentsOf: URL(fileURLWithPath: artifact.path))
            #expect(SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined() == artifact.sha256)
            return try decoder.decode(ComputerActionBoundaryRecord.self, from: data)
        }
        #expect(records.map(\.phase) == [.preflightPrepared, .commitIntent])
        #expect(records.allSatisfy { $0.actionDigest == receipt.actionDigest })
        #expect(records.allSatisfy { $0.preparationID == records.first?.preparationID })
    }

    @Test("journal failures stop accessibility work before the side effect")
    func journalFailuresPreventAccessibilityCommit() async throws {
        let preflightContext = try await makeBrokerTestContext(
            actionJournal: FailingComputerUseActionJournal(failingPhase: .preflightPrepared)
        )
        defer { try? FileManager.default.removeItem(at: preflightContext.artifactRoot) }
        let preflightEvents = await collectEvents(
            try await preflightContext.broker.performAction(
                makeActionRequest(
                    context: preflightContext,
                    actionID: "preflight-journal-failure",
                    idempotencyKey: "preflight-journal-failure",
                    approvalID: "preflight-journal-failure"
                )
            )
        )
        #expect(preflightEvents.last?.receipt?.failure?.code == "preflight_persistence_failed")
        #expect(preflightEvents.last?.receipt?.sideEffectCommitted == false)
        #expect(await preflightContext.accessibility.pressCount() == 0)
        #expect(preflightEvents.last?.receipt?.boundaryArtifacts?.isEmpty == true)

        let commitContext = try await makeBrokerTestContext(
            actionJournal: FailingComputerUseActionJournal(failingPhase: .commitIntent)
        )
        defer { try? FileManager.default.removeItem(at: commitContext.artifactRoot) }
        let commitEvents = await collectEvents(
            try await commitContext.broker.performAction(
                makeActionRequest(
                    context: commitContext,
                    actionID: "commit-journal-failure",
                    idempotencyKey: "commit-journal-failure",
                    approvalID: "commit-journal-failure"
                )
            )
        )
        #expect(commitEvents.last?.receipt?.failure?.code == "commit_intent_persistence_failed")
        #expect(commitEvents.last?.receipt?.sideEffectCommitted == false)
        #expect(await commitContext.accessibility.pressCount() == 0)
        #expect(commitEvents.last?.receipt?.boundaryArtifacts?.count == 1)
    }

    @Test("commit-time accessibility revalidation can reject without claiming a side effect")
    func accessibilityCommitRejectionIsPreSideEffect() async throws {
        let context = try await makeBrokerTestContext(
            accessibility: FakeAccessibilityAdapter(
                commitRejection: .invalidRequest("fixture changed before commit")
            )
        )
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let events = await collectEvents(
            try await context.broker.performAction(
                makeActionRequest(
                    context: context,
                    actionID: "commit-rejected",
                    idempotencyKey: "commit-rejected",
                    approvalID: "commit-rejected"
                )
            )
        )
        #expect(events.last?.receipt?.failure?.code == "accessibility_commit_rejected")
        #expect(events.last?.receipt?.sideEffectCommitted == false)
        #expect(events.last?.receipt?.boundaryArtifacts?.count == 2)
        #expect(await context.accessibility.pressCount() == 0)
    }

    @Test("post-commit capture and evidence failures never masquerade as success")
    func committedEvidenceFailuresAreExplicit() async throws {
        let captureContext = try await makeBrokerTestContext(
            limits: ComputerUseSessionLimits(maximumFrameCount: 1, maximumActionCount: 1)
        )
        defer { try? FileManager.default.removeItem(at: captureContext.artifactRoot) }
        let captureEvents = await collectEvents(
            try await captureContext.broker.performAction(
                makeActionRequest(
                    context: captureContext,
                    actionID: "post-capture",
                    idempotencyKey: "post-capture",
                    approvalID: "post-capture"
                )
            )
        )
        #expect(captureEvents.last?.state == .failed)
        #expect(captureEvents.last?.receipt?.failure?.code == "post_action_capture_failed")
        #expect(captureEvents.last?.receipt?.sideEffectCommitted == true)

        let evidenceContext = try await makeBrokerTestContext(
            evidenceSink: FailingComputerUseEvidenceSink()
        )
        defer { try? FileManager.default.removeItem(at: evidenceContext.artifactRoot) }
        let evidenceEvents = await collectEvents(
            try await evidenceContext.broker.performAction(
                makeActionRequest(
                    context: evidenceContext,
                    actionID: "evidence-failure",
                    idempotencyKey: "evidence-failure",
                    approvalID: "evidence-failure"
                )
            )
        )
        #expect(evidenceEvents.last?.state == .failed)
        #expect(evidenceEvents.last?.receipt?.failure?.code == "evidence_persistence_failed")
        #expect(evidenceEvents.last?.receipt?.sideEffectCommitted == true)
    }

    @Test("cancel dispositions distinguish missing scope, missing action, and terminal work")
    func cancelDispositionsAreTyped() async throws {
        let context = try await makeBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let missingSession = await context.broker.cancelAction(
            CancelComputerActionRequest(
                sessionID: "missing",
                capability: context.session.capability,
                actionID: "missing",
                cancellationID: "cancel-missing-session",
                reason: ""
            )
        )
        #expect(missingSession.disposition == .notFound)
        let wrongScope = await context.broker.cancelAction(
            CancelComputerActionRequest(
                sessionID: context.session.sessionID,
                capability: ComputerUseSessionCapability(rawValue: "wrong"),
                actionID: "missing",
                cancellationID: "cancel-wrong-scope",
                reason: ""
            )
        )
        #expect(wrongScope.disposition == .scopeMismatch)
        let missingAction = await context.broker.cancelAction(
            CancelComputerActionRequest(
                sessionID: context.session.sessionID,
                capability: context.session.capability,
                actionID: "missing",
                cancellationID: "cancel-missing-action",
                reason: ""
            )
        )
        #expect(missingAction.disposition == .notFound)

        let request = try makeActionRequest(
            context: context,
            actionID: "finished-action",
            idempotencyKey: "finished-action",
            approvalID: "finished-action"
        )
        _ = await collectEvents(try await context.broker.performAction(request))
        let terminal = await context.broker.cancelAction(
            CancelComputerActionRequest(
                sessionID: context.session.sessionID,
                capability: context.session.capability,
                actionID: request.actionID,
                cancellationID: "cancel-terminal",
                reason: ""
            )
        )
        #expect(terminal.disposition == .alreadyTerminal)
        #expect(terminal.terminalReceipt?.state == .completed)

        let replayEvents = await collectEvents(
            try await context.broker.performAction(request)
        )
        #expect(replayEvents.last?.state == .completed)

        await expectBrokerError(.sessionNotFound) {
            try await context.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: "missing",
                    capability: context.session.capability,
                    target: context.target
                )
            )
        }
    }

    @Test("closing a session cancels pre-commit work and reports committing work as too late")
    func closeSessionLinearizesWithActions() async throws {
        let inspectionRelease = TestLatch()
        let preflightAccessibility = FakeAccessibilityAdapter(
            inspectionRelease: inspectionRelease
        )
        let preflightContext = try await makeBrokerTestContext(
            accessibility: preflightAccessibility
        )
        defer { try? FileManager.default.removeItem(at: preflightContext.artifactRoot) }
        let preflightRequest = try makeActionRequest(
            context: preflightContext,
            actionID: "close-preflight",
            idempotencyKey: "close-preflight",
            approvalID: "close-preflight"
        )
        let preflightExecution = try await preflightContext.broker.performAction(preflightRequest)
        await preflightAccessibility.inspectionStarted.wait()
        let preflightClose = try await preflightContext.broker.closeSession(
            CloseComputerUseSessionRequest(
                sessionID: preflightContext.session.sessionID,
                capability: preflightContext.session.capability
            )
        )
        await inspectionRelease.signal()
        let preflightEvents = await collectEvents(preflightExecution)
        #expect(preflightClose.cancelledActionIDs == [preflightRequest.actionID])
        #expect(preflightClose.tooLateActionIDs.isEmpty)
        #expect(preflightEvents.last?.state == .cancelled)
        let repeatedClose = try await preflightContext.broker.closeSession(
            CloseComputerUseSessionRequest(
                sessionID: preflightContext.session.sessionID,
                capability: preflightContext.session.capability
            )
        )
        #expect(repeatedClose.cancelledActionIDs.isEmpty)

        let pressRelease = TestLatch()
        let commitAccessibility = FakeAccessibilityAdapter(pressRelease: pressRelease)
        let commitContext = try await makeBrokerTestContext(accessibility: commitAccessibility)
        defer { try? FileManager.default.removeItem(at: commitContext.artifactRoot) }
        let commitRequest = try makeActionRequest(
            context: commitContext,
            actionID: "close-commit",
            idempotencyKey: "close-commit",
            approvalID: "close-commit"
        )
        let commitExecution = try await commitContext.broker.performAction(commitRequest)
        await commitAccessibility.pressStarted.wait()
        let commitClose = try await commitContext.broker.closeSession(
            CloseComputerUseSessionRequest(
                sessionID: commitContext.session.sessionID,
                capability: commitContext.session.capability
            )
        )
        await pressRelease.signal()
        let commitEvents = await collectEvents(commitExecution)
        #expect(commitClose.tooLateActionIDs == [commitRequest.actionID])
        #expect(commitEvents.last?.state == .failed)
        #expect(commitEvents.last?.receipt?.sideEffectCommitted == true)
    }

    @Test("frame and approval are revalidated immediately before the commit transition")
    func commitPreconditionsAreRevalidated() async throws {
        let staleRelease = TestLatch()
        let staleAccessibility = FakeAccessibilityAdapter(inspectionRelease: staleRelease)
        let staleContext = try await makeBrokerTestContext(accessibility: staleAccessibility)
        defer { try? FileManager.default.removeItem(at: staleContext.artifactRoot) }
        let staleRequest = try makeActionRequest(
            context: staleContext,
            actionID: "stale-at-commit",
            idempotencyKey: "stale-at-commit",
            approvalID: "stale-at-commit"
        )
        let staleExecution = try await staleContext.broker.performAction(staleRequest)
        await staleAccessibility.inspectionStarted.wait()
        _ = try await staleContext.broker.captureFrame(
            CaptureComputerFrameRequest(
                sessionID: staleContext.session.sessionID,
                capability: staleContext.session.capability,
                target: staleContext.target
            )
        )
        await staleRelease.signal()
        let staleEvents = await collectEvents(staleExecution)
        let stalePressCount = await staleAccessibility.pressCount()
        #expect(staleEvents.last?.receipt?.failure?.code == "stale_frame_before_commit")
        #expect(staleEvents.last?.receipt?.sideEffectCommitted == false)
        #expect(stalePressCount == 0)

        let expiryRelease = TestLatch()
        let expiryAccessibility = FakeAccessibilityAdapter(inspectionRelease: expiryRelease)
        let expiryContext = try await makeBrokerTestContext(accessibility: expiryAccessibility)
        defer { try? FileManager.default.removeItem(at: expiryContext.artifactRoot) }
        let expiryRequest = try makeActionRequest(
            context: expiryContext,
            actionID: "expiry-at-commit",
            idempotencyKey: "expiry-at-commit",
            approvalID: "expiry-at-commit",
            approvalExpiryOffset: 1
        )
        let expiryExecution = try await expiryContext.broker.performAction(expiryRequest)
        await expiryAccessibility.inspectionStarted.wait()
        expiryContext.clock.advance(by: 2)
        await expiryRelease.signal()
        let expiryEvents = await collectEvents(expiryExecution)
        let expiryPressCount = await expiryAccessibility.pressCount()
        #expect(expiryEvents.last?.receipt?.failure?.code == "action_expired_before_commit")
        #expect(expiryEvents.last?.receipt?.sideEffectCommitted == false)
        #expect(expiryPressCount == 0)
    }

    @Test("session expiry, missing frames, deadlines, budgets, and idempotency conflicts fail closed")
    func remainingAdmissionBoundariesFailClosed() async throws {
        let bare = makeBareBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: bare.artifactRoot) }
        let target = standardTarget()
        let noFrameSession = try await bare.broker.openSession(
            OpenComputerUseSessionRequest(
                ownerID: "operator",
                runID: "run",
                allowedBundleIdentifiers: [target.bundleIdentifier],
                allowedWindowIDs: [target.windowID],
                artifactNamespace: "no-frame"
            )
        )
        let action = ComputerAction.press(
            PressAccessibilityElementAction(
                element: AccessibilityElementTarget(title: "Increment", role: "AXButton")
            )
        )
        let digest = try ComputerActionDigest.compute(
            sessionID: noFrameSession.sessionID,
            actionID: "no-frame",
            idempotencyKey: "no-frame",
            target: target,
            expectedFrameID: "missing",
            expectedFrameGeneration: 1,
            action: action
        )
        let noFrameRequest = PerformComputerActionRequest(
            sessionID: noFrameSession.sessionID,
            capability: noFrameSession.capability,
            actionID: "no-frame",
            idempotencyKey: "no-frame",
            target: target,
            expectedFrameID: "missing",
            expectedFrameGeneration: 1,
            action: action,
            approval: ComputerUseApprovalGrant(
                approvalID: "no-frame",
                actionDigest: digest,
                policyRevision: "policy",
                approvedByActorID: "operator",
                approvedAt: bare.clock.now(),
                expiresAt: bare.clock.now().addingTimeInterval(60)
            )
        )
        await expectBrokerError(.frameRequired) {
            try await bare.broker.performAction(noFrameRequest)
        }

        let budgetContext = try await makeBrokerTestContext(
            limits: ComputerUseSessionLimits(maximumFrameCount: 4, maximumActionCount: 1)
        )
        defer { try? FileManager.default.removeItem(at: budgetContext.artifactRoot) }
        let first = try makeActionRequest(
            context: budgetContext,
            actionID: "budget-first",
            idempotencyKey: "budget-first",
            approvalID: "budget-first"
        )
        let firstEvents = await collectEvents(try await budgetContext.broker.performAction(first))
        let currentFrame = try #require(firstEvents.last?.receipt?.afterFrame)
        let second = try makeActionRequest(
            context: budgetContext,
            frame: currentFrame,
            actionID: "budget-second",
            idempotencyKey: "budget-second",
            approvalID: "budget-second"
        )
        await expectBrokerError(.actionBudgetExceeded) {
            try await budgetContext.broker.performAction(second)
        }

        let deadlineBase = try makeActionRequest(
            context: budgetContext,
            frame: currentFrame,
            actionID: "deadline",
            idempotencyKey: "deadline",
            approvalID: "deadline"
        )
        let expiredDeadline = PerformComputerActionRequest(
            sessionID: deadlineBase.sessionID,
            capability: deadlineBase.capability,
            actionID: deadlineBase.actionID,
            idempotencyKey: deadlineBase.idempotencyKey,
            target: deadlineBase.target,
            expectedFrameID: deadlineBase.expectedFrameID,
            expectedFrameGeneration: deadlineBase.expectedFrameGeneration,
            action: deadlineBase.action,
            approval: deadlineBase.approval,
            deadline: budgetContext.clock.now().addingTimeInterval(-1)
        )
        // Action budget is already exhausted, so use a fresh context for the deadline branch.
        let deadlineContext = try await makeBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: deadlineContext.artifactRoot) }
        let deadlineRequestBase = try makeActionRequest(
            context: deadlineContext,
            actionID: "deadline",
            idempotencyKey: "deadline",
            approvalID: "deadline"
        )
        let deadlineRequest = PerformComputerActionRequest(
            sessionID: deadlineRequestBase.sessionID,
            capability: deadlineRequestBase.capability,
            actionID: deadlineRequestBase.actionID,
            idempotencyKey: deadlineRequestBase.idempotencyKey,
            target: deadlineRequestBase.target,
            expectedFrameID: deadlineRequestBase.expectedFrameID,
            expectedFrameGeneration: deadlineRequestBase.expectedFrameGeneration,
            action: deadlineRequestBase.action,
            approval: deadlineRequestBase.approval,
            deadline: deadlineContext.clock.now().addingTimeInterval(-1)
        )
        _ = expiredDeadline
        await expectBrokerError(
            .invalidRequest("Computer Use action deadline expired.")
        ) {
            try await deadlineContext.broker.performAction(deadlineRequest)
        }

        let conflictRelease = TestLatch()
        let conflictAccessibility = FakeAccessibilityAdapter(pressRelease: conflictRelease)
        let conflictContext = try await makeBrokerTestContext(
            accessibility: conflictAccessibility
        )
        defer { try? FileManager.default.removeItem(at: conflictContext.artifactRoot) }
        let conflictFirst = try makeActionRequest(
            context: conflictContext,
            actionID: "conflict-first",
            idempotencyKey: "shared-key",
            approvalID: "conflict-first"
        )
        let conflictExecution = try await conflictContext.broker.performAction(conflictFirst)
        await conflictAccessibility.pressStarted.wait()
        let differentAction = ComputerAction.press(
            PressAccessibilityElementAction(
                element: AccessibilityElementTarget(title: "Different", role: "AXButton")
            )
        )
        let differentDigest = try ComputerActionDigest.compute(
            sessionID: conflictContext.session.sessionID,
            actionID: "conflict-second",
            idempotencyKey: "shared-key",
            target: conflictContext.target,
            expectedFrameID: conflictContext.frame.frameID,
            expectedFrameGeneration: conflictContext.frame.generation,
            action: differentAction
        )
        let conflictSecond = PerformComputerActionRequest(
            sessionID: conflictContext.session.sessionID,
            capability: conflictContext.session.capability,
            actionID: "conflict-second",
            idempotencyKey: "shared-key",
            target: conflictContext.target,
            expectedFrameID: conflictContext.frame.frameID,
            expectedFrameGeneration: conflictContext.frame.generation,
            action: differentAction,
            approval: ComputerUseApprovalGrant(
                approvalID: "conflict-second",
                actionDigest: differentDigest,
                policyRevision: "policy",
                approvedByActorID: "operator",
                approvedAt: conflictContext.clock.now(),
                expiresAt: conflictContext.clock.now().addingTimeInterval(60)
            )
        )
        await expectBrokerError(.idempotencyConflict) {
            try await conflictContext.broker.performAction(conflictSecond)
        }
        await conflictRelease.signal()
        _ = await collectEvents(conflictExecution)

        let expiryContext = try await makeBrokerTestContext(
            limits: ComputerUseSessionLimits(
                absoluteDeadline: Date(timeIntervalSince1970: 1_800_000_005)
            )
        )
        defer { try? FileManager.default.removeItem(at: expiryContext.artifactRoot) }
        expiryContext.clock.advance(by: 10)
        await expectBrokerError(.sessionExpired) {
            try await expiryContext.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: expiryContext.session.sessionID,
                    capability: expiryContext.session.capability,
                    target: expiryContext.target
                )
                )
            }
        }
    @Test("artifact bytes and idle time are enforced per session")
    func artifactAndIdleBudgetsAreEnforced() async throws {
        let artifactContext = try await makeBrokerTestContext(
            limits: ComputerUseSessionLimits(
                maximumArtifactBytes: 12,
                idleTimeoutSeconds: 60
            )
        )
        defer { try? FileManager.default.removeItem(at: artifactContext.artifactRoot) }
        await expectBrokerError(.artifactBudgetExceeded) {
            try await artifactContext.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: artifactContext.session.sessionID,
                    capability: artifactContext.session.capability,
                    target: artifactContext.target
                )
            )
        }

        let idleContext = try await makeBrokerTestContext(
            limits: ComputerUseSessionLimits(idleTimeoutSeconds: 5)
        )
        defer { try? FileManager.default.removeItem(at: idleContext.artifactRoot) }
        idleContext.clock.advance(by: 5)
        await expectBrokerError(.sessionIdleExpired) {
            try await idleContext.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: idleContext.session.sessionID,
                    capability: idleContext.session.capability,
                    target: idleContext.target
                )
            )
        }
    }

    @Test("upper session limits, filesystem roots, and action identifiers fail closed")
    func additionalAdmissionBoundariesFailClosed() async throws {
        let bare = makeBareBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: bare.artifactRoot) }
        let bundles: Set<String> = ["io.melix.fixture"]
        for limits in [
            ComputerUseSessionLimits(maximumFrameCount: 65),
            ComputerUseSessionLimits(maximumActionCount: 33),
            ComputerUseSessionLimits(maximumArtifactBytes: 64 * 1_024 * 1_024 + 1),
            ComputerUseSessionLimits(idleTimeoutSeconds: 301),
            ComputerUseSessionLimits(idleTimeoutSeconds: .infinity),
        ] {
            do {
                _ = try await bare.broker.openSession(
                    OpenComputerUseSessionRequest(
                        ownerID: "operator",
                        runID: "run",
                        allowedBundleIdentifiers: bundles,
                        artifactNamespace: "upper-bound",
                        limits: limits
                    )
                )
                Issue.record("Expected an upper-bound session refusal.")
            } catch let error as ComputerUseBrokerError {
                guard case .invalidRequest = error else {
                    Issue.record("Expected invalidRequest, received \(error).")
                    continue
                }
            } catch {
                Issue.record("Expected ComputerUseBrokerError, received \(error).")
            }
        }

        let slashRootBroker = DefaultComputerUseBroker(
            frameCapture: FakeFrameCaptureAdapter(),
            accessibility: FakeAccessibilityAdapter(),
            clock: bare.clock,
            identityGenerator: TestComputerUseIdentityGenerator(),
            artifactRoot: URL(fileURLWithPath: "/", isDirectory: true)
        )
        await expectBrokerError(
            .invalidRequest("Computer Use artifact root escaped its boundary.")
        ) {
            try await slashRootBroker.openSession(
                OpenComputerUseSessionRequest(
                    ownerID: "operator",
                    runID: "run",
                    allowedBundleIdentifiers: bundles,
                    artifactNamespace: "slash-root"
                )
            )
        }

        let fileRoot = bare.artifactRoot.appendingPathComponent("not-a-directory")
        try FileManager.default.createDirectory(
            at: bare.artifactRoot,
            withIntermediateDirectories: true
        )
        try Data("file-root".utf8).write(to: fileRoot)
        let fileRootBroker = DefaultComputerUseBroker(
            frameCapture: FakeFrameCaptureAdapter(),
            accessibility: FakeAccessibilityAdapter(),
            clock: bare.clock,
            identityGenerator: TestComputerUseIdentityGenerator(),
            artifactRoot: fileRoot
        )
        do {
            _ = try await fileRootBroker.openSession(
                OpenComputerUseSessionRequest(
                    ownerID: "operator",
                    runID: "run",
                    allowedBundleIdentifiers: bundles,
                    artifactNamespace: "file-root"
                )
            )
            Issue.record("Expected private artifact directory creation to fail.")
        } catch let error as ComputerUseBrokerError {
            guard case .evidenceFailure = error else {
                Issue.record("Expected evidenceFailure, received \(error).")
                return
            }
        }

        let context = try await makeBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        let base = try makeActionRequest(
            context: context,
            actionID: "valid-action",
            idempotencyKey: "valid-idempotency",
            approvalID: "valid-approval"
        )
        let blankActionID = PerformComputerActionRequest(
            sessionID: base.sessionID,
            capability: base.capability,
            actionID: " ",
            idempotencyKey: base.idempotencyKey,
            target: base.target,
            expectedFrameID: base.expectedFrameID,
            expectedFrameGeneration: base.expectedFrameGeneration,
            action: base.action,
            approval: base.approval
        )
        await expectBrokerError(
            .invalidRequest("Computer Use actionID must be non-empty.")
        ) {
            try await context.broker.performAction(blankActionID)
        }
        let blankIdempotency = PerformComputerActionRequest(
            sessionID: base.sessionID,
            capability: base.capability,
            actionID: base.actionID,
            idempotencyKey: " ",
            target: base.target,
            expectedFrameID: base.expectedFrameID,
            expectedFrameGeneration: base.expectedFrameGeneration,
            action: base.action,
            approval: base.approval
        )
        await expectBrokerError(
            .invalidRequest("Computer Use idempotencyKey must be non-empty.")
        ) {
            try await context.broker.performAction(blankIdempotency)
        }
    }

    @Test("session cancellation is typed for missing, wrong-scope, closed, preflight, and commit states")
    func sessionCancellationBoundariesAreTyped() async throws {
        let idle = try await makeBrokerTestContext()
        defer { try? FileManager.default.removeItem(at: idle.artifactRoot) }
        let missing = await idle.broker.cancelSession(
            CancelComputerUseSessionRequest(
                sessionID: "missing-session",
                capability: idle.session.capability,
                cancellationID: "cancel-session-missing",
                reason: "missing"
            )
        )
        #expect(missing.disposition == .notFound)
        let wrongScope = await idle.broker.cancelSession(
            CancelComputerUseSessionRequest(
                sessionID: idle.session.sessionID,
                capability: ComputerUseSessionCapability(rawValue: "wrong"),
                cancellationID: "cancel-session-wrong-scope",
                reason: "wrong scope"
            )
        )
        #expect(wrongScope.disposition == .scopeMismatch)
        let blankID = await idle.broker.cancelSession(
            CancelComputerUseSessionRequest(
                sessionID: idle.session.sessionID,
                capability: idle.session.capability,
                cancellationID: " ",
                reason: "blank"
            )
        )
        #expect(blankID.disposition == .scopeMismatch)
        _ = try await idle.broker.closeSession(
            CloseComputerUseSessionRequest(
                sessionID: idle.session.sessionID,
                capability: idle.session.capability
            )
        )
        let alreadyClosed = await idle.broker.cancelSession(
            CancelComputerUseSessionRequest(
                sessionID: idle.session.sessionID,
                capability: idle.session.capability,
                cancellationID: "cancel-session-closed",
                reason: "closed"
            )
        )
        #expect(alreadyClosed.disposition == .alreadyTerminal)

        let preflightRelease = TestLatch()
        let preflightAccessibility = FakeAccessibilityAdapter(
            inspectionRelease: preflightRelease
        )
        let preflight = try await makeBrokerTestContext(
            accessibility: preflightAccessibility
        )
        defer { try? FileManager.default.removeItem(at: preflight.artifactRoot) }
        let preflightRequest = try makeActionRequest(
            context: preflight,
            actionID: "session-cancel-preflight",
            idempotencyKey: "session-cancel-preflight",
            approvalID: "session-cancel-preflight"
        )
        let preflightExecution = try await preflight.broker.performAction(
            preflightRequest
        )
        await preflightAccessibility.inspectionStarted.wait()
        let preflightReceipt = await preflight.broker.cancelSession(
            CancelComputerUseSessionRequest(
                sessionID: preflight.session.sessionID,
                capability: preflight.session.capability,
                cancellationID: "cancel-session-preflight",
                reason: ""
            )
        )
        await preflightRelease.signal()
        #expect(preflightReceipt.cancelledActionIDs == [preflightRequest.actionID])
        #expect(preflightReceipt.tooLateActionIDs.isEmpty)
        #expect(await collectEvents(preflightExecution).last?.state == .cancelled)

        let commitRelease = TestLatch()
        let commitAccessibility = FakeAccessibilityAdapter(
            pressRelease: commitRelease
        )
        let committing = try await makeBrokerTestContext(
            accessibility: commitAccessibility
        )
        defer { try? FileManager.default.removeItem(at: committing.artifactRoot) }
        let commitRequest = try makeActionRequest(
            context: committing,
            actionID: "session-cancel-commit",
            idempotencyKey: "session-cancel-commit",
            approvalID: "session-cancel-commit"
        )
        let commitExecution = try await committing.broker.performAction(commitRequest)
        await commitAccessibility.pressStarted.wait()
        let commitReceipt = await committing.broker.cancelSession(
            CancelComputerUseSessionRequest(
                sessionID: committing.session.sessionID,
                capability: committing.session.capability,
                cancellationID: "cancel-session-commit",
                reason: "operator stopped"
            )
        )
        await commitRelease.signal()
        #expect(commitReceipt.cancelledActionIDs.isEmpty)
        #expect(commitReceipt.tooLateActionIDs == [commitRequest.actionID])
        #expect(await collectEvents(commitExecution).last?.receipt?.sideEffectCommitted == true)
    }

    @Test("capture completion rechecks cancellation and discards the produced artifact")
    func captureCancellationRaceDiscardsArtifact() async throws {
        let release = TestLatch()
        let frames = FakeFrameCaptureAdapter(captureRelease: release)
        let bare = makeBareBrokerTestContext(frames: frames)
        defer { try? FileManager.default.removeItem(at: bare.artifactRoot) }
        let target = standardTarget()
        let session = try await openBoundarySession(
            broker: bare.broker,
            target: target,
            namespace: "capture-cancel-race"
        )
        let capture = Task {
            try await bare.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: session.sessionID,
                    capability: session.capability,
                    target: target
                )
            )
        }
        await frames.captureStarted.wait()
        let cancellation = await bare.broker.cancelSession(
            CancelComputerUseSessionRequest(
                sessionID: session.sessionID,
                capability: session.capability,
                cancellationID: "cancel-session-capture-race",
                reason: "stop while capture is running"
            )
        )
        #expect(cancellation.disposition == .accepted)
        await release.signal()
        await expectBrokerError(.sessionClosed) {
            try await capture.value
        }
        let artifact = bare.artifactRoot
            .appendingPathComponent("capture-cancel-race")
            .appendingPathComponent(session.sessionID)
            .appendingPathComponent("fake-frame-1.bin")
        #expect(!FileManager.default.fileExists(atPath: artifact.path))
    }

    @Test("artifact receipts must stay regular, bounded, immutable, and digest-correct")
    func malformedArtifactReceiptsFailClosed() async throws {
        let target = standardTarget()
        let scenarios: [(BoundaryArtifactScenario, ComputerUseBrokerError)] = [
            (
                .missing,
                .evidenceFailure("Computer Use artifact escaped its session directory.")
            ),
            (
                .outside,
                .evidenceFailure("Computer Use artifact escaped its session directory.")
            ),
            (
                .directory,
                .evidenceFailure("Computer Use artifact must be a regular non-symlink file.")
            ),
            (
                .symbolicLink,
                .evidenceFailure("Computer Use artifact must be a regular non-symlink file.")
            ),
            (
                .sizeMismatch,
                .evidenceFailure("Computer Use artifact size did not match its bounded receipt.")
            ),
            (
                .digestMismatch,
                .evidenceFailure("Computer Use artifact digest did not match its receipt.")
            ),
        ]
        for (index, pair) in scenarios.enumerated() {
            let bare = makeBareBrokerTestContext(
                frames: BoundaryArtifactFrameAdapter(scenario: pair.0)
            )
            defer { try? FileManager.default.removeItem(at: bare.artifactRoot) }
            let session = try await openBoundarySession(
                broker: bare.broker,
                target: target,
                namespace: "artifact-boundary-\(index)"
            )
            await expectBrokerError(pair.1) {
                try await bare.broker.captureFrame(
                    CaptureComputerFrameRequest(
                        sessionID: session.sessionID,
                        capability: session.capability,
                        target: target
                    )
                )
            }
        }

        let reuse = makeBareBrokerTestContext(
            frames: BoundaryArtifactFrameAdapter(scenario: .reusedPath)
        )
        defer { try? FileManager.default.removeItem(at: reuse.artifactRoot) }
        let session = try await openBoundarySession(
            broker: reuse.broker,
            target: target,
            namespace: "artifact-reuse"
        )
        _ = try await reuse.broker.captureFrame(
            CaptureComputerFrameRequest(
                sessionID: session.sessionID,
                capability: session.capability,
                target: target
            )
        )
        await expectBrokerError(
            .evidenceFailure("Computer Use artifact path was reused with different content.")
        ) {
            try await reuse.broker.captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: session.sessionID,
                    capability: session.capability,
                    target: target
                )
            )
        }
    }

    @Test("default adapters, clocks, identifiers, and semantic discovery fallback are usable")
    func defaultRuntimeSeamsAreCovered() async throws {
        let target = standardTarget()
        let adapter = DefaultElementsAccessibilityAdapter()
        #expect(try await adapter.elements(for: target, frameGeneration: 1).isEmpty)
        let clock = SystemComputerUseClock()
        #expect(abs(clock.now().timeIntervalSinceNow) < 1)
        let generator = UUIDComputerUseIdentityGenerator()
        let generated = generator.nextID(prefix: "coverage")
        #expect(generated.hasPrefix("coverage-"))

        let context = try await makeBrokerTestContext(
            accessibility: FakeAccessibilityAdapter(
                elementsErrorMessage: "semantic enumeration unavailable"
            )
        )
        defer { try? FileManager.default.removeItem(at: context.artifactRoot) }
        #expect(context.frame.elements.isEmpty)
    }

}

private enum BoundaryArtifactScenario: Sendable {
    case missing
    case outside
    case directory
    case symbolicLink
    case sizeMismatch
    case digestMismatch
    case reusedPath
}

private actor BoundaryArtifactFrameAdapter: FrameCaptureAdapter {
    nonisolated let adapterKind = "test.boundary.artifact"
    private let scenario: BoundaryArtifactScenario

    init(scenario: BoundaryArtifactScenario) {
        self.scenario = scenario
    }

    func permissionState() async -> ComputerUsePermissionState { .granted }

    func capture(
        _ request: AdapterFrameCaptureRequest
    ) async throws -> ComputerFrameObservation {
        try FileManager.default.createDirectory(
            at: request.artifactDirectory,
            withIntermediateDirectories: true
        )
        let data = Data("boundary-frame-\(request.generation)".utf8)
        var url = request.artifactDirectory.appendingPathComponent(
            "boundary-\(request.generation).bin"
        )
        var byteCount = data.count
        var digest = testSHA256(data)
        switch scenario {
        case .missing:
            break
        case .outside:
            url = request.artifactDirectory
                .deletingLastPathComponent()
                .appendingPathComponent("outside-\(request.generation).bin")
            try data.write(to: url)
        case .directory:
            try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
            byteCount = 0
            digest = testSHA256(Data())
        case .symbolicLink:
            let target = request.artifactDirectory.appendingPathComponent(
                "symbolic-target-\(request.generation).bin"
            )
            try data.write(to: target)
            try FileManager.default.createSymbolicLink(
                atPath: url.path,
                withDestinationPath: target.path
            )
        case .sizeMismatch:
            try data.write(to: url)
            byteCount += 1
        case .digestMismatch:
            try data.write(to: url)
            digest = String(repeating: "0", count: 64)
        case .reusedPath:
            url = request.artifactDirectory.appendingPathComponent("reused.bin")
            try data.write(to: url)
        }
        return ComputerFrameObservation(
            frameID: request.frameID,
            generation: request.generation,
            target: request.target,
            artifact: ComputerArtifactReference(
                artifactID: "boundary-\(request.generation)",
                path: url.path,
                sha256: digest,
                byteCount: byteCount,
                mediaType: "application/octet-stream",
                adapterKind: adapterKind
            ),
            capturedAt: request.capturedAt
        )
    }
}

private struct DefaultElementsAccessibilityAdapter: AccessibilityAdapter {
    let adapterKind = "test.default-elements"

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

    func press(_: AdapterAccessibilityRequest) async throws {}
}

private func openBoundarySession(
    broker: DefaultComputerUseBroker,
    target: ComputerWindowTarget,
    namespace: String
) async throws -> ComputerUseSession {
    try await broker.openSession(
        OpenComputerUseSessionRequest(
            ownerID: "operator",
            runID: "run",
            allowedBundleIdentifiers: [target.bundleIdentifier],
            allowedWindowIDs: [target.windowID],
            artifactNamespace: namespace
        )
    )
}

private func testSHA256(_ data: Data) -> String {
    SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
}

private func standardTarget() -> ComputerWindowTarget {
    ComputerWindowTarget(
        bundleIdentifier: "io.melix.fixture",
        processIdentifier: 4242,
        processLaunchIdentity: "fixture-launch-1",
        windowID: 77,
        windowTitle: "Computer Use Fixture"
    )
}
