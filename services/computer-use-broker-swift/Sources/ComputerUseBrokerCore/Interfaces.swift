import Foundation

public protocol ComputerUseBroker: Sendable {
    func permissions() async -> ComputerUsePermissionSnapshot
    func listTargets() async throws -> [ComputerWindowTarget]
    func openSession(_ request: OpenComputerUseSessionRequest) async throws -> ComputerUseSession
    func captureFrame(_ request: CaptureComputerFrameRequest) async throws -> ComputerFrameObservation
    func performAction(_ request: PerformComputerActionRequest) async throws -> ComputerActionExecution
    func cancelAction(
        _ request: CancelComputerActionRequest
    ) async -> ComputerActionCancellationReceipt
    func cancelSession(
        _ request: CancelComputerUseSessionRequest
    ) async -> ComputerUseSessionCancellationReceipt
    func closeSession(
        _ request: CloseComputerUseSessionRequest
    ) async throws -> CloseComputerUseSessionReceipt
    func metricsSnapshot() async -> ComputerUseMetricsSnapshot
}

public struct AdapterFrameCaptureRequest: Sendable, Equatable {
    public let target: ComputerWindowTarget
    public let frameID: String
    public let generation: UInt64
    public let capturedAt: Date
    public let artifactDirectory: URL

    public init(
        target: ComputerWindowTarget,
        frameID: String,
        generation: UInt64,
        capturedAt: Date,
        artifactDirectory: URL
    ) {
        self.target = target
        self.frameID = frameID
        self.generation = generation
        self.capturedAt = capturedAt
        self.artifactDirectory = artifactDirectory
    }
}

public protocol FrameCaptureAdapter: Sendable {
    var adapterKind: String { get }
    func permissionState() async -> ComputerUsePermissionState
    func listTargets() async throws -> [ComputerWindowTarget]
    func capture(_ request: AdapterFrameCaptureRequest) async throws -> ComputerFrameObservation
}

public extension FrameCaptureAdapter {
    func listTargets() async throws -> [ComputerWindowTarget] {
        []
    }
}

public struct AdapterAccessibilityRequest: Sendable, Equatable {
    public let target: ComputerWindowTarget
    public let element: AccessibilityElementTarget

    public init(target: ComputerWindowTarget, element: AccessibilityElementTarget) {
        self.target = target
        self.element = element
    }
}

public protocol AccessibilityAdapter: Sendable {
    var adapterKind: String { get }
    func permissionState() async -> ComputerUsePermissionState
    func elements(
        for target: ComputerWindowTarget,
        frameGeneration: UInt64
    ) async throws -> [ComputerFrameElement]
    func inspect(_ request: AdapterAccessibilityRequest) async throws -> AccessibilityElementSnapshot
    func press(_ request: AdapterAccessibilityRequest) async throws
    func preparePress(
        _ request: AdapterAccessibilityRequest
    ) async throws -> PreparedAccessibilityPress
    func commitPress(
        _ preparation: PreparedAccessibilityPress
    ) async -> AccessibilityPressCommitOutcome
}

public extension AccessibilityAdapter {
    func elements(
        for _: ComputerWindowTarget,
        frameGeneration _: UInt64
    ) async throws -> [ComputerFrameElement] {
        []
    }

    func preparePress(
        _ request: AdapterAccessibilityRequest
    ) async throws -> PreparedAccessibilityPress {
        PreparedAccessibilityPress(
            preparationID: UUID().uuidString.lowercased(),
            request: request,
            snapshot: try await inspect(request)
        )
    }

    func commitPress(
        _ preparation: PreparedAccessibilityPress
    ) async -> AccessibilityPressCommitOutcome {
        do {
            try await press(preparation.request)
            return .committed
        } catch {
            return .indeterminate(error.localizedDescription)
        }
    }
}

public protocol ComputerUseEvidenceSink: Sendable {
    func record(
        _ receipt: ComputerActionReceipt,
        in artifactDirectory: URL
    ) throws -> ComputerArtifactReference
}

public protocol ComputerUseActionJournal: Sendable {
    func record(
        _ boundary: ComputerActionBoundaryRecord,
        in artifactDirectory: URL
    ) throws -> ComputerArtifactReference
}

public protocol ComputerUseClock: Sendable {
    func now() -> Date
}

public struct SystemComputerUseClock: ComputerUseClock {
    public init() {}

    public func now() -> Date {
        Date()
    }
}

public protocol ComputerUseIdentityGenerator: Sendable {
    func nextID(prefix: String) -> String
}

public struct UUIDComputerUseIdentityGenerator: ComputerUseIdentityGenerator {
    public init() {}

    public func nextID(prefix: String) -> String {
        "\(prefix)-\(UUID().uuidString.lowercased())"
    }
}
