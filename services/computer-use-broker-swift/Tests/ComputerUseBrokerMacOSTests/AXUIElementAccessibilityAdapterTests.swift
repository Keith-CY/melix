import AppKit
import ApplicationServices
import ComputerUseBrokerCore
import Foundation
import Testing
@testable import ComputerUseBrokerMacOS

@Suite("AXUIElement accessibility adapter", .serialized)
struct AXUIElementAccessibilityAdapterTests {
    @Test("semantic press refuses a locator that becomes ambiguous after capture")
    func duplicateLocatorAfterCaptureFailsClosed() async throws {
        let fixture = AXSystemFixture()
        let captured = try await fixture.adapter.elements(
            for: fixture.target,
            frameGeneration: 7
        )
        #expect(captured.count == 1)
        #expect(captured.first?.handleID == fixture.locator.accessibilityIdentifier)

        fixture.system.installDuplicateButton()

        await expectBrokerError(.targetOutOfScope) {
            try await fixture.adapter.press(fixture.request)
        }
        #expect(fixture.system.pressedElementCount() == 0)
    }

    @Test("semantic press refuses an element that becomes disabled after capture")
    func enabledFlipAfterCaptureFailsClosed() async throws {
        let fixture = AXSystemFixture()
        let captured = try await fixture.adapter.elements(
            for: fixture.target,
            frameGeneration: 11
        )
        #expect(captured.first?.isEnabled == true)

        fixture.system.setButtonEnabled(false)

        await expectBrokerError(
            .invalidRequest(
                "Computer Use refuses disabled or unverifiably enabled elements."
            )
        ) {
            try await fixture.adapter.press(fixture.request)
        }
        #expect(fixture.system.pressedElementCount() == 0)
    }

    @Test("semantic press treats a missing enabled attribute as disabled")
    func missingEnabledAttributeFailsClosed() async throws {
        let fixture = AXSystemFixture()
        fixture.system.setButtonEnabled(nil)
        let captured = try await fixture.adapter.elements(
            for: fixture.target,
            frameGeneration: 13
        )
        #expect(captured.first?.isEnabled == false)

        await expectBrokerError(
            .invalidRequest(
                "Computer Use refuses disabled or unverifiably enabled elements."
            )
        ) {
            try await fixture.adapter.press(fixture.request)
        }
        #expect(fixture.system.pressedElementCount() == 0)
    }

    @Test("semantic press rechecks secure state and AXPress on the current element")
    func secureAndActionFlipsAfterCaptureFailClosed() async throws {
        do {
            let fixture = AXSystemFixture()
            _ = try await fixture.adapter.elements(
                for: fixture.target,
                frameGeneration: 17
            )
            fixture.system.setButtonSecure(true)

            await expectBrokerError(.secureFieldRefused) {
                try await fixture.adapter.press(fixture.request)
            }
            #expect(fixture.system.pressedElementCount() == 0)
        }

        do {
            let fixture = AXSystemFixture()
            _ = try await fixture.adapter.elements(
                for: fixture.target,
                frameGeneration: 19
            )
            fixture.system.setButtonActions([])

            await expectBrokerError(
                .adapterFailure("Accessibility element does not support AXPress.")
            ) {
                try await fixture.adapter.press(fixture.request)
            }
            #expect(fixture.system.pressedElementCount() == 0)
        }
    }

    @Test("semantic press executes once when the current match remains unique and safe")
    func uniqueEnabledElementIsPressedOnce() async throws {
        let fixture = AXSystemFixture()
        _ = try await fixture.adapter.elements(
            for: fixture.target,
            frameGeneration: 23
        )

        try await fixture.adapter.press(fixture.request)

        #expect(fixture.system.pressedElementCount() == 1)
        #expect(fixture.system.lastPressedElementIsOriginalButton())
    }

