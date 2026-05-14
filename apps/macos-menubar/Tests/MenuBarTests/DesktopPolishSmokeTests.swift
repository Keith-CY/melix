import AppKit
import Foundation
import SwiftUI
import Testing

@testable import AppMain
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Desktop Polish Smoke", .serialized)
struct DesktopPolishSmokeTests {
    @Test("desktop polish smoke emits canonical metrics")
    @MainActor
    func desktopPolishSmokeEmitsCanonicalMetrics() async throws {
        let smoothedAssistantText = "Assistant response with enough characters to require multiple presentation flushes before completion."
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-desktop-polish-smoke-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let downloadFixture = MenuBarDownloadFixture(
            jobID: "model-ops-download-smoke",
            sourceModel: "melix-dev-text",
            status: "stalled",
            stage: "download",
            pct: 0.5,
            outputDir: "/tmp/melix-downloads/melix-dev-text",
            outputPath: "/tmp/melix-downloads/melix-dev-text/download.artifact",
            partialPath: "/tmp/melix-downloads/melix-dev-text/download.artifact.partial",
            statePath: "/tmp/melix-downloads/melix-dev-text/download.state.json",
            selectedMirror: "https://mirror.example/hf",
            downloadedBytes: 2_048,
            totalBytes: 4_096,
            resumeUsed: true,
            resumeFromBytes: 1_024,
            retryCount: 1,
            stallDetectionCount: 1,
            stallReason: "no_progress_timeout",
            resumeReady: true
        )
        let manifestJSON = makeModelOpsRegistrySnapshotManifestJSON(
            roots: [],
            downloads: [downloadFixture]
        )

        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeDesktopPolishSnapshot(
                models: [ModelCatalog.devTextModel()],
                runtimeSessions: [makeDesktopPolishRuntimeSession()]
            )
        )
        await client.configureModelOperation(
            makeDesktopPolishNamedModelOperationResult(
                operation: "registry_snapshot",
                manifestJSON: manifestJSON
            ),
            forNamedOperation: "registry_snapshot"
        )
        await client.configureScheduledChatEvents([
            .init(delay: .zero, event: .queued(lane: "text.decode.interactive", queuePosition: 0, backpressure: 0)),
            .init(delay: .zero, event: .admitted(lane: "text.decode.interactive", workerID: "swift-text-worker", queueDelayMs: 0.5)),
            .init(delay: .zero, event: .tokenDelta(smoothedAssistantText)),
            .init(delay: .milliseconds(200), event: .completed(
                finishReason: "stop",
                assistantText: smoothedAssistantText,
                reasoningText: ""
            )),
        ])

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let metrics = MenuBarMetricsStore()
        let updateProvider = StubProductInstallStateProvider(
            updateStatusResponse: ProductUpdateStatus(
                summary: "Update available: 0.2.0",
                detail: "Current 0.1.0 on stable",
                isAvailable: true,
                checkSucceeded: true
            )
        )

