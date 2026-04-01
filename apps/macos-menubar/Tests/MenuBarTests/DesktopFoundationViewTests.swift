import AppKit
import SwiftUI
import Testing

@testable import AppMain
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Desktop Foundation View")
struct DesktopFoundationViewTests {
    @Test("root view renders the desktop foundation shell")
    @MainActor
    func rootViewRendersDesktopFoundationShell() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopFoundationRootView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedSurface == .chat)
    }

    @Test("command center view renders global operator summaries")
    @MainActor
    func commandCenterViewRendersGlobalOperatorSummaries() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(
            DesktopCommandCenterView(
                foundation: viewModel.desktopFoundationState,
                chatSessions: viewModel.chatSessions,
                serverSessions: viewModel.serverSessions
            )
        )

        #expect(view.subviews.isEmpty == false)
    }

    @Test("models tab renders model actions and settings")
    @MainActor
    func modelsTabRendersModelActionsAndSettings() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(
            DesktopModelsTabView(
                foundation: viewModel.desktopFoundationState,
                viewModel: viewModel
            )
        )

        #expect(view.subviews.isEmpty == false)
    }

    @Test("models tab renders residency memory alerts when a model is guard-blocked")
    @MainActor
    func modelsTabRendersResidencyMemoryAlerts() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            makeMenuBarModelSummary(
                modelID: "melix-dev-guarded",
                state: .modelFailed,
                transitionReason: "memory_budget_exceeded",
                estimatedBytes: 512 * 1024 * 1024,
                inflightRequests: 2
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let foundation = viewModel.desktopFoundationState
        let guardedModel = try #require(foundation.models.first)
        let view = hostView(
            DesktopModelsTabView(
                foundation: foundation,
                viewModel: viewModel
            )
        )

        #expect(view.subviews.isEmpty == false)
        #expect(guardedModel.memoryAlertText == "Memory protection • Memory budget exceeded")
        #expect(guardedModel.memoryText.contains("2 inflight"))
    }

    @Test("models tab buttons dispatch latency profile and load actions")
    @MainActor
    func modelsTabButtonsDispatchActions() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopModelsTabView(
            foundation: viewModel.desktopFoundationState,
            viewModel: viewModel
        )
        let model = try #require(viewModel.primaryModel)
        await tab.applyLatencyProfile(to: model)
        await tab.toggleModelLoad(for: model)

        let actions = await client.recordedActions
        #expect(actions.contains("settings:melix-dev-text"))
        #expect(actions.contains("load:melix-dev-text"))
    }

    @Test("tools tab renders model information and operations state")
    @MainActor
    func toolsTabRendersModelInformationAndOperationsState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.inspectPrimaryModel()
        await viewModel.runDoctor()
        await viewModel.runBench()
        await viewModel.quantizePrimaryModel()

        let view = hostView(DesktopToolsTabView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
    }

    @Test("tools tab renders OCR profile metadata when selected model info includes OCR defaults")
    @MainActor
    func toolsTabRendersOCRProfileMetadata() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-dev-ocr"
        model.kind = "ocr"
        model.state = .modelDiscovered
        model.settings.alias = "Melix Dev OCR"
        model.settings.ext["ocr_prompt_profile_id"] = "ocr-default-v1"
        model.settings.ext["ocr_sampling_profile_id"] = "ocr-deterministic"
        model.settings.ext["ocr_stop_sequences"] = "<ocr:end>"
        snapshot.models = [model]

        var info = Melix_Controlplane_V1_ModelInfo()
        info.ok = true
        info.modelKind = "ocr"
        info.maxContext = 4096
        info.supportedParsers = ["text"]
        info.supportedModalities = ["image"]

        await client.configureSnapshot(snapshot)
        await client.configureModelInfo(info)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.fetchModelInfo(modelID: "melix-dev-ocr")

        let view = hostView(DesktopToolsTabView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedModelInfo?.ocrPromptProfileText == "ocr-default-v1")
        #expect(viewModel.selectedModelInfo?.ocrSamplingProfileText == "ocr-deterministic")
        #expect(viewModel.selectedModelInfo?.ocrStopSequencesText == "<ocr:end>")
    }

    @Test("tools tab buttons dispatch inspect diagnostics bench and model operations")
    @MainActor
    func toolsTabButtonsDispatchActions() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeRegistrySnapshotManifest(
                    publishedRepo: "",
                    targetRepo: "melix/adapters/melix-dev-adapter"
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopToolsTabView(viewModel: viewModel)
        await tab.inspectPrimaryModel()
        await tab.refreshModelOpsProductState()
        await tab.runDoctor()
        await tab.runBench()
        await tab.quantizePrimaryModel()
        await tab.trainPrimaryModel()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeRegistrySnapshotManifest(
                    publishedRepo: "",
                    targetRepo: "melix/adapters/melix-dev-adapter",
                    activationStatus: "activated",
                    derivedModelID: "melix-dev-text-lora-adapter",
                    derivedModelPath: "/tmp/melix-derived/model"
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        await tab.activateLatestAdapter()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeRegistrySnapshotManifest(
                    publishedRepo: "melix/adapters/melix-dev-adapter",
                    targetRepo: "melix/adapters/melix-dev-adapter",
                    activationStatus: "activated",
                    derivedModelID: "melix-dev-text-lora-adapter",
                    derivedModelPath: "/tmp/melix-derived/model"
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        await tab.publishLatestAdapter()
        await tab.downloadPrimaryModel()
        await tab.uploadPrimaryModel()

        let actions = await client.recordedActions
        #expect(actions.contains("info:melix-dev-text"))
        #expect(actions.contains("operation:registry_snapshot:melix-dev-text"))
        #expect(actions.contains("doctor"))
        #expect(actions.contains("bench"))
        #expect(actions.contains("operation:quantize:melix-dev-text"))
        #expect(actions.contains("operation:train_lora:melix-dev-text"))
        #expect(actions.contains("operation:activate_adapter:melix-dev-text"))
        #expect(actions.contains("operation:download:melix-dev-text"))
        #expect(actions.contains("operation:upload:melix-dev-text"))
        #expect(viewModel.selectedModelInfo?.modelID == "melix-dev-text")
        #expect(viewModel.lastDoctorReport?.markdown.contains("Melix Doctor") == true)
        #expect(viewModel.lastBenchReport?.markdown.contains("Melix Bench") == true)
        #expect(viewModel.lastModelOperation?.operation == "upload")
        #expect(viewModel.adapterPackages.first?.adapterName == "melix-dev-adapter")
        #expect(viewModel.adapterPackages.first?.activationStatusText == "Activated")
        #expect(viewModel.trainingHistory.first?.jobID == "model-ops-0001")
    }

    @Test("tools tab renders pending adapter registry and history rows")
    @MainActor
    func toolsTabRendersPendingAdapterRegistryRows() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makePendingRegistrySnapshotManifest()
            ),
            forNamedOperation: "registry_snapshot"
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        let view = hostView(DesktopToolsTabView(viewModel: viewModel))
        let adapter = try #require(viewModel.adapterPackages.first)
        let trainingJob = try #require(viewModel.trainingHistory.first)

        #expect(view.subviews.isEmpty == false)
        #expect(adapter.statusText == "Queued for publish")
        #expect(adapter.activationStatusText == "Pending activation")
        #expect(adapter.responseOnlyEnabled)
        #expect(adapter.gradientCheckpointingEnabled)
        #expect(adapter.publishedRepo.isEmpty)
        #expect(trainingJob.statusText == "Unknown")
        #expect(trainingJob.stageText == "write_manifest • 42%")
    }

    @Test("tools tab renders empty tooling state without a primary model")
    @MainActor
    func toolsTabRendersWithoutPrimaryModel() async throws {
        let client = EmptyToolsSnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopToolsTabView(viewModel: viewModel))

        #expect(viewModel.primaryModel == nil)
        #expect(viewModel.adapterPackages.isEmpty)
        #expect(viewModel.trainingHistory.isEmpty)
        #expect(view.subviews.isEmpty == false)
    }

    @Test("dashboard settings logs bench and api tabs render from foundation state")
    @MainActor
    func supportingTabsRenderFromFoundationState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await client.sendLog(level: "info", message: "operator-log")
        try await Task.sleep(for: .milliseconds(20))

        let foundation = viewModel.desktopFoundationState
        let dashboard = hostView(DesktopDashboardTabView(foundation: foundation))
        let settings = hostView(DesktopSettingsTabView(foundation: foundation))
        let logs = hostView(DesktopLogsTabView(foundation: foundation))
        let bench = hostView(DesktopBenchTabView(foundation: foundation))
        let chat = hostView(DesktopChatTabView(viewModel: viewModel))
        let api = hostView(DesktopAPIReferenceTabView(foundation: foundation))
        let hasConnectionCard = foundation.dashboardCards.contains { row in
            row.id == "connection" && row.value == "Connected"
        }
        let hasResidencyCard = foundation.dashboardCards.contains { row in
            row.id == "residency"
        }
        let hasEvictionsCard = foundation.dashboardCards.contains { row in
            row.id == "evictions"
        }
        let hasGuardCard = foundation.dashboardCards.contains { row in
            row.id == "guards"
        }
        let hasConnectionSetting = foundation.settings.contains { row in
            row.key == "Connection" && row.value == "Connected"
        }

        #expect(dashboard.subviews.isEmpty == false)
        #expect(hasConnectionCard)
        #expect(hasResidencyCard)
        #expect(hasEvictionsCard)
        #expect(hasGuardCard)
        #expect(hasConnectionSetting)
        #expect(settings.subviews.isEmpty == false)
        #expect(logs.subviews.isEmpty == false)
        #expect(bench.subviews.isEmpty == false)
        #expect(chat.subviews.isEmpty == false)
        #expect(api.subviews.isEmpty == false)
    }

    @Test("chat tab submit and clear actions dispatch through the view model")
    @MainActor
    func chatTabDispatchesViewModelActions() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopChatTabView(viewModel: viewModel)
        viewModel.chatComposerText = "Hello from SwiftUI"
        await viewModel.submitChatPrompt()
        viewModel.clearChatTranscript()

        let view = hostView(tab)

        #expect(await client.recordedActions.contains("chat:melix-dev-text"))
        #expect(viewModel.chatTranscript.isEmpty)
        #expect(view.subviews.isEmpty == false)
    }

    @Test("chat tab renders populated transcript rows and runtime metadata")
    @MainActor
    func chatTabRendersPopulatedTranscriptRowsAndRuntimeMetadata() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.chatComposerText = "Render the transcript"

        await viewModel.submitChatPrompt()

        let view = hostView(DesktopChatTabView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .user }))
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .assistant }))
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .reasoning }))
        #expect(viewModel.chatTranscript.contains(where: { $0.kind == .tool }))
        #expect(viewModel.lastChatRequestID == "chat-request-1")
        #expect(viewModel.lastChatUsageText == "12 prompt • 24 completion")
    }

    @Test("chat tab renders terminal error entries")
    @MainActor
    func chatTabRendersTerminalErrorEntries() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureChatEvents([
            .failed(code: "runtime_error", message: "worker failed"),
        ])
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.chatComposerText = "Render the error path"

        await viewModel.submitChatPrompt()

        let view = hostView(DesktopChatTabView(viewModel: viewModel))
        let renderedErrorEntry = viewModel.chatTranscript.contains { entry in
            entry.kind == .error && entry.body == "worker failed"
        }

        #expect(view.subviews.isEmpty == false)
        #expect(renderedErrorEntry)
        #expect(viewModel.chatStatusText == "Failed • runtime_error")
    }

    @Test("chat session sidebar renders the empty state when no chat sessions exist")
    @MainActor
    func chatSessionSidebarRendersTheEmptyStateWhenNoChatSessionsExist() async throws {
        let client = EmptyToolsSnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let view = hostView(DesktopChatSessionSidebar(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.chatSessions.isEmpty)
    }

    @Test("chat session workspace renders the server required state when no server is running")
    @MainActor
    func chatSessionWorkspaceRendersTheServerRequiredStateWhenNoServerIsRunning() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await viewModel.stopSelectedServerSession()
        viewModel.chatComposerText = "Need a running server"
        await viewModel.submitChatPrompt()

        let view = hostView(
            DesktopChatSessionWorkspace(
                viewModel: viewModel,
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.selectedChatServerSession?.isRunning == false)
        #expect(viewModel.chatStatusText == "No Server Session")
    }

    @Test("image tab renders image jobs and artifact previews")
    @MainActor
    func imageTabRendersImageJobsAndArtifacts() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-preview",
                requestID: "req-image-preview",
                operation: "image_generate",
                artifacts: [makeMenuBarImageArtifact(jobID: "job-image-preview", storageURI: "/tmp/preview.png")]
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopImageTabView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.imageJobs.count == 1)
        #expect(viewModel.selectedImageJob?.artifacts.first?.storageUri == "/tmp/preview.png")
    }

    @Test("chat session inspector renders export metadata when a session has been exported")
    @MainActor
    func chatSessionInspectorRendersExportMetadataWhenASessionHasBeenExported() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.chatComposerText = "Export the transcript"
        await viewModel.submitChatPrompt()
        let exportPath = try #require(viewModel.exportSelectedChatSession())

        let view = hostView(DesktopChatSessionInspector(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(FileManager.default.fileExists(atPath: exportPath))
        #expect(viewModel.selectedChatSession?.exportPath == exportPath)
    }

    @Test("image workspace renders edit mode fields directly")
    @MainActor
    func imageWorkspaceRendersEditModeFieldsDirectly() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.imagePromptText = "Edit a cover"
        viewModel.imageEditSourceURL = "file:///tmp/source.png"
        viewModel.imageEditMaskURL = "file:///tmp/mask.png"

        let view = hostView(
            DesktopImageWorkspace(
                viewModel: viewModel,
                selectedMode: .constant(.edit),
                showsSidebar: .constant(true),
                showsInspector: .constant(true)
            )
        )

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.imageEditSourceURL == "file:///tmp/source.png")
        #expect(viewModel.imageEditMaskURL == "file:///tmp/mask.png")
    }

    @Test("image tab dispatches generate and edit actions through the view model")
    @MainActor
    func imageTabDispatchesGenerateAndEditActions() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopImageTabView(viewModel: viewModel)
        viewModel.imagePromptText = "Generate a cover"
        await viewModel.submitImageGeneration()
        viewModel.imagePromptText = "Edit the cover"
        viewModel.imageEditSourceURL = "file:///tmp/source.png"
        await viewModel.submitImageEdit()

        let view = hostView(tab)

        #expect(await client.recordedActions.contains("image.generate:melix-dev-image"))
        #expect(await client.recordedActions.contains("image.edit:melix-dev-image"))
        #expect(view.subviews.isEmpty == false)
    }

    @Test("image tab dispatches cancel for the selected cancelable job")
    @MainActor
    func imageTabDispatchesCancelForSelectedJob() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-running",
                requestID: "req-image-running",
                operation: "image_generate",
                state: .imageJobRunning
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let tab = DesktopImageTabView(viewModel: viewModel)
        tab.cancelSelectedJob()
        try await Task.sleep(for: .milliseconds(20))
        let view = hostView(tab)

        #expect(await client.recordedActions.contains("cancel:req-image-running"))
        #expect(view.subviews.isEmpty == false)
    }

    @Test("image tab renders completed jobs without dispatching cancel")
    @MainActor
    func imageTabRendersCompletedJobsWithoutCancelDispatch() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-complete",
                requestID: "req-image-complete",
                operation: "image_generate",
                state: .imageJobCompleted
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopImageTabView(viewModel: viewModel))
        await viewModel.cancelSelectedImageJob()

        #expect(view.subviews.isEmpty == false)
        #expect(await client.recordedActions.contains("cancel:req-image-complete") == false)
        #expect(viewModel.imageStatusText != "Canceling")
        #expect(viewModel.imageStatusText != "Failed")
    }

    @Test("image tab renders empty-state placeholders when no jobs are available")
    @MainActor
    func imageTabRendersEmptyStatePlaceholders() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            {
                var model = Melix_Controlplane_V1_ModelSummary()
                model.modelID = "melix-dev-text"
                model.kind = "text"
                model.state = .modelWarm
                model.features = ["chat"]
                return model
            }(),
            makeMenuBarImageModelSummary(),
        ]
        snapshot.imageJobs = []
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let view = hostView(DesktopImageTabView(viewModel: viewModel))

        #expect(view.subviews.isEmpty == false)
        #expect(viewModel.imageJobs.isEmpty)
        #expect(viewModel.selectedImageJob == nil)
    }

    @Test("dashboard renders residency and memory protection summaries from control-plane truth")
    @MainActor
    func dashboardRendersResidencyAndMemoryProtectionSummaries() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [
            makeMenuBarModelSummary(
                modelID: "melix-dev-text",
                state: .modelPinned,
                pinRequested: true,
                pinned: true,
                ttlSeconds: 900,
                estimatedBytes: 768 * 1024 * 1024,
                memoryPolicy: .memoryResidencyPinned
            ),
            makeMenuBarModelSummary(
                modelID: "melix-dev-guarded",
                state: .modelFailed,
                transitionReason: "memory_budget_exceeded",
                estimatedBytes: 512 * 1024 * 1024,
                inflightRequests: 1
            ),
        ]
        snapshot.metrics.values = [
            "control_plane.model_eviction_ttl_count": 1,
            "control_plane.model_eviction_lru_same_capability_count": 1,
            "control_plane.model_eviction_last_pinned_protected_count": 1,
        ]
        snapshot.recentErrors = [
            {
                var error = Melix_Controlplane_V1_RecentError()
                error.code = "memory_budget_exceeded"
                error.message = "Model load rejected by memory budget headroom."
                return error
            }(),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let foundation = viewModel.desktopFoundationState
        let view = hostView(DesktopDashboardTabView(foundation: foundation))
        let hasResidencyCard = foundation.dashboardCards.contains { row in
            row.id == "residency" && row.value == "1 pinned"
        }
        let hasGuardCard = foundation.dashboardCards.contains { row in
            row.id == "guards" && row.value == "1"
        }
        let hasGuardedModel = foundation.models.contains { row in
            row.modelID == "melix-dev-guarded" && row.memoryAlertText.contains("Memory protection")
        }

        #expect(view.subviews.isEmpty == false)
        #expect(hasResidencyCard)
        #expect(hasGuardCard)
        #expect(hasGuardedModel)
    }

    @Test("dashboard renders an empty residency section when no models are discovered")
    @MainActor
    func dashboardRendersEmptyResidencySection() async throws {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = []
        let foundation = DesktopFoundationState.build(
            statusTitle: "Melix Ready",
            serverStateText: "Ready",
            connectionStateText: "Connected",
            connectionDetailText: "Empty snapshot",
            snapshot: snapshot,
            protocolVersion: "melix.controlplane.v1",
            serverVersion: "0.1.0",
            daemonInstanceID: "daemon-empty",
            features: ["xpc", "models"],
            lastError: nil,
            recentEvents: []
        )
        let view = hostView(DesktopDashboardTabView(foundation: foundation))
        let hasResidencyCard = foundation.dashboardCards.contains { row in
            row.id == "residency" && row.value == "0 pinned"
        }

        #expect(view.subviews.isEmpty == false)
        #expect(foundation.models.isEmpty)
        #expect(hasResidencyCard)
    }
}

