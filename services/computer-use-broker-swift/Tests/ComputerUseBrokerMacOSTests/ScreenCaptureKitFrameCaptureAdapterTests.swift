import AppKit
import ComputerUseBrokerCore
import CoreGraphics
import Foundation
import Testing
@testable import ComputerUseBrokerMacOS

@Suite("ScreenCaptureKit frame capture adapter", .serialized)
struct ScreenCaptureKitFrameCaptureAdapterTests {
    @Test("production runtime initializes AppKit without activating a UI app")
    @MainActor
    func productionRuntimeInitializesHeadlessAppKit() {
        ProductionComputerUseBrokerFactory.prepareProcessForDesktopServices()

        #expect(NSApplication.shared.activationPolicy() == .prohibited)
    }

    @Test("injected permission and enumeration seams fail closed")
    func injectedPermissionAndEnumerationSeamsFailClosed() async {
        let denied = ScreenCaptureKitFrameCaptureAdapter(
            dependencies: dependencies(permissionGranted: false)
        )
        #expect(await denied.permissionState() == .notGranted)
        await expectFrameBrokerError(.permissionDenied("screen_capture")) {
            try await denied.listTargets()
        }
        await expectFrameBrokerError(.permissionDenied("screen_capture")) {
            try await denied.capture(frameRequest(artifactDirectory: temporaryRoot()))
        }

        let enumerationFailure = ScreenCaptureKitFrameCaptureAdapter(
            dependencies: dependencies(
                loadWindows: { _ in
                    throw ScreenCaptureFixtureError.enumeration
                }
            )
        )
        #expect(await enumerationFailure.permissionState() == .granted)
        await expectFrameBrokerError(
            .adapterFailure(
                "ScreenCaptureKit could not enumerate shareable windows: fixture enumeration failed"
            )
        ) {
            try await enumerationFailure.listTargets()
        }
        await expectFrameBrokerError(
            .adapterFailure(
                "ScreenCaptureKit could not enumerate shareable windows: fixture enumeration failed"
            )
        ) {
            try await enumerationFailure.capture(
                frameRequest(artifactDirectory: temporaryRoot())
            )
        }
    }

