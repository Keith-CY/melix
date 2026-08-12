import AppKit
import ApplicationServices
import ComputerUseBrokerCore
import Foundation

enum AXUIElementPressResult: Sendable, Equatable {
    case success
    case failure(String)
}

protocol AXUIElementSystem: Sendable {
    func isProcessTrusted() -> Bool
    func processIdentityMatches(_ target: ComputerWindowTarget) -> Bool
    func frontmostProcessIdentifier() async -> Int32?
    func activate(_ target: ComputerWindowTarget) async -> Bool
    func focusWindow(_ window: AXUIElement, target: ComputerWindowTarget) -> Bool
    func applicationElement(processIdentifier: Int32) -> AXUIElement
    func focusedWindow(of application: AXUIElement) -> AXUIElement?
    func setMessagingTimeout(_ timeout: Float, for element: AXUIElement)
    func stringAttribute(_ attribute: CFString, of element: AXUIElement) -> String?
    func boolAttribute(_ attribute: CFString, of element: AXUIElement) -> Bool?
    func elementArrayAttribute(_ attribute: CFString, of element: AXUIElement) -> [AXUIElement]
    func actionNames(of element: AXUIElement) -> [String]
    func performPress(on element: AXUIElement) -> AXUIElementPressResult
}

struct SystemAXUIElementSystem: AXUIElementSystem {
    func isProcessTrusted() -> Bool {
        AXIsProcessTrusted()
    }

    func processIdentityMatches(_ target: ComputerWindowTarget) -> Bool {
        guard let application = NSRunningApplication(
            processIdentifier: target.processIdentifier
        ) else {
            return false
        }
        return application.bundleIdentifier == target.bundleIdentifier
            && MacOSProcessIdentity.launchIdentity(
                processIdentifier: target.processIdentifier
            ) == target.processLaunchIdentity
    }

    func frontmostProcessIdentifier() async -> Int32? {
        await MainActor.run {
            NSWorkspace.shared.frontmostApplication?.processIdentifier
        }
    }

    func activate(_ target: ComputerWindowTarget) async -> Bool {
        guard processIdentityMatches(target),
              let application = NSRunningApplication(
                  processIdentifier: target.processIdentifier
              )
        else {
            return false
        }
        return await MainActor.run {
            application.activate()
        }
    }

    func focusWindow(
        _ window: AXUIElement,
        target: ComputerWindowTarget
    ) -> Bool {
        guard processIdentityMatches(target) else { return false }
        guard AXUIElementSetAttributeValue(
            window,
            kAXMainAttribute as CFString,
            kCFBooleanTrue
        ) == .success else {
            return false
        }
        return AXUIElementPerformAction(
            window,
            kAXRaiseAction as CFString
        ) == .success
    }

    func applicationElement(processIdentifier: Int32) -> AXUIElement {
        AXUIElementCreateApplication(processIdentifier)
    }

    func focusedWindow(of application: AXUIElement) -> AXUIElement? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(
            application,
            kAXFocusedWindowAttribute as CFString,
            &value
        ) == .success else {
            return nil
        }
        return (value as! AXUIElement?)
    }

    func setMessagingTimeout(_ timeout: Float, for element: AXUIElement) {
        AXUIElementSetMessagingTimeout(element, timeout)
    }

    func stringAttribute(_ attribute: CFString, of element: AXUIElement) -> String? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute, &value) == .success else {
            return nil
        }
        return value as? String
    }

    func boolAttribute(_ attribute: CFString, of element: AXUIElement) -> Bool? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute, &value) == .success else {
            return nil
        }
        return (value as? NSNumber)?.boolValue
    }

    func elementArrayAttribute(
        _ attribute: CFString,
        of element: AXUIElement
    ) -> [AXUIElement] {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, attribute, &value) == .success else {
            return []
        }
        return value as? [AXUIElement] ?? []
    }

    func actionNames(of element: AXUIElement) -> [String] {
        var names: CFArray?
        guard AXUIElementCopyActionNames(element, &names) == .success else {
            return []
        }
        return names as? [String] ?? []
    }

    func performPress(on element: AXUIElement) -> AXUIElementPressResult {
        let result = AXUIElementPerformAction(element, kAXPressAction as CFString)
        guard result == .success else {
            return .failure(axErrorName(result))
        }
        return .success
    }
}