    @Test("semantic press explicitly focuses the approval-bound target and revalidates it")
    func approvalBoundTargetIsFocusedBeforePress() async throws {
        let fixture = AXSystemFixture()
        fixture.system.setFrontmostProcessIdentifier(9_999)

        try await fixture.adapter.press(fixture.request)

        #expect(
            fixture.system.activatedProcessIdentifiers()
                == [fixture.target.processIdentifier]
        )
        #expect(fixture.system.pressedElementCount() == 1)
    }

    @Test("semantic press refuses a target that cannot be safely focused")
    func failedTargetActivationFailsClosed() async {
        let fixture = AXSystemFixture()
        fixture.system.setFrontmostProcessIdentifier(9_999)
        fixture.system.setActivationAllowed(false)

        await expectBrokerError(.targetOutOfScope) {
            try await fixture.adapter.press(fixture.request)
        }
        #expect(fixture.system.pressedElementCount() == 0)
    }

    @Test("semantic press refuses an activation that never reaches the approved target")
    func acceptedActivationWithoutFocusFailsClosed() async {
        let fixture = AXSystemFixture()
        fixture.system.setFrontmostProcessIdentifier(9_999)
        fixture.system.setActivationChangesFrontmost(false)

        await expectBrokerError(.targetOutOfScope) {
            try await fixture.adapter.press(fixture.request)
        }
        #expect(
            fixture.system.activatedProcessIdentifiers()
                == [fixture.target.processIdentifier]
        )
        #expect(fixture.system.pressedElementCount() == 0)
    }

    @Test("semantic press rejects an approved window identity that changes before commit")
    func liveWindowIdentityChangeAtCommitFailsClosed() async {
        let validation = LiveWindowValidationSequence(
            outcomes: [.success(()), .success(()), .success(()), .failure(.targetOutOfScope)]
        )
        let fixture = AXSystemFixture(validateLiveWindowTarget: { target in
            try await validation.validate(target)
        })

        await expectBrokerError(.targetOutOfScope) {
            try await fixture.adapter.press(fixture.request)
        }
        #expect(fixture.system.pressedElementCount() == 0)
    }

    @Test("prepared presses are revalidated at commit without ambiguous side-effect claims")
    func preparedPressCommitBoundaryIsTyped() async throws {
        do {
            let fixture = AXSystemFixture()
            let preparation = try await fixture.adapter.preparePress(
                fixture.request
            )
            let emptyPreparation = PreparedAccessibilityPress(
                preparationID: "",
                request: preparation.request,
                snapshot: preparation.snapshot
            )

            #expect(
                await fixture.adapter.commitPress(emptyPreparation)
                    == .rejected(
                        .invalidRequest(
                            "Accessibility preparation ID must be non-empty."
                        )
                    )
            )
        }

        do {
            let fixture = AXSystemFixture()
            let preparation = try await fixture.adapter.preparePress(
                fixture.request
            )
            let mismatchedPreparation = PreparedAccessibilityPress(
                preparationID: preparation.preparationID,
                request: preparation.request,
                snapshot: AccessibilityElementSnapshot(
                    target: preparation.snapshot.target,
                    element: preparation.snapshot.element,
                    resolvedRole: preparation.snapshot.resolvedRole,
                    resolvedSubrole: preparation.snapshot.resolvedSubrole,
                    resolvedTitle: "Changed after preflight",
                    supportedActions: preparation.snapshot.supportedActions,
                    isSecureField: preparation.snapshot.isSecureField
                )
            )

            #expect(
                await fixture.adapter.commitPress(mismatchedPreparation)
                    == .rejected(.targetOutOfScope)
            )
        }

        do {
            let fixture = AXSystemFixture()
            let preparation = try await fixture.adapter.preparePress(
                fixture.request
            )
            fixture.system.setButtonEnabled(false)

            let outcome = await fixture.adapter.commitPress(preparation)

            #expect(
                outcome == .rejected(
                    .invalidRequest(
                        "Computer Use refuses disabled or unverifiably enabled elements."
                    )
                )
            )
            #expect(fixture.system.pressedElementCount() == 0)
        }

        do {
            let fixture = AXSystemFixture()
            let preparation = try await fixture.adapter.preparePress(
                fixture.request
            )
            fixture.system.setPressResult(.failure("cannot_complete"))

            let outcome = await fixture.adapter.commitPress(preparation)

            #expect(
                outcome == .indeterminate(
                    "AXUIElementPerformAction returned cannot_complete."
                )
            )
            #expect(fixture.system.pressedElementCount() == 0)
        }

        do {
            let fixture = AXSystemFixture()
            fixture.system.setButtonEnabledReadSequence([true, false])

            await expectBrokerError(
                .invalidRequest(
                    "Computer Use refuses disabled or unverifiably enabled elements."
                )
            ) {
                try await fixture.adapter.press(fixture.request)
            }
            #expect(fixture.system.pressedElementCount() == 0)
        }

        do {
            let fixture = AXSystemFixture()
            fixture.system.setPressResult(.failure("cannot_complete"))

            await expectBrokerError(
                .adapterFailure(
                    "AXUIElementPerformAction returned cannot_complete."
                )
            ) {
                try await fixture.adapter.press(fixture.request)
            }
            #expect(fixture.system.pressedElementCount() == 0)
        }
    }

    @Test("permission and identity checks fail before AX traversal")
    func admissionChecksFailClosed() async throws {
        do {
            let fixture = AXSystemFixture()
            #expect(await fixture.adapter.permissionState() == .granted)
            fixture.system.setTrusted(false)
            #expect(await fixture.adapter.permissionState() == .notGranted)
            await expectBrokerError(.permissionDenied("accessibility")) {
                try await fixture.adapter.elements(
                    for: fixture.target,
                    frameGeneration: 29
                )
            }
            await expectBrokerError(.permissionDenied("accessibility")) {
                try await fixture.adapter.inspect(fixture.request)
            }
            await expectBrokerError(.permissionDenied("accessibility")) {
                try await fixture.adapter.press(fixture.request)
            }
        }

        do {
            let fixture = AXSystemFixture()
            fixture.system.setIdentityAllowed(false)
            await expectBrokerError(.targetOutOfScope) {
                try await fixture.adapter.elements(
                    for: fixture.target,
                    frameGeneration: 31
                )
            }
            await expectBrokerError(.targetOutOfScope) {
                try await fixture.adapter.inspect(fixture.request)
            }
            await expectBrokerError(.targetOutOfScope) {
                try await fixture.adapter.press(fixture.request)
            }
        }
    }

    @Test("window and locator admission reject missing or ambiguous current scope")
    func windowAndLocatorAdmissionFailsClosed() async throws {
        do {
            let fixture = AXSystemFixture(
                target: testWindowTarget(windowTitle: "")
            )
            await expectBrokerError(
                .invalidRequest(
                    "AX element discovery requires the exact captured window title."
                )
            ) {
                try await fixture.adapter.elements(
                    for: fixture.target,
                    frameGeneration: 37
                )
            }
            await expectBrokerError(
                .invalidRequest(
                    "AX semantic action requires the title of the captured window."
                )
            ) {
                try await fixture.adapter.press(fixture.request)
            }
        }

        do {
            let fixture = AXSystemFixture()
            fixture.system.setWindowCount(0)
            await expectBrokerError(.targetOutOfScope) {
                try await fixture.adapter.elements(
                    for: fixture.target,
                    frameGeneration: 41
                )
            }
            await expectBrokerError(.targetOutOfScope) {
                try await fixture.adapter.press(fixture.request)
            }
        }

        do {
            let fixture = AXSystemFixture()
            fixture.system.setWindowCount(2)
            await expectBrokerError(.targetOutOfScope) {
                try await fixture.adapter.press(fixture.request)
            }
        }

        do {
            let fixture = AXSystemFixture(
                locator: AccessibilityElementTarget()
            )
            await expectBrokerError(
                .invalidRequest(
                    "AX semantic action requires an accessibility identifier or exact title."
                )
            ) {
                try await fixture.adapter.press(fixture.request)
            }
        }
    }

    @Test("inspection and locator fields stay bound to the current element")
    func inspectionAndLocatorFieldsAreCurrent() async throws {
        do {
            let fixture = AXSystemFixture()
            let snapshot = try await fixture.adapter.inspect(fixture.request)
            #expect(snapshot.resolvedRole == "AXButton")
            #expect(snapshot.resolvedTitle == "Increment")
            #expect(snapshot.supportedActions == [kAXPressAction as String])
        }

        for locator in [
            AccessibilityElementTarget(
                accessibilityIdentifier: "fixture.increment",
                title: "Different title",
                role: "AXButton"
            ),
            AccessibilityElementTarget(
                accessibilityIdentifier: "fixture.increment",
                title: "Increment",
                role: "AXCheckBox"
            ),
        ] {
            let fixture = AXSystemFixture(locator: locator)
            await expectBrokerError(
                .adapterFailure(
                    "Accessibility element was not found within the bounded traversal budget."
                )
            ) {
                try await fixture.adapter.press(fixture.request)
            }
        }

        do {
            let fixture = AXSystemFixture()
            fixture.system.setButtonIdentifier("different.identifier")
            await expectBrokerError(
                .adapterFailure(
                    "Accessibility element was not found within the bounded traversal budget."
                )
            ) {
                try await fixture.adapter.inspect(fixture.request)
            }
        }
    }

    @Test("discovery bounds and duplicate candidate filtering fail closed")
    func discoveryBoundsAndCandidateFiltering() async throws {
        do {
            let fixture = AXSystemFixture()
            fixture.system.setButtonIdentifier("")
            let elements = try await fixture.adapter.elements(
                for: fixture.target,
                frameGeneration: 43
            )
            #expect(elements.count == 1)
            #expect(elements.first?.handleID.isEmpty == true)
        }

        do {
            let fixture = AXSystemFixture()
            fixture.system.setButtonIdentifier("")
            fixture.system.setButtonTitle("")
            let elements = try await fixture.adapter.elements(
                for: fixture.target,
                frameGeneration: 47
            )
            #expect(elements.isEmpty)
        }

        do {
            let fixture = AXSystemFixture()
            fixture.system.installDuplicateButton()
            let elements = try await fixture.adapter.elements(
                for: fixture.target,
                frameGeneration: 53
            )
            #expect(elements.isEmpty)
        }

        do {
            let fixture = AXSystemFixture(maximumTraversalDepth: 0)
            let elements = try await fixture.adapter.elements(
                for: fixture.target,
                frameGeneration: 59
            )
            #expect(elements.isEmpty)
            await expectBrokerError(
                .adapterFailure(
                    "Accessibility element was not found within the bounded traversal budget."
                )
            ) {
                try await fixture.adapter.press(fixture.request)
            }
        }
    }

    @Test("AX perform failures remain typed and never report a committed press")
    func performFailureRemainsTyped() async throws {
        let fixture = AXSystemFixture()
        fixture.system.setPressResult(.failure("cannot_complete"))

        await expectBrokerError(
            .adapterFailure("AXUIElementPerformAction returned cannot_complete.")
        ) {
            try await fixture.adapter.press(fixture.request)
        }
        #expect(fixture.system.pressedElementCount() == 0)
    }

    @Test("native AX facade maps system failures without broadening scope")
    func nativeSystemFacadeIsBounded() async {
        let adapter = AXUIElementAccessibilityAdapter()
        #expect(adapter.adapterKind == "production.axuielement.semantic.v1")
        _ = await adapter.permissionState()

        let system = SystemAXUIElementSystem()
        _ = system.isProcessTrusted()
        _ = await system.frontmostProcessIdentifier()

        let impossibleTarget = ComputerWindowTarget(
            bundleIdentifier: "com.melix.missing",
            processIdentifier: Int32.max,
            processLaunchIdentity: "missing-launch",
            windowID: 1,
            windowTitle: "Missing"
        )
        #expect(!system.processIdentityMatches(impossibleTarget))
        #expect(!(await system.activate(impossibleTarget)))

        let currentPID = ProcessInfo.processInfo.processIdentifier
        if let application = NSRunningApplication(processIdentifier: currentPID),
           let bundleIdentifier = application.bundleIdentifier,
           let launchIdentity = MacOSProcessIdentity.launchIdentity(
               processIdentifier: currentPID
           )
        {
            let currentTarget = ComputerWindowTarget(
                bundleIdentifier: bundleIdentifier,
                processIdentifier: currentPID,
                processLaunchIdentity: launchIdentity,
                windowID: 1,
                windowTitle: "Current"
            )
            #expect(system.processIdentityMatches(currentTarget))
        }

        let element = system.applicationElement(processIdentifier: Int32.max)
        system.setMessagingTimeout(0.01, for: element)
        _ = system.stringAttribute(kAXTitleAttribute as CFString, of: element)
        _ = system.boolAttribute(kAXEnabledAttribute as CFString, of: element)
        _ = system.elementArrayAttribute(kAXWindowsAttribute as CFString, of: element)
        _ = system.actionNames(of: element)
        if case .success = system.performPress(on: element) {
            Issue.record("An impossible AX application unexpectedly accepted AXPress.")
        }

        let errorNames: [(AXError, String)] = [
            (.success, "success"),
            (.failure, "failure"),
            (.illegalArgument, "illegal_argument"),
            (.invalidUIElement, "invalid_ui_element"),
            (.invalidUIElementObserver, "invalid_ui_element_observer"),
            (.cannotComplete, "cannot_complete"),
            (.attributeUnsupported, "attribute_unsupported"),
            (.actionUnsupported, "action_unsupported"),
            (.notificationUnsupported, "notification_unsupported"),
            (.notImplemented, "not_implemented"),
            (.notificationAlreadyRegistered, "notification_already_registered"),
            (.notificationNotRegistered, "notification_not_registered"),
            (.apiDisabled, "api_disabled"),
            (.noValue, "no_value"),
            (.parameterizedAttributeUnsupported, "parameterized_attribute_unsupported"),
            (.notEnoughPrecision, "not_enough_precision"),
        ]
        for (error, expectedName) in errorNames {
            #expect(axErrorName(error) == expectedName)
        }
    }

    @Test("opt-in exact-window focus acceptance uses native AX when permission is available")
    @MainActor
    func nativeFocusActivationAcceptance() async throws {
        guard ProcessInfo.processInfo.environment[
            "MELIX_RUN_NATIVE_FOCUS_ACCEPTANCE"
        ] == "1" else {
            return
        }
        ProductionComputerUseBrokerFactory.prepareProcessForDesktopServices()
        let previous = NSWorkspace.shared.frontmostApplication
        defer {
            if let previous {
                _ = previous.activate()
            }
        }
        let nativeSystem = SystemAXUIElementSystem()
        guard let liveApplication = nativeFocusApplication(
            from: NSWorkspace.shared.runningApplications
        ) else {
            try await assertExactWindowFocusFallback()
            return
        }
        let liveTarget = ComputerWindowTarget(
            bundleIdentifier: try #require(liveApplication.bundleIdentifier),
            processIdentifier: liveApplication.processIdentifier,
            processLaunchIdentity: try #require(
                MacOSProcessIdentity.launchIdentity(
                    processIdentifier: liveApplication.processIdentifier
                )
            ),
            windowID: 1,
            windowTitle: "Native permission probe"
        )
        #expect(nativeSystem.processIdentityMatches(liveTarget))
        #expect(await nativeSystem.activate(liveTarget))
        let impossibleElement = nativeSystem.applicationElement(
            processIdentifier: Int32.max
        )
        #expect(!nativeSystem.focusWindow(impossibleElement, target: liveTarget))
        #expect(nativeSystem.focusedWindow(of: impossibleElement) == nil)

        guard nativeSystem.isProcessTrusted() else {
            try await assertExactWindowFocusFallback()
            return
        }
        let targets = try await ScreenCaptureKitFrameCaptureAdapter().listTargets()
        let target = try #require(
            targets.first(where: { target in
                let application = nativeSystem.applicationElement(
                    processIdentifier: target.processIdentifier
                )
                return nativeSystem.elementArrayAttribute(
                    kAXWindowsAttribute as CFString,
                    of: application
                ).filter {
                    nativeSystem.stringAttribute(
                        kAXTitleAttribute as CFString,
                        of: $0
                    ) == target.windowTitle
                }.count == 1
            })
        )
        let validator = ScreenCaptureKitWindowTargetValidator()
        try await assertExactWindowFocus(
            system: nativeSystem,
            target: target,
            validateLiveTarget: { target in
                try await validator.validate(target)
            }
        )
    }

    @Test("native focus acceptance falls back when no GUI application is available")
    @MainActor
    func nativeFocusActivationAcceptanceWithoutGUIApplication() async throws {
        #expect(nativeFocusApplication(from: []) == nil)
        try await assertExactWindowFocusFallback()
    }
}