    @Test("injected live path validates scope, scales, captures, and persists")
    func injectedLivePathValidatesScopeScalesCapturesAndPersists() async throws {
        let root = temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let recorder = ScreenCaptureDependencyRecorder()
        let image = try #require(makeImage(width: 100, height: 50))
        let descriptor = ScreenCaptureWindowDescriptor(
            metadata: metadata(
                windowID: 77,
                width: 800,
                height: 400
            ),
            pointPixelScale: 2,
            handle: nil
        )
        let adapter = ScreenCaptureKitFrameCaptureAdapter(
            maximumDimension: 100,
            dependencies: dependencies(
                loadWindows: { excludingDesktopWindows in
                    await recorder.recordLoad(
                        excludingDesktopWindows: excludingDesktopWindows
                    )
                    return [descriptor]
                },
                captureImage: { candidate, dimensions in
                    await recorder.recordCapture(
                        windowID: candidate.metadata.windowID,
                        dimensions: dimensions
                    )
                    return image
                }
            )
        )

        let targets = try await adapter.listTargets()
        #expect(targets.map(\.windowID) == [77])
        let observation = try await adapter.capture(
            frameRequest(artifactDirectory: root)
        )
        #expect(observation.artifact.width == 100)
        #expect(observation.artifact.height == 50)
        #expect(observation.artifact.mediaType == "image/png")
        #expect(FileManager.default.fileExists(atPath: observation.artifact.path))
        let calls = await recorder.snapshot()
        #expect(calls.excludingDesktopWindows == [true, false, false])
        #expect(calls.capturedWindowIDs == [77])
        #expect(
            calls.dimensions
                == [ScreenCaptureDimensions(width: 100, height: 50)]
        )
    }

    @Test("injected capture refuses stale identity and target mismatch, then maps capture failure")
    func injectedCaptureRefusesScopeAndMapsCaptureFailure() async {
        let descriptor = ScreenCaptureWindowDescriptor(
            metadata: metadata(windowID: 77),
            pointPixelScale: 1,
            handle: nil
        )
        let staleIdentity = ScreenCaptureKitFrameCaptureAdapter(
            dependencies: dependencies(
                loadWindows: { _ in [descriptor] },
                resolveProcessIdentity: { _ in "different-launch" }
            )
        )
        await expectFrameBrokerError(.targetOutOfScope) {
            try await staleIdentity.capture(
                frameRequest(artifactDirectory: temporaryRoot())
            )
        }

        let missingTarget = ScreenCaptureKitFrameCaptureAdapter(
            dependencies: dependencies(
                loadWindows: { _ in
                    [
                        ScreenCaptureWindowDescriptor(
                            metadata: metadata(windowID: 88),
                            pointPixelScale: 1,
                            handle: nil
                        ),
                    ]
                }
            )
        )
        await expectFrameBrokerError(.targetOutOfScope) {
            try await missingTarget.capture(
                frameRequest(artifactDirectory: temporaryRoot())
            )
        }

        let captureFailure = ScreenCaptureKitFrameCaptureAdapter(
            dependencies: dependencies(
                loadWindows: { _ in [descriptor] },
                captureImage: { _, _ in
                    throw ScreenCaptureFixtureError.capture
                }
            )
        )
        await expectFrameBrokerError(
            .adapterFailure(
                "ScreenCaptureKit window capture failed: fixture capture failed"
            )
        ) {
            try await captureFailure.capture(
                frameRequest(artifactDirectory: temporaryRoot())
            )
        }
    }

    @Test("capture candidate enumeration rejects a restarted approved process")
    func captureEnumerationBindsExactProcessLaunchIdentity() async throws {
        let root = temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let recorder = ScreenCaptureDependencyRecorder()
        let image = try #require(makeImage(width: 8, height: 8))
        let restarted = descriptor(
            metadata(
                windowID: 77,
                processLaunchIdentity: "restarted-launch"
            )
        )
        let adapter = ScreenCaptureKitFrameCaptureAdapter(
            dependencies: dependencies(
                loadWindows: { _ in [restarted] },
                captureImage: { candidate, dimensions in
                    await recorder.recordCapture(
                        windowID: candidate.metadata.windowID,
                        dimensions: dimensions
                    )
                    return image
                }
            )
        )

        await expectFrameBrokerError(.targetOutOfScope) {
            try await adapter.capture(
                frameRequest(artifactDirectory: root)
            )
        }
        #expect((await recorder.snapshot()).capturedWindowIDs.isEmpty)
        #expect(FileManager.default.fileExists(atPath: root.path) == false)
    }

    @Test("capture candidate enumeration rejects duplicate exact windows")
    func captureEnumerationRequiresOneExactCandidate() async {
        let root = temporaryRoot()
        defer { try? FileManager.default.removeItem(at: root) }
        let approved = descriptor(metadata(windowID: 77))
        let adapter = ScreenCaptureKitFrameCaptureAdapter(
            dependencies: dependencies(
                loadWindows: { _ in [approved, approved] }
            )
        )

        await expectFrameBrokerError(.targetOutOfScope) {
            try await adapter.capture(frameRequest(artifactDirectory: root))
        }
        #expect(FileManager.default.fileExists(atPath: root.path) == false)
    }

    @Test("capture revalidates process and exact window before persisting")
    func capturePostflightRejectsRestartAndWindowReplacement() async throws {
        let image = try #require(makeImage(width: 8, height: 8))
        let approved = descriptor(metadata(windowID: 77))
        let postflightMutations = [
            descriptor(
                metadata(
                    windowID: 77,
                    processLaunchIdentity: "restarted-launch"
                )
            ),
            descriptor(
                metadata(
                    windowID: 77,
                    windowTitle: "Replacement Window"
                )
            ),
        ]

        for postflightMutation in postflightMutations {
            let root = temporaryRoot()
            defer { try? FileManager.default.removeItem(at: root) }
            let sequence = ScreenCaptureWindowSequence(
                batches: [[approved], [postflightMutation]]
            )
            let recorder = ScreenCaptureDependencyRecorder()
            let adapter = ScreenCaptureKitFrameCaptureAdapter(
                dependencies: dependencies(
                    loadWindows: { _ in
                        await sequence.next()
                    },
                    captureImage: { candidate, dimensions in
                        await recorder.recordCapture(
                            windowID: candidate.metadata.windowID,
                            dimensions: dimensions
                        )
                        return image
                    }
                )
            )

            await expectFrameBrokerError(.targetOutOfScope) {
                try await adapter.capture(
                    frameRequest(artifactDirectory: root)
                )
            }
            #expect(
                (await recorder.snapshot()).capturedWindowIDs == [77]
            )
            #expect(
                FileManager.default.fileExists(atPath: root.path) == false
            )
        }
    }

    @Test("target projection filters unsafe metadata, deduplicates, sorts, and bounds")
    func targetProjectionIsDeterministicAndBounded() {
        let valid = (1 ... 130).map { index in
            metadata(
                windowID: UInt32(index),
                windowTitle: String(format: "Window %03d", 131 - index),
                applicationName: index.isMultiple(of: 2) ? "Beta" : "Alpha"
            )
        }
        let invalid = [
            metadata(windowID: 0),
            metadata(windowID: 200, width: 63),
            metadata(windowID: 201, height: 63),
            metadata(windowID: 202, processIdentifier: 0),
            metadata(windowID: 203, bundleIdentifier: ""),
            metadata(windowID: 204, processLaunchIdentity: nil),
            metadata(windowID: 1),
        ]

        let targets = screenCaptureTargets(from: valid + invalid)

        #expect(targets.count == 128)
        #expect(Set(targets.map(\.windowID)).count == targets.count)
        #expect(targets.allSatisfy { $0.windowID > 0 })
        #expect(targets.first?.applicationName == "Alpha")
        #expect(
            targets == targets.sorted { lhs, rhs in
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
        )

        let windowIDTiebreaker = screenCaptureTargets(
            from: [
                metadata(
                    windowID: 2,
                    processIdentifier: 2,
                    windowTitle: "Same Window",
                    applicationName: "Same App"
                ),
                metadata(
                    windowID: 1,
                    processIdentifier: 1,
                    windowTitle: "Same Window",
                    applicationName: "Same App"
                ),
            ]
        )
        #expect(windowIDTiebreaker.map(\.windowID) == [1, 2])
    }

    @Test("target discovery advertises only AX semantic-action eligible windows")
    func targetDiscoveryRequiresUniqueNonemptyTitlePerProcess() {
        let targets = screenCaptureTargets(
            from: [
                metadata(windowID: 1, windowTitle: ""),
                metadata(windowID: 2, windowTitle: "  \n"),
                metadata(windowID: 3, windowTitle: "Duplicate"),
                metadata(windowID: 4, windowTitle: "Duplicate"),
                metadata(windowID: 5, windowTitle: "Unique"),
                metadata(
                    windowID: 6,
                    processIdentifier: 43,
                    windowTitle: "Duplicate"
                ),
            ]
        )

        #expect(targets.map(\.windowID) == [6, 5])
        #expect(targets.allSatisfy {
            !$0.windowTitle.trimmingCharacters(
                in: .whitespacesAndNewlines
            ).isEmpty
        })
    }

    @Test("live target validation rejects title swaps and ambiguous AX mappings")
    func liveTargetValidationBindsExactSCKIdentityToOneAXTitle() async throws {
        let target = frameRequest(artifactDirectory: temporaryRoot()).target
        let exact = descriptor(metadata(windowID: 77))
        let exactValidator = ScreenCaptureKitWindowTargetValidator(
            dependencies: dependencies(loadWindows: { _ in [exact] })
        )
        try await exactValidator.validate(target)

        let titleSwapped = ScreenCaptureKitWindowTargetValidator(
            dependencies: dependencies(loadWindows: { _ in
                [
                    descriptor(metadata(windowID: 77, windowTitle: "Other")),
                    descriptor(metadata(windowID: 78, windowTitle: "Fixture Window")),
                ]
            })
        )
        await expectFrameBrokerError(.targetOutOfScope) {
            try await titleSwapped.validate(target)
        }

        let ambiguousTitle = ScreenCaptureKitWindowTargetValidator(
            dependencies: dependencies(loadWindows: { _ in
                [exact, descriptor(metadata(windowID: 78))]
            })
        )
        await expectFrameBrokerError(.targetOutOfScope) {
            try await ambiguousTitle.validate(target)
        }

        await expectFrameBrokerError(.permissionDenied("screen_capture")) {
            try await ScreenCaptureKitWindowTargetValidator(
                dependencies: dependencies(permissionGranted: false)
            ).validate(target)
        }
        await expectFrameBrokerError(.targetOutOfScope) {
            try await ScreenCaptureKitWindowTargetValidator(
                dependencies: dependencies(resolveProcessIdentity: { _ in "restarted" })
            ).validate(target)
        }
        await expectFrameBrokerError(where: { error in
            error == .adapterFailure(
                "ScreenCaptureKit could not revalidate the approved window: fixture enumeration failed"
            )
        }) {
            try await ScreenCaptureKitWindowTargetValidator(
                dependencies: dependencies(loadWindows: { _ in
                    throw ScreenCaptureFixtureError.enumeration
                })
            ).validate(target)
        }
    }

    @Test("dimension and artifact helpers preserve bounds and sanitize identity")
    func pureCaptureHelpersAreBounded() {
        #expect(
            screenCaptureDimensions(
                naturalWidth: 800,
                naturalHeight: 600,
                maximumDimension: 4_096
            ) == ScreenCaptureDimensions(width: 800, height: 600)
        )
        #expect(
            screenCaptureDimensions(
                naturalWidth: 8_000,
                naturalHeight: 4_000,
                maximumDimension: 4_000
            ) == ScreenCaptureDimensions(width: 4_000, height: 2_000)
        )
        #expect(
            screenCaptureDimensions(
                naturalWidth: 0,
                naturalHeight: -1,
                maximumDimension: 0
            ) == ScreenCaptureDimensions(width: 1, height: 1)
        )
        #expect(safeScreenCaptureComponent("") == "unknown")
        #expect(safeScreenCaptureComponent("safe_ID-1") == "safe_ID-1")
        #expect(safeScreenCaptureComponent("a/b:c") == "a_b_c")
        #expect(safeScreenCaptureComponent(String(repeating: "x", count: 120)).count == 96)
        #expect(
            screenCaptureArtifactID(generation: 7, frameID: "a/b")
                == "frame-7-a_b"
        )
    }

    @Test("PNG encoding and persistence emit bounded private frame evidence")
    func pngPersistenceIsTypedAndBounded() async throws {
        let image = try #require(makeImage(width: 2, height: 3))
        let png = try ScreenCaptureKitFrameCaptureAdapter.pngData(for: image)
        #expect(png.isEmpty == false)

        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-screen-capture-tests-\(UUID().uuidString)",
            isDirectory: true
        )
        defer { try? FileManager.default.removeItem(at: root) }
        let adapter = ScreenCaptureKitFrameCaptureAdapter(
            maximumDimension: 512,
            maximumArtifactBytes: png.count
        )
        let request = frameRequest(artifactDirectory: root)

        let observation = try await adapter.persistFrame(
            data: png,
            width: image.width,
            height: image.height,
            request: request
        )

        #expect(observation.frameID == request.frameID)
        #expect(observation.generation == request.generation)
        #expect(observation.target == request.target)
        #expect(observation.artifact.byteCount == png.count)
        #expect(observation.artifact.width == 2)
        #expect(observation.artifact.height == 3)
        #expect(observation.artifact.sha256.count == 64)
        #expect(FileManager.default.fileExists(atPath: observation.artifact.path))

        let tooSmall = ScreenCaptureKitFrameCaptureAdapter(
            maximumArtifactBytes: png.count - 1
        )
        await expectFrameBrokerError(
            .adapterFailure(
                "Captured frame exceeded the bounded artifact byte limit."
            )
        ) {
            try await tooSmall.persistFrame(
                data: png,
                width: 2,
                height: 3,
                request: frameRequest(
                    artifactDirectory: root.appendingPathComponent("oversized")
                )
            )
        }
    }

    @Test("persistence maps directory and write failures to evidence errors")
    func persistenceFailuresAreEvidenceErrors() async throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(
            "melix-screen-capture-failure-tests-\(UUID().uuidString)",
            isDirectory: true
        )
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createDirectory(
            at: root,
            withIntermediateDirectories: true
        )
        let adapter = ScreenCaptureKitFrameCaptureAdapter()
        let directoryAsFile = root.appendingPathComponent("not-a-directory")
        try Data("file".utf8).write(to: directoryAsFile)

        await expectFrameBrokerError(where: { error in
            if case .evidenceFailure = error { return true }
            return false
        }) {
            try await adapter.persistFrame(
                data: Data("frame".utf8),
                width: 1,
                height: 1,
                request: frameRequest(artifactDirectory: directoryAsFile)
            )
        }

        let writeFailureRoot = root.appendingPathComponent("write-failure")
        try FileManager.default.createDirectory(
            at: writeFailureRoot,
            withIntermediateDirectories: true
        )
        let request = frameRequest(artifactDirectory: writeFailureRoot)
        let collision = writeFailureRoot.appendingPathComponent(
            "\(screenCaptureArtifactID(generation: request.generation, frameID: request.frameID)).png",
            isDirectory: true
        )
        try FileManager.default.createDirectory(
            at: collision,
            withIntermediateDirectories: true
        )
        await expectFrameBrokerError(where: { error in
            if case .evidenceFailure = error { return true }
            return false
        }) {
            try await adapter.persistFrame(
                data: Data("frame".utf8),
                width: 1,
                height: 1,
                request: request
            )
        }
    }

    @Test("production permission, process identity, and factory seams are typed")
    func productionSeamsAreObservableWithoutRequestingPermission() async {
        let adapter = ScreenCaptureKitFrameCaptureAdapter()
        let permission = await adapter.permissionState()
        #expect(permission == .granted || permission == .notGranted)

        let identity = MacOSProcessIdentity.launchIdentity(
            processIdentifier: 42,
            bundleIdentifier: "io.melix.fixture",
            launchDate: Date(timeIntervalSince1970: 1_700_000_000.125)
        )
        #expect(
            identity
                == "pid:42:launch_ms:1700000000125:bundle:io.melix.fixture"
        )
        let optionalBundleIdentifier: String? = "io.melix.fixture"
        let optionalLaunchDate: Date? = Date(
            timeIntervalSince1970: 1_700_000_000.125
        )
        #expect(
            MacOSProcessIdentity.launchIdentity(
                processIdentifier: 42,
                bundleIdentifier: optionalBundleIdentifier,
                launchDate: optionalLaunchDate
            ) == identity
        )
        #expect(
            MacOSProcessIdentity.launchIdentity(
                processIdentifier: Int32.max
            ) == nil
        )
        #expect(
            MacOSProcessIdentity.launchIdentity(
                processIdentifier: 42,
                bundleIdentifier: nil,
                launchDate: Date()
            ) == nil
        )

        let liveDependencies = ScreenCaptureKitFrameCaptureDependencies.live
        #expect(liveDependencies.resolveProcessIdentity(Int32.max) == nil)
        await expectFrameBrokerError(
            .adapterFailure(
                "ScreenCaptureKit window handle was unavailable."
            )
        ) {
            try await liveDependencies.captureImage(
                ScreenCaptureWindowDescriptor(
                    metadata: metadata(windowID: 77),
                    pointPixelScale: 1,
                    handle: nil
                ),
                ScreenCaptureDimensions(width: 1, height: 1)
            )
        }

        let tieBrokenTargets = screenCaptureTargets(
            from: [
                metadata(
                    windowID: 78,
                    windowTitle: "Same",
                    applicationName: "Same"
                ),
                metadata(
                    windowID: 77,
                    windowTitle: "Same",
                    applicationName: "Same"
                ),
            ]
        )
        #expect(tieBrokenTargets.isEmpty)

        let broker = ProductionComputerUseBrokerFactory.make(
            artifactRoot: FileManager.default.temporaryDirectory
        )
        let permissions = await broker.permissions()
        #expect(
            permissions.screenCapture == .granted
                || permissions.screenCapture == .notGranted
        )
    }
}

