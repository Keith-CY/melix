import Foundation

public actor DefaultComputerUseBroker: ComputerUseBroker {
    private struct ActionRecord {
        let request: PerformComputerActionRequest
        let actionDigest: String
        let beforeFrame: ComputerFrameObservation
        let artifactDirectory: URL
        let startedAt: Date
        let startedUptimeNanoseconds: UInt64
        var state: ComputerActionState
        var nextSequence: UInt64
        var events: [ComputerActionEvent]
        var subscribers: [AsyncStream<ComputerActionEvent>.Continuation]
        var preparation: PreparedAccessibilityPress?
        var elementSnapshot: AccessibilityElementSnapshot?
        var preflightArtifact: ComputerArtifactReference?
        var commitIntentArtifact: ComputerArtifactReference?
        var afterFrame: ComputerFrameObservation?
        var sideEffectCommitted: Bool
        var terminalReceipt: ComputerActionReceipt?
        var cancellationReceipts: [String: ComputerActionCancellationReceipt]
    }

    private struct SessionRecord {
        let session: ComputerUseSession
        let artifactDirectory: URL
        var closed: Bool
        var lastActivityAt: Date
        var nextFrameGeneration: UInt64
        var frameCount: Int
        var actionCount: Int
        var artifactByteCount: Int
        var recordedArtifactDigests: [String: String]
        var latestFrame: ComputerFrameObservation?
        var consumedApprovalIDs: Set<String>
        var actionIDByIdempotencyKey: [String: String]
        var actions: [String: ActionRecord]
        var cancellationReceipts: [String: ComputerUseSessionCancellationReceipt]
    }

    private let frameCapture: any FrameCaptureAdapter
    private let accessibility: any AccessibilityAdapter
    private let evidenceSink: any ComputerUseEvidenceSink
    private let actionJournal: any ComputerUseActionJournal
    private let clock: any ComputerUseClock
    private let identityGenerator: any ComputerUseIdentityGenerator
    private let artifactRoot: URL
    private var sessions: [String: SessionRecord] = [:]
    private var metricValues: [String: Double] = [
        "computer.capture_ms": 0,
        "computer.capture_count": 0,
        "computer.action_ack_ms": 0,
        "computer.action_count": 0,
        "computer.stale_frame_refusal_count": 0,
        "computer.scope_refusal_count": 0,
        "computer.secure_field_refusal_count": 0,
        "computer.cancel_propagation_ms": 0,
        "computer.cancel_accepted_count": 0,
        "computer.terminal_duplicate_event_count": 0,
    ]

    public init(
        frameCapture: any FrameCaptureAdapter,
        accessibility: any AccessibilityAdapter,
        evidenceSink: any ComputerUseEvidenceSink = FileComputerUseEvidenceSink(),
        actionJournal: any ComputerUseActionJournal = FileComputerUseActionJournal(),
        clock: any ComputerUseClock = SystemComputerUseClock(),
        identityGenerator: any ComputerUseIdentityGenerator = UUIDComputerUseIdentityGenerator(),
        artifactRoot: URL
    ) {
        self.frameCapture = frameCapture
        self.accessibility = accessibility
        self.evidenceSink = evidenceSink
        self.actionJournal = actionJournal
        self.clock = clock
        self.identityGenerator = identityGenerator
        self.artifactRoot = artifactRoot.standardizedFileURL
    }

    public func permissions() async -> ComputerUsePermissionSnapshot {
        async let screenCaptureState = frameCapture.permissionState()
        async let accessibilityState = accessibility.permissionState()
        return await ComputerUsePermissionSnapshot(
            screenCapture: screenCaptureState,
            accessibility: accessibilityState
        )
    }

    public func listTargets() async throws -> [ComputerWindowTarget] {
        try await frameCapture.listTargets()
    }

    public func openSession(
        _ request: OpenComputerUseSessionRequest
    ) async throws -> ComputerUseSession {
        let ownerID = request.ownerID.trimmingCharacters(in: .whitespacesAndNewlines)
        let runID = request.runID.trimmingCharacters(in: .whitespacesAndNewlines)
        let namespace = request.artifactNamespace.trimmingCharacters(in: .whitespacesAndNewlines)
        let bundles = Set(
            request.allowedBundleIdentifiers
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
        )
        guard !ownerID.isEmpty else {
            throw ComputerUseBrokerError.invalidRequest("Computer Use ownerID must be non-empty.")
        }
        guard !runID.isEmpty else {
            throw ComputerUseBrokerError.invalidRequest("Computer Use runID must be non-empty.")
        }
        guard !bundles.isEmpty else {
            throw ComputerUseBrokerError.invalidRequest(
                "Computer Use session requires at least one allowed bundle identifier."
            )
        }
        guard isValidArtifactNamespace(namespace) else {
            throw ComputerUseBrokerError.invalidRequest(
                "Computer Use artifact namespace must contain only letters, numbers, underscores, or hyphens."
            )
        }
        guard request.limits.maximumFrameCount > 0,
              request.limits.maximumActionCount > 0
        else {
            throw ComputerUseBrokerError.invalidRequest(
                "Computer Use frame and action budgets must be positive."
            )
        }
        guard request.limits.maximumFrameCount <= 64,
              request.limits.maximumActionCount <= 32
        else {
            throw ComputerUseBrokerError.invalidRequest(
                "Computer Use frame and action budgets exceed the supported bounds."
            )
        }
        guard 1...(64 * 1_024 * 1_024) ~= request.limits.maximumArtifactBytes else {
            throw ComputerUseBrokerError.invalidRequest(
                "Computer Use artifact-byte budget must be between 1 and 67108864 bytes."
            )
        }
        guard request.limits.idleTimeoutSeconds >= 1,
              request.limits.idleTimeoutSeconds <= 300,
              request.limits.idleTimeoutSeconds.isFinite
        else {
            throw ComputerUseBrokerError.invalidRequest(
                "Computer Use idle timeout must be between 1 and 300 seconds."
            )
        }
        let now = clock.now()
        if let deadline = request.limits.absoluteDeadline, deadline <= now {
            throw ComputerUseBrokerError.sessionExpired
        }

        let sessionID = identityGenerator.nextID(prefix: "computer-session")
        let capability = ComputerUseSessionCapability(
            rawValue: identityGenerator.nextID(prefix: "computer-capability")
        )
        let session = ComputerUseSession(
            sessionID: sessionID,
            ownerID: ownerID,
            runID: runID,
            capability: capability,
            allowedBundleIdentifiers: bundles,
            allowedWindowIDs: request.allowedWindowIDs,
            createdAt: now,
            limits: request.limits
        )
        let directory = artifactRoot
            .appendingPathComponent(namespace, isDirectory: true)
            .appendingPathComponent(sessionID, isDirectory: true)
            .standardizedFileURL
        guard directory.path.hasPrefix(artifactRoot.path + "/") else {
            throw ComputerUseBrokerError.invalidRequest("Computer Use artifact root escaped its boundary.")
        }
        do {
            try ComputerUseArtifactSecurity.ensurePrivateDirectory(
                directory.deletingLastPathComponent()
            )
            try ComputerUseArtifactSecurity.ensurePrivateDirectory(directory)
        } catch {
            throw ComputerUseBrokerError.evidenceFailure(error.localizedDescription)
        }
        sessions[sessionID] = SessionRecord(
            session: session,
            artifactDirectory: directory,
            closed: false,
            lastActivityAt: now,
            nextFrameGeneration: 1,
            frameCount: 0,
            actionCount: 0,
            artifactByteCount: 0,
            recordedArtifactDigests: [:],
            latestFrame: nil,
            consumedApprovalIDs: [],
            actionIDByIdempotencyKey: [:],
            actions: [:],
            cancellationReceipts: [:]
        )
        return session
    }

    public func captureFrame(
        _ request: CaptureComputerFrameRequest
    ) async throws -> ComputerFrameObservation {
        var session = try validatedSession(
            sessionID: request.sessionID,
            capability: request.capability,
            requireOpen: true
        )
        try validateTarget(request.target, in: session)
        guard session.frameCount < session.session.limits.maximumFrameCount else {
            throw ComputerUseBrokerError.frameBudgetExceeded
        }

        let generation = session.nextFrameGeneration
        let frameID = identityGenerator.nextID(prefix: "computer-frame")
        let capturedAt = clock.now()
        session.nextFrameGeneration += 1
        session.frameCount += 1
        session.lastActivityAt = capturedAt
        sessions[request.sessionID] = session
        let adapterRequest = AdapterFrameCaptureRequest(
            target: request.target,
            frameID: frameID,
            generation: generation,
            capturedAt: capturedAt,
            artifactDirectory: session.artifactDirectory
        )

        let started = DispatchTime.now().uptimeNanoseconds
        let capturedObservation: ComputerFrameObservation
        do {
            capturedObservation = try await frameCapture.capture(adapterRequest)
        } catch let error as ComputerUseBrokerError {
            throw error
        } catch {
            throw ComputerUseBrokerError.adapterFailure(error.localizedDescription)
        }
        recordDuration(
            name: "computer.capture_ms",
            countName: "computer.capture_count",
            startedAt: started
        )
        guard capturedObservation.frameID == frameID,
              capturedObservation.generation == generation,
              capturedObservation.target == request.target
        else {
            throw ComputerUseBrokerError.adapterFailure(
                "Frame adapter returned an observation for a different target or generation."
            )
        }
        do {
            session = try validatedSession(
                sessionID: request.sessionID,
                capability: request.capability,
                requireOpen: true,
                enforceIdleTimeout: false
            )
        } catch {
            discardArtifact(
                capturedObservation.artifact,
                within: session.artifactDirectory
            )
            throw error
        }
        try validateAndRecordArtifact(
            capturedObservation.artifact,
            within: session.artifactDirectory,
            sessionID: request.sessionID
        )
        let semanticElements: [ComputerFrameElement]
        do {
            semanticElements = try await accessibility.elements(
                for: request.target,
                frameGeneration: generation
            )
        } catch {
            semanticElements = []
        }
        let observation = ComputerFrameObservation(
            frameID: capturedObservation.frameID,
            generation: capturedObservation.generation,
            target: capturedObservation.target,
            artifact: capturedObservation.artifact,
            capturedAt: capturedObservation.capturedAt,
            redactionApplied: capturedObservation.redactionApplied,
            elements: semanticElements.isEmpty
                ? capturedObservation.elements
                : semanticElements
        )

        session = try validatedSession(
            sessionID: request.sessionID,
            capability: request.capability,
            requireOpen: true,
            enforceIdleTimeout: false
        )
        if session.latestFrame == nil || observation.generation > session.latestFrame!.generation {
            session.latestFrame = observation
        }
        session.lastActivityAt = clock.now()
        sessions[request.sessionID] = session
        return observation
    }

    public func performAction(
        _ request: PerformComputerActionRequest
    ) async throws -> ComputerActionExecution {
        guard !request.actionID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ComputerUseBrokerError.invalidRequest("Computer Use actionID must be non-empty.")
        }
        guard !request.idempotencyKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw ComputerUseBrokerError.invalidRequest("Computer Use idempotencyKey must be non-empty.")
        }
        var session = try validatedSession(
            sessionID: request.sessionID,
            capability: request.capability,
            requireOpen: true
        )
        try validateTarget(request.target, in: session)
        let actionDigest: String
        do {
            actionDigest = try ComputerActionDigest.compute(for: request)
        } catch {
            throw ComputerUseBrokerError.invalidRequest(
                "Computer Use action could not be deterministically encoded."
            )
        }

        if let existingActionID = session.actionIDByIdempotencyKey[request.idempotencyKey],
           let existing = session.actions[existingActionID]
        {
            guard existing.actionDigest == actionDigest else {
                throw ComputerUseBrokerError.idempotencyConflict
            }
            return subscribe(to: existingActionID, in: request.sessionID)
        }
        if let existing = session.actions[request.actionID] {
            guard existing.request.idempotencyKey == request.idempotencyKey,
                  existing.actionDigest == actionDigest
            else {
                throw ComputerUseBrokerError.idempotencyConflict
            }
            return subscribe(to: request.actionID, in: request.sessionID)
        }

        guard let frame = session.latestFrame else {
            throw ComputerUseBrokerError.frameRequired
        }
        guard frame.frameID == request.expectedFrameID,
              frame.generation == request.expectedFrameGeneration,
              frame.target == request.target
        else {
            incrementMetric("computer.stale_frame_refusal_count")
            throw ComputerUseBrokerError.staleFrame
        }
        try validateActionElement(request.action, against: frame)
        guard session.actionCount < session.session.limits.maximumActionCount else {
            throw ComputerUseBrokerError.actionBudgetExceeded
        }
        let now = clock.now()
        if let deadline = request.deadline, deadline <= now {
            throw ComputerUseBrokerError.invalidRequest("Computer Use action deadline expired.")
        }
        guard request.approval.actionDigest == actionDigest else {
            throw ComputerUseBrokerError.approvalDigestMismatch
        }
        guard request.approval.expiresAt > now,
              request.approval.approvedAt <= now,
              request.approval.expiresAt > request.approval.approvedAt,
              !request.approval.approvalID.isEmpty,
              !request.approval.policyRevision.isEmpty,
              !request.approval.approvedByActorID.isEmpty
        else {
            throw ComputerUseBrokerError.approvalExpired
        }
        guard !session.consumedApprovalIDs.contains(request.approval.approvalID) else {
            throw ComputerUseBrokerError.approvalReplay
        }

        let queuedEvent = ComputerActionEvent(
            sequence: 1,
            state: .queued,
            occurredAt: now,
            message: "Action admitted and queued."
        )
        let actionRecord = ActionRecord(
            request: request,
            actionDigest: actionDigest,
            beforeFrame: frame,
            artifactDirectory: session.artifactDirectory,
            startedAt: now,
            startedUptimeNanoseconds: DispatchTime.now().uptimeNanoseconds,
            state: .queued,
            nextSequence: 2,
            events: [queuedEvent],
            subscribers: [],
            preparation: nil,
            elementSnapshot: nil,
            preflightArtifact: nil,
            commitIntentArtifact: nil,
            afterFrame: nil,
            sideEffectCommitted: false,
            terminalReceipt: nil,
            cancellationReceipts: [:]
        )
        session.consumedApprovalIDs.insert(request.approval.approvalID)
        session.actionCount += 1
        session.lastActivityAt = now
        session.actionIDByIdempotencyKey[request.idempotencyKey] = request.actionID
        session.actions[request.actionID] = actionRecord
        sessions[request.sessionID] = session
        incrementMetric("computer.action_count")

        let execution = subscribe(to: request.actionID, in: request.sessionID)
        Task {
            await self.driveAction(sessionID: request.sessionID, actionID: request.actionID)
        }
        return execution
    }

    public func cancelAction(
        _ request: CancelComputerActionRequest
    ) async -> ComputerActionCancellationReceipt {
        let started = DispatchTime.now().uptimeNanoseconds
        let now = clock.now()
        guard var session = sessions[request.sessionID] else {
            return ComputerActionCancellationReceipt(
                actionID: request.actionID,
                cancellationID: request.cancellationID,
                disposition: .notFound,
                requestedAt: now,
                terminalReceipt: nil
            )
        }
        guard session.session.capability == request.capability else {
            return ComputerActionCancellationReceipt(
                actionID: request.actionID,
                cancellationID: request.cancellationID,
                disposition: .scopeMismatch,
                requestedAt: now,
                terminalReceipt: nil
            )
        }
        guard var action = session.actions[request.actionID] else {
            return ComputerActionCancellationReceipt(
                actionID: request.actionID,
                cancellationID: request.cancellationID,
                disposition: .notFound,
                requestedAt: now,
                terminalReceipt: nil
            )
        }
        if let existing = action.cancellationReceipts[request.cancellationID] {
            return existing
        }

        let receipt: ComputerActionCancellationReceipt
        if action.state.isTerminal {
            receipt = ComputerActionCancellationReceipt(
                actionID: request.actionID,
                cancellationID: request.cancellationID,
                disposition: .alreadyTerminal,
                requestedAt: now,
                terminalReceipt: action.terminalReceipt
            )
        } else if action.state == .committing {
            receipt = ComputerActionCancellationReceipt(
                actionID: request.actionID,
                cancellationID: request.cancellationID,
                disposition: .tooLate,
                requestedAt: now,
                terminalReceipt: nil
            )
        } else {
            let terminal = finishAction(
                sessionID: request.sessionID,
                actionID: request.actionID,
                state: .cancelled,
                failure: ComputerUseFailure(
                    code: "cancelled",
                    message: sanitizedCancellationReason(request.reason)
                )
            )
            receipt = ComputerActionCancellationReceipt(
                actionID: request.actionID,
                cancellationID: request.cancellationID,
                disposition: .accepted,
                requestedAt: now,
                terminalReceipt: terminal
            )
            incrementMetric("computer.cancel_accepted_count")
            session = sessions[request.sessionID] ?? session
            action = session.actions[request.actionID] ?? action
        }
        action.cancellationReceipts[request.cancellationID] = receipt
        session.actions[request.actionID] = action
        sessions[request.sessionID] = session
        metricValues["computer.cancel_propagation_ms"] = elapsedMilliseconds(since: started)
        return receipt
    }

    public func cancelSession(
        _ request: CancelComputerUseSessionRequest
    ) async -> ComputerUseSessionCancellationReceipt {
        let now = clock.now()
        guard var session = sessions[request.sessionID] else {
            return ComputerUseSessionCancellationReceipt(
                sessionID: request.sessionID,
                cancellationID: request.cancellationID,
                disposition: .notFound,
                cancelledAt: now,
                cancelledActionIDs: [],
                tooLateActionIDs: []
            )
        }
        guard session.session.capability == request.capability else {
            return ComputerUseSessionCancellationReceipt(
                sessionID: request.sessionID,
                cancellationID: request.cancellationID,
                disposition: .scopeMismatch,
                cancelledAt: now,
                cancelledActionIDs: [],
                tooLateActionIDs: []
            )
        }
        if let existing = session.cancellationReceipts[request.cancellationID] {
            return existing
        }
        guard !request.cancellationID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return ComputerUseSessionCancellationReceipt(
                sessionID: request.sessionID,
                cancellationID: request.cancellationID,
                disposition: .scopeMismatch,
                cancelledAt: now,
                cancelledActionIDs: [],
                tooLateActionIDs: []
            )
        }
        if session.closed {
            let receipt = ComputerUseSessionCancellationReceipt(
                sessionID: request.sessionID,
                cancellationID: request.cancellationID,
                disposition: .alreadyTerminal,
                cancelledAt: now,
                cancelledActionIDs: [],
                tooLateActionIDs: []
            )
            session.cancellationReceipts[request.cancellationID] = receipt
            sessions[request.sessionID] = session
            return receipt
        }

        session.closed = true
        sessions[request.sessionID] = session
        var cancelled: [String] = []
        var tooLate: [String] = []
        for actionID in session.actions.keys.sorted() {
            guard let state = sessions[request.sessionID]?.actions[actionID]?.state,
                  !state.isTerminal
            else {
                continue
            }
            if state == .committing {
                tooLate.append(actionID)
            } else {
                _ = finishAction(
                    sessionID: request.sessionID,
                    actionID: actionID,
                    state: .cancelled,
                    failure: ComputerUseFailure(
                        code: "session_cancelled",
                        message: sanitizedCancellationReason(request.reason)
                    )
                )
                cancelled.append(actionID)
            }
        }
        let receipt = ComputerUseSessionCancellationReceipt(
            sessionID: request.sessionID,
            cancellationID: request.cancellationID,
            disposition: .accepted,
            cancelledAt: now,
            cancelledActionIDs: cancelled,
            tooLateActionIDs: tooLate
        )
        session = sessions[request.sessionID] ?? session
        session.cancellationReceipts[request.cancellationID] = receipt
        sessions[request.sessionID] = session
        return receipt
    }

    public func closeSession(
        _ request: CloseComputerUseSessionRequest
    ) async throws -> CloseComputerUseSessionReceipt {
        var session = try validatedSession(
            sessionID: request.sessionID,
            capability: request.capability,
            requireOpen: false,
            enforceDeadlines: false,
            enforceIdleTimeout: false
        )
        if session.closed {
            return CloseComputerUseSessionReceipt(
                sessionID: request.sessionID,
                closedAt: clock.now(),
                cancelledActionIDs: [],
                tooLateActionIDs: []
            )
        }
        session.closed = true
        sessions[request.sessionID] = session
        var cancelled: [String] = []
        var tooLate: [String] = []
        for actionID in session.actions.keys.sorted() {
            guard let state = sessions[request.sessionID]?.actions[actionID]?.state,
                  !state.isTerminal
            else {
                continue
            }
            if state == .committing {
                tooLate.append(actionID)
            } else {
                _ = finishAction(
                    sessionID: request.sessionID,
                    actionID: actionID,
                    state: .cancelled,
                    failure: ComputerUseFailure(
                        code: "session_closed",
                        message: "Session closed before the action commit point."
                    )
                )
                cancelled.append(actionID)
            }
        }
        return CloseComputerUseSessionReceipt(
            sessionID: request.sessionID,
            closedAt: clock.now(),
            cancelledActionIDs: cancelled,
            tooLateActionIDs: tooLate
        )
    }

    public func metricsSnapshot() async -> ComputerUseMetricsSnapshot {
        ComputerUseMetricsSnapshot(values: metricValues)
    }
}