private func nativeFocusApplication(
    from runningApplications: [NSRunningApplication]
) -> NSRunningApplication? {
    runningApplications.first(where: {
        $0.activationPolicy == .regular
            && $0.bundleIdentifier != nil
            && MacOSProcessIdentity.launchIdentity(
                processIdentifier: $0.processIdentifier
            ) != nil
    })
}

@MainActor
private func assertExactWindowFocusFallback() async throws {
    let fixture = AXSystemFixture()
    try await assertExactWindowFocus(
        system: fixture.system,
        target: fixture.target,
        validateLiveTarget: { _ in }
    )
}

@MainActor
private func assertExactWindowFocus(
    system: any AXUIElementSystem,
    target: ComputerWindowTarget,
    validateLiveTarget: @escaping @Sendable (
        ComputerWindowTarget
    ) async throws -> Void
) async throws {
    try await validateLiveTarget(target)
    #expect(await system.activate(target))
    let application = system.applicationElement(
        processIdentifier: target.processIdentifier
    )
    let window = try #require(
        system.elementArrayAttribute(
            kAXWindowsAttribute as CFString,
            of: application
        ).first(where: {
            system.stringAttribute(
                kAXTitleAttribute as CFString,
                of: $0
            ) == target.windowTitle
        })
    )
    #expect(system.focusWindow(window, target: target))
    #expect(await system.frontmostProcessIdentifier() == target.processIdentifier)
    #expect(system.boolAttribute(kAXMainAttribute as CFString, of: window) == true)
    #expect(system.focusedWindow(of: application).map { CFEqual($0, window) } == true)
    try await validateLiveTarget(target)
}