private func metadata(
    windowID: UInt32,
    width: CGFloat = 800,
    height: CGFloat = 600,
    processIdentifier: Int32 = 42,
    bundleIdentifier: String = "io.melix.fixture",
    processLaunchIdentity: String? = "fixture-launch",
    windowTitle: String = "Fixture Window",
    applicationName: String = "Fixture"
) -> ScreenCaptureWindowMetadata {
    ScreenCaptureWindowMetadata(
        windowID: windowID,
        width: width,
        height: height,
        processIdentifier: processIdentifier,
        bundleIdentifier: bundleIdentifier,
        processLaunchIdentity: processLaunchIdentity,
        windowTitle: windowTitle,
        applicationName: applicationName
    )
}

private func descriptor(
    _ metadata: ScreenCaptureWindowMetadata
) -> ScreenCaptureWindowDescriptor {
    ScreenCaptureWindowDescriptor(
        metadata: metadata,
        pointPixelScale: 1,
        handle: nil
    )
}

private func frameRequest(
    artifactDirectory: URL
) -> AdapterFrameCaptureRequest {
    AdapterFrameCaptureRequest(
        target: ComputerWindowTarget(
            bundleIdentifier: "io.melix.fixture",
            processIdentifier: 42,
            processLaunchIdentity: "fixture-launch",
            windowID: 77,
            windowTitle: "Fixture Window",
            applicationName: "Fixture"
        ),
        frameID: "frame/fixture",
        generation: 7,
        capturedAt: Date(timeIntervalSince1970: 1_700_000_000),
        artifactDirectory: artifactDirectory
    )
}