public actor AXUIElementAccessibilityAdapter: AccessibilityAdapter {
    public nonisolated let adapterKind = "production.axuielement.semantic.v1"

    private let maximumTraversalNodes: Int
    private let maximumTraversalDepth: Int
    private let messagingTimeoutSeconds: Float
    private let system: any AXUIElementSystem
    private let validateLiveWindowTarget: @Sendable (
        ComputerWindowTarget
    ) async throws -> Void

    public init(
        maximumTraversalNodes: Int = 500,
        maximumTraversalDepth: Int = 24,
        messagingTimeoutSeconds: Float = 1
    ) {
        self.maximumTraversalNodes = maximumTraversalNodes
        self.maximumTraversalDepth = maximumTraversalDepth
        self.messagingTimeoutSeconds = messagingTimeoutSeconds
        system = SystemAXUIElementSystem()
        let targetValidator = ScreenCaptureKitWindowTargetValidator()
        validateLiveWindowTarget = { target in
            try await targetValidator.validate(target)
        }
    }

    init(
        maximumTraversalNodes: Int = 500,
        maximumTraversalDepth: Int = 24,
        messagingTimeoutSeconds: Float = 1,
        system: any AXUIElementSystem,
        validateLiveWindowTarget: @escaping @Sendable (
            ComputerWindowTarget
        ) async throws -> Void = { _ in }
    ) {
        self.maximumTraversalNodes = maximumTraversalNodes
        self.maximumTraversalDepth = maximumTraversalDepth
        self.messagingTimeoutSeconds = messagingTimeoutSeconds
        self.system = system
        self.validateLiveWindowTarget = validateLiveWindowTarget
    }

    public func permissionState() async -> ComputerUsePermissionState {
        system.isProcessTrusted() ? .granted : .notGranted
    }

    public func inspect(
        _ request: AdapterAccessibilityRequest
    ) async throws -> AccessibilityElementSnapshot {
        guard system.isProcessTrusted() else {
            throw ComputerUseBrokerError.permissionDenied("accessibility")
        }
        try validateProcessIdentity(request.target)
        try await validateLiveWindowTarget(request.target)
        let element = try resolveElement(request)
        return snapshot(element: element, request: request)
    }

    public func elements(
        for target: ComputerWindowTarget,
        frameGeneration: UInt64
    ) async throws -> [ComputerFrameElement] {
        guard system.isProcessTrusted() else {
            throw ComputerUseBrokerError.permissionDenied("accessibility")
        }
        try validateProcessIdentity(target)
        try await validateLiveWindowTarget(target)
        guard !target.windowTitle.isEmpty else {
            throw ComputerUseBrokerError.invalidRequest(
                "AX element discovery requires the exact captured window title."
            )
        }

        let application = system.applicationElement(
            processIdentifier: target.processIdentifier
        )
        system.setMessagingTimeout(messagingTimeoutSeconds, for: application)
        let roots = elementArrayAttribute(
            application,
            kAXWindowsAttribute as CFString
        ).filter {
            stringAttribute($0, kAXTitleAttribute as CFString)
                == target.windowTitle
        }
        guard roots.count == 1 else {
            throw ComputerUseBrokerError.targetOutOfScope
        }

        struct Candidate {
            let key: String
            let value: ComputerFrameElement
        }
        var candidates: [Candidate] = []
        var queue: [(element: AXUIElement, depth: Int)] = roots.map {
            ($0, 0)
        }
        var index = 0
        var visited = 0
        while index < queue.count, visited < maximumTraversalNodes {
            let current = queue[index]
            index += 1
            visited += 1

            let actions = actionNames(current.element)
            if actions.contains(kAXPressAction as String) {
                let identifier = stringAttribute(
                    current.element,
                    kAXIdentifierAttribute as CFString
                )
                let title = stringAttribute(
                    current.element,
                    kAXTitleAttribute as CFString
                )
                let role = stringAttribute(
                    current.element,
                    kAXRoleAttribute as CFString
                )
                let subrole = stringAttribute(
                    current.element,
                    kAXSubroleAttribute as CFString
                )
                if !identifier.isEmpty || !title.isEmpty {
                    let key = identifier.isEmpty
                        ? "title:\(role):\(title)"
                        : "identifier:\(identifier)"
                    candidates.append(
                        Candidate(
                            key: key,
                            value: ComputerFrameElement(
                                handleID: identifier,
                                frameGeneration: frameGeneration,
                                role: role,
                                title: title,
                                isSecure: subrole
                                    == (kAXSecureTextFieldSubrole as String),
                                isEnabled: boolAttribute(
                                    current.element,
                                    kAXEnabledAttribute as CFString,
                                    defaultValue: false
                                )
                            )
                        )
                    )
                }
            }

            guard current.depth < maximumTraversalDepth else {
                continue
            }
            let children = elementArrayAttribute(
                current.element,
                kAXChildrenAttribute as CFString
            )
            queue.append(
                contentsOf: children.map {
                    ($0, current.depth + 1)
                }
            )
        }

        let counts = Dictionary(
            grouping: candidates,
            by: \.key
        ).mapValues(\.count)
        return candidates.compactMap { candidate in
            counts[candidate.key] == 1 ? candidate.value : nil
        }
    }

    public func preparePress(
        _ request: AdapterAccessibilityRequest
    ) async throws -> PreparedAccessibilityPress {
        let (_, currentSnapshot) = try await validatePressPreparation(request)
        return PreparedAccessibilityPress(
            preparationID: UUID().uuidString.lowercased(),
            request: request,
            snapshot: currentSnapshot
        )
    }

    public func commitPress(
        _ preparation: PreparedAccessibilityPress
    ) async -> AccessibilityPressCommitOutcome {
        guard !preparation.preparationID.isEmpty else {
            return .rejected(
                .invalidRequest("Accessibility preparation ID must be non-empty.")
            )
        }
        let element: AXUIElement
        let currentSnapshot: AccessibilityElementSnapshot
        do {
            (element, currentSnapshot) = try await validatePressPreparation(
                preparation.request
            )
        } catch let error as ComputerUseBrokerError {
            return .rejected(error)
        } catch {
            return .rejected(.adapterFailure(error.localizedDescription))
        }
        guard currentSnapshot == preparation.snapshot else {
            return .rejected(.targetOutOfScope)
        }
        switch system.performPress(on: element) {
        case .success:
            return .committed
        case let .failure(errorName):
            return .indeterminate(
                "AXUIElementPerformAction returned \(errorName)."
            )
        }
    }

    public func press(_ request: AdapterAccessibilityRequest) async throws {
        let preparation = try await preparePress(request)
        switch await commitPress(preparation) {
        case .committed:
            return
        case let .rejected(error):
            throw error
        case let .indeterminate(message):
            throw ComputerUseBrokerError.adapterFailure(message)
        }
    }
}

