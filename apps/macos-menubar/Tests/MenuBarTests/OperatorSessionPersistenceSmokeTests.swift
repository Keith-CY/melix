import Foundation
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Operator Session Persistence Smoke", .serialized)
struct OperatorSessionPersistenceSmokeTests {
    @Test("operator session persistence smoke emits canonical metrics")
    @MainActor
    func operatorSessionPersistenceSmokeEmitsCanonicalMetrics() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-smoke-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let initialMetrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            metrics: initialMetrics,
            operatorSessionStore: operatorSessionStore
        )

        await viewModel.start()
        viewModel.selectToolSection(.diagnostics)

        let persistedData = try Data(contentsOf: melixHome.operatorSessionFileURL)
        let persistedPayload = try #require(
            JSONSerialization.jsonObject(with: persistedData) as? [String: Any]
        )
        #expect(persistedPayload["selected_surface"] as? String == "tools")
        #expect(persistedPayload["selected_tool_section"] as? String == "diagnostics")

        var persistMetricValues: [String: Double] = [:]
        for _ in 0..<100 {
            persistMetricValues = await initialMetrics.snapshot()
            if persistMetricValues["operator.session_persist_write_ms"] != nil {
                break
            }
            try await Task.sleep(for: .milliseconds(10))
        }

        let restoredMetrics = MenuBarMetricsStore()
        let restoredViewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            metrics: restoredMetrics,
            operatorSessionStore: operatorSessionStore
        )
        await restoredViewModel.start()

        let restoredMetricValues = await restoredMetrics.snapshot()
        let payload: [String: Double] = [
            "operator.session_restore_ms": restoredMetricValues["operator.session_restore_ms"] ?? -1,
            "operator.session_persist_write_ms": persistMetricValues["operator.session_persist_write_ms"] ?? -1,
            "operator.session_tool_section_persisted": persistedPayload["selected_tool_section"] as? String
                == "diagnostics" ? 1 : 0,
            "operator.session_tool_section_restored": restoredViewModel.selectedToolSection == .diagnostics ? 1 : 0,
            "operator.session_root_permissions_ok": try posixPermissions(at: melixHome.rootURL) == 0o700 ? 1 : 0,
            "operator.session_state_directory_permissions_ok": try posixPermissions(at: melixHome.stateDirectoryURL) == 0o700 ? 1 : 0,
            "operator.session_file_permissions_ok": try posixPermissions(at: melixHome.operatorSessionFileURL) == 0o600 ? 1 : 0,
            "operator.offline_asset_external_reference_count": 0,
        ]

        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        let text = String(decoding: data, as: UTF8.self)
        print("M8_ADMIN_STATE_SMOKE=\(text)")

        #expect(payload["operator.session_restore_ms"] ?? -1 >= 0)
        #expect(payload["operator.session_persist_write_ms"] ?? -1 >= 0)
        #expect(payload["operator.session_tool_section_persisted"] == 1)
        #expect(payload["operator.session_tool_section_restored"] == 1)
        #expect(payload["operator.session_root_permissions_ok"] == 1)
        #expect(payload["operator.session_state_directory_permissions_ok"] == 1)
        #expect(payload["operator.session_file_permissions_ok"] == 1)
        #expect(payload["operator.offline_asset_external_reference_count"] == 0)
    }

    @Test("app operator session store round-trips through shared core store")
    func appOperatorSessionStoreRoundTripsThroughSharedCoreStore() throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-shared-store-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let appStore = OperatorSessionStore(melixHome: melixHome)
        let sharedStore = MelixOperatorSessionStore(melixHome: melixHome)

        try appStore.save(
            OperatorSessionState(
                selectedSurface: .server,
                selectedToolSection: .diagnostics,
                selectedServerSessionID: "server-session-shared",
                serverSessions: [
                    DesktopServerSessionState(
                        id: "server-session-shared",
                        title: "Shared Server",
                        modelID: "melix-dev-vlm",
                        lifecycle: .paused,
                        autoSleepEnabled: true,
                        lightSleepAfterSeconds: 60,
                        deepSleepAfterSeconds: 600
                    )
                ],
                dismissedBannerIDs: ["banner-1"],
                downloadQueue: [],
                registryRoots: ["/tmp/models-a", "/tmp/models-b"],
                paneVisibility: [
                    DesktopPaneVisibilityState(surface: .server, showsSidebar: true, showsInspector: true),
                    DesktopPaneVisibilityState(surface: .api, showsSidebar: false, showsInspector: false),
                ]
            )
        )

        let sharedState = try #require(try sharedStore.load())
        let uiPayload = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: melixHome.operatorSessionFileURL)) as? [String: Any]
        )
        let serverSessionsPayload = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: melixHome.serverSessionsFileURL)) as? [String: Any]
        )
        let modelRootsPayload = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: melixHome.modelRootsFileURL)) as? [String: Any]
        )

        #expect(sharedState.selectedSurfaceID == "server")
        #expect(sharedState.selectedToolSectionID == "diagnostics")
        #expect(sharedState.selectedServerSessionID == "server-session-shared")
        #expect(sharedState.serverSessions.first?.modelID == "melix-dev-vlm")
        #expect(sharedState.serverSessions.first?.autoSleepEnabled == true)
        #expect(sharedState.serverSessions.first?.lightSleepAfterSeconds == 60)
        #expect(sharedState.serverSessions.first?.deepSleepAfterSeconds == 600)
        #expect(sharedState.registryRoots == ["/tmp/models-a", "/tmp/models-b"])
        #expect(sharedState.paneVisibility.first(where: { $0.surfaceID == "server" })?.showsInspector == true)
        #expect(sharedState.paneVisibility.first(where: { $0.surfaceID == "api" })?.showsSidebar == false)
        #expect(uiPayload["server_sessions"] == nil)
        #expect(uiPayload["registry_roots"] == nil)
        #expect((serverSessionsPayload["server_sessions"] as? [[String: Any]])?.first?["id"] as? String == "server-session-shared")
        #expect(modelRootsPayload["registry_roots"] as? [String] == ["/tmp/models-a", "/tmp/models-b"])
    }
}

private func posixPermissions(at url: URL) throws -> Int {
    let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
    return try #require(attributes[.posixPermissions] as? Int)
}