        let viewModel = RuntimeViewModel(
            client: client,
            metrics: metrics,
            operatorSessionStore: operatorSessionStore,
            productInstallStateProvider: updateProvider
        )
        await viewModel.start()
        await viewModel.refreshDownloadQueueState()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.downloads)
        await viewModel.refreshDownloadQueueState()

        let chatServerSessionID = try #require(viewModel.selectedServerSession?.id)
        viewModel.bindSelectedChatSessionToServer(serverSessionID: chatServerSessionID)
        viewModel.chatComposerText = "Smooth bursty deltas"
        let submitTask = Task { @MainActor in
            await viewModel.submitChatPrompt()
        }

        await submitTask.value
        let assistantEntry = try #require(viewModel.chatTranscript.first { $0.kind == .assistant })
        #expect(assistantEntry.body == smoothedAssistantText)

        #expect(hostedDesktopPolishViewHasSubviews(DesktopDownloadsToolSectionView(viewModel: viewModel)))
        #expect(viewModel.desktopBannerState?.title == "Download Recovery Available")
        #expect(viewModel.desktopSignalStates.contains(where: { $0.title == "Update available: 0.2.0" && $0.isDismissible }))

        viewModel.selectToolSection(.downloads)
        await viewModel.refreshDownloadQueueState()
        try await waitForDesktopPolishCondition("download queue should refresh before persistence") {
            if viewModel.downloadQueue.isEmpty {
                return false
            }
            viewModel.selectToolSection(.downloads)
            return true
        }
        try await waitForDesktopPolishCondition("operator session should persist queue state") {
            viewModel.selectToolSection(.downloads)
            guard let restoredState = try? operatorSessionStore.load() else {
                return false
            }
            return restoredState.downloadQueue.isEmpty == false
                && restoredState.selectedToolSection == .downloads
        }
        _ = try requireDesktopPolishPersistedQueue(
            from: operatorSessionStore,
            expectedSection: .downloads
        )

        let persistedUIData = try Data(contentsOf: melixHome.operatorSessionFileURL)
        let persistedUIPayload = try #require(
            JSONSerialization.jsonObject(with: persistedUIData) as? [String: Any]
        )
        let persistedQueueData = try Data(contentsOf: melixHome.downloadQueueFileURL)
        let persistedQueuePayload = try #require(
            JSONSerialization.jsonObject(with: persistedQueueData) as? [String: Any]
        )
        let persistedQueue = try #require(persistedQueuePayload["download_queue"] as? [[String: Any]])
        #expect(persistedUIPayload["selected_tool_section"] as? String == "downloads")

        let restoredMetrics = MenuBarMetricsStore()
        let restoredViewModel = RuntimeViewModel(
            client: client,
            metrics: restoredMetrics,
            operatorSessionStore: operatorSessionStore,
            productInstallStateProvider: updateProvider
        )
        await restoredViewModel.start()

        let metricsSnapshot = await metrics.snapshot()
        let restoreMetricsSnapshot = await restoredMetrics.snapshot()
        let persistWriteMs = metricsSnapshot["operator.session_persist_write_ms"] ?? -1
        let restoreMs = restoreMetricsSnapshot["operator.session_restore_ms"] ?? -1
        let restoredSelectedToolSection = restoredViewModel.selectedToolSection

        let groundingViewModel = RuntimeViewModel(
            client: client,
            metrics: MenuBarMetricsStore(),
            operatorSessionStore: operatorSessionStore,
            productInstallStateProvider: updateProvider
        )
        await groundingViewModel.start()
        let surfaceGroundingCount = groundedSurfaceCount(for: groundingViewModel)
        let toolSectionGroundingCount = groundedToolSectionCount(for: groundingViewModel)

        let payload: [String: Any] = [
            "chat": [
                "presentation_lag_ms": metricsSnapshot["menu.chat_presentation_lag_ms"] ?? -1,
                "presentation_flush_count": metricsSnapshot["menu.chat_presentation_flush_count"] ?? -1,
            ],
            "signals": [
                "top_banner_title": viewModel.desktopBannerState?.title ?? "",
                "download_recovery_visible": viewModel.desktopSignalStates.contains(where: { $0.title == "Download Recovery Available" }) ? 1 : 0,
                "update_signal_visible": viewModel.desktopSignalStates.contains(where: { $0.title == "Update available: 0.2.0" }) ? 1 : 0,
                "update_signal_dismissible": viewModel.desktopSignalStates.contains(where: { $0.title == "Update available: 0.2.0" && $0.isDismissible }) ? 1 : 0,
            ],
            "persistence": [
                "operator_session_restore_ms": restoreMs,
                "operator_session_persist_write_ms": persistWriteMs,
                "persisted_download_queue_count": persistedQueue.count,
                "restored_download_queue_count": restoredViewModel.downloadQueue.count,
                "restored_selected_tool_section": restoredSelectedToolSection.rawValue,
            ],
            "navigation": [
                "grounded_surface_count": surfaceGroundingCount,
                "grounded_tool_section_count": toolSectionGroundingCount,
            ],
        ]

        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        let text = String(decoding: data, as: UTF8.self)
        print("M15_DESKTOP_POLISH_SMOKE=\(text)")

        #expect((metricsSnapshot["menu.chat_presentation_lag_ms"] ?? -1) >= 0)
        #expect((metricsSnapshot["menu.chat_presentation_flush_count"] ?? 0) > 1)
        #expect(viewModel.desktopBannerState?.title == "Download Recovery Available")
        #expect(persistedQueue.count == 1)
        #expect(restoredViewModel.downloadQueue.count == 1)
        #expect(restoredSelectedToolSection == .downloads)
        #expect(surfaceGroundingCount == DesktopSurface.allCases.count)
        #expect(toolSectionGroundingCount == DesktopToolSection.allCases.count)
    }
}

@MainActor
private func groundedSurfaceCount(for viewModel: RuntimeViewModel) -> Int {
    DesktopSurface.allCases.reduce(into: 0) { count, surface in
        viewModel.selectSurface(surface)
        if hostedDesktopPolishViewHasSubviews(DesktopWorkspaceShellView(viewModel: viewModel)) {
            count += 1
        }
    }
}

