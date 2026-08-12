import Foundation

public enum ComputerUsePermissionState: String, Codable, Sendable, Equatable {
    case granted
    case notGranted
    case unavailable
}

public struct ComputerUsePermissionSnapshot: Codable, Sendable, Equatable {
    public let screenCapture: ComputerUsePermissionState
    public let accessibility: ComputerUsePermissionState

    public init(
        screenCapture: ComputerUsePermissionState,
        accessibility: ComputerUsePermissionState
    ) {
        self.screenCapture = screenCapture
        self.accessibility = accessibility
    }
}

public struct ComputerWindowTarget: Codable, Sendable, Hashable {
    public let bundleIdentifier: String
    public let processIdentifier: Int32
    public let processLaunchIdentity: String
    public let windowID: UInt32
    public let windowTitle: String
    public let applicationName: String

    public init(
        bundleIdentifier: String,
        processIdentifier: Int32,
        processLaunchIdentity: String,
        windowID: UInt32,
        windowTitle: String = "",
        applicationName: String = ""
    ) {
        self.bundleIdentifier = bundleIdentifier
        self.processIdentifier = processIdentifier
        self.processLaunchIdentity = processLaunchIdentity
        self.windowID = windowID
        self.windowTitle = windowTitle
        self.applicationName = applicationName
    }
}

public struct ComputerUseSessionLimits: Codable, Sendable, Equatable {
    public let maximumFrameCount: Int
    public let maximumActionCount: Int
    public let maximumArtifactBytes: Int
    public let idleTimeoutSeconds: TimeInterval
    public let absoluteDeadline: Date?

    public init(
        maximumFrameCount: Int = 32,
        maximumActionCount: Int = 16,
        maximumArtifactBytes: Int = 16 * 1_024 * 1_024,
        idleTimeoutSeconds: TimeInterval = 60,
        absoluteDeadline: Date? = nil
    ) {
        self.maximumFrameCount = maximumFrameCount
        self.maximumActionCount = maximumActionCount
        self.maximumArtifactBytes = maximumArtifactBytes
        self.idleTimeoutSeconds = idleTimeoutSeconds
        self.absoluteDeadline = absoluteDeadline
    }
}

public struct OpenComputerUseSessionRequest: Codable, Sendable, Equatable {
    public let ownerID: String
    public let runID: String
    public let allowedBundleIdentifiers: Set<String>
    public let allowedWindowIDs: Set<UInt32>
    public let artifactNamespace: String
    public let limits: ComputerUseSessionLimits

    public init(
        ownerID: String,
        runID: String,
        allowedBundleIdentifiers: Set<String>,
        allowedWindowIDs: Set<UInt32> = [],
        artifactNamespace: String,
        limits: ComputerUseSessionLimits = ComputerUseSessionLimits()
    ) {
        self.ownerID = ownerID
        self.runID = runID
        self.allowedBundleIdentifiers = allowedBundleIdentifiers
        self.allowedWindowIDs = allowedWindowIDs
        self.artifactNamespace = artifactNamespace
        self.limits = limits
    }
}

public struct ComputerUseSessionCapability: Codable, Sendable, Hashable {
    public let rawValue: String

    public init(rawValue: String) {
        self.rawValue = rawValue
    }
}

public struct ComputerUseSession: Codable, Sendable, Equatable {
    public let sessionID: String
    public let ownerID: String
    public let runID: String
    public let capability: ComputerUseSessionCapability
    public let allowedBundleIdentifiers: Set<String>
    public let allowedWindowIDs: Set<UInt32>
    public let createdAt: Date
    public let limits: ComputerUseSessionLimits

    public init(
        sessionID: String,
        ownerID: String,
        runID: String,
        capability: ComputerUseSessionCapability,
        allowedBundleIdentifiers: Set<String>,
        allowedWindowIDs: Set<UInt32>,
        createdAt: Date,
        limits: ComputerUseSessionLimits
    ) {
        self.sessionID = sessionID
        self.ownerID = ownerID
        self.runID = runID
        self.capability = capability
        self.allowedBundleIdentifiers = allowedBundleIdentifiers
        self.allowedWindowIDs = allowedWindowIDs
        self.createdAt = createdAt
        self.limits = limits
    }
}

public struct ComputerArtifactReference: Codable, Sendable, Equatable {
    public let artifactID: String
    public let path: String
    public let sha256: String
    public let byteCount: Int
    public let mediaType: String
    public let width: Int
    public let height: Int
    public let adapterKind: String