private func makeImage(width: Int, height: Int) -> CGImage? {
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    let context = CGContext(
        data: nil,
        width: width,
        height: height,
        bitsPerComponent: 8,
        bytesPerRow: width * 4,
        space: colorSpace,
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
    )
    context?.setFillColor(NSColor.systemTeal.cgColor)
    context?.fill(
        CGRect(x: 0, y: 0, width: width, height: height)
    )
    return context?.makeImage()
}

private func temporaryRoot() -> URL {
    FileManager.default.temporaryDirectory.appendingPathComponent(
        "melix-screen-capture-seam-tests-\(UUID().uuidString)",
        isDirectory: true
    )
}

private func dependencies(
    permissionGranted: Bool = true,
    loadWindows: @escaping @Sendable (Bool) async throws ->
        [ScreenCaptureWindowDescriptor] = { _ in [] },
    captureImage: @escaping @Sendable (
        ScreenCaptureWindowDescriptor,
        ScreenCaptureDimensions
    ) async throws -> CGImage = { _, _ in
        throw ScreenCaptureFixtureError.capture
    },
    resolveProcessIdentity: @escaping @Sendable (Int32) -> String? = { _ in
        "fixture-launch"
    }
) -> ScreenCaptureKitFrameCaptureDependencies {
    ScreenCaptureKitFrameCaptureDependencies(
        permissionCheck: { permissionGranted },
        loadWindows: loadWindows,
        captureImage: captureImage,
        resolveProcessIdentity: resolveProcessIdentity
    )
}

