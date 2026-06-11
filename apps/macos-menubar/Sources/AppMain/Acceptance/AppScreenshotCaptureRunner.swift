import AppKit
import Foundation
import MelixControlPlaneCore
import MelixControlPlaneProtocol
import SwiftUI

private let appScreenshotCaptureSchemaVersion = "melix.app_screenshots.v1"

public enum AppScreenshotCaptureError: Error, LocalizedError {
    case invalidOutputDirectory(String)
    case renderFailed(String)

    public var errorDescription: String? {
        switch self {
        case .invalidOutputDirectory(let path):
            return "Invalid app screenshot output directory: \(path)"
        case .renderFailed(let reason):
            return "App screenshot capture failed: \(reason)"
        }
    }
}

public struct AppScreenshotCaptureConfig: Equatable, Sendable {
    public let outputDirectoryPath: String
    public let appPath: String
    public let width: Int
    public let height: Int

    public init(
        outputDirectoryPath: String,
        appPath: String = "",
        width: Int = 1440,
        height: Int = 960
    ) {
        self.outputDirectoryPath = outputDirectoryPath
        self.appPath = appPath
        self.width = width
        self.height = height
    }

    public init(environment: [String: String]) {
        self.outputDirectoryPath = Self.normalized(environment["MELIX_APP_SCREENSHOT_OUTPUT_DIR"])
            ?? Self.defaultOutputDirectoryPath()
        self.appPath = Self.normalized(environment["MELIX_APP_SCREENSHOT_APP_PATH"]) ?? ""
        self.width = Self.positiveInt(environment["MELIX_APP_SCREENSHOT_WIDTH"]) ?? 1440
        self.height = Self.positiveInt(environment["MELIX_APP_SCREENSHOT_HEIGHT"]) ?? 960
    }

    private static func normalized(_ value: String?) -> String? {
        guard let value else {
            return nil
        }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func positiveInt(_ value: String?) -> Int? {
        guard let normalized = normalized(value), let parsed = Int(normalized), parsed > 0 else {
            return nil
        }
        return parsed
    }

    private static func defaultOutputDirectoryPath() -> String {
        FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-app-screenshots-\(UUID().uuidString)", isDirectory: true)
            .path
    }
}

public enum AppScreenshotCaptureCase: Equatable, Sendable {
    public enum ChatState: String, Equatable, Sendable {
        case ready = "ready"
        case noProvider = "no-provider"
        case noModel = "no-model"
    }

    case chat(ChatState)
    case workspace(DesktopSurface)
    case toolSection(DesktopToolSection)
    case commandCenter

    public static var defaultCases: [AppScreenshotCaptureCase] {
        [
            .chat(.ready),
            .chat(.noProvider),
            .chat(.noModel),
            .workspace(.server),
            .workspace(.models),
            .workspace(.workflows),
            .workspace(.settings),
        ]
    }

    public var id: String {
        switch self {
        case .chat(let state):
            return "workspace-chat-\(state.rawValue)"
        case .workspace(let surface):
            return "workspace-\(Self.slug(surface.rawValue))"
        case .toolSection(let section):
            return "workspace-\(Self.slug(section.domain.surface.rawValue))-\(Self.slug(section.rawValue))"
        case .commandCenter:
            return "command-center"
        }
    }

    var kind: String {
        switch self {
        case .chat:
            return "chat_state"
        case .workspace:
            return "workspace"
        case .toolSection:
            return "tool_section"
        case .commandCenter:
            return "command_center"
        }
    }

    var surface: DesktopSurface? {
        switch self {
        case .chat:
            return .chat
        case .workspace(let surface):
            return surface
        case .toolSection(let section):
            return section.domain.surface
        case .commandCenter:
            return nil
        }
    }

    var toolSection: DesktopToolSection? {
        switch self {
        case .toolSection(let section):
            return section
        case .chat, .workspace, .commandCenter:
            return nil
        }
    }

    var chatState: ChatState? {
        switch self {
        case .chat(let state):
            return state
        case .workspace, .toolSection, .commandCenter:
            return nil
        }
    }

    private static func slug(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics
        var result = ""
        var previousWasSeparator = false
        for scalar in value.lowercased().unicodeScalars {
            if allowed.contains(scalar) {
                result.unicodeScalars.append(scalar)
                previousWasSeparator = false
            } else if !previousWasSeparator {
                result.append("-")
                previousWasSeparator = true
            }
        }
        return result.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
    }
}

public struct AppScreenshotCaptureEntry: Codable, Equatable, Sendable {
    public let id: String
    public let kind: String
    public let surface: String
    public let toolSection: String
    public let path: String
    public let renderMs: Double
}

public struct AppScreenshotCaptureManifest: Codable, Equatable, Sendable {
    public let schemaVersion: String
    public let manifestPath: String
    public let appPath: String
    public let outputDirectoryPath: String
    public let screenshotRoot: String
    public let width: Int
    public let height: Int
    public let screenshots: [AppScreenshotCaptureEntry]
}

@MainActor
public final class AppScreenshotCaptureRunner {
    private let config: AppScreenshotCaptureConfig
    private let makeViewModel: @MainActor () -> RuntimeViewModel
    private let renderer: MelixSwiftUIScreenshotRenderer
    private let fileManager: FileManager
    private let cases: [AppScreenshotCaptureCase]