private struct AXSystemFixture {
    let target: ComputerWindowTarget
    let locator: AccessibilityElementTarget
    let system: FakeAXUIElementSystem
    let adapter: AXUIElementAccessibilityAdapter

    init(
        target: ComputerWindowTarget = testWindowTarget(),
        locator: AccessibilityElementTarget = testElementLocator(),
        maximumTraversalDepth: Int = 24,
        validateLiveWindowTarget: @escaping @Sendable (
            ComputerWindowTarget
        ) async throws -> Void = { _ in }
    ) {
        self.target = target
        self.locator = locator
        let system = FakeAXUIElementSystem(target: target)
        self.system = system
        adapter = AXUIElementAccessibilityAdapter(
            maximumTraversalDepth: maximumTraversalDepth,
            system: system,
            validateLiveWindowTarget: validateLiveWindowTarget
        )
    }

    var request: AdapterAccessibilityRequest {
        AdapterAccessibilityRequest(target: target, element: locator)
    }
}

private func testWindowTarget(
    windowTitle: String = "Fixture Window"
) -> ComputerWindowTarget {
    ComputerWindowTarget(
        bundleIdentifier: "com.melix.fixture",
        processIdentifier: 42_424,
        processLaunchIdentity: "fixture-launch",
        windowID: 77,
        windowTitle: windowTitle
    )
}

