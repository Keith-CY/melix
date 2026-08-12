import AppKit
import ComputerUseBrokerCore
import CoreGraphics
import CryptoKit
import Foundation
import ImageIO
import ScreenCaptureKit
import UniformTypeIdentifiers

struct ScreenCaptureWindowMetadata: Sendable, Equatable {
    let windowID: UInt32
    let width: CGFloat
    let height: CGFloat
    let processIdentifier: Int32
    let bundleIdentifier: String
    let processLaunchIdentity: String?
    let windowTitle: String
    let applicationName: String
}

struct ScreenCaptureDimensions: Sendable, Equatable {
    let width: Int
    let height: Int
}

final class ScreenCaptureWindowHandle: @unchecked Sendable {
    let window: SCWindow

    init(window: SCWindow) {
        self.window = window
    }
}

struct ScreenCaptureWindowDescriptor: @unchecked Sendable {
    let metadata: ScreenCaptureWindowMetadata
    let pointPixelScale: CGFloat
    let handle: ScreenCaptureWindowHandle?
}

struct ScreenCaptureKitFrameCaptureDependencies: @unchecked Sendable {
    let permissionCheck: @Sendable () -> Bool
    let loadWindows: @Sendable (Bool) async throws -> [ScreenCaptureWindowDescriptor]
    let captureImage: @Sendable (
        ScreenCaptureWindowDescriptor,
        ScreenCaptureDimensions
    ) async throws -> CGImage
    let resolveProcessIdentity: @Sendable (Int32) -> String?

    static let live = ScreenCaptureKitFrameCaptureDependencies(
        permissionCheck: {
            CGPreflightScreenCaptureAccess()
        },
        loadWindows: { excludingDesktopWindows in
            let content = try await SCShareableContent.excludingDesktopWindows(
                excludingDesktopWindows,
                onScreenWindowsOnly: true
            )
            return content.windows.map { window in
                let application = window.owningApplication
                let filter = SCContentFilter(desktopIndependentWindow: window)
                return ScreenCaptureWindowDescriptor(
                    metadata: ScreenCaptureWindowMetadata(
                        windowID: window.windowID,
                        width: window.frame.width,
                        height: window.frame.height,
                        processIdentifier: application?.processID ?? 0,
                        bundleIdentifier: application?.bundleIdentifier ?? "",
                        processLaunchIdentity: application.flatMap {
                            MacOSProcessIdentity.launchIdentity(
                                processIdentifier: $0.processID
                            )
                        },
                        windowTitle: window.title ?? "",
                        applicationName: application?.applicationName ?? ""
                    ),
                    pointPixelScale: max(
                        CGFloat(1),
                        CGFloat(filter.pointPixelScale)
                    ),
                    handle: ScreenCaptureWindowHandle(window: window)
                )
            }
        },
        captureImage: { descriptor, dimensions in
            guard let handle = descriptor.handle else {
                throw ComputerUseBrokerError.adapterFailure(
                    "ScreenCaptureKit window handle was unavailable."
                )
            }
            let filter = SCContentFilter(
                desktopIndependentWindow: handle.window
            )
            let configuration = SCStreamConfiguration()
            configuration.width = dimensions.width
            configuration.height = dimensions.height
            configuration.showsCursor = false
            configuration.captureResolution = .best
            return try await SCScreenshotManager.captureImage(
                contentFilter: filter,
                configuration: configuration
            )
        },
        resolveProcessIdentity: { processIdentifier in
            MacOSProcessIdentity.launchIdentity(
                processIdentifier: processIdentifier
            )
        }
    )
}

struct ScreenCaptureKitWindowTargetValidator: Sendable {
    private let dependencies: ScreenCaptureKitFrameCaptureDependencies

    init(dependencies: ScreenCaptureKitFrameCaptureDependencies = .live) {
        self.dependencies = dependencies
    }

