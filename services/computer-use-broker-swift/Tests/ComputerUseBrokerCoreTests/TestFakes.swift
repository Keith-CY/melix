import ComputerUseBrokerCore
import CryptoKit
import Foundation

final class TestComputerUseClock: ComputerUseClock, @unchecked Sendable {
    private let lock = NSLock()
    private var current: Date

    init(now: Date) {
        current = now
    }

    func now() -> Date {
        lock.withLock { current }
    }

    func advance(by interval: TimeInterval) {
        lock.withLock {
            current = current.addingTimeInterval(interval)
        }
    }
}

final class TestComputerUseIdentityGenerator: ComputerUseIdentityGenerator, @unchecked Sendable {
    private let lock = NSLock()
    private var counter = 0

    func nextID(prefix: String) -> String {
        lock.withLock {
            counter += 1
            return "\(prefix)-test-\(counter)"
        }
    }
}

actor TestLatch {
    private var signalled = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
        if signalled {
            return
        }
        await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func signal() {
        guard !signalled else {
            return
        }
        signalled = true
        let current = waiters
        waiters.removeAll()
        for waiter in current {
            waiter.resume()
        }
    }
}

actor FakeFrameCaptureAdapter: FrameCaptureAdapter {
    nonisolated let adapterKind = "test.fake.frame"
    let captureStarted = TestLatch()
    private let permission: ComputerUsePermissionState
    private let failOnCaptureNumber: Int?
    private let mismatchOnCaptureNumber: Int?
    private let throwsBrokerError: Bool
    private let captureRelease: TestLatch?
    private var captures = 0

    init(
        permission: ComputerUsePermissionState = .granted,
        failOnCaptureNumber: Int? = nil,
        mismatchOnCaptureNumber: Int? = nil,
        throwsBrokerError: Bool = false,
        captureRelease: TestLatch? = nil
    ) {
        self.permission = permission
        self.failOnCaptureNumber = failOnCaptureNumber
        self.mismatchOnCaptureNumber = mismatchOnCaptureNumber
        self.throwsBrokerError = throwsBrokerError
        self.captureRelease = captureRelease
    }

    func permissionState() async -> ComputerUsePermissionState {
        permission
    }

    func capture(_ request: AdapterFrameCaptureRequest) async throws -> ComputerFrameObservation {
        captures += 1
        await captureStarted.signal()
        if let captureRelease {
            await captureRelease.wait()
        }
        if failOnCaptureNumber == captures {
            if throwsBrokerError {
                throw ComputerUseBrokerError.permissionDenied("screen_capture")
            }
            throw TestAdapterError(message: "fixture frame failure")
        }
        let data = Data("fake-frame-\(request.generation)".utf8)
        try FileManager.default.createDirectory(
            at: request.artifactDirectory,
            withIntermediateDirectories: true
        )
        let url = request.artifactDirectory.appendingPathComponent(
            "fake-frame-\(request.generation).bin"
        )
        try data.write(to: url, options: .atomic)
        let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        return ComputerFrameObservation(
            frameID: mismatchOnCaptureNumber == captures ? "mismatched-frame" : request.frameID,
            generation: request.generation,
            target: request.target,
            artifact: ComputerArtifactReference(
                artifactID: "fake-frame-\(request.generation)",
                path: url.path,
                sha256: digest,
                byteCount: data.count,
                mediaType: "application/octet-stream",
                width: 100,
                height: 80,
                adapterKind: adapterKind
            ),
            capturedAt: request.capturedAt
        )
    }

    func captureCount() -> Int {
        captures
    }
}