private func testElementLocator() -> AccessibilityElementTarget {
    AccessibilityElementTarget(
        accessibilityIdentifier: "fixture.increment",
        title: "Increment",
        role: "AXButton"
    )
}

private final class FakeAXUIElementSystem: AXUIElementSystem, @unchecked Sendable {
    private struct Node {
        let element: AXUIElement
        var strings: [String: String]
        var enabled: Bool?
        var children: [AXUIElement]
        var actions: [String]
    }

    private let lock = NSLock()
    private let target: ComputerWindowTarget
    private let application = AXUIElementCreateApplication(41_001)
    private let window = AXUIElementCreateApplication(41_002)
    private let originalButton = AXUIElementCreateApplication(41_003)
    private let duplicateButton = AXUIElementCreateApplication(41_004)
    private var nodes: [Node]
    private var trusted = true
    private var identityAllowed = true
    private var frontmostProcessID: Int32?
    private var windowElements: [AXUIElement]
    private var pressResult: AXUIElementPressResult = .success
    private var pressedElements: [AXUIElement] = []
    private var enabledReadSequence: [Bool?] = []
    private var activationAllowed = true
    private var activationChangesFrontmost = true
    private var activatedProcessIDs: [Int32] = []
    private var focusedWindowElement: AXUIElement?