    func validate(_ target: ComputerWindowTarget) async throws {
        guard dependencies.permissionCheck() else {
            throw ComputerUseBrokerError.permissionDenied("screen_capture")
        }
        guard dependencies.resolveProcessIdentity(target.processIdentifier)
            == target.processLaunchIdentity
        else {
            throw ComputerUseBrokerError.targetOutOfScope
        }

        let windows: [ScreenCaptureWindowDescriptor]
        do {
            windows = try await dependencies.loadWindows(false)
        } catch {
            throw ComputerUseBrokerError.adapterFailure(
                "ScreenCaptureKit could not revalidate the approved window: \(error.localizedDescription)"
            )
        }
        let exactMatches = windows.filter { candidate in
            screenCaptureWindowExactlyMatches(candidate.metadata, target: target)
        }
        let axTitleMatches = windows.filter { candidate in
            candidate.metadata.processIdentifier == target.processIdentifier
                && candidate.metadata.bundleIdentifier == target.bundleIdentifier
                && candidate.metadata.processLaunchIdentity == target.processLaunchIdentity
                && candidate.metadata.windowTitle == target.windowTitle
        }
        // AX does not expose the ScreenCaptureKit window ID. The only mapping
        // Melix can prove with public APIs is therefore one live SCK identity
        // and one title-matched window in the exact approved process.
        guard exactMatches.count == 1, axTitleMatches.count == 1 else {
            throw ComputerUseBrokerError.targetOutOfScope
        }
    }
}