private extension AXUIElementAccessibilityAdapter {
    func validatePressPreparation(
        _ request: AdapterAccessibilityRequest
    ) async throws -> (AXUIElement, AccessibilityElementSnapshot) {
        guard system.isProcessTrusted() else {
            throw ComputerUseBrokerError.permissionDenied("accessibility")
        }
        try validateProcessIdentity(request.target)
        try await validateLiveWindowTarget(request.target)
        let application = system.applicationElement(
            processIdentifier: request.target.processIdentifier
        )
        system.setMessagingTimeout(messagingTimeoutSeconds, for: application)
        let root = try resolveWindowRoot(
            request.target,
            application: application
        )
        try await focusAndRevalidateWindow(
            root,
            application: application,
            target: request.target
        )
        let matches = try resolveElements(request, root: root)
        guard matches.count == 1, let element = matches.first else {
            if matches.isEmpty {
                throw ComputerUseBrokerError.adapterFailure(
                    "Accessibility element was not found within the bounded traversal budget."
                )
            }
            throw ComputerUseBrokerError.targetOutOfScope
        }
        guard boolAttribute(
            element,
            kAXEnabledAttribute as CFString
        ) == true else {
            throw ComputerUseBrokerError.invalidRequest(
                "Computer Use refuses disabled or unverifiably enabled elements."
            )
        }
        let currentSnapshot = snapshot(element: element, request: request)
        guard !currentSnapshot.isSecureField else {
            throw ComputerUseBrokerError.secureFieldRefused
        }
        guard currentSnapshot.supportedActions.contains(kAXPressAction as String) else {
            throw ComputerUseBrokerError.adapterFailure("Accessibility element does not support AXPress.")
        }
        try validateProcessIdentity(request.target)
        try await validateLiveWindowTarget(request.target)
        try await validateExactForegroundWindow(
            root,
            application: application,
            target: request.target
        )
        return (element, currentSnapshot)
    }