    init(target: ComputerWindowTarget) {
        self.target = target
        frontmostProcessID = target.processIdentifier
        windowElements = [window]
        nodes = [
            Node(
                element: window,
                strings: [kAXTitleAttribute as String: target.windowTitle],
                enabled: true,
                children: [originalButton],
                actions: []
            ),
            Self.buttonNode(element: originalButton),
        ]
    }

    func isProcessTrusted() -> Bool {
        lock.withLock {
            trusted
        }
    }

    func processIdentityMatches(_ target: ComputerWindowTarget) -> Bool {
        lock.withLock {
            identityAllowed && target == self.target
        }
    }

    func frontmostProcessIdentifier() async -> Int32? {
        lock.withLock {
            frontmostProcessID
        }
    }

    func activate(_ target: ComputerWindowTarget) async -> Bool {
        lock.withLock {
            guard activationAllowed,
                  identityAllowed,
                  target == self.target
            else {
                return false
            }
            activatedProcessIDs.append(target.processIdentifier)
            if activationChangesFrontmost {
                frontmostProcessID = target.processIdentifier
            }
            return true
        }
    }

    func focusWindow(
        _ window: AXUIElement,
        target: ComputerWindowTarget
    ) -> Bool {
        lock.withLock {
            guard windowElements.contains(where: { sameElement($0, window) }) else {
                return false
            }
            focusedWindowElement = window
            return true
        }
    }