public actor ScreenCaptureKitFrameCaptureAdapter: FrameCaptureAdapter {
    public nonisolated let adapterKind = "production.screencapturekit.window.v1"

    private let maximumDimension: Int
    private let maximumArtifactBytes: Int
    private let dependencies: ScreenCaptureKitFrameCaptureDependencies

    public init(
        maximumDimension: Int = 4_096,
        maximumArtifactBytes: Int = 16 * 1_024 * 1_024
    ) {
        self.maximumDimension = maximumDimension
        self.maximumArtifactBytes = maximumArtifactBytes
        self.dependencies = .live
    }

    init(
        maximumDimension: Int = 4_096,
        maximumArtifactBytes: Int = 16 * 1_024 * 1_024,
        dependencies: ScreenCaptureKitFrameCaptureDependencies
    ) {
        self.maximumDimension = maximumDimension
        self.maximumArtifactBytes = maximumArtifactBytes
        self.dependencies = dependencies
    }

    public func permissionState() async -> ComputerUsePermissionState {
        dependencies.permissionCheck() ? .granted : .notGranted
    }

    public func listTargets() async throws -> [ComputerWindowTarget] {
        guard dependencies.permissionCheck() else {
            throw ComputerUseBrokerError.permissionDenied("screen_capture")
        }
        let windows: [ScreenCaptureWindowDescriptor]
        do {
            windows = try await dependencies.loadWindows(true)
        } catch {
            throw ComputerUseBrokerError.adapterFailure(
                "ScreenCaptureKit could not enumerate shareable windows: \(error.localizedDescription)"
            )
        }
        return screenCaptureTargets(from: windows.map(\.metadata))
    }

    public func capture(
        _ request: AdapterFrameCaptureRequest
    ) async throws -> ComputerFrameObservation {
        guard dependencies.permissionCheck() else {
            throw ComputerUseBrokerError.permissionDenied("screen_capture")
        }
        try validateProcessIdentity(request.target)

        let windows: [ScreenCaptureWindowDescriptor]
        do {
            windows = try await dependencies.loadWindows(false)
        } catch {
            throw ComputerUseBrokerError.adapterFailure(
                "ScreenCaptureKit could not enumerate shareable windows: \(error.localizedDescription)"
            )
        }
        let matchingWindows = windows.filter { candidate in
            screenCaptureWindowExactlyMatches(
                candidate.metadata,
                target: request.target
            )
        }
        guard matchingWindows.count == 1,
              let window = matchingWindows.first
        else {
            throw ComputerUseBrokerError.targetOutOfScope
        }

        let naturalWidth = max(
            1,
            Int((window.metadata.width * window.pointPixelScale).rounded())
        )
        let naturalHeight = max(
            1,
            Int((window.metadata.height * window.pointPixelScale).rounded())
        )
        let dimensions = screenCaptureDimensions(
            naturalWidth: naturalWidth,
            naturalHeight: naturalHeight,
            maximumDimension: maximumDimension
        )

        let image: CGImage
        do {
            image = try await dependencies.captureImage(window, dimensions)
        } catch {
            throw ComputerUseBrokerError.adapterFailure(
                "ScreenCaptureKit window capture failed: \(error.localizedDescription)"
            )
        }
        // Capturing is an asynchronous trust-boundary crossing. Re-enumerate
        // the live window after ScreenCaptureKit returns and before encoding or
        // persisting any artifact so a process restart, window replacement, or
        // title swap cannot commit evidence under the prior approval.
        try await ScreenCaptureKitWindowTargetValidator(
            dependencies: dependencies
        ).validate(request.target)
        let data = try Self.pngData(for: image)
        return try persistFrame(
            data: data,
            width: image.width,
            height: image.height,
            request: request
        )
    }

    func persistFrame(
        data: Data,
        width: Int,
        height: Int,
        request: AdapterFrameCaptureRequest
    ) throws -> ComputerFrameObservation {
        guard data.count <= maximumArtifactBytes else {
            throw ComputerUseBrokerError.adapterFailure(
                "Captured frame exceeded the bounded artifact byte limit."
            )
        }
        do {
            try ComputerUseArtifactSecurity.ensurePrivateDirectory(
                request.artifactDirectory
            )
        } catch {
            throw ComputerUseBrokerError.evidenceFailure(error.localizedDescription)
        }
        let artifactID = screenCaptureArtifactID(
            generation: request.generation,
            frameID: request.frameID
        )
        let artifactURL = request.artifactDirectory
            .appendingPathComponent("\(artifactID).png", isDirectory: false)
        do {
            try data.write(to: artifactURL, options: .atomic)
            try ComputerUseArtifactSecurity.protectPrivateFile(artifactURL)
        } catch {
            throw ComputerUseBrokerError.evidenceFailure(error.localizedDescription)
        }
        let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        return ComputerFrameObservation(
            frameID: request.frameID,
            generation: request.generation,
            target: request.target,
            artifact: ComputerArtifactReference(
                artifactID: artifactID,
                path: artifactURL.path,
                sha256: digest,
                byteCount: data.count,
                mediaType: "image/png",
                width: width,
                height: height,
                adapterKind: adapterKind
            ),
            capturedAt: request.capturedAt,
            redactionApplied: false
        )
    }
}

private func screenCaptureWindowExactlyMatches(
    _ metadata: ScreenCaptureWindowMetadata,
    target: ComputerWindowTarget
) -> Bool {
    metadata.windowID == target.windowID
        && metadata.processIdentifier == target.processIdentifier
        && metadata.bundleIdentifier == target.bundleIdentifier
        && metadata.processLaunchIdentity == target.processLaunchIdentity
        && metadata.windowTitle == target.windowTitle
}

extension ScreenCaptureKitFrameCaptureAdapter {
    func validateProcessIdentity(_ target: ComputerWindowTarget) throws {
        guard let resolvedIdentity = dependencies.resolveProcessIdentity(
            target.processIdentifier
        ), resolvedIdentity == target.processLaunchIdentity else {
            throw ComputerUseBrokerError.targetOutOfScope
        }
    }