private extension DefaultComputerUseBroker {
    func driveAction(sessionID: String, actionID: String) async {
        guard let request = beginPreflight(sessionID: sessionID, actionID: actionID) else {
            return
        }
        let accessibilityRequest: AdapterAccessibilityRequest
        switch request.action {
        case let .press(action):
            accessibilityRequest = AdapterAccessibilityRequest(
                target: request.target,
                element: action.element
            )
        }

        let preparation: PreparedAccessibilityPress
        do {
            preparation = try await accessibility.preparePress(accessibilityRequest)
        } catch {
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "accessibility_inspection_failed",
                message: error.localizedDescription,
                sideEffectCommitted: false
            )
            return
        }
        guard acceptPreflight(
            preparation,
            sessionID: sessionID,
            actionID: actionID
        ) else {
            return
        }

        await Task.yield()
        guard beginCommit(sessionID: sessionID, actionID: actionID) else {
            return
        }
        switch await accessibility.commitPress(preparation) {
        case .committed:
            guard markCommitted(sessionID: sessionID, actionID: actionID) else {
                return
            }
        case let .rejected(error):
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "accessibility_commit_rejected",
                message: error.localizedDescription,
                sideEffectCommitted: false
            )
            return
        case let .indeterminate(message):
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "accessibility_press_failed",
                message: message,
                sideEffectCommitted: true
            )
            return
        }

        guard let action = sessions[sessionID]?.actions[actionID] else {
            return
        }
        do {
            let afterFrame = try await captureFrame(
                CaptureComputerFrameRequest(
                    sessionID: sessionID,
                    capability: action.request.capability,
                    target: action.request.target
                )
            )
            recordAfterFrame(afterFrame, sessionID: sessionID, actionID: actionID)
            _ = finishAction(
                sessionID: sessionID,
                actionID: actionID,
                state: .completed,
                failure: nil
            )
        } catch {
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "post_action_capture_failed",
                message: error.localizedDescription,
                sideEffectCommitted: true
            )
        }
    }

    func validateActionElement(
        _ action: ComputerAction,
        against frame: ComputerFrameObservation
    ) throws {
        let locator: AccessibilityElementTarget
        switch action {
        case let .press(press):
            locator = press.element
        }
        let matches = frame.elements.filter { element in
            element.frameGeneration == frame.generation
                && (
                    locator.accessibilityIdentifier.isEmpty
                        || element.handleID == locator.accessibilityIdentifier
                )
                && (locator.title.isEmpty || element.title == locator.title)
                && (locator.role.isEmpty || element.role == locator.role)
        }
        guard matches.count == 1, let element = matches.first else {
            incrementMetric("computer.scope_refusal_count")
            throw ComputerUseBrokerError.targetOutOfScope
        }
        guard !element.isSecure else {
            incrementMetric("computer.secure_field_refusal_count")
            throw ComputerUseBrokerError.secureFieldRefused
        }
        guard element.isEnabled else {
            throw ComputerUseBrokerError.invalidRequest(
                "Computer Use refuses disabled elements."
            )
        }
    }

    func beginPreflight(
        sessionID: String,
        actionID: String
    ) -> PerformComputerActionRequest? {
        guard var session = sessions[sessionID],
              var action = session.actions[actionID],
              action.state == .queued,
              !session.closed
        else {
            return nil
        }
        action.state = .preflighting
        appendEvent(
            to: &action,
            state: .preflighting,
            message: "Accessibility target preflight started."
        )
        session.actions[actionID] = action
        sessions[sessionID] = session
        return action.request
    }

    func acceptPreflight(
        _ preparation: PreparedAccessibilityPress,
        sessionID: String,
        actionID: String
    ) -> Bool {
        guard let session = sessions[sessionID],
              let action = session.actions[actionID],
              action.state == .preflighting,
              !session.closed
        else {
            return false
        }
        let snapshot = preparation.snapshot
        let expectedElement: AccessibilityElementTarget
        switch action.request.action {
        case let .press(press):
            expectedElement = press.element
        }
        guard !preparation.preparationID.isEmpty,
              preparation.request == AdapterAccessibilityRequest(
                  target: action.request.target,
                  element: expectedElement
              ),
              snapshot.element == expectedElement
        else {
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "accessibility_preparation_mismatch",
                message: "Accessibility preparation did not match the admitted action.",
                sideEffectCommitted: false
            )
            return false
        }
        guard snapshot.target == action.request.target else {
            incrementMetric("computer.scope_refusal_count")
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "accessibility_target_mismatch",
                message: "Accessibility adapter resolved a target outside the admitted action scope.",
                sideEffectCommitted: false
            )
            return false
        }
        guard !snapshot.isSecureField else {
            incrementMetric("computer.secure_field_refusal_count")
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "secure_field_refused",
                message: ComputerUseBrokerError.secureFieldRefused.localizedDescription,
                sideEffectCommitted: false,
                elementSnapshot: snapshot
            )
            return false
        }
        guard snapshot.supportedActions.contains("AXPress") else {
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "ax_press_unsupported",
                message: "Accessibility element does not support AXPress.",
                sideEffectCommitted: false,
                elementSnapshot: snapshot
            )
            return false
        }
        let preflightArtifact: ComputerArtifactReference
        do {
            preflightArtifact = try recordBoundary(
                phase: .preflightPrepared,
                preparation: preparation,
                action: action,
                sessionID: sessionID
            )
        } catch {
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "preflight_persistence_failed",
                message: error.localizedDescription,
                sideEffectCommitted: false,
                elementSnapshot: snapshot
            )
            return false
        }
        guard var refreshedSession = sessions[sessionID],
              var refreshedAction = refreshedSession.actions[actionID],
              refreshedAction.state == .preflighting,
              !refreshedSession.closed
        else {
            return false
        }
        refreshedAction.preparation = preparation
        refreshedAction.elementSnapshot = snapshot
        refreshedAction.preflightArtifact = preflightArtifact
        refreshedAction.state = .readyToCommit
        appendEvent(
            to: &refreshedAction,
            state: .readyToCommit,
            message: "Target checks passed and durable preflight evidence committed."
        )
        refreshedSession.actions[actionID] = refreshedAction
        sessions[sessionID] = refreshedSession
        return true
    }

    func beginCommit(sessionID: String, actionID: String) -> Bool {
        guard let session = sessions[sessionID],
              let action = session.actions[actionID],
              action.state == .readyToCommit,
              !session.closed
        else {
            return false
        }
        guard let currentFrame = session.latestFrame,
              currentFrame.frameID == action.request.expectedFrameID,
              currentFrame.generation == action.request.expectedFrameGeneration,
              currentFrame.target == action.request.target
        else {
            incrementMetric("computer.stale_frame_refusal_count")
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "stale_frame_before_commit",
                message: "The admitted frame became stale during action preflight.",
                sideEffectCommitted: false
            )
            return false
        }
        let now = clock.now()
        if action.request.approval.expiresAt <= now
            || action.request.deadline.map({ $0 <= now }) == true
            || session.session.limits.absoluteDeadline.map({ $0 <= now }) == true
        {
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "action_expired_before_commit",
                message: "The session, action, or approval expired during action preflight.",
                sideEffectCommitted: false
            )
            return false
        }
        guard let preparation = action.preparation else {
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "accessibility_preparation_missing",
                message: "Accessibility commit requires a durable preflight preparation.",
                sideEffectCommitted: false
            )
            return false
        }
        let commitIntentArtifact: ComputerArtifactReference
        do {
            commitIntentArtifact = try recordBoundary(
                phase: .commitIntent,
                preparation: preparation,
                action: action,
                sessionID: sessionID
            )
        } catch {
            _ = failAction(
                sessionID: sessionID,
                actionID: actionID,
                code: "commit_intent_persistence_failed",
                message: error.localizedDescription,
                sideEffectCommitted: false
            )
            return false
        }
        guard var refreshedSession = sessions[sessionID],
              var refreshedAction = refreshedSession.actions[actionID],
              refreshedAction.state == .readyToCommit,
              !refreshedSession.closed
        else {
            return false
        }
        refreshedAction.commitIntentArtifact = commitIntentArtifact
        refreshedAction.state = .committing
        appendEvent(
            to: &refreshedAction,
            state: .committing,
            message: "Durable commit intent recorded; cancellation can no longer be accepted."
        )
        refreshedSession.actions[actionID] = refreshedAction
        sessions[sessionID] = refreshedSession
        return true
    }

    private func recordBoundary(
        phase: ComputerActionBoundaryPhase,
        preparation: PreparedAccessibilityPress,
        action: ActionRecord,
        sessionID: String
    ) throws -> ComputerArtifactReference {
        let record = ComputerActionBoundaryRecord(
            phase: phase,
            sessionID: sessionID,
            actionID: action.request.actionID,
            idempotencyKey: action.request.idempotencyKey,
            actionDigest: action.actionDigest,
            target: action.request.target,
            expectedFrameID: action.request.expectedFrameID,
            expectedFrameGeneration: action.request.expectedFrameGeneration,
            approvalID: action.request.approval.approvalID,
            policyRevision: action.request.approval.policyRevision,
            adapterKind: accessibility.adapterKind,
            preparationID: preparation.preparationID,
            elementSnapshot: preparation.snapshot,
            recordedAt: clock.now()
        )
        let artifact = try actionJournal.record(
            record,
            in: action.artifactDirectory
        )
        do {
            try validateAndRecordArtifact(
                artifact,
                within: action.artifactDirectory,
                sessionID: sessionID
            )
        } catch {
            discardArtifact(artifact, within: action.artifactDirectory)
            throw error
        }
        return artifact
    }

    func markCommitted(sessionID: String, actionID: String) -> Bool {
        guard var session = sessions[sessionID],
              var action = session.actions[actionID],
              action.state == .committing
        else {
            return false
        }
        action.sideEffectCommitted = true
        appendEvent(
            to: &action,
            state: .committing,
            message: "Accessibility action committed."
        )
        session.actions[actionID] = action
        sessions[sessionID] = session
        return true
    }

    func recordAfterFrame(
        _ frame: ComputerFrameObservation,
        sessionID: String,
        actionID: String
    ) {
        guard var session = sessions[sessionID], var action = session.actions[actionID] else {
            return
        }
        action.afterFrame = frame
        session.actions[actionID] = action
        sessions[sessionID] = session
    }

    @discardableResult
    func failAction(
        sessionID: String,
        actionID: String,
        code: String,
        message: String,
        sideEffectCommitted: Bool,
        elementSnapshot: AccessibilityElementSnapshot? = nil
    ) -> ComputerActionReceipt? {
        if let elementSnapshot {
            guard var session = sessions[sessionID], var action = session.actions[actionID] else {
                return nil
            }
            action.elementSnapshot = elementSnapshot
            session.actions[actionID] = action
            sessions[sessionID] = session
        }
        return finishAction(
            sessionID: sessionID,
            actionID: actionID,
            state: .failed,
            failure: ComputerUseFailure(
                code: code,
                message: sanitizedFailureMessage(message),
                sideEffectCommitted: sideEffectCommitted
            ),
            forcedSideEffectCommitted: sideEffectCommitted
        )
    }

    @discardableResult
    func finishAction(
        sessionID: String,
        actionID: String,
        state: ComputerActionState,
        failure: ComputerUseFailure?,
        forcedSideEffectCommitted: Bool? = nil
    ) -> ComputerActionReceipt? {
        guard state.isTerminal,
              var session = sessions[sessionID],
              var action = session.actions[actionID]
        else {
            return nil
        }
        if let terminal = action.terminalReceipt {
            incrementMetric("computer.terminal_duplicate_event_count")
            return terminal
        }
        let finishedAt = clock.now()
        let duration = elapsedMilliseconds(since: action.startedUptimeNanoseconds)
        var receipt = ComputerActionReceipt(
            sessionID: sessionID,
            actionID: actionID,
            idempotencyKey: action.request.idempotencyKey,
            state: state,
            target: action.request.target,
            actionDigest: action.actionDigest,
            approvalID: action.request.approval.approvalID,
            policyRevision: action.request.approval.policyRevision,
            adapterKind: accessibility.adapterKind,
            sideEffectCommitted: forcedSideEffectCommitted ?? action.sideEffectCommitted,
            beforeFrame: action.beforeFrame,
            afterFrame: action.afterFrame,
            elementSnapshot: action.elementSnapshot,
            startedAt: action.startedAt,
            finishedAt: finishedAt,
            durationMilliseconds: duration,
            failure: failure,
            boundaryArtifacts: [
                action.preflightArtifact,
                action.commitIntentArtifact,
            ].compactMap { $0 }
        )
        do {
            let artifact = try evidenceSink.record(receipt, in: action.artifactDirectory)
            try validateAndRecordArtifact(
                artifact,
                within: action.artifactDirectory,
                sessionID: sessionID
            )
            receipt = receipt.withEvidenceArtifact(artifact)
            session = sessions[sessionID] ?? session
        } catch {
            receipt = ComputerActionReceipt(
                sessionID: receipt.sessionID,
                actionID: receipt.actionID,
                idempotencyKey: receipt.idempotencyKey,
                state: state == .completed ? .failed : state,
                target: receipt.target,
                actionDigest: receipt.actionDigest,
                approvalID: receipt.approvalID,
                policyRevision: receipt.policyRevision,
                adapterKind: receipt.adapterKind,
                sideEffectCommitted: receipt.sideEffectCommitted,
                beforeFrame: receipt.beforeFrame,
                afterFrame: receipt.afterFrame,
                elementSnapshot: receipt.elementSnapshot,
                startedAt: receipt.startedAt,
                finishedAt: receipt.finishedAt,
                durationMilliseconds: receipt.durationMilliseconds,
                failure: ComputerUseFailure(
                    code: "evidence_persistence_failed",
                    message: sanitizedFailureMessage(error.localizedDescription),
                    sideEffectCommitted: receipt.sideEffectCommitted
                ),
                boundaryArtifacts: receipt.boundaryArtifacts
            )
        }
        action.state = receipt.state
        action.terminalReceipt = receipt
        appendEvent(
            to: &action,
            state: receipt.state,
            message: receipt.failure?.message ?? "Action completed.",
            receipt: receipt
        )
        for continuation in action.subscribers {
            continuation.finish()
        }
        action.subscribers.removeAll()
        session.lastActivityAt = finishedAt
        session.actions[actionID] = action
        sessions[sessionID] = session
        metricValues["computer.action_ack_ms"] = duration
        return receipt
    }

    func validateAndRecordArtifact(
        _ artifact: ComputerArtifactReference,
        within directory: URL,
        sessionID: String
    ) throws {
        let root = directory.standardizedFileURL
        let artifactURL = URL(
            fileURLWithPath: artifact.path
        ).standardizedFileURL
        guard artifactURL.path.hasPrefix(root.path + "/"),
              FileManager.default.fileExists(atPath: artifactURL.path)
        else {
            throw ComputerUseBrokerError.evidenceFailure(
                "Computer Use artifact escaped its session directory."
            )
        }
        let resourceValues = try artifactURL.resourceValues(
            forKeys: [.isRegularFileKey, .isSymbolicLinkKey]
        )
        guard resourceValues.isRegularFile == true,
              resourceValues.isSymbolicLink != true
        else {
            throw ComputerUseBrokerError.evidenceFailure(
                "Computer Use artifact must be a regular non-symlink file."
            )
        }
        let attributes = try FileManager.default.attributesOfItem(
            atPath: artifactURL.path
        )
        let byteCount = (attributes[.size] as? NSNumber)?.intValue ?? -1
        guard byteCount >= 0,
              byteCount == artifact.byteCount
        else {
            throw ComputerUseBrokerError.evidenceFailure(
                "Computer Use artifact size did not match its bounded receipt."
            )
        }
        guard var session = sessions[sessionID] else {
            throw ComputerUseBrokerError.sessionNotFound
        }
        let previouslyRecordedDigest = session.recordedArtifactDigests[
            artifactURL.path
        ]
        if let previouslyRecordedDigest,
           previouslyRecordedDigest != artifact.sha256 {
            throw ComputerUseBrokerError.evidenceFailure(
                "Computer Use artifact path was reused with different content."
            )
        }
        if previouslyRecordedDigest == nil,
           byteCount > session.session.limits.maximumArtifactBytes
                - session.artifactByteCount
        {
            try? FileManager.default.removeItem(at: artifactURL)
            throw ComputerUseBrokerError.artifactBudgetExceeded
        }
        let data = try Data(contentsOf: artifactURL)
        guard sha256Hex(data) == artifact.sha256 else {
            throw ComputerUseBrokerError.evidenceFailure(
                "Computer Use artifact digest did not match its receipt."
            )
        }
        try ComputerUseArtifactSecurity.protectPrivateFile(artifactURL)
        if previouslyRecordedDigest == nil {
            session.artifactByteCount += byteCount
            session.recordedArtifactDigests[artifactURL.path] = artifact.sha256
            sessions[sessionID] = session
        }
    }

    func discardArtifact(
        _ artifact: ComputerArtifactReference,
        within directory: URL
    ) {
        let root = directory.standardizedFileURL.path
        let artifactURL = URL(fileURLWithPath: artifact.path).standardizedFileURL
        guard artifactURL.path.hasPrefix(root + "/") else {
            return
        }
        try? FileManager.default.removeItem(at: artifactURL)
    }

    func subscribe(to actionID: String, in sessionID: String) -> ComputerActionExecution {
        let pair = AsyncStream<ComputerActionEvent>.makeStream(bufferingPolicy: .unbounded)
        guard var session = sessions[sessionID], var action = session.actions[actionID] else {
            pair.continuation.finish()
            return ComputerActionExecution(actionID: actionID, events: pair.stream)
        }
        for event in action.events {
            pair.continuation.yield(event)
        }
        if action.state.isTerminal {
            pair.continuation.finish()
        } else {
            action.subscribers.append(pair.continuation)
            session.actions[actionID] = action
            sessions[sessionID] = session
        }
        return ComputerActionExecution(actionID: actionID, events: pair.stream)
    }

    private func appendEvent(
        to action: inout ActionRecord,
        state: ComputerActionState,
        message: String,
        receipt: ComputerActionReceipt? = nil
    ) {
        let event = ComputerActionEvent(
            sequence: action.nextSequence,
            state: state,
            occurredAt: clock.now(),
            message: message,
            receipt: receipt
        )
        action.nextSequence += 1
        action.events.append(event)
        for continuation in action.subscribers {
            continuation.yield(event)
        }
    }

    private func validatedSession(
        sessionID: String,
        capability: ComputerUseSessionCapability,
        requireOpen: Bool,
        enforceDeadlines: Bool = true,
        enforceIdleTimeout: Bool = true
    ) throws -> SessionRecord {
        guard let session = sessions[sessionID] else {
            throw ComputerUseBrokerError.sessionNotFound
        }
        guard session.session.capability == capability else {
            throw ComputerUseBrokerError.invalidSessionCapability
        }
        if requireOpen, session.closed {
            throw ComputerUseBrokerError.sessionClosed
        }
        if enforceDeadlines,
           let deadline = session.session.limits.absoluteDeadline,
           deadline <= clock.now() {
            throw ComputerUseBrokerError.sessionExpired
        }
        if enforceIdleTimeout,
           clock.now().timeIntervalSince(session.lastActivityAt)
            >= session.session.limits.idleTimeoutSeconds
        {
            throw ComputerUseBrokerError.sessionIdleExpired
        }
        return session
    }

    private func validateTarget(_ target: ComputerWindowTarget, in session: SessionRecord) throws {
        guard target.processIdentifier > 0,
              target.windowID > 0,
              !target.processLaunchIdentity.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              session.session.allowedBundleIdentifiers.contains(target.bundleIdentifier),
              (session.session.allowedWindowIDs.isEmpty
                  || session.session.allowedWindowIDs.contains(target.windowID))
        else {
            incrementMetric("computer.scope_refusal_count")
            throw ComputerUseBrokerError.targetOutOfScope
        }
    }

    func recordDuration(
        name: String,
        countName: String,
        startedAt: UInt64
    ) {
        let count = (metricValues[countName] ?? 0) + 1
        let previousAverage = metricValues[name] ?? 0
        metricValues[countName] = count
        metricValues[name] = previousAverage + (elapsedMilliseconds(since: startedAt) - previousAverage) / count
    }

    func incrementMetric(_ name: String) {
        metricValues[name, default: 0] += 1
    }
}

private func elapsedMilliseconds(since startedAt: UInt64) -> Double {
    let now = DispatchTime.now().uptimeNanoseconds
    guard now >= startedAt else {
        return 0
    }
    return Double(now - startedAt) / 1_000_000
}

private func isValidArtifactNamespace(_ namespace: String) -> Bool {
    guard !namespace.isEmpty, namespace.count <= 64 else {
        return false
    }
    return namespace.range(
        of: "^[A-Za-z0-9][A-Za-z0-9_-]*$",
        options: .regularExpression
    ) != nil
}

private func sanitizedCancellationReason(_ reason: String) -> String {
    let trimmed = reason.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty {
        return "Action cancelled before the commit point."
    }
    return String(trimmed.prefix(256))
}

private func sanitizedFailureMessage(_ message: String) -> String {
    let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines)
    return String((trimmed.isEmpty ? "Computer Use action failed." : trimmed).prefix(512))
}