actor FakeAccessibilityAdapter: AccessibilityAdapter {
    nonisolated let adapterKind = "test.fake.accessibility"

    let inspectionStarted = TestLatch()
    let pressStarted = TestLatch()
    private let inspectionRelease: TestLatch?
    private let pressRelease: TestLatch?
    private let permission: ComputerUsePermissionState
    private let secureField: Bool
    private let actionNames: [String]
    private let inspectionErrorMessage: String?
    private let elementsErrorMessage: String?
    private let pressErrorMessage: String?
    private let commitRejection: ComputerUseBrokerError?
    private let resolvedTarget: ComputerWindowTarget?
    private let discoveredElements: [ComputerFrameElement]
    private let preparationID: String
    private var presses = 0

    init(
        secureField: Bool = false,
        actionNames: [String] = ["AXPress"],
        permission: ComputerUsePermissionState = .granted,
        inspectionRelease: TestLatch? = nil,
        pressRelease: TestLatch? = nil,
        elementsErrorMessage: String? = nil,
        inspectionErrorMessage: String? = nil,
        pressErrorMessage: String? = nil,
        commitRejection: ComputerUseBrokerError? = nil,
        resolvedTarget: ComputerWindowTarget? = nil,
        preparationID: String = "preparation-test",
        discoveredElements: [ComputerFrameElement] = [
            ComputerFrameElement(
                handleID: "fixture.increment",
                frameGeneration: 0,
                role: "AXButton",
                title: "Increment",
                isSecure: false,
                isEnabled: true
            ),
        ]
    ) {
        self.secureField = secureField
        self.actionNames = actionNames
        self.permission = permission
        self.inspectionRelease = inspectionRelease
        self.pressRelease = pressRelease
        self.elementsErrorMessage = elementsErrorMessage
        self.inspectionErrorMessage = inspectionErrorMessage
        self.pressErrorMessage = pressErrorMessage
        self.commitRejection = commitRejection
        self.resolvedTarget = resolvedTarget
        self.preparationID = preparationID
        self.discoveredElements = discoveredElements
    }

    func permissionState() async -> ComputerUsePermissionState {
        permission
    }

    func elements(
        for _: ComputerWindowTarget,
        frameGeneration: UInt64
    ) async throws -> [ComputerFrameElement] {
        if let elementsErrorMessage {
            throw TestAdapterError(message: elementsErrorMessage)
        }
        return discoveredElements.map { element in
            ComputerFrameElement(
                handleID: element.handleID,
                frameGeneration: frameGeneration,
                role: element.role,
                title: element.title,
                isSecure: element.isSecure,
                isEnabled: element.isEnabled
            )
        }
    }

    func inspect(_ request: AdapterAccessibilityRequest) async throws -> AccessibilityElementSnapshot {
        await inspectionStarted.signal()
        if let inspectionRelease {
            await inspectionRelease.wait()
        }
        if let inspectionErrorMessage {
            throw TestAdapterError(message: inspectionErrorMessage)
        }
        return AccessibilityElementSnapshot(
            target: resolvedTarget ?? request.target,
            element: request.element,
            resolvedRole: request.element.role.isEmpty ? "AXButton" : request.element.role,
            resolvedSubrole: secureField ? "AXSecureTextField" : "",
            resolvedTitle: request.element.title,
            supportedActions: actionNames,
            isSecureField: secureField
        )
    }

    func press(_ request: AdapterAccessibilityRequest) async throws {
        _ = request
        await pressStarted.signal()
        if let pressRelease {
            await pressRelease.wait()
        }
        if let pressErrorMessage {
            throw TestAdapterError(message: pressErrorMessage)
        }
        presses += 1
    }

    func preparePress(
        _ request: AdapterAccessibilityRequest
    ) async throws -> PreparedAccessibilityPress {
        PreparedAccessibilityPress(
            preparationID: preparationID,
            request: request,
            snapshot: try await inspect(request)
        )
    }

    func commitPress(
        _ preparation: PreparedAccessibilityPress
    ) async -> AccessibilityPressCommitOutcome {
        if let commitRejection {
            return .rejected(commitRejection)
        }
        do {
            try await press(preparation.request)
            return .committed
        } catch {
            return .indeterminate(error.localizedDescription)
        }
    }

    func pressCount() -> Int {
        presses
    }
}

struct BrokerTestContext {
    let broker: DefaultComputerUseBroker
    let clock: TestComputerUseClock
    let frames: FakeFrameCaptureAdapter
    let accessibility: FakeAccessibilityAdapter
    let artifactRoot: URL
    let session: ComputerUseSession
    let target: ComputerWindowTarget
    let frame: ComputerFrameObservation
}

struct BareBrokerTestContext {
    let broker: DefaultComputerUseBroker
    let clock: TestComputerUseClock
    let artifactRoot: URL
}

func makeBareBrokerTestContext(
    frames: any FrameCaptureAdapter = FakeFrameCaptureAdapter(),
    accessibility: FakeAccessibilityAdapter = FakeAccessibilityAdapter(),
    evidenceSink: any ComputerUseEvidenceSink = FileComputerUseEvidenceSink(),
    actionJournal: any ComputerUseActionJournal = FileComputerUseActionJournal()
) -> BareBrokerTestContext {
    let artifactRoot = FileManager.default.temporaryDirectory.appendingPathComponent(
        "melix-computer-broker-bare-tests-\(UUID().uuidString)",
        isDirectory: true
    )
    let clock = TestComputerUseClock(now: Date(timeIntervalSince1970: 1_800_000_000))
    return BareBrokerTestContext(
        broker: DefaultComputerUseBroker(
            frameCapture: frames,
            accessibility: accessibility,
            evidenceSink: evidenceSink,
            actionJournal: actionJournal,
            clock: clock,
            identityGenerator: TestComputerUseIdentityGenerator(),
            artifactRoot: artifactRoot
        ),
        clock: clock,
        artifactRoot: artifactRoot
    )
}

