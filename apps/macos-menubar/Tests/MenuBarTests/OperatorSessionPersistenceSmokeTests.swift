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
                selectedToolSection: .jobs,
                selectedServerSessionID: "server-session-shared",
                selectedRuntimeJobID: "job-shared-selection",
                serverSessions: [
                    DesktopServerSessionState(
                        id: "server-session-shared",
                        title: "Shared Server",
                        modelID: "melix-dev-vlm",
                        servingDefaults: DesktopServerServingDefaultsState(
                            maxConcurrentRequests: 3,
                            concurrentProcessingEnabled: false,
                            prefillBatchSize: 1,
                            completionBatchSize: 1,
                            accelerationProfile: "long-session",
                            accelerationMode: "sparse_prefill",
                            draftModelID: "melix-dev-draft",
                            numDraftTokens: 2
                        ),
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
        let restoredAppState = try #require(try appStore.load())
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
        #expect(sharedState.selectedToolSectionID == "jobs")
        #expect(sharedState.selectedRuntimeJobID == "job-shared-selection")
        #expect(restoredAppState.selectedToolSection == .jobs)
        #expect(restoredAppState.selectedRuntimeJobID == "job-shared-selection")
        #expect(sharedState.selectedServerSessionID == "server-session-shared")
        #expect(sharedState.serverSessions.first?.modelID == "melix-dev-vlm")
        #expect(sharedState.serverSessions.first?.servingDefaults.accelerationProfile == "long-session")
        #expect(sharedState.serverSessions.first?.servingDefaults.accelerationMode == "sparse_prefill")
        #expect(sharedState.serverSessions.first?.servingDefaults.maxConcurrentRequests == 3)
        #expect(sharedState.serverSessions.first?.servingDefaults.concurrentProcessingEnabled == false)
        #expect(sharedState.serverSessions.first?.servingDefaults.prefillBatchSize == 1)
        #expect(sharedState.serverSessions.first?.servingDefaults.completionBatchSize == 1)
        #expect(restoredAppState.serverSessions.first?.servingDefaults.accelerationProfile == "long-session")
        #expect(restoredAppState.serverSessions.first?.servingDefaults.effectiveAccelerationProfile == "long-session")
        #expect(restoredAppState.serverSessions.first?.servingDefaults.accelerationProfileIntent ==
            "Repeated-session serving with bounded batching and baseline decode."
        )
        #expect(sharedState.serverSessions.first?.autoSleepEnabled == true)
        #expect(sharedState.serverSessions.first?.lightSleepAfterSeconds == 60)
        #expect(sharedState.serverSessions.first?.deepSleepAfterSeconds == 600)
        #expect(sharedState.registryRoots == ["/tmp/models-a", "/tmp/models-b"])
        #expect(sharedState.paneVisibility.first(where: { $0.surfaceID == "server" })?.showsInspector == true)
        #expect(sharedState.paneVisibility.first(where: { $0.surfaceID == "api" })?.showsSidebar == false)
        #expect(uiPayload["selected_runtime_job_id"] as? String == "job-shared-selection")
        #expect(uiPayload["server_sessions"] == nil)
        #expect(uiPayload["registry_roots"] == nil)
        #expect((serverSessionsPayload["server_sessions"] as? [[String: Any]])?.first?["id"] as? String == "server-session-shared")
        let persistedServingDefaults = try #require(
            (serverSessionsPayload["server_sessions"] as? [[String: Any]])?.first?["serving_defaults"] as? [String: Any]
        )
        #expect(persistedServingDefaults["acceleration_profile"] as? String == "long-session")
        #expect(persistedServingDefaults["acceleration_mode"] as? String == "sparse_prefill")
        #expect(modelRootsPayload["registry_roots"] as? [String] == ["/tmp/models-a", "/tmp/models-b"])
    }

    @Test("app operator session state codable preserves selected runtime job")
    func appOperatorSessionStateCodablePreservesSelectedRuntimeJob() throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let state = OperatorSessionState(
            schemaVersion: 1,
            selectedSurface: .tools,
            selectedToolSection: .jobs,
            selectedServerSessionID: "",
            selectedRuntimeJobID: "job-codable-selection",
            serverSessions: [],
            paneVisibility: []
        )

        var decodedState = try JSONDecoder().decode(OperatorSessionState.self, from: encoder.encode(state))
        #expect(decodedState.schemaVersion == 6)
        #expect(decodedState.selectedToolSection == .jobs)
        #expect(decodedState.selectedRuntimeJobID == "job-codable-selection")
        #expect(decodedState.paneVisibility.count == DesktopPaneVisibilityState.defaultStates.count)

        decodedState.schemaVersion = 1
        decodedState.ensurePaneVisibilityDefaults()
        #expect(decodedState.schemaVersion == 6)
        #expect(decodedState.paneVisibility.count == DesktopPaneVisibilityState.defaultStates.count)

        let legacyJSON = Data(
            #"""
            {
              "schema_version": 5,
              "selected_surface": "tools",
              "selected_tool_section": "jobs",
              "selected_server_session_id": "",
              "server_sessions": []
            }
            """#.utf8
        )
        let legacyState = try JSONDecoder().decode(OperatorSessionState.self, from: legacyJSON)
        #expect(legacyState.schemaVersion == 6)
        #expect(legacyState.selectedRuntimeJobID.isEmpty)
    }

    @Test("app operator session store round-trips batch runs tool section")
    func appOperatorSessionStoreRoundTripsBatchRunsToolSection() throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-batch-runs-store-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let appStore = OperatorSessionStore(melixHome: melixHome)

        try appStore.save(
            OperatorSessionState(
                selectedSurface: .tools,
                selectedToolSection: .batchRuns,
                selectedServerSessionID: "",
                serverSessions: []
            )
        )

        let restoredState = try #require(try appStore.load())
        let uiPayload = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: melixHome.operatorSessionFileURL)) as? [String: Any]
        )
        #expect(restoredState.selectedToolSection == .batchRuns)
        #expect(uiPayload["selected_tool_section"] as? String == "batchRuns")
    }

    @Test("shared operator session store migrates legacy monolithic state")
    func sharedOperatorSessionStoreMigratesLegacyMonolithicState() throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-legacy-store-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let sharedStore = MelixOperatorSessionStore(melixHome: melixHome)
        let legacyState = MelixOperatorSessionState(
            selectedSurfaceID: "server",
            selectedToolSectionID: "downloads",
            selectedServerSessionID: "legacy-server",
            serverSessions: [
                MelixOperatorServerSessionState(
                    id: "legacy-server",
                    title: "Legacy Server",
                    modelID: "melix-dev-text",
                    lifecycle: .running
                )
            ],
            dismissedBannerIDs: ["legacy-banner"],
            downloadQueue: [
                MelixOperatorDownloadQueueEntryState(
                    jobID: "job-legacy-download",
                    sourceModel: "mlx-community/Legacy",
                    status: "running",
                    stage: "download",
                    pct: 42,
                    outputDir: "/tmp/legacy-output",
                    outputPath: "/tmp/legacy-output/model",
                    partialPath: "/tmp/legacy-output/model.partial",
                    statePath: "/tmp/legacy-output/download.state.json",
                    selectedMirror: "hf",
                    downloadedBytes: 42,
                    totalBytes: 100,
                    resumeUsed: false,
                    resumeFromBytes: 0,
                    retryCount: 1,
                    stallDetectionCount: 0,
                    stallReason: "",
                    resumeReady: true
                )
            ],
            registryRoots: ["/tmp/legacy-models-a", "/tmp/legacy-models-b"]
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        encoder.dateEncodingStrategy = .iso8601
        try melixHome.writeAtomically(try encoder.encode(legacyState), to: melixHome.operatorSessionFileURL)

        #expect(FileManager.default.fileExists(atPath: melixHome.serverSessionsFileURL.path) == false)
        #expect(FileManager.default.fileExists(atPath: melixHome.modelRootsFileURL.path) == false)
        #expect(FileManager.default.fileExists(atPath: melixHome.downloadQueueFileURL.path) == false)

        let restoredState = try #require(try sharedStore.load())
        let uiPayload = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: melixHome.operatorSessionFileURL)) as? [String: Any]
        )
        let serverSessionsPayload = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: melixHome.serverSessionsFileURL)) as? [String: Any]
        )
        let modelRootsPayload = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: melixHome.modelRootsFileURL)) as? [String: Any]
        )
        let downloadQueuePayload = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: melixHome.downloadQueueFileURL)) as? [String: Any]
        )

        #expect(restoredState.selectedSurfaceID == "server")
        #expect(restoredState.selectedToolSectionID == "downloads")
        #expect(restoredState.selectedServerSessionID == "legacy-server")
        #expect(restoredState.serverSessions.first?.title == "Legacy Server")
        #expect(restoredState.registryRoots == ["/tmp/legacy-models-a", "/tmp/legacy-models-b"])
        #expect(restoredState.downloadQueue.first?.jobID == "job-legacy-download")
        #expect(uiPayload["server_sessions"] == nil)
        #expect(uiPayload["registry_roots"] == nil)
        #expect(uiPayload["download_queue"] == nil)
        #expect((serverSessionsPayload["server_sessions"] as? [[String: Any]])?.first?["id"] as? String == "legacy-server")
        #expect(modelRootsPayload["registry_roots"] as? [String] == ["/tmp/legacy-models-a", "/tmp/legacy-models-b"])
        #expect((downloadQueuePayload["download_queue"] as? [[String: Any]])?.first?["job_id"] as? String == "job-legacy-download")
    }
}

private func posixPermissions(at url: URL) throws -> Int {
    let attributes = try FileManager.default.attributesOfItem(atPath: url.path)
    return try #require(attributes[.posixPermissions] as? Int)
}