    public init(
        artifactID: String,
        path: String,
        sha256: String,
        byteCount: Int,
        mediaType: String,
        width: Int = 0,
        height: Int = 0,
        adapterKind: String
    ) {
        self.artifactID = artifactID
        self.path = path
        self.sha256 = sha256
        self.byteCount = byteCount
        self.mediaType = mediaType
        self.width = width
        self.height = height
        self.adapterKind = adapterKind
    }
}

public struct ComputerFrameObservation: Codable, Sendable, Equatable {
    public let frameID: String
    public let generation: UInt64
    public let target: ComputerWindowTarget
    public let artifact: ComputerArtifactReference
    public let capturedAt: Date
    public let redactionApplied: Bool
    public let elements: [ComputerFrameElement]

    public init(
        frameID: String,
        generation: UInt64,
        target: ComputerWindowTarget,
        artifact: ComputerArtifactReference,
        capturedAt: Date,
        redactionApplied: Bool = false,
        elements: [ComputerFrameElement] = []
    ) {
        self.frameID = frameID
        self.generation = generation
        self.target = target
        self.artifact = artifact
        self.capturedAt = capturedAt
        self.redactionApplied = redactionApplied
        self.elements = elements
    }
}

public struct ComputerFrameElement: Codable, Sendable, Equatable {
    public let handleID: String
    public let frameGeneration: UInt64
    public let role: String
    public let title: String
    public let isSecure: Bool
    public let isEnabled: Bool

    public init(
        handleID: String,
        frameGeneration: UInt64,
        role: String,
        title: String,
        isSecure: Bool,
        isEnabled: Bool
    ) {
        self.handleID = handleID
        self.frameGeneration = frameGeneration
        self.role = role
        self.title = title
        self.isSecure = isSecure
        self.isEnabled = isEnabled
    }
}

public struct CaptureComputerFrameRequest: Codable, Sendable, Equatable {
    public let sessionID: String
    public let capability: ComputerUseSessionCapability
    public let target: ComputerWindowTarget

    public init(
        sessionID: String,
        capability: ComputerUseSessionCapability,
        target: ComputerWindowTarget
    ) {
        self.sessionID = sessionID
        self.capability = capability
        self.target = target
    }
}

public struct AccessibilityElementTarget: Codable, Sendable, Equatable {
    public let accessibilityIdentifier: String
    public let title: String
    public let role: String

    public init(
        accessibilityIdentifier: String = "",
        title: String = "",
        role: String = ""
    ) {
        self.accessibilityIdentifier = accessibilityIdentifier
        self.title = title
        self.role = role
    }
}

public struct AccessibilityElementSnapshot: Codable, Sendable, Equatable {
    public let target: ComputerWindowTarget
    public let element: AccessibilityElementTarget
    public let resolvedRole: String
    public let resolvedSubrole: String
    public let resolvedTitle: String
    public let supportedActions: [String]
    public let isSecureField: Bool

    public init(
        target: ComputerWindowTarget,
        element: AccessibilityElementTarget,
        resolvedRole: String,
        resolvedSubrole: String,
        resolvedTitle: String,
        supportedActions: [String],
        isSecureField: Bool
    ) {
        self.target = target
        self.element = element
        self.resolvedRole = resolvedRole
        self.resolvedSubrole = resolvedSubrole
        self.resolvedTitle = resolvedTitle
        self.supportedActions = supportedActions
        self.isSecureField = isSecureField
    }
}

public struct PressAccessibilityElementAction: Codable, Sendable, Equatable {
    public let element: AccessibilityElementTarget

    public init(element: AccessibilityElementTarget) {
        self.element = element
    }
}

public enum ComputerAction: Codable, Sendable, Equatable {
    case press(PressAccessibilityElementAction)
}

public struct ComputerUseApprovalGrant: Codable, Sendable, Equatable {
    public let approvalID: String
    public let actionDigest: String
    public let policyRevision: String
    public let approvedByActorID: String
    public let approvedAt: Date
    public let expiresAt: Date

    public init(
        approvalID: String,
        actionDigest: String,
        policyRevision: String,
        approvedByActorID: String,
        approvedAt: Date,
        expiresAt: Date
    ) {
        self.approvalID = approvalID
        self.actionDigest = actionDigest
        self.policyRevision = policyRevision
        self.approvedByActorID = approvedByActorID
        self.approvedAt = approvedAt
        self.expiresAt = expiresAt
    }
}

public struct PerformComputerActionRequest: Codable, Sendable, Equatable {
    public let sessionID: String
    public let capability: ComputerUseSessionCapability
    public let actionID: String
    public let idempotencyKey: String
    public let target: ComputerWindowTarget
    public let expectedFrameID: String
    public let expectedFrameGeneration: UInt64
    public let action: ComputerAction
    public let approval: ComputerUseApprovalGrant
    public let deadline: Date?