private enum ScreenCaptureFixtureError: LocalizedError {
    case enumeration
    case capture

    var errorDescription: String? {
        switch self {
        case .enumeration:
            "fixture enumeration failed"
        case .capture:
            "fixture capture failed"
        }
    }
}

private actor ScreenCaptureDependencyRecorder {
    private var excludingDesktopWindows: [Bool] = []
    private var capturedWindowIDs: [UInt32] = []
    private var dimensions: [ScreenCaptureDimensions] = []

    func recordLoad(excludingDesktopWindows: Bool) {
        self.excludingDesktopWindows.append(excludingDesktopWindows)
    }

    func recordCapture(
        windowID: UInt32,
        dimensions: ScreenCaptureDimensions
    ) {
        capturedWindowIDs.append(windowID)
        self.dimensions.append(dimensions)
    }

    func snapshot() -> (
        excludingDesktopWindows: [Bool],
        capturedWindowIDs: [UInt32],
        dimensions: [ScreenCaptureDimensions]
    ) {
        (excludingDesktopWindows, capturedWindowIDs, dimensions)
    }
}

private actor ScreenCaptureWindowSequence {
    private var batches: [[ScreenCaptureWindowDescriptor]]

    init(batches: [[ScreenCaptureWindowDescriptor]]) {
        self.batches = batches
    }

    func next() -> [ScreenCaptureWindowDescriptor] {
        guard batches.isEmpty == false else {
            return []
        }
        return batches.removeFirst()
    }
}

private func expectFrameBrokerError<T>(
    _ expected: ComputerUseBrokerError,
    operation: () async throws -> T
) async {
    await expectFrameBrokerError(where: { $0 == expected }, operation: operation)
}

private func expectFrameBrokerError<T>(
    where predicate: (ComputerUseBrokerError) -> Bool,
    operation: () async throws -> T
) async {
    do {
        _ = try await operation()
        Issue.record("Expected ComputerUseBrokerError, but operation succeeded.")
    } catch let error as ComputerUseBrokerError {
        #expect(predicate(error))
    } catch {
        Issue.record("Expected ComputerUseBrokerError, received \(error).")
    }
}