func makeBrokerTestContext(
    accessibility: FakeAccessibilityAdapter = FakeAccessibilityAdapter(),
    frames: FakeFrameCaptureAdapter = FakeFrameCaptureAdapter(),
    evidenceSink: any ComputerUseEvidenceSink = FileComputerUseEvidenceSink(),
    actionJournal: any ComputerUseActionJournal = FileComputerUseActionJournal(),
    limits: ComputerUseSessionLimits = ComputerUseSessionLimits()
) async throws -> BrokerTestContext {
    let artifactRoot = FileManager.default.temporaryDirectory.appendingPathComponent(
        "melix-computer-broker-tests-\(UUID().uuidString)",
        isDirectory: true
    )
    let clock = TestComputerUseClock(now: Date(timeIntervalSince1970: 1_800_000_000))
    let broker = DefaultComputerUseBroker(
        frameCapture: frames,
        accessibility: accessibility,
        evidenceSink: evidenceSink,
        actionJournal: actionJournal,
        clock: clock,
        identityGenerator: TestComputerUseIdentityGenerator(),
        artifactRoot: artifactRoot
    )
    let target = ComputerWindowTarget(
        bundleIdentifier: "io.melix.fixture",
        processIdentifier: 4242,
        processLaunchIdentity: "fixture-launch-1",
        windowID: 77,
        windowTitle: "Computer Use Fixture"
    )
    let session = try await broker.openSession(
        OpenComputerUseSessionRequest(
            ownerID: "operator-1",
            runID: "run-1",
            allowedBundleIdentifiers: [target.bundleIdentifier],
            allowedWindowIDs: [target.windowID],
            artifactNamespace: "contract-tests",
            limits: limits
        )
    )
    let frame = try await broker.captureFrame(
        CaptureComputerFrameRequest(
            sessionID: session.sessionID,
            capability: session.capability,
            target: target
        )
    )
    return BrokerTestContext(
        broker: broker,
        clock: clock,
        frames: frames,
        accessibility: accessibility,
        artifactRoot: artifactRoot,
        session: session,
        target: target,
        frame: frame
    )
}

struct FailingComputerUseEvidenceSink: ComputerUseEvidenceSink {
    func record(
        _ receipt: ComputerActionReceipt,
        in artifactDirectory: URL
    ) throws -> ComputerArtifactReference {
        _ = receipt
        _ = artifactDirectory
        throw TestAdapterError(message: "fixture evidence failure")
    }
}

struct FailingComputerUseActionJournal: ComputerUseActionJournal {
    let failingPhase: ComputerActionBoundaryPhase
    private let delegate = FileComputerUseActionJournal()

    func record(
        _ boundary: ComputerActionBoundaryRecord,
        in artifactDirectory: URL
    ) throws -> ComputerArtifactReference {
        if boundary.phase == failingPhase {
            throw TestAdapterError(
                message: "fixture \(failingPhase.rawValue) journal failure"
            )
        }
        return try delegate.record(boundary, in: artifactDirectory)
    }
}

struct TestAdapterError: LocalizedError, Sendable {
    let message: String

    var errorDescription: String? {
        message
    }
}

func makeActionRequest(
    context: BrokerTestContext,
    frame: ComputerFrameObservation? = nil,
    actionID: String,
    idempotencyKey: String,
    approvalID: String,
    approvalExpiryOffset: TimeInterval = 60
) throws -> PerformComputerActionRequest {
    let admittedFrame = frame ?? context.frame
    let action = ComputerAction.press(
        PressAccessibilityElementAction(
            element: AccessibilityElementTarget(
                accessibilityIdentifier: "fixture.increment",
                title: "Increment",
                role: "AXButton"
            )
        )
    )
    let digest = try ComputerActionDigest.compute(
        sessionID: context.session.sessionID,
        actionID: actionID,
        idempotencyKey: idempotencyKey,
        target: context.target,
        expectedFrameID: admittedFrame.frameID,
        expectedFrameGeneration: admittedFrame.generation,
        action: action
    )
    let now = context.clock.now()
    return PerformComputerActionRequest(
        sessionID: context.session.sessionID,
        capability: context.session.capability,
        actionID: actionID,
        idempotencyKey: idempotencyKey,
        target: context.target,
        expectedFrameID: admittedFrame.frameID,
        expectedFrameGeneration: admittedFrame.generation,
        action: action,
        approval: ComputerUseApprovalGrant(
            approvalID: approvalID,
            actionDigest: digest,
            policyRevision: "policy-v1",
            approvedByActorID: "operator-1",
            approvedAt: now,
            expiresAt: now.addingTimeInterval(approvalExpiryOffset)
        )
    )
}

func collectEvents(_ execution: ComputerActionExecution) async -> [ComputerActionEvent] {
    var events: [ComputerActionEvent] = []
    for await event in execution.events {
        events.append(event)
    }
    return events
}