    public init(
        sessionID: String,
        capability: ComputerUseSessionCapability,
        actionID: String,
        idempotencyKey: String,
        target: ComputerWindowTarget,
        expectedFrameID: String,
        expectedFrameGeneration: UInt64,
        action: ComputerAction,
        approval: ComputerUseApprovalGrant,
        deadline: Date? = nil
    ) {
        self.sessionID = sessionID
        self.capability = capability
        self.actionID = actionID
        self.idempotencyKey = idempotencyKey
        self.target = target
        self.expectedFrameID = expectedFrameID
        self.expectedFrameGeneration = expectedFrameGeneration
        self.action = action
        self.approval = approval
        self.deadline = deadline
    }
}

public struct PreparedAccessibilityPress: Sendable, Equatable {
    public let preparationID: String
    public let request: AdapterAccessibilityRequest
    public let snapshot: AccessibilityElementSnapshot

    public init(
        preparationID: String,
        request: AdapterAccessibilityRequest,
        snapshot: AccessibilityElementSnapshot
    ) {
        self.preparationID = preparationID
        self.request = request
        self.snapshot = snapshot
    }
}

public enum AccessibilityPressCommitOutcome: Sendable, Equatable {
    case committed
    case rejected(ComputerUseBrokerError)
    case indeterminate(String)
}

public enum ComputerActionBoundaryPhase: String, Codable, Sendable, Equatable {
    case preflightPrepared = "preflight_prepared"
    case commitIntent = "commit_intent"
}

public struct ComputerActionBoundaryRecord: Codable, Sendable, Equatable {
    public let schemaVersion: String
    public let phase: ComputerActionBoundaryPhase
    public let sessionID: String
    public let actionID: String
    public let idempotencyKey: String
    public let actionDigest: String
    public let target: ComputerWindowTarget
    public let expectedFrameID: String
    public let expectedFrameGeneration: UInt64
    public let approvalID: String
    public let policyRevision: String
    public let adapterKind: String
    public let preparationID: String
    public let elementSnapshot: AccessibilityElementSnapshot
    public let recordedAt: Date

    public init(
        phase: ComputerActionBoundaryPhase,
        sessionID: String,
        actionID: String,
        idempotencyKey: String,
        actionDigest: String,
        target: ComputerWindowTarget,
        expectedFrameID: String,
        expectedFrameGeneration: UInt64,
        approvalID: String,
        policyRevision: String,
        adapterKind: String,
        preparationID: String,
        elementSnapshot: AccessibilityElementSnapshot,
        recordedAt: Date
    ) {
        schemaVersion = "melix.computer_action_boundary.v1"
        self.phase = phase
        self.sessionID = sessionID
        self.actionID = actionID
        self.idempotencyKey = idempotencyKey
        self.actionDigest = actionDigest
        self.target = target
        self.expectedFrameID = expectedFrameID
        self.expectedFrameGeneration = expectedFrameGeneration
        self.approvalID = approvalID
        self.policyRevision = policyRevision
        self.adapterKind = adapterKind
        self.preparationID = preparationID
        self.elementSnapshot = elementSnapshot
        self.recordedAt = recordedAt
    }
}

public enum ComputerActionState: String, Codable, Sendable, Equatable {
    case queued
    case preflighting
    case readyToCommit
    case committing
    case completed
    case cancelled
    case failed

    public var isTerminal: Bool {
        self == .completed || self == .cancelled || self == .failed
    }
}

public struct ComputerUseFailure: Codable, Sendable, Equatable {
    public let code: String
    public let message: String
    public let sideEffectCommitted: Bool

    public init(code: String, message: String, sideEffectCommitted: Bool = false) {
        self.code = code
        self.message = message
        self.sideEffectCommitted = sideEffectCommitted
    }
}

public struct ComputerActionReceipt: Codable, Sendable, Equatable {
    public let sessionID: String
    public let actionID: String
    public let idempotencyKey: String
    public let state: ComputerActionState
    public let target: ComputerWindowTarget
    public let actionDigest: String
    public let approvalID: String
    public let policyRevision: String
    public let adapterKind: String
    public let sideEffectCommitted: Bool
    public let beforeFrame: ComputerFrameObservation
    public let afterFrame: ComputerFrameObservation?
    public let elementSnapshot: AccessibilityElementSnapshot?
    public let startedAt: Date
    public let finishedAt: Date
    public let durationMilliseconds: Double
    public let failure: ComputerUseFailure?
    public let evidenceArtifact: ComputerArtifactReference?
    public let boundaryArtifacts: [ComputerArtifactReference]?