    func applicationElement(processIdentifier _: Int32) -> AXUIElement {
        application
    }

    func focusedWindow(of application: AXUIElement) -> AXUIElement? {
        lock.withLock {
            guard sameElement(application, self.application) else {
                return nil
            }
            return focusedWindowElement
        }
    }

    func setMessagingTimeout(_: Float, for _: AXUIElement) {}

    func stringAttribute(_ attribute: CFString, of element: AXUIElement) -> String? {
        lock.withLock {
            node(for: element)?.strings[attribute as String]
        }
    }

    func boolAttribute(_ attribute: CFString, of element: AXUIElement) -> Bool? {
        if attribute as String == kAXMainAttribute as String {
            return lock.withLock {
                focusedWindowElement.map { sameElement($0, element) } ?? false
            }
        }
        guard attribute as String == kAXEnabledAttribute as String else {
            return nil
        }
        return lock.withLock {
            if sameElement(element, originalButton),
               enabledReadSequence.isEmpty == false {
                return enabledReadSequence.removeFirst()
            }
            return node(for: element)?.enabled
        }
    }

    func elementArrayAttribute(
        _ attribute: CFString,
        of element: AXUIElement
    ) -> [AXUIElement] {
        lock.withLock {
            if sameElement(element, application),
               attribute as String == kAXWindowsAttribute as String
            {
                return windowElements
            }
            guard attribute as String == kAXChildrenAttribute as String else {
                return []
            }
            return node(for: element)?.children ?? []
        }
    }

    func actionNames(of element: AXUIElement) -> [String] {
        lock.withLock {
            node(for: element)?.actions ?? []
        }
    }

    func performPress(on element: AXUIElement) -> AXUIElementPressResult {
        lock.withLock {
            guard pressResult == .success else {
                return pressResult
            }
            pressedElements.append(element)
            return .success
        }
    }