@MainActor
private func hostView<Content: View>(_ rootView: Content) -> NSView {
    let controller = NSHostingController(rootView: rootView)
    let view = controller.view
    view.frame = NSRect(x: 0, y: 0, width: 1200, height: 800)
    view.layoutSubtreeIfNeeded()
    return view
}

private func makeNamedModelOperationResult(
    operation: String,
    outputPath: String,
    manifestJSON: String
) -> Melix_Controlplane_V1_ModelOperationResult {
    var result = Melix_Controlplane_V1_ModelOperationResult()
    result.ok = true
    result.operation = operation
    result.jobID = "job-\(operation)"
    result.stage = "completed"
    result.pct = 1
    result.outputPath = outputPath
    result.manifestJson = manifestJSON
    return result
}

private func makeMenuBarModelSummary(
    modelID: String,
    state: Melix_Controlplane_V1_ModelState,
    transitionReason: String = "",
    pinRequested: Bool = false,
    pinned: Bool = false,
    ttlSeconds: UInt32 = 0,
    estimatedBytes: UInt64 = 0,
    inflightRequests: UInt64 = 0,
    memoryPolicy: Melix_Controlplane_V1_MemoryResidencyPolicy = .memoryResidencyEvictable
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = "text"
    model.state = state
    model.features = ["chat"]
    model.maxContext = 8192
    model.pinned = pinned
    model.inflightRequests = inflightRequests
    model.estimatedBytes = estimatedBytes
    model.settings.alias = "Melix \(modelID)"
    model.settings.pinOnLoad = pinRequested
    model.settings.ttlSeconds = ttlSeconds
    model.settings.memoryPolicy = memoryPolicy
    model.settings.defaultAccelerationMode = .baseline
    model.residency.pinRequested = pinRequested
    model.residency.pinned = pinned
    model.residency.ttlSeconds = ttlSeconds
    model.residency.policy = memoryPolicy
    model.residency.transitionReason = transitionReason
    return model
}