    public init(
        sessionID: String,
        actionID: String,
        idempotencyKey: String,
        state: ComputerActionState,
        target: ComputerWindowTarget,
        actionDigest: String,
        approvalID: String,
        policyRevision: String,
        adapterKind: String,
        sideEffectCommitted: Bool,
        beforeFrame: ComputerFrameObservation,
        afterFrame: ComputerFrameObservation?,
        elementSnapshot: AccessibilityElementSnapshot?,
        startedAt: Date,
        finishedAt: Date,
        durationMilliseconds: Double,
        failure: ComputerUseFailure?,
        evidenceArtifact: ComputerArtifactReference? = nil,
        boundaryArtifacts: [ComputerArtifactReference]? = nil
    ) {
        self.sessionID = sessionID
        self.actionID = actionID
        self.idempotencyKey = idempotencyKey
        self.state = state
        self.target = target
        self.actionDigest = actionDigest
        self.approvalID = approvalID
        self.policyRevision = policyRevision
        self.adapterKind = adapterKind
        self.sideEffectCommitted = sideEffectCommitted
        self.beforeFrame = beforeFrame
        self.afterFrame = afterFrame
        self.elementSnapshot = elementSnapshot
        self.startedAt = startedAt
        self.finishedAt = finishedAt
        self.durationMilliseconds = durationMilliseconds
        self.failure = failure
        self.evidenceArtifact = evidenceArtifact
        self.boundaryArtifacts = boundaryArtifacts
    }

    public func withEvidenceArtifact(_ artifact: ComputerArtifactReference) -> ComputerActionReceipt {
        ComputerActionReceipt(
            sessionID: sessionID,
            actionID: actionID,
            idempotencyKey: idempotencyKey,
            state: state,
            target: target,
            actionDigest: actionDigest,
            approvalID: approvalID,
            policyRevision: policyRevision,
            adapterKind: adapterKind,
            sideEffectCommitted: sideEffectCommitted,
            beforeFrame: beforeFrame,
            afterFrame: afterFrame,
            elementSnapshot: elementSnapshot,
            startedAt: startedAt,
            finishedAt: finishedAt,
            durationMilliseconds: durationMilliseconds,
            failure: failure,
            evidenceArtifact: artifact,
            boundaryArtifacts: boundaryArtifacts
        )
    }
}

public struct ComputerActionEvent: Codable, Sendable, Equatable {
    public let sequence: UInt64
    public let state: ComputerActionState
    public let occurredAt: Date
    public let message: String
    public let receipt: ComputerActionReceipt?

    public init(
        sequence: UInt64,
        state: ComputerActionState,
        occurredAt: Date,
        message: String = "",
        receipt: ComputerActionReceipt? = nil
    ) {
        self.sequence = sequence
        self.state = state
        self.occurredAt = occurredAt
        self.message = message
        self.receipt = receipt
    }

    public var isTerminal: Bool {
        state.isTerminal
    }
}

public struct ComputerActionExecution: Sendable {
    public let actionID: String
    public let events: AsyncStream<ComputerActionEvent>

    public init(actionID: String, events: AsyncStream<ComputerActionEvent>) {
        self.actionID = actionID
        self.events = events
    }
}

public enum ComputerActionCancelDisposition: String, Codable, Sendable, Equatable {
    case accepted
    case alreadyTerminal
    case tooLate
    case notFound
    case scopeMismatch
}

public struct CancelComputerActionRequest: Codable, Sendable, Equatable {
    public let sessionID: String
    public let capability: ComputerUseSessionCapability
    public let actionID: String
    public let cancellationID: String
    public let reason: String

    public init(
        sessionID: String,
        capability: ComputerUseSessionCapability,
        actionID: String,
        cancellationID: String,
        reason: String
    ) {
        self.sessionID = sessionID
        self.capability = capability
        self.actionID = actionID
        self.cancellationID = cancellationID
        self.reason = reason
    }
}

public struct ComputerActionCancellationReceipt: Codable, Sendable, Equatable {
    public let actionID: String
    public let cancellationID: String
    public let disposition: ComputerActionCancelDisposition
    public let requestedAt: Date
    public let terminalReceipt: ComputerActionReceipt?

    public init(
        actionID: String,
        cancellationID: String,
        disposition: ComputerActionCancelDisposition,
        requestedAt: Date,
        terminalReceipt: ComputerActionReceipt?
    ) {
        self.actionID = actionID
        self.cancellationID = cancellationID
        self.disposition = disposition
        self.requestedAt = requestedAt
        self.terminalReceipt = terminalReceipt
    }
}