    /// Public AX APIs do not expose an SCK window ID. The live SCK validator
    /// first proves that the approved full identity is still unique; only then
    /// may this exact unique AX root be made main, raised, and revalidated as
    /// the focused window before any element is resolved or committed.
    func focusAndRevalidateWindow(
        _ window: AXUIElement,
        application: AXUIElement,
        target: ComputerWindowTarget
    ) async throws {
        if await system.frontmostProcessIdentifier() != target.processIdentifier,
           !(await system.activate(target))
        {
            throw ComputerUseBrokerError.targetOutOfScope
        }
        guard system.focusWindow(window, target: target) else {
            throw ComputerUseBrokerError.targetOutOfScope
        }
        for _ in 0 ..< 20 {
            if await system.frontmostProcessIdentifier()
                == target.processIdentifier,
               isExactFocusedWindow(window, application: application)
            {
                break
            }
            try await Task.sleep(for: .milliseconds(50))
        }
        try validateProcessIdentity(target)
        try await validateLiveWindowTarget(target)
        try await validateExactForegroundWindow(
            window,
            application: application,
            target: target
        )
    }

    func validateExactForegroundWindow(
        _ window: AXUIElement,
        application: AXUIElement,
        target: ComputerWindowTarget
    ) async throws {
        let currentRoot = try resolveWindowRoot(
            target,
            application: application
        )
        guard system.processIdentityMatches(target),
              await system.frontmostProcessIdentifier() == target.processIdentifier,
              isExactFocusedWindow(window, application: application),
              CFEqual(currentRoot, window)
        else {
            throw ComputerUseBrokerError.targetOutOfScope
        }
    }

    func validateProcessIdentity(_ target: ComputerWindowTarget) throws {
        guard system.processIdentityMatches(target) else {
            throw ComputerUseBrokerError.targetOutOfScope
        }
    }

    func resolveElement(_ request: AdapterAccessibilityRequest) throws -> AXUIElement {
        let matches = try resolveElements(request)
        guard let element = matches.first else {
            throw ComputerUseBrokerError.adapterFailure(
                "Accessibility element was not found within the bounded traversal budget."
            )
        }
        return element
    }

    func resolveElements(_ request: AdapterAccessibilityRequest) throws -> [AXUIElement] {
        let application = system.applicationElement(
            processIdentifier: request.target.processIdentifier
        )
        system.setMessagingTimeout(messagingTimeoutSeconds, for: application)
        let root = try resolveWindowRoot(
            request.target,
            application: application
        )
        return try resolveElements(request, root: root)
    }

    func resolveWindowRoot(
        _ target: ComputerWindowTarget,
        application: AXUIElement
    ) throws -> AXUIElement {
        guard !target.windowTitle.isEmpty else {
            throw ComputerUseBrokerError.invalidRequest(
                "AX semantic action requires the title of the captured window."
            )
        }
        let roots = elementArrayAttribute(application, kAXWindowsAttribute as CFString).filter {
            stringAttribute($0, kAXTitleAttribute as CFString) == target.windowTitle
        }
        // Public Accessibility APIs do not expose the ScreenCaptureKit window ID.
        // Requiring one exact title match prevents a semantic action from drifting
        // to a sibling window in the same application.
        guard roots.count == 1 else {
            throw ComputerUseBrokerError.targetOutOfScope
        }
        return roots[0]
    }