private func makeRegistrySnapshotManifest(
    publishedRepo: String,
    targetRepo: String,
    activationStatus: String = "pending_activation",
    derivedModelID: String = "",
    derivedModelPath: String = "",
    status: String? = nil
) -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "jobs": [
        {
          "job_id": "model-ops-0001",
          "operation": "train_lora",
          "source_model": "melix-dev-text",
          "status": "completed",
          "stage": "write_artifact",
          "pct": 1.0,
          "output_path": "/tmp/melix-train-lora/train_lora.adapter.json",
          "manifest": {
            "adapter_name": "melix-dev-adapter",
            "dataset_uri": "datasets/melix-dev",
            "target_repo": "\#(targetRepo)"
          }
        }
      ],
      "adapters": [
        {
          "adapter_id": "melix-dev-adapter@model-ops-0001",
          "job_id": "model-ops-0001",
          "adapter_name": "melix-dev-adapter",
          "source_model": "melix-dev-text",
          "dataset_uri": "datasets/melix-dev",
          "output_path": "/tmp/melix-train-lora/train_lora.adapter.json",
          "activation_status": "\#(activationStatus)",
          "derived_model_id": "\#(derivedModelID)",
          "derived_model_path": "\#(derivedModelPath)",
          "exportable_state": "ready",
          "published_state": "\#(publishedRepo.isEmpty ? "not_published" : "published")",
          "target_repo": "\#(targetRepo)",
          "published_repo": "\#(publishedRepo)",
          "status": "\#(status ?? (publishedRepo.isEmpty ? (activationStatus == "activated" ? "activated" : "completed") : "published"))",
          "response_only": true,
          "gradient_checkpointing": false,
          "training_duration_ms": 1420.0,
          "activation_duration_ms": \#(derivedModelID.isEmpty ? "0.0" : "321.0"),
          "adapter_publish_ms": 118.0
        }
      ],
      "derived_models": [
        {
          "model_id": "\#(derivedModelID)",
          "model_path": "\#(derivedModelPath)",
          "adapter_set_hash": "\#(derivedModelID.isEmpty ? "" : "adapter-alpha")",
          "source_model": "melix-dev-text",
          "activation_mode": "\#(derivedModelID.isEmpty ? "" : "fused_derived_model")",
          "status": "\#(derivedModelID.isEmpty ? "" : "activated")"
        }
      ]
    }
    """#
}

private func makePendingRegistrySnapshotManifest() -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "jobs": [
        {
          "job_id": "model-ops-0008",
          "operation": "train_lora",
          "source_model": "melix-dev-text",
          "status": "",
          "stage": "write_manifest",
          "pct": 0.42,
          "output_path": "/tmp/melix-train-lora/pending.adapter.json",
          "manifest": {
            "adapter_name": "pending-adapter",
            "dataset_uri": "datasets/pending",
            "target_repo": ""
          }
        }
      ],
      "adapters": [
        {
          "adapter_id": "pending-adapter@model-ops-0008",
          "job_id": "model-ops-0008",
          "adapter_name": "pending-adapter",
          "source_model": "melix-dev-text",
          "dataset_uri": "datasets/pending",
          "output_path": "/tmp/melix-train-lora/pending.adapter.json",
          "activation_status": "pending_activation",
          "derived_model_id": "",
          "derived_model_path": "",
          "exportable_state": "ready",
          "published_state": "not_published",
          "target_repo": "",
          "published_repo": "",
          "status": "queued_for_publish",
          "response_only": true,
          "gradient_checkpointing": true,
          "training_duration_ms": 950,
          "activation_duration_ms": 0,
          "adapter_publish_ms": 0
        }
      ],
      "derived_models": []
    }
    """#
}

private actor EmptyToolsSnapshotControlPlaneXPCClient: ControlPlaneXPCClient {
    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "daemon-empty-tools"
        response.snapshot = Melix_Controlplane_V1_ServerSnapshot()
        response.snapshot.serverState = .serverReady
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
        throw ControlPlaneChatExecutionError.unavailable
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        return snapshot
    }

    func loadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        return Melix_Controlplane_V1_ModelSummary()
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        return Melix_Controlplane_V1_ModelSummary()
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        _ = modelID
        _ = values
        return Melix_Controlplane_V1_ModelSummary()
    }

    func modelInfo(modelID: String) async throws -> Melix_Controlplane_V1_ModelInfo {
        _ = modelID
        return Melix_Controlplane_V1_ModelInfo()
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
        return Melix_Controlplane_V1_ModelOperationResult()
    }
}
