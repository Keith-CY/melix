import Foundation
import MelixControlPlaneCore
import Testing

@testable import AppMain

@Suite("App Screenshot Capture", .serialized)
struct AppScreenshotCaptureTests {
    @Test("default cases cover all workspace surfaces, chat composer states, tool sections, and command center")
    func defaultCasesCoverAllAppSurfaces() {
        let cases = AppScreenshotCaptureCase.defaultCases
        let workspaceSurfaces = cases.compactMap { captureCase -> String? in
            guard case .workspace(let surface) = captureCase else {
                return nil
            }
            return surface.rawValue
        }
        let toolSections = cases.compactMap { captureCase -> String? in
            guard case .toolSection(let section) = captureCase else {
                return nil
            }
            return section.rawValue
        }
        let chatComposerStates = cases.compactMap { captureCase -> String? in
            guard case .chatComposer(let state) = captureCase else {
                return nil
            }
            return state.id
        }
        let commandCenterCount = cases.filter {
            if case .commandCenter = $0 {
                return true
            }
            return false
        }.count

        #expect(workspaceSurfaces.sorted() == DesktopSurface.routableWorkspaceCases.map(\.rawValue).sorted())
        #expect(toolSections.sorted() == DesktopToolSection.allCases.map(\.rawValue).sorted())
        #expect(chatComposerStates.sorted() == AppScreenshotChatComposerState.allCases.map(\.id).sorted())
        #expect(commandCenterCount == 1)
    }

    @Test("config environment normalizes overrides and falls back to deterministic defaults")
    func configEnvironmentNormalizesOverridesAndDefaults() {
        let configured = AppScreenshotCaptureConfig(environment: [
            "MELIX_APP_SCREENSHOT_OUTPUT_DIR": " /tmp/melix-screenshots \n",
            "MELIX_APP_SCREENSHOT_APP_PATH": " /tmp/Melix.app ",
            "MELIX_APP_SCREENSHOT_WIDTH": "1280",
            "MELIX_APP_SCREENSHOT_HEIGHT": "720",
        ])
        let fallback = AppScreenshotCaptureConfig(environment: [
            "MELIX_APP_SCREENSHOT_OUTPUT_DIR": " \n",
            "MELIX_APP_SCREENSHOT_WIDTH": "0",
            "MELIX_APP_SCREENSHOT_HEIGHT": "invalid",
        ])

        #expect(configured.outputDirectoryPath == "/tmp/melix-screenshots")
        #expect(configured.appPath == "/tmp/Melix.app")
        #expect(configured.width == 1280)
        #expect(configured.height == 720)
        #expect(fallback.outputDirectoryPath.contains("melix-app-screenshots-"))
        #expect(fallback.appPath == "")
        #expect(fallback.width == 1440)
        #expect(fallback.height == 960)
    }

    @Test("capture and render errors expose localized descriptions")
    func captureAndRenderErrorsExposeLocalizedDescriptions() throws {
        let outputDirectoryError = AppScreenshotCaptureError.invalidOutputDirectory("")
        let renderFailureError = AppScreenshotCaptureError.renderFailed("bitmap unavailable")
        let bitmapError = MelixSwiftUIScreenshotRenderError.bitmapAllocationFailed
        let pngError = MelixSwiftUIScreenshotRenderError.pngEncodingFailed

        #expect(outputDirectoryError.localizedDescription == "Invalid app screenshot output directory: ")
        #expect(renderFailureError.localizedDescription == "App screenshot capture failed: bitmap unavailable")
        #expect(bitmapError.localizedDescription == "NSHostingView could not allocate a bitmap snapshot.")
        #expect(pngError.localizedDescription == "Bitmap snapshot could not be encoded as PNG.")
    }