    public init(
        config: AppScreenshotCaptureConfig,
        viewModel: RuntimeViewModel? = nil,
        renderer: MelixSwiftUIScreenshotRenderer = MelixSwiftUIScreenshotRenderer(),
        fileManager: FileManager = .default,
        cases: [AppScreenshotCaptureCase] = AppScreenshotCaptureCase.defaultCases
    ) {
        self.config = config
        self.makeViewModel = {
            viewModel ?? RuntimeViewModel(client: AppScreenshotCaptureControlPlaneClient())
        }
        self.renderer = renderer
        self.fileManager = fileManager
        self.cases = cases
    }

    public func run() async throws -> AppScreenshotCaptureManifest {
        let outputDirectoryPath = config.outputDirectoryPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !outputDirectoryPath.isEmpty else {
            throw AppScreenshotCaptureError.invalidOutputDirectory(config.outputDirectoryPath)
        }
        let outputRoot = URL(fileURLWithPath: outputDirectoryPath, isDirectory: true)
        let screenshotRoot = outputRoot.appendingPathComponent("screenshots", isDirectory: true)
        let manifestURL = outputRoot.appendingPathComponent("screenshot_manifest.json")
        let size = CGSize(width: config.width, height: config.height)

        try fileManager.createDirectory(at: screenshotRoot, withIntermediateDirectories: true)

        var entries: [AppScreenshotCaptureEntry] = []
        for captureCase in cases {
            let viewModel = makeViewModel()
            await viewModel.start()
            apply(captureCase, to: viewModel)
            let screenshotURL = screenshotRoot.appendingPathComponent("\(captureCase.id).png")
            let startedAt = Date()
            do {
                switch captureCase {
                case .commandCenter:
                    try renderer.render(
                        DesktopCommandCenterView(viewModel: viewModel),
                        to: screenshotURL,
                        size: size
                    )
                case .chat, .workspace, .toolSection:
                    try renderer.render(
                        AppScreenshotCaptureWindowShellView(viewModel: viewModel),
                        to: screenshotURL,
                        size: size
                    )
                }
            } catch {
                throw AppScreenshotCaptureError.renderFailed(String(describing: error))
            }

            entries.append(
                AppScreenshotCaptureEntry(
                    id: captureCase.id,
                    kind: captureCase.kind,
                    surface: captureCase.surface?.rawValue ?? "",
                    toolSection: captureCase.toolSection?.rawValue ?? "",
                    path: screenshotURL.path,
                    renderMs: (Date().timeIntervalSince(startedAt) * 1_000_000).rounded() / 1_000
                )
            )
        }

        let manifest = AppScreenshotCaptureManifest(
            schemaVersion: appScreenshotCaptureSchemaVersion,
            manifestPath: manifestURL.path,
            appPath: config.appPath,
            outputDirectoryPath: outputRoot.path,
            screenshotRoot: screenshotRoot.path,
            width: config.width,
            height: config.height,
            screenshots: entries
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.keyEncodingStrategy = .convertToSnakeCase
        try encoder.encode(manifest).write(to: manifestURL)
        return manifest
    }

    private func apply(_ captureCase: AppScreenshotCaptureCase, to viewModel: RuntimeViewModel) {
        switch captureCase {
        case .chat(let state):
            applyChatState(state, to: viewModel)
        case .workspace(let surface):
            viewModel.selectSurface(surface)
        case .toolSection(let section):
            viewModel.selectToolSection(section)
        case .commandCenter:
            break
        }
    }

    private func applyChatState(_ state: AppScreenshotCaptureCase.ChatState, to viewModel: RuntimeViewModel) {
        viewModel.applyAppScreenshotChatState(state)
    }
}

private struct AppScreenshotCaptureWindowShellView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                Spacer(minLength: 92)
                DesktopWorkspaceTitleBarTabsView(viewModel: viewModel)
                Spacer(minLength: 12)
                DesktopWorkspaceTitleBarActionsView(viewModel: viewModel)
            }
            .frame(height: 44)
            .padding(.horizontal, 14)
            .background(MelixDesignTokens.Palette.backgroundSurface.color)
            .overlay(alignment: .bottom) {
                Rectangle()
                    .fill(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline))
                    .frame(height: 1)
            }

            DesktopWorkspaceShellView(viewModel: viewModel)
        }
        .frame(minWidth: 980, minHeight: 680)
        .background(MelixDesignTokens.Palette.backgroundBase.color)
        .tint(MelixDesignTokens.accent)
    }
}