    func resolveElements(
        _ request: AdapterAccessibilityRequest,
        root: AXUIElement
    ) throws -> [AXUIElement] {
        let locator = request.element
        guard !locator.accessibilityIdentifier.isEmpty || !locator.title.isEmpty else {
            throw ComputerUseBrokerError.invalidRequest(
                "AX semantic action requires an accessibility identifier or exact title."
            )
        }
        var queue: [(element: AXUIElement, depth: Int)] = [(root, 0)]
        var index = 0
        var visited = 0
        var matchedElements: [AXUIElement] = []
        while index < queue.count, visited < maximumTraversalNodes {
            let current = queue[index]
            index += 1
            visited += 1
            if matches(current.element, locator: locator) {
                matchedElements.append(current.element)
            }
            guard current.depth < maximumTraversalDepth else {
                continue
            }
            let children = elementArrayAttribute(current.element, kAXChildrenAttribute as CFString)
            queue.append(contentsOf: children.map { ($0, current.depth + 1) })
        }
        return matchedElements
    }

    func isExactFocusedWindow(
        _ window: AXUIElement,
        application: AXUIElement
    ) -> Bool {
        guard boolAttribute(window, kAXMainAttribute as CFString) == true,
              let focusedWindow = system.focusedWindow(of: application)
        else {
            return false
        }
        return CFEqual(focusedWindow, window)
    }

    func matches(_ element: AXUIElement, locator: AccessibilityElementTarget) -> Bool {
        if !locator.accessibilityIdentifier.isEmpty,
           stringAttribute(element, kAXIdentifierAttribute as CFString)
               != locator.accessibilityIdentifier
        {
            return false
        }
        if !locator.title.isEmpty,
           stringAttribute(element, kAXTitleAttribute as CFString) != locator.title
        {
            return false
        }
        if !locator.role.isEmpty,
           stringAttribute(element, kAXRoleAttribute as CFString) != locator.role
        {
            return false
        }
        return true
    }

    func snapshot(
        element: AXUIElement,
        request: AdapterAccessibilityRequest
    ) -> AccessibilityElementSnapshot {
        let role = stringAttribute(element, kAXRoleAttribute as CFString)
        let subrole = stringAttribute(element, kAXSubroleAttribute as CFString)
        let title = stringAttribute(element, kAXTitleAttribute as CFString)
        let actions = actionNames(element)
        return AccessibilityElementSnapshot(
            target: request.target,
            element: request.element,
            resolvedRole: role,
            resolvedSubrole: subrole,
            resolvedTitle: title,
            supportedActions: actions,
            isSecureField: subrole == (kAXSecureTextFieldSubrole as String)
        )
    }

    func stringAttribute(_ element: AXUIElement, _ attribute: CFString) -> String {
        system.stringAttribute(attribute, of: element) ?? ""
    }

    func boolAttribute(
        _ element: AXUIElement,
        _ attribute: CFString
    ) -> Bool? {
        system.boolAttribute(attribute, of: element)
    }

    func boolAttribute(
        _ element: AXUIElement,
        _ attribute: CFString,
        defaultValue: Bool
    ) -> Bool {
        boolAttribute(element, attribute) ?? defaultValue
    }

    func elementArrayAttribute(
        _ element: AXUIElement,
        _ attribute: CFString
    ) -> [AXUIElement] {
        system.elementArrayAttribute(attribute, of: element)
    }

    func actionNames(_ element: AXUIElement) -> [String] {
        system.actionNames(of: element)
    }
}

func axErrorName(_ error: AXError) -> String {
    switch error {
    case .success: "success"
    case .failure: "failure"
    case .illegalArgument: "illegal_argument"
    case .invalidUIElement: "invalid_ui_element"
    case .invalidUIElementObserver: "invalid_ui_element_observer"
    case .cannotComplete: "cannot_complete"
    case .attributeUnsupported: "attribute_unsupported"
    case .actionUnsupported: "action_unsupported"
    case .notificationUnsupported: "notification_unsupported"
    case .notImplemented: "not_implemented"
    case .notificationAlreadyRegistered: "notification_already_registered"
    case .notificationNotRegistered: "notification_not_registered"
    case .apiDisabled: "api_disabled"
    case .noValue: "no_value"
    case .parameterizedAttributeUnsupported: "parameterized_attribute_unsupported"
    case .notEnoughPrecision: "not_enough_precision"
    @unknown default: "unknown_\(error.rawValue)"
    }
}