@MainActor
private func groundedToolSectionCount(for viewModel: RuntimeViewModel) -> Int {
    let foundation = viewModel.desktopFoundationState
    let sectionChecks: [(DesktopToolSection, Bool)] = [
        (
            .modelsLibrary,
            hostedDesktopPolishViewHasSubviews(
                DesktopModelsTabView(foundation: foundation, viewModel: viewModel)
            )
        ),
        (.downloads, hostedDesktopPolishViewHasSubviews(DesktopDownloadsToolSectionView(viewModel: viewModel))),
        (.training, hostedDesktopPolishViewHasSubviews(DesktopTrainingToolSectionView(viewModel: viewModel))),
        (
            .diagnostics,
            hostedDesktopPolishViewHasSubviews(
                DesktopDiagnosticsToolSectionView(viewModel: viewModel, foundation: foundation)
            )
        ),
        (.logs, hostedDesktopPolishViewHasSubviews(DesktopLogsTabView(foundation: foundation))),
        (.settings, hostedDesktopPolishViewHasSubviews(DesktopSettingsTabView(foundation: foundation))),
    ]

    return sectionChecks.reduce(into: 0) { count, candidate in
        let (section, isGrounded) = candidate
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(section)
        if isGrounded {
            count += 1
        }
    }
}

private func makeDesktopPolishNamedModelOperationResult(
    operation: String,
    manifestJSON: String
) -> Melix_Controlplane_V1_ModelOperationResult {
    var result = Melix_Controlplane_V1_ModelOperationResult()
    result.operation = operation
    result.outputPath = "/tmp/\(operation)"
    result.manifestJson = manifestJSON
    return result
}

private func makeDesktopPolishServerSession() -> DesktopServerSessionState {
    DesktopServerSessionState(
        id: "server-session-1",
        title: "Dev Text Session",
        modelID: "melix-dev-text",
        host: "0.0.0.0",
        port: 18_080,
        effectiveHost: "127.0.0.1",
        effectivePort: 11_434,
        gatewayConfigSourceText: "Operator Override",
        gatewayConfigActiveBinding: true,
        gatewayConfigRequiresRestart: false,
        authMode: .none,
        sharedAccessState: .enabled,
        rateLimitPerMinute: 240,
        timeoutSeconds: 90,
        lifecycle: .running,
        powerState: .active,
        wakeReason: .initialBoot,
        idleTimerSeconds: 0,
        autoSleepEnabled: false,
        lightSleepAfterSeconds: 300,
        deepSleepAfterSeconds: 1_800,
        lastError: "",
        lastKnownModelStateText: "Loaded"
    )
}

private func makeDesktopPolishRuntimeSession() -> Melix_Controlplane_V1_ServerSessionRuntimeState {
    var runtimeSession = Melix_Controlplane_V1_ServerSessionRuntimeState()
    runtimeSession.serverSessionID = "server-session-1"
    runtimeSession.lifecycleState = .ready
    runtimeSession.powerState = .active
    runtimeSession.wakeReason = .initialBoot
    runtimeSession.updatedAtUnixMs = 1_717_171_717
    return runtimeSession
}

private func makeDesktopPolishSnapshot(
    models: [Melix_Controlplane_V1_ModelSummary],
    runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState]
) -> Melix_Controlplane_V1_ServerSnapshot {
    var snapshot = Melix_Controlplane_V1_ServerSnapshot()
    snapshot.serverState = .serverReady
    snapshot.models = models
    snapshot.runtimeSessions = runtimeSessions
    return snapshot
}

@MainActor
private func hostedDesktopPolishViewHasSubviews<Content: View>(_ rootView: Content) -> Bool {
    let controller = NSHostingController(rootView: rootView)
    let view = controller.view
    view.frame = NSRect(x: 0, y: 0, width: 1_200, height: 800)
    view.layoutSubtreeIfNeeded()
    return view.subviews.isEmpty == false
}

@MainActor
private func waitForDesktopPolishCondition(
    _ description: String,
    timeout: Duration = .seconds(5),
    pollInterval: Duration = .milliseconds(10),
    condition: @MainActor @escaping () -> Bool
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if condition() {
            return
        }
        try await Task.sleep(for: pollInterval)
    }
    throw NSError(domain: "DesktopPolishSmokeTests", code: 1, userInfo: [
        NSLocalizedDescriptionKey: description,
    ])
}

private func requireDesktopPolishPersistedQueue(
    from store: OperatorSessionStore,
    expectedSection: DesktopToolSection
) throws -> OperatorSessionState {
    guard let restoredState = try store.load() else {
        throw NSError(domain: "DesktopPolishSmokeTests", code: 1, userInfo: [
            NSLocalizedDescriptionKey: "operator session should exist after queue refresh",
        ])
    }

    guard restoredState.downloadQueue.isEmpty == false,
          restoredState.selectedToolSection == expectedSection
    else {
        throw NSError(domain: "DesktopPolishSmokeTests", code: 1, userInfo: [
            NSLocalizedDescriptionKey: """
            operator session should persist queue state \
            (queue_count=\(restoredState.downloadQueue.count), \
            selected_tool_section=\(restoredState.selectedToolSection.rawValue))
            """,
        ])
    }

    return restoredState
}