    func setTrusted(_ trusted: Bool) {
        lock.withLock {
            self.trusted = trusted
        }
    }

    func setIdentityAllowed(_ allowed: Bool) {
        lock.withLock {
            identityAllowed = allowed
        }
    }

    func setFrontmostProcessIdentifier(_ processIdentifier: Int32?) {
        lock.withLock {
            frontmostProcessID = processIdentifier
        }
    }

    func setActivationAllowed(_ allowed: Bool) {
        lock.withLock {
            activationAllowed = allowed
        }
    }

    func setActivationChangesFrontmost(_ changesFrontmost: Bool) {
        lock.withLock {
            activationChangesFrontmost = changesFrontmost
        }
    }

    func activatedProcessIdentifiers() -> [Int32] {
        lock.withLock {
            activatedProcessIDs
        }
    }

    func setWindowCount(_ count: Int) {
        lock.withLock {
            windowElements = Array(repeating: window, count: count)
        }
    }

    func setPressResult(_ result: AXUIElementPressResult) {
        lock.withLock {
            pressResult = result
        }
    }

    func installDuplicateButton() {
        lock.withLock {
            nodes.append(Self.buttonNode(element: duplicateButton))
            let windowIndex = nodes.firstIndex {
                sameElement($0.element, window)
            }
            guard let windowIndex else {
                return
            }
            nodes[windowIndex].children.append(duplicateButton)
        }
    }

    func setButtonEnabled(_ enabled: Bool?) {
        updateOriginalButton { node in
            node.enabled = enabled
        }
    }

    func setButtonEnabledReadSequence(_ values: [Bool?]) {
        lock.withLock {
            enabledReadSequence = values
        }
    }

    func setButtonIdentifier(_ identifier: String) {
        updateOriginalButton { node in
            node.strings[kAXIdentifierAttribute as String] = identifier
        }
    }

    func setButtonTitle(_ title: String) {
        updateOriginalButton { node in
            node.strings[kAXTitleAttribute as String] = title
        }
    }

    func setButtonSecure(_ secure: Bool) {
        updateOriginalButton { node in
            node.strings[kAXSubroleAttribute as String] = secure
                ? kAXSecureTextFieldSubrole as String
                : ""
        }
    }

    func setButtonActions(_ actions: [String]) {
        updateOriginalButton { node in
            node.actions = actions
        }
    }

    func pressedElementCount() -> Int {
        lock.withLock {
            pressedElements.count
        }
    }

    func lastPressedElementIsOriginalButton() -> Bool {
        lock.withLock {
            guard let last = pressedElements.last else {
                return false
            }
            return sameElement(last, originalButton)
        }
    }

    private static func buttonNode(element: AXUIElement) -> Node {
        Node(
            element: element,
            strings: [
                kAXIdentifierAttribute as String: "fixture.increment",
                kAXTitleAttribute as String: "Increment",
                kAXRoleAttribute as String: "AXButton",
                kAXSubroleAttribute as String: "",
            ],
            enabled: true,
            children: [],
            actions: [kAXPressAction as String]
        )
    }

    private func updateOriginalButton(_ update: (inout Node) -> Void) {
        lock.withLock {
            guard let index = nodes.firstIndex(where: {
                sameElement($0.element, originalButton)
            }) else {
                return
            }
            update(&nodes[index])
        }
    }

    private func node(for element: AXUIElement) -> Node? {
        nodes.first {
            sameElement($0.element, element)
        }
    }

    private func sameElement(_ lhs: AXUIElement, _ rhs: AXUIElement) -> Bool {
        CFEqual(lhs, rhs)
    }
}

private actor LiveWindowValidationSequence {
    private var outcomes: [Result<Void, ComputerUseBrokerError>]

    init(outcomes: [Result<Void, ComputerUseBrokerError>]) {
        self.outcomes = outcomes
    }

    func validate(_: ComputerWindowTarget) throws {
        guard outcomes.isEmpty == false else { return }
        try outcomes.removeFirst().get()
    }
}

private func expectBrokerError<T>(
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