    nonisolated static func pngData(for image: CGImage) throws -> Data {
        let data = NSMutableData()
        guard let destination = CGImageDestinationCreateWithData(
            data,
            UTType.png.identifier as CFString,
            1,
            nil
        ) else {
            throw ComputerUseBrokerError.adapterFailure("Could not create a PNG destination.")
        }
        CGImageDestinationAddImage(destination, image, nil)
        guard CGImageDestinationFinalize(destination) else {
            throw ComputerUseBrokerError.adapterFailure("Could not finalize captured PNG data.")
        }
        return data as Data
    }
}

func screenCaptureTargets(
    from windows: [ScreenCaptureWindowMetadata]
) -> [ComputerWindowTarget] {
    var seenWindowIDs = Set<UInt32>()
    let structurallyEligible = windows.compactMap {
        window -> ComputerWindowTarget? in
            guard window.windowID > 0,
                  window.width >= 64,
                  window.height >= 64,
                  window.processIdentifier > 0,
                  window.bundleIdentifier.isEmpty == false,
                  !window.windowTitle.trimmingCharacters(
                      in: .whitespacesAndNewlines
                  ).isEmpty,
                  let launchIdentity = window.processLaunchIdentity,
                  seenWindowIDs.insert(window.windowID).inserted
            else {
                return nil
            }
            return ComputerWindowTarget(
                bundleIdentifier: window.bundleIdentifier,
                processIdentifier: window.processIdentifier,
                processLaunchIdentity: launchIdentity,
                windowID: window.windowID,
                windowTitle: window.windowTitle,
                applicationName: window.applicationName
            )
        }

    // Public AX APIs cannot correlate an AX window back to a ScreenCaptureKit
    // window ID. Semantic actions therefore require one exact title match in
    // the target process. Do not advertise a target that cannot satisfy that
    // invariant at action time.
    let titleCounts = Dictionary(
        grouping: structurallyEligible,
        by: { target in
            SemanticWindowKey(
                processIdentifier: target.processIdentifier,
                windowTitle: target.windowTitle
            )
        }
    ).mapValues(\.count)
    let semanticEligible = structurallyEligible.filter { target in
        titleCounts[
            SemanticWindowKey(
                processIdentifier: target.processIdentifier,
                windowTitle: target.windowTitle
            )
        ] == 1
    }

    return Array(
        semanticEligible
        .sorted { lhs, rhs in
            if lhs.applicationName != rhs.applicationName {
                return lhs.applicationName.localizedCaseInsensitiveCompare(
                    rhs.applicationName
                ) == .orderedAscending
            }
            if lhs.windowTitle != rhs.windowTitle {
                return lhs.windowTitle.localizedCaseInsensitiveCompare(
                    rhs.windowTitle
                ) == .orderedAscending
            }
            return lhs.windowID < rhs.windowID
        }
        .prefix(128)
    )
}

private struct SemanticWindowKey: Hashable {
    let processIdentifier: Int32
    let windowTitle: String
}

func screenCaptureDimensions(
    naturalWidth: Int,
    naturalHeight: Int,
    maximumDimension: Int
) -> ScreenCaptureDimensions {
    let boundedWidth = max(1, naturalWidth)
    let boundedHeight = max(1, naturalHeight)
    let boundedMaximum = max(1, maximumDimension)
    let scale = min(
        1,
        min(
            Double(boundedMaximum) / Double(boundedWidth),
            Double(boundedMaximum) / Double(boundedHeight)
        )
    )
    return ScreenCaptureDimensions(
        width: max(1, Int((Double(boundedWidth) * scale).rounded())),
        height: max(1, Int((Double(boundedHeight) * scale).rounded()))
    )
}

func screenCaptureArtifactID(generation: UInt64, frameID: String) -> String {
    "frame-\(generation)-\(safeScreenCaptureComponent(frameID))"
}

func safeScreenCaptureComponent(_ value: String) -> String {
    let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_"))
    let scalars = value.unicodeScalars.map { allowed.contains($0) ? Character(String($0)) : "_" }
    let component = String(scalars).prefix(96)
    return component.isEmpty ? "unknown" : String(component)
}