    @Test("runner writes manifest and png screenshots")
    @MainActor
    func runnerWritesManifestAndPNGScreenshots() async throws {
        let outputURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-app-screenshot-tests-\(UUID().uuidString)", isDirectory: true)
        defer {
            try? FileManager.default.removeItem(at: outputURL)
        }

        let runner = AppScreenshotCaptureRunner(
            config: AppScreenshotCaptureConfig(
                outputDirectoryPath: outputURL.path,
                appPath: "/tmp/Melix.app",
                width: 640,
                height: 420
            ),
            cases: [.workspace(.models), .toolSection(.downloads), .chatComposer(.offlineProvider), .commandCenter]
        )

        let manifest = try await runner.run()
        let manifestURL = URL(fileURLWithPath: manifest.manifestPath)
        let firstScreenshot = try #require(manifest.screenshots.first)
        let screenshot = try #require(manifest.screenshots.last)
        let screenshotURL = URL(fileURLWithPath: screenshot.path)
        let screenshotData = try Data(contentsOf: screenshotURL)
        let manifestJSON = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: manifestURL)) as? [String: Any]
        )

        #expect(manifest.schemaVersion == "melix.app_screenshots.v1")
        #expect(manifest.appPath == "/tmp/Melix.app")
        #expect(manifest.width == 640)
        #expect(manifest.height == 420)
        #expect(manifest.screenshots.map(\.id) == [
            "workspace-models",
            "workspace-models-downloads",
            "chat-composer-offline-provider",
            "command-center",
        ])
        #expect(firstScreenshot.surface == "Models")
        #expect(firstScreenshot.toolSection == "")
        #expect(screenshot.id == "command-center")
        #expect(screenshot.surface == "")
        #expect(screenshotURL.path.hasSuffix("command-center.png"))
        #expect(Array(screenshotData.prefix(8)) == [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        #expect(manifestJSON["schema_version"] as? String == "melix.app_screenshots.v1")
        #expect(manifestJSON["screenshot_root"] as? String == manifest.screenshotRoot)
    }

    @Test("runner rejects an empty output directory before writing artifacts")
    @MainActor
    func runnerRejectsEmptyOutputDirectory() async {
        let runner = AppScreenshotCaptureRunner(
            config: AppScreenshotCaptureConfig(outputDirectoryPath: ""),
            cases: [.workspace(.chat)]
        )

        await #expect(throws: AppScreenshotCaptureError.self) {
            try await runner.run()
        }
    }

    @Test("screenshot fixture client provides deterministic app data")
    @MainActor
    func screenshotFixtureClientProvidesDeterministicAppData() async throws {
        let client = AppScreenshotCaptureControlPlaneClient()
        let handshake = try await client.handshake()
        let stream = await client.subscribe(lastSeenSeq: 42)
        var iterator = stream.makeAsyncIterator()
        let firstEvent = await iterator.next()
        let snapshot = try await client.serverSnapshot()
        let fallbackModel = try await client.loadModel(modelID: "missing-model")
        let unloadedModel = try await client.unloadModel(modelID: "melix-dev-text")
        let updatedModel = try await client.updateModelSettings(modelID: "melix-dev-text", values: ["alias": "Text"])
        let modelInfo = try await client.modelInfo(modelID: "melix-dev-text")

        #expect(handshake.protocolVersion == "melix.controlplane.v1")
        #expect(handshake.daemonInstanceID == "screenshot-daemon")
        #expect(firstEvent == nil)
        #expect(snapshot.models.map(\.modelID) == ["melix-dev-text", "melix-dev-image", "melix-dev-vision"])
        #expect(fallbackModel.modelID == "melix-dev-text")
        #expect(unloadedModel.modelID == "melix-dev-text")
        #expect(updatedModel.modelID == "melix-dev-text")
        #expect(modelInfo.ok)
        #expect(modelInfo.supportedModalities == ["text"])

        await #expect(throws: ControlPlaneXPCClientError.self) {
            try await client.startChat(
                ControlPlaneChatRequest(
                    modelID: "melix-dev-text",
                    messages: [.init(role: "user", content: "hello")]
                )
            )
        }
        await #expect(throws: ControlPlaneXPCClientError.self) {
            try await client.runModelOperation(
                modelID: "melix-dev-text",
                operation: "quantize",
                outputDir: "/tmp/model",
                quantProfileID: "q4",
                weightQuant: "q4",
                kvQuant: "q4",
                ext: [:]
            )
        }
    }

    @Test("live phase 8 renderer writes a png through the shared SwiftUI renderer")
    @MainActor
    func livePhase8RendererWritesPNGThroughSharedRenderer() async throws {
        let outputURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-phase8-renderer-\(UUID().uuidString)")
            .appendingPathComponent("workspace.png")
        defer {
            try? FileManager.default.removeItem(at: outputURL.deletingLastPathComponent().deletingLastPathComponent())
        }
        let viewModel = RuntimeViewModel(client: AppScreenshotCaptureControlPlaneClient())
        await viewModel.start()

        try LivePhase8WindowUIRenderer().render(
            viewModel: viewModel,
            to: outputURL,
            size: CGSize(width: 360, height: 240)
        )

        let data = try Data(contentsOf: outputURL)
        #expect(Array(data.prefix(8)) == [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
    }
}