public struct CloseComputerUseSessionRequest: Codable, Sendable, Equatable {
    public let sessionID: String
    public let capability: ComputerUseSessionCapability

    public init(sessionID: String, capability: ComputerUseSessionCapability) {
        self.sessionID = sessionID
        self.capability = capability
    }
}

public enum ComputerSessionCancelDisposition: String, Codable, Sendable, Equatable {
    case accepted
    case alreadyTerminal
    case notFound
    case scopeMismatch
}

public struct CancelComputerUseSessionRequest: Codable, Sendable, Equatable {
    public let sessionID: String
    public let capability: ComputerUseSessionCapability
    public let cancellationID: String
    public let reason: String

    public init(
        sessionID: String,
        capability: ComputerUseSessionCapability,
        cancellationID: String,
        reason: String
    ) {
        self.sessionID = sessionID
        self.capability = capability
        self.cancellationID = cancellationID
        self.reason = reason
    }
}

public struct ComputerUseSessionCancellationReceipt: Codable, Sendable, Equatable {
    public let sessionID: String
    public let cancellationID: String
    public let disposition: ComputerSessionCancelDisposition
    public let cancelledAt: Date
    public let cancelledActionIDs: [String]
    public let tooLateActionIDs: [String]

    public init(
        sessionID: String,
        cancellationID: String,
        disposition: ComputerSessionCancelDisposition,
        cancelledAt: Date,
        cancelledActionIDs: [String],
        tooLateActionIDs: [String]
    ) {
        self.sessionID = sessionID
        self.cancellationID = cancellationID
        self.disposition = disposition
        self.cancelledAt = cancelledAt
        self.cancelledActionIDs = cancelledActionIDs
        self.tooLateActionIDs = tooLateActionIDs
    }
}

public struct CloseComputerUseSessionReceipt: Codable, Sendable, Equatable {
    public let sessionID: String
    public let closedAt: Date
    public let cancelledActionIDs: [String]
    public let tooLateActionIDs: [String]

    public init(
        sessionID: String,
        closedAt: Date,
        cancelledActionIDs: [String],
        tooLateActionIDs: [String]
    ) {
        self.sessionID = sessionID
        self.closedAt = closedAt
        self.cancelledActionIDs = cancelledActionIDs
        self.tooLateActionIDs = tooLateActionIDs
    }
}

public struct ComputerUseMetricsSnapshot: Codable, Sendable, Equatable {
    public let values: [String: Double]

    public init(values: [String: Double]) {
        self.values = values
    }
}

public enum ComputerUseBrokerError: Error, Sendable, Equatable {
    case invalidRequest(String)
    case sessionNotFound
    case invalidSessionCapability
    case sessionClosed
    case sessionExpired
    case sessionIdleExpired
    case targetOutOfScope
    case frameBudgetExceeded
    case actionBudgetExceeded
    case artifactBudgetExceeded
    case frameRequired
    case staleFrame
    case approvalDigestMismatch
    case approvalExpired
    case approvalReplay
    case idempotencyConflict
    case secureFieldRefused
    case permissionDenied(String)
    case adapterFailure(String)
    case evidenceFailure(String)
}

extension ComputerUseBrokerError: LocalizedError {
    public var errorDescription: String? {
        switch self {
        case let .invalidRequest(message): message
        case .sessionNotFound: "Computer Use session was not found."
        case .invalidSessionCapability: "Computer Use session capability did not match."
        case .sessionClosed: "Computer Use session is closed."
        case .sessionExpired: "Computer Use session expired."
        case .sessionIdleExpired: "Computer Use session expired after its idle timeout."
        case .targetOutOfScope: "Computer Use target is outside the session scope."
        case .frameBudgetExceeded: "Computer Use frame budget was exceeded."
        case .actionBudgetExceeded: "Computer Use action budget was exceeded."
        case .artifactBudgetExceeded: "Computer Use artifact-byte budget was exceeded."
        case .frameRequired: "Computer Use action requires a captured frame."
        case .staleFrame: "Computer Use action referenced a stale frame."
        case .approvalDigestMismatch: "Computer Use approval does not match the action digest."
        case .approvalExpired: "Computer Use approval expired."
        case .approvalReplay: "Computer Use approval was already consumed."
        case .idempotencyConflict: "Computer Use idempotency key was reused for a different action."
        case .secureFieldRefused: "Computer Use refuses secure-field interaction."
        case let .permissionDenied(permission): "Computer Use permission is not granted: \(permission)."
        case let .adapterFailure(message): "Computer Use adapter failed: \(message)"
        case let .evidenceFailure(message): "Computer Use evidence persistence failed: \(message)"
        }
    }
}