// Capture-only fixture client. The screenshot runner drives it from the main actor,
// but the actor still owns ControlPlaneXPCClient serialization; revisit this boundary
// before reusing the fixture outside deterministic off-screen capture.
actor AppScreenshotCaptureControlPlaneClient: ControlPlaneXPCClient {
    private let snapshot: Melix_Controlplane_V1_ServerSnapshot

    init() {
        self.snapshot = Self.makeSnapshot()
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "screenshot-daemon"
        response.features = ["xpc", "models", "metrics", "cache-metadata", "image-jobs"]
        response.snapshot = snapshot
        return response
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        _ = lastSeenSeq
        return AsyncStream { continuation in
            continuation.finish()
        }
    }

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        _ = request
        throw unimplemented("chat")
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        snapshot
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        return snapshot.models.first(where: { $0.modelID == modelID }) ?? Self.makeModelSummary(
            modelID: "melix-dev-text",
            kind: "text",
            features: ["chat"],
            state: .modelWarm
        )
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        // Fixture: treat unload as a no-op and return the model's current state.
        try await loadModel(modelID: modelID)
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = values
        return try await loadModel(modelID: modelID)
    }

    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        _ = modelID
        var info = Melix_Controlplane_V1_ModelInfo()
        info.ok = true
        info.modelKind = "text"
        info.maxContext = 8192
        info.supportedModalities = ["text"]
        info.supportedParsers = ["text", "json"]
        return info
    }

    func runModelOperation(
        modelID: String,
        operation: String,
        outputDir: String,
        quantProfileID: String,
        weightQuant: String,
        kvQuant: String,
        ext: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelOperationResult {
        _ = modelID
        _ = operation
        _ = outputDir
        _ = quantProfileID
        _ = weightQuant
        _ = kvQuant
        _ = ext
        throw unimplemented("model operation")
    }

    private func unimplemented(_ operation: String) -> Error {
        ControlPlaneXPCClientError.requestFailed(
            code: "screenshot_capture_fixture",
            message: "App screenshot capture fixture does not execute \(operation)."
        )
    }

    private static func makeSnapshot() -> Melix_Controlplane_V1_ServerSnapshot {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            makeModelSummary(
                modelID: "melix-dev-text",
                kind: "text",
                features: ["chat", "responses", "evaluation"],
                state: .modelWarm
            ),
            makeModelSummary(
                modelID: "melix-dev-image",
                kind: "image",
                features: ["image-generation", "image-edit"],
                state: .modelDiscovered
            ),
        ]
        snapshot.queues = makeQueueSummary()
        snapshot.cache = makeCacheSummary()
        snapshot.metrics = makeMetricsSummary()
        snapshot.providers = [makeRuntimeSession()]
        return snapshot
    }

    private static func makeModelSummary(
        modelID: String,
        kind: String,
        features: [String],
        state: Melix_Controlplane_V1_ModelState
    ) -> Melix_Controlplane_V1_ModelSummary {
        var settings = Melix_Controlplane_V1_ModelSettings()
        settings.alias = modelID == "melix-dev-text" ? "Melix Text" : "Melix Image"
        settings.memoryPolicy = .memoryResidencyEvictable
        settings.defaultAccelerationMode = .baseline

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = modelID
        model.kind = kind
        model.features = features
        model.maxContext = 8192
        model.state = state
        model.settings = settings
        return model
    }

    private static func makeQueueSummary() -> Melix_Controlplane_V1_QueueSummary {
        var queue = Melix_Controlplane_V1_QueueSummary()
        queue.activeRequests = 1
        queue.queuedRequests = 1
        queue.backpressure = 0.12

        var decode = Melix_Controlplane_V1_QueueLaneSummary()
        decode.laneID = "text.decode.interactive"
        decode.laneClass = "interactive-decode"
        decode.activeRequests = 1
        decode.priorityScore = 100

        var prefill = Melix_Controlplane_V1_QueueLaneSummary()
        prefill.laneID = "text.prefill.hot"
        prefill.laneClass = "hot-prefill"
        prefill.queuedRequests = 1
        prefill.priorityScore = 120

        queue.lanes = [decode, prefill]
        return queue
    }

    private static func makeCacheSummary() -> Melix_Controlplane_V1_CacheSummary {
        var cache = Melix_Controlplane_V1_CacheSummary()
        cache.l1Bytes = 16 * 1024 * 1024
        cache.l2Bytes = 64 * 1024 * 1024
        cache.l1HitRate = 0.72
        cache.l2HitRate = 0.35
        cache.activeMode = .tiered
        cache.cacheRoot = "/tmp/melix-cache"
        cache.supportedModes = [.tiered, .rotating, .hybrid]
        return cache
    }

    private static func makeMetricsSummary() -> Melix_Controlplane_V1_MetricsSummary {
        var metrics = Melix_Controlplane_V1_MetricsSummary()
        metrics.values = [
            "http.translation_ms": 2.4,
            "http.stream_first_event_ms": 18.8,
            "requests.inflight": 1,
        ]
        return metrics
    }

    private static func makeRuntimeSession() -> Melix_Controlplane_V1_ProviderRuntimeState {
        var runtimeSession = Melix_Controlplane_V1_ProviderRuntimeState()
        runtimeSession.providerID = "screenshot-local-server"
        runtimeSession.lifecycleState = .ready
        runtimeSession.powerState = .active
        runtimeSession.wakeReason = .initialBoot
        runtimeSession.updatedAtUnixMs = 1_717_171_717
        return runtimeSession
    }
}
