import Foundation
import SwiftUI
import Testing

@testable import AppMain
import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Runtime View Model", .serialized)
struct RuntimeViewModelTests {
    @Test("start hydrates the initial snapshot into app state")
    @MainActor
    func startHydratesInitialSnapshot() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()

        #expect(viewModel.statusTitle == "Melix Ready")
        #expect(viewModel.primaryModel?.modelID == "melix-dev-text")
        #expect(viewModel.primaryModel?.stateText == "Discovered")
        #expect(viewModel.primaryModel?.actionTitle == "Load")
        #expect(viewModel.selectedSurface == .chat)
        #expect(viewModel.selectedToolSection == .modelsLibrary)
        #expect(viewModel.serverSessions.isEmpty == false)
        #expect(viewModel.selectedServerSession?.modelID == "melix-dev-text")
        #expect(await metrics.snapshot()["menu.handshake_ms"] != nil)
        #expect(await metrics.snapshot()["menu.hydration_ms"] != nil)
    }

    @Test("server session seed prefers the first serveable model even when it is vlm")
    @MainActor
    func serverSessionSeedPrefersFirstServeableModelEvenWhenItIsVLM() async throws {
        let client = FakeControlPlaneXPCClient()
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeCapabilityModelSummary(
                    modelID: "melix-dev-ocr",
                    kind: "ocr",
                    state: .modelWarm,
                    features: ["ocr"]
                ),
                makeCapabilityModelSummary(
                    modelID: "melix-dev-vlm",
                    kind: "vlm",
                    state: .modelWarm,
                    features: ["vlm", "chat"]
                ),
            ]
        )
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        #expect(viewModel.serveableModels.map(\.modelID) == ["melix-dev-vlm"])
        #expect(viewModel.selectedServerSession?.modelID == "melix-dev-vlm")
    }

    @Test("remote server draft saves through app store and clears the API key field")
    @MainActor
    func remoteServerDraftSavesThroughAppStoreAndClearsTheAPIKeyField() throws {
        let store = FakeRemoteServerStore()
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            remoteServerStore: store
        )

        viewModel.prepareNewRemoteServerDraft()
        viewModel.remoteServerIDDraft = "sub2api"
        viewModel.remoteServerTitleDraft = "sub2api"
        viewModel.remoteServerProviderKindDraft = "openai-compatible"
        viewModel.remoteServerBaseURLDraft = "https://sub2api.example/v1/"
        viewModel.remoteServerDefaultModelIDDraft = "gemini-2.5-flash"
        viewModel.remoteServerAPIKeyDraft = "sk-test-1234567890"
        viewModel.remoteServerTimeoutSecondsDraft = 180
        viewModel.remoteServerRateLimitPerMinuteDraft = 60

        viewModel.saveRemoteServerDraft()

        let saved = try #require(viewModel.remoteServers.first)
        #expect(saved.id == "sub2api")
        #expect(saved.baseURL == "https://sub2api.example/v1/")
        #expect(saved.defaultModelID == "gemini-2.5-flash")
        #expect(saved.apiKeyHint == "sk-t...7890")
        #expect(viewModel.selectedRemoteServerID == "sub2api")
        #expect(viewModel.remoteServerAPIKeyDraft.isEmpty)
        #expect(store.savedMutations.first?.apiKey == "sk-test-1234567890")
    }

    @Test("remote server provider presets lock base URL and save resolved execution kind")
    @MainActor
    func remoteServerProviderPresetsLockBaseURLAndSaveResolvedExecutionKind() throws {
        let store = FakeRemoteServerStore()
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            remoteServerStore: store
        )

        viewModel.prepareNewRemoteServerDraft()
        viewModel.selectRemoteServerProviderPreset(.gemini)
        viewModel.remoteServerIDDraft = "gemini"
        viewModel.remoteServerTitleDraft = "Gemini"
        viewModel.remoteServerBaseURLDraft = "https://operator-override.example/v1"
        viewModel.remoteServerDefaultModelIDDraft = "gemini-2.5-flash"
        viewModel.remoteServerAPIKeyDraft = "AIza-secret"

        #expect(viewModel.isRemoteServerBaseURLEditable == false)
        #expect(viewModel.remoteServerProviderKindDraft == "gemini-generative-language")
        #expect(viewModel.remoteServerBaseURLDraft == "https://generativelanguage.googleapis.com/v1beta")

        viewModel.saveRemoteServerDraft()

        let savedMutation = try #require(store.savedMutations.first)
        #expect(savedMutation.providerPreset == .gemini)
        #expect(savedMutation.providerKind == "gemini-generative-language")
        #expect(savedMutation.baseURL == "https://generativelanguage.googleapis.com/v1beta")
        #expect(viewModel.remoteServers.first?.providerPreset == .gemini)

        viewModel.selectRemoteServerProviderPreset(.custom)
        #expect(viewModel.isRemoteServerBaseURLEditable)
        viewModel.remoteServerBaseURLDraft = "https://llm2api.owlia.ai/v1"
        #expect(viewModel.remoteServerBaseURLDraft == "https://llm2api.owlia.ai/v1")
    }

    @Test("remote server selection hydrates metadata but not the API key")
    @MainActor
    func remoteServerSelectionHydratesMetadataButNotTheAPIKey() throws {
        let store = FakeRemoteServerStore(servers: [
            RemoteServer(
                id: "sub2api",
                title: "sub2api",
                providerPreset: .custom,
                providerKind: "openai-compatible",
                baseURL: "https://sub2api.example/v1",
                defaultModelID: "deepseek-v4",
                timeoutSeconds: 120,
                rateLimitPerMinute: 0,
                credentialRef: RemoteServerStore.credentialRef(for: "sub2api"),
                apiKeyHint: "sk-t...7890"
            ),
        ])
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            remoteServerStore: store
        )

        viewModel.selectRemoteServer(id: "sub2api")

        #expect(viewModel.remoteServerIDDraft == "sub2api")
        #expect(viewModel.remoteServerBaseURLDraft == "https://sub2api.example/v1")
        #expect(viewModel.remoteServerDefaultModelIDDraft == "deepseek-v4")
        #expect(viewModel.remoteServerAPIKeyDraft.isEmpty)
    }

    @Test("remote server save rejects id changes for selected records")
    @MainActor
    func remoteServerSaveRejectsIDChangesForSelectedRecords() throws {
        let store = FakeRemoteServerStore(servers: [
            RemoteServer(
                id: "sub2api",
                title: "sub2api",
                providerPreset: .custom,
                providerKind: "openai-compatible",
                baseURL: "https://sub2api.example/v1",
                defaultModelID: "deepseek-v4",
                timeoutSeconds: 120,
                rateLimitPerMinute: 0,
                credentialRef: RemoteServerStore.credentialRef(for: "sub2api"),
                apiKeyHint: "sk-t...7890"
            ),
        ])
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            remoteServerStore: store
        )

        viewModel.selectRemoteServer(id: "sub2api")
        viewModel.remoteServerIDDraft = "kimi"
        viewModel.remoteServerTitleDraft = "Kimi"
        viewModel.remoteServerDefaultModelIDDraft = "kimi-2.6"

        viewModel.saveRemoteServerDraft()

        #expect(viewModel.remoteServers.map(\.id) == ["sub2api"])
        #expect(store.savedMutations.isEmpty)
        #expect(viewModel.lastError == "Remote Server ID cannot be changed after creation. Use New to create another server.")
    }

    @Test("remote server draft validates required fields and records persistence failures")
    @MainActor
    func remoteServerDraftValidatesRequiredFieldsAndRecordsPersistenceFailures() async throws {
        let store = FakeRemoteServerStore()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            metrics: metrics,
            remoteServerStore: store
        )

        viewModel.prepareNewRemoteServerDraft()
        viewModel.remoteServerIDDraft = " "
        viewModel.saveRemoteServerDraft()

        #expect(viewModel.lastError == "Remote Server requires id, title, provider, base URL, and default model.")
        #expect(store.savedMutations.isEmpty)

        viewModel.remoteServerIDDraft = "sub2api"
        viewModel.remoteServerTitleDraft = "sub2api"
        viewModel.remoteServerBaseURLDraft = "https://sub2api.example/v1"
        viewModel.remoteServerDefaultModelIDDraft = "gemini-2.5-flash"
        store.saveError = .save

        viewModel.saveRemoteServerDraft()
        try await waitForRuntimeMetric(
            metrics,
            name: "remote_server.persist_failures",
            equals: 1
        )

        #expect(viewModel.lastError == "Remote Server save failed: save")
    }

    @Test("remote server removal selects the next server and surfaces failures")
    @MainActor
    func remoteServerRemovalSelectsNextServerAndSurfacesFailures() async throws {
        let metrics = MenuBarMetricsStore()
        let store = FakeRemoteServerStore(servers: [
            RemoteServer(
                id: "kimi",
                title: "Kimi",
                providerPreset: .kimi,
                providerKind: "openai-compatible",
                baseURL: "https://api.kimi.com/coding",
                defaultModelID: "kimi-2.6",
                timeoutSeconds: 60,
                rateLimitPerMinute: 0,
                credentialRef: RemoteServerStore.credentialRef(for: "kimi"),
                apiKeyHint: "sk-k...7890"
            ),
            RemoteServer(
                id: "glm",
                title: "GLM",
                providerPreset: .glm,
                providerKind: "openai-compatible",
                baseURL: "https://open.bigmodel.cn/api/paas/v4",
                defaultModelID: "glm-5.1",
                timeoutSeconds: 90,
                rateLimitPerMinute: 5,
                credentialRef: RemoteServerStore.credentialRef(for: "glm"),
                apiKeyHint: "sk-g...7890"
            ),
        ])
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            metrics: metrics,
            remoteServerStore: store
        )

        viewModel.selectRemoteServer(id: "kimi")
        viewModel.removeSelectedRemoteServer()

        #expect(store.removedIDs == ["kimi"])
        #expect(viewModel.remoteServers.map(\.id) == ["glm"])
        #expect(viewModel.selectedRemoteServerID == "glm")
        #expect(viewModel.remoteServerIDDraft == "glm")

        store.removeError = .remove
        viewModel.removeSelectedRemoteServer()
        try await waitForRuntimeMetric(
            metrics,
            name: "remote_server.persist_failures",
            equals: 1
        )

        #expect(viewModel.lastError == "Remote Server remove failed: remove")
    }

    @Test("null remote server store materializes non-secret state")
    func nullRemoteServerStoreMaterializesNonSecretState() throws {
        let server = try NullRemoteServerStore().save(
            RemoteServerMutation(
                id: "gemini",
                title: "Gemini",
                providerPreset: .gemini,
                providerKind: "gemini-generative-language",
                baseURL: "https://override.example/v1",
                defaultModelID: "gemini-2.5-flash",
                timeoutSeconds: 75,
                rateLimitPerMinute: 12,
                apiKey: "AIza-secret"
            )
        )

        #expect(server.id == "gemini")
        #expect(server.providerKind == "gemini-generative-language")
        #expect(server.baseURL == "https://generativelanguage.googleapis.com/v1beta")
        #expect(server.defaultModelID == "gemini-2.5-flash")
        #expect(server.apiKeyHint == "AIza...cret")
        #expect(try NullRemoteServerStore().loadAPIKey(remoteServerID: "gemini") == nil)
        try NullRemoteServerStore().remove(id: "gemini")
        #expect(try NullRemoteServerStore().list().isEmpty)
    }

    @Test("null evaluation prompt store materializes deterministic revision hashes")
    func nullEvaluationPromptStoreMaterializesDeterministicRevisionHashes() throws {
        let store = NullEvaluationPromptStore()

        let created = try store.create(
            promptID: "custom",
            title: "Custom",
            systemPrompt: "Extract events."
        )
        let createdRevision = try #require(created.latestRevision)
        let createdHash = try EvaluationPromptStore.contentHash(systemPrompt: "Extract events.")
        #expect(createdRevision.contentHash == createdHash)

        let updated = try store.update(promptID: "custom", systemPrompt: "Extract more events.")
        let updatedRevision = try #require(updated.latestRevision)
        let updatedHash = try EvaluationPromptStore.contentHash(systemPrompt: "Extract more events.")
        #expect(updatedRevision.contentHash == updatedHash)

        let frozen = try store.freeze(promptID: "custom", revisionID: "rev-9")
        let frozenRevision = try #require(frozen.latestRevision)
        let frozenHash = try EvaluationPromptStore.contentHash(
            systemPrompt: EvaluationPromptStore.builtInBaselineSystemPrompt
        )
        #expect(frozenRevision.contentHash == frozenHash)
    }

    @Test("evaluation prompt drafts save freeze and create new draft revisions")
    @MainActor
    func evaluationPromptDraftsSaveFreezeAndCreateNewDraftRevisions() throws {
        let store = FakeEvaluationPromptStore()
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            evaluationPromptStore: store
        )

        #expect(viewModel.evaluationPrompts.map(\.id).contains(EvaluationPromptStore.builtInBaselinePromptID))
        #expect(viewModel.isEvaluationPromptDraftEditable == false)

        viewModel.prepareNewEvaluationPromptDraft()
        viewModel.evaluationPromptIDDraft = "event-prod"
        viewModel.evaluationPromptTitleDraft = "Event Production"
        viewModel.evaluationPromptSystemPromptDraft = "Extract production events."
        viewModel.saveEvaluationPromptDraft()

        #expect(store.createdPrompts.first?.id == "event-prod")
        #expect(viewModel.selectedEvaluationPromptID == "event-prod")
        #expect(viewModel.canFreezeSelectedEvaluationPrompt)

        viewModel.freezeSelectedEvaluationPrompt()

        #expect(store.frozenPrompts.first?.id == "event-prod")
        #expect(viewModel.selectedEvaluationPromptRevision?.status == .frozen)
        #expect(viewModel.isEvaluationPromptDraftEditable == false)

        viewModel.prepareEvaluationPromptDraftFromSelection()
        #expect(viewModel.isEvaluationPromptDraftEditable)

        viewModel.evaluationPromptSystemPromptDraft = "Extract production events with stricter JSON."
        viewModel.saveEvaluationPromptDraft()

        #expect(store.updatedPrompts.first?.id == "event-prod")
        #expect(viewModel.selectedEvaluationPromptRevision?.revisionID == "rev-2")
        #expect(viewModel.selectedEvaluationPromptRevision?.status == .draft)
    }

    @Test("event extraction evaluation sends the selected frozen prompt snapshot")
    @MainActor
    func eventExtractionEvaluationSendsSelectedFrozenPromptSnapshot() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                ]
            )
        )
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )
        let store = FakeEvaluationPromptStore()
        _ = try store.create(
            promptID: "event-prod",
            title: "Event Production",
            systemPrompt: "Extract only events from the current dialogue."
        )
        _ = try store.freeze(promptID: "event-prod", revisionID: "")
        let viewModel = RuntimeViewModel(
            client: client,
            evaluationPromptStore: store
        )

        await viewModel.start()
        viewModel.selectEvaluationPrompt(id: "event-prod")
        viewModel.selectedEvaluationSuiteIDs = ["event_extraction"]
        viewModel.evaluationScoringMode = "event_extraction_weighted_f1"
        viewModel.evaluationDatasetSourceKind = .localJSONL
        viewModel.evaluationSourcePath = "/tmp/top200_final.jsonl"
        viewModel.evaluationFieldInputTextPath = "dialogue"
        viewModel.evaluationFieldTargetPath = "events"

        await viewModel.runEvaluation()

        let request = try #require(await client.recordedEvaluationRequests.last)
        #expect(request.suiteID == "event_extraction")
        #expect(request.parameters["eval_prompt_id"] == "event-prod")
        #expect(request.parameters["eval_prompt_revision_id"] == "rev-1")
        #expect(request.parameters["eval_prompt_system_prompt"] == "Extract only events from the current dialogue.")
        #expect(request.parameters["eval_prompt_examples_json"] == "[]")
    }

    @Test("evaluation prompt guard rails surface local errors")
    @MainActor
    func evaluationPromptGuardRailsSurfaceLocalErrors() throws {
        let listFailingStore = FakeEvaluationPromptStore()
        listFailingStore.listError = .list
        let listFailingViewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            evaluationPromptStore: listFailingStore
        )
        #expect(listFailingViewModel.lastError?.contains("Evaluation prompt load failed") == true)

        let store = FakeEvaluationPromptStore()
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            evaluationPromptStore: store
        )

        viewModel.selectedEvaluationPromptID = ""
        #expect(viewModel.selectedEvaluationPromptSummaryText == "New draft prompt")
        #expect(viewModel.isEvaluationPromptDraftEditable)

        viewModel.freezeSelectedEvaluationPrompt()
        #expect(viewModel.lastError == "Save the evaluation prompt draft before freezing it.")

        viewModel.selectEvaluationPrompt(id: EvaluationPromptStore.builtInBaselinePromptID)
        viewModel.prepareEvaluationPromptDraftFromSelection()
        #expect(viewModel.lastError == "The built-in evaluation prompt is read-only. Create a new prompt to customize it.")

        viewModel.evaluationPromptIDDraft = EvaluationPromptStore.builtInBaselinePromptID
        viewModel.evaluationPromptTitleDraft = "Baseline"
        viewModel.evaluationPromptSystemPromptDraft = "Cannot save baseline."
        viewModel.saveEvaluationPromptDraft()
        #expect(viewModel.lastError == "The built-in evaluation prompt is read-only. Create a new prompt to customize it.")

        _ = try store.create(
            promptID: "event-prod",
            title: "Event Production",
            systemPrompt: "Extract production events."
        )
        viewModel.reloadEvaluationPrompts()
        viewModel.selectEvaluationPrompt(id: "event-prod")
        viewModel.evaluationPromptIDDraft = "event-renamed"
        viewModel.saveEvaluationPromptDraft()
        #expect(viewModel.evaluationPromptIDDraft == "event-prod")
        #expect(viewModel.lastError == "Evaluation prompt ID cannot be changed after creation. Use New Prompt to create another prompt.")

        viewModel.prepareNewEvaluationPromptDraft()
        viewModel.evaluationPromptIDDraft = ""
        viewModel.evaluationPromptTitleDraft = ""
        viewModel.evaluationPromptSystemPromptDraft = ""
        viewModel.saveEvaluationPromptDraft()
        #expect(viewModel.lastError == "Evaluation prompt requires id, title, and system prompt.")

        store.createError = .create
        viewModel.prepareNewEvaluationPromptDraft()
        viewModel.evaluationPromptIDDraft = "event-create-error"
        viewModel.evaluationPromptTitleDraft = "Event Create Error"
        viewModel.evaluationPromptSystemPromptDraft = "Create fails."
        viewModel.saveEvaluationPromptDraft()
        #expect(viewModel.lastError?.contains("Evaluation prompt save failed") == true)
        store.createError = nil

        _ = try store.create(
            promptID: "event-freeze-error",
            title: "Event Freeze Error",
            systemPrompt: "Freeze fails."
        )
        viewModel.reloadEvaluationPrompts()
        viewModel.selectEvaluationPrompt(id: "event-freeze-error")
        store.freezeError = .freeze
        viewModel.freezeSelectedEvaluationPrompt()
        #expect(viewModel.lastError?.contains("Evaluation prompt freeze failed") == true)
        store.freezeError = nil

        _ = try store.create(
            promptID: "event-archive",
            title: "Event Archive",
            systemPrompt: "Archive succeeds."
        )
        viewModel.reloadEvaluationPrompts()
        viewModel.selectEvaluationPrompt(id: "event-archive")
        viewModel.archiveSelectedEvaluationPrompt()
        #expect(store.archivedPromptIDs.contains("event-archive"))

        _ = try store.create(
            promptID: "event-archive-error",
            title: "Event Archive Error",
            systemPrompt: "Archive fails."
        )
        viewModel.reloadEvaluationPrompts()
        viewModel.selectEvaluationPrompt(id: "event-archive-error")
        store.archiveError = .archive
        viewModel.archiveSelectedEvaluationPrompt()
        #expect(viewModel.lastError?.contains("Evaluation prompt archive failed") == true)
    }

    @Test("event extraction prompt run guard rails surface local errors")
    @MainActor
    func eventExtractionPromptRunGuardRailsSurfaceLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                    makeModelSummary(modelID: "melix-dev-text-lora", state: .modelWarm),
                ]
            )
        )
        let store = FakeEvaluationPromptStore()
        let viewModel = RuntimeViewModel(
            client: client,
            evaluationPromptStore: store
        )

        await viewModel.start()
        viewModel.selectedEvaluationModelID = "melix-dev-text"
        viewModel.selectedEvaluationSuiteIDs = ["event_extraction", "mmlu"]
        await viewModel.runEvaluation()
        #expect(viewModel.lastError == "Event extraction prompts require selecting only the Event Extraction suite.")

        viewModel.selectedEvaluationMode = .compare
        viewModel.selectedEvaluationCompareTargetModelIDs = ["melix-dev-text-lora"]
        viewModel.selectedEvaluationSuiteIDs = ["event_extraction"]
        await viewModel.runEvaluation()
        #expect(viewModel.lastError == "Event extraction prompts are available for standard Evaluation runs.")

        store.resolveError = .resolve
        viewModel.selectedEvaluationMode = .standard
        viewModel.selectedEvaluationCompareTargetModelIDs = []
        viewModel.evaluationDatasetSourceKind = .localJSONL
        viewModel.evaluationSourcePath = "/tmp/top200_final.jsonl"
        viewModel.evaluationFieldInputTextPath = "dialogue"
        viewModel.evaluationFieldTargetPath = "events"
        await viewModel.runEvaluation()
        #expect(viewModel.lastError?.contains("resolve") == true)
    }

    @Test("applySelectedServerGatewayConfig sends a typed request and hydrates effective listener state")
    @MainActor
    func applySelectedServerGatewayConfigSendsATypedRequestAndHydratesEffectiveListenerState() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        viewModel.updateSelectedServerSessionHost("0.0.0.0")
        viewModel.updateSelectedServerSessionPort(18080)
        viewModel.updateSelectedServerSessionModelID("melix-dev-text")
        viewModel.updateSelectedServerSessionRateLimit(240)
        viewModel.updateSelectedServerSessionTimeout(90)

        await viewModel.applySelectedServerGatewayConfig()

        let request = try #require(await client.recordedGatewayConfigApplyRequests.last)
        let session = try #require(viewModel.selectedServerSession)

        #expect(request.serverSessionID == session.id)
        #expect(request.host == "0.0.0.0")
        #expect(request.port == 18_080)
        #expect(request.servedModelID == "melix-dev-text")
        #expect(request.rateLimitPerMinute == 240)
        #expect(request.timeoutSeconds == 90)
        #expect(session.host == "0.0.0.0")
        #expect(session.port == 18_080)
        #expect(session.effectiveHost == "0.0.0.0")
        #expect(session.effectivePort == 18_080)
        #expect(session.modelID == "melix-dev-text")
        #expect(session.gatewayConfigSourceText == "Operator Override")
        #expect(session.gatewayConfigActiveBinding)
        #expect(session.gatewayConfigRequiresRestart == false)
        #expect(await metrics.snapshot()["menu.gateway_config_apply_ms"] != nil)
    }

    @Test("applySelectedServerServingDefaults sends a typed request and hydrates effective defaults")
    @MainActor
    func applySelectedServerServingDefaultsSendsATypedRequestAndHydratesEffectiveDefaults() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        viewModel.updateSelectedServerSessionTemperature(0.33)
        viewModel.updateSelectedServerSessionTopP(0.92)
        viewModel.updateSelectedServerSessionMaxTokens(384)
        viewModel.updateSelectedServerSessionStreamIntervalTokens(3)
        viewModel.updateSelectedServerSessionMaxConcurrentRequests(5)
        viewModel.updateSelectedServerSessionConcurrentProcessingEnabled(true)
        viewModel.updateSelectedServerSessionPrefillBatchSize(3)
        viewModel.updateSelectedServerSessionCompletionBatchSize(2)
        viewModel.updateSelectedServerSessionAccelerationMode("speculative_decode")
        viewModel.updateSelectedServerSessionDraftModelID("melix-dev-draft")
        viewModel.updateSelectedServerSessionNumDraftTokens(6)

        await viewModel.applySelectedServerServingDefaults()

        let request = try #require(await client.recordedServingDefaultsApplyRequests.last)
        let session = try #require(viewModel.selectedServerSession)

        #expect(request.serverSessionID == session.id)
        #expect(request.temperature == 0.33)
        #expect(request.topP == 0.92)
        #expect(request.maxTokens == 384)
        #expect(request.streamIntervalTokens == 3)
        #expect(request.maxConcurrentRequests == 5)
        #expect(request.concurrentProcessingEnabled == true)
        #expect(request.prefillBatchSize == 3)
        #expect(request.completionBatchSize == 2)
        #expect(request.accelerationMode == .speculativeDecode)
        #expect(request.draftModelID == "melix-dev-draft")
        #expect(request.numDraftTokens == 6)
        #expect(session.servingDefaults.temperature == 0.33)
        #expect(session.servingDefaults.topP == 0.92)
        #expect(session.servingDefaults.maxTokens == 384)
        #expect(session.servingDefaults.streamIntervalTokens == 3)
        #expect(session.servingDefaults.maxConcurrentRequests == 5)
        #expect(session.servingDefaults.prefillBatchSize == 3)
        #expect(session.servingDefaults.completionBatchSize == 2)
        #expect(session.servingDefaults.accelerationMode == "speculative_decode")
        #expect(session.servingDefaults.draftModelID == "melix-dev-draft")
        #expect(session.servingDefaults.numDraftTokens == 6)
        #expect(session.servingDefaults.sourceText == "Operator Override")
        #expect(await metrics.snapshot()["menu.serving_defaults_apply_ms"] != nil)
    }

    @Test("applySelectedServerServingDefaults no-ops without a selected session")
    @MainActor
    func applySelectedServerServingDefaultsNoOpsWithoutSelectedSession() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.applySelectedServerServingDefaults()

        #expect(await client.recordedServingDefaultsApplyRequests.isEmpty)
    }

    @Test("applySelectedServerServingDefaultsFromUI schedules the typed request through the view model")
    @MainActor
    func applySelectedServerServingDefaultsFromUISchedulesTypedRequest() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.updateSelectedServerSessionTemperature(0.41)
        viewModel.updateSelectedServerSessionTopP(0.9)
        viewModel.updateSelectedServerSessionMaxTokens(300)
        viewModel.updateSelectedServerSessionStreamIntervalTokens(2)
        viewModel.updateSelectedServerSessionMaxConcurrentRequests(6)
        viewModel.updateSelectedServerSessionConcurrentProcessingEnabled(false)
        viewModel.updateSelectedServerSessionPrefillBatchSize(4)
        viewModel.updateSelectedServerSessionCompletionBatchSize(3)
        viewModel.updateSelectedServerSessionAccelerationMode("speculative_decode")
        viewModel.updateSelectedServerSessionDraftModelID("melix-dev-draft")
        viewModel.updateSelectedServerSessionNumDraftTokens(7)

        viewModel.applySelectedServerServingDefaultsFromUI()

        let deadline = ContinuousClock.now + .seconds(2)
        while ContinuousClock.now < deadline {
            if await client.recordedServingDefaultsApplyRequests.isEmpty == false {
                break
            }
            try await Task.sleep(for: .milliseconds(10))
        }

        let request = try #require(await client.recordedServingDefaultsApplyRequests.last)
        #expect(request.temperature == 0.41)
        #expect(request.topP == 0.9)
        #expect(request.maxTokens == 300)
        #expect(request.streamIntervalTokens == 2)
        #expect(request.maxConcurrentRequests == 6)
        #expect(request.concurrentProcessingEnabled == false)
        #expect(request.prefillBatchSize == 4)
        #expect(request.completionBatchSize == 3)
        #expect(request.accelerationMode == .speculativeDecode)
        #expect(request.draftModelID == "melix-dev-draft")
        #expect(request.numDraftTokens == 7)
    }

    @Test("applySelectedServerServingDefaults updates an existing projected summary in the fake control plane client")
    @MainActor
    func applySelectedServerServingDefaultsUpdatesExistingProjectedSummary() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            runtimeSessions: [makeRuntimeSession()]
        )
        var servingDefaults = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
        servingDefaults.serverSessionID = "server-session-1"
        servingDefaults.servedModelID = "melix-dev-text"
        servingDefaults.requestedTemperature = 0.7
        servingDefaults.requestedTopP = 1.0
        servingDefaults.requestedMaxTokens = 256
        servingDefaults.requestedStreamIntervalTokens = 1
        servingDefaults.requestedMaxConcurrentRequests = 4
        servingDefaults.requestedConcurrentProcessingEnabled = true
        servingDefaults.requestedPrefillBatchSize = 2
        servingDefaults.requestedCompletionBatchSize = 2
        servingDefaults.requestedAccelerationMode = .baseline
        servingDefaults.effectiveTemperature = 0.7
        servingDefaults.effectiveTopP = 1.0
        servingDefaults.effectiveMaxTokens = 256
        servingDefaults.effectiveStreamIntervalTokens = 1
        servingDefaults.effectiveMaxConcurrentRequests = 4
        servingDefaults.effectiveConcurrentProcessingEnabled = true
        servingDefaults.effectivePrefillBatchSize = 2
        servingDefaults.effectiveCompletionBatchSize = 2
        servingDefaults.source = .builtInDefaults
        snapshot.servingDefaults.sessions = [servingDefaults]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.updateSelectedServerSessionTemperature(0.33)
        viewModel.updateSelectedServerSessionTopP(0.92)
        viewModel.updateSelectedServerSessionMaxTokens(384)
        viewModel.updateSelectedServerSessionStreamIntervalTokens(3)
        viewModel.updateSelectedServerSessionMaxConcurrentRequests(5)
        viewModel.updateSelectedServerSessionConcurrentProcessingEnabled(true)
        viewModel.updateSelectedServerSessionPrefillBatchSize(3)
        viewModel.updateSelectedServerSessionCompletionBatchSize(2)
        viewModel.updateSelectedServerSessionAccelerationMode("speculative_decode")
        viewModel.updateSelectedServerSessionDraftModelID("melix-dev-draft")
        viewModel.updateSelectedServerSessionNumDraftTokens(6)

        await viewModel.applySelectedServerServingDefaults()

        let session = try #require(viewModel.selectedServerSession)
        #expect(session.servingDefaults.temperature == 0.33)
        #expect(session.servingDefaults.topP == 0.92)
        #expect(session.servingDefaults.maxTokens == 384)
        #expect(session.servingDefaults.streamIntervalTokens == 3)
        #expect(session.servingDefaults.maxConcurrentRequests == 5)
        #expect(session.servingDefaults.effectiveTemperature == 0.33)
        #expect(session.servingDefaults.effectiveTopP == 0.92)
        #expect(session.servingDefaults.effectiveMaxTokens == 384)
        #expect(session.servingDefaults.effectiveStreamIntervalTokens == 3)
        #expect(session.servingDefaults.effectiveMaxConcurrentRequests == 2)
        #expect(session.servingDefaults.effectiveConcurrentProcessingEnabled == true)
        #expect(session.servingDefaults.effectivePrefillBatchSize == 2)
        #expect(session.servingDefaults.effectiveCompletionBatchSize == 2)
        #expect(session.servingDefaults.accelerationMode == "speculative_decode")
        #expect(session.servingDefaults.draftModelID == "melix-dev-draft")
        #expect(session.servingDefaults.numDraftTokens == 6)
        #expect(session.servingDefaults.effectiveAccelerationMode == "speculative_decode")
        #expect(session.servingDefaults.effectiveDraftModelID == "melix-dev-draft")
        #expect(session.servingDefaults.effectiveNumDraftTokens == 6)
        #expect(session.servingDefaults.sourceText == "Operator Override")
        #expect(session.servingDefaults.modelOverrideApplied == false)
    }

    @Test("starting a selected server session persists gateway config and serving defaults before the lifecycle mutation")
    @MainActor
    func startingASelectedServerSessionPersistsGatewayConfigAndServingDefaultsBeforeTheLifecycleMutation() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.createServerSession()
        let serverSessionID = try #require(viewModel.selectedServerSession?.id)
        viewModel.updateSelectedServerSessionHost("127.0.0.1")
        viewModel.updateSelectedServerSessionPort(18081)
        viewModel.updateSelectedServerSessionStreamIntervalTokens(2)

        await viewModel.startSelectedServerSession()

        let actions = await client.recordedActions
        let applyConfigIndex = try #require(actions.firstIndex(of: "gateway.config:\(serverSessionID)"))
        let applyServingDefaultsIndex = try #require(actions.firstIndex(of: "serving-defaults.apply:\(serverSessionID)"))
        let startIndex = try #require(actions.firstIndex(of: "server.start:\(serverSessionID)"))

        #expect(applyConfigIndex < startIndex)
        #expect(applyServingDefaultsIndex < startIndex)
        #expect(await client.recordedGatewayConfigApplyRequests.count == 1)
        #expect(await client.recordedServingDefaultsApplyRequests.count == 1)
        #expect(viewModel.selectedServerSession?.lifecycle == .running)
    }

    @Test("gateway config apply failures block server starts and surface local errors")
    @MainActor
    func gatewayConfigApplyFailuresBlockServerStartsAndSurfaceLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.createServerSession()
        let serverSessionID = try #require(viewModel.selectedServerSession?.id)
        await client.configureErrors(applyGatewayConfig: MenuBarTestError(description: "persist failed"))

        await viewModel.startSelectedServerSession()

        let actions = await client.recordedActions
        #expect(actions.contains("gateway.config:\(serverSessionID)"))
        #expect(actions.contains("server.start:\(serverSessionID)") == false)
        #expect(viewModel.lastError?.contains("Gateway config apply failed") == true)
        #expect(viewModel.lastError?.contains("persist failed") == true)
    }

    @Test("serving defaults apply failures block server starts and surface local errors")
    @MainActor
    func servingDefaultsApplyFailuresBlockServerStartsAndSurfaceLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.createServerSession()
        let serverSessionID = try #require(viewModel.selectedServerSession?.id)
        await client.configureServingDefaultsApplyError(MenuBarTestError(description: "defaults persist failed"))

        await viewModel.startSelectedServerSession()

        let actions = await client.recordedActions
        #expect(actions.contains("gateway.config:\(serverSessionID)"))
        #expect(actions.contains("serving-defaults.apply:\(serverSessionID)"))
        #expect(actions.contains("server.start:\(serverSessionID)") == false)
        #expect(viewModel.lastError?.contains("Serving defaults apply failed") == true)
        #expect(viewModel.lastError?.contains("defaults persist failed") == true)
    }

    @Test("snapshot gateway config projection hydrates requested and effective listener state")
    @MainActor
    func snapshotGatewayConfigProjectionHydratesRequestedAndEffectiveListenerState() async throws {
        let client = FakeControlPlaneXPCClient()
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            runtimeSessions: [makeRuntimeSession()],
            gatewayConfig: makeGatewayConfigSummary(
                listener: makeGatewayConfigListener(
                    serverSessionID: "server-session-1",
                    requestedHost: "0.0.0.0",
                    requestedPort: 18_090,
                    effectiveHost: "127.0.0.1",
                    effectivePort: 11_434,
                    servedModelID: "melix-dev-text",
                    rateLimitPerMinute: 360,
                    timeoutSeconds: 75,
                    source: .operatorOverride,
                    activeBinding: true,
                    requiresRestart: true
                )
            )
        )
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let session = try #require(viewModel.selectedServerSession)
        #expect(session.host == "0.0.0.0")
        #expect(session.port == 18_090)
        #expect(session.effectiveHost == "127.0.0.1")
        #expect(session.effectivePort == 11_434)
        #expect(session.modelID == "melix-dev-text")
        #expect(session.rateLimitPerMinute == 360)
        #expect(session.timeoutSeconds == 75)
        #expect(session.gatewayConfigSourceText == "Operator Override")
        #expect(session.gatewayConfigActiveBinding)
        #expect(session.gatewayConfigRequiresRestart)
    }

    @Test("snapshot gateway config projection maps built-in environment config-file and unknown source labels")
    @MainActor
    func snapshotGatewayConfigProjectionMapsSourceLabels() async throws {
        let cases: [(Melix_Controlplane_V1_GatewayConfigSource, String)] = [
            (.builtInDefaults, "Built-in Defaults"),
            (.environmentDefaults, "Environment Defaults"),
            (.configFileImport, "Config File Import"),
            (.UNRECOGNIZED(99), "Unknown Source"),
        ]

        for (source, expected) in cases {
            let client = FakeControlPlaneXPCClient()
            let snapshot = makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(state: .modelWarm)],
                runtimeSessions: [makeRuntimeSession()],
                gatewayConfig: makeGatewayConfigSummary(
                    listener: makeGatewayConfigListener(
                        serverSessionID: "server-session-1",
                        requestedHost: "127.0.0.1",
                        requestedPort: 11_434,
                        effectiveHost: "127.0.0.1",
                        effectivePort: 11_434,
                        servedModelID: "melix-dev-text",
                        rateLimitPerMinute: 120,
                        timeoutSeconds: 60,
                        source: source,
                        activeBinding: true,
                        requiresRestart: false
                    )
                )
            )
            await client.configureSnapshot(snapshot)

            let viewModel = RuntimeViewModel(client: client)
            await viewModel.start()

            #expect(viewModel.selectedServerSession?.gatewayConfigSourceText == expected)
        }
    }

    @Test("snapshot serving defaults projection hydrates requested and effective generation state")
    @MainActor
    func snapshotServingDefaultsProjectionHydratesRequestedAndEffectiveGenerationState() async throws {
        let client = FakeControlPlaneXPCClient()
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            runtimeSessions: [makeRuntimeSession()],
            gatewayConfig: makeGatewayConfigSummary(
                listener: makeGatewayConfigListener(
                    serverSessionID: "server-session-1",
                    requestedHost: "127.0.0.1",
                    requestedPort: 11_434,
                    effectiveHost: "127.0.0.1",
                    effectivePort: 11_434,
                    servedModelID: "melix-dev-text",
                    rateLimitPerMinute: 120,
                    timeoutSeconds: 60,
                    source: .operatorOverride,
                    activeBinding: true,
                    requiresRestart: false
                )
            )
        )
        var servingDefaults = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
        servingDefaults.serverSessionID = "server-session-1"
        servingDefaults.servedModelID = "melix-dev-text"
        servingDefaults.requestedTemperature = 0.31
        servingDefaults.requestedTopP = 0.89
        servingDefaults.requestedMaxTokens = 400
        servingDefaults.requestedStreamIntervalTokens = 2
        servingDefaults.requestedMaxConcurrentRequests = 5
        servingDefaults.requestedAccelerationMode = .speculativeDecode
        servingDefaults.requestedDraftModelID = "melix-dev-draft"
        servingDefaults.requestedNumDraftTokens = 6
        servingDefaults.effectiveTemperature = 0.2
        servingDefaults.effectiveTopP = 0.88
        servingDefaults.effectiveMaxTokens = 512
        servingDefaults.effectiveStreamIntervalTokens = 2
        servingDefaults.effectiveMaxConcurrentRequests = 5
        servingDefaults.effectiveAccelerationMode = .speculativeDecode
        servingDefaults.effectiveDraftModelID = "melix-dev-draft"
        servingDefaults.effectiveNumDraftTokens = 6
        servingDefaults.source = .operatorOverride
        servingDefaults.modelOverrideApplied = true
        var projectedSnapshot = snapshot
        projectedSnapshot.servingDefaults.sessions = [servingDefaults]
        await client.configureSnapshot(projectedSnapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let session = try #require(viewModel.selectedServerSession)
        #expect(session.servingDefaults.temperature == 0.31)
        #expect(session.servingDefaults.topP == 0.89)
        #expect(session.servingDefaults.maxTokens == 400)
        #expect(session.servingDefaults.streamIntervalTokens == 2)
        #expect(session.servingDefaults.maxConcurrentRequests == 5)
        #expect(session.servingDefaults.accelerationMode == "speculative_decode")
        #expect(session.servingDefaults.draftModelID == "melix-dev-draft")
        #expect(session.servingDefaults.numDraftTokens == 6)
        #expect(session.servingDefaults.effectiveTemperature == 0.2)
        #expect(session.servingDefaults.effectiveTopP == 0.88)
        #expect(session.servingDefaults.effectiveMaxTokens == 512)
        #expect(session.servingDefaults.effectiveAccelerationMode == "speculative_decode")
        #expect(session.servingDefaults.effectiveDraftModelID == "melix-dev-draft")
        #expect(session.servingDefaults.effectiveNumDraftTokens == 6)
        #expect(session.servingDefaults.sourceText == "Operator Override")
        #expect(session.servingDefaults.modelOverrideApplied)
    }

    @Test("snapshot serving defaults projection keeps local defaults when no summary is available")
    @MainActor
    func snapshotServingDefaultsProjectionKeepsLocalDefaultsWhenSummaryIsMissing() async throws {
        let client = FakeControlPlaneXPCClient()
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            runtimeSessions: [makeRuntimeSession()]
        )
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let session = try #require(viewModel.selectedServerSession)
        #expect(session.servingDefaults.temperature == 0.7)
        #expect(session.servingDefaults.topP == 1.0)
        #expect(session.servingDefaults.maxTokens == 256)
        #expect(session.servingDefaults.streamIntervalTokens == 1)
        #expect(session.servingDefaults.maxConcurrentRequests == 4)
        #expect(session.servingDefaults.accelerationMode == "baseline")
        #expect(session.servingDefaults.numDraftTokens == 0)
        #expect(session.servingDefaults.sourceText == "Built-in Defaults")
        #expect(session.servingDefaults.modelOverrideApplied == false)
    }

    @Test("lora model selection falls back to the first text model and stays empty without text models")
    @MainActor
    func loraModelSelectionFallsBackToFirstTextModel() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.selectedLoraModelID = "missing-model"

        #expect(viewModel.selectedLoraModel?.modelID == "melix-dev-text")
        #expect(viewModel.selectedLoraModelID == "melix-dev-text")

        var imageOnlySnapshot = Melix_Controlplane_V1_ServerSnapshot()
        imageOnlySnapshot.serverState = .serverReady
        imageOnlySnapshot.models = [makeMenuBarImageModelSummary()]
        await client.configureSnapshot(imageOnlySnapshot)

        let imageOnlyViewModel = RuntimeViewModel(client: client)
        await imageOnlyViewModel.start()
        imageOnlyViewModel.selectedLoraModelID = "missing-model"

        #expect(imageOnlyViewModel.loraCapableModels.isEmpty)
        #expect(imageOnlyViewModel.selectedLoraModel == nil)
    }

    @Test("restoresSelectedSurfaceAndServerSession from operator-session state")
    @MainActor
    func restoresSelectedSurfaceAndServerSessionFromOperatorSessionState() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-restore-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let restoredServerSession = DesktopServerSessionState(
            id: "server-session-restored",
            title: "Restored Server",
            modelID: "melix-dev-text",
            lifecycle: .running
        )
        try operatorSessionStore.save(
            OperatorSessionState(
                selectedSurface: .api,
                selectedServerSessionID: restoredServerSession.id,
                serverSessions: [restoredServerSession]
            )
        )

        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()

        #expect(viewModel.selectedSurface == .api)
        #expect(viewModel.selectedServerSession?.id == restoredServerSession.id)
    }

    @Test("persists selected tool section and restores it across restart")
    @MainActor
    func persistsSelectedToolSectionAndRestoresAcrossRestart() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-tool-section-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client, operatorSessionStore: operatorSessionStore)

        await viewModel.start()
        viewModel.selectToolSection(.diagnostics)

        let persistedData = try Data(contentsOf: melixHome.operatorSessionFileURL)
        let persistedPayload = try #require(
            JSONSerialization.jsonObject(with: persistedData) as? [String: Any]
        )
        #expect(persistedPayload["selected_surface"] as? String == "tools")
        #expect(persistedPayload["selected_tool_section"] as? String == "diagnostics")

        let restoredViewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            operatorSessionStore: operatorSessionStore
        )
        await restoredViewModel.start()

        #expect(restoredViewModel.selectedSurface == .tools)
        #expect(restoredViewModel.selectedToolSection == .diagnostics)
    }

    @Test("restores models library tool section when persisted state predates selected tool sections")
    @MainActor
    func restoresDefaultToolSectionForLegacyOperatorSessionState() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-tool-section-legacy-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let restoredServerSession = DesktopServerSessionState(
            id: "server-session-restored",
            title: "Restored Server",
            modelID: "melix-dev-text",
            lifecycle: .running
        )

        try operatorSessionStore.save(
            OperatorSessionState(
                selectedSurface: .tools,
                selectedServerSessionID: restoredServerSession.id,
                serverSessions: [restoredServerSession]
            )
        )

        let legacyData = try Data(contentsOf: melixHome.operatorSessionFileURL)
        let legacyPayload = try #require(
            JSONSerialization.jsonObject(with: legacyData) as? [String: Any]
        )
        var mutatedPayload = legacyPayload
        mutatedPayload.removeValue(forKey: "selected_tool_section")
        let mutatedData = try JSONSerialization.data(withJSONObject: mutatedPayload, options: [.sortedKeys])
        try mutatedData.write(to: melixHome.operatorSessionFileURL, options: [.atomic])

        let restoredViewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            operatorSessionStore: operatorSessionStore
        )
        await restoredViewModel.start()

        #expect(restoredViewModel.selectedSurface == .tools)
        #expect(restoredViewModel.selectedToolSection == .modelsLibrary)
    }

    @Test("persists download queue state and restores it across shell restart")
    @MainActor
    func persistsDownloadQueueStateAndRestoresItAcrossShellRestart() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-download-queue-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let fixture = MenuBarDownloadFixture(
            jobID: "model-ops-0042",
            sourceModel: "melix-dev-text",
            status: "stalled",
            stage: "download",
            pct: 0.5,
            outputDir: "/tmp/melix-downloads/melix-dev-text",
            outputPath: "/tmp/melix-downloads/melix-dev-text/download.artifact",
            partialPath: "/tmp/melix-downloads/melix-dev-text/download.artifact.partial",
            statePath: "/tmp/melix-downloads/melix-dev-text/download.state.json",
            selectedMirror: "https://mirror.example/hf",
            downloadedBytes: 1024,
            totalBytes: 2048,
            resumeUsed: true,
            resumeFromBytes: 512,
            retryCount: 1,
            stallDetectionCount: 1,
            stallReason: "no_progress_timeout",
            resumeReady: true
        )

        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [],
                    downloads: [fixture]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        let firstViewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore
        )
        await firstViewModel.start()
        firstViewModel.selectToolSection(.downloads)
        await firstViewModel.refreshDownloadQueueState()

        let persistedData = try Data(contentsOf: melixHome.operatorSessionFileURL)
        let persistedPayload = try #require(
            JSONSerialization.jsonObject(with: persistedData) as? [String: Any]
        )
        let persistedQueue = try #require(persistedPayload["download_queue"] as? [[String: Any]])
        #expect(persistedQueue.count == 1)
        #expect(persistedQueue.first?["job_id"] as? String == "model-ops-0042")

        let restoredViewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            operatorSessionStore: operatorSessionStore
        )
        await restoredViewModel.start()

        let restoredQueue = try #require(restoredViewModel.downloadQueue.first)
        #expect(restoredQueue.jobID == "model-ops-0042")
        #expect(restoredQueue.resumeReady)
        #expect(restoredQueue.statusText == "Stalled")
    }

    @Test("generatesPrimaryAPIKeyForSelectedServerSession and forces api key auth mode")
    @MainActor
    func generatesPrimaryAPIKeyForSelectedServerSessionAndForcesAPIKeyAuthMode() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-generate-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(
            client: client,
            metrics: metrics,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        let selectedServerSessionID = try #require(viewModel.selectedServerSession?.id)
        let generatedPrimaryKey = try #require(await viewModel.generatePrimaryAPIKeyForSelectedServerSession())
        let persistedPrimaryKey = try #require(try apiKeyStore.loadPrimaryKey(serverSessionID: selectedServerSessionID))

        #expect(generatedPrimaryKey.hasPrefix("melix_sk_"))
        #expect(persistedPrimaryKey.primaryKey == generatedPrimaryKey)
        #expect(viewModel.selectedServerSession?.authMode == .apiKeys)

        var persistMetricFound = false
        for _ in 0..<100 {
            let metricValues = await metrics.snapshot()
            if metricValues["operator.session_persist_write_ms"] != nil {
                persistMetricFound = true
                break
            }
            try await Task.sleep(for: .milliseconds(10))
        }

        let metricValues = await metrics.snapshot()
        #expect(metricValues["operator.session_restore_ms"] != nil)
        #expect(persistMetricFound)
        #expect(metricValues["gateway.api_key_persist_failures"] == 0)
    }

    @Test("defers gateway apply when selected server session is not running")
    @MainActor
    func defersGatewayApplyWhenSelectedServerSessionIsNotRunning() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-defer-apply-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        viewModel.createServerSession()
        #expect(viewModel.selectedServerSession?.isRunning == false)

        _ = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()

        #expect(await client.recordedGatewayAccessApplyRequests.isEmpty)
    }

    @Test("appliesStoredKeyWhenSelectedRunningServerSessionBecomesActive")
    @MainActor
    func appliesStoredKeyWhenSelectedRunningServerSessionBecomesActive() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-apply-stored-key-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        viewModel.createServerSession()
        let selectedServerSessionID = try #require(viewModel.selectedServerSession?.id)
        let primaryKey = try #require(await viewModel.generatePrimaryAPIKeyForSelectedServerSession())
        #expect(await client.recordedGatewayAccessApplyRequests.isEmpty)

        await viewModel.startSelectedServerSession()
        var applyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.isEmpty, applyAttempts < 200 {
            applyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.isEmpty == false)

        let appliedRequest = try #require(await client.recordedGatewayAccessApplyRequests.last)
        #expect(appliedRequest.serverSessionID == selectedServerSessionID)
        #expect(appliedRequest.primaryKey == primaryKey)
    }

    @Test("selecting a keyless server session clears previously applied gateway access")
    @MainActor
    func selectingAKeylessServerSessionClearsPreviouslyAppliedGatewayAccess() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-clear-keyless-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        _ = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()
        var applyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.isEmpty, applyAttempts < 200 {
            applyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.count == 1)

        viewModel.createServerSession()

        var clearAttempts = 0
        while await client.recordedGatewayAccessClearRequests.isEmpty, clearAttempts < 200 {
            clearAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessClearRequests == [try #require(viewModel.selectedServerSession?.id)])
    }

    @Test("stopping a keyed server session clears previously applied gateway access")
    @MainActor
    func stoppingAKeyedServerSessionClearsPreviouslyAppliedGatewayAccess() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-clear-stopped-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        let selectedServerSessionID = try #require(viewModel.selectedServerSession?.id)
        _ = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()
        var applyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.isEmpty, applyAttempts < 200 {
            applyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.count == 1)

        await viewModel.stopSelectedServerSession()

        var clearAttempts = 0
        while await client.recordedGatewayAccessClearRequests.isEmpty, clearAttempts < 200 {
            clearAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessClearRequests == [selectedServerSessionID])
    }

    @Test("gateway access clear failures surface as recoverable local errors")
    @MainActor
    func gatewayAccessClearFailuresSurfaceAsRecoverableLocalErrors() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-clear-error-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let apiKeyStore = ServerSessionAPIKeyStore(melixHome: melixHome)
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            serverSessionAPIKeyStore: apiKeyStore
        )

        await viewModel.start()
        _ = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()
        var applyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.count < 1, applyAttempts < 200 {
            applyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.count == 1)

        await client.configureGatewayAccessClearError(MenuBarTestError(description: "clear failed"))
        viewModel.createServerSession()

        try await waitForRuntimeViewModelCondition("expected gateway access clear failure to surface") {
            viewModel.lastError?.contains("Gateway access clear failed") == true
        }
    }

    @Test("generate primary key returns nil when no server session exists")
    @MainActor
    func generatePrimaryKeyReturnsNilWhenNoServerSessionExists() async throws {
        let client = EmptySnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        let generatedPrimaryKey = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()

        #expect(generatedPrimaryKey == nil)
    }

    @Test("generate primary key records persistence failures when the store write fails")
    @MainActor
    func generatePrimaryKeyRecordsPersistenceFailuresWhenStoreWriteFails() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(
            client: client,
            metrics: metrics,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: false,
                throwOnSave: true,
                loadPrimaryKeyValue: nil
            )
        )

        await viewModel.start()
        let generatedPrimaryKey = await viewModel.generatePrimaryAPIKeyForSelectedServerSession()

        #expect(generatedPrimaryKey == nil)
        var metricValues = await metrics.snapshot()
        if metricValues["gateway.api_key_persist_failures"] != 1 {
            try await Task.sleep(for: .milliseconds(20))
            metricValues = await metrics.snapshot()
        }
        #expect(metricValues["gateway.api_key_persist_failures"] == 1)
    }

    @Test("start captures operator-session restore failures as local errors")
    @MainActor
    func startCapturesOperatorSessionRestoreFailuresAsLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: ThrowingOperatorSessionStore(throwOnLoad: true, throwOnSave: false),
            serverSessionAPIKeyStore: NullServerSessionAPIKeyStore()
        )

        await viewModel.start()

        #expect(viewModel.lastError?.contains("Operator session restore failed") == true)
    }

    @Test("persist operator-session failures are isolated to local error state")
    @MainActor
    func persistOperatorSessionFailuresAreIsolatedToLocalErrorState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: ThrowingOperatorSessionStore(throwOnLoad: false, throwOnSave: true),
            serverSessionAPIKeyStore: NullServerSessionAPIKeyStore()
        )

        await viewModel.start()
        viewModel.selectSurface(.server)

        #expect(viewModel.lastError?.contains("Operator session persistence failed") == true)
    }

    @Test("stored gateway key load and apply failures surface as recoverable local errors")
    @MainActor
    func storedGatewayKeyLoadAndApplyFailuresSurfaceAsRecoverableLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(applyGatewayAccess: MenuBarTestError(description: "apply failed"))
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: true,
                throwOnSave: false,
                loadPrimaryKeyValue: nil
            )
        )

        await viewModel.start()
        viewModel.selectServerSession(id: viewModel.selectedServerSession?.id ?? "")
        #expect(viewModel.lastError?.contains("Gateway API key restore failed") == true)

        let applyFailureViewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: false,
                throwOnSave: false,
                loadPrimaryKeyValue: "melix_sk_apply_failure"
            )
        )

        await applyFailureViewModel.start()
        applyFailureViewModel.selectServerSession(id: applyFailureViewModel.selectedServerSession?.id ?? "")
        try await Task.sleep(for: .milliseconds(20))
        #expect(applyFailureViewModel.lastError?.contains("Gateway access apply failed") == true)
    }

    @Test("stored gateway apply skips empty keys and dedupes already-applied keys")
    @MainActor
    func storedGatewayApplySkipsEmptyKeysAndDedupesAlreadyAppliedKeys() async throws {
        let emptyKeyClient = FakeControlPlaneXPCClient()
        let emptyKeyViewModel = RuntimeViewModel(
            client: emptyKeyClient,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: false,
                throwOnSave: false,
                loadPrimaryKeyValue: ""
            )
        )

        await emptyKeyViewModel.start()
        emptyKeyViewModel.selectServerSession(id: emptyKeyViewModel.selectedServerSession?.id ?? "")
        try await Task.sleep(for: .milliseconds(20))
        #expect(await emptyKeyClient.recordedGatewayAccessApplyRequests.isEmpty)

        let dedupeClient = FakeControlPlaneXPCClient()
        let dedupeViewModel = RuntimeViewModel(
            client: dedupeClient,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: false,
                throwOnSave: false,
                loadPrimaryKeyValue: "melix_sk_dedupe"
            )
        )

        await dedupeViewModel.start()
        dedupeViewModel.selectServerSession(id: dedupeViewModel.selectedServerSession?.id ?? "")
        try await Task.sleep(for: .milliseconds(20))
        dedupeViewModel.selectServerSession(id: dedupeViewModel.selectedServerSession?.id ?? "")
        try await Task.sleep(for: .milliseconds(20))
        #expect(await dedupeClient.recordedGatewayAccessApplyRequests.count == 1)
    }

    @Test("chat requires an interactive server session before sending prompts")
    @MainActor
    func chatRequiresInteractiveServerSession() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "hello"
        await viewModel.stopSelectedServerSession()
        await viewModel.submitChatPrompt()

        let actions = await client.recordedActions
        #expect(actions.contains(where: { $0.hasPrefix("chat:") }) == false)
        #expect(viewModel.chatStatusText == "Stopped")
        #expect(viewModel.lastError == "Start the bound Server Session before sending chat prompts.")
    }

    @Test("sleeping chat stays interactive while paused chat is blocked")
    @MainActor
    func sleepingChatStaysInteractiveWhilePausedChatIsBlocked() async throws {
        let client = FakeControlPlaneXPCClient()
        let sleepingSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            runtimeSessions: [
                makeRuntimeSession(
                    lifecycleState: .sleeping,
                    powerState: .deepSleep,
                    wakeReason: .requestActivity,
                    idleTimerSeconds: 240,
                    autoSleepEnabled: true,
                    lightSleepAfterSeconds: 300,
                    deepSleepAfterSeconds: 900
                )
            ]
        )
        await client.configureSnapshot(sleepingSnapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "wake on demand"
        await viewModel.submitChatPrompt()

        #expect(await client.recordedActions.contains(where: { $0.hasPrefix("chat:") }))
        #expect(viewModel.selectedChatServerSession?.isInteractiveReady == true)
        #expect(viewModel.selectedChatServerSession?.chatWorkspaceNoticeState?.severity == .info)

        let serverSessionID = try #require(viewModel.selectedServerSession?.id)
        await client.sendServerStateChanged(
            state: .serverReady,
            runtimeSessions: [
                makeRuntimeSession(
                    serverSessionID: serverSessionID,
                    lifecycleState: .paused,
                    powerState: .active,
                    wakeReason: .policyApply,
                    idleTimerSeconds: 120,
                    autoSleepEnabled: true,
                    lightSleepAfterSeconds: 300,
                    deepSleepAfterSeconds: 900
                )
            ]
        )

        try await waitForRuntimeViewModelCondition("expected selected chat server session to enter paused state") {
            viewModel.selectedChatServerSession?.lifecycle == .paused
        }

        viewModel.chatComposerText = "blocked while paused"
        let recordedChatCount = await client.recordedActions.filter { $0.hasPrefix("chat:") }.count
        await viewModel.submitChatPrompt()

        #expect(await client.recordedActions.filter { $0.hasPrefix("chat:") }.count == recordedChatCount)
        #expect(viewModel.chatStatusText == "Paused")
        #expect(viewModel.lastError == "Resume the paused Server Session before sending chat prompts.")
    }

    @Test("new chat sessions require an explicit server selection before sending")
    @MainActor
    func newChatSessionsRequireExplicitServerSelectionBeforeSending() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        let originalServerID = try #require(viewModel.selectedServerSession?.id)

        viewModel.createChatSession()

        #expect(viewModel.chatSessions.count == 2)
        #expect(viewModel.selectedChatSession?.serverSessionID == "")
        #expect(viewModel.selectedChatServerSession == nil)

        viewModel.chatComposerText = "should wait for server choice"
        await viewModel.submitChatPrompt()

        #expect(await client.recordedActions.contains(where: { $0.hasPrefix("chat:") }) == false)
        #expect(viewModel.chatStatusText == "Choose Server")
        #expect(viewModel.lastError == "Choose a Server Session before sending chat prompts.")

        viewModel.bindSelectedChatSessionToServer(serverSessionID: originalServerID)
        viewModel.chatComposerText = "send after server choice"
        await viewModel.submitChatPrompt()

        #expect(viewModel.selectedChatSession?.serverSessionID == originalServerID)
        #expect(await client.recordedActions.contains("chat:melix-dev-text"))
    }

    @Test("chat submit reports missing managed Hugging Face cache without dispatching")
    @MainActor
    func chatSubmitReportsMissingManagedHuggingFaceCacheWithoutDispatching() async throws {
        let client = FakeControlPlaneXPCClient()
        var missingModel = makeModelSummary(state: .modelDiscovered)
        missingModel.settings.ext["melix.model_path_missing"] = "true"
        missingModel.settings.ext["melix.model_path"] = "/tmp/hf-cache/models--mlx-community--Qwen3/snapshots/missing"
        await client.configureSnapshot(makeSnapshot(
            serverState: .serverReady,
            models: [missingModel],
            runtimeSessions: [makeRuntimeSession()]
        ))
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "hello"
        await viewModel.submitChatPrompt()

        let errorEntry = try #require(viewModel.chatTranscript.last)
        #expect(await client.recordedActions.contains(where: { $0.hasPrefix("chat:") }) == false)
        #expect(errorEntry.kind == .error)
        #expect(errorEntry.body == "Hugging Face cache files are missing. Re-download this model to restore it.")
        #expect(viewModel.chatStatusText == "Failed • model_runtime_missing")
        #expect(viewModel.lastError == "Hugging Face cache files are missing. Re-download this model to restore it.")
    }

    @Test("surface selection command center and server session controls update shell state")
    @MainActor
    func shellStateSelectionAndServerSessionControlsUpdateState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        var stateChangeCount = 0
        var commandCenterOpenCount = 0
        viewModel.onStateChanged = { stateChangeCount += 1 }
        viewModel.openCommandCenterAction = { commandCenterOpenCount += 1 }

        await viewModel.start()

        viewModel.selectSurface(.api)
        #expect(viewModel.selectedSurface == .api)

        viewModel.selectToolSection(.diagnostics)
        #expect(viewModel.selectedSurface == .tools)
        #expect(viewModel.selectedToolSection == .diagnostics)

        viewModel.openCommandCenter()
        #expect(commandCenterOpenCount == 1)

        let originalServerID = try #require(viewModel.selectedServerSession?.id)
        viewModel.createServerSession()

        let createdServer = try #require(viewModel.selectedServerSession)
        #expect(createdServer.id != originalServerID)
        #expect(createdServer.title == "Server 2")
        #expect(createdServer.lifecycle == .draft)
        #expect(viewModel.selectedSurface == .server)

        viewModel.selectServerSession(id: "missing-server")
        #expect(viewModel.selectedServerSession?.id == createdServer.id)

        viewModel.selectServerSession(id: originalServerID)
        #expect(viewModel.selectedServerSession?.id == originalServerID)

        viewModel.selectServerSession(id: createdServer.id)
        viewModel.updateSelectedServerSessionModelID("melix-dev-text")
        viewModel.updateSelectedServerSessionHost("0.0.0.0")
        viewModel.updateSelectedServerSessionPort(0)
        viewModel.updateSelectedServerSessionAuthMode(.bearerToken)
        viewModel.updateSelectedServerSessionAuthTokenHint("dev-token")
        viewModel.updateSelectedServerSessionRateLimit(0)
        viewModel.updateSelectedServerSessionTimeout(0)
        viewModel.updateSelectedServerSessionTemperature(-1)
        viewModel.updateSelectedServerSessionTopP(5)
        viewModel.updateSelectedServerSessionMaxTokens(0)
        viewModel.updateSelectedServerSessionStreamIntervalTokens(0)
        viewModel.updateSelectedServerSessionMaxConcurrentRequests(0)

        let configuredServer = try #require(viewModel.selectedServerSession)
        #expect(configuredServer.host == "0.0.0.0")
        #expect(configuredServer.port == 1)
        #expect(configuredServer.authMode == .bearerToken)
        #expect(configuredServer.authTokenHint == "dev-token")
        #expect(configuredServer.rateLimitPerMinute == 1)
        #expect(configuredServer.timeoutSeconds == 1)
        #expect(configuredServer.servingDefaults.temperature == 0)
        #expect(configuredServer.servingDefaults.topP == 1)
        #expect(configuredServer.servingDefaults.maxTokens == 1)
        #expect(configuredServer.servingDefaults.streamIntervalTokens == 1)
        #expect(configuredServer.servingDefaults.maxConcurrentRequests == 1)

        await viewModel.startSelectedServerSession()
        #expect(await client.recordedActions.contains("server.start:\(createdServer.id)"))
        #expect(viewModel.selectedServerSession?.lifecycle == .running)

        let runningServerID = try #require(viewModel.selectedServerSession?.id)
        await viewModel.stopSelectedServerSession()
        #expect(await client.recordedActions.contains("server.stop:\(runningServerID)"))
        #expect(viewModel.selectedServerSession?.lifecycle == .stopped)
        #expect(stateChangeCount > 0)
    }

    @Test("server lifecycle controls and idle policy updates hydrate the selected session")
    @MainActor
    func serverLifecycleControlsAndIdlePolicyUpdatesHydrateSelectedSession() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        let serverSessionID = try #require(viewModel.selectedServerSession?.id)

        await viewModel.pauseSelectedServerSession()
        #expect(await client.recordedActions.contains("server.pause:\(serverSessionID)"))
        #expect(viewModel.selectedServerSession?.lifecycle == .paused)
        #expect(viewModel.selectedServerSession?.wakeReason == .policyApply)

        await viewModel.resumeSelectedServerSession()
        #expect(await client.recordedActions.contains("server.resume:\(serverSessionID)"))
        #expect(viewModel.selectedServerSession?.lifecycle == .running)
        #expect(viewModel.selectedServerSession?.wakeReason == .operatorResume)

        await client.sendServerStateChanged(
            state: .serverReady,
            runtimeSessions: [
                makeRuntimeSession(
                    serverSessionID: serverSessionID,
                    lifecycleState: .sleeping,
                    powerState: .lightSleep,
                    wakeReason: .requestActivity,
                    idleTimerSeconds: 180,
                    autoSleepEnabled: false,
                    lightSleepAfterSeconds: 0,
                    deepSleepAfterSeconds: 0
                )
            ]
        )
        try await waitForRuntimeViewModelCondition("expected server session to enter sleeping state") {
            viewModel.selectedServerSession?.lifecycle == .sleeping
        }

        await viewModel.wakeSelectedServerSession()
        #expect(await client.recordedActions.contains("server.wake:\(serverSessionID)"))
        #expect(viewModel.selectedServerSession?.lifecycle == .running)

        viewModel.updateSelectedServerSessionAutoSleepEnabled(true)
        viewModel.updateSelectedServerSessionLightSleepAfterSeconds(300)
        viewModel.updateSelectedServerSessionDeepSleepAfterSeconds(900)
        await viewModel.applySelectedServerIdlePolicy()

        let idlePolicyRequest = try #require(await client.recordedServerIdlePolicyRequests.last)
        #expect(idlePolicyRequest.serverSessionID == serverSessionID)
        #expect(idlePolicyRequest.autoSleepEnabled)
        #expect(idlePolicyRequest.lightSleepAfterSeconds == 300)
        #expect(idlePolicyRequest.deepSleepAfterSeconds == 900)
        #expect(viewModel.selectedServerSession?.autoSleepEnabled == true)
        #expect(viewModel.selectedServerSession?.lightSleepAfterSeconds == 300)
        #expect(viewModel.selectedServerSession?.deepSleepAfterSeconds == 900)

        let metricValues = await metrics.snapshot()
        #expect(metricValues["menu.server_pause_ms"] != nil)
        #expect(metricValues["menu.server_resume_ms"] != nil)
        #expect(metricValues["menu.server_wake_ms"] != nil)
        #expect(metricValues["menu.server_idle_policy_ms"] != nil)
    }

    @Test("server lifecycle helper entry points no-op without a selected session or explicit id")
    @MainActor
    func serverLifecycleHelperEntryPointsNoOpWithoutSelectedSessionOrExplicitID() async throws {
        let client = EmptySnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await viewModel.stopSelectedServerSession()
        await viewModel.pauseSelectedServerSession()
        await viewModel.resumeSelectedServerSession()
        await viewModel.wakeSelectedServerSession()
        await viewModel.applySelectedServerIdlePolicy()

        await viewModel.startServerSession(id: "")
        await viewModel.stopServerSession(id: "")
        await viewModel.pauseServerSession(id: "")
        await viewModel.resumeServerSession(id: "")
        await viewModel.wakeServerSession(id: "")

        #expect(await client.recordedActions.isEmpty)
    }

    @Test("server lifecycle and idle policy failures surface local errors")
    @MainActor
    func serverLifecycleAndIdlePolicyFailuresSurfaceLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.configureErrors(pauseServer: MenuBarTestError(description: "pause failed"))
        await viewModel.pauseSelectedServerSession()
        #expect(viewModel.lastError?.contains("pause failed") == true)

        await client.configureErrors(
            pauseServer: nil,
            resumeServer: MenuBarTestError(description: "resume failed")
        )
        await viewModel.resumeSelectedServerSession()
        #expect(viewModel.lastError?.contains("resume failed") == true)

        let serverSessionID = try #require(viewModel.selectedServerSession?.id)
        await client.sendServerStateChanged(
            state: .serverReady,
            runtimeSessions: [
                makeRuntimeSession(
                    serverSessionID: serverSessionID,
                    lifecycleState: .sleeping,
                    powerState: .lightSleep,
                    wakeReason: .requestActivity
                )
            ]
        )
        try await waitForRuntimeViewModelCondition("expected server session to enter sleeping state before wake failure") {
            viewModel.selectedServerSession?.lifecycle == .sleeping
        }

        await client.configureErrors(
            pauseServer: nil,
            resumeServer: nil,
            wakeServer: MenuBarTestError(description: "wake failed")
        )
        await viewModel.wakeSelectedServerSession()
        #expect(viewModel.lastError?.contains("wake failed") == true)

        await client.configureErrors(
            pauseServer: nil,
            resumeServer: nil,
            wakeServer: nil,
            stopServer: MenuBarTestError(description: "stop failed")
        )
        await viewModel.stopSelectedServerSession()
        #expect(viewModel.lastError?.contains("stop failed") == true)

        await client.configureErrors(
            pauseServer: nil,
            resumeServer: nil,
            wakeServer: nil,
            stopServer: nil,
            updateServerIdlePolicy: MenuBarTestError(description: "idle policy failed")
        )
        viewModel.updateSelectedServerSessionAutoSleepEnabled(true)
        viewModel.updateSelectedServerSessionLightSleepAfterSeconds(300)
        viewModel.updateSelectedServerSessionDeepSleepAfterSeconds(900)
        await viewModel.applySelectedServerIdlePolicy()

        #expect(viewModel.lastError?.contains("idle policy failed") == true)
    }

    @Test("chat blocked messages cover starting restored stopped and failed server sessions")
    @MainActor
    func chatBlockedMessagesCoverStartingStoppedAndFailedServerSessions() async throws {
        let client = FakeControlPlaneXPCClient()
        let startingSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            runtimeSessions: [
                makeRuntimeSession(
                    lifecycleState: .loading,
                    powerState: .active,
                    wakeReason: .initialBoot
                )
            ]
        )
        await client.configureSnapshot(startingSnapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "starting blocked"
        await viewModel.submitChatPrompt()
        #expect(viewModel.lastError == "Wait for the Server Session to finish starting before sending chat prompts.")

        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-stopping-chat-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let stoppingServer = DesktopServerSessionState(
            id: "server-session-stopping",
            title: "Stopping Server",
            modelID: "melix-dev-text",
            lifecycle: .stopping,
            powerState: .active
        )
        try operatorSessionStore.save(
            OperatorSessionState(
                selectedSurface: .chat,
                selectedServerSessionID: stoppingServer.id,
                serverSessions: [stoppingServer]
            )
        )

        let stoppingClient = FakeControlPlaneXPCClient()
        let stoppingViewModel = RuntimeViewModel(
            client: stoppingClient,
            operatorSessionStore: operatorSessionStore
        )
        await stoppingViewModel.start()
        stoppingViewModel.selectServerSession(id: stoppingServer.id)
        #expect(stoppingViewModel.selectedServerSession?.lifecycle == .stopped)
        stoppingViewModel.createChatSession()
        stoppingViewModel.bindSelectedChatSessionToServer(serverSessionID: stoppingServer.id)
        #expect(stoppingViewModel.selectedChatServerSession?.lifecycle == .stopped)
        stoppingViewModel.chatComposerText = "stopping blocked"
        await stoppingViewModel.submitChatPrompt()
        #expect(stoppingViewModel.lastError == "Start the bound Server Session before sending chat prompts.")

        let failingClient = FakeControlPlaneXPCClient()
        let failingSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            runtimeSessions: [
                makeRuntimeSession(
                    lifecycleState: .error,
                    powerState: .stopped
                )
            ]
        )
        await failingClient.configureSnapshot(failingSnapshot)
        await failingClient.configureErrors(pauseServer: MenuBarTestError(description: "gpu lost"))
        let failingViewModel = RuntimeViewModel(client: failingClient)
        await failingViewModel.start()
        failingViewModel.createChatSession()
        try bindSelectedChatSessionToPrimaryServer(failingViewModel)
        await failingViewModel.pauseSelectedServerSession()
        failingViewModel.chatComposerText = "error blocked"
        await failingViewModel.submitChatPrompt()
        #expect(failingViewModel.lastError == "Recover the failed Server Session before sending chat prompts. gpu lost")
    }

    @Test("agent integration exports mirror the selected server session and record metrics")
    @MainActor
    func agentIntegrationExportsMirrorTheSelectedServerSessionAndRecordMetrics() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        try await waitForRuntimeViewModelCondition("expected agent exports to be generated") {
            viewModel.agentIntegrationExports.count == AgentIntegrationExportTarget.allCases.count
        }

        let selectedExport = try #require(viewModel.selectedAgentIntegrationExport)
        let metricValues = await metrics.snapshot()

        #expect(viewModel.agentIntegrationExports.map(\.target) == AgentIntegrationExportTarget.allCases)
        #expect(selectedExport.target == .openAICompatible)
        #expect(selectedExport.baseURL == "http://127.0.0.1:8080/v1")
        #expect(selectedExport.modelID == "melix-dev-text")
        #expect(selectedExport.shellSnippet.contains("curl http://127.0.0.1:8080/v1/responses"))
        #expect(metricValues["integration.export_generation_ms"] != nil)
        #expect(metricValues["integration.export_target_count"] == Double(AgentIntegrationExportTarget.allCases.count))
    }

    @Test("agent integration exports render auth placeholders and rebind when the selected server changes")
    @MainActor
    func agentIntegrationExportsRenderAuthPlaceholdersAndRebindWhenTheSelectedServerChanges() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.updateSelectedServerSessionAuthMode(.bearerToken)
        viewModel.updateSelectedServerSessionAuthTokenHint("dev-token")
        viewModel.selectAgentIntegrationTarget(.codex)

        let codexExport = try #require(viewModel.selectedAgentIntegrationExport)
        #expect(codexExport.configFragment.contains("<dev-token>"))
        #expect(codexExport.shellSnippet.contains("OPENAI_API_KEY=<dev-token>"))

        viewModel.createServerSession()
        viewModel.updateSelectedServerSessionHost("0.0.0.0")
        viewModel.updateSelectedServerSessionPort(9090)
        viewModel.updateSelectedServerSessionAuthMode(.none)
        viewModel.selectAgentIntegrationTarget(.openClaw)

        let reboundServer = try #require(viewModel.selectedServerSession)
        let reboundExport = try #require(viewModel.selectedAgentIntegrationExport)
        #expect(reboundServer.port == 9090)
        #expect(reboundExport.baseURL == reboundServer.effectiveBaseURL)
        #expect(reboundExport.configFragment.contains(reboundServer.effectiveBaseURL))
        #expect(reboundExport.configFragment.contains("not-required"))
    }

    @Test("shared-access snapshot hydrates server-session state and agent exports")
    @MainActor
    func sharedAccessSnapshotHydratesServerSessionStateAndAgentExports() async throws {
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            gatewayAccess: makeGatewayAccessSummary(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                acceptedApiKeyCount: 2,
                keyHints: ["desktop-agent", "codex"]
            )
        )
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let session = try #require(viewModel.selectedServerSession)
        let export = try #require(viewModel.selectedAgentIntegrationExport)

        #expect(session.authMode == .apiKeys)
        #expect(session.sharedAccessState == .enabled)
        #expect(session.accessKeyCount == 2)
        #expect(session.accessKeyHints == ["desktop-agent", "codex"])
        #expect(export.configFragment.contains("<desktop-agent>"))
        #expect(export.shellSnippet.contains("x-api-key: <desktop-agent>"))
    }

    @Test("configured-but-disabled shared access stays local trust while surfacing key hints")
    @MainActor
    func configuredButDisabledSharedAccessStaysLocalTrustWhileSurfacingKeyHints() async throws {
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            gatewayAccess: makeGatewayAccessSummary(
                mode: .apiKeys,
                sharedAccessEnabled: false,
                acceptedApiKeyCount: 2,
                keyHints: ["desktop-agent", "codex"]
            )
        )
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let session = try #require(viewModel.selectedServerSession)
        let export = try #require(viewModel.selectedAgentIntegrationExport)
        let authReference = desktopAPIAuthenticationReferenceText(
            selectedSession: session,
            selectedExport: export
        )

        #expect(session.authMode == .none)
        #expect(session.sharedAccessState == .configuredDisabled)
        #expect(session.accessKeyCount == 2)
        #expect(session.accessKeyHints == ["desktop-agent", "codex"])
        #expect(export.configFragment.contains("not-required"))
        #expect(export.shellSnippet.contains("x-api-key") == false)
        #expect(authReference.contains("configured but disabled"))
        #expect(authReference.contains("desktop-agent, codex"))
    }

    @Test("persistent session metrics hydrate remembered-session operator state")
    @MainActor
    func persistentSessionMetricsHydrateRememberedSessionOperatorState() async throws {
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            gatewayAccess: makeGatewayAccessSummary(
                mode: .apiKeys,
                sharedAccessEnabled: true,
                acceptedApiKeyCount: 1,
                keyHints: ["desktop-agent"]
            )
        )
        snapshot.metrics.values["persistent_session.active_session_count"] = 3
        snapshot.metrics.values["persistent_session.remembered_session_count"] = 2
        snapshot.metrics.values["persistent_session.expired_session_count"] = 1
        snapshot.metrics.values["persistent_session.retention_ttl_seconds"] = 86_400
        snapshot.metrics.values["persistent_session.sign_out_latency_ms"] = 14

        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let session = try #require(viewModel.selectedServerSession)
        #expect(session.activeAuthSessionCount == 3)
        #expect(session.rememberedAuthSessionCount == 2)
        #expect(session.expiredRememberedSessionCount == 1)
        #expect(session.authSessionRetentionSeconds == 86_400)
        #expect(session.lastAuthSessionSignOutLatencyMs == 14)
        #expect(session.persistentSessionSummaryText.contains("2 remembered"))
    }

    @Test("persistent session summary covers active-only and empty session states")
    func persistentSessionSummaryCoversActiveOnlyAndEmptyStates() {
        let activeOnly = DesktopServerSessionState(
            id: "active-only",
            title: "Active Only",
            modelID: "melix-dev-text",
            activeAuthSessionCount: 1,
            rememberedAuthSessionCount: 0,
            expiredRememberedSessionCount: 0,
            authSessionRetentionSeconds: 300
        )
        let empty = DesktopServerSessionState(
            id: "empty",
            title: "Empty",
            modelID: "melix-dev-text",
            activeAuthSessionCount: 0,
            rememberedAuthSessionCount: 0,
            expiredRememberedSessionCount: 0,
            authSessionRetentionSeconds: 60
        )

        #expect(activeOnly.persistentSessionSummaryText == "1 gateway sessions active. TTL 300s.")
        #expect(empty.persistentSessionSummaryText == "No remembered gateway sessions. TTL 60s.")
    }

    @Test("switching auth mode away from shared access restores local-only trust state")
    @MainActor
    func switchingAuthModeAwayFromSharedAccessRestoresLocalOnlyTrustState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.updateSelectedServerSessionAuthMode(.apiKeys)
        #expect(viewModel.selectedServerSession?.sharedAccessState == .enabled)

        viewModel.updateSelectedServerSessionAuthMode(.bearerToken)

        let session = try #require(viewModel.selectedServerSession)
        #expect(session.authMode == .bearerToken)
        #expect(session.sharedAccessState == .localOnly)
    }

    @Test("gateway access projection covers none bearer and unknown modes")
    @MainActor
    func gatewayAccessProjectionCoversNoneBearerAndUnknownModes() async throws {
        let noneSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            gatewayAccess: makeGatewayAccessSummary(
                mode: .none,
                sharedAccessEnabled: false,
                acceptedApiKeyCount: 0,
                keyHints: []
            )
        )
        let bearerSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            gatewayAccess: makeGatewayAccessSummary(
                mode: .bearerToken,
                sharedAccessEnabled: false,
                acceptedApiKeyCount: 0,
                keyHints: ["desktop-agent"]
            )
        )
        var unknownGatewayAccess = makeGatewayAccessSummary(
            mode: .none,
            sharedAccessEnabled: false,
            acceptedApiKeyCount: 0,
            keyHints: []
        )
        unknownGatewayAccess.mode = .UNRECOGNIZED(99)
        let unknownSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            gatewayAccess: unknownGatewayAccess
        )

        let noneViewModel = RuntimeViewModel(client: SnapshotControlPlaneXPCClient(snapshot: noneSnapshot))
        await noneViewModel.start()
        let noneSession = try #require(noneViewModel.selectedServerSession)
        #expect(noneSession.authMode == .none)
        #expect(noneSession.sharedAccessState == .localOnly)
        #expect(noneSession.accessKeyCount == 0)

        let bearerViewModel = RuntimeViewModel(client: SnapshotControlPlaneXPCClient(snapshot: bearerSnapshot))
        await bearerViewModel.start()
        let bearerSession = try #require(bearerViewModel.selectedServerSession)
        #expect(bearerSession.authMode == .bearerToken)
        #expect(bearerSession.authTokenHint == "desktop-agent")
        #expect(bearerSession.sharedAccessState == .localOnly)
        #expect(bearerSession.accessKeyCount == 1)
        #expect(bearerSession.accessKeyHints == ["desktop-agent"])

        let unknownViewModel = RuntimeViewModel(client: SnapshotControlPlaneXPCClient(snapshot: unknownSnapshot))
        await unknownViewModel.start()
        let unknownSession = try #require(unknownViewModel.selectedServerSession)
        #expect(unknownSession.authMode == .none)
        #expect(unknownSession.sharedAccessState == .localOnly)
        #expect(unknownSession.accessKeyCount == 0)
        #expect(unknownSession.authTokenHint.isEmpty)
    }

    @Test("server session shared-access summary text covers configured disabled and enabled states")
    func serverSessionSharedAccessSummaryTextCoversConfiguredDisabledAndEnabledStates() {
        let configuredDisabled = DesktopServerSessionState(
            id: "configured-disabled",
            title: "Configured Disabled",
            modelID: "melix-dev-text",
            sharedAccessState: .configuredDisabled
        )
        let enabledSingleKey = DesktopServerSessionState(
            id: "enabled-single",
            title: "Enabled Single",
            modelID: "melix-dev-text",
            sharedAccessState: .enabled,
            accessKeyCount: 1
        )
        let enabledMultipleKeys = DesktopServerSessionState(
            id: "enabled-multi",
            title: "Enabled Multiple",
            modelID: "melix-dev-text",
            sharedAccessState: .enabled,
            accessKeyCount: 2
        )

        #expect(configuredDisabled.sharedAccessSummaryText == "Shared access is configured but disabled.")
        #expect(enabledSingleKey.sharedAccessSummaryText == "Shared access is enabled for 1 key.")
        #expect(enabledMultipleKeys.sharedAccessSummaryText == "Shared access is enabled for 2 keys.")
    }

    @Test("agent integration exports stay empty when no server session is available")
    @MainActor
    func agentIntegrationExportsStayEmptyWhenNoServerSessionIsAvailable() async throws {
        let client = EmptySnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        #expect(viewModel.serverSessions.isEmpty)
        #expect(viewModel.agentIntegrationExports.isEmpty)
        #expect(viewModel.selectedAgentIntegrationExport == nil)
    }

    @Test("empty workspace creates unbound chat sessions until a server is selected")
    @MainActor
    func emptyWorkspaceCreatesUnboundChatSessionsUntilServerSelection() async throws {
        let client = EmptySnapshotControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        #expect(viewModel.serverSessions.isEmpty)
        #expect(viewModel.chatSessions.count == 1)
        #expect(viewModel.selectedChatSession?.serverSessionID == "")

        viewModel.createChatSession()
        #expect(viewModel.chatSessions.count == 2)
        #expect(viewModel.selectedChatSession?.serverSessionID == "")
        #expect(viewModel.selectedSurface == .chat)

        viewModel.chatComposerText = "wait for server"
        await viewModel.submitChatPrompt()
        #expect(viewModel.chatStatusText == "Choose Server")
        #expect(viewModel.lastError == "Choose a Server Session before sending chat prompts.")

        viewModel.createServerSession()

        let seededServer = try #require(viewModel.selectedServerSession)
        let seededChat = try #require(viewModel.selectedChatSession)
        #expect(viewModel.serverSessions.count == 1)
        #expect(viewModel.chatSessions.count == 2)
        #expect(seededServer.title == "Primary Server")
        #expect(seededServer.modelID == "melix-dev-text")
        #expect(seededServer.port == 8080)
        #expect(seededChat.serverSessionID == "")

        viewModel.bindSelectedChatSessionToServer(serverSessionID: seededServer.id)
        #expect(viewModel.selectedChatSession?.serverSessionID == seededServer.id)
        #expect(viewModel.selectedSurface == .server)
    }

    @Test("chat sessions can be exported forked and reselected without losing server bindings")
    @MainActor
    func chatSessionsCanBeExportedForkedAndReselected() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Export this chat session"
        await viewModel.submitChatPrompt()

        let originalSession = try #require(viewModel.selectedChatSession)
        let exportPath = try #require(viewModel.exportSelectedChatSession())
        #expect(FileManager.default.fileExists(atPath: exportPath))
        #expect(viewModel.selectedChatSession?.exportPath == exportPath)

        viewModel.forkSelectedChatSession()

        let forkedSession = try #require(viewModel.selectedChatSession)
        #expect(viewModel.chatSessions.count == 2)
        #expect(forkedSession.title == "\(originalSession.title) Fork")
        #expect(forkedSession.serverSessionID == originalSession.serverSessionID)
        #expect(forkedSession.branchID == "branch-2")
        #expect(forkedSession.branchTitle == "Branch 2")
        #expect(forkedSession.transcript == originalSession.transcript)
        #expect(forkedSession.exportPath == exportPath)

        viewModel.selectChatSession(id: originalSession.id)
        #expect(viewModel.selectedChatSession?.id == originalSession.id)

        viewModel.selectChatSession(id: "missing-chat-session")
        #expect(viewModel.selectedChatSession?.id == originalSession.id)

        viewModel.deleteChatSession(id: originalSession.id)
        #expect(viewModel.chatSessions.count == 1)
        #expect(viewModel.selectedChatSession?.id == forkedSession.id)

        viewModel.deleteChatSession(id: forkedSession.id)
        #expect(viewModel.chatSessions.isEmpty)
        #expect(viewModel.selectedChatSession == nil)
        #expect(viewModel.chatTranscript.isEmpty)
    }

    @Test("chat export sanitizes transcript markdown without mutating stored transcript state")
    @MainActor
    func chatExportSanitizesTranscriptMarkdownWithoutMutatingStoredTranscriptState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureChatEvents([
            .queued(lane: "text.decode.interactive", queuePosition: 0, backpressure: 0),
            .admitted(lane: "text.decode.interactive", workerID: "swift-text-worker", queueDelayMs: 0.5),
            .tokenDelta("<b>assistant</b> [click](javascript:alert(1))"),
            .completed(
                finishReason: "stop",
                assistantText: "<b>assistant</b> [click](javascript:alert(1))",
                reasoningText: ""
            ),
        ])

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "<i>Export me</i> file:///tmp/melix"
        await viewModel.submitChatPrompt()

        let assistantEntry = try #require(viewModel.chatTranscript.first(where: { $0.kind == .assistant }))
        #expect(assistantEntry.body.contains("<b>assistant</b>"))
        let exportPath = try #require(viewModel.exportSelectedChatSession())
        let exported = try String(contentsOfFile: exportPath, encoding: .utf8)

        #expect(exported.contains("<b>") == false)
        #expect(exported.contains("<i>") == false)
        #expect(exported.contains("javascript:") == false)
        #expect(exported.contains("file:///tmp/melix") == false)
        #expect(exported.contains("assistant click"))
        #expect(exported.contains("[unsafe link removed]"))
        #expect(viewModel.selectedChatSession?.transcript.contains(where: { $0.body.contains("<b>assistant</b>") }) == true)
    }

    @Test("guarded server and chat actions no-op safely before hydration")
    @MainActor
    func guardedServerAndChatActionsNoOpSafelyBeforeHydration() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        viewModel.chatComposerText = "hello from a cold start"
        await viewModel.startSelectedServerSession()
        await viewModel.stopSelectedServerSession()
        viewModel.clearChatTranscript()
        viewModel.forkSelectedChatSession()
        let exportPath = viewModel.exportSelectedChatSession()
        await viewModel.submitChatPrompt()

        #expect(exportPath == nil)
        #expect(await client.recordedActions.isEmpty)
        #expect(viewModel.chatStatusText == "No Server Session")
        #expect(viewModel.lastError == "Create a Server Session before sending chat prompts.")
        #expect(viewModel.selectedSurface == .server)
    }

    @Test("server session sync keeps missing bindings unavailable and surfaces recovery banners")
    @MainActor
    func serverSessionSyncKeepsMissingBindingsUnavailableAndSurfacesRecoveryBanners() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.updateSelectedServerSessionModelID("missing-model")

        let alternateTextSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(modelID: "melix-alt-text", state: .modelWarm)]
        )
        await client.configureSnapshot(alternateTextSnapshot)
        await viewModel.refreshDesktopFoundation()

        #expect(viewModel.selectedServerSession?.modelID == "missing-model")
        #expect(viewModel.selectedServerSession?.lifecycle == .unavailable)
        #expect(viewModel.selectedServerSession?.lastKnownModelStateText == "Unavailable")
        #expect(viewModel.selectedChatServerSession?.modelID == "missing-model")

        var drainingEvent = Melix_Controlplane_V1_ServerStateChanged()
        drainingEvent.state = .serverDraining
        await client.sendServerStateChanged(state: .serverDraining)
        try await waitForRuntimeViewModelCondition("warning banner should surface draining runtime state") {
            viewModel.desktopBannerState?.title == "Runtime Needs Monitoring"
        }
        #expect(viewModel.desktopBannerState?.title == "Runtime Needs Monitoring")

        let imageOnlySnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeCapabilityModelSummary(
                modelID: "melix-dev-image",
                kind: "image",
                state: .modelWarm,
                features: ["image_generate"]
            )]
        )
        await client.configureSnapshot(imageOnlySnapshot)
        await viewModel.refreshDesktopFoundation()

        #expect(viewModel.selectedServerSession?.lifecycle == .unavailable)
        #expect(viewModel.selectedServerSession?.lastKnownModelStateText == "Unavailable")

        let failingClient = FakeControlPlaneXPCClient()
        let failingSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            runtimeSessions: [
                makeRuntimeSession(
                    lifecycleState: .error,
                    powerState: .stopped
                )
            ]
        )
        await failingClient.configureSnapshot(failingSnapshot)
        await failingClient.configureErrors(pauseServer: MenuBarTestError(description: "pause failed"))
        let failingViewModel = RuntimeViewModel(client: failingClient)
        await failingViewModel.start()
        await failingViewModel.pauseSelectedServerSession()

        let failingBanner = try #require(failingViewModel.desktopBannerState)
        #expect(failingBanner.severity == .critical)
        #expect(failingBanner.title.contains("Needs Recovery"))
        #expect(failingBanner.detail.contains("pause failed"))
    }

    @Test("critical banner surfaces failed runtime state")
    @MainActor
    func criticalBannerSurfacesFailedRuntimeState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendServerStateChanged(state: .serverFailed)

        try await waitForRuntimeViewModelCondition("critical banner should surface failed runtime state") {
            viewModel.desktopBannerState?.severity == .critical
        }

        let banner = try #require(viewModel.desktopBannerState)
        #expect(banner.title == "Operator Attention Required")
        #expect(banner.detail == viewModel.connectionDetailText)
    }

    @Test("audio setup remediation stays contextual instead of becoming a desktop banner")
    @MainActor
    func audioSetupRemediationStaysContextualInsteadOfBecomingDesktopBanner() async throws {
        let client = FakeControlPlaneXPCClient()
        var whisper = ModelCatalog.mlxWhisperModel()
        whisper.settings.ext["melix.audio.runtime_pack_state"] = "missing"
        whisper.settings.ext["melix.audio.runtime_pack_id"] = "melix-audio-runtime-pack"
        whisper.settings.ext["melix.audio.model_state"] = "catalog_default"
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [ModelCatalog.devTextModel(), whisper]
        )
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let action = try #require(viewModel.audioSetupActions.first)

        #expect(viewModel.desktopSignalStates.contains { $0.title == "Audio Setup Required" } == false)
        #expect(viewModel.pendingAudioSetupPrompt == nil)
        #expect(action.modelID == "melix-whisper-mlx")
        #expect(action.actionTitle == "Install Audio Support")
        #expect(action.detail.contains("melix-audio-runtime-pack"))

        viewModel.presentAudioSetupPrompt(action)

        let prompt = try #require(viewModel.pendingAudioSetupPrompt)
        #expect(prompt.title == "Audio Support Required")
        #expect(prompt.primaryActionTitle == "Install Audio Support")
        #expect(prompt.modelID == "melix-whisper-mlx")
    }

    @Test("runtime endpoint projection drives primary model and integration exports")
    @MainActor
    func runtimeEndpointProjectionDrivesPrimaryModelAndIntegrationExports() async throws {
        let client = FakeControlPlaneXPCClient()
        let baseModel = makeCapabilityModelSummary(
            modelID: "melix-dev-text",
            kind: "text",
            state: .modelWarm,
            features: ["chat"]
        )
        let selectedModel = makeCapabilityModelSummary(
            modelID: "melix-selected-text",
            kind: "text",
            state: .modelWarm,
            features: ["chat"]
        )
        let listener = makeGatewayConfigListener(
            serverSessionID: "server-session-1",
            requestedHost: "127.0.0.1",
            requestedPort: 8080,
            effectiveHost: "127.0.0.1",
            effectivePort: 12434,
            servedModelID: "melix-selected-text",
            rateLimitPerMinute: 120,
            timeoutSeconds: 120,
            source: .environmentDefaults,
            activeBinding: true,
            requiresRestart: false
        )
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [baseModel, selectedModel],
                runtimeSessions: [makeRuntimeSession(serverSessionID: "server-session-1")],
                gatewayConfig: makeGatewayConfigSummary(listener: listener)
            )
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        #expect(viewModel.primaryModel?.modelID == "melix-selected-text")
        #expect(viewModel.desktopRuntimeEndpointState.effectiveBaseURL == "http://127.0.0.1:12434/v1")
        #expect(viewModel.desktopRuntimeEndpointState.requestedBaseURL == "http://127.0.0.1:8080/v1")
        #expect(viewModel.agentIntegrationExports.isEmpty == false)
        #expect(viewModel.agentIntegrationExports.allSatisfy { $0.baseURL == "http://127.0.0.1:12434/v1" })
        #expect(viewModel.agentIntegrationExports.allSatisfy { $0.modelID == "melix-selected-text" })
    }

    @Test("gateway projection preserves restored server model when listener model is stale")
    @MainActor
    func gatewayProjectionPreservesRestoredServerModelWhenListenerModelIsStale() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-gateway-stale-model-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let selectedModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let staleGatewayModelID = "melix-dev-qwen-local"
        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let restoredServerSession = DesktopServerSessionState(
            id: "server-session-1",
            title: "Primary Session",
            modelID: selectedModelID,
            lifecycle: .running
        )
        try operatorSessionStore.save(
            OperatorSessionState(
                selectedSurface: .chat,
                selectedServerSessionID: restoredServerSession.id,
                serverSessions: [restoredServerSession]
            )
        )

        let client = FakeControlPlaneXPCClient()
        let listener = makeGatewayConfigListener(
            serverSessionID: restoredServerSession.id,
            requestedHost: "127.0.0.1",
            requestedPort: 8080,
            effectiveHost: "127.0.0.1",
            effectivePort: 11_434,
            servedModelID: staleGatewayModelID,
            rateLimitPerMinute: 120,
            timeoutSeconds: 120,
            source: .configFileImport,
            activeBinding: true,
            requiresRestart: false
        )
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: staleGatewayModelID, state: .modelWarm),
                    makeModelSummary(modelID: selectedModelID, state: .modelWarm),
                ],
                runtimeSessions: [makeRuntimeSession(serverSessionID: restoredServerSession.id)],
                gatewayConfig: makeGatewayConfigSummary(listener: listener)
            )
        )

        let viewModel = RuntimeViewModel(client: client, operatorSessionStore: operatorSessionStore)
        await viewModel.start()

        #expect(viewModel.selectedServerSession?.modelID == selectedModelID)
        #expect(viewModel.primaryModel?.modelID == selectedModelID)
        #expect(viewModel.desktopRuntimeEndpointState.effectiveBaseURL == "http://127.0.0.1:11434/v1")

        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Use the restored server model"

        await viewModel.submitChatPrompt()

        let actions = await client.recordedActions
        #expect(actions.contains("chat:\(selectedModelID)"))
        #expect(actions.contains("chat:\(staleGatewayModelID)") == false)
    }

    @Test("chat submission uses bound server model even before registry refresh surfaces it")
    @MainActor
    func chatSubmissionUsesBoundServerModelBeforeRegistryRefreshSurfacesIt() async throws {
        let client = FakeControlPlaneXPCClient()
        let selectedModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let listener = makeGatewayConfigListener(
            serverSessionID: "server-session-1",
            requestedHost: "127.0.0.1",
            requestedPort: 8080,
            effectiveHost: "127.0.0.1",
            effectivePort: 8080,
            servedModelID: selectedModelID,
            rateLimitPerMinute: 120,
            timeoutSeconds: 120,
            source: .environmentDefaults,
            activeBinding: true,
            requiresRestart: false
        )
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeCapabilityModelSummary(
                    modelID: "melix-dev-text",
                    kind: "text",
                    state: .modelWarm,
                    features: ["chat"]
                )],
                runtimeSessions: [makeRuntimeSession(serverSessionID: "server-session-1")],
                gatewayConfig: makeGatewayConfigSummary(listener: listener)
            )
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Use the selected server"

        await viewModel.submitChatPrompt()

        let actions = await client.recordedActions
        let snapshotIndex = try #require(actions.firstIndex(of: "snapshot"))
        let chatIndex = try #require(actions.firstIndex(of: "chat:\(selectedModelID)"))
        #expect(snapshotIndex < chatIndex)
        #expect(actions.contains("load:\(selectedModelID)") == false)
        #expect(actions.contains("chat:melix-dev-text") == false)
    }

    @Test("audio setup actions dispatch install and download operations then refresh snapshot")
    @MainActor
    func audioSetupActionsDispatchInstallAndDownloadOperationsThenRefreshSnapshot() async throws {
        let client = FakeControlPlaneXPCClient()

        var missingRuntime = ModelCatalog.mlxWhisperModel()
        missingRuntime.settings.ext["melix.audio.runtime_pack_state"] = "missing"
        missingRuntime.settings.ext["melix.audio.runtime_pack_id"] = "melix-audio-runtime-pack"
        missingRuntime.settings.ext["melix.audio.model_state"] = "catalog_default"

        var runtimeInstalled = missingRuntime
        runtimeInstalled.settings.ext["melix.audio.runtime_pack_state"] = "installed"
        runtimeInstalled.settings.ext["melix.audio.model_state"] = "catalog_default"

        var managedLocal = runtimeInstalled
        managedLocal.settings.ext["melix.audio.model_state"] = "managed_local"
        managedLocal.settings.ext["melix.model_path"] = "/Users/test/Library/Application Support/Melix/models/default-managed/hf/mlx-community/whisper-large-v3-turbo-asr-fp16/mlx-audio"

        await client.configureSnapshot(
            makeSnapshot(serverState: .serverReady, models: [ModelCatalog.devTextModel(), missingRuntime])
        )
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "install_audio_runtime",
                outputPath: "/Users/test/Library/Application Support/Melix/runtime-packs/audio/melix-audio-runtime-pack/0.3.0",
                manifestJSON: "{}"
            ),
            forNamedOperation: "install_audio_runtime"
        )
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "download",
                outputPath: managedLocal.settings.ext["melix.model_path"] ?? "",
                manifestJSON: "{}"
            ),
            forNamedOperation: "download"
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let installAction = try #require(viewModel.audioSetupActions.first)
        await client.configureSnapshot(
            makeSnapshot(serverState: .serverReady, models: [ModelCatalog.devTextModel(), runtimeInstalled])
        )
        await viewModel.performAudioSetupAction(installAction)

        let installRequest = try #require(await client.recordedModelOperationRequests.first)
        #expect(installRequest.operation == "install_audio_runtime")
        #expect(installRequest.modelID == "melix-whisper-mlx")
        #expect(viewModel.audioSetupActions.first?.actionTitle == "Download Audio Model")

        let downloadAction = try #require(viewModel.audioSetupActions.first)
        await client.configureSnapshot(
            makeSnapshot(serverState: .serverReady, models: [ModelCatalog.devTextModel(), managedLocal])
        )
        await viewModel.performAudioSetupAction(downloadAction)

        let requests = await client.recordedModelOperationRequests
        #expect(requests.count == 3)
        #expect(requests[1].operation == "download")
        #expect(requests[1].modelID == "melix-whisper-mlx")
        #expect(requests[2].operation == "registry_snapshot")
        #expect(viewModel.audioSetupActions.isEmpty)
        #expect(viewModel.lastModelOperation?.operation == "download")
    }

    @Test("download queue refresh parses registry snapshot rows and surfaces recovery signals")
    @MainActor
    func downloadQueueRefreshParsesRegistrySnapshotRowsAndSurfacesRecoverySignals() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [],
                    downloads: [
                        MenuBarDownloadFixture(
                            jobID: "model-ops-0043",
                            sourceModel: "melix-dev-text",
                            status: "stalled",
                            stage: "download",
                            pct: 0.75,
                            outputDir: "/tmp/melix-downloads/melix-dev-text",
                            outputPath: "/tmp/melix-downloads/melix-dev-text/download.artifact",
                            partialPath: "/tmp/melix-downloads/melix-dev-text/download.artifact.partial",
                            statePath: "/tmp/melix-downloads/melix-dev-text/download.state.json",
                            selectedMirror: "https://mirror.example/hf",
                            downloadedBytes: 3072,
                            totalBytes: 4096,
                            resumeUsed: true,
                            resumeFromBytes: 1024,
                            retryCount: 2,
                            stallDetectionCount: 1,
                            stallReason: "no_progress_timeout",
                            resumeReady: true
                        )
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshDownloadQueueState()

        let queueEntry = try #require(viewModel.downloadQueue.first)
        #expect(queueEntry.jobID == "model-ops-0043")
        #expect(queueEntry.resumeReady)
        #expect(queueEntry.progressText.contains("75%"))
        #expect(queueEntry.transferDetailText.contains("mirror.example/hf"))
        #expect(viewModel.desktopSignalStates.contains(where: { $0.title == "Download Recovery Available" }))
        #expect(await client.recordedModelOperationRequests.last?.operation == "registry_snapshot")
    }

    @Test("download queue entry state formats status progress transfer and activity labels")
    func downloadQueueEntryStateFormatsStatusProgressTransferAndActivityLabels() {
        let stalled = makeRuntimeDownloadQueueEntryState(
            status: "stalled",
            pct: 0.25,
            selectedMirror: "https://mirror.example/hf",
            downloadedBytes: 1024,
            totalBytes: 4096,
            resumeUsed: true,
            resumeFromBytes: 512,
            retryCount: 2,
            stallDetectionCount: 1,
            stallReason: "no_progress_timeout",
            resumeReady: true
        )
        let running = makeRuntimeDownloadQueueEntryState(status: "running", pct: 0.1, totalBytes: 0)
        let retrying = makeRuntimeDownloadQueueEntryState(status: "retrying")
        let completed = makeRuntimeDownloadQueueEntryState(status: "completed")
        let failed = makeRuntimeDownloadQueueEntryState(status: "failed")
        let unknown = makeRuntimeDownloadQueueEntryState(status: " ")

        #expect(stalled.statusText == "Stalled")
        #expect(running.statusText == "Running")
        #expect(retrying.statusText == "Retrying")
        #expect(completed.statusText == "Completed")
        #expect(failed.statusText == "Failed")
        #expect(unknown.statusText == "Unknown")
        #expect(stalled.progressText.contains("25%"))
        #expect(running.progressText == "10%")
        #expect(stalled.transferDetailText.contains("https://mirror.example/hf"))
        #expect(stalled.transferDetailText.contains("retries 2"))
        #expect(stalled.transferDetailText.contains("stall detections 1"))
        #expect(stalled.transferDetailText.contains("no progress timeout"))
        #expect(stalled.transferDetailText.contains("resumed from"))
        #expect(stalled.resumeActionTitle == "Resume Download")
        #expect(stalled.isActive == false)
        #expect(running.isActive)
        #expect(retrying.isActive)
    }

    @Test("resume download reuses original output directory and mirror before refreshing queue state")
    @MainActor
    func resumeDownloadReusesOriginalOutputDirectoryAndMirror() async throws {
        let client = FakeControlPlaneXPCClient()
        let fixture = MenuBarDownloadFixture(
            jobID: "model-ops-0044",
            sourceModel: "melix-dev-text",
            status: "failed",
            stage: "download",
            pct: 0.5,
            outputDir: "/tmp/melix-downloads/melix-dev-text",
            outputPath: "/tmp/melix-downloads/melix-dev-text/download.artifact",
            partialPath: "/tmp/melix-downloads/melix-dev-text/download.artifact.partial",
            statePath: "/tmp/melix-downloads/melix-dev-text/download.state.json",
            selectedMirror: "https://mirror.example/resume",
            downloadedBytes: 2048,
            totalBytes: 4096,
            resumeUsed: true,
            resumeFromBytes: 1024,
            retryCount: 1,
            stallDetectionCount: 1,
            stallReason: "no_progress_timeout",
            resumeReady: true
        )
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(roots: [], downloads: [fixture])
            ),
            forNamedOperation: "registry_snapshot"
        )
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "download",
                outputPath: fixture.outputPath,
                manifestJSON: "{}"
            ),
            forNamedOperation: "download"
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshDownloadQueueState()
        await viewModel.resumeDownload(jobID: fixture.jobID)

        let requests = await client.recordedModelOperationRequests
        let downloadRequest = try #require(requests.first(where: { $0.operation == "download" }))
        #expect(downloadRequest.outputDir == fixture.outputDir)
        #expect(downloadRequest.ext["mirror_url"] == fixture.selectedMirror)
        #expect(requests.filter { $0.operation == "registry_snapshot" }.count == 2)
    }

    @Test("download queue refresh handles empty catalog targets registry errors and queue ordering")
    @MainActor
    func downloadQueueRefreshHandlesEmptyTargetsErrorsAndOrdering() async throws {
        let emptyClient = FakeControlPlaneXPCClient()
        await emptyClient.configureSnapshot(makeSnapshot(serverState: .serverReady, models: []))
        let emptyViewModel = RuntimeViewModel(client: emptyClient)
        await emptyViewModel.refreshDownloadQueueState()
        #expect(await emptyClient.recordedModelOperationRequests.isEmpty)

        let failingClient = FakeControlPlaneXPCClient()
        await failingClient.configureErrors(modelOperation: MenuBarTestError(description: "registry snapshot failed"))
        let failingViewModel = RuntimeViewModel(client: failingClient)
        await failingViewModel.start()
        await failingViewModel.refreshDownloadQueueState()
        #expect(failingViewModel.lastError?.contains("registry snapshot failed") == true)

        let orderingClient = FakeControlPlaneXPCClient()
        let manifestJSON = """
        {
          "jobs": [],
          "adapters": [],
          "derived_models": [],
          "downloads": [
            {
              "job_id": "model-ops-0040",
              "source_model": "melix-dev-text",
              "status": "running",
              "stage": "download",
              "pct": 0.2,
              "output_dir": "/tmp/melix-downloads/melix-dev-text",
              "output_path": "/tmp/melix-downloads/melix-dev-text/download.artifact",
              "partial_path": "/tmp/melix-downloads/melix-dev-text/download.artifact.partial",
              "state_path": "/tmp/melix-downloads/melix-dev-text/download.state.json",
              "selected_mirror": "",
              "downloaded_bytes": 512,
              "total_bytes": 4096,
              "resume_used": false,
              "resume_from_bytes": 0,
              "retry_count": 0,
              "stall_detection_count": 0,
              "stall_reason": "",
              "resume_ready": false
            },
            {
              "job_id": "model-ops-0009",
              "source_model": "melix-dev-text",
              "status": "failed",
              "stage": "download",
              "pct": 0.6,
              "output_dir": "/tmp/melix-downloads/melix-dev-text",
              "output_path": "/tmp/melix-downloads/melix-dev-text/download.artifact",
              "partial_path": "/tmp/melix-downloads/melix-dev-text/download.artifact.partial",
              "state_path": "/tmp/melix-downloads/melix-dev-text/download.state.json",
              "selected_mirror": "https://mirror.example/recoverable",
              "downloaded_bytes": 2048,
              "total_bytes": 4096,
              "resume_used": true,
              "resume_from_bytes": 1024,
              "retry_count": 1,
              "stall_detection_count": 1,
              "stall_reason": "no_progress_timeout",
              "resume_ready": true
            },
            {
              "job_id": "model-ops-invalid",
              "source_model": "",
              "status": "failed",
              "stage": "download",
              "pct": 0.1,
              "output_dir": "",
              "output_path": "",
              "partial_path": "",
              "state_path": "",
              "selected_mirror": "",
              "downloaded_bytes": 0,
              "total_bytes": 0,
              "resume_used": false,
              "resume_from_bytes": 0,
              "retry_count": 0,
              "stall_detection_count": 0,
              "stall_reason": "",
              "resume_ready": true
            }
          ],
          "model_registry": {
            "scanned_at_unix_ms": 1712300000000,
            "roots": []
          }
        }
        """
        await orderingClient.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: manifestJSON
            ),
            forNamedOperation: "registry_snapshot"
        )
        let orderingViewModel = RuntimeViewModel(client: orderingClient)
        await orderingViewModel.start()
        await orderingViewModel.refreshDownloadQueueState()

        #expect(orderingViewModel.downloadQueue.count == 2)
        #expect(orderingViewModel.downloadQueue.first?.jobID == "model-ops-0009")
        #expect(orderingViewModel.downloadQueue.last?.jobID == "model-ops-0040")
    }

    @Test("download primary model uses a stable per-model output directory and refreshes queue state")
    @MainActor
    func downloadPrimaryModelUsesStablePerModelOutputDirectoryAndRefreshesQueueState() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "download",
                outputPath: "/tmp/melix-downloads/melix-dev-text/download.artifact",
                manifestJSON: "{}"
            ),
            forNamedOperation: "download"
        )
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [],
                    downloads: [
                        MenuBarDownloadFixture(
                            jobID: "job-download",
                            sourceModel: "melix-dev-text",
                            status: "running",
                            stage: "download",
                            pct: 1.0,
                            outputDir: "/tmp/melix-downloads/melix-dev-text",
                            outputPath: "/tmp/melix-downloads/melix-dev-text/download.artifact",
                            partialPath: "/tmp/melix-downloads/melix-dev-text/download.artifact.partial",
                            statePath: "/tmp/melix-downloads/melix-dev-text/download.state.json",
                            selectedMirror: "https://huggingface.co",
                            downloadedBytes: 4096,
                            totalBytes: 4096,
                            resumeReady: false
                        )
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.downloadPrimaryModel()

        let requests = await client.recordedModelOperationRequests
        let downloadRequest = try #require(requests.first(where: { $0.operation == "download" }))
        let refreshRequest = try #require(requests.last(where: { $0.operation == "registry_snapshot" }))

        #expect(downloadRequest.outputDir.contains("melix-downloads"))
        #expect(downloadRequest.outputDir.contains("melix-dev-text"))
        #expect(refreshRequest.operation == "registry_snapshot")
        #expect(viewModel.downloadQueue.first?.sourceModel == "melix-dev-text")
    }

    @Test("download and lora actions use the shared operator command runner when available")
    @MainActor
    func downloadAndLoraActionsUseSharedOperatorCommandRunnerWhenAvailable() async throws {
        let directClient = FakeControlPlaneXPCClient()
        let runnerClient = FakeControlPlaneXPCClient()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-runner-tool-actions-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        await runnerClient.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "download",
                outputPath: "/tmp/melix-downloads/melix-dev-text/download.artifact",
                manifestJSON: "{}"
            ),
            forNamedOperation: "download"
        )
        await runnerClient.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "train_lora",
                outputPath: "/tmp/melix-train-lora/train_lora.adapter.json",
                manifestJSON: "{}"
            ),
            forNamedOperation: "train_lora"
        )
        await runnerClient.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "activate_adapter",
                outputPath: "/tmp/melix-activate/activate_adapter.derived_model.json",
                manifestJSON: "{}"
            ),
            forNamedOperation: "activate_adapter"
        )
        await runnerClient.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeRegistrySnapshotManifest(
                    publishedRepo: "",
                    targetRepo: "melix/adapters/hf-demo-adapter"
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        let operatorStore = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        let runner = MelixCLIRunner(
            client: runnerClient,
            environment: ["MELIX_HOME": temporaryRoot.path],
            operatorSessionStore: operatorStore
        )
        let viewModel = RuntimeViewModel(
            client: directClient,
            operatorCommandRunner: runner
        )

        await viewModel.start()
        viewModel.selectedLoraModelID = "melix-dev-text"
        viewModel.loraDatasetSourceKind = .huggingFaceDataset
        viewModel.loraHFDatasetPath = "neuralmagic/ultrachat_2k"
        viewModel.loraHFTrainSplit = "train_sft"
        viewModel.loraChatFeature = "messages"
        viewModel.loraAdapterName = "hf-demo-adapter"
        viewModel.loraDerivedModelAlias = "melix-dev-text-ultrachat"

        await viewModel.downloadPrimaryModel()
        await viewModel.trainPrimaryModel()
        await viewModel.activateLatestAdapter()

        let directRequests = await directClient.recordedModelOperationRequests
        let runnerRequests = await runnerClient.recordedModelOperationRequests
        let hasRunnerDownload = runnerRequests.contains { request in
            request.operation == "download" && request.modelID == "melix-dev-text"
        }
        let hasRunnerTrain = runnerRequests.contains { request in
            request.operation == "train_lora" && request.modelID == "melix-dev-text"
        }
        let hasRunnerActivate = runnerRequests.contains { request in
            request.operation == "activate_adapter" && request.modelID == "melix-dev-text"
        }

        #expect(directRequests.isEmpty)
        #expect(hasRunnerDownload)
        #expect(hasRunnerTrain)
        #expect(hasRunnerActivate)
    }

    @Test("model library and hub actions use the shared operator command runner when available")
    @MainActor
    func modelLibraryAndHubActionsUseSharedOperatorCommandRunnerWhenAvailable() async throws {
        let directClient = FakeControlPlaneXPCClient()
        let runnerClient = FakeControlPlaneXPCClient()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-runner-model-hub-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        await directClient.configureErrors(
            load: MenuBarTestError(description: "direct load should not run"),
            unload: MenuBarTestError(description: "direct unload should not run"),
            modelInfo: MenuBarTestError(description: "direct inspect should not run"),
            modelOperation: MenuBarTestError(description: "direct download should not run")
        )

        var info = Melix_Controlplane_V1_ModelInfo()
        info.ok = true
        info.modelKind = "text"
        info.maxContext = 8_192
        info.supportedParsers = ["text", "json"]
        info.supportedModalities = ["text"]
        await runnerClient.configureModelInfo(info)

        var searchResult = Melix_Controlplane_V1_HubSearchResult()
        searchResult.nextCursor = "cursor:page-2"
        var searchModel = Melix_Controlplane_V1_HubModelSummary()
        searchModel.repoID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        searchModel.author = "mlx-community"
        searchModel.modelName = "Qwen3.5-0.8B-OptiQ-4bit"
        searchModel.pipelineTag = "text-generation"
        searchModel.downloads = 1234
        searchModel.likes = 88
        searchModel.mlxCompatible = true
        searchResult.models = [searchModel]
        await runnerClient.configureHubSearchResult(searchResult)

        var card = Melix_Controlplane_V1_HubModelCard()
        card.repoID = searchModel.repoID
        card.author = searchModel.author
        card.modelName = searchModel.modelName
        card.summary = "Compact Qwen acceptance model."
        card.pipelineTag = "text-generation"
        card.mlxCompatible = true
        card.tags = ["mlx", "4bit"]
        card.baseModels = ["Qwen/Qwen3.5-0.8B"]
        await runnerClient.configureHubModelCard(card)

        await runnerClient.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "download",
                outputPath: "/tmp/melix-downloads/qwen35/download.artifact",
                manifestJSON: "{}"
            ),
            forNamedOperation: "download"
        )
        await runnerClient.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [],
                    downloads: [
                        MenuBarDownloadFixture(
                            jobID: "download-qwen35",
                            sourceModel: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit",
                            status: "completed",
                            stage: "materialize",
                            pct: 1.0,
                            outputDir: "/tmp/melix-downloads/qwen35",
                            outputPath: "/tmp/melix-downloads/qwen35/download.artifact",
                            partialPath: "",
                            statePath: "/tmp/melix-downloads/qwen35/download.state.json",
                            selectedMirror: "https://huggingface.co",
                            downloadedBytes: 4096,
                            totalBytes: 4096,
                            resumeReady: false
                        )
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let sharedOperatorStore = MelixOperatorSessionStore(melixHome: melixHome)
        let operatorStore = OperatorSessionStore(melixHome: melixHome)
        let runner = MelixCLIRunner(
            client: runnerClient,
            environment: ["MELIX_HOME": temporaryRoot.path],
            operatorSessionStore: sharedOperatorStore
        )
        let viewModel = RuntimeViewModel(
            client: directClient,
            operatorSessionStore: operatorStore,
            operatorCommandRunner: runner
        )

        await viewModel.start()
        await viewModel.loadModel(modelID: "melix-dev-text")
        await viewModel.fetchModelInfo(modelID: "melix-dev-text")
        await viewModel.unloadModel(modelID: "melix-dev-text")

        viewModel.modelHubSearchQuery = "qwen3.5"
        viewModel.modelHubSearchMLXOnly = true
        viewModel.modelHubSelectedRevision = "main"
        viewModel.modelHubTokenDraft = "hf_secret_token"

        await viewModel.searchModelHub()
        await viewModel.inspectHubModel(repoID: searchModel.repoID)
        await viewModel.downloadHubModel(repoID: searchModel.repoID)

        #expect(await directClient.recordedHubSearchRequests.isEmpty)
        #expect(await directClient.recordedHubModelCardRequests.isEmpty)
        #expect(await directClient.recordedModelOperationRequests.isEmpty)
        #expect(await directClient.recordedActions.contains("load:melix-dev-text") == false)
        #expect(await directClient.recordedActions.contains("unload:melix-dev-text") == false)
        #expect(await directClient.recordedActions.contains("info:melix-dev-text") == false)

        #expect(await runnerClient.recordedActions.contains("load:melix-dev-text"))
        #expect(await runnerClient.recordedActions.contains("unload:melix-dev-text"))
        #expect(await runnerClient.recordedActions.contains("info:melix-dev-text"))
        #expect(await runnerClient.recordedHubSearchRequests.count == 1)
        #expect(await runnerClient.recordedHubModelCardRequests == [.init(repoID: searchModel.repoID)])
        #expect(await runnerClient.recordedModelOperationRequests.contains {
            $0.operation == "download"
                && $0.modelID == searchModel.repoID
                && $0.ext["melix.hf_token"] == "hf_secret_token"
        })

        #expect(viewModel.selectedModelInfo?.modelID == "melix-dev-text")
        #expect(viewModel.selectedModelInfo?.maxContext == 8_192)
        #expect(viewModel.modelHubSearchResults.map { $0.repoID } == [searchModel.repoID])
        #expect(viewModel.modelHubNextCursor == "cursor:page-2")
        #expect(viewModel.selectedHubModelCard?.repoID == searchModel.repoID)
        #expect(viewModel.lastModelOperation?.modelID == searchModel.repoID)
        #expect(viewModel.downloadQueue.first?.sourceModel == searchModel.repoID)
        #expect(viewModel.modelHubTokenDraft.isEmpty)
        #expect(viewModel.modelHubTokenHint.contains("hf_secret_token") == false)
    }

    @Test("server config and serving defaults use the shared operator command runner when available")
    @MainActor
    func serverConfigAndServingDefaultsUseSharedOperatorCommandRunnerWhenAvailable() async throws {
        let directClient = FakeControlPlaneXPCClient()
        let runnerClient = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-runner-server-config-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        await directClient.configureErrors(
            applyGatewayConfig: MenuBarTestError(description: "direct gateway apply should not run"),
            applyServingDefaults: MenuBarTestError(description: "direct serving defaults apply should not run")
        )

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let sharedOperatorStore = MelixOperatorSessionStore(melixHome: melixHome)
        let operatorStore = OperatorSessionStore(melixHome: melixHome)
        let runner = MelixCLIRunner(
            client: runnerClient,
            environment: ["MELIX_HOME": temporaryRoot.path],
            operatorSessionStore: sharedOperatorStore
        )
        let viewModel = RuntimeViewModel(
            client: directClient,
            metrics: metrics,
            operatorSessionStore: operatorStore,
            operatorCommandRunner: runner
        )

        await viewModel.start()
        viewModel.createServerSession()
        try await waitForRuntimeViewModelCondition("expected CLI-created server session to hydrate") {
            viewModel.serverSessions.count >= 2
        }
        let serverSessionID = try #require(viewModel.serverSessions.map(\.id).sorted().last)
        viewModel.selectServerSession(id: serverSessionID)
        try await waitForRuntimeViewModelCondition("expected CLI-created server session to become selected") {
            viewModel.selectedServerSession?.id == serverSessionID
        }
        viewModel.updateSelectedServerSessionHost("127.0.0.1")
        viewModel.updateSelectedServerSessionPort(18081)
        viewModel.updateSelectedServerSessionRateLimit(360)
        viewModel.updateSelectedServerSessionTimeout(75)
        viewModel.updateSelectedServerSessionTemperature(0.33)
        viewModel.updateSelectedServerSessionTopP(0.91)
        viewModel.updateSelectedServerSessionMaxTokens(640)
        viewModel.updateSelectedServerSessionStreamIntervalTokens(4)
        viewModel.updateSelectedServerSessionMaxConcurrentRequests(3)
        viewModel.updateSelectedServerSessionConcurrentProcessingEnabled(true)
        viewModel.updateSelectedServerSessionPrefillBatchSize(3)
        viewModel.updateSelectedServerSessionCompletionBatchSize(2)
        viewModel.updateSelectedServerSessionAccelerationMode("speculative_decode")
        viewModel.updateSelectedServerSessionDraftModelID("melix-dev-draft")
        viewModel.updateSelectedServerSessionNumDraftTokens(8)

        await viewModel.applySelectedServerGatewayConfig()
        await viewModel.applySelectedServerServingDefaults()

        #expect(await directClient.recordedGatewayConfigApplyRequests.isEmpty)
        #expect(await directClient.recordedServingDefaultsApplyRequests.isEmpty)

        let gatewayRequest = try #require(await runnerClient.recordedGatewayConfigApplyRequests.first)
        let servingRequest = try #require(await runnerClient.recordedServingDefaultsApplyRequests.first)

        #expect(gatewayRequest.serverSessionID == serverSessionID)
        #expect(gatewayRequest.host == "127.0.0.1")
        #expect(gatewayRequest.port == 18081)
        #expect(gatewayRequest.rateLimitPerMinute == 360)
        #expect(gatewayRequest.timeoutSeconds == 75)
        #expect(servingRequest.serverSessionID == serverSessionID)
        #expect(servingRequest.temperature == 0.33)
        #expect(servingRequest.topP == 0.91)
        #expect(servingRequest.maxTokens == 640)
        #expect(servingRequest.streamIntervalTokens == 4)
        #expect(servingRequest.maxConcurrentRequests == 3)
        #expect(servingRequest.concurrentProcessingEnabled == true)
        #expect(servingRequest.prefillBatchSize == 3)
        #expect(servingRequest.completionBatchSize == 2)
        #expect(servingRequest.accelerationMode == .speculativeDecode)
        #expect(servingRequest.draftModelID == "melix-dev-draft")
        #expect(servingRequest.numDraftTokens == 8)
        #expect(viewModel.selectedServerSession?.effectiveBaseURL == "http://127.0.0.1:18081/v1")
        #expect(viewModel.selectedServerSession?.servingDefaults.effectiveTemperature == 0.33)
        #expect(viewModel.selectedServerSession?.servingDefaults.effectiveTopP == 0.91)
        #expect(viewModel.selectedServerSession?.servingDefaults.effectiveMaxTokens == 640)
        #expect(await metrics.snapshot()["menu.gateway_config_apply_ms"] != nil)
        #expect(await metrics.snapshot()["menu.serving_defaults_apply_ms"] != nil)
    }

    @Test("load and unload actions dispatch through the client and refresh app state")
    @MainActor
    func loadAndUnloadDispatchThroughClient() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.loadPrimaryModel()
        #expect(await client.recordedActions == ["load:melix-dev-text"])
        #expect(viewModel.primaryModel?.stateText == "Warm")
        #expect(viewModel.primaryModel?.actionTitle == "Unload")

        await viewModel.unloadPrimaryModel()
        #expect(await client.recordedActions == ["load:melix-dev-text", "unload:melix-dev-text"])
        #expect(viewModel.primaryModel?.stateText == "Unloaded")
        #expect(viewModel.primaryModel?.actionTitle == "Load")
        #expect(await metrics.snapshot()["menu.model_load_ms"] != nil)
        #expect(await metrics.snapshot()["menu.model_unload_ms"] != nil)
    }

    @Test("model-state events update runtime state after hydration")
    @MainActor
    func modelStateEventsUpdateRuntimeState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendModelStateChanged(state: .modelPinned)

        try await Task.sleep(for: .milliseconds(20))

        #expect(viewModel.primaryModel?.stateText == "Pinned")
        #expect(viewModel.primaryModel?.actionTitle == "Unload")
    }

    @Test("start records an error state when handshake fails")
    @MainActor
    func startRecordsHandshakeFailure() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(handshake: MenuBarTestError(description: "handshake failed"))
        let viewModel = RuntimeViewModel(
            client: client,
            productInstallStateProvider: StubProductInstallStateProvider(
                updateStatusResponse: nil,
                startupDiagnosticResponse: nil
            )
        )

        await viewModel.start()

        #expect(viewModel.statusTitle == "Melix Error")
        #expect(viewModel.connectionDetailText == "Handshake failed")
        #expect(viewModel.lastError?.contains("Startup failed:") == true)
        #expect(viewModel.lastError?.contains("handshake failed") == true)
    }

    @Test("start uses packaged startup diagnostics and refreshes update status when available")
    @MainActor
    func startUsesPackagedStartupDiagnostics() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(handshake: MenuBarTestError(description: "handshake failed"))
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(
            client: client,
            metrics: metrics,
            productInstallStateProvider: StubProductInstallStateProvider(
                updateStatusResponse: ProductUpdateStatus(
                    summary: "Update available: 0.2.0",
                    detail: "Current 0.1.0 on stable",
                    isAvailable: true,
                    checkSucceeded: true
                ),
                startupDiagnosticResponse: ProductStartupFailureDiagnostic(
                    classification: "host_port_conflict",
                    userMessage: "Startup failed: port 11434 is already in use. Check /tmp/control-plane.stderr.log and restart Melix.",
                    detail: "Ready probe: http://127.0.0.1:11434/v1/models"
                )
            )
        )

        await viewModel.start()
        let foundationSettings = viewModel.desktopFoundationState.settings
        let hasUpdateRow = foundationSettings.contains { row in
            row.id == "product-update" && row.value == "Update available: 0.2.0"
        }
        let hasUpdateDetailRow = foundationSettings.contains { row in
            row.id == "product-update-detail" && row.value == "Current 0.1.0 on stable"
        }

        #expect(viewModel.productUpdateSummary == "Update available: 0.2.0")
        #expect(viewModel.productUpdateDetail == "Current 0.1.0 on stable")
        #expect(viewModel.lastError == "Startup failed: port 11434 is already in use. Check /tmp/control-plane.stderr.log and restart Melix.")
        #expect(viewModel.desktopBannerState?.title == "Operator Attention Required")
        #expect(viewModel.desktopSignalStates.contains { $0.title == "Update available: 0.2.0" && $0.isDismissible })
        #expect(hasUpdateRow)
        #expect(hasUpdateDetailRow)
        #expect(await metrics.snapshot()["update.check_success_rate"] == 100)
        #expect(await metrics.snapshot()["startup.failure_classification_count"] == 1)
    }

    @Test("update banners are dismissible and persist across restart until the version changes")
    @MainActor
    func updateBannersPersistDismissalAcrossRestart() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-update-banner-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let initialProvider = StubProductInstallStateProvider(
            updateStatusResponse: ProductUpdateStatus(
                summary: "Update available: 0.2.0",
                detail: "Current 0.1.0 on stable",
                isAvailable: true,
                checkSucceeded: true
            ),
            startupDiagnosticResponse: nil
        )
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: operatorSessionStore,
            productInstallStateProvider: initialProvider
        )

        await viewModel.start()

        let initialSignal = try #require(viewModel.desktopSignalStates.first { $0.title == "Update available: 0.2.0" })
        #expect(initialSignal.isDismissible)
        #expect(viewModel.desktopBannerState == nil)

        viewModel.dismissDesktopBanner(id: initialSignal.id)
        #expect(viewModel.desktopBannerState == nil)
        #expect(viewModel.desktopSignalStates.contains { $0.title == "Update available: 0.2.0" } == false)

        let restoredViewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            operatorSessionStore: operatorSessionStore,
            productInstallStateProvider: initialProvider
        )
        await restoredViewModel.start()
        #expect(restoredViewModel.desktopBannerState == nil)
        #expect(restoredViewModel.desktopSignalStates.contains { $0.title == "Update available: 0.2.0" } == false)

        let upgradedProvider = StubProductInstallStateProvider(
            updateStatusResponse: ProductUpdateStatus(
                summary: "Update available: 0.3.0",
                detail: "Current 0.1.0 on stable",
                isAvailable: true,
                checkSucceeded: true
            ),
            startupDiagnosticResponse: nil
        )
        let upgradedViewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            operatorSessionStore: operatorSessionStore,
            productInstallStateProvider: upgradedProvider
        )
        await upgradedViewModel.start()

        #expect(upgradedViewModel.desktopBannerState == nil)
        #expect(upgradedViewModel.desktopSignalStates.contains { $0.title == "Update available: 0.3.0" })
    }

    @Test("failed update checks stay out of the top banner")
    @MainActor
    func failedUpdateChecksStayOutOfTopBanner() async throws {
        let viewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            productInstallStateProvider: StubProductInstallStateProvider(
                updateStatusResponse: ProductUpdateStatus(
                    summary: "Update: check failed",
                    detail: "Could not read /tmp/missing-stable.json",
                    isAvailable: false,
                    checkSucceeded: false
                ),
                startupDiagnosticResponse: nil
            )
        )

        await viewModel.start()

        let signal = try #require(viewModel.desktopSignalStates.first { $0.title == "Update: check failed" })
        #expect(signal.severity == .info)
        #expect(signal.isDismissible)
        #expect(viewModel.desktopBannerState == nil)
    }

    @Test("critical runtime banners ignore dismiss requests")
    @MainActor
    func criticalRuntimeBannersIgnoreDismissRequests() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendServerStateChanged(state: .serverFailed)

        try await waitForRuntimeViewModelCondition("critical runtime banner should appear") {
            viewModel.desktopBannerState?.severity == .critical
        }

        let banner = try #require(viewModel.desktopBannerState)
        #expect(banner.isDismissible == false)
        viewModel.dismissDesktopBanner()
        #expect(viewModel.desktopBannerState?.id == banner.id)
    }

    @Test("load and unload surface client failures in app state")
    @MainActor
    func loadAndUnloadFailuresSurfaceErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(
            load: MenuBarTestError(description: "load failed"),
            unload: MenuBarTestError(description: "unload failed")
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await viewModel.loadPrimaryModel()
        #expect(viewModel.lastError?.contains("load failed") == true)

        await client.configureErrors(load: nil, unload: MenuBarTestError(description: "unload failed"))
        await viewModel.unloadPrimaryModel()
        #expect(viewModel.lastError?.contains("unload failed") == true)
    }

    @Test("load and unload no-op when there is no primary model")
    @MainActor
    func loadAndUnloadNoopWithoutPrimaryModel() async throws {
        let client = EmptySnapshotControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.loadPrimaryModel()
        await viewModel.unloadPrimaryModel()

        #expect(viewModel.primaryModel == nil)
        #expect(await client.recordedActions.isEmpty)
        #expect(await metrics.snapshot()["menu.model_load_ms"] == nil)
        #expect(await metrics.snapshot()["menu.model_unload_ms"] == nil)
    }

    @Test("snapshot server and model states map to user-facing labels")
    @MainActor
    func snapshotStatesMapToUserFacingLabels() async throws {
        let serverCases: [(Melix_Controlplane_V1_ServerState, String)] = [
            (.serverBooting, "Melix Booting"),
            (.serverDegraded, "Melix Degraded"),
            (.serverDraining, "Melix Draining"),
            (.serverStopped, "Melix Stopped"),
            (.serverFailed, "Melix Failed"),
            (.UNRECOGNIZED(-1), "Melix Unknown"),
        ]

        for (serverState, expectedTitle) in serverCases {
            let client = SnapshotControlPlaneXPCClient(
                snapshot: makeSnapshot(
                    serverState: serverState,
                    models: [makeModelSummary(state: .modelLoading)]
                )
            )
            let viewModel = RuntimeViewModel(client: client)
            await viewModel.start()

            #expect(viewModel.statusTitle == expectedTitle)
            #expect(viewModel.primaryModel?.stateText == "Loading")
            #expect(viewModel.primaryModel?.actionTitle == "Load")
        }

        let failedClient = SnapshotControlPlaneXPCClient(
            snapshot: makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(state: .modelFailed)]
            )
        )
        let failedViewModel = RuntimeViewModel(client: failedClient)
        await failedViewModel.start()
        #expect(failedViewModel.primaryModel?.stateText == "Failed")

        let evictingClient = SnapshotControlPlaneXPCClient(
            snapshot: makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(state: .modelEvicting)]
            )
        )
        let evictingViewModel = RuntimeViewModel(client: evictingClient)
        await evictingViewModel.start()
        #expect(evictingViewModel.primaryModel?.stateText == "Evicting")

        let unknownClient = SnapshotControlPlaneXPCClient(
            snapshot: makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(state: .UNRECOGNIZED(-1))]
            )
        )
        let unknownViewModel = RuntimeViewModel(client: unknownClient)
        await unknownViewModel.start()
        #expect(unknownViewModel.primaryModel?.stateText == "Unknown")
    }

    @Test("unknown model events append new models and ignore unrelated payloads")
    @MainActor
    func unknownModelEventsAppendModelsAndIgnoreOtherPayloads() async throws {
        let client = EventingSnapshotControlPlaneXPCClient(
            snapshot: makeSnapshot(serverState: .serverReady, models: [])
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendQueueSummary()
        await client.sendModelStateChanged(modelID: "secondary-model", state: .modelWarm)
        try await Task.sleep(for: .milliseconds(20))

        #expect(viewModel.models.count == 1)
        #expect(viewModel.primaryModel?.modelID == "secondary-model")
        #expect(viewModel.primaryModel?.stateText == "Warm")
        #expect(viewModel.primaryModel?.actionTitle == "Unload")
    }

    @Test("runtime model row reports loaded states for warm and pinned models")
    func runtimeModelRowReportsLoadedStates() {
        #expect(makeRuntimeModelRow(state: .modelWarm).isLoaded)
        #expect(makeRuntimeModelRow(state: .modelPinned).isLoaded)
        #expect(makeRuntimeModelRow(state: .modelDiscovered).isLoaded == false)
    }

    @Test("runtime model row surfaces eviction transition reasons for operator visibility")
    func runtimeModelRowSurfacesEvictionTransitionReasons() {
        let evicting = makeModelSummary(
            state: .modelEvicting,
            transitionReason: "ttl_expired"
        )
        let unloaded = makeModelSummary(
            state: .modelUnloaded,
            transitionReason: "lru_same_capability"
        )
        let failed = makeModelSummary(
            state: .modelFailed,
            transitionReason: "operator_unload_failed"
        )

        #expect(makeRuntimeModelRow(evicting).stateText == "Evicting • Ttl expired")
        #expect(makeRuntimeModelRow(unloaded).stateText == "Unloaded • Lru same capability")
        #expect(makeRuntimeModelRow(failed).stateText == "Failed • Operator unload failed")
    }

    @Test("runtime model row surfaces missing managed Hugging Face cache recovery state")
    func runtimeModelRowSurfacesMissingManagedHuggingFaceCacheRecoveryState() {
        var model = makeModelSummary(state: .modelDiscovered)
        model.settings.ext["melix.model_path_missing"] = "true"
        model.settings.ext["melix.model_path"] = "/tmp/hf-cache/models--mlx-community--Qwen3/snapshots/missing"
        model.settings.ext["melix.registry_descriptor_path"] = "/tmp/melix-managed/huggingface/mlx-community/Qwen3/main"
        model.settings.ext["melix.hf_repo_id"] = "mlx-community/Qwen3"
        model.settings.ext["melix.hf_revision"] = "main"

        let row = makeRuntimeModelRow(model)

        #expect(row.runtimeCacheMissing)
        #expect(row.runtimeCacheStatusText == "Missing cache")
        #expect(row.runtimeCacheDetailText == "Hugging Face cache files are missing. Re-download this model to restore it.")
        #expect(row.actionTitle == "Restore Download")
        #expect(row.runtimePathText == "/tmp/hf-cache/models--mlx-community--Qwen3/snapshots/missing")
        #expect(row.registryDescriptorPathText == "/tmp/melix-managed/huggingface/mlx-community/Qwen3/main")
        #expect(row.restoreCommandText == "melix model hub download --repo-id mlx-community/Qwen3 --revision main")
    }

    @Test("runtime model row surfaces residency memory and guard descriptors")
    func runtimeModelRowSurfacesResidencyMemoryAndGuardDescriptors() {
        let guarded = makeModelSummary(
            state: .modelFailed,
            transitionReason: "memory_budget_exceeded",
            pinRequested: true,
            pinned: false,
            ttlSeconds: 600,
            estimatedBytes: 512 * 1024 * 1024,
            inflightRequests: 3,
            memoryPolicy: .memoryResidencyPinned,
            memoryBudgetBytes: 768 * 1024 * 1024,
            memoryHeadroomBytes: 256 * 1024 * 1024,
            requiredBytes: 896 * 1024 * 1024
        )

        let row = makeRuntimeModelRow(guarded)

        #expect(row.residencyText.contains("Failed"))
        #expect(row.residencyText.contains("Pinned"))
        #expect(row.residencyText.contains("TTL 600s"))
        #expect(row.residencyText.contains("Pin requested"))
        #expect(row.memoryText.contains("estimated"))
        #expect(row.memoryText.contains("3 inflight"))
        #expect(row.memoryAlertText.contains("Memory protection"))
        #expect(row.memoryAlertText.contains("Memory budget exceeded"))
        #expect(row.memoryAlertText.contains("budget 768 MB"))
        #expect(row.memoryAlertText.contains("headroom 256 MB"))
        #expect(row.memoryAlertText.contains("required 896 MB"))
    }

    @Test("runtime model row surfaces adaptive thinking policy")
    func runtimeModelRowSurfacesAdaptiveThinkingPolicy() {
        let adaptive = makeModelSummary(
            state: .modelWarm,
            adaptiveThinkingMode: "adaptive",
            adaptiveThinkingBudgetTokens: 192
        )
        let off = makeModelSummary(
            state: .modelWarm,
            adaptiveThinkingMode: "off"
        )

        #expect(makeRuntimeModelRow(adaptive).adaptiveThinkingText == "Adaptive • 192 tok")
        #expect(makeRuntimeModelRow(off).adaptiveThinkingText == "Off")
    }

    @Test("runtime model row falls back across residency states policies and ttl descriptors")
    func runtimeModelRowFallsBackAcrossResidencyStateBranches() {
        var explicitResidency = makeModelSummary(
            state: .modelDiscovered,
            memoryPolicy: .unspecified
        )
        explicitResidency.residency.state = .loading

        let loadingFallback = makeModelSummary(
            state: .modelLoading,
            memoryPolicy: .unspecified
        )
        let evictingFallback = makeModelSummary(
            state: .modelEvicting,
            memoryPolicy: .unspecified
        )
        let unloadedFallback = makeModelSummary(
            state: .modelUnloaded,
            memoryPolicy: .unspecified
        )
        let ttlFallback = makeModelSummary(
            state: .modelDiscovered,
            ttlSeconds: 30,
            memoryPolicy: .unspecified
        )
        let unknownFallback = makeModelSummary(
            state: .UNRECOGNIZED(-1),
            memoryPolicy: .unspecified
        )

        #expect(makeRuntimeModelRow(explicitResidency).residencyText.contains("Loading"))
        #expect(makeRuntimeModelRow(loadingFallback).residencyText.contains("Loading"))
        #expect(makeRuntimeModelRow(evictingFallback).residencyText.contains("Evicting"))
        #expect(makeRuntimeModelRow(unloadedFallback).residencyText.contains("Unloaded"))
        #expect(makeRuntimeModelRow(ttlFallback).residencyText.contains("TTL 30s"))
        #expect(makeRuntimeModelRow(unknownFallback).residencyText.contains("Unknown"))
    }

    @Test("desktop foundation derives dashboard settings bench and api state from control-plane truth")
    @MainActor
    func desktopFoundationDerivesOperatorPanelsFromSnapshotTruth() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
        )
        var surface = Melix_Controlplane_V1_APIOnboardingSurfaceSummary()
        surface.surfaceID = "openai_compatible"
        surface.title = "OpenAI-Compatible"
        surface.status = .shipped
        surface.endpointIds = ["responses"]
        var endpoint = Melix_Controlplane_V1_APIReferenceEndpointSummary()
        endpoint.endpointID = "responses"
        endpoint.surfaceID = "openai_compatible"
        endpoint.method = "POST"
        endpoint.path = "/v1/responses"
        endpoint.summary = "Run Responses-style generation."
        endpoint.streaming = true
        snapshot.apiOnboarding.surfaces = [surface]
        snapshot.apiOnboarding.endpoints = [endpoint]
        var queue = Melix_Controlplane_V1_QueueSummary()
        var decode = Melix_Controlplane_V1_QueueLaneSummary()
        decode.laneID = "text.decode.interactive"
        decode.laneClass = "interactive-decode"
        decode.activeRequests = 1
        queue.lanes = [decode]
        snapshot.queues = queue
        var metrics = Melix_Controlplane_V1_MetricsSummary()
        metrics.values = ["http.translation_ms": 2.4]
        snapshot.metrics = metrics
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let foundation = viewModel.desktopFoundationState
        let hasReadyServerCard = foundation.dashboardCards.contains { $0.id == "server" && $0.value == "Ready" }
        let hasConnectedCard = foundation.dashboardCards.contains { $0.id == "connection" && $0.value == "Connected" }
        let hasDecodeLane = foundation.queueLanes.contains { $0.id == "text.decode.interactive" }
        let hasPrimaryModel = foundation.models.contains { $0.modelID == "melix-dev-text" }
        let hasProtocolSetting = foundation.settings.contains { $0.key == "Protocol" && $0.value == "melix.controlplane.v1" }
        let hasConnectionSetting = foundation.settings.contains { $0.key == "Connection" && $0.value == "Connected" }
        let hasTranslationMetric = foundation.benchMetrics.contains { $0.name == "http.translation_ms" }
        let hasResponsesEndpoint = foundation.apiReference.contains { $0.path == "/v1/responses" }
        #expect(foundation.title == "Melix Ready")
        #expect(hasReadyServerCard)
        #expect(hasConnectedCard)
        #expect(hasDecodeLane)
        #expect(hasPrimaryModel)
        #expect(hasProtocolSetting)
        #expect(hasConnectionSetting)
        #expect(hasTranslationMetric)
        #expect(hasResponsesEndpoint)
    }

    @Test("desktop foundation surfaces residency eviction and memory guard summaries")
    @MainActor
    func desktopFoundationSurfacesResidencyEvictionAndMemoryGuardSummaries() async throws {
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(
                    modelID: "melix-dev-text",
                    state: .modelPinned,
                    pinRequested: true,
                    pinned: true,
                    ttlSeconds: 900,
                    estimatedBytes: 768 * 1024 * 1024,
                    memoryPolicy: .memoryResidencyPinned
                ),
                makeModelSummary(
                    modelID: "melix-dev-evicting",
                    state: .modelEvicting,
                    transitionReason: "ttl_expired",
                    ttlSeconds: 120,
                    estimatedBytes: 256 * 1024 * 1024,
                    memoryPolicy: .memoryResidencyTtl
                ),
                makeModelSummary(
                    modelID: "melix-dev-guarded",
                    state: .modelFailed,
                    transitionReason: "prefill_memory_guard_exceeded",
                    estimatedBytes: 512 * 1024 * 1024,
                    inflightRequests: 1
                ),
            ]
        )
        snapshot.metrics.values = [
            "control_plane.model_eviction_ttl_count": 2,
            "control_plane.model_eviction_lru_same_capability_count": 1,
            "control_plane.model_eviction_last_pinned_protected_count": 1,
        ]
        snapshot.recentErrors = [
            {
                var error = Melix_Controlplane_V1_RecentError()
                error.code = "prefill_memory_guard_exceeded"
                error.message = "Prefill memory guard exceeded for melix-dev-guarded"
                return error
            }(),
        ]
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let foundation = viewModel.desktopFoundationState
        let hasResidencyCard = foundation.dashboardCards.contains { row in
            row.id == "residency" && row.value == "1 pinned"
        }
        let hasEvictionsCard = foundation.dashboardCards.contains { row in
            row.id == "evictions" && row.value == "3"
        }
        let hasGuardCard = foundation.dashboardCards.contains { row in
            row.id == "guards" && row.value == "1"
        }
        let hasGuardedModel = foundation.models.contains { row in
            row.modelID == "melix-dev-guarded" && row.memoryAlertText.contains("Memory protection")
        }
        let hasEvictingModel = foundation.models.contains { row in
            row.modelID == "melix-dev-evicting" && row.stateText == "Evicting • Ttl expired"
        }

        #expect(hasResidencyCard)
        #expect(hasEvictionsCard)
        #expect(hasGuardCard)
        #expect(hasGuardedModel)
        #expect(hasEvictingModel)
    }

    @Test("desktop foundation formats guard details from model transitions when recent errors are absent")
    @MainActor
    func desktopFoundationFormatsGuardDetailFromModelTransitionFallback() async throws {
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(
                    modelID: "melix-dev-guarded",
                    state: .modelFailed,
                    transitionReason: "quadratic_prefill_guard_exceeded",
                    estimatedBytes: 128 * 1024 * 1024
                ),
            ]
        )
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let foundation = viewModel.desktopFoundationState
        let guardCard = try #require(foundation.dashboardCards.first(where: { $0.id == "guards" }))

        #expect(guardCard.value == "1")
        #expect(guardCard.detail == "Quadratic prefill guard exceeded")
    }

    @Test("subscription termination triggers bounded reconnect and records recovery metrics")
    @MainActor
    func subscriptionTerminationTriggersReconnect() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await client.sendHeartbeat()
        await client.finishLatestSubscription()

        try await waitForRuntimeViewModelCondition("subscription termination should reconnect") {
            let foundation = viewModel.desktopFoundationState
            return foundation.settings.contains(where: { $0.key == "Connection" && $0.value == "Connected" })
                && foundation.logs.contains(where: { $0.message.contains("Reconnected event stream") })
        }

        let foundation = viewModel.desktopFoundationState
        let requests = await client.subscriptionRequests
        let hasConnectedSetting = foundation.settings.contains { $0.key == "Connection" && $0.value == "Connected" }
        let hasReconnectLog = foundation.logs.contains { $0.message.contains("Reconnected event stream") }
        #expect(requests.count == 2)
        if requests.count >= 2 {
            #expect(requests[0] == 0)
            #expect(requests[1] == 1)
        }
        #expect(hasConnectedSetting)
        #expect(hasReconnectLog)
        #expect(await metrics.snapshot()["desktop.reconnect_success_ms"] != nil)
    }

    @Test("subscription reconnect reapplies stored gateway access for the selected running server session")
    @MainActor
    func subscriptionReconnectReappliesStoredGatewayAccessForSelectedRunningServerSession() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(
            client: client,
            operatorSessionStore: NullOperatorSessionStore(),
            serverSessionAPIKeyStore: ThrowingServerSessionAPIKeyStore(
                throwOnLoad: false,
                throwOnSave: false,
                loadPrimaryKeyValue: "melix_sk_reconnect"
            )
        )

        await viewModel.start()
        var initialApplyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.count < 1, initialApplyAttempts < 200 {
            initialApplyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.count == 1)

        await client.finishLatestSubscription()

        var reconnectApplyAttempts = 0
        while await client.recordedGatewayAccessApplyRequests.count < 2, reconnectApplyAttempts < 200 {
            reconnectApplyAttempts += 1
            try await Task.sleep(for: .milliseconds(10))
        }
        #expect(await client.recordedGatewayAccessApplyRequests.count == 2)
    }

    @Test("desktop foundation refresh pulls a fresh server snapshot and records metrics")
    @MainActor
    func desktopFoundationRefreshPullsFreshSnapshotAndRecordsMetrics() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await viewModel.start()

        var refreshedSnapshot = makeSnapshot(
            serverState: .serverDegraded,
            models: [makeModelSummary(state: .modelWarm)]
        )
        refreshedSnapshot.sessions = {
            var summary = Melix_Controlplane_V1_SessionSummary()
            summary.sessionID = "session-1"
            summary.activeBranchID = "branch-main"
            summary.branchCount = 1
            return [summary]
        }()
        refreshedSnapshot.metrics.values["http.stream_first_event_ms"] = 12.5
        await client.configureSnapshot(refreshedSnapshot)

        await viewModel.refreshDesktopFoundation()

        let foundation = viewModel.desktopFoundationState
        let hasSessionsCard = foundation.dashboardCards.contains { card in
            card.id == "sessions" && card.value == "1"
        }
        let hasWarmTextModel = foundation.models.contains { model in
            model.modelID == "melix-dev-text" && model.stateText == "Warm"
        }
        #expect(viewModel.statusTitle == "Melix Degraded")
        #expect(hasSessionsCard)
        #expect(hasWarmTextModel)
        #expect(await metrics.snapshot()["menu.foundation_refresh_ms"] != nil)
        #expect(await client.recordedActions.contains("snapshot"))
    }

    @Test("desktop foundation refresh records local snapshot errors")
    @MainActor
    func desktopFoundationRefreshRecordsSnapshotErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await client.configureErrors(snapshot: MenuBarTestError(description: "snapshot failed"))

        await viewModel.refreshDesktopFoundation()

        let foundation = viewModel.desktopFoundationState
        #expect(viewModel.lastError?.contains("snapshot failed") == true)
        #expect(foundation.logs.first?.message.contains("snapshot failed") == true)
        #expect(await metrics.snapshot()["menu.foundation_refresh_ms"] == nil)
    }

    @Test("event log records streamed control-plane events for the desktop foundation")
    @MainActor
    func eventLogRecordsStreamedControlPlaneEvents() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendLog(level: "warning", message: "queue pressure rising")
        try await Task.sleep(for: .milliseconds(20))

        let foundation = viewModel.desktopFoundationState
        #expect(foundation.logs.contains(where: { $0.message == "queue pressure rising" }))
    }

    @Test("streamed control-plane events update dashboard state")
    @MainActor
    func streamedEventsUpdateDashboardState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendServerStateChanged(state: .serverDraining)
        await client.sendSessionStateChanged(sessionID: "session-42", branchCount: 2)
        await client.sendCacheStats(l1Bytes: 32 * 1024 * 1024, l2Bytes: 128 * 1024 * 1024)
        await client.sendResourcePressure(scope: "metal", usedBytes: 4 * 1024 * 1024 * 1024, totalBytes: 8 * 1024 * 1024 * 1024)
        await client.sendRequestProgress(
            requestID: "request-42",
            phase: .requestPrefilling,
            prefillProcessedTokens: 12,
            prefillTotalTokens: 24,
            activeRequests: 2,
            waitingRequests: 1,
            restoreStage: "partial",
            cachePressure: 0.25
        )
        await client.sendHeartbeat()
        await client.sendLog(level: "error", message: "thermal pressure")
        try await waitForRuntimeViewModelCondition("streamed events should update dashboard state") {
            let foundation = viewModel.desktopFoundationState
            return viewModel.lastError == "thermal pressure"
                && foundation.logs.contains(where: { $0.message == "Heartbeat" })
                && foundation.logs.contains(where: { $0.message == "thermal pressure" })
        }

        let foundation = viewModel.desktopFoundationState
        let hasSessionsCard = foundation.dashboardCards.contains { card in
            card.id == "sessions" && card.value == "1"
        }
        let hasCacheCard = foundation.dashboardCards.contains { card in
            card.id == "cache" && card.detail == "L1 / L2"
        }
        let hasMemoryCard = foundation.dashboardCards.contains { card in
            card.id == "memory" && card.detail.contains("8")
        }
        let hasSessionUpdateLog = foundation.logs.contains { $0.message == "Session session-42 updated" }
        let hasCacheLog = foundation.logs.contains { $0.message == "Cache summary updated" }
        let hasResourcePressureLog = foundation.logs.contains {
            $0.message == "Resource pressure in metal" && $0.level == "warning"
        }
        let hasPrefillLog = foundation.logs.contains {
            $0.message == "request-42 prefilling • 50% 12/24 • active 2 • waiting 1 • restore partial • pressure 0.25"
        }
        let hasHeartbeatLog = foundation.logs.contains { $0.message == "Heartbeat" }
        let hasPrefillMetric = foundation.benchMetrics.contains {
            $0.name == "scheduler.prefill_progress_pct" && $0.value == "50.00"
        }
        let hasCachePressureMetric = foundation.benchMetrics.contains {
            $0.name == "scheduler.cache_pressure" && $0.value == "0.25"
        }
        #expect(viewModel.statusTitle == "Melix Draining")
        #expect(viewModel.lastError == "thermal pressure")
        #expect(hasSessionsCard)
        #expect(hasCacheCard)
        #expect(hasMemoryCard)
        #expect(hasSessionUpdateLog)
        #expect(hasCacheLog)
        #expect(hasResourcePressureLog)
        #expect(hasPrefillLog)
        #expect(hasHeartbeatLog)
        #expect(hasPrefillMetric)
        #expect(hasCachePressureMetric)
    }

    @Test("snapshot runtime sessions project typed lifecycle and power metadata into server sessions")
    @MainActor
    func snapshotRuntimeSessionsProjectTypedLifecycleAndPowerMetadataIntoServerSessions() async throws {
        let client = FakeControlPlaneXPCClient()
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            runtimeSessions: [
                makeRuntimeSession(
                    lifecycleState: .sleeping,
                    powerState: .deepSleep,
                    wakeReason: .requestActivity,
                    idleTimerSeconds: 120,
                    autoSleepEnabled: true,
                    lightSleepAfterSeconds: 300,
                    deepSleepAfterSeconds: 900
                )
            ]
        )
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let session = try #require(viewModel.serverSessions.first)
        #expect(session.id == "server-session-1")
        #expect(session.lifecycle == .sleeping)
        #expect(session.powerState == .deepSleep)
        #expect(session.wakeReason == .requestActivity)
        #expect(session.idleTimerSeconds == 120)
        #expect(session.autoSleepEnabled)
        #expect(session.lightSleepAfterSeconds == 300)
        #expect(session.deepSleepAfterSeconds == 900)
    }

    @Test("server state changed events update runtime session lifecycle metadata")
    @MainActor
    func serverStateChangedEventsUpdateRuntimeSessionLifecycleMetadata() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        let serverSessionID = viewModel.serverSessions.first?.id ?? "server-session-1"
        await client.sendServerStateChanged(
            state: .serverReady,
            runtimeSessions: [
                makeRuntimeSession(
                    serverSessionID: serverSessionID,
                    lifecycleState: .paused,
                    powerState: .active,
                    wakeReason: .policyApply,
                    idleTimerSeconds: 42,
                    autoSleepEnabled: true,
                    lightSleepAfterSeconds: 300,
                    deepSleepAfterSeconds: 1200
                )
            ]
        )

        try await waitForRuntimeViewModelCondition("server runtime session event should project paused state") {
            viewModel.serverSessions.first?.lifecycle == .paused
                && viewModel.serverSessions.first?.wakeReason == .policyApply
        }

        let session = try #require(viewModel.serverSessions.first)
        let foundation = viewModel.desktopFoundationState
        #expect(session.lifecycle == .paused)
        #expect(session.powerState == .active)
        #expect(session.wakeReason == .policyApply)
        #expect(session.idleTimerSeconds == 42)
        #expect(session.autoSleepEnabled)
        #expect(session.deepSleepAfterSeconds == 1200)
        #expect(foundation.logs.contains(where: { $0.message.contains("Paused") && $0.message.contains("Active") }))
    }

    @Test("runtime session fallback and enum mapping cover loading stopped error and unknown states")
    @MainActor
    func runtimeSessionFallbackAndEnumMappingCoverLoadingStoppedErrorAndUnknownStates() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-runtime-session-fallback-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorSessionStore = OperatorSessionStore(melixHome: melixHome)
        let restoredServerSession = DesktopServerSessionState(
            id: "server-session-restored",
            title: "Restored Server",
            modelID: "melix-dev-text",
            lifecycle: .running
        )
        try operatorSessionStore.save(
            OperatorSessionState(
                selectedSurface: .server,
                selectedServerSessionID: restoredServerSession.id,
                serverSessions: [restoredServerSession]
            )
        )

        let client = FakeControlPlaneXPCClient()
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeModelSummary(state: .modelWarm)],
            runtimeSessions: [
                makeRuntimeSession(
                    serverSessionID: "detached-runtime-session",
                    lifecycleState: .loading,
                    powerState: .lightSleep,
                    wakeReason: .operatorResume
                )
            ]
        )
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client, operatorSessionStore: operatorSessionStore)

        await viewModel.start()

        let sessionID = try #require(viewModel.serverSessions.first?.id)
        let hydrated = try #require(viewModel.serverSessions.first)
        #expect(hydrated.lifecycle == .starting)
        #expect(hydrated.powerState == .lightSleep)
        #expect(hydrated.wakeReason == .operatorResume)

        await client.sendServerStateChanged(
            state: .serverReady,
            runtimeSessions: [
                makeRuntimeSession(
                    serverSessionID: sessionID,
                    lifecycleState: .stopped,
                    powerState: .stopped,
                    wakeReason: .toolActivity
                )
            ]
        )

        try await waitForRuntimeViewModelCondition("runtime session should project stopped/tool activity state") {
            viewModel.serverSessions.first?.lifecycle == .stopped
                && viewModel.serverSessions.first?.powerState == .stopped
                && viewModel.serverSessions.first?.wakeReason == .toolActivity
        }

        await client.sendServerStateChanged(
            state: .serverReady,
            runtimeSessions: [
                makeRuntimeSession(
                    serverSessionID: sessionID,
                    lifecycleState: .error,
                    powerState: .UNRECOGNIZED(777),
                    wakeReason: .initialBoot
                )
            ]
        )

        try await waitForRuntimeViewModelCondition("runtime session should project error and unavailable power state") {
            viewModel.serverSessions.first?.lifecycle == .error
                && viewModel.serverSessions.first?.powerState == .unavailable
                && viewModel.serverSessions.first?.wakeReason == .initialBoot
        }

        await client.sendServerStateChanged(
            state: .serverReady,
            runtimeSessions: [
                makeRuntimeSession(
                    serverSessionID: sessionID,
                    lifecycleState: .ready,
                    powerState: .active,
                    wakeReason: .UNRECOGNIZED(888)
                )
            ]
        )

        try await waitForRuntimeViewModelCondition("runtime session should project ready state and unknown wake reason fallback") {
            viewModel.serverSessions.first?.lifecycle == .running
                && viewModel.serverSessions.first?.powerState == .active
                && viewModel.serverSessions.first?.wakeReason == .unspecified
        }

        await client.sendServerStateChanged(
            state: .serverReady,
            runtimeSessions: [
                makeRuntimeSession(
                    serverSessionID: sessionID,
                    lifecycleState: .UNRECOGNIZED(999),
                    powerState: .active,
                    wakeReason: .initialBoot
                )
            ]
        )

        try await waitForRuntimeViewModelCondition("runtime session should fall back to unavailable lifecycle for unknown values") {
            viewModel.serverSessions.first?.lifecycle == .unavailable
        }
    }

    @Test("request progress events map all operator-facing phase labels")
    @MainActor
    func requestProgressEventsMapAllOperatorFacingPhaseLabels() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.sendRequestProgress(
            requestID: "request-queue",
            phase: .requestQueued,
            restoreStage: "restored"
        )
        await client.sendRequestProgress(
            requestID: "request-admitted",
            phase: .requestAdmitted
        )
        await client.sendRequestProgress(
            requestID: "request-decode",
            phase: .requestDecoding
        )
        await client.sendRequestProgress(
            requestID: "request-complete",
            phase: .requestCompleted
        )
        await client.sendRequestProgress(
            requestID: "request-abort",
            phase: .requestAborted
        )
        await client.sendRequestProgress(
            requestID: "request-fail",
            phase: .requestFailed
        )
        await client.sendRequestProgress(
            requestID: "request-reject",
            phase: .requestRejected
        )
        await client.sendRequestProgress(
            requestID: "request-unknown",
            phase: .UNRECOGNIZED(-1),
            restoreStage: "none"
        )

        try await waitForRuntimeViewModelCondition("all request progress labels should be logged") {
            let messages = viewModel.desktopFoundationState.logs.map(\.message)
            return messages.contains("request-queue queued • restore restored")
                && messages.contains("request-admitted admitted")
                && messages.contains("request-decode decoding")
                && messages.contains("request-complete completed")
                && messages.contains("request-abort aborted")
                && messages.contains("request-fail failed")
                && messages.contains("request-reject rejected")
                && messages.contains("request-unknown unknown • restore none")
        }

        let foundation = viewModel.desktopFoundationState
        let hasRestoreStageMetric = foundation.benchMetrics.contains {
            $0.name == "scheduler.restore_stage_code" && $0.value == "0.00"
        }
        #expect(hasRestoreStageMetric)
    }

    @Test("recent logs are trimmed to the last forty entries")
    @MainActor
    func recentLogsAreTrimmedToFortyEntries() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        for index in 0..<45 {
            await client.sendLog(level: "info", message: "log-\(index)")
        }
        try await Task.sleep(for: .milliseconds(30))

        let foundation = viewModel.desktopFoundationState
        #expect(foundation.logs.count == 40)
        #expect(foundation.logs.first?.message == "log-44")
        #expect(foundation.logs.contains(where: { $0.message == "log-5" }))
        #expect(foundation.logs.contains(where: { $0.message == "log-4" }) == false)
    }

    @Test("featureless model responses still hydrate model rows")
    @MainActor
    func featurelessModelResponsesStillHydrateModelRows() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.configureModelResponseFeatures([])

        await viewModel.loadModel(modelID: "melix-dev-text")

        #expect(viewModel.primaryModel?.modelID == "melix-dev-text")
        #expect(viewModel.primaryModel?.stateText == "Warm")
        #expect(viewModel.desktopFoundationState.models.contains(where: { $0.modelID == "melix-dev-text" }))
    }

    @Test("model settings dispatch through the client and hydrate typed row settings")
    @MainActor
    func modelSettingsDispatchThroughClientAndHydrateRows() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.updatePrimaryModelForLatency()

        #expect(await client.recordedActions.contains("settings:melix-dev-text"))
        #expect(viewModel.primaryModel?.memoryPolicyText == "Pinned")
        #expect(viewModel.primaryModel?.accelerationModeText == "Speculative Decode")
        #expect(viewModel.primaryModel?.accelerationProfileID == "draft-q4")
        #expect(await metrics.snapshot()["menu.model_settings_ms"] != nil)
    }

    @Test("model settings drafts apply typed controls and inspect effective defaults")
    @MainActor
    func modelSettingsDraftsApplyTypedControlsAndInspectEffectiveDefaults() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady

        var model = makeModelSummary(modelID: "melix-dev-ocr", state: .modelDiscovered)
        model.kind = "ocr"
        model.supportedModalities = ["image"]
        model.settings.ext["ocr_prompt_profile_id"] = "ocr-default-v1"
        model.settings.ext["melix.generation_config.source"] = "/tmp/melix-dev-ocr/generation_config.json"
        model.settings.ext["melix.generation_config.temperature"] = "0.12"
        model.settings.ext["melix.generation_config.top_p"] = "0.9"
        model.settings.ext["melix.generation_config.max_tokens"] = "320"
        model.settings.ext["ocr_stop_sequences"] = "<ocr:end>"
        model.cachePolicy.effectiveMode = .hybrid
        model.cachePolicy.compatibility = .cacheCompatibilityCompatible
        model.cachePolicy.compatibilityReason = "requested policy is compatible with the current worker cache capabilities"
        model.cachePolicy.effectiveDirectory = "/tmp/melix-dev-ocr/cache"
        model.cachePolicy.effectiveBlockSizeTokens = 64
        model.cachePolicy.effectiveCacheMemoryBudgetBytes = 4_096
        model.cachePolicy.effectiveMultimodalCacheBudgetBytes = 2_048
        model.cachePolicy.initialCacheBlocks = 4
        snapshot.models = [model]

        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        viewModel.modelSettingsAliasDraft = "Melix Text Turbo"
        viewModel.modelSettingsTypeOverrideDraft = "mlx-text"
        viewModel.modelSettingsTTLDraft = "600"
        viewModel.modelSettingsPinOnLoadDraft = true
        viewModel.modelSettingsMemoryPolicyDraft = "ttl"
        viewModel.modelSettingsMemoryBudgetDraft = "32768"
        viewModel.modelSettingsAccelerationModeDraft = "active_kv_quantized"
        viewModel.modelSettingsAccelerationProfileIDDraft = "kv-q8"
        viewModel.modelSettingsCacheModeDraft = "rotating"
        viewModel.modelSettingsCacheMemoryBudgetDraft = "4096"
        viewModel.modelSettingsCacheMemoryBudgetPctDraft = "25"
        viewModel.modelSettingsCacheBlockSizeTokensDraft = "64"
        viewModel.modelSettingsCacheDirectoryDraft = "/tmp/melix-dev-ocr/cache"
        viewModel.modelSettingsMultimodalCacheBudgetDraft = "2048"
        viewModel.modelSettingsAdaptiveThinkingModeDraft = "adaptive"
        viewModel.modelSettingsAdaptiveThinkingBudgetDraft = "192"
        viewModel.modelSettingsToolParserXMLFallbackDraft = true
        viewModel.modelSettingsOCRSamplingProfileDraft = "ocr-operator"
        viewModel.modelSettingsOCRTemperatureDraft = "0.05"
        viewModel.modelSettingsOCRTopPDraft = "0.82"
        viewModel.modelSettingsOCRMaxTokensDraft = "192"

        await viewModel.applyPrimaryModelSettings()
        await viewModel.inspectPrimaryModel()

        #expect(await client.recordedActions.contains("settings:melix-dev-ocr"))
        #expect(viewModel.primaryModel?.alias == "Melix Text Turbo")
        #expect(viewModel.primaryModel?.typeOverrideText == "mlx-text")
        #expect(viewModel.primaryModel?.adaptiveThinkingText == "Adaptive • 192 tok")
        #expect(viewModel.primaryModel?.toolParserFallbackText == "XML")
        #expect(viewModel.selectedModelInfo?.typeOverrideText == "mlx-text")
        #expect(viewModel.selectedModelInfo?.ttlSeconds == 600)
        #expect(viewModel.selectedModelInfo?.memoryBudgetText == "32 KB")
        #expect(viewModel.selectedModelInfo?.adaptiveThinkingText == "Adaptive • 192 tok")
        #expect(viewModel.selectedModelInfo?.toolParserFallbackText == "XML")
        #expect(viewModel.selectedModelInfo?.cacheModeText == "Hybrid")
        #expect(viewModel.selectedModelInfo?.cacheCompatibilityText == "Compatible")
        #expect(viewModel.selectedModelInfo?.cacheDirectoryText == "/tmp/melix-dev-ocr/cache")
        #expect(viewModel.selectedModelInfo?.cacheBlockSizeText == "64 tokens")
        #expect(viewModel.selectedModelInfo?.cacheBudgetText == "4 KB")
        #expect(viewModel.selectedModelInfo?.multimodalCacheBudgetText == "2 KB")
        #expect(viewModel.selectedModelInfo?.initialCacheBlocksText == "4")
        #expect(viewModel.selectedModelInfo?.ocrSamplingProfileText == "ocr-operator")
        #expect(viewModel.selectedModelInfo?.ocrTemperatureText == "0.05")
        #expect(viewModel.selectedModelInfo?.ocrTopPText == "0.82")
        #expect(viewModel.selectedModelInfo?.ocrMaxTokensText == "192")
        #expect(viewModel.selectedModelInfo?.generationConfigTemperatureText == "0.12")
    }

    @Test("model settings validation guards invalid drafts resets typed values and no-ops without a primary model")
    @MainActor
    func modelSettingsValidationGuardsInvalidDraftsResetsValuesAndNoOpsWithoutPrimaryModel() async throws {
        let idleClient = FakeControlPlaneXPCClient()
        let idleViewModel = RuntimeViewModel(client: idleClient)
        await idleViewModel.applyPrimaryModelSettings()
        #expect(await idleClient.recordedActions.isEmpty)

        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        viewModel.modelSettingsAliasDraft = "Draft Alias"
        viewModel.modelSettingsTTLDraft = "oops"
        await viewModel.applyPrimaryModelSettings()

        #expect(viewModel.lastError == "TTL seconds must be an unsigned integer.")
        #expect(await client.recordedActions.isEmpty)

        viewModel.modelSettingsTTLDraft = "120"
        viewModel.modelSettingsAdaptiveThinkingBudgetDraft = "still-bad"
        await viewModel.applyPrimaryModelSettings()

        #expect(viewModel.lastError == "Adaptive thinking budget must be an unsigned integer.")
        #expect(await client.recordedActions.isEmpty)

        viewModel.modelSettingsAdaptiveThinkingBudgetDraft = "32"
        viewModel.modelSettingsMemoryBudgetDraft = "bad-budget"
        await viewModel.applyPrimaryModelSettings()

        #expect(viewModel.lastError == "Memory budget bytes must be an unsigned integer.")
        #expect(await client.recordedActions.isEmpty)

        viewModel.modelSettingsMemoryBudgetDraft = "1024"
        viewModel.modelSettingsCacheMemoryBudgetDraft = "bad-cache-budget"
        await viewModel.applyPrimaryModelSettings()

        #expect(viewModel.lastError == "Cache memory budget bytes must be an unsigned integer.")
        #expect(await client.recordedActions.isEmpty)

        viewModel.modelSettingsCacheMemoryBudgetDraft = "4096"
        viewModel.modelSettingsCacheMemoryBudgetPctDraft = "bad-cache-pct"
        await viewModel.applyPrimaryModelSettings()

        #expect(viewModel.lastError == "Cache memory budget percent must be an unsigned integer.")
        #expect(await client.recordedActions.isEmpty)

        viewModel.modelSettingsCacheMemoryBudgetPctDraft = "25"
        viewModel.modelSettingsCacheBlockSizeTokensDraft = "bad-block"
        await viewModel.applyPrimaryModelSettings()

        #expect(viewModel.lastError == "Cache block size tokens must be an unsigned integer.")
        #expect(await client.recordedActions.isEmpty)

        viewModel.modelSettingsCacheBlockSizeTokensDraft = "64"
        viewModel.modelSettingsMultimodalCacheBudgetDraft = "bad-multimodal"
        await viewModel.applyPrimaryModelSettings()

        #expect(viewModel.lastError == "Multimodal cache budget bytes must be an unsigned integer.")
        #expect(await client.recordedActions.isEmpty)

        viewModel.modelSettingsAliasDraft = "Mutated Alias"
        viewModel.modelSettingsTypeOverrideDraft = "mlx-mutated"
        viewModel.resetPrimaryModelSettingsDrafts()

        #expect(viewModel.modelSettingsAliasDraft == viewModel.primaryModel?.alias)
        #expect(viewModel.modelSettingsTypeOverrideDraft == viewModel.primaryModel?.typeOverrideText)
    }

    @Test("model settings drafts normalize unknown residency acceleration and adaptive defaults")
    @MainActor
    func modelSettingsDraftsNormalizeUnknownResidencyAccelerationAndAdaptiveDefaults() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady

        var model = makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)
        model.settings.memoryPolicy = .UNRECOGNIZED(999)
        model.settings.defaultAccelerationMode = .UNRECOGNIZED(999)
        model.settings.adaptiveThinking.mode = ""
        snapshot.models = [model]

        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        #expect(viewModel.modelSettingsMemoryPolicyDraft == "evictable")
        #expect(viewModel.modelSettingsAccelerationModeDraft == "baseline")
        #expect(viewModel.modelSettingsAdaptiveThinkingModeDraft == "off")

        model.settings.memoryPolicy = .memoryResidencyPinned
        model.residency.policy = .memoryResidencyPinned
        model.settings.defaultAccelerationMode = .sparsePrefill
        snapshot.models = [model]
        await client.configureSnapshot(snapshot)
        await viewModel.refreshDesktopFoundation()
        viewModel.resetPrimaryModelSettingsDrafts()

        #expect(viewModel.modelSettingsMemoryPolicyDraft == "pinned")
        #expect(viewModel.modelSettingsAccelerationModeDraft == "sparse_prefill")
    }

    @Test("cache policy helpers hydrate row text info summaries and cache mode drafts")
    @MainActor
    func cachePolicyHelpersHydrateRowTextInfoSummariesAndCacheModeDrafts() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady

        var tieredModel = makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)
        tieredModel.settings.cacheMode = .tiered
        tieredModel.cachePolicy.effectiveMode = .tiered
        tieredModel.cachePolicy.compatibility = .cacheCompatibilityCompatible
        tieredModel.cachePolicy.compatibilityReason = "requested policy is compatible with the current worker cache capabilities"
        tieredModel.cachePolicy.effectiveDirectory = "/var/melix/cache"
        tieredModel.cachePolicy.effectiveCacheMemoryBudgetPct = 25
        tieredModel.cachePolicy.initialCacheBlocks = 4

        var rotatingModel = makeModelSummary(modelID: "melix-dev-rotate", state: .modelWarm)
        rotatingModel.settings.cacheMode = .rotating
        rotatingModel.cachePolicy.requestedMode = .rotating
        rotatingModel.cachePolicy.effectiveMode = .rotating
        rotatingModel.cachePolicy.compatibility = .cacheCompatibilityLimited
        rotatingModel.cachePolicy.compatibilityReason = "requested cache mode is not advertised by the worker"
        rotatingModel.cachePolicy.requestedDirectory = "/tmp/requested-cache"
        rotatingModel.cachePolicy.effectiveDirectory = "/var/melix/cache"
        rotatingModel.cachePolicy.requestedBlockSizeTokens = 32
        rotatingModel.cachePolicy.effectiveBlockSizeTokens = 64

        var hybridModel = makeModelSummary(modelID: "melix-dev-hybrid", state: .modelWarm)
        hybridModel.kind = "vlm"
        hybridModel.supportedModalities = ["text", "image"]
        hybridModel.settings.cacheMode = .hybrid
        hybridModel.cachePolicy.requestedMode = .hybrid
        hybridModel.cachePolicy.effectiveMode = .hybrid
        hybridModel.cachePolicy.compatibility = .cacheCompatibilityDisabled
        hybridModel.cachePolicy.compatibilityReason = "requested cache policy is disabled by the current worker safety profile"
        hybridModel.cachePolicy.effectiveDirectory = "/var/melix/cache-vlm"
        hybridModel.cachePolicy.requestedCacheMemoryBudgetBytes = 8_192
        hybridModel.cachePolicy.effectiveCacheMemoryBudgetBytes = 16_384
        hybridModel.cachePolicy.requestedMultimodalCacheBudgetBytes = 2_048
        hybridModel.cachePolicy.effectiveMultimodalCacheBudgetBytes = 4_096

        var unknownModel = makeModelSummary(modelID: "melix-dev-unknown", state: .modelWarm)
        unknownModel.settings.cacheMode = .unspecified
        unknownModel.cachePolicy.effectiveMode = .unspecified
        unknownModel.cachePolicy.compatibility = .cacheCompatibilityUnknown
        unknownModel.cachePolicy.compatibilityReason = "worker cache compatibility evidence is unavailable"

        snapshot.models = [tieredModel, rotatingModel, hybridModel, unknownModel]
        await client.configureSnapshot(snapshot)

        var info = Melix_Controlplane_V1_ModelInfo()
        info.ok = true
        info.modelKind = "text"
        info.maxContext = 8192
        info.supportedParsers = ["text", "json"]
        info.supportedModalities = ["text", "image"]
        await client.configureModelInfo(info)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        let rows = viewModel.desktopFoundationState.models
        #expect(rows.first(where: { $0.modelID == "melix-dev-text" })?.cachePolicyText == "Compatible • Tiered")
        #expect(rows.first(where: { $0.modelID == "melix-dev-text" })?.cacheSettingsText == "/var/melix/cache • cache 25%")
        #expect(rows.first(where: { $0.modelID == "melix-dev-rotate" })?.cachePolicyText == "Limited • Rotating")
        #expect(rows.first(where: { $0.modelID == "melix-dev-rotate" })?.cacheSettingsText == "/var/melix/cache • block 64")
        #expect(rows.first(where: { $0.modelID == "melix-dev-hybrid" })?.cachePolicyText == "Disabled • Hybrid")
        #expect(rows.first(where: { $0.modelID == "melix-dev-hybrid" })?.cacheSettingsText == "/var/melix/cache-vlm • cache 16 KB • multimodal 4 KB")
        #expect(rows.first(where: { $0.modelID == "melix-dev-unknown" })?.cachePolicyText == "Unknown • Unspecified")
        #expect(viewModel.primaryModel?.modelID == "melix-dev-hybrid")
        #expect(viewModel.modelSettingsCacheModeDraft == "hybrid")

        await viewModel.fetchModelInfo(modelID: "melix-dev-rotate")
        #expect(viewModel.selectedModelInfo?.cacheCompatibilityText == "Limited")
        #expect(viewModel.selectedModelInfo?.cacheDirectoryText == "/tmp/requested-cache -> /var/melix/cache")
        #expect(viewModel.selectedModelInfo?.cacheBlockSizeText == "32 -> 64 tokens")

        await client.configureModelInfo({
            var info = Melix_Controlplane_V1_ModelInfo()
            info.ok = true
            info.modelKind = "vlm"
            info.maxContext = 8192
            info.supportedParsers = ["text", "json"]
            info.supportedModalities = ["text", "image"]
            return info
        }())
        await viewModel.fetchModelInfo(modelID: "melix-dev-hybrid")
        #expect(viewModel.selectedModelInfo?.cacheModeText == "Hybrid")
        #expect(viewModel.selectedModelInfo?.cacheCompatibilityText == "Disabled")
        #expect(viewModel.selectedModelInfo?.cacheBudgetText == "8 KB -> 16 KB")
        #expect(viewModel.selectedModelInfo?.multimodalCacheBudgetText == "2 KB -> 4 KB")

        let rotatingClient = FakeControlPlaneXPCClient()
        var rotatingSnapshot = Melix_Controlplane_V1_ServerSnapshot()
        rotatingSnapshot.serverState = .serverReady
        var rotatingPrimary = makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)
        rotatingPrimary.settings.cacheMode = .rotating
        rotatingSnapshot.models = [rotatingPrimary]
        await rotatingClient.configureSnapshot(rotatingSnapshot)
        let rotatingViewModel = RuntimeViewModel(client: rotatingClient)
        await rotatingViewModel.start()
        #expect(rotatingViewModel.modelSettingsCacheModeDraft == "rotating")

        let hybridClient = FakeControlPlaneXPCClient()
        var hybridSnapshot = Melix_Controlplane_V1_ServerSnapshot()
        hybridSnapshot.serverState = .serverReady
        var hybridPrimary = makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)
        hybridPrimary.settings.cacheMode = .hybrid
        hybridSnapshot.models = [hybridPrimary]
        await hybridClient.configureSnapshot(hybridSnapshot)
        let hybridViewModel = RuntimeViewModel(client: hybridClient)
        await hybridViewModel.start()
        #expect(hybridViewModel.modelSettingsCacheModeDraft == "hybrid")
    }

    @Test("model loads forward configured memory budget bytes to the client")
    @MainActor
    func modelLoadsForwardConfiguredMemoryBudgetBytesToTheClient() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        var model = makeModelSummary(modelID: "melix-dev-text", state: .modelDiscovered)
        model.settings.memoryBudgetBytes = 65_536
        snapshot.models = [model]
        await client.configureSnapshot(snapshot)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.loadModel(modelID: "melix-dev-text")

        #expect(await client.lastLoadMemoryBudgetBytes == 65_536)
    }

    @Test("fake control-plane client default load helper uses a zero memory budget")
    func fakeControlPlaneClientDefaultLoadHelperUsesZeroMemoryBudget() async throws {
        let client = FakeControlPlaneXPCClient()

        _ = try await client.loadModel(modelID: "melix-dev-text")

        #expect(await client.lastLoadMemoryBudgetBytes == 0)
    }

    @Test("model info ops doctor and bench dispatch through the client and populate tool state")
    @MainActor
    func modelInfoOpsDoctorAndBenchPopulateToolState() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
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

        await viewModel.start()
        await viewModel.inspectPrimaryModel()
        await viewModel.runDoctor()
        await viewModel.runBench()
        await viewModel.quantizePrimaryModel()
        await viewModel.trainPrimaryModel()
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
        await viewModel.activateLatestAdapter()
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
        await viewModel.publishLatestAdapter()

        #expect(await client.recordedActions.contains("info:melix-dev-text"))
        #expect(await client.recordedActions.contains("doctor"))
        #expect(await client.recordedActions.contains("bench"))
        #expect(await client.recordedActions.contains("operation:quantize:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:train_lora:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:activate_adapter:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:upload:melix-dev-text"))
        #expect(await client.recordedActions.contains("operation:registry_snapshot:melix-dev-text"))
        #expect(viewModel.selectedModelInfo?.modelKind == "text")
        #expect(viewModel.selectedModelInfo?.supportedParsers == ["text", "json"])
        #expect(viewModel.lastDoctorReport?.markdown.contains("Melix Doctor") == true)
        #expect(viewModel.lastBenchReport?.reportPath.contains("bench-report") == true)
        #expect(viewModel.desktopFoundationState.benchMetrics.contains(where: { $0.name == "bench.smoke.ttft_ms" }))
        #expect(viewModel.lastModelOperation?.operation == "upload")
        #expect(viewModel.lastModelOperation?.outputPath.contains("/tmp/melix-upload-adapter") == true)
        #expect(viewModel.adapterPackages.first?.adapterName == "melix-dev-adapter")
        #expect(viewModel.adapterPackages.first?.statusText == "Published")
        #expect(viewModel.adapterPackages.first?.activationStatusText == "Activated")
        #expect(viewModel.adapterPackages.first?.derivedModelID == "melix-dev-text-lora-adapter")
        #expect(viewModel.adapterPackages.first?.responseOnlyEnabled == true)
        #expect(viewModel.adapterPackages.first?.publishedRepo == "melix/adapters/melix-dev-adapter")
        #expect(viewModel.adapterPackages.first?.checkpointCount == 2)
        #expect(viewModel.adapterPackages.first?.resumeReady == true)
        #expect(viewModel.adapterPackages.first?.tokensPerSecond == 128.5)
        #expect(viewModel.adapterPackages.first?.peakMemoryGB == 5.25)
        #expect(viewModel.trainingHistory.first?.datasetURI == "datasets/melix-dev")
        #expect(viewModel.trainingHistory.first?.checkpointCount == 2)
        #expect(viewModel.trainingHistory.first?.resumeReady == true)
        #expect(viewModel.trainingHistory.first?.tokensPerSecond == 128.5)
        #expect(viewModel.trainingHistory.first?.peakMemoryGB == 5.25)
        #expect(viewModel.loraExperimentGroups.first?.title == "nightly-qwen35")
        #expect(viewModel.loraExperimentGroups.first?.runCount == 2)
        #expect(viewModel.loraExperimentGroups.first?.latestPresetTitle == "Balanced Adapter")
        #expect(viewModel.loraExperimentGroups.first?.recommendedManifestPath == "/tmp/melix-train-lora/train_lora.adapter.json")
        #expect(await metrics.snapshot()["menu.model_info_ms"] != nil)
        #expect(await metrics.snapshot()["menu.ops_doctor_ms"] != nil)
        #expect(await metrics.snapshot()["menu.ops_bench_ms"] != nil)
        #expect(await metrics.snapshot()["menu.model_operation_ms"] != nil)
        #expect(await metrics.snapshot()["menu.model_ops_refresh_ms"] != nil)
    }

    @Test("doctor report maps typed health and findings into runtime state")
    @MainActor
    func doctorReportMapsTypedHealthAndFindingsIntoRuntimeState() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        var degraded = Melix_Controlplane_V1_DoctorFinding()
        degraded.code = "model_not_loaded"
        degraded.severity = .degraded
        degraded.summary = "Model missing from registry"
        degraded.detail = "The requested handle was not found."

        var failed = Melix_Controlplane_V1_DoctorFinding()
        failed.code = "worker_failed"
        failed.severity = .failed
        failed.summary = "Worker failed"
        failed.detail = "Worker state is failed."

        var unknown = Melix_Controlplane_V1_DoctorFinding()
        unknown.code = "cache_unavailable"
        unknown.severity = .unspecified
        unknown.summary = "Cache unavailable"
        unknown.detail = "The cache report did not contain resident bytes."

        await client.configureDoctorResponse(
            "# Melix Doctor\n\n- worker_state: warning\n",
            healthStatus: .warning,
            findings: [degraded, failed, unknown]
        )

        await viewModel.start()
        await viewModel.runDoctor()

        let report = try #require(viewModel.lastDoctorReport)
        #expect(report.healthStatusText == "Warning")
        #expect(report.findings.count == 3)
        #expect(report.findings[0].id == "model_not_loaded")
        #expect(report.findings[0].severityText == "Degraded")
        #expect(report.findings[1].severityText == "Failed")
        #expect(report.findings[2].severityText == "Unknown")
    }

    @Test("benchmark configuration dispatches explicit model suites history refresh and csv export")
    @MainActor
    func benchmarkConfigurationDispatchesExplicitModelSuitesHistoryRefreshAndCSVExport() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                    makeModelSummary(modelID: "melix-dev-text-lora", state: .modelWarm),
                ]
            )
        )
        await client.configureBenchResponse(
            ControlPlaneBenchResult(
                reportPath: "/tmp/melix/bench/runs/bench-newer/bench-report.md",
                reportMarkdown: "# Melix Bench\n\n- bench.smoke.tokens_per_second: 61.20 tok/s\n",
                metrics: [
                    "bench.smoke.ttft_ms": 21.10,
                    "bench.smoke.tokens_per_second": 61.20,
                    "bench.latency.p95_ms": 39.70,
                ]
            )
        )
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        await viewModel.start()
        viewModel.selectedBenchmarkModelID = "melix-dev-text-lora"
        viewModel.selectedBenchmarkSuiteIDs = ["smoke", "latency"]
        viewModel.benchmarkSampleSize = "6"
        viewModel.benchmarkBatchFactor = "2"

        await viewModel.runBench()
        viewModel.selectBenchmarkMetric("bench.smoke.tokens_per_second")

        let benchRequest = try #require(await client.recordedBenchRequests.last)
        #expect(benchRequest.modelID == "melix-dev-text-lora")
        #expect(Set(benchRequest.suites) == Set(["smoke", "latency"]))
        #expect(benchRequest.parameters["sample_size"] == "6")
        #expect(benchRequest.parameters["batch_factor"] == "2")
        #expect(viewModel.benchmarkHistory.count == 3)
        #expect(viewModel.selectedBenchmarkHistoryEntry?.jobID == "bench-newer")
        #expect(viewModel.benchmarkMetricCards.count == 3)
        #expect(viewModel.benchmarkMetricOptions.contains("bench.smoke.tokens_per_second"))
        #expect(viewModel.benchmarkChartPoints.count == 2)

        await viewModel.exportSelectedBenchmarkCSV()

        let exportState = try #require(viewModel.lastBenchmarkCSVExport)
        #expect(exportState.rowCount == 3)
        #expect(FileManager.default.fileExists(atPath: exportState.outputPath))
        let csv = try String(contentsOfFile: exportState.outputPath, encoding: .utf8)
        #expect(csv.contains("bench-newer"))
        #expect(await client.recordedActions.contains("bench.export"))
        #expect(await client.recordedExportOutputDirs.isEmpty == false)
        #expect(await metrics.snapshot()["menu.bench_history_refresh_ms"] != nil)
        #expect(await metrics.snapshot()["menu.bench_export_csv_ms"] != nil)
    }

    @Test("benchmark configuration forwards canonical context lengths batch sizes repeats cache reasoning and structured output controls")
    @MainActor
    func benchmarkConfigurationForwardsCanonicalControls() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                    makeModelSummary(modelID: "melix-dev-text-lora", state: .modelWarm),
                ]
            )
        )
        await client.configureBenchResponse(
            ControlPlaneBenchResult(
                reportPath: "/tmp/melix/bench/runs/bench-newer/bench-report.md",
                reportMarkdown: "# Melix Bench\n",
                metrics: ["bench.smoke.tokens_per_second": 61.20]
            )
        )
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        await viewModel.start()
        viewModel.selectedBenchmarkModelID = "melix-dev-text-lora"
        viewModel.selectedBenchmarkSuiteIDs = ["smoke"]
        viewModel.selectedBenchContextLengths = [4096, 1024, 1024]
        viewModel.selectedBenchBatchSizes = [4, 2, 4]
        viewModel.benchRepeats = "3"
        viewModel.benchCacheProfile = "partial_prefix"
        viewModel.benchReasoningMode = "enabled"
        viewModel.benchStructuredOutputMode = "json_schema"

        await viewModel.runBench()

        let request = try #require(await client.recordedBenchRequests.last)
        #expect(request.contextLengths == [1024, 4096])
        #expect(request.batchSizes == [2, 4])
        #expect(request.repeats == 3)
        #expect(request.cacheProfile == "partial_prefix")
        #expect(request.reasoningMode == "enabled")
        #expect(request.structuredOutputMode == "json_schema")
        #expect(viewModel.benchmarkHistory.count == 3)
        #expect(viewModel.benchmarkMetricCards.count == 3)
        #expect(await metrics.snapshot()["menu.ops_bench_ms"] != nil)
    }

    @Test("rich output state sanitization covers doctor bench evaluation previews and local errors")
    @MainActor
    func richOutputStateSanitizationCoversDoctorBenchEvaluationPreviewsAndLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
            )
        )
        await client.configureDoctorResponse("# <b>Doctor</b> [open](file:///tmp/melix)")
        await client.configureBenchResponse(
            ControlPlaneBenchResult(
                reportPath: "/tmp/melix/bench/runs/bench-sanitize/bench-report.md",
                reportMarkdown: "# <b>Bench</b> [click](javascript:alert(1))",
                metrics: ["<b>bench.smoke.ttft_ms</b>": 21.10]
            )
        )
        let maliciousExportBundle = makeBenchmarkExportBundleJSON()
            .replacingOccurrences(
                of: "\"input_text\": \"What is 2 + 2?\"",
                with: "\"input_text\": \"<b>What is 2 + 2?</b> [click](javascript:alert(1))\""
            )
            .replacingOccurrences(
                of: "\"extracted_result\": \"Lyon\"",
                with: "\"extracted_result\": \"<script>alert(1)</script>Lyon\""
            )
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: maliciousExportBundle)
        )

        await viewModel.start()
        await viewModel.runDoctor()
        await viewModel.runBench()
        await viewModel.runEvaluation()

        #expect(viewModel.lastDoctorReport?.markdown == "# Doctor open")
        #expect(viewModel.lastBenchReport?.markdown == "# Bench click")
        #expect(viewModel.lastBenchReport?.metrics.first?.name == "bench.smoke.ttft_ms")
        let firstPreview = try #require(viewModel.evaluationSamplePreview.first)
        #expect(firstPreview.inputText.contains("<b>") == false)
        #expect(firstPreview.inputText.contains("javascript:") == false)
        #expect(firstPreview.inputText == "What is 2 + 2? click")
        let secondPreview = try #require(viewModel.evaluationSamplePreview.last)
        #expect(secondPreview.extractedResult == "Lyon")
        #expect(secondPreview.rawResponse == "Lyon")

        await client.configureErrors(bench: MenuBarTestError(description: "<b>boom</b> [click](javascript:alert(1))"))
        await viewModel.runBench()

        #expect(viewModel.lastError == "boom click")
        #expect(viewModel.desktopFoundationState.logs.contains(where: { $0.message == "boom click" }))
    }

    @Test("benchmark selection state falls back and benchmark guard rails surface local errors")
    @MainActor
    func benchmarkSelectionStateFallsBackAndGuardRailsSurfaceLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        viewModel.selectedBenchmarkModelID = "missing-model"
        viewModel.selectedBenchmarkSuiteIDs = ["unknown-suite"]
        viewModel.selectedBenchmarkHistoryJobID = "stale-job"
        viewModel.selectedBenchmarkMetricName = "stale-metric"

        await viewModel.start()

        #expect(viewModel.selectedBenchmarkModelID == "melix-dev-text")
        #expect(viewModel.selectedBenchmarkSuiteIDs == ["smoke"])
        #expect(viewModel.selectedBenchmarkHistoryJobID.isEmpty)
        #expect(viewModel.selectedBenchmarkMetricName.isEmpty)

        viewModel.toggleBenchmarkSuite("latency")
        #expect(viewModel.selectedBenchmarkSuiteIDs.contains("latency"))
        viewModel.toggleBenchmarkSuite("latency")
        #expect(viewModel.selectedBenchmarkSuiteIDs.contains("latency") == false)

        viewModel.selectBenchmarkHistory(jobID: "bench-older")
        viewModel.selectBenchmarkMetric("bench.smoke.tokens_per_second")
        #expect(viewModel.selectedBenchmarkHistoryJobID.isEmpty)
        #expect(viewModel.selectedBenchmarkMetricName.isEmpty)

        viewModel.selectedBenchmarkSuiteIDs = []
        await viewModel.runBench()
        #expect(viewModel.lastError == "Select at least one benchmark dataset before running Benchmark.")

        let imageOnlyClient = FakeControlPlaneXPCClient()
        await imageOnlyClient.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeMenuBarImageModelSummary()]
            )
        )
        let imageOnlyViewModel = RuntimeViewModel(client: imageOnlyClient)
        await imageOnlyViewModel.start()
        imageOnlyViewModel.selectedBenchmarkSuiteIDs = ["smoke"]

        await imageOnlyViewModel.runBench()

        let imageBenchRequest = try #require(await imageOnlyClient.recordedBenchRequests.last)
        #expect(imageBenchRequest.modelID == "melix-dev-image")
        #expect(imageOnlyViewModel.lastError == nil)
    }

    @Test("benchmark and evaluation control normalization fills defaults and preserves toggle state")
    @MainActor
    func benchmarkAndEvaluationControlNormalizationFillsDefaultsAndPreservesToggleState() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                ]
            )
        )

        let viewModel = RuntimeViewModel(client: client)
        viewModel.selectedBenchContextLengths = []
        viewModel.selectedBenchBatchSizes = []
        viewModel.benchRepeats = ""
        viewModel.benchCacheProfile = ""
        viewModel.benchReasoningMode = "  enabled  "
        viewModel.benchStructuredOutputMode = " json_schema "
        viewModel.evaluationScoringMode = ""
        viewModel.evaluationCodeExecPolicy = ""

        await viewModel.start()

        #expect(viewModel.selectedBenchContextLengths == [1024, 4096])
        #expect(viewModel.selectedBenchBatchSizes == [2, 4])
        #expect(viewModel.benchRepeats == "3")
        #expect(viewModel.benchCacheProfile == "cold")
        #expect(viewModel.benchReasoningMode == "enabled")
        #expect(viewModel.benchStructuredOutputMode == "json_schema")
        #expect(viewModel.evaluationScoringMode == "multiple_choice_accuracy")
        #expect(viewModel.evaluationCodeExecPolicy == "sandboxed")

        viewModel.toggleBenchContextLength(1024)
        #expect(viewModel.selectedBenchContextLengths == [4096])
        viewModel.toggleBenchContextLength(1024)
        #expect(viewModel.selectedBenchContextLengths == [1024, 4096])

        viewModel.toggleBenchBatchSize(4)
        #expect(viewModel.selectedBenchBatchSizes == [2])
        viewModel.toggleBenchBatchSize(4)
        #expect(viewModel.selectedBenchBatchSizes == [2, 4])
    }

    @Test("benchmark direct repo mode dispatches hf repo ids and infers multimodal suite family")
    @MainActor
    func benchmarkDirectRepoModeDispatchesHFRepoIDs() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        viewModel.selectedBenchmarkTargetMode = .huggingFaceRepo
        viewModel.benchmarkHFRepoID = "unsloth/gemma-4-E4B-it-MLX-8bit"
        viewModel.selectedBenchmarkSuiteIDs = ["smoke", "latency"]

        #expect(viewModel.benchmarkTargetTaskKind == "image-text-to-text")
        #expect(viewModel.benchmarkSuites.map(\.title).contains("Docs Images VLM Smoke"))

        await viewModel.runBench()

        let request = try #require(await client.recordedBenchRequests.last)
        #expect(request.modelID.isEmpty)
        #expect(request.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(Set(request.suites) == Set(["smoke", "latency"]))
    }

    @Test("benchmark target summaries and task inference cover catalog fallback and repo families")
    @MainActor
    func benchmarkTargetSummariesAndTaskInferenceCoverFallbacksAndRepoFamilies() async throws {
        let client = FakeControlPlaneXPCClient()
        let audioOnlyModel = makeCapabilityModelSummary(
            modelID: "melix-dev-audio",
            kind: "audio",
            state: .modelWarm,
            features: ["transcribe"]
        )
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [audioOnlyModel]
            )
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        #expect(viewModel.benchmarkTargetTaskKind == "text-generation")
        #expect(viewModel.benchmarkTargetSummaryText == "Select a benchmark-capable catalog model.")

        viewModel.selectedBenchmarkTargetMode = .huggingFaceRepo
        #expect(viewModel.benchmarkTargetSummaryText == "Enter a Hugging Face repo to detect a supported benchmark task.")

        viewModel.benchmarkHFRepoID = "google/paligemma2-3b-ft-docci-448"
        #expect(viewModel.benchmarkTargetTaskKind == "image-text-to-text")
        #expect(viewModel.benchmarkTargetTaskTitle == "Image + Text to Text")

        viewModel.benchmarkHFRepoID = "mlx-community/ocr-demo"
        #expect(viewModel.benchmarkTargetTaskKind == "image-to-text")
        #expect(viewModel.benchmarkTargetTaskTitle == "Image to Text")

        viewModel.benchmarkHFRepoID = "mlx-community/sdxl-edit"
        #expect(viewModel.benchmarkTargetTaskKind == "image-text-to-image")
        #expect(viewModel.benchmarkTargetTaskTitle == "Image + Text to Image")

        viewModel.benchmarkHFRepoID = "black-forest-labs/FLUX.1-schnell"
        #expect(viewModel.benchmarkTargetTaskKind == "text-to-image")
        #expect(viewModel.benchmarkTargetTaskTitle == "Text to Image")
    }

    @Test("benchmark task inference covers catalog OCR and image model families")
    @MainActor
    func benchmarkTaskInferenceCoversCatalogOCRAndImageFamilies() async throws {
        let client = FakeControlPlaneXPCClient()
        let ocrModel = makeCapabilityModelSummary(
            modelID: "melix-dev-ocr",
            kind: "ocr",
            state: .modelWarm,
            features: ["vision", "caption"]
        )
        var imageModel = makeMenuBarImageModelSummary(modelID: "melix-dev-image")
        imageModel.settings.ext["melix.image.task_kind"] = "image-text-to-image"
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [ocrModel, imageModel]
            )
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        viewModel.selectedBenchmarkModelID = "melix-dev-ocr"
        #expect(viewModel.benchmarkTargetTaskKind == "image-to-text")
        #expect(viewModel.benchmarkTargetTaskTitle == "Image to Text")

        viewModel.selectedBenchmarkModelID = "melix-dev-image"
        #expect(viewModel.benchmarkTargetTaskKind == "image-text-to-image")
        #expect(viewModel.benchmarkTargetTaskTitle == "Image + Text to Image")
        #expect(viewModel.benchmarkTargetSummaryText.contains("melix-dev-image"))
    }

    @Test("benchmark run guard rails require an explicit catalog model or Hugging Face repo target")
    @MainActor
    func benchmarkRunGuardRailsRequireExplicitTargets() async throws {
        let client = FakeControlPlaneXPCClient()
        let audioOnlyModel = makeCapabilityModelSummary(
            modelID: "melix-dev-audio",
            kind: "audio",
            state: .modelWarm,
            features: ["transcribe"]
        )
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [audioOnlyModel]
            )
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        viewModel.selectedBenchmarkSuiteIDs = ["smoke"]
        await viewModel.runBench()
        #expect(viewModel.lastError == "Select a benchmark-capable model before running Benchmark.")

        viewModel.selectedBenchmarkTargetMode = .huggingFaceRepo
        viewModel.benchmarkHFRepoID = ""
        viewModel.selectedBenchmarkSuiteIDs = ["smoke"]
        await viewModel.runBench()
        #expect(viewModel.lastError == "Enter a Hugging Face repo before running Benchmark.")
    }

    @Test("benchmark history refresh and csv export surface export failures and empty rows")
    @MainActor
    func benchmarkHistoryRefreshAndCSVExportSurfaceFailuresAndEmptyRows() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSONWithoutResults())
        )

        await viewModel.start()
        await viewModel.refreshBenchmarkHistory()

        #expect(viewModel.benchmarkHistory.count == 1)
        #expect(viewModel.selectedBenchmarkHistoryEntry?.jobID == "bench-empty")
        #expect(viewModel.benchmarkMetricCards.isEmpty)
        #expect(viewModel.benchmarkChartPoints.isEmpty)

        await viewModel.exportSelectedBenchmarkCSV()
        #expect(viewModel.lastError == "No benchmark rows are available for CSV export.")

        await client.configureErrors(exportResults: MenuBarTestError(description: "export failed"))
        await viewModel.refreshBenchmarkHistory()

        #expect(viewModel.lastError == "export failed")
    }

    @Test("benchmark matrix configuration dispatches canonical controls history refresh and csv exports")
    @MainActor
    func benchmarkMatrixConfigurationDispatchesCanonicalControlsHistoryRefreshAndCSVExports() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                    makeModelSummary(modelID: "melix-dev-text-lora", state: .modelWarm),
                ]
            )
        )
        var matrixJob = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
        matrixJob.jobID = "matrix-newer"
        matrixJob.modelID = "melix-dev-text-lora"
        matrixJob.taskKind = "text-generation"
        matrixJob.sourceRepo = "databricks/databricks-dolly-15k"
        matrixJob.suiteIds = ["smoke", "latency"]
        matrixJob.benchmarkMode = "matrix"
        matrixJob.status = "completed"
        matrixJob.outputDir = "/tmp/melix/bench/matrix-runs/matrix-newer"
        matrixJob.createdAtUnixMs = 1_712_250_000_000
        matrixJob.updatedAtUnixMs = 1_712_250_000_500
        var smokeRow = Melix_Controlplane_V1_BenchmarkMatrixSummaryRow()
        smokeRow.jobID = "matrix-newer"
        smokeRow.taskKind = "text-generation"
        smokeRow.sourceRepo = "databricks/databricks-dolly-15k"
        smokeRow.modelID = "melix-dev-text-lora"
        smokeRow.suiteID = "smoke"
        smokeRow.contextLength = 1024
        smokeRow.generationLength = 128
        smokeRow.batchSize = 2
        smokeRow.cacheProfile = "warm"
        smokeRow.reasoningMode = "enabled"
        smokeRow.structuredOutputMode = "json_schema"
        smokeRow.concurrencyLevel = 1
        smokeRow.repeats = 4
        smokeRow.requests = 12
        smokeRow.ttftMeanMs = 21.4
        smokeRow.requestLatencyMeanMs = 29.1
        smokeRow.prefillTokensPerSecondMean = 340
        smokeRow.decodeTokensPerSecondMean = 66
        smokeRow.throughputRequestsPerSecond = 5.4
        smokeRow.throughputTokensPerSecond = 284
        smokeRow.successRate = 1
        smokeRow.peakMemoryBytesMax = 1_984_000_000
        smokeRow.queueWaitMeanMs = 1.8
        smokeRow.queueWaitP95Ms = 2.4
        smokeRow.createdAtUnixMs = 1_712_250_000_000
        var latencyRow = smokeRow
        latencyRow.suiteID = "latency"
        latencyRow.contextLength = 4096
        latencyRow.generationLength = 256
        latencyRow.batchSize = 4
        latencyRow.concurrencyLevel = 2
        latencyRow.ttftMeanMs = 31.8
        latencyRow.requestLatencyMeanMs = 44.7
        latencyRow.decodeTokensPerSecondMean = 74
        latencyRow.throughputRequestsPerSecond = 7.6
        latencyRow.throughputTokensPerSecond = 512
        await client.configureBenchMatrixResponse(
            ControlPlaneBenchMatrixResult(job: matrixJob, summaryRows: [smokeRow, latencyRow])
        )
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        await viewModel.start()
        viewModel.selectedBenchmarkPresentationMode = .matrix
        viewModel.selectedBenchmarkModelID = "melix-dev-text-lora"
        viewModel.selectedBenchmarkSuiteIDs = ["smoke", "latency"]
        viewModel.selectedBenchContextLengths = [4096, 1024, 1024]
        viewModel.selectedBenchGenerationLengths = [256, 128, 256]
        viewModel.selectedBenchBatchSizes = [4, 2, 4]
        viewModel.selectedBenchMatrixCacheProfiles = ["warm", "cold", "warm"]
        viewModel.selectedBenchMatrixReasoningModes = ["enabled", "off", "enabled"]
        viewModel.selectedBenchMatrixStructuredOutputModes = ["json_schema", "off", "json_schema"]
        viewModel.selectedBenchMatrixConcurrencyLevels = [2, 1, 2]
        viewModel.benchMatrixRepeats = "4"
        viewModel.selectedBenchmarkMatrixLoadBudgetMode = .requests
        viewModel.benchMatrixRequests = "12"

        await viewModel.runBenchMatrix()

        let matrixRequest = try #require(await client.recordedBenchMatrixRequests.last)
        #expect(matrixRequest.modelID == "melix-dev-text-lora")
        #expect(matrixRequest.hfRepoID.isEmpty)
        #expect(matrixRequest.taskKind == "text-generation")
        #expect(matrixRequest.suites == ["latency", "smoke"])
        #expect(matrixRequest.contextLengths == [1024, 4096])
        #expect(matrixRequest.generationLengths == [128, 256])
        #expect(matrixRequest.batchSizes == [2, 4])
        #expect(matrixRequest.cacheProfiles == ["cold", "warm"])
        #expect(matrixRequest.reasoningModes == ["enabled", "off"])
        #expect(matrixRequest.structuredOutputModes == ["json_schema", "off"])
        #expect(matrixRequest.concurrencyLevels == [1, 2])
        #expect(matrixRequest.repeats == 4)
        #expect(matrixRequest.requests == 12)
        #expect(matrixRequest.durationSeconds == 0)
        #expect(matrixRequest.matrixCellCount == 256)
        #expect(viewModel.benchmarkMatrixHistory.count == 2)
        #expect(viewModel.selectedBenchmarkMatrixHistoryEntry?.jobID == "matrix-newer")
        #expect(viewModel.benchmarkMatrixSummaryRows.count == 2)
        #expect(viewModel.benchmarkMatrixSummaryCards.count == 6)
        #expect(viewModel.benchmarkMatrixContextChartPoints.count == 2)
        #expect(viewModel.benchmarkMatrixThroughputChartPoints.count == 2)

        await viewModel.exportSelectedBenchmarkMatrixSummaryCSV()

        let summaryExport = try #require(viewModel.lastBenchmarkMatrixExport)
        #expect(summaryExport.formatTitle == "summary.csv")
        #expect(summaryExport.rowCount == 2)
        #expect(FileManager.default.fileExists(atPath: summaryExport.outputPath))
        let summaryCSV = try String(contentsOfFile: summaryExport.outputPath, encoding: .utf8)
        #expect(summaryCSV.contains("matrix-newer"))

        await viewModel.exportSelectedBenchmarkMatrixRequestsCSV()

        let requestsExport = try #require(viewModel.lastBenchmarkMatrixExport)
        #expect(requestsExport.formatTitle == "requests.csv")
        #expect(requestsExport.rowCount == 2)
        let requestsCSV = try String(contentsOfFile: requestsExport.outputPath, encoding: .utf8)
        #expect(requestsCSV.contains("matrix-newer"))
        #expect(await client.recordedActions.contains("bench.matrix"))
        #expect(await client.recordedActions.contains("bench.export"))
        #expect(await metrics.snapshot()["menu.ops_bench_matrix_ms"] != nil)
        #expect(await metrics.snapshot()["menu.bench_matrix_history_refresh_ms"] != nil)
        #expect(await metrics.snapshot()["menu.bench_matrix_export_summary_csv_ms"] != nil)
        #expect(await metrics.snapshot()["menu.bench_matrix_export_requests_csv_ms"] != nil)
    }

    @Test("benchmark matrix supports direct repo duration mode and local guard rails")
    @MainActor
    func benchmarkMatrixDirectRepoDurationModeAndGuardRails() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()

        viewModel.selectedBenchmarkPresentationMode = .matrix
        viewModel.selectedBenchmarkTargetMode = .huggingFaceRepo
        viewModel.benchmarkHFRepoID = "unsloth/gemma-4-E4B-it-MLX-8bit"
        viewModel.selectedBenchmarkSuiteIDs = ["smoke"]
        viewModel.selectedBenchmarkMatrixLoadBudgetMode = .durationSeconds
        viewModel.benchMatrixDurationSeconds = "60"

        await viewModel.runBenchMatrix()

        let directRepoRequest = try #require(await client.recordedBenchMatrixRequests.last)
        #expect(directRepoRequest.modelID.isEmpty)
        #expect(directRepoRequest.hfRepoID == "unsloth/gemma-4-E4B-it-MLX-8bit")
        #expect(directRepoRequest.taskKind == "image-text-to-text")
        #expect(directRepoRequest.requests == 0)
        #expect(directRepoRequest.durationSeconds == 60)

        let missingRepoClient = FakeControlPlaneXPCClient()
        let missingRepoViewModel = RuntimeViewModel(client: missingRepoClient)
        await missingRepoViewModel.start()
        missingRepoViewModel.selectedBenchmarkPresentationMode = .matrix
        missingRepoViewModel.selectedBenchmarkTargetMode = .huggingFaceRepo
        missingRepoViewModel.selectedBenchmarkSuiteIDs = ["smoke"]
        await missingRepoViewModel.runBenchMatrix()
        #expect(missingRepoViewModel.lastError == "Enter a Hugging Face repo before running Matrix.")

        let imageClient = FakeControlPlaneXPCClient()
        await imageClient.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeMenuBarImageModelSummary()]
            )
        )
        let imageViewModel = RuntimeViewModel(client: imageClient)
        await imageViewModel.start()
        imageViewModel.selectedBenchmarkPresentationMode = .matrix
        imageViewModel.selectedBenchmarkSuiteIDs = ["smoke"]
        await imageViewModel.runBenchMatrix()
        #expect(imageViewModel.lastError == "Benchmark matrix supports only text-generation, image-to-text, and image-text-to-text targets.")

        let requestsClient = FakeControlPlaneXPCClient()
        let requestsViewModel = RuntimeViewModel(client: requestsClient)
        await requestsViewModel.start()
        requestsViewModel.selectedBenchmarkPresentationMode = .matrix
        requestsViewModel.selectedBenchmarkSuiteIDs = ["smoke"]
        requestsViewModel.selectedBenchmarkMatrixLoadBudgetMode = .requests
        requestsViewModel.benchMatrixRequests = "0"
        await requestsViewModel.runBenchMatrix()
        #expect(requestsViewModel.lastError == "Set a positive requests value before running Matrix.")
    }

    @Test("benchmark matrix control normalization fills defaults and toggles preserve selections")
    @MainActor
    func benchmarkMatrixControlNormalizationFillsDefaultsAndTogglesPreserveSelections() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
            )
        )
        let viewModel = RuntimeViewModel(client: client)
        viewModel.selectedBenchGenerationLengths = []
        viewModel.selectedBenchMatrixCacheProfiles = []
        viewModel.selectedBenchMatrixReasoningModes = []
        viewModel.selectedBenchMatrixStructuredOutputModes = []
        viewModel.selectedBenchMatrixConcurrencyLevels = []
        viewModel.benchMatrixRepeats = ""
        viewModel.benchMatrixRequests = ""
        viewModel.benchMatrixDurationSeconds = ""

        await viewModel.start()

        #expect(viewModel.selectedBenchGenerationLengths == [128, 256])
        #expect(viewModel.selectedBenchMatrixCacheProfiles == ["cold"])
        #expect(viewModel.selectedBenchMatrixReasoningModes == ["off"])
        #expect(viewModel.selectedBenchMatrixStructuredOutputModes == ["off"])
        #expect(viewModel.selectedBenchMatrixConcurrencyLevels == [1, 2])
        #expect(viewModel.benchMatrixRepeats == "3")
        #expect(viewModel.benchMatrixRequests == "8")
        #expect(viewModel.benchMatrixDurationSeconds == "60")
        #expect(viewModel.benchmarkMatrixCellCount == 16)

        viewModel.toggleBenchGenerationLength(512)
        #expect(viewModel.selectedBenchGenerationLengths == [128, 256, 512])
        viewModel.toggleBenchMatrixCacheProfile("warm")
        #expect(viewModel.selectedBenchMatrixCacheProfiles == ["cold", "warm"])
        viewModel.toggleBenchMatrixReasoningMode("enabled")
        #expect(viewModel.selectedBenchMatrixReasoningModes == ["enabled", "off"])
        viewModel.toggleBenchMatrixStructuredOutputMode("json_schema")
        #expect(viewModel.selectedBenchMatrixStructuredOutputModes == ["json_schema", "off"])
        viewModel.toggleBenchMatrixConcurrencyLevel(4)
        #expect(viewModel.selectedBenchMatrixConcurrencyLevels == [1, 2, 4])
    }

    @Test("evaluation configuration dispatches explicit suites history refresh and exports")
    @MainActor
    func evaluationConfigurationDispatchesExplicitSuitesHistoryRefreshAndExports() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                    makeModelSummary(modelID: "melix-dev-text-lora", state: .modelWarm),
                ]
            )
        )
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        await viewModel.start()
        viewModel.selectedEvaluationModelID = "melix-dev-text-lora"
        viewModel.selectedEvaluationSuiteIDs = ["mmlu", "gsm8k"]
        viewModel.evaluationSampleSize = "12"
        viewModel.evaluationBatchFactor = "2"
        viewModel.evaluationFewShot = "3"
        viewModel.evaluationSeed = "7"

        await viewModel.runEvaluation()

        let evaluationRequests = await client.recordedEvaluationRequests
        #expect(evaluationRequests.count == 2)
        #expect(Set(evaluationRequests.map(\.suiteID)) == Set(["mmlu", "gsm8k"]))
        #expect(evaluationRequests.allSatisfy { $0.modelID == "melix-dev-text-lora" })
        #expect(evaluationRequests.allSatisfy { $0.sampleSize == 12 })
        #expect(evaluationRequests.allSatisfy { $0.parameters["batch_factor"] == "2" })
        #expect(evaluationRequests.allSatisfy { $0.parameters["few_shot"] == "3" })
        #expect(evaluationRequests.allSatisfy { $0.parameters["seed"] == "7" })
        #expect(viewModel.evaluationHistory.count == 1)
        #expect(viewModel.selectedEvaluationHistoryEntry?.jobID == "eval-newer")
        #expect(viewModel.evaluationMetricCards.count == 1)
        #expect(viewModel.evaluationSamplePreview.count == 2)
        let metricCard = try #require(viewModel.evaluationMetricCards.first)
        #expect(metricCard.verdictText == "improvement")
        #expect(metricCard.thresholdText == "0.1000")
        #expect(metricCard.bootstrapCIText == "[+0.1200, +0.4100]")
        #expect(metricCard.analyticalCIText == "[+0.1000, +0.3800]")
        let firstSample = try #require(viewModel.evaluationSamplePreview.first)
        #expect(firstSample.categoryLabel == "math")
        #expect(firstSample.subjectLabel == "arithmetic")

        await viewModel.exportSelectedEvaluationSummaryCSV()
        let summaryExport = try #require(viewModel.lastEvaluationExport)
        #expect(summaryExport.formatTitle == "summary.csv")
        #expect(summaryExport.rowCount == 1)
        #expect(FileManager.default.fileExists(atPath: summaryExport.outputPath))
        let summaryCSV = try String(contentsOfFile: summaryExport.outputPath, encoding: .utf8)
        #expect(summaryCSV.contains("effect_threshold,verdict,bootstrap_lower_bound,bootstrap_upper_bound,analytical_lower_bound,analytical_upper_bound"))
        #expect(summaryCSV.contains("0.1,improvement,0.12,0.41,0.1,0.38"))

        await viewModel.exportSelectedEvaluationSamplesCSV()
        let samplesCSVExport = try #require(viewModel.lastEvaluationExport)
        #expect(samplesCSVExport.formatTitle == "samples.csv")
        let samplesCSV = try String(contentsOfFile: samplesCSVExport.outputPath, encoding: .utf8)
        #expect(samplesCSV.contains("mmlu-0001"))
        #expect(samplesCSV.contains("category_label,subject_label"))
        #expect(samplesCSV.contains("math,arithmetic"))

        await viewModel.exportSelectedEvaluationSamplesJSONL()
        let samplesJSONLExport = try #require(viewModel.lastEvaluationExport)
        #expect(samplesJSONLExport.formatTitle == "samples.jsonl")
        let samplesJSONL = try String(contentsOfFile: samplesJSONLExport.outputPath, encoding: .utf8)
        #expect(samplesJSONL.contains("\"sample_id\":\"mmlu-0001\""))
        #expect(await client.recordedActions.contains("eval"))
        #expect(await client.recordedActions.contains("bench.export"))
        #expect(await metrics.snapshot()["menu.ops_eval_ms"] != nil)
        #expect(await metrics.snapshot()["menu.eval_history_refresh_ms"] != nil)
        #expect(await metrics.snapshot()["menu.eval_export_csv_ms"] != nil)
        #expect(await metrics.snapshot()["menu.eval_export_jsonl_ms"] != nil)
    }

    @Test("evaluation metric cards omit compare evidence text when summary evidence is sparse")
    @MainActor
    func evaluationMetricCardsOmitCompareEvidenceTextWhenSummaryEvidenceIsSparse() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureExportResult(
            ControlPlaneExportResult(
                exportBundleJSON: makeBenchmarkExportBundleJSONWithSparseEvaluationCompareEvidence()
            )
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        await viewModel.refreshEvaluationHistory()

        let metricCard = try #require(viewModel.evaluationMetricCards.first)

        #expect(metricCard.verdictText == "inconclusive")
        #expect(metricCard.thresholdText.isEmpty)
        #expect(metricCard.bootstrapCIText.isEmpty)
        #expect(metricCard.analyticalCIText.isEmpty)
    }

    @Test("benchmark matrix evaluation and exports use the shared operator command runner when available")
    @MainActor
    func benchmarkMatrixEvaluationAndExportsUseSharedOperatorCommandRunnerWhenAvailable() async throws {
        let directClient = FakeControlPlaneXPCClient()
        let runnerClient = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-runner-bench-eval-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        await runnerClient.configureBenchResponse(
            ControlPlaneBenchResult(
                reportPath: "/tmp/melix/bench/runs/bench-newer/bench-report.md",
                reportMarkdown: "# Melix Bench\n\n- bench.smoke.tokens_per_second: 61.20 tok/s\n",
                metrics: [
                    "bench.smoke.ttft_ms": 21.10,
                    "bench.smoke.tokens_per_second": 61.20,
                ]
            )
        )
        await runnerClient.configureBenchMatrixResponse(
            ControlPlaneBenchMatrixResult(
                job: {
                    var job = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
                    job.jobID = "matrix-newer"
                    job.modelID = "melix-dev-text-lora"
                    job.taskKind = "text-generation"
                    job.suiteIds = ["smoke"]
                    job.status = "completed"
                    job.outputDir = "/tmp/melix/bench/matrix-runs/matrix-newer"
                    return job
                }(),
                summaryRows: []
            )
        )
        await runnerClient.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        let operatorStore = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        let runner = MelixCLIRunner(
            client: runnerClient,
            environment: ["MELIX_HOME": temporaryRoot.path],
            operatorSessionStore: operatorStore
        )
        let viewModel = RuntimeViewModel(
            client: directClient,
            metrics: metrics,
            operatorCommandRunner: runner
        )

        await viewModel.start()
        viewModel.selectedBenchmarkModelID = "melix-dev-text-lora"
        viewModel.selectedBenchmarkSuiteIDs = ["smoke"]
        viewModel.selectedEvaluationModelID = "melix-dev-text-lora"
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]

        await viewModel.runBench()
        await viewModel.exportSelectedBenchmarkCSV()
        await viewModel.runBenchMatrix()
        await viewModel.exportSelectedBenchmarkMatrixSummaryCSV()
        await viewModel.runEvaluation()
        await viewModel.exportSelectedEvaluationSummaryCSV()
        await viewModel.exportSelectedEvaluationSamplesJSONL()

        #expect(await directClient.recordedBenchRequests.isEmpty)
        #expect(await directClient.recordedBenchMatrixRequests.isEmpty)
        #expect(await directClient.recordedEvaluationRequests.isEmpty)
        #expect(await directClient.recordedExportOutputDirs.isEmpty)

        #expect(await runnerClient.recordedBenchRequests.isEmpty == false)
        #expect(await runnerClient.recordedBenchMatrixRequests.isEmpty == false)
        #expect(await runnerClient.recordedEvaluationRequests.isEmpty == false)
        #expect(await runnerClient.recordedExportOutputDirs.isEmpty == false)
        #expect(viewModel.lastBenchmarkCSVExport != nil)
        #expect(viewModel.lastBenchmarkMatrixExport != nil)
        #expect(viewModel.lastEvaluationExport != nil)
    }

    @Test("phase8 write workflows use cli workflow json receipts when configured")
    @MainActor
    func phase8WriteWorkflowsUseCLIWorkflowJSONReceiptsWhenConfigured() async throws {
        let directClient = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-cli-workflows-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorStore = OperatorSessionStore(melixHome: melixHome)
        let initialServerSession = DesktopServerSessionState(
            id: "server-session-1",
            title: "Primary Server",
            modelID: "melix-dev-text",
            host: "127.0.0.1",
            port: 18_080
        )
        try operatorStore.save(
            OperatorSessionState(
                selectedSurface: .server,
                selectedServerSessionID: initialServerSession.id,
                serverSessions: [initialServerSession]
            )
        )

        await directClient.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                    makeModelSummary(modelID: "melix-dev-text-lora", state: .modelWarm),
                ]
            )
        )
        await directClient.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await workflowRunner.configureHandler { command in
            func sessionJSON(modelID: String) -> String {
                """
                {
                  "selected_surface": "server",
                  "selected_tool_section": "models_library",
                  "selected_server_session_id": "server-session-1",
                  "dismissed_banner_ids": [],
                  "download_queue": [],
                  "registry_roots": [],
                  "server_sessions": [
                    {
                      "id": "server-session-1",
                      "title": "Primary Server",
                      "model_id": "\(modelID)",
                      "host": "127.0.0.1",
                      "port": 18080,
                      "rate_limit_per_minute": 120,
                      "timeout_seconds": 120,
                      "lifecycle": "draft",
                      "updated_at": "2026-04-09T16:30:00Z"
                    }
                  ]
                }
                """
            }

            switch command {
            case .modelHubDownload(let options):
                return .success(
                    makeManagedModelReceiptJSON(
                        modelID: options.repoID,
                        managedModelPath: "/tmp/melix-managed/\(options.repoID)",
                        sourceKind: "hub_repo",
                        sourceLocator: options.repoID
                    )
                )
            case .modelRootsRescan:
                return .success("{\"operation\":\"registry_snapshot\"}\n")
            case .serverSessionUpdate(let options):
                return .success(sessionJSON(modelID: options.modelID.isEmpty ? "melix-dev-text" : options.modelID))
            case .serverSessionSelect:
                return .success(sessionJSON(modelID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"))
            case .serverStart(let options):
                return .success(makeCLIServerSnapshotJSON(serverSessionID: options.serverSessionID))
            case .loraTrain:
                return .success(
                    """
                    {
                      "operation": "train_lora",
                      "job_id": "model-ops-0001",
                      "source_model": "melix-dev-text",
                      "output_path": "/tmp/melix-train-lora/train_lora.adapter.json",
                      "adapter_name": "phase8-acceptance",
                      "dataset_uri": "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1"
                    }
                    """
                )
            case .loraActivate:
                return .success(
                    """
                    {
                      "activation_mode": "fused_derived_model",
                      "source_model": "melix-dev-text",
                      "adapter_name": "phase8-acceptance",
                      "derived_model_id": "melix-dev-text-lora",
                      "derived_model_path": "/tmp/melix-derived/model"
                    }
                    """
                )
            case .benchRun:
                return .success(makeCLIBenchRunJSON())
            case .benchMatrixRun:
                return .success(makeCLIBenchmarkMatrixRunJSON())
            case .evalRun:
                return .success(makeCLIEvaluationRunJSON())
            case .benchExportCSV(let options):
                return .success(
                    makeCLIExportResponseJSON(jobID: options.jobID, outputPath: options.outputPath, rowCount: 2)
                )
            case .benchMatrixExportSummaryCSV(let options):
                return .success(
                    makeCLIExportResponseJSON(jobID: options.jobID, outputPath: options.outputPath, rowCount: 1)
                )
            case .evalExportSummaryCSV(let options):
                return .success(
                    makeCLIExportResponseJSON(jobID: options.jobID, outputPath: options.outputPath, rowCount: 1)
                )
            case .evalExportSamplesJSONL(let options):
                return .success(
                    makeCLIExportResponseJSON(jobID: options.jobID, outputPath: options.outputPath, rowCount: 2)
                )
            default:
                return .success("{}\n")
            }
        }

        let viewModel = RuntimeViewModel(
            client: directClient,
            metrics: metrics,
            operatorSessionStore: operatorStore,
            cliWorkflowRunner: workflowRunner
        )

        await viewModel.start()
        viewModel.modelHubSelectedRevision = "main"
        viewModel.selectedLoraModelID = "melix-dev-text"
        viewModel.loraDatasetSourceKind = .localPackage
        viewModel.loraDatasetURI = "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1"
        viewModel.loraAdapterName = "phase8-acceptance"
        viewModel.loraDerivedModelAlias = "melix-dev-text-lora"
        viewModel.selectedBenchmarkModelID = "melix-dev-text-lora"
        viewModel.selectedBenchmarkSuiteIDs = ["smoke"]
        viewModel.selectedEvaluationModelID = "melix-dev-text-lora"
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]

        await viewModel.downloadHubModel(repoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        viewModel.updateSelectedServerSessionModelID("mlx-community/Qwen3.5-0.8B-OptiQ-4bit")
        await viewModel.startSelectedServerSession()
        await viewModel.trainPrimaryModel()
        await viewModel.activateLatestAdapter()
        await viewModel.runBench()
        await viewModel.exportSelectedBenchmarkCSV()
        await viewModel.runBenchMatrix()
        await viewModel.exportSelectedBenchmarkMatrixSummaryCSV()
        await viewModel.runEvaluation()
        await viewModel.exportSelectedEvaluationSummaryCSV()
        await viewModel.exportSelectedEvaluationSamplesJSONL()

        let recordedCommands = await workflowRunner.snapshotRecordedCommands()

        #expect(recordedCommands.contains {
            if case .modelHubDownload = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .serverSessionUpdate = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .serverSessionSelect = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .serverStart = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .loraTrain = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .loraActivate = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .benchRun = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .benchMatrixRun = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .evalRun = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .benchExportCSV = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .benchMatrixExportSummaryCSV = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .evalExportSummaryCSV = $0 { return true }
            return false
        })
        #expect(recordedCommands.contains {
            if case .evalExportSamplesJSONL = $0 { return true }
            return false
        })

        let directOperations = await directClient.recordedModelOperationRequests
        #expect(directOperations.contains { $0.operation == "download" } == false)
        #expect(directOperations.contains { $0.operation == "train_lora" } == false)
        #expect(directOperations.contains { $0.operation == "activate_adapter" } == false)
        #expect(await directClient.recordedBenchRequests.isEmpty)
        #expect(await directClient.recordedBenchMatrixRequests.isEmpty)
        #expect(await directClient.recordedEvaluationRequests.isEmpty)

        #expect(viewModel.lastModelOperation?.modelID == "melix-dev-text")
        #expect(viewModel.selectedServerSession?.lifecycle == .running)
        #expect(viewModel.lastBenchReport?.reportPath.contains("bench-report") == true)
        #expect(viewModel.selectedBenchmarkMatrixHistoryEntry?.jobID == "matrix-newer")
        #expect(viewModel.selectedEvaluationHistoryEntry?.jobID == "eval-newer")
        #expect(viewModel.lastBenchmarkCSVExport != nil)
        #expect(viewModel.lastBenchmarkMatrixExport?.formatTitle == "summary.csv")
        #expect(viewModel.lastEvaluationExport?.formatTitle == "samples.jsonl")
        #expect(await metrics.snapshot()["menu.ops_bench_ms"] != nil)
        #expect(await metrics.snapshot()["menu.ops_bench_matrix_ms"] != nil)
        #expect(await metrics.snapshot()["menu.ops_eval_ms"] != nil)
    }

    @Test("cli server start forwards draft serving defaults through session update")
    @MainActor
    func cliServerStartForwardsDraftServingDefaultsThroughSessionUpdate() async throws {
        let directClient = FakeControlPlaneXPCClient()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-cli-start-draft-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let operatorStore = OperatorSessionStore(melixHome: melixHome)
        let initialServerSession = DesktopServerSessionState(
            id: "server-session-1",
            title: "Qwen DFlash",
            modelID: "mlx-community/Qwen3.5-27B-4bit",
            host: "127.0.0.1",
            port: 18_080
        )
        try operatorStore.save(
            OperatorSessionState(
                selectedSurface: .server,
                selectedServerSessionID: initialServerSession.id,
                serverSessions: [initialServerSession]
            )
        )
        await directClient.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "mlx-community/Qwen3.5-27B-4bit", state: .modelWarm),
                ]
            )
        )

        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await workflowRunner.configureHandler { command in
            switch command {
            case .serverStart(let options):
                return .success(makeCLIServerSnapshotJSON(serverSessionID: options.serverSessionID))
            default:
                return .success("{}\n")
            }
        }
        let viewModel = RuntimeViewModel(
            client: directClient,
            operatorSessionStore: operatorStore,
            cliWorkflowRunner: workflowRunner
        )

        await viewModel.start()
        viewModel.updateSelectedServerSessionAccelerationMode("speculative_decode")
        viewModel.updateSelectedServerSessionDraftModelID("z-lab/Qwen3.5-27B-DFlash")
        viewModel.updateSelectedServerSessionNumDraftTokens(4)

        await viewModel.startSelectedServerSession()

        let recordedCommands = await workflowRunner.snapshotRecordedCommands()
        let updateCommand = try #require(recordedCommands.compactMap { command in
            if case .serverSessionUpdate(let options) = command {
                return options
            }
            return nil
        }.first)
        #expect(updateCommand.serverSessionID == "server-session-1")
        #expect(updateCommand.accelerationMode == "speculative_decode")
        #expect(updateCommand.draftModelID == "z-lab/Qwen3.5-27B-DFlash")
        #expect(updateCommand.numDraftTokens == 4)
    }

    @Test("cli workflow failures surface typed failure state into the runtime view model")
    @MainActor
    func cliWorkflowFailuresSurfaceTypedFailureStateIntoTheRuntimeViewModel() async throws {
        let directClient = FakeControlPlaneXPCClient()
        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await directClient.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(modelID: "melix-dev-text-lora", state: .modelWarm)]
            )
        )
        await workflowRunner.configureHandler { command in
            switch command {
            case .benchRun:
                return Result<String, MelixCLIWorkflowError>.failure(
                    MelixCLIWorkflowError.invalidJSON(
                        commandID: "bench.run",
                        surface: MelixCLIWorkflowSurface.subprocess,
                        output: "{"
                    )
                )
            default:
                return .success("{}\n")
            }
        }

        let viewModel = RuntimeViewModel(
            client: directClient,
            cliWorkflowRunner: workflowRunner
        )

        await viewModel.start()
        viewModel.selectedBenchmarkModelID = "melix-dev-text-lora"
        viewModel.selectedBenchmarkSuiteIDs = ["smoke"]

        await viewModel.runBench()

        let failure = try #require(viewModel.lastCLIWorkflowFailure)
        #expect(failure.commandID == "bench.run")
        #expect(failure.failureKind == .invalidJSON)
        #expect(failure.surface == .subprocess)
        #expect(viewModel.lastError?.contains("bench.run") == true)
        #expect(await directClient.recordedBenchRequests.isEmpty)
    }

    @Test("recording cli workflow runner supports configured outputs and failures")
    func recordingCLIWorkflowRunnerSupportsConfiguredOutputsAndFailures() async throws {
        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        let benchCommand = MelixCLICommand.benchRun(.init(modelID: "melix-dev-text", suites: ["smoke"], json: true))
        let exportCommand = MelixCLICommand.benchExportCSV(
            .init(jobID: "bench-newer", outputPath: "/tmp/bench-newer.csv", json: true)
        )

        await workflowRunner.configureOutput("{\"ok\":true}\n", for: benchCommand)
        await workflowRunner.configureFailure(
            .processFailed(
                commandID: "bench.export_csv",
                surface: .subprocess,
                exitCode: 2,
                stderr: "export failed"
            ),
            for: exportCommand
        )

        let output = try await workflowRunner.run(benchCommand)
        #expect(output.contains("\"ok\":true"))

        do {
            _ = try await workflowRunner.run(exportCommand)
            Issue.record("Expected configured CLI workflow failure.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error.failureKind == .processFailed)
        }
    }

    @Test("cli create and select server session failures surface local error state")
    @MainActor
    func cliCreateAndSelectServerSessionFailuresSurfaceLocalErrorState() async throws {
        let directClient = FakeControlPlaneXPCClient()
        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await directClient.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
            )
        )
        await workflowRunner.configureHandler { command in
            switch command {
            case .serverSessionCreate:
                return .failure(
                    .processFailed(
                        commandID: "server.session.create",
                        surface: .subprocess,
                        exitCode: 3,
                        stderr: "create failed"
                    )
                )
            case .serverSessionSelect:
                return .failure(
                    .processFailed(
                        commandID: "server.session.select",
                        surface: .subprocess,
                        exitCode: 4,
                        stderr: "select failed"
                    )
                )
            default:
                return .success("{}\n")
            }
        }

        let viewModel = RuntimeViewModel(client: directClient, cliWorkflowRunner: workflowRunner)
        await viewModel.start()

        viewModel.createServerSession()
        try await waitForRuntimeViewModelCondition("expected create session CLI failure") {
            viewModel.lastCLIWorkflowFailure?.commandID == "server.session.create"
        }
        #expect(viewModel.lastError?.contains("server.session.create") == true)

        let selectedServerSessionID = try #require(viewModel.selectedServerSession?.id)
        viewModel.selectServerSession(id: selectedServerSessionID)
        try await waitForRuntimeViewModelCondition("expected select session CLI failure") {
            viewModel.lastCLIWorkflowFailure?.commandID == "server.session.select"
        }
        #expect(viewModel.lastError?.contains("server.session.select") == true)
    }

    @Test("cli download and train failures surface typed local errors")
    @MainActor
    func cliDownloadAndTrainFailuresSurfaceTypedLocalErrors() async throws {
        let directClient = FakeControlPlaneXPCClient()
        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await directClient.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
            )
        )

        let viewModel = RuntimeViewModel(client: directClient, cliWorkflowRunner: workflowRunner)
        await viewModel.start()
        viewModel.modelHubSelectedRevision = "main"

        await workflowRunner.configureHandler { command in
            switch command {
            case .modelHubDownload:
                return .failure(
                    .invalidJSON(
                        commandID: "model.hub.download",
                        surface: .subprocess,
                        output: "{"
                    )
                )
            default:
                return .success("{}\n")
            }
        }

        await viewModel.downloadHubModel(repoID: "mlx-community/Qwen3.5-0.8B-OptiQ-4bit")

        let downloadFailure = try #require(viewModel.lastCLIWorkflowFailure)
        #expect(downloadFailure.commandID == "model.hub.download")
        #expect(downloadFailure.failureKind == .invalidJSON)
        #expect(viewModel.lastError?.contains("model.hub.download") == true)

        viewModel.selectedLoraModelID = "melix-dev-text"
        viewModel.loraDatasetSourceKind = .localPackage
        viewModel.loraDatasetURI = "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1"
        viewModel.loraAdapterName = "phase8-acceptance"

        await workflowRunner.configureHandler { command in
            switch command {
            case .loraTrain:
                return .failure(
                    .processFailed(
                        commandID: "lora.train",
                        surface: .subprocess,
                        exitCode: 5,
                        stderr: "training failed"
                    )
                )
            default:
                return .success("{}\n")
            }
        }

        await viewModel.trainPrimaryModel()

        let trainingFailure = try #require(viewModel.lastCLIWorkflowFailure)
        #expect(trainingFailure.commandID == "lora.train")
        #expect(trainingFailure.failureKind == .processFailed)
        #expect(viewModel.lastError?.contains("lora.train") == true)
    }

    @Test("cli activate failure reuses the latest trained adapter path and surfaces a typed local error")
    @MainActor
    func cliActivateFailureReusesTheLatestTrainedAdapterPathAndSurfacesATypedLocalError() async throws {
        let directClient = FakeControlPlaneXPCClient()
        let workflowRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await directClient.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
            )
        )
        await workflowRunner.configureHandler { command in
            switch command {
            case .loraTrain:
                return .success(
                    """
                    {
                      "operation": "train_lora",
                      "job_id": "model-ops-activate-fallback",
                      "source_model": "melix-dev-text",
                      "output_path": "/tmp/melix-train-lora/train_lora.adapter.json",
                      "adapter_name": "phase8-acceptance",
                      "dataset_uri": "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1"
                    }
                    """
                )
            case .loraActivate:
                return .failure(
                    .processFailed(
                        commandID: "lora.activate",
                        surface: .subprocess,
                        exitCode: 6,
                        stderr: "activation failed"
                    )
                )
            default:
                return .success("{}\n")
            }
        }

        let viewModel = RuntimeViewModel(client: directClient, cliWorkflowRunner: workflowRunner)
        await viewModel.start()
        viewModel.selectedLoraModelID = "melix-dev-text"
        viewModel.loraDatasetSourceKind = .localPackage
        viewModel.loraDatasetURI = "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1"
        viewModel.loraAdapterName = "phase8-acceptance"
        viewModel.loraDerivedModelAlias = "melix-dev-text-lora"

        await viewModel.trainPrimaryModel()
        await viewModel.activateLatestAdapter()

        let failure = try #require(viewModel.lastCLIWorkflowFailure)
        #expect(failure.commandID == "lora.activate")
        #expect(failure.failureKind == .processFailed)
        #expect(viewModel.lastError?.contains("lora.activate") == true)

        let recordedCommands = await workflowRunner.snapshotRecordedCommands()
        #expect(recordedCommands.contains {
            if case .loraActivate(let options) = $0 {
                return options.adapterPath == "/tmp/melix-train-lora/train_lora.adapter.json"
            }
            return false
        })
    }

    @Test("evaluation configuration forwards few shot seed scoring mode and code execution policy controls")
    @MainActor
    func evaluationConfigurationForwardsCanonicalControls() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                    makeModelSummary(modelID: "melix-dev-text-lora", state: .modelWarm),
                ]
            )
        )
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        await viewModel.start()
        viewModel.selectedEvaluationModelID = "melix-dev-text-lora"
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        viewModel.evaluationSampleSize = "12"
        viewModel.evaluationBatchFactor = "2"
        viewModel.evaluationFewShot = "4"
        viewModel.evaluationSeed = "9"
        viewModel.evaluationScoringMode = "multiple_choice_accuracy"
        viewModel.evaluationCodeExecPolicy = "sandboxed"

        await viewModel.runEvaluation()

        let request = try #require(await client.recordedEvaluationRequests.last)
        #expect(request.parameters["few_shot"] == "4")
        #expect(request.parameters["seed"] == "9")
        #expect(request.parameters["scoring_mode"] == "multiple_choice_accuracy")
        #expect(request.parameters["code_exec_policy"] == "sandboxed")
        #expect(viewModel.evaluationHistory.count == 1)
        #expect(viewModel.evaluationMetricCards.count == 1)
        #expect(await metrics.snapshot()["menu.ops_eval_ms"] != nil)
    }

    @Test("evaluation semantic judge selection forwards remote server parameters")
    @MainActor
    func evaluationSemanticJudgeSelectionForwardsRemoteServerParameters() async throws {
        let client = FakeControlPlaneXPCClient()
        let remoteStore = FakeRemoteServerStore(
            servers: [
                RemoteServer(
                    id: "judge",
                    title: "Judge",
                    providerPreset: .custom,
                    providerKind: "openai-compatible",
                    baseURL: "https://judge.example/v1",
                    defaultModelID: "judge-default",
                    timeoutSeconds: 41,
                    rateLimitPerMinute: 12,
                    credentialRef: RemoteServerStore.credentialRef(for: "judge"),
                    apiKeyHint: "sk-j...udge"
                ),
            ],
            apiKeys: ["judge": "sk-judge"]
        )
        let viewModel = RuntimeViewModel(
            client: client,
            remoteServerStore: remoteStore
        )
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
            )
        )

        await viewModel.start()
        viewModel.selectedEvaluationModelID = "melix-dev-text"
        viewModel.selectedEvaluationSuiteIDs = ["event_extraction"]
        viewModel.evaluationDatasetSourceKind = .localJSONL
        viewModel.evaluationSourcePath = "/Users/ChenYu/Downloads/top200_final.jsonl"
        viewModel.evaluationFieldInputTextPath = "dialogue"
        viewModel.evaluationFieldTargetPath = "events"
        viewModel.evaluationScoringMode = "event_extraction_weighted_f1"
        viewModel.selectedEvaluationSemanticJudgeRemoteServerID = "judge"
        viewModel.evaluationSemanticJudgeModelID = "judge-model"

        await viewModel.runEvaluation()

        let request = try #require(await client.recordedEvaluationRequests.last)
        #expect(request.parameters["semantic_judge_remote_server_id"] == "judge")
        #expect(request.parameters["semantic_judge_provider_kind"] == "openai-compatible")
        #expect(request.parameters["semantic_judge_base_url"] == "https://judge.example/v1")
        #expect(request.parameters["semantic_judge_api_key"] == "sk-judge")
        #expect(request.parameters["semantic_judge_model_id"] == "judge-model")
        #expect(request.parameters["semantic_judge_timeout_seconds"] == "41")
        #expect(request.parameters["semantic_judge_rate_limit_per_minute"] == "12")
    }

    @Test("evaluation semantic judge selection validates stale servers credentials and model")
    @MainActor
    func evaluationSemanticJudgeSelectionValidatesStaleServersCredentialsAndModel() async throws {
        let client = FakeControlPlaneXPCClient()
        let judgeServer = RemoteServer(
            id: "judge",
            title: "Judge",
            providerPreset: .custom,
            providerKind: "openai-compatible",
            baseURL: "https://judge.example/v1",
            defaultModelID: "judge-default",
            timeoutSeconds: 41,
            rateLimitPerMinute: 12,
            credentialRef: RemoteServerStore.credentialRef(for: "judge"),
            apiKeyHint: "sk-j...udge"
        )
        let remoteStore = FakeRemoteServerStore(
            servers: [judgeServer],
            apiKeys: ["judge": "sk-judge"]
        )
        let viewModel = RuntimeViewModel(
            client: client,
            remoteServerStore: remoteStore
        )
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)]
            )
        )
        await viewModel.start()
        viewModel.selectedEvaluationModelID = "melix-dev-text"
        viewModel.selectedEvaluationSuiteIDs = ["event_extraction"]
        viewModel.evaluationDatasetSourceKind = .localJSONL
        viewModel.evaluationSourcePath = "/Users/ChenYu/Downloads/top200_final.jsonl"
        viewModel.evaluationFieldInputTextPath = "dialogue"
        viewModel.evaluationFieldTargetPath = "events"
        viewModel.evaluationScoringMode = "event_extraction_weighted_f1"
        viewModel.selectedEvaluationSemanticJudgeRemoteServerID = "judge"
        viewModel.evaluationSemanticJudgeModelID = "judge-model"

        remoteStore.servers = []
        viewModel.reloadRemoteServers()
        #expect(viewModel.selectedEvaluationSemanticJudgeRemoteServerID == "")
        #expect(viewModel.evaluationSemanticJudgeModelID == "")

        remoteStore.servers = [judgeServer]
        viewModel.reloadRemoteServers()
        viewModel.selectedEvaluationSemanticJudgeRemoteServerID = "judge"
        viewModel.evaluationSemanticJudgeModelID = "judge-model"
        viewModel.selectedEvaluationMode = .compare
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        viewModel.evaluationScoringMode = "multiple_choice_accuracy"
        viewModel.selectedEvaluationCompareTargetModelIDs = ["melix-dev-text"]
        await viewModel.runEvaluation()
        #expect(viewModel.lastError == "Semantic judge scoring is available for standard Evaluation runs.")

        viewModel.selectedEvaluationMode = .standard
        await viewModel.runEvaluation()
        #expect(viewModel.lastError == "Semantic judge scoring requires selecting only the Event Extraction suite.")

        viewModel.selectedEvaluationSuiteIDs = ["event_extraction"]
        viewModel.evaluationScoringMode = "event_extraction_weighted_f1"
        viewModel.selectedEvaluationSemanticJudgeRemoteServerID = "missing"
        await viewModel.runEvaluation()
        #expect(viewModel.lastError?.contains("Remote server missing was not found.") == true)

        viewModel.selectedEvaluationSemanticJudgeRemoteServerID = "judge"
        remoteStore.apiKeys.removeValue(forKey: "judge")
        await viewModel.runEvaluation()
        #expect(viewModel.lastError?.contains("Remote server judge has no API key configured.") == true)

        remoteStore.apiKeys["judge"] = "sk-judge"
        remoteStore.servers = [
            RemoteServer(
                id: "judge",
                title: "Judge",
                providerPreset: .custom,
                providerKind: "openai-compatible",
                baseURL: "https://judge.example/v1",
                defaultModelID: "",
                timeoutSeconds: 41,
                rateLimitPerMinute: 12,
                credentialRef: RemoteServerStore.credentialRef(for: "judge"),
                apiKeyHint: "sk-j...udge"
            ),
        ]
        viewModel.reloadRemoteServers()
        viewModel.selectedEvaluationSemanticJudgeRemoteServerID = "judge"
        viewModel.evaluationSemanticJudgeModelID = " "
        await viewModel.runEvaluation()
        #expect(viewModel.lastError?.contains("Remote server judge has no model configured.") == true)
    }

    @Test("evaluation configuration forwards structured source mapping and profile controls")
    @MainActor
    func evaluationConfigurationForwardsStructuredSourceMappingAndProfileControls() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                ]
            )
        )
        await client.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        await viewModel.start()
        viewModel.selectedEvaluationModelID = "melix-dev-text"
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        viewModel.evaluationDatasetSourceKind = .localCSV
        viewModel.evaluationSourcePath = "/tmp/eval/mmlu.csv"
        viewModel.evaluationFieldSystemPath = "system_prompt"
        viewModel.evaluationFieldInputTextPath = "question"
        viewModel.evaluationFieldTargetPath = "gold_answer"
        viewModel.evaluationFieldSampleIDPath = "sample_id"
        viewModel.evaluationResultKind = "text"
        viewModel.evaluationExtractionMode = "heuristic_final"
        viewModel.evaluationScoringMode = "normalized_exact_match"
        viewModel.evaluationThreshold = "1.0"

        await viewModel.runEvaluation()

        let request = try #require(await client.recordedEvaluationRequests.last)
        #expect(request.datasetID.isEmpty)
        #expect(request.source.kind == .localCSV)
        #expect(request.source.path == "/tmp/eval/mmlu.csv")
        #expect(request.fieldMapping.systemPath == "system_prompt")
        #expect(request.fieldMapping.inputTextPath == "question")
        #expect(request.fieldMapping.targetPath == "gold_answer")
        #expect(request.fieldMapping.sampleIDPath == "sample_id")
        #expect(request.profile.resultKind == "text")
        #expect(request.profile.extractionMode == "heuristic_final")
        #expect(request.profile.scoringMode == "normalized_exact_match")
        #expect(request.profile.threshold == 1.0)
    }

    @Test("evaluation compare supports custom JSONL dataset sources")
    @MainActor
    func evaluationCompareSupportsCustomJSONLDatasetSources() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                    makeModelSummary(modelID: "melix-dev-text-lora", state: .modelWarm),
                ]
            )
        )

        await viewModel.start()
        viewModel.selectedEvaluationModelID = "melix-dev-text"
        viewModel.selectedEvaluationMode = .compare
        viewModel.selectedEvaluationCompareTargetModelIDs = ["melix-dev-text-lora"]
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        viewModel.evaluationDatasetSourceKind = .localJSONL
        viewModel.evaluationSourcePath = "/tmp/eval/mmlu.jsonl"
        viewModel.evaluationFieldInputTextPath = "prompt"
        viewModel.evaluationFieldTargetPath = "expected"
        viewModel.evaluationFieldSampleIDPath = "sample_id"
        viewModel.evaluationResultKind = "text"
        viewModel.evaluationExtractionMode = "heuristic_final"
        viewModel.evaluationScoringMode = "normalized_exact_match"
        viewModel.evaluationThreshold = "1.0"

        await viewModel.runEvaluation()

        let request = try #require(await client.recordedEvaluationRequests.last)
        #expect(viewModel.lastError == nil)
        #expect(request.datasetID.isEmpty)
        #expect(request.source.kind == .localJSONL)
        #expect(request.source.path == "/tmp/eval/mmlu.jsonl")
        #expect(request.fieldMapping.inputTextPath == "prompt")
        #expect(request.fieldMapping.targetPath == "expected")
        #expect(request.fieldMapping.sampleIDPath == "sample_id")
        #expect(request.parameters["compare_mode"] == "base_vs_targets")
        #expect(request.parameters["compare_target_model_ids"] == "melix-dev-text-lora")
    }

    @Test("evaluation selection state and guard rails cover catalog and direct repo flows")
    @MainActor
    func evaluationSelectionStateAndGuardRailsCoverCatalogAndDirectRepoFlows() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        viewModel.selectedEvaluationModelID = "missing-model"
        viewModel.selectedEvaluationSuiteIDs = ["unknown-suite"]
        viewModel.selectedEvaluationHistoryJobID = "stale-job"

        await viewModel.start()

        #expect(viewModel.selectedEvaluationModelID == "melix-dev-text")
        #expect(viewModel.selectedEvaluationSuiteIDs == ["mmlu"])
        #expect(viewModel.selectedEvaluationHistoryJobID.isEmpty)

        viewModel.toggleEvaluationSuite("gsm8k")
        #expect(viewModel.selectedEvaluationSuiteIDs.contains("gsm8k"))
        viewModel.toggleEvaluationSuite("gsm8k")
        #expect(viewModel.selectedEvaluationSuiteIDs.contains("gsm8k") == false)

        viewModel.selectedEvaluationSuiteIDs = []
        await viewModel.runEvaluation()
        #expect(viewModel.lastError == "Select at least one evaluation suite before running Evaluation.")

        viewModel.selectedEvaluationTargetMode = .huggingFaceRepo
        viewModel.evaluationHFRepoID = ""
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        await viewModel.runEvaluation()
        #expect(viewModel.lastError == "Enter a Hugging Face repo before running Evaluation.")

        viewModel.evaluationHFRepoID = "meta-llama/Llama-3.2-1B-Instruct"
        await viewModel.runEvaluation()

        let request = try #require(await client.recordedEvaluationRequests.last)
        #expect(request.modelID.isEmpty)
        #expect(request.hfRepoID == "meta-llama/Llama-3.2-1B-Instruct")
        #expect(viewModel.evaluationTargetSummaryText.contains("meta-llama/Llama-3.2-1B-Instruct"))

        let audioOnlyClient = FakeControlPlaneXPCClient()
        let audioOnlyModel = makeCapabilityModelSummary(
            modelID: "melix-dev-audio",
            kind: "audio",
            state: .modelWarm,
            features: ["transcribe"]
        )
        await audioOnlyClient.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [audioOnlyModel]
            )
        )
        let audioOnlyViewModel = RuntimeViewModel(client: audioOnlyClient)
        await audioOnlyViewModel.start()
        audioOnlyViewModel.selectedEvaluationSuiteIDs = ["mmlu"]

        await audioOnlyViewModel.runEvaluation()

        #expect(audioOnlyViewModel.lastError == "Select a text-generation model before running Evaluation.")
    }

    @Test("lora training and activation dispatch the configured dataset source hyperparameters and derived alias")
    @MainActor
    func loraTrainingAndActivationDispatchConfiguredPayloads() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeRegistrySnapshotManifest(
                    publishedRepo: "",
                    targetRepo: "melix/adapters/hf-demo-adapter"
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        await viewModel.start()
        viewModel.selectedLoraModelID = "melix-dev-text"
        viewModel.loraDatasetSourceKind = .huggingFaceDataset
        viewModel.loraHFDatasetPath = "HuggingFaceH4/ultrachat_200k"
        viewModel.loraHFDatasetName = "default"
        viewModel.loraHFDatasetRevision = "main"
        viewModel.loraHFTrainSplit = "train_sft"
        viewModel.loraHFValidSplit = "test_sft"
        viewModel.loraTextFeature = "messages"
        viewModel.loraPromptFeature = "prompt"
        viewModel.loraCompletionFeature = "completion"
        viewModel.loraChatFeature = "messages"
        viewModel.loraAdapterName = "hf-demo-adapter"
        viewModel.loraTargetRepo = "melix/adapters/hf-demo-adapter"
        viewModel.selectedLoraTrainingPreset = .balancedAdapter
        viewModel.loraExperimentGroupID = "nightly-qwen35"
        viewModel.loraRank = "32"
        viewModel.loraAlpha = "64"
        viewModel.loraDropout = "0.1"
        viewModel.loraTargetModules = "q_proj,k_proj,v_proj"
        viewModel.loraNumLayers = "24"
        viewModel.loraBatchSize = "4"
        viewModel.loraEpochs = "2"
        viewModel.loraLearningRate = "0.0002"
        viewModel.loraMaxSeqLength = "8192"
        viewModel.loraResponseOnly = true
        viewModel.loraMaskPrompt = true
        viewModel.loraGradientCheckpointing = true
        viewModel.loraDerivedModelAlias = "melix-dev-text-ultrachat"
        viewModel.loraTrainingMode = .qlora
        viewModel.loraActivationMode = .adapterBackedRuntime

        await viewModel.trainPrimaryModel()
        let trainRequest = try #require(await client.recordedModelOperationRequests.first(where: { $0.operation == "train_lora" }))
        #expect(trainRequest.modelID == "melix-dev-text")
        #expect(trainRequest.ext["dataset_source_kind"] == "hf_dataset")
        #expect(trainRequest.ext["hf_dataset_path"] == "HuggingFaceH4/ultrachat_200k")
        #expect(trainRequest.ext["hf_dataset_name"] == "default")
        #expect(trainRequest.ext["hf_dataset_revision"] == "main")
        #expect(trainRequest.ext["hf_train_split"] == "train_sft")
        #expect(trainRequest.ext["hf_valid_split"] == "test_sft")
        #expect(trainRequest.ext["text_feature"] == "messages")
        #expect(trainRequest.ext["prompt_feature"] == "prompt")
        #expect(trainRequest.ext["completion_feature"] == "completion")
        #expect(trainRequest.ext["chat_feature"] == "messages")
        #expect(trainRequest.ext["adapter_name"] == "hf-demo-adapter")
        #expect(trainRequest.ext["target_repo"] == "melix/adapters/hf-demo-adapter")
        #expect(trainRequest.ext["preset_id"] == "balanced_adapter")
        #expect(trainRequest.ext["experiment_group_id"] == "nightly-qwen35")
        #expect(trainRequest.ext["rank"] == "32")
        #expect(trainRequest.ext["alpha"] == "64")
        #expect(trainRequest.ext["dropout"] == "0.1")
        #expect(trainRequest.ext["target_modules"] == "q_proj,k_proj,v_proj")
        #expect(trainRequest.ext["num_layers"] == "24")
        #expect(trainRequest.ext["batch_size"] == "4")
        #expect(trainRequest.ext["epochs"] == "2")
        #expect(trainRequest.ext["learning_rate"] == "0.0002")
        #expect(trainRequest.ext["max_seq_length"] == "8192")
        #expect(trainRequest.ext["response_only"] == "true")
        #expect(trainRequest.ext["mask_prompt"] == "true")
        #expect(trainRequest.ext["gradient_checkpointing"] == "true")
        #expect(trainRequest.ext["derived_model_alias"] == "melix-dev-text-ultrachat")
        #expect(trainRequest.ext["training_mode"] == "qlora")

        await viewModel.activateLatestAdapter()
        let activateRequest = try #require(await client.recordedModelOperationRequests.first(where: { $0.operation == "activate_adapter" }))
        #expect(activateRequest.modelID == "melix-dev-text")
        #expect(activateRequest.ext["artifact_path"] == "/tmp/melix-train-lora/train_lora.adapter.json")
        #expect(activateRequest.ext["derived_model_alias"] == "melix-dev-text-ultrachat")
        #expect(activateRequest.ext["activation_mode"] == "adapter_backed_runtime")
    }

    @Test("lora activation surfaces a running workflow state before completion and a success summary afterward")
    @MainActor
    func loraActivationSurfacesRunningThenSuccessWorkflowState() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperationDelay(.milliseconds(120))
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
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "activate_adapter",
                outputPath: "/tmp/melix-activate/activate_adapter.derived_model.json",
                manifestJSON: #"{"operation":"activate_adapter","derived_model_path":"/tmp/melix-activate/activate_adapter.derived_model.json"}"#
            ),
            forNamedOperation: "activate_adapter"
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        let task = Task { await viewModel.activateLatestAdapter() }
        try await Task.sleep(for: .milliseconds(20))

        let runningStatus = try #require(viewModel.loraWorkflowStatus)
        #expect(runningStatus.phase == .running)
        #expect(runningStatus.operation == "activate_adapter")
        #expect(runningStatus.title == "Activating Adapter")

        await task.value

        let completedStatus = try #require(viewModel.loraWorkflowStatus)
        #expect(completedStatus.phase == .succeeded)
        #expect(completedStatus.operation == "activate_adapter")
        #expect(completedStatus.title == "Adapter Activated")
        #expect(completedStatus.detail.contains("activate_adapter.derived_model.json"))
    }

    @Test("lora activation failure surfaces workflow failure details inline")
    @MainActor
    func loraActivationFailureSurfacesWorkflowFailureDetails() async throws {
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
        await client.configureModelOperationError(
            NSError(
                domain: "RuntimeViewModelTests",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "activation unavailable"]
            ),
            forNamedOperation: "activate_adapter"
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()
        await viewModel.activateLatestAdapter()

        let failedStatus = try #require(viewModel.loraWorkflowStatus)
        #expect(failedStatus.phase == .failed)
        #expect(failedStatus.operation == "activate_adapter")
        #expect(failedStatus.title == "Activation Failed")
        #expect(failedStatus.detail.contains("activation unavailable"))
    }

    @Test("lora removal and compare workflows dispatch configured modes through the shared runner seam")
    @MainActor
    func loraRemovalAndCompareDispatchConfiguredModesThroughSharedRunnerSeam() async throws {
        let directClient = FakeControlPlaneXPCClient()
        let runnerClient = FakeControlPlaneXPCClient()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-runner-phase4-lora-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        await directClient.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                    makeModelSummary(modelID: "melix-dev-text-lora", state: .modelWarm),
                ]
            )
        )
        await runnerClient.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                    makeModelSummary(modelID: "melix-dev-text-lora", state: .modelWarm),
                ]
            )
        )
        await runnerClient.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "train_lora",
                outputPath: "/tmp/melix-train-lora/train_lora.adapter.json",
                manifestJSON: "{}"
            ),
            forNamedOperation: "train_lora"
        )
        await runnerClient.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "activate_adapter",
                outputPath: "/tmp/melix-activate/activate_adapter.derived_model.json",
                manifestJSON: "{}"
            ),
            forNamedOperation: "activate_adapter"
        )
        await runnerClient.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "remove_derived_model",
                outputPath: "/tmp/melix-remove/remove_derived_model.json",
                manifestJSON: "{}"
            ),
            forNamedOperation: "remove_derived_model"
        )
        await runnerClient.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeRegistrySnapshotManifest(
                    publishedRepo: "",
                    targetRepo: "melix/adapters/hf-demo-adapter",
                    activationStatus: "activated",
                    derivedModelID: "melix-dev-text-lora",
                    derivedModelPath: "/tmp/melix-derived/model"
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        await runnerClient.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        let operatorStore = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        let runner = MelixCLIRunner(
            client: runnerClient,
            environment: ["MELIX_HOME": temporaryRoot.path],
            operatorSessionStore: operatorStore
        )
        let viewModel = RuntimeViewModel(
            client: directClient,
            operatorCommandRunner: runner
        )

        await viewModel.start()
        await viewModel.refreshModelOpsProductState()
        viewModel.selectedLoraModelID = "melix-dev-text"
        viewModel.loraDatasetSourceKind = .huggingFaceDataset
        viewModel.loraHFDatasetPath = "HuggingFaceH4/ultrachat_200k"
        viewModel.loraHFTrainSplit = "train_sft"
        viewModel.loraChatFeature = "messages"
        viewModel.loraAdapterName = "hf-demo-adapter"
        viewModel.loraDerivedModelAlias = "melix-dev-text-ultrachat"
        viewModel.loraTrainingMode = .qlora
        viewModel.loraActivationMode = .adapterBackedRuntime
        await viewModel.trainPrimaryModel()
        await viewModel.activateLatestAdapter()
        viewModel.selectedEvaluationTargetMode = .catalogModel
        viewModel.selectedEvaluationModelID = "melix-dev-text"
        viewModel.selectedEvaluationMode = .compare
        viewModel.selectedEvaluationCompareTargetModelIDs = ["melix-dev-text-lora"]
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        viewModel.evaluationSampleSize = "6"
        viewModel.evaluationBatchFactor = "2"
        viewModel.evaluationFewShot = "1"
        viewModel.evaluationSeed = "9"
        viewModel.evaluationScoringMode = "multiple_choice_accuracy"
        viewModel.evaluationCodeExecPolicy = "sandboxed"
        await viewModel.runEvaluation()
        await viewModel.removeSelectedDerivedModel()

        let runnerModelOps = await runnerClient.recordedModelOperationRequests
        let trainRequest = try #require(runnerModelOps.first(where: { $0.operation == "train_lora" }))
        let activateRequest = try #require(runnerModelOps.first(where: { $0.operation == "activate_adapter" }))
        let removeRequest = try #require(runnerModelOps.first(where: { $0.operation == "remove_derived_model" }))
        let evaluationRequest = try #require(await runnerClient.recordedEvaluationRequests.last)

        #expect(await directClient.recordedModelOperationRequests.isEmpty)
        #expect(await directClient.recordedEvaluationRequests.isEmpty)
        #expect(trainRequest.ext["training_mode"] == "qlora")
        #expect(activateRequest.ext["activation_mode"] == "adapter_backed_runtime")
        #expect(removeRequest.ext["derived_model_id"] == "melix-dev-text-lora")
        #expect(removeRequest.ext["manifest_path"] == nil)
        #expect(evaluationRequest.parameters["compare_mode"] == "base_vs_targets")
        #expect(evaluationRequest.parameters["compare_target_model_ids"] == "melix-dev-text-lora")
        #expect(evaluationRequest.parameters["batch_factor"] == "2")
        #expect(evaluationRequest.parameters["few_shot"] == "1")
        #expect(evaluationRequest.parameters["seed"] == "9")
        #expect(evaluationRequest.parameters["scoring_mode"] == "multiple_choice_accuracy")
        #expect(evaluationRequest.parameters["code_exec_policy"] == "sandboxed")
    }

    @Test("lora remove and compare guard rails require concrete targets")
    @MainActor
    func loraRemoveAndCompareGuardRailsRequireConcreteTargets() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.selectedEvaluationMode = .compare
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]

        await viewModel.runEvaluation()
        #expect(viewModel.lastError == "Select at least one compare target model before running Evaluation Compare.")

        await viewModel.removeSelectedDerivedModel()
        #expect(viewModel.lastError == "Select an activated adapter before removing its derived model.")
    }

    @Test("fetch model info surfaces OCR profile defaults from the active snapshot")
    @MainActor
    func fetchModelInfoSurfacesOCRProfileDefaultsFromActiveSnapshot() async throws {
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

        #expect(viewModel.selectedModelInfo?.modelID == "melix-dev-ocr")
        #expect(viewModel.selectedModelInfo?.ocrPromptProfileText == "ocr-default-v1")
        #expect(viewModel.selectedModelInfo?.ocrSamplingProfileText == "ocr-deterministic")
        #expect(viewModel.selectedModelInfo?.ocrStopSequencesText == "<ocr:end>")
    }

    @Test("fetch model info merges speech voice catalog metadata from the active snapshot")
    @MainActor
    func fetchModelInfoMergesSpeechVoiceCatalogMetadataFromActiveSnapshot() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = "melix-qwen3-tts-mlx"
        model.kind = "speech"
        model.state = .modelDiscovered
        model.supportedTasks = ["speak"]
        model.supportedModalities = ["text", "audio"]
        model.settings.alias = "Melix Qwen3 TTS MLX"
        model.settings.ext["melix.audio.backend_id"] = "mlx_audio.tts"
        model.settings.ext["melix.audio.family_id"] = "qwen3-tts"
        model.settings.ext["melix.audio.install_profile"] = "audio-tts"
        model.settings.ext["melix.audio.languages"] = "zh,en"
        model.settings.ext["melix.audio.voice_mode"] = "hybrid"
        model.settings.ext["melix.audio.output_formats"] = "wav"
        model.settings.ext["melix.audio.supports_instructions"] = "true"
        model.settings.ext["melix.audio.voice_catalog_summary"] =
            "Hybrid named and instruction-conditioned multilingual voices for Chinese and English synthesis."
        model.settings.ext["melix.audio.voice_locales"] = "zh,en"
        model.settings.ext["melix.audio.default_locale"] = "zh"
        model.settings.ext["melix.audio.packaged_default_locale"] = "zh"
        model.settings.ext["melix.audio.locale_policy"] = "request>model_default>packaged_default"
        model.settings.ext["melix.audio.runtime_pack_state"] = "installed"
        model.settings.ext["melix.audio.runtime_pack_id"] = "melix-audio-runtime-pack"
        model.settings.ext["melix.audio.model_state"] = "managed_local"
        snapshot.models = [model]

        var info = Melix_Controlplane_V1_ModelInfo()
        info.ok = true
        info.modelKind = "speech"
        info.maxContext = 4096
        info.supportedParsers = ["text"]
        info.supportedModalities = ["text", "audio"]
        info.supportedTasks = ["speak"]
        info.backendID = "mlx_audio.tts"
        info.familyID = "qwen3-tts"
        info.modelPath = "mlx-community/Qwen3-TTS-4B-Instruct-2507-4bit"
        info.modelRevision = "mlx-audio"

        await client.configureSnapshot(snapshot)
        await client.configureModelInfo(info)

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.fetchModelInfo(modelID: "melix-qwen3-tts-mlx")

        #expect(viewModel.selectedModelInfo?.modelID == "melix-qwen3-tts-mlx")
        #expect(viewModel.selectedModelInfo?.audioInstallProfileText == "audio-tts")
        #expect(viewModel.selectedModelInfo?.audioLanguagesText == "zh,en")
        #expect(viewModel.selectedModelInfo?.audioVoiceModeText == "hybrid")
        #expect(viewModel.selectedModelInfo?.audioOutputFormatsText == "wav")
        #expect(viewModel.selectedModelInfo?.audioSupportsInstructionsText == "Yes")
        #expect(viewModel.selectedModelInfo?.audioVoiceLocalesText == "zh,en")
        #expect(viewModel.selectedModelInfo?.audioDefaultLocaleText == "zh")
        #expect(viewModel.selectedModelInfo?.audioPackagedDefaultLocaleText == "zh")
        #expect(viewModel.selectedModelInfo?.audioLocalePolicyText == "request>model_default>packaged_default")
        #expect(viewModel.selectedModelInfo?.audioRuntimePackStateText == "installed")
        #expect(viewModel.selectedModelInfo?.audioRuntimePackIDText == "melix-audio-runtime-pack")
        #expect(viewModel.selectedModelInfo?.audioModelStateText == "managed_local")
        #expect(
            viewModel.selectedModelInfo?.audioVoiceCatalogSummaryText
                == "Hybrid named and instruction-conditioned multilingual voices for Chinese and English synthesis."
        )
    }

    @Test("model tool actions no-op when there is no primary model")
    @MainActor
    func modelToolActionsNoopWithoutPrimaryModel() async throws {
        let client = EmptySnapshotControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.updatePrimaryModelForLatency()
        await viewModel.inspectPrimaryModel()
        await viewModel.convertPrimaryModel()
        await viewModel.quantizePrimaryModel()
        await viewModel.trainPrimaryModel()
        await viewModel.refreshModelOpsProductState()
        await viewModel.publishLatestAdapter()
        await viewModel.downloadPrimaryModel()
        await viewModel.uploadPrimaryModel()

        #expect(viewModel.primaryModel == nil)
        #expect(await client.recordedActions.isEmpty)
        let snapshot = await metrics.snapshot()
        #expect(snapshot["menu.model_settings_ms"] == nil)
        #expect(snapshot["menu.model_info_ms"] == nil)
        #expect(snapshot["menu.model_operation_ms"] == nil)
        #expect(snapshot["menu.model_ops_refresh_ms"] == nil)
    }

    @Test("model tool failures surface local errors")
    @MainActor
    func modelToolFailuresSurfaceLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await client.configureErrors(
            modelSettings: MenuBarTestError(description: "settings failed"),
            modelInfo: MenuBarTestError(description: "inspect failed"),
            modelOperation: MenuBarTestError(description: "operation failed"),
            doctor: MenuBarTestError(description: "doctor failed"),
            bench: MenuBarTestError(description: "bench failed")
        )

        await viewModel.updatePrimaryModelForLatency()
        #expect(viewModel.lastError?.contains("settings failed") == true)

        await viewModel.inspectPrimaryModel()
        #expect(viewModel.lastError?.contains("inspect failed") == true)

        await viewModel.runDoctor()
        #expect(viewModel.lastError?.contains("doctor failed") == true)

        await viewModel.runBench()
        #expect(viewModel.lastError?.contains("bench failed") == true)

        await viewModel.quantizePrimaryModel()
        #expect(viewModel.lastError?.contains("operation failed") == true)

        await viewModel.refreshModelOpsProductState()
        #expect(viewModel.lastError?.contains("operation failed") == true)
    }

    @Test("registry root add refresh forwards explicit overrides and parses root snapshot state")
    @MainActor
    func registryRootAddRefreshForwardsExplicitOverridesAndParsesRootSnapshotState() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [
                        MenuBarRegistryRootFixture(
                            id: "root-a",
                            path: "/tmp/root-a",
                            order: 1,
                            discoveredModelIDs: ["registry-model-a"]
                        ),
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        await viewModel.start()
        viewModel.registryRootPathDraft = "/tmp/root-a"
        await viewModel.addRegistryRoot()

        let request = try #require(await client.recordedModelOperationRequests.last)
        let root = try #require(viewModel.registryRoots.first)

        #expect(request.ext["melix.registry_roots_json"] == #"["/tmp/root-a"]"#)
        #expect(request.ext["melix.registry_rescan"] == "true")
        #expect(viewModel.registryHasConfiguredRootOverride)
        #expect(viewModel.registryConfiguredRootPaths == ["/tmp/root-a"])
        #expect(viewModel.registryScannedAtText != "Never")
        #expect(root.rootPath == "/tmp/root-a")
        #expect(root.statusText == "Accessible")
        #expect(root.detailText == "1 model")
        #expect(await metrics.snapshot()["menu.model_ops_refresh_ms"] != nil)
    }

    @Test("registry root reorder remove and rescan reuse configured root overrides")
    @MainActor
    func registryRootReorderRemoveAndRescanReuseConfiguredRootOverrides() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [
                        MenuBarRegistryRootFixture(id: "root-a", path: "/tmp/root-a", order: 1),
                        MenuBarRegistryRootFixture(id: "root-b", path: "/tmp/root-b", order: 2),
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        await viewModel.start()
        await viewModel.refreshModelOpsProductState()
        await viewModel.moveRegistryRootDown(rootID: "root-a")
        await viewModel.removeRegistryRoot(rootID: "root-b")
        await viewModel.rescanRegistryRoots()

        let requests = await client.recordedModelOperationRequests.filter { $0.operation == "registry_snapshot" }
        #expect(requests.count == 4)
        let refreshRequest = requests[0]
        let moveRequest = requests[1]
        let removeRequest = requests[2]
        let rescanRequest = requests[3]

        #expect(refreshRequest.ext["melix.registry_roots_json"] == nil)
        #expect(moveRequest.ext["melix.registry_roots_json"] == #"["/tmp/root-b","/tmp/root-a"]"#)
        #expect(moveRequest.ext["melix.registry_rescan"] == "true")
        #expect(removeRequest.ext["melix.registry_roots_json"] == #"["/tmp/root-a"]"#)
        #expect(removeRequest.ext["melix.registry_rescan"] == "true")
        #expect(rescanRequest.ext["melix.registry_roots_json"] == #"["/tmp/root-a"]"#)
        #expect(rescanRequest.ext["melix.registry_rescan"] == "true")
        #expect(viewModel.registryHasConfiguredRootOverride)
        #expect(viewModel.registryConfiguredRootPaths == ["/tmp/root-a"])
    }

    @Test("registry root state formats unavailable status and detail text")
    @MainActor
    func registryRootStateFormatsUnavailableStatusAndDetailText() {
        let inaccessibleWithoutCode = RuntimeRegistryRootState(
            id: "root-none",
            rootPath: "/tmp/root-none",
            rootOrder: 1,
            accessible: false,
            errorCode: "",
            errorMessage: "",
            discoveredModelIDs: []
        )
        let inaccessibleWithCode = RuntimeRegistryRootState(
            id: "root-denied",
            rootPath: "/tmp/root-denied",
            rootOrder: 2,
            accessible: false,
            errorCode: "permission_denied",
            errorMessage: "Sandbox denied access",
            discoveredModelIDs: ["model-a", "model-b"]
        )

        #expect(inaccessibleWithoutCode.statusText == "Unavailable")
        #expect(inaccessibleWithoutCode.detailText == "0 models")
        #expect(inaccessibleWithCode.statusText == "Permission denied")
        #expect(inaccessibleWithCode.detailText == "2 models • Sandbox denied access")
    }

    @Test("registry root summaries cover configured overrides and empty override state")
    @MainActor
    func registryRootSummariesCoverConfiguredOverridesAndEmptyOverrideState() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [
                        MenuBarRegistryRootFixture(id: "root-a", path: "/tmp/root-a", order: 1),
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        let addViewModel = RuntimeViewModel(client: client)
        await addViewModel.start()
        await addViewModel.refreshModelOpsProductState()
        addViewModel.registryRootPathDraft = "/tmp/root-b"
        await addViewModel.addRegistryRoot()
        #expect(addViewModel.registryRootSummaryText == "Control-plane override active • 2 roots configured")
        #expect(addViewModel.canAddRegistryRoot == false)

        let removeViewModel = RuntimeViewModel(client: client)
        await removeViewModel.start()
        await removeViewModel.refreshModelOpsProductState()
        await removeViewModel.removeRegistryRoot(rootID: "root-a")
        #expect(removeViewModel.registryRootSummaryText == "Control-plane override active • no roots configured")
    }

    @Test("registry root guard rails no-op for missing models invalid drafts duplicate roots and invalid moves")
    @MainActor
    func registryRootGuardRailsNoOpForMissingModelsInvalidDraftsDuplicateRootsAndInvalidMoves() async throws {
        let imageOnlyClient = FakeControlPlaneXPCClient()
        var imageOnlySnapshot = Melix_Controlplane_V1_ServerSnapshot()
        imageOnlySnapshot.serverState = .serverReady
        imageOnlySnapshot.models = [makeMenuBarImageModelSummary()]
        await imageOnlyClient.configureSnapshot(imageOnlySnapshot)
        let imageOnlyViewModel = RuntimeViewModel(client: imageOnlyClient)
        await imageOnlyViewModel.start()
        imageOnlyViewModel.registryRootPathDraft = "/tmp/no-text-root"
        await imageOnlyViewModel.rescanRegistryRoots()
        await imageOnlyViewModel.addRegistryRoot()
        await imageOnlyViewModel.removeRegistryRoot(rootID: "missing-root")
        await imageOnlyViewModel.moveRegistryRootUp(rootID: "missing-root")
        #expect(await imageOnlyClient.recordedModelOperationRequests.isEmpty)

        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeModelOpsRegistrySnapshotManifestJSON(
                    roots: [
                        MenuBarRegistryRootFixture(id: "root-a", path: "/tmp/root-a", order: 1),
                    ]
                )
            ),
            forNamedOperation: "registry_snapshot"
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        let initialRequestCount = await client.recordedModelOperationRequests.count
        viewModel.registryRootPathDraft = "   "
        await viewModel.addRegistryRoot()
        viewModel.registryRootPathDraft = "/tmp/root-a"
        await viewModel.addRegistryRoot()
        await viewModel.removeRegistryRoot(rootID: "missing-root")
        await viewModel.moveRegistryRootDown(rootID: "root-a")
        await viewModel.moveRegistryRootUp(rootID: "missing-root")

        let finalRequestCount = await client.recordedModelOperationRequests.count
        #expect(initialRequestCount == 1)
        #expect(finalRequestCount == 1)
        #expect(viewModel.registryRootPathDraft.isEmpty)
    }

    @Test("registry snapshot parsing sorts same-order roots and drops invalid rows")
    @MainActor
    func registrySnapshotParsingSortsSameOrderRootsAndDropsInvalidRows() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: #"""
                {
                  "operation": "registry_snapshot",
                  "jobs": [],
                  "adapters": [],
                  "derived_models": [],
                  "model_registry": {
                    "scanned_at_unix_ms": "1712300000000",
                    "roots": [
                      {
                        "root_path": "/tmp/invalid-root",
                        "root_order": "9",
                        "accessible": "yes",
                        "error_code": "",
                        "error_message": "",
                        "discovered_model_ids": []
                      },
                      {
                        "root_id": "root-b",
                        "root_path": "/tmp/root-b",
                        "root_order": "7",
                        "accessible": "yes",
                        "error_code": "permission_denied",
                        "error_message": "needs entitlement",
                        "discovered_model_ids": ["model-b", ""]
                      },
                      {
                        "root_id": "root-a",
                        "root_path": "/tmp/root-a",
                        "root_order": "7",
                        "accessible": false,
                        "error_code": "",
                        "error_message": "",
                        "discovered_model_ids": ["model-a"]
                      }
                    ],
                    "models": []
                  }
                }
                """#
            ),
            forNamedOperation: "registry_snapshot"
        )

        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        #expect(viewModel.registryRoots.map(\.rootPath) == ["/tmp/root-a", "/tmp/root-b"])
        #expect(viewModel.registryRoots.count == 2)
        #expect(viewModel.registryRoots[0].statusText == "Unavailable")
        #expect(viewModel.registryRoots[1].detailText == "1 model • needs entitlement")
        #expect(viewModel.registryScannedAtText != "Never")
    }

    @Test("quantize action stores typed quantization summary")
    @MainActor
    func quantizeActionStoresTypedQuantizationSummary() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "quantize",
                outputPath: "/tmp/melix-quantize/model-ops-0001/quantize.artifact",
                manifestJSON: #"""
                {
                  "operation": "quantize",
                  "calibration": {
                    "sample_count": 32
                  }
                }
                """#,
                quantProfileID: "q6",
                artifactKind: "quantized_model_bundle",
                manifestPath: "/tmp/melix-quantize/model-ops-0001/quantize.artifact/manifest.json",
                artifactBytes: 256,
                smokeTestPassed: true
            ),
            forNamedOperation: "quantize"
        )

        await viewModel.start()
        viewModel.selectedQuantizationProfileID = "q6"
        await viewModel.quantizePrimaryModel()

        #expect(viewModel.lastModelOperation?.operation == "quantize")
        #expect(viewModel.lastModelOperation?.quantProfileID == "q6")
        #expect(viewModel.lastModelOperation?.artifactKind == "quantized_model_bundle")
        #expect(viewModel.lastModelOperation?.manifestPath == "/tmp/melix-quantize/model-ops-0001/quantize.artifact/manifest.json")
        #expect(viewModel.lastModelOperation?.artifactBytes == 256)
        #expect(viewModel.lastModelOperation?.smokeTestPassed == true)
        #expect(viewModel.lastModelOperation?.calibrationSampleCount == 32)
    }

    @Test("convert action stores typed packaging summary")
    @MainActor
    func convertActionStoresTypedPackagingSummary() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "convert",
                outputPath: "/tmp/melix-convert/job-1/convert.artifact",
                manifestJSON: #"""
                {
                  "operation": "convert",
                  "target_format": "melix_model_bundle",
                  "compatibility": {
                    "runtime": "mlx_text",
                    "serving_compatible": true,
                    "smoke_test_requested": true,
                    "smoke_test_passed": true
                  }
                }
                """#,
                artifactKind: "converted_model_bundle",
                manifestPath: "/tmp/melix-convert/job-1/convert.artifact/manifest.json",
                artifactBytes: 384,
                smokeTestPassed: true
            ),
            forNamedOperation: "convert"
        )

        await viewModel.start()
        await viewModel.convertPrimaryModel()

        #expect(viewModel.lastModelOperation?.operation == "convert")
        #expect(viewModel.lastModelOperation?.artifactKind == "converted_model_bundle")
        #expect(viewModel.lastModelOperation?.conversionTargetFormat == "melix_model_bundle")
        #expect(viewModel.lastModelOperation?.artifactRuntime == "mlx_text")
        #expect(viewModel.lastModelOperation?.servingCompatible == true)
        #expect(viewModel.lastModelOperation?.smokeTestRequested == true)
        #expect(viewModel.lastModelOperation?.smokeTestPassed == true)
    }

    @Test("convert action tolerates invalid manifest json and keeps artifact fallback state")
    @MainActor
    func convertActionToleratesInvalidManifestJSON() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "convert",
                outputPath: "/tmp/melix-convert/job-1/convert.artifact",
                manifestJSON: "{not-json",
                artifactKind: "converted_model_bundle",
                manifestPath: "/tmp/melix-convert/job-1/convert.artifact/manifest.json",
                artifactBytes: 384,
                smokeTestPassed: true
            ),
            forNamedOperation: "convert"
        )

        await viewModel.start()
        await viewModel.convertPrimaryModel()

        #expect(viewModel.lastModelOperation?.operation == "convert")
        #expect(viewModel.lastModelOperation?.artifactKind == "converted_model_bundle")
        #expect(viewModel.lastModelOperation?.conversionTargetFormat == "")
        #expect(viewModel.lastModelOperation?.artifactRuntime == "mlx_text")
    }

    @Test("upload action links the latest quantized artifact when available")
    @MainActor
    func uploadActionLinksLatestQuantizedArtifact() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "quantize",
                outputPath: "/tmp/melix-quantize/model-ops-0001/quantize.artifact",
                manifestJSON: #"""
                {
                  "operation": "quantize",
                  "calibration": {
                    "sample_count": 48
                  }
                }
                """#,
                quantProfileID: "q5",
                artifactKind: "quantized_model_bundle",
                manifestPath: "/tmp/melix-quantize/model-ops-0001/quantize.artifact/manifest.json",
                artifactBytes: 256,
                smokeTestPassed: true
            ),
            forNamedOperation: "quantize"
        )

        await viewModel.start()
        await viewModel.quantizePrimaryModel()
        await viewModel.uploadPrimaryModel()

        let uploadRequest = try #require(await client.recordedModelOperationRequests.last)
        #expect(uploadRequest.operation == "upload")
        #expect(uploadRequest.ext["artifact_kind"] == "model")
        #expect(uploadRequest.ext["artifact_path"] == "/tmp/melix-quantize/model-ops-0001/quantize.artifact")
        #expect(uploadRequest.ext["quantization_manifest_path"] == "/tmp/melix-quantize/model-ops-0001/quantize.artifact/manifest.json")
        #expect(uploadRequest.ext["quant_profile_id"] == "q5")
        #expect(uploadRequest.ext["target_repo"] == "melix/upload-target")
    }

    @Test("upload action links the latest converted artifact when available")
    @MainActor
    func uploadActionLinksLatestConvertedArtifact() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "convert",
                outputPath: "/tmp/melix-convert/job-1/convert.artifact",
                manifestJSON: #"""
                {
                  "operation": "convert",
                  "target_format": "melix_model_bundle",
                  "compatibility": {
                    "runtime": "mlx_text",
                    "serving_compatible": true,
                    "smoke_test_requested": true,
                    "smoke_test_passed": true
                  }
                }
                """#,
                artifactKind: "converted_model_bundle",
                manifestPath: "/tmp/melix-convert/job-1/convert.artifact/manifest.json",
                artifactBytes: 512,
                smokeTestPassed: true
            ),
            forNamedOperation: "convert"
        )

        await viewModel.start()
        await viewModel.convertPrimaryModel()
        await viewModel.uploadPrimaryModel()

        let uploadRequest = try #require(await client.recordedModelOperationRequests.last)
        #expect(uploadRequest.operation == "upload")
        #expect(uploadRequest.ext["artifact_kind"] == "model")
        #expect(uploadRequest.ext["artifact_path"] == "/tmp/melix-convert/job-1/convert.artifact")
        #expect(uploadRequest.ext["artifact_manifest_path"] == "/tmp/melix-convert/job-1/convert.artifact/manifest.json")
        #expect(uploadRequest.ext["quantization_manifest_path"] == nil)
        #expect(uploadRequest.ext["target_repo"] == "melix/upload-target")
    }

    @Test("model tooling refresh surfaces parse failures and publish no-ops without adapters")
    @MainActor
    func modelToolingRefreshSurfacesParseFailuresAndPublishNoopsWithoutAdapters() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: "{not-json"
            ),
            forNamedOperation: "registry_snapshot"
        )

        await viewModel.start()
        await viewModel.refreshModelOpsProductState()
        #expect(viewModel.lastError?.contains("registry snapshot") == true)
        await viewModel.publishLatestAdapter()

        #expect(viewModel.lastError == "Select an adapter package before publishing it.")
        #expect(viewModel.adapterPackages.isEmpty)
        #expect(viewModel.trainingHistory.isEmpty)
        #expect(viewModel.loraWorkflowStatus?.phase == .failed)
        #expect(viewModel.loraWorkflowStatus?.title == "Publish Failed")
    }

    @Test("model tooling snapshot normalizes pending adapter payloads and fallback publish flows")
    @MainActor
    func modelToolingSnapshotNormalizesPendingAdapterPayloads() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makePendingRegistrySnapshotManifest()
            ),
            forNamedOperation: "registry_snapshot"
        )

        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        let adapter = try #require(viewModel.adapterPackages.first)
        let trainingJob = try #require(viewModel.trainingHistory.first)

        #expect(adapter.adapterName == "pending-adapter")
        #expect(adapter.statusText == "Queued for publish")
        #expect(adapter.activationStatusText == "Pending activation")
        #expect(adapter.targetRepo.isEmpty)
        #expect(adapter.responseOnlyEnabled)
        #expect(adapter.gradientCheckpointingEnabled)
        #expect(adapter.trainingDurationText == "950ms")
        #expect(adapter.publishDurationText == "n/a")
        #expect(adapter.checkpointCount == 1)
        #expect(adapter.resumeReady)
        #expect(adapter.tokensPerSecond == 64.0)
        #expect(adapter.peakMemoryGB == 4.1)
        #expect(trainingJob.adapterName == "pending-adapter")
        #expect(trainingJob.datasetURI == "datasets/pending")
        #expect(trainingJob.statusText == "Unknown")
        #expect(trainingJob.stageText == "write_manifest • 42%")
        #expect(trainingJob.checkpointCount == 1)
        #expect(trainingJob.resumeReady)
        #expect(trainingJob.tokensPerSecond == 64.0)
        #expect(trainingJob.peakMemoryGB == 4.1)
        #expect(viewModel.loraExperimentGroups.first?.latestPresetTitle == "Debug Fast")
        #expect(viewModel.loraExperimentGroups.first?.runCount == 1)

        await viewModel.publishLatestAdapter()

        #expect(await client.recordedActions.contains("operation:upload:melix-dev-text"))
        #expect(await metrics.snapshot()["menu.model_ops_refresh_ms"] != nil)
        #expect(await metrics.snapshot()["menu.model_operation_ms"] != nil)
    }

    @Test("lora training presets apply the expected named defaults")
    @MainActor
    func loraTrainingPresetsApplyExpectedNamedDefaults() {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())

        viewModel.loraRank = "99"
        viewModel.loraAlpha = "199"
        viewModel.loraDropout = "0.9"
        viewModel.loraBatchSize = "9"
        viewModel.loraEpochs = "9"
        viewModel.loraLearningRate = "0.9"
        viewModel.loraMaxSeqLength = "999"
        viewModel.loraGradientCheckpointing = true

        viewModel.applyLoraTrainingPreset(.custom)
        #expect(viewModel.selectedLoraTrainingPreset == .custom)
        #expect(viewModel.loraRank == "99")
        #expect(viewModel.loraAlpha == "199")
        #expect(viewModel.loraDropout == "0.9")
        #expect(viewModel.loraBatchSize == "9")
        #expect(viewModel.loraEpochs == "9")
        #expect(viewModel.loraLearningRate == "0.9")
        #expect(viewModel.loraMaxSeqLength == "999")
        #expect(viewModel.loraGradientCheckpointing)

        viewModel.applyLoraTrainingPreset(.debugFast)
        #expect(viewModel.selectedLoraTrainingPreset == .debugFast)
        #expect(viewModel.loraRank == "8")
        #expect(viewModel.loraAlpha == "16")
        #expect(viewModel.loraDropout == "0.0")
        #expect(viewModel.loraBatchSize == "1")
        #expect(viewModel.loraEpochs == "1")
        #expect(viewModel.loraLearningRate == "0.0001")
        #expect(viewModel.loraMaxSeqLength == "1024")
        #expect(viewModel.loraGradientCheckpointing == false)

        viewModel.applyLoraTrainingPreset(.balancedAdapter)
        #expect(viewModel.selectedLoraTrainingPreset == .balancedAdapter)
        #expect(viewModel.loraRank == "16")
        #expect(viewModel.loraAlpha == "32")
        #expect(viewModel.loraDropout == "0.05")
        #expect(viewModel.loraBatchSize == "2")
        #expect(viewModel.loraEpochs == "2")
        #expect(viewModel.loraLearningRate == "0.0001")
        #expect(viewModel.loraMaxSeqLength == "2048")
        #expect(viewModel.loraGradientCheckpointing)

        viewModel.applyLoraTrainingPreset(.qualityAdapter)
        #expect(viewModel.selectedLoraTrainingPreset == .qualityAdapter)
        #expect(viewModel.loraRank == "32")
        #expect(viewModel.loraAlpha == "64")
        #expect(viewModel.loraDropout == "0.05")
        #expect(viewModel.loraBatchSize == "1")
        #expect(viewModel.loraEpochs == "4")
        #expect(viewModel.loraLearningRate == "0.00005")
        #expect(viewModel.loraMaxSeqLength == "2048")
        #expect(viewModel.loraGradientCheckpointing)
    }

    @Test("experiment group state surfaces resume-ready run ids and checkpoint lineage")
    @MainActor
    func experimentGroupStateSurfacesResumeReadyAndLineage() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeExperimentLineageRegistrySnapshotManifest()
            ),
            forNamedOperation: "registry_snapshot"
        )

        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        let group = try #require(viewModel.loraExperimentGroups.first)
        #expect(group.bestRunID == "model-ops-0012")
        #expect(group.resumeReadyRunIDs == ["model-ops-0012", "model-ops-0009"])
        #expect(group.resumeReadySummaryText == "2 of 3 runs resume-ready")
        #expect(group.checkpointLineage.count == 3)
        #expect(group.checkpointLineage.first?.runID == "model-ops-0012")
        #expect(group.checkpointLineage.first?.checkpointCount == 5)
        #expect(group.checkpointLineage.first?.resumeReady == true)
        #expect(group.checkpointLineage.last?.resumeReady == false)
    }

    @Test("resume-from-manifest path flows into the lora training request ext and is cleared after training")
    @MainActor
    func resumeFromManifestFlowsIntoTrainingExt() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "train_lora",
                outputPath: "/tmp/melix-train-lora/resume.adapter.json",
                manifestJSON: #"{"operation":"train_lora"}"#
            ),
            forNamedOperation: "train_lora"
        )

        await viewModel.start()
        viewModel.loraExperimentGroupID = "nightly-qwen35"
        viewModel.loraResumeFromManifestPath = "/tmp/prior/manifest.json"
        await viewModel.trainPrimaryModel()

        let call = try #require(
            await client.recordedModelOperationRequests.last(where: { $0.operation == "train_lora" })
        )
        #expect(call.ext["experiment_group_id"] == "nightly-qwen35")
        #expect(call.ext["resume_manifest_path"] == "/tmp/prior/manifest.json")
        #expect(viewModel.loraResumeFromManifestPath == "")
    }

    @Test("model tooling snapshot skips invalid experiment groups and parses string-backed doubles")
    @MainActor
    func modelToolingSnapshotSkipsInvalidExperimentGroupsAndParsesStringBackedDoubles() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)
        await client.configureModelOperation(
            makeNamedModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix-model-ops-registry/registry_snapshot.json",
                manifestJSON: makeStringBackedExperimentGroupRegistrySnapshotManifest()
            ),
            forNamedOperation: "registry_snapshot"
        )

        await viewModel.start()
        await viewModel.refreshModelOpsProductState()

        #expect(viewModel.loraExperimentGroups.count == 1)
        let group = try #require(viewModel.loraExperimentGroups.first)
        #expect(group.groupID == "string-metrics")
        #expect(group.bestLoss == 0.42)
        #expect(group.latestTokensPerSecond == 128.5)
        #expect(group.latestPeakMemoryGB == 5.25)
        #expect(group.experimentSummaryText == "2 checkpoints • resume ready")
        #expect(group.performanceSummaryText == "128.5 tok/s • 5.25 GB peak")
    }

    @Test("model settings support ttl and advanced acceleration labels")
    @MainActor
    func modelSettingsSupportAdvancedLabels() async throws {
        let client = FakeControlPlaneXPCClient()
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await viewModel.updateModelSettings(
            modelID: "melix-dev-text",
            alias: "Melix Warm Cache",
            pinOnLoad: false,
            memoryPolicy: "ttl",
            diskStreamingMode: "prefer_disk",
            accelerationMode: "accelerated_prefill",
            accelerationProfileID: "prefill-hot"
        )
        #expect(viewModel.primaryModel?.memoryPolicyText == "TTL")
        #expect(viewModel.primaryModel?.diskStreamingModeText == "Prefer Disk")
        #expect(viewModel.primaryModel?.accelerationModeText == "Accelerated Prefill")

        await viewModel.updateModelSettings(
            modelID: "melix-dev-text",
            alias: "Melix Quantized",
            pinOnLoad: false,
            memoryPolicy: "evictable",
            diskStreamingMode: "disabled",
            accelerationMode: "active_kv_quantized",
            accelerationProfileID: "kv-q8"
        )
        #expect(viewModel.primaryModel?.memoryPolicyText == "Evictable")
        #expect(viewModel.primaryModel?.diskStreamingModeText == "Disabled")
        #expect(viewModel.primaryModel?.accelerationModeText == "Active KV Quantized")
        #expect(viewModel.primaryModel?.accelerationProfileID == "kv-q8")
    }

    @Test("model settings drafts map require and unknown disk streaming modes")
    @MainActor
    func modelSettingsDraftsMapRequireAndUnknownDiskStreamingModes() async throws {
        let requireClient = FakeControlPlaneXPCClient()
        var requireSnapshot = Melix_Controlplane_V1_ServerSnapshot()
        requireSnapshot.serverState = .serverReady
        var requireModel = makeModelSummary(
            modelID: "melix-dev-text",
            state: Melix_Controlplane_V1_ModelState.modelWarm
        )
        requireModel.settings.diskStreamingMode = Melix_Controlplane_V1_DiskStreamingMode.diskStreamingRequireDisk
        requireSnapshot.models = [requireModel]
        await requireClient.configureSnapshot(requireSnapshot)

        let requireViewModel = RuntimeViewModel(client: requireClient)
        await requireViewModel.start()

        #expect(requireViewModel.primaryModel?.diskStreamingModeText == "Require Disk")
        #expect(requireViewModel.modelSettingsDiskStreamingModeDraft == "require_disk")

        let unknownClient = FakeControlPlaneXPCClient()
        var unknownSnapshot = Melix_Controlplane_V1_ServerSnapshot()
        unknownSnapshot.serverState = .serverReady
        var unknownModel = makeModelSummary(
            modelID: "melix-dev-text",
            state: Melix_Controlplane_V1_ModelState.modelWarm
        )
        unknownModel.settings.diskStreamingMode = Melix_Controlplane_V1_DiskStreamingMode.UNRECOGNIZED(-1)
        unknownSnapshot.models = [unknownModel]
        await unknownClient.configureSnapshot(unknownSnapshot)

        let unknownViewModel = RuntimeViewModel(client: unknownClient)
        await unknownViewModel.start()

        #expect(unknownViewModel.primaryModel?.diskStreamingModeText == "Disabled")
        #expect(unknownViewModel.modelSettingsDiskStreamingModeDraft == "disabled")
    }

    @Test("chat prompt streams assistant reasoning and tool deltas into the transcript")
    @MainActor
    func chatPromptStreamsAssistantReasoningAndToolDeltas() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Explain Melix"

        await viewModel.submitChatPrompt()

        let hasUserEntry = viewModel.chatTranscript.contains { $0.kind == .user && $0.body == "Explain Melix" }
        let hasAssistantEntry = viewModel.chatTranscript.contains {
            $0.kind == .assistant && $0.body.contains("Assistant response")
        }
        let hasReasoningEntry = viewModel.chatTranscript.contains {
            $0.kind == .reasoning && $0.body.contains("Reasoning trace")
        }
        let hasToolEntry = viewModel.chatTranscript.contains {
            $0.kind == .tool && $0.body.contains(#""q":"melix""#)
        }
        let userEntry = try #require(viewModel.chatTranscript.first { $0.kind == .user })
        let assistantEntry = try #require(viewModel.chatTranscript.first { $0.kind == .assistant })

        #expect(await client.recordedActions.contains("chat:melix-dev-text"))
        #expect(hasUserEntry)
        #expect(hasAssistantEntry)
        #expect(hasReasoningEntry)
        #expect(hasToolEntry)
        #expect(userEntry.detail.isEmpty)
        #expect(assistantEntry.detail.isEmpty)
        #expect(viewModel.chatStatusText.contains("Completed"))
        #expect(viewModel.lastChatUsageText == "12 prompt • 24 completion")
        #expect(await metrics.snapshot()["menu.chat_submit_ms"] != nil)
        #expect(await metrics.snapshot()["menu.chat_first_delta_ms"] != nil)
        #expect(await metrics.snapshot()["menu.chat_stream_ms"] != nil)
        #expect(await metrics.snapshot()["menu.chat_presentation_lag_ms"] != nil)
        #expect(await metrics.snapshot()["menu.chat_presentation_flush_count"] != nil)
    }

    @Test("chat prompt merges repeated deltas into shared transcript entries")
    @MainActor
    func chatPromptMergesRepeatedDeltasIntoSharedEntries() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureChatEvents([
            .queued(lane: "text.decode.interactive", queuePosition: 0, backpressure: 0),
            .admitted(lane: "text.decode.interactive", workerID: "swift-text-worker", queueDelayMs: 0.5),
            .tokenDelta("Assistant "),
            .tokenDelta("response"),
            .reasoningDelta("Reasoning "),
            .reasoningDelta("trace"),
            .toolCallDelta(callID: "tool-1", toolName: "search", argumentsFragment: ""),
            .toolCallDelta(callID: "tool-1", toolName: "search", argumentsFragment: #"{"q":"melix"}"#),
            .completed(finishReason: "stop", assistantText: "Assistant response", reasoningText: "Reasoning trace"),
        ])
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Merge deltas"

        await viewModel.submitChatPrompt()

        let assistantEntries = viewModel.chatTranscript.filter { $0.kind == .assistant }
        let reasoningEntries = viewModel.chatTranscript.filter { $0.kind == .reasoning }
        let toolEntries = viewModel.chatTranscript.filter { $0.kind == .tool }

        #expect(assistantEntries.count == 1)
        #expect(assistantEntries.first?.body == "Assistant response")
        #expect(reasoningEntries.count == 1)
        #expect(reasoningEntries.first?.body == "Reasoning trace")
        #expect(toolEntries.count == 1)
        #expect(toolEntries.first?.body == #"{"q":"melix"}"#)
    }

    @Test("chat prompt smooths bursty deltas while preserving final transcript fidelity")
    @MainActor
    func chatPromptSmoothsBurstyDeltasWhilePreservingFinalTranscriptFidelity() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureScheduledChatEvents([
            .init(delay: .zero, event: .queued(lane: "text.decode.interactive", queuePosition: 0, backpressure: 0)),
            .init(delay: .zero, event: .admitted(lane: "text.decode.interactive", workerID: "swift-text-worker", queueDelayMs: 0.5)),
            .init(delay: .zero, event: .tokenDelta("Assistant response")),
            .init(delay: .milliseconds(80), event: .completed(
                finishReason: "stop",
                assistantText: "Assistant response",
                reasoningText: ""
            )),
        ])
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Smooth bursty deltas"

        let submitTask = Task { @MainActor in
            await viewModel.submitChatPrompt()
        }

        try await waitForRuntimeViewModelCondition("chat smoothing should present a partial assistant row") {
            viewModel.chatTranscript.contains { entry in
                entry.kind == .assistant && entry.body.isEmpty == false && entry.body != "Assistant response"
            }
        }

        let partialAssistantEntry = try #require(viewModel.chatTranscript.first { $0.kind == .assistant })
        #expect(partialAssistantEntry.body.isEmpty == false)
        #expect(partialAssistantEntry.body != "Assistant response")
        #expect(viewModel.isChatStreaming)

        await submitTask.value

        let finalAssistantEntry = try #require(viewModel.chatTranscript.first { $0.kind == .assistant })
        let metricsSnapshot = await metrics.snapshot()
        #expect(finalAssistantEntry.body == "Assistant response")
        #expect(metricsSnapshot["menu.chat_presentation_lag_ms"] != nil)
        #expect((metricsSnapshot["menu.chat_presentation_flush_count"] ?? 0) > 1)
    }

    @Test("chat prompt creates a transient assistant pending row before the first token")
    @MainActor
    func chatPromptCreatesTransientAssistantPendingRowBeforeFirstToken() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureScheduledChatEvents([
            .init(delay: .milliseconds(120), event: .tokenDelta("Assistant final")),
            .init(delay: .zero, event: .completed(
                finishReason: "stop",
                assistantText: "Assistant final",
                reasoningText: ""
            )),
        ])
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Wait for model"

        let submitTask = Task { @MainActor in
            await viewModel.submitChatPrompt()
        }

        try await waitForRuntimeViewModelCondition("chat should expose a pending assistant row before first token") {
            viewModel.isChatStreaming && viewModel.chatTranscript.contains { entry in
                entry.kind == .assistant && entry.body.isEmpty
            }
        }

        let pendingAssistantEntries = viewModel.chatTranscript.filter { $0.kind == .assistant }
        let persistedPendingAssistantEntries = viewModel.selectedChatSession?.transcript.filter {
            $0.kind == .assistant && $0.body.isEmpty
        } ?? []

        #expect(pendingAssistantEntries.count == 1)
        #expect(pendingAssistantEntries.first?.body.isEmpty == true)
        #expect(persistedPendingAssistantEntries.isEmpty)

        await submitTask.value

        let finalAssistantEntries = viewModel.chatTranscript.filter { $0.kind == .assistant }
        #expect(finalAssistantEntries.count == 1)
        #expect(finalAssistantEntries.first?.body == "Assistant final")
    }

    @Test("chat prompt removes an empty pending assistant row after terminal stream failure")
    @MainActor
    func chatPromptRemovesPendingAssistantAfterTerminalStreamFailure() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureScheduledChatEvents([
            .init(delay: .milliseconds(80), event: .failed(code: "runtime_error", message: "worker failed")),
        ])
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Trigger failure"

        let submitTask = Task { @MainActor in
            await viewModel.submitChatPrompt()
        }

        try await waitForRuntimeViewModelCondition("chat should show pending assistant before failure") {
            viewModel.chatTranscript.contains { entry in
                entry.kind == .assistant && entry.body.isEmpty
            }
        }

        await submitTask.value

        #expect(viewModel.chatTranscript.filter { $0.kind == .assistant }.isEmpty)
        #expect(viewModel.chatTranscript.contains { $0.kind == .error && $0.body == "worker failed" })
        #expect(viewModel.selectedChatSession?.transcript.contains { $0.kind == .assistant && $0.body.isEmpty } == false)
    }

    @Test("chat prompt removes an empty pending assistant row after empty completion")
    @MainActor
    func chatPromptRemovesPendingAssistantAfterEmptyCompletion() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureScheduledChatEvents([
            .init(delay: .milliseconds(80), event: .completed(
                finishReason: "stop",
                assistantText: "",
                reasoningText: ""
            )),
        ])
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Return nothing"

        let submitTask = Task { @MainActor in
            await viewModel.submitChatPrompt()
        }

        try await waitForRuntimeViewModelCondition("chat should show pending assistant before empty completion") {
            viewModel.chatTranscript.contains { entry in
                entry.kind == .assistant && entry.body.isEmpty
            }
        }

        await submitTask.value

        #expect(viewModel.chatTranscript.filter { $0.kind == .assistant }.isEmpty)
        #expect(viewModel.chatStatusText == "Completed • stop")
        #expect(viewModel.selectedChatSession?.transcript.contains { $0.kind == .assistant && $0.body.isEmpty } == false)
    }

    @Test("chat completion can synthesize transcript entries without prior deltas")
    @MainActor
    func chatCompletionSynthesizesTranscriptEntriesWithoutPriorDeltas() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureChatEvents([
            .queued(lane: "text.decode.interactive", queuePosition: 0, backpressure: 0),
            .admitted(lane: "text.decode.interactive", workerID: "swift-text-worker", queueDelayMs: 0.5),
            .completed(finishReason: "stop", assistantText: "Assistant final", reasoningText: "Reasoning final"),
        ])
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Completion only"

        await viewModel.submitChatPrompt()

        let hasAssistantFinal = viewModel.chatTranscript.contains {
            $0.kind == .assistant && $0.body == "Assistant final"
        }
        let hasReasoningFinal = viewModel.chatTranscript.contains {
            $0.kind == .reasoning && $0.body == "Reasoning final"
        }

        #expect(hasAssistantFinal)
        #expect(hasReasoningFinal)
        #expect(viewModel.chatTranscript.filter { $0.kind == .assistant }.count == 1)
        #expect(viewModel.chatStatusText == "Completed • stop")
    }

    @Test("chat prompt records phase transitions and terminal worker failures")
    @MainActor
    func chatPromptRecordsPhaseTransitionsAndWorkerFailures() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureChatEvents([
            .queued(lane: "text.prefill.hot", queuePosition: 1, backpressure: 0.15),
            .admitted(lane: "text.prefill.hot", workerID: "swift-text-worker", queueDelayMs: 1.2),
            .prefillStarted(inputTokens: 64),
            .decodeStarted(decodeHandle: "decode-hot-1", maxOutputTokens: 96),
            .heartbeat,
            .failed(code: "runtime_error", message: "worker failed"),
        ])
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Diagnose runtime phases"

        await viewModel.submitChatPrompt()

        let hasErrorEntry = viewModel.chatTranscript.contains {
            $0.kind == .error && $0.body == "worker failed"
        }

        #expect(viewModel.lastChatRequestID == "chat-request-1")
        #expect(viewModel.chatStatusText == "Failed • runtime_error")
        #expect(viewModel.lastError == "worker failed")
        #expect(viewModel.isChatStreaming == false)
        #expect(hasErrorEntry)
    }

    @Test("chat transport failures surface local error rows and reset streaming state")
    @MainActor
    func chatTransportFailuresSurfaceLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(chat: MenuBarTestError(description: "chat transport failed"))
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        try bindSelectedChatSessionToPrimaryServer(viewModel)
        viewModel.chatComposerText = "Diagnose transport"

        await viewModel.submitChatPrompt()

        let hasTransportErrorEntry = viewModel.chatTranscript.contains {
            $0.kind == .error && $0.body.contains("chat transport failed")
        }

        #expect(viewModel.chatStatusText == "Failed")
        #expect(viewModel.lastError?.contains("chat transport failed") == true)
        #expect(viewModel.isChatStreaming == false)
        #expect(hasTransportErrorEntry)
    }

    @Test("chat route readiness reflects multimodal model availability from the snapshot")
    @MainActor
    func chatRouteReadinessReflectsMultimodalAvailability() async throws {
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeCapabilityModelSummary(modelID: "melix-dev-ocr", kind: "ocr", state: .modelWarm, features: ["ocr"]),
                makeCapabilityModelSummary(modelID: "melix-dev-vlm", kind: "vlm", state: .modelDiscovered, features: ["vlm", "vision"]),
                makeCapabilityModelSummary(modelID: "melix-dev-transcription", kind: "transcription", state: .modelWarm, features: ["audio", "transcription"]),
                makeCapabilityModelSummary(modelID: "melix-dev-speech", kind: "speech", state: .modelDiscovered, features: ["audio", "speech"]),
            ]
        )
        snapshot.metrics.values["http.translation_ms"] = 4.2
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        let hasReadyTextCapability = viewModel.chatCapabilities.contains { $0.id == "text" && $0.isReady }
        let hasReadyOCRCapability = viewModel.chatCapabilities.contains { $0.id == "ocr" && $0.isReady }
        let hasPendingVLMBinding = viewModel.chatCapabilities.contains { $0.id == "vlm" && $0.isReady == false }
        let hasReadyTranscriptionCapability = viewModel.chatCapabilities.contains { $0.id == "transcription" && $0.isReady }
        let hasPendingSpeechCapability = viewModel.chatCapabilities.contains { $0.id == "speech" && $0.isReady == false }
        #expect(hasReadyTextCapability)
        #expect(hasReadyOCRCapability)
        #expect(hasPendingVLMBinding)
        #expect(hasReadyTranscriptionCapability)
        #expect(hasPendingSpeechCapability)
    }

    @Test("image snapshot hydrates image panel state from control-plane truth")
    @MainActor
    func imageSnapshotHydratesImagePanelState() async throws {
        let artifact = makeMenuBarImageArtifact(
            jobID: "job-image-1",
            storageURI: "/tmp/melix-image-preview.png"
        )
        let imageJob = makeMenuBarImageJobSummary(
            jobID: "job-image-1",
            requestID: "req-image-1",
            operation: "image_generate",
            artifacts: [artifact]
        )
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        snapshot.imageJobs = [imageJob]
        let client = SnapshotControlPlaneXPCClient(snapshot: snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        #expect(viewModel.selectedImageModelID == "melix-dev-image")
        #expect(viewModel.imageJobs.count == 1)
        #expect(viewModel.selectedImageJobID == "job-image-1")
        #expect(viewModel.selectedImageJob?.operation == "image_generate")
        #expect(viewModel.selectedImageJob?.artifacts.first?.storageUri == "/tmp/melix-image-preview.png")
    }

    @Test("image picker filters models by workflow role and keeps separate selections")
    @MainActor
    func imagePickerFiltersModelsByWorkflowRoleAndKeepsSeparateSelections() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeMenuBarImageModelSummary(
                        modelID: "melix-qwen-image",
                        familyID: "qwenimage-v1",
                        supportsGeneration: true,
                        supportsEdit: false
                    ),
                    makeMenuBarImageModelSummary(
                        modelID: "melix-fill-image",
                        familyID: "fill-v1",
                        supportsGeneration: false,
                        supportsEdit: true
                    ),
                    makeMenuBarImageModelSummary(
                        modelID: "melix-kontext-image",
                        familyID: "kontext-v1",
                        supportsGeneration: true,
                        supportsEdit: true
                    ),
                ]
            )
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        #expect(viewModel.imageModels(for: .generate).map(\.modelID) == ["melix-kontext-image", "melix-qwen-image"])
        #expect(viewModel.imageModels(for: .edit).map(\.modelID) == ["melix-fill-image", "melix-kontext-image"])
        #expect(viewModel.selectedImageModelID(for: .generate) == "melix-kontext-image")
        #expect(viewModel.selectedImageModelID(for: .edit) == "melix-fill-image")

        viewModel.setSelectedImageModelID("melix-qwen-image", for: .generate)
        viewModel.setSelectedImageModelID("melix-kontext-image", for: .edit)

        #expect(viewModel.selectedImageModelID(for: .generate) == "melix-qwen-image")
        #expect(viewModel.selectedImageModelID(for: .edit) == "melix-kontext-image")
        #expect(viewModel.selectedImageModelID == "melix-qwen-image")
    }

    @Test("image defaults snapshot hydrates requested and effective control state")
    @MainActor
    func imageDefaultsSnapshotHydratesRequestedAndEffectiveState() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeMenuBarImageModelSummary(
                    modelID: "melix-qwen-image",
                    familyID: "qwenimage-v1",
                    supportsGeneration: true,
                    supportsEdit: false
                ),
                makeMenuBarImageModelSummary(
                    modelID: "melix-fill-image",
                    familyID: "fill-v1",
                    supportsGeneration: false,
                    supportsEdit: true
                ),
            ]
        )
        var defaults = Melix_Controlplane_V1_ImageDefaultsSummary()
        defaults.requestedGenerateModelID = "melix-qwen-image"
        defaults.requestedEditModelID = "melix-fill-image"
        defaults.requestedSize = "1536x1024"
        defaults.requestedSteps = 40
        defaults.requestedGuidance = 6.5
        defaults.requestedStrength = 0.75
        defaults.requestedNegativePrompt = "grain"
        defaults.effectiveGenerateModelID = "melix-qwen-image"
        defaults.effectiveEditModelID = "melix-fill-image"
        defaults.effectiveSize = "1024x1024"
        defaults.effectiveSteps = 32
        defaults.effectiveGuidance = 7
        defaults.effectiveStrength = 0.6
        defaults.effectiveNegativePrompt = "grain"
        defaults.requestTimeoutSeconds = 900
        defaults.source = .operatorOverride
        defaults.updatedAtUnixMs = 1_717_171_717_000
        snapshot.imageDefaults = defaults
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        #expect(viewModel.selectedImageModelID(for: .generate) == "melix-qwen-image")
        #expect(viewModel.selectedImageModelID(for: .edit) == "melix-fill-image")
        #expect(viewModel.imageSize == "1536x1024")
        #expect(viewModel.imageSteps == "40")
        #expect(viewModel.imageGuidance == "6.5")
        #expect(viewModel.imageStrength == "0.75")
        #expect(viewModel.imageNegativePrompt == "grain")
        #expect(viewModel.imageDefaultsSourceText == "Operator Override")
        #expect(viewModel.effectiveImageGenerateModelID == "melix-qwen-image")
        #expect(viewModel.effectiveImageEditModelID == "melix-fill-image")
        #expect(viewModel.effectiveImageSize == "1024x1024")
        #expect(viewModel.effectiveImageSteps == "32")
        #expect(viewModel.effectiveImageGuidance == "7")
        #expect(viewModel.effectiveImageStrength == "0.6")
        #expect(viewModel.effectiveImageNegativePrompt == "grain")
        #expect(viewModel.imageRequestTimeoutSeconds == 900)
        #expect(viewModel.imageTimeoutPolicyText == "15-minute creative workflow deadline")
    }

    @Test("image defaults apply forwards typed defaults and projects hydrated summary")
    @MainActor
    func imageDefaultsApplyForwardsTypedDefaultsAndProjectsHydratedSummary() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeMenuBarImageModelSummary(
                        modelID: "melix-qwen-image",
                        familyID: "qwenimage-v1",
                        supportsGeneration: true,
                        supportsEdit: false
                    ),
                    makeMenuBarImageModelSummary(
                        modelID: "melix-fill-image",
                        familyID: "fill-v1",
                        supportsGeneration: false,
                        supportsEdit: true
                    ),
                ]
            )
        )
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        viewModel.setSelectedImageModelID("melix-qwen-image", for: .generate)
        viewModel.setSelectedImageModelID("melix-fill-image", for: .edit)
        viewModel.imageSize = "1536x1024"
        viewModel.imageSteps = "40"
        viewModel.imageGuidance = "6.25"
        viewModel.imageStrength = "0.7"
        viewModel.imageNegativePrompt = "noise"

        await viewModel.applyImageDefaults()

        let request = try #require(await client.recordedImageDefaultsApplyRequests.last)
        #expect(request.generateModelID == "melix-qwen-image")
        #expect(request.editModelID == "melix-fill-image")
        #expect(request.size == "1536x1024")
        #expect(request.steps == 40)
        #expect(request.guidance == 6.25)
        #expect(request.strength == 0.7)
        #expect(request.negativePrompt == "noise")
        #expect(viewModel.imageDefaultsSourceText == "Operator Override")
        #expect(viewModel.effectiveImageGenerateModelID == "melix-qwen-image")
        #expect(viewModel.effectiveImageEditModelID == "melix-fill-image")
        #expect(viewModel.effectiveImageSize == "1536x1024")
        #expect(viewModel.effectiveImageSteps == "40")
        #expect(viewModel.effectiveImageGuidance == "6.25")
        #expect(viewModel.effectiveImageStrength == "0.7")
        #expect(viewModel.effectiveImageNegativePrompt == "noise")
        #expect(await metrics.snapshot()["desktop.image_defaults_apply_ms"] != nil)
    }

    @Test("desktop image workspace body evaluates role-aware picker and summary branches")
    @MainActor
    func desktopImageWorkspaceBodyEvaluatesRoleAwarePickerAndSummaryBranches() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeMenuBarImageModelSummary(
                        modelID: "melix-fill-image",
                        familyID: "fill-v1",
                        supportsGeneration: false,
                        supportsEdit: true
                    ),
                    makeMenuBarImageModelSummary(
                        modelID: "melix-kontext-image",
                        familyID: "kontext-v1",
                        supportsGeneration: true,
                        supportsEdit: true
                    ),
                ]
            )
        )
        let viewModel = RuntimeViewModel(client: client)
        await viewModel.start()
        viewModel.imagePromptText = "Generate a poster"
        viewModel.imageEditSourceURL = "file:///tmp/source.png"
        viewModel.setSelectedImageModelID("melix-kontext-image", for: .generate)
        viewModel.setSelectedImageModelID("melix-kontext-image", for: .edit)

        var generateMode = DesktopImageWorkspaceMode.generate
        var editMode = DesktopImageWorkspaceMode.edit
        var showsSidebar = true
        var showsInspector = true
        let generateWorkspace = DesktopImageWorkspace(
            viewModel: viewModel,
            selectedMode: Binding(
                get: { generateMode },
                set: { generateMode = $0 }
            ),
            showsSidebar: Binding(
                get: { showsSidebar },
                set: { showsSidebar = $0 }
            ),
            showsInspector: Binding(
                get: { showsInspector },
                set: { showsInspector = $0 }
            )
        )
        let editWorkspace = DesktopImageWorkspace(
            viewModel: viewModel,
            selectedMode: Binding(
                get: { editMode },
                set: { editMode = $0 }
            ),
            showsSidebar: Binding(
                get: { showsSidebar },
                set: { showsSidebar = $0 }
            ),
            showsInspector: Binding(
                get: { showsInspector },
                set: { showsInspector = $0 }
            )
        )

        let generateBody = generateWorkspace.body
        let editBody = editWorkspace.body

        #expect(String(describing: type(of: generateBody)).isEmpty == false)
        #expect(String(describing: type(of: editBody)).isEmpty == false)
    }

    @Test("image generate and edit actions dispatch through the client and update runtime state")
    @MainActor
    func imageActionsDispatchThroughClientAndUpdateRuntimeState() async throws {
        let client = FakeControlPlaneXPCClient()
        let snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        await client.configureSnapshot(snapshot)
        await client.configureImageResponses(
            generation: makeMenuBarImageJobSummary(
                jobID: "job-image-generate",
                requestID: "req-image-generate",
                operation: "image_generate",
                artifacts: [makeMenuBarImageArtifact(jobID: "job-image-generate")]
            ),
            edit: makeMenuBarImageJobSummary(
                jobID: "job-image-edit",
                requestID: "req-image-edit",
                operation: "image_edit",
                artifacts: [
                    makeMenuBarImageArtifact(jobID: "job-image-edit", role: .imageArtifactEditSource, storageURI: "/tmp/source.png"),
                    makeMenuBarImageArtifact(jobID: "job-image-edit", role: .imageArtifactGenerated, storageURI: "/tmp/output.png"),
                ]
            )
        )
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        viewModel.imagePromptText = "Generate a poster"
        viewModel.imageSteps = "36"
        viewModel.imageGuidance = "6.75"
        viewModel.imageNegativePrompt = "blur"
        await viewModel.submitImageGeneration()

        let generateRequest = try #require(await client.recordedImageGenerateRequests.last)
        #expect(await client.recordedActions.contains("image.generate:melix-dev-image"))
        #expect(generateRequest.steps == 36)
        #expect(generateRequest.guidance == 6.75)
        #expect(generateRequest.negativePrompt == "blur")
        #expect(viewModel.imageStatusText == "Completed • image_generate")
        #expect(viewModel.imageJobs.contains(where: { $0.jobID == "job-image-generate" }))
        #expect(await metrics.snapshot()["desktop.image_action_latency_ms"] != nil)

        viewModel.imagePromptText = "Edit the poster"
        viewModel.imageEditSourceURL = "file:///tmp/source.png"
        viewModel.imageEditMaskURL = "file:///tmp/mask.png"
        viewModel.imageStrength = "0.45"
        viewModel.imageSteps = "28"
        viewModel.imageGuidance = "5.5"
        viewModel.imageNegativePrompt = "washed out"
        await viewModel.submitImageEdit()

        let editRequest = try #require(await client.recordedImageEditRequests.last)
        #expect(await client.recordedActions.contains("image.edit:melix-dev-image"))
        #expect(editRequest.strength == 0.45)
        #expect(editRequest.steps == 28)
        #expect(editRequest.guidance == 5.5)
        #expect(editRequest.negativePrompt == "washed out")
        #expect(viewModel.imageJobs.contains(where: { $0.jobID == "job-image-edit" }))
        #expect(viewModel.selectedImageJob?.artifacts.contains(where: { $0.storageUri == "/tmp/output.png" }) == true)
    }

    @Test("image actions use workflow-specific model selections")
    @MainActor
    func imageActionsUseWorkflowSpecificModelSelections() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [
                    makeMenuBarImageModelSummary(
                        modelID: "melix-qwen-image",
                        familyID: "qwenimage-v1",
                        supportsGeneration: true,
                        supportsEdit: false
                    ),
                    makeMenuBarImageModelSummary(
                        modelID: "melix-fill-image",
                        familyID: "fill-v1",
                        supportsGeneration: false,
                        supportsEdit: true
                    ),
                ]
            )
        )
        await client.configureImageResponses(
            generation: makeMenuBarImageJobSummary(
                jobID: "job-image-generate",
                requestID: "req-image-generate",
                operation: "image_generate",
                artifacts: [makeMenuBarImageArtifact(jobID: "job-image-generate")]
            ),
            edit: makeMenuBarImageJobSummary(
                jobID: "job-image-edit",
                requestID: "req-image-edit",
                operation: "image_edit",
                artifacts: [makeMenuBarImageArtifact(jobID: "job-image-edit")]
            )
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.imagePromptText = "Generate a poster"
        await viewModel.submitImageGeneration()

        viewModel.imagePromptText = "Edit the poster"
        viewModel.imageEditSourceURL = "file:///tmp/source.png"
        await viewModel.submitImageEdit()

        #expect(await client.recordedActions.contains("image.generate:melix-qwen-image"))
        #expect(await client.recordedActions.contains("image.edit:melix-fill-image"))
    }

    @Test("redo selected image job reconstructs generation parameters from persisted recipe")
    @MainActor
    func redoSelectedImageJobReconstructsGenerationRecipe() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeMenuBarImageModelSummary()]
        )
        var recipe = Melix_Controlplane_V1_ImageJobRecipeSummary()
        recipe.prompt = "Redo this cover"
        recipe.size = "1536x1024"
        recipe.steps = 48
        recipe.guidance = 6.25
        recipe.negativePrompt = "artifacts"
        recipe.variantCount = 2
        recipe.responseFormat = "png"
        recipe.artifactNamespace = "melix.image.demo"
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-redo-generate",
                requestID: "req-image-redo-generate",
                operation: "image_generate",
                recipe: recipe
            ),
        ]
        await client.configureSnapshot(snapshot)
        await client.configureImageResponses(
            generation: makeMenuBarImageJobSummary(
                jobID: "job-image-redo-generate-2",
                requestID: "req-image-redo-generate-2",
                operation: "image_generate",
                artifacts: [makeMenuBarImageArtifact(jobID: "job-image-redo-generate-2")]
            )
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        await viewModel.redoSelectedImageJob()

        let request = try #require(await client.recordedImageGenerateRequests.last)
        #expect(request.prompt == "Redo this cover")
        #expect(request.size == "1536x1024")
        #expect(request.steps == 48)
        #expect(request.guidance == 6.25)
        #expect(request.negativePrompt == "artifacts")
        #expect(request.n == 2)
        #expect(request.responseFormat == "png")
        #expect(request.artifactNamespace == "melix.image.demo")
    }

    @Test("reiterate preparation seeds iterate state from the selected image job and dispatches iterate edits")
    @MainActor
    func prepareReiterateSeedsIterateStateAndDispatchesEdit() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeMenuBarImageModelSummary()]
        )
        let generatedArtifact = makeMenuBarImageArtifact(
            jobID: "job-image-iterate-source",
            role: .imageArtifactGenerated,
            storageURI: "/tmp/generated.png"
        )
        var recipe = Melix_Controlplane_V1_ImageJobRecipeSummary()
        recipe.prompt = "Base prompt"
        recipe.size = "1024x1024"
        recipe.steps = 36
        recipe.guidance = 5.5
        recipe.strength = 0.45
        recipe.negativePrompt = "noise"
        recipe.variantCount = 1
        recipe.responseFormat = "png"
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-iterate-source",
                requestID: "req-image-iterate-source",
                operation: "image_edit",
                artifacts: [generatedArtifact],
                recipe: recipe,
                timeoutSeconds: 600,
                sourceArtifactID: "artifact-origin",
                promptDelta: "make it brighter",
                editMode: .iterate
            ),
        ]
        await client.configureSnapshot(snapshot)
        await client.configureImageResponses(
            edit: makeMenuBarImageJobSummary(
                jobID: "job-image-iterate-dispatch",
                requestID: "req-image-iterate-dispatch",
                operation: "image_iterate",
                artifacts: [makeMenuBarImageArtifact(jobID: "job-image-iterate-dispatch")]
            )
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.prepareReiterateFromSelectedImageJob()

        #expect(viewModel.imageEditMode == .iterate)
        #expect(viewModel.imageEditSourceArtifactID == generatedArtifact.artifactID)
        #expect(viewModel.imageEditSourceURL.isEmpty)
        #expect(viewModel.imagePromptText.isEmpty)
        #expect(viewModel.imageSteps == "36")
        #expect(viewModel.imageGuidance == "5.5")
        #expect(viewModel.imageStrength == "0.45")
        #expect(viewModel.imageNegativePrompt == "noise")
        #expect(viewModel.imageStatusText == "Iterate draft seeded")
        #expect(viewModel.selectedImageJobTimeoutText == "10-minute deadline")

        viewModel.imagePromptText = "push the contrast further"
        await viewModel.submitImageEdit()

        let request = try #require(await client.recordedImageEditRequests.last)
        #expect(request.sourceArtifactID == generatedArtifact.artifactID)
        #expect(request.imageURL.isEmpty)
        #expect(request.prompt.isEmpty)
        #expect(request.promptDelta == "push the contrast further")
        #expect(request.mode == .iterate)
        #expect(request.strength == 0.45)
    }

    @Test("timed out image jobs surface explicit timeout status text")
    @MainActor
    func timedOutImageJobsSurfaceExplicitStatusText() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeMenuBarImageModelSummary()]
            )
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        var timedOutError = Melix_Controlplane_V1_ErrorStatus()
        timedOutError.code = "deadline_exceeded"
        timedOutError.message = "Image request exceeded the 600-second creative workflow deadline."

        let timedOutJob = makeMenuBarImageJobSummary(
            jobID: "job-image-timeout",
            requestID: "req-image-timeout",
            operation: "image_generate",
            state: .imageJobFailed,
            timeoutSeconds: 600,
            error: timedOutError
        )
        await client.sendImageJobStateChanged(timedOutJob)

        try await waitForRuntimeViewModelCondition("expected timed out image job to appear") {
            viewModel.selectedImageJob?.jobID == "job-image-timeout"
        }

        #expect(viewModel.imageStatusText == "Timed Out • image_generate")
        #expect(viewModel.selectedImageJobTimeoutText == "Timed out • 10-minute deadline")
    }

    @Test("runtime image edit mode exposes typed identifiers titles and control-plane mapping")
    func runtimeImageEditModeExposesTypedIdentifiersTitlesAndControlPlaneMapping() {
        let expectations: [(RuntimeImageEditMode, String, String, ControlPlaneImageEditRequest.Mode)] = [
            (.edit, "edit", "Edit", .edit),
            (.variation, "variation", "Variation", .variation),
            (.iterate, "iterate", "Iterate", .iterate),
        ]

        for (mode, expectedID, expectedTitle, expectedControlPlaneMode) in expectations {
            #expect(mode.id == expectedID)
            #expect(mode.title == expectedTitle)
            #expect(mode.controlPlaneMode == expectedControlPlaneMode)
        }
    }

    @Test("image timeout text falls back to second-based policy text when no job is selected")
    @MainActor
    func imageTimeoutTextFallsBackToSecondBasedPolicyTextWhenNoJobIsSelected() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeMenuBarImageModelSummary()]
        )
        snapshot.imageDefaults.requestTimeoutSeconds = 75
        snapshot.imageDefaults.source = .operatorOverride
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        #expect(viewModel.selectedImageJob == nil)
        #expect(viewModel.imageTimeoutPolicyText == "75-second creative workflow deadline")
        #expect(viewModel.selectedImageJobTimeoutText == "75-second creative workflow deadline")
    }

    @Test("image source artifact summary resolves matching artifacts and raw fallback text")
    @MainActor
    func imageSourceArtifactSummaryResolvesMatchingArtifactsAndRawFallbackText() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeMenuBarImageModelSummary()]
        )
        var sourceArtifact = makeMenuBarImageArtifact(
            jobID: "job-image-source-summary",
            role: .imageArtifactGenerated,
            storageURI: "/tmp/generated-source.png"
        )
        sourceArtifact.artifactID = "artifact-source-summary"
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-source-summary",
                requestID: "req-image-source-summary",
                operation: "image_edit",
                artifacts: [sourceArtifact]
            ),
        ]
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.imageEditSourceArtifactID = "artifact-source-summary"
        #expect(viewModel.imageEditSourceArtifactSummaryText == "artifact-source-summary • /tmp/generated-source.png")

        viewModel.imageEditSourceArtifactID = "artifact-missing"
        #expect(viewModel.imageEditSourceArtifactSummaryText == "artifact-missing")

        viewModel.imageEditSourceArtifactID = "   "
        #expect(viewModel.imageEditSourceArtifactSummaryText == nil)
    }

    @Test("image edit validation enforces source artifact prompt delta and strength bounds")
    @MainActor
    func imageEditValidationEnforcesSourceArtifactPromptDeltaAndStrengthBounds() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureSnapshot(
            makeSnapshot(
                serverState: .serverReady,
                models: [makeMenuBarImageModelSummary()]
            )
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.imagePromptText = "Edit the scene"
        viewModel.imageStrength = "0.5"
        viewModel.imageEditMode = .variation
        viewModel.imageEditSourceURL = "file:///tmp/source.png"

        await viewModel.submitImageEdit()
        #expect(viewModel.imageStatusText == "Failed")
        #expect(viewModel.lastError?.contains("source artifact") == true)
        #expect(await client.recordedImageEditRequests.isEmpty)

        viewModel.imageEditMode = .iterate
        viewModel.imageEditSourceArtifactID = "artifact-source"
        viewModel.imageEditSourceURL = ""
        viewModel.imagePromptText = "   "
        viewModel.imageStrength = "0.5"

        await viewModel.submitImageEdit()
        #expect(viewModel.lastError?.contains("prompt delta") == true)
        #expect(await client.recordedImageEditRequests.isEmpty)

        viewModel.imageEditMode = .edit
        viewModel.imageEditSourceArtifactID = ""
        viewModel.imageEditSourceURL = "file:///tmp/source.png"
        viewModel.imagePromptText = "Adjust the contrast"
        viewModel.imageStrength = "1.25"

        await viewModel.submitImageEdit()
        #expect(viewModel.lastError?.contains("between 0 and 1") == true)
        #expect(await client.recordedImageEditRequests.isEmpty)
    }

    @Test("redo selected image edit reconstructs direct and fallback lineage branches across edit modes")
    @MainActor
    func redoSelectedImageEditReconstructsDirectAndFallbackLineageBranchesAcrossEditModes() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeMenuBarImageModelSummary()]
        )

        var editRecipe = Melix_Controlplane_V1_ImageJobRecipeSummary()
        editRecipe.prompt = "Replace the sky"
        var editSourceArtifact = makeMenuBarImageArtifact(
            jobID: "job-image-redo-edit",
            role: .imageArtifactEditSource,
            storageURI: "/tmp/edit-source.png"
        )
        editSourceArtifact.artifactID = "artifact-edit-source"
        var editMaskArtifact = makeMenuBarImageArtifact(
            jobID: "job-image-redo-edit",
            role: .imageArtifactMask,
            storageURI: "/tmp/edit-mask.png"
        )
        editMaskArtifact.artifactID = "artifact-edit-mask"

        var variationRecipe = Melix_Controlplane_V1_ImageJobRecipeSummary()
        variationRecipe.prompt = "Keep the composition"
        variationRecipe.sourceImageUri = "file:///tmp/direct-variation-source.png"
        variationRecipe.maskUri = "file:///tmp/direct-variation-mask.png"
        variationRecipe.size = "2048x1024"

        var iterateRecipe = Melix_Controlplane_V1_ImageJobRecipeSummary()
        iterateRecipe.prompt = "Make it warmer"
        iterateRecipe.maskUri = "file:///tmp/direct-iterate-mask.png"

        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-redo-edit",
                requestID: "req-image-redo-edit",
                operation: "image_edit",
                artifacts: [editSourceArtifact, editMaskArtifact],
                recipe: editRecipe,
                editMode: .edit
            ),
            makeMenuBarImageJobSummary(
                jobID: "job-image-redo-variation",
                requestID: "req-image-redo-variation",
                operation: "image_edit",
                recipe: variationRecipe,
                editMode: .variation
            ),
            makeMenuBarImageJobSummary(
                jobID: "job-image-redo-iterate",
                requestID: "req-image-redo-iterate",
                operation: "image_edit",
                recipe: iterateRecipe,
                sourceArtifactID: "artifact-iterate-source",
                promptDelta: "   ",
                editMode: .iterate
            ),
        ]
        await client.configureSnapshot(snapshot)
        await client.configureImageResponses(
            edit: makeMenuBarImageJobSummary(
                jobID: "job-image-redo-edit-dispatched",
                requestID: "req-image-redo-edit-dispatched",
                operation: "image_edit",
                artifacts: [makeMenuBarImageArtifact(jobID: "job-image-redo-edit-dispatched")]
            )
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        viewModel.selectImageJob(jobID: "job-image-redo-edit")
        await viewModel.redoSelectedImageJob()
        let editRequest = try #require(await client.recordedImageEditRequests.last)
        #expect(editRequest.mode == .edit)
        #expect(editRequest.imageURL == "/tmp/edit-source.png")
        #expect(editRequest.maskURL == "/tmp/edit-mask.png")
        #expect(editRequest.prompt == "Replace the sky")
        #expect(editRequest.sourceArtifactID.isEmpty)
        #expect(editRequest.strength == 1)
        #expect(editRequest.size == "1024x1024")
        #expect(editRequest.responseFormat == "png")

        viewModel.selectImageJob(jobID: "job-image-redo-variation")
        await viewModel.redoSelectedImageJob()
        let variationRequest = try #require(await client.recordedImageEditRequests.last)
        #expect(variationRequest.mode == .variation)
        #expect(variationRequest.imageURL == "file:///tmp/direct-variation-source.png")
        #expect(variationRequest.maskURL == "file:///tmp/direct-variation-mask.png")
        #expect(variationRequest.prompt == "Keep the composition")
        #expect(variationRequest.size == "2048x1024")

        viewModel.selectImageJob(jobID: "job-image-redo-iterate")
        await viewModel.redoSelectedImageJob()
        let iterateRequest = try #require(await client.recordedImageEditRequests.last)
        #expect(iterateRequest.mode == .iterate)
        #expect(iterateRequest.sourceArtifactID == "artifact-iterate-source")
        #expect(iterateRequest.imageURL.isEmpty)
        #expect(iterateRequest.maskURL == "file:///tmp/direct-iterate-mask.png")
        #expect(iterateRequest.prompt.isEmpty)
        #expect(iterateRequest.promptDelta == "Make it warmer")
    }

    @Test("redo and reiterate no-op branches preserve state and image generation load failures surface local errors")
    @MainActor
    func redoAndReiterateNoOpBranchesPreserveStateAndImageGenerationLoadFailuresSurfaceLocalErrors() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [makeMenuBarImageModelSummary()]
        )
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-running-no-redo",
                requestID: "req-image-running-no-redo",
                operation: "image_edit",
                state: .imageJobRunning
            ),
            makeMenuBarImageJobSummary(
                jobID: "job-image-no-generated-artifact",
                requestID: "req-image-no-generated-artifact",
                operation: "image_edit",
                artifacts: [
                    makeMenuBarImageArtifact(
                        jobID: "job-image-no-generated-artifact",
                        role: .imageArtifactEditSource,
                        storageURI: "/tmp/source-only.png"
                    )
                ]
            ),
        ]
        await client.configureSnapshot(snapshot)
        await client.configureErrors(
            imageGenerate: NSError(
                domain: "MenuBarTests",
                code: 17,
                userInfo: [NSLocalizedDescriptionKey: "synthetic generate failure"]
            )
        )
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()
        viewModel.selectImageJob(jobID: "job-image-running-no-redo")
        await viewModel.redoSelectedImageJob()
        #expect(await client.recordedImageGenerateRequests.isEmpty)
        #expect(await client.recordedImageEditRequests.isEmpty)

        viewModel.selectImageJob(jobID: "job-image-no-generated-artifact")
        viewModel.imageEditMode = .edit
        let priorMode = viewModel.imageEditMode
        let priorArtifactID = viewModel.imageEditSourceArtifactID
        viewModel.prepareReiterateFromSelectedImageJob()
        #expect(viewModel.imageEditMode == priorMode)
        #expect(viewModel.imageEditSourceArtifactID == priorArtifactID)

        viewModel.imagePromptText = "Draw a failure case"
        await viewModel.submitImageGeneration()
        #expect(await client.recordedActions.contains("image.generate:melix-dev-image"))
        #expect(viewModel.imageStatusText == "Failed")
        #expect(viewModel.lastError?.contains("synthetic generate failure") == true)
    }

    @Test("image cancel action dispatches through the client and records cancel latency")
    @MainActor
    func imageCancelActionDispatchesThroughClient() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-live",
                requestID: "req-image-live",
                operation: "image_generate",
                state: .imageJobRunning
            ),
        ]
        await client.configureSnapshot(snapshot)
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.cancelSelectedImageJob()

        #expect(await client.recordedActions.contains("cancel:req-image-live"))
        #expect(viewModel.imageStatusText == "Canceling")
        #expect(await metrics.snapshot()["desktop.image_cancel_latency_ms"] != nil)
    }

    @Test("image cancel action is a no-op for non-cancelable jobs")
    @MainActor
    func imageCancelActionNoopsForNonCancelableJobs() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-complete",
                requestID: "req-image-complete",
                operation: "image_generate",
                state: .imageJobCompleted
            ),
        ]
        await client.configureSnapshot(snapshot)
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        let initialStatus = viewModel.imageStatusText
        await viewModel.cancelSelectedImageJob()

        #expect(await client.recordedActions.contains("cancel:req-image-complete") == false)
        #expect(viewModel.imageStatusText == initialStatus)
        #expect(await metrics.snapshot()["desktop.image_cancel_latency_ms"] == nil)
    }

    @Test("image cancel action surfaces client failures")
    @MainActor
    func imageCancelActionSurfacesClientFailures() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        snapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-failing-cancel",
                requestID: "req-image-failing-cancel",
                operation: "image_generate",
                state: .imageJobRunning
            ),
        ]
        await client.configureSnapshot(snapshot)
        await client.configureErrors(cancel: MenuBarTestError(description: "cancel failed"))
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        await viewModel.cancelSelectedImageJob()

        #expect(await client.recordedActions.contains("cancel:req-image-failing-cancel"))
        #expect(viewModel.imageStatusText == "Failed")
        #expect(viewModel.lastError?.contains("cancel failed") == true)
        #expect(await metrics.snapshot()["desktop.image_cancel_latency_ms"] == nil)
    }

    @Test("image job events refresh selected job progress and terminal state")
    @MainActor
    func imageJobEventsRefreshSelectedJobProgressAndTerminalState() async throws {
        let client = FakeControlPlaneXPCClient()
        var snapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        snapshot.imageJobs = []
        await client.configureSnapshot(snapshot)
        let viewModel = RuntimeViewModel(client: client)

        await viewModel.start()

        var runningJob = makeMenuBarImageJobSummary(
            jobID: "job-image-live",
            requestID: "req-image-live",
            operation: "image_generate",
            state: .imageJobRunning
        )
        runningJob.progress.stage = "sampling"
        runningJob.progress.pct = 0.5
        await client.sendImageJobStateChanged(runningJob)

        try await waitForRuntimeViewModelCondition("expected running image job to appear") {
            viewModel.imageJobs.contains(where: { $0.jobID == "job-image-live" })
        }

        #expect(viewModel.imageStatusText == "Running • image_generate")

        var completedJob = runningJob
        completedJob.state = .imageJobCompleted
        completedJob.progress.stage = "completed"
        completedJob.progress.pct = 1
        completedJob.artifacts = [makeMenuBarImageArtifact(jobID: "job-image-live", storageURI: "/tmp/live-output.png")]
        await client.sendImageJobStateChanged(completedJob)

        try await waitForRuntimeViewModelCondition("expected completed image job artifact") {
            viewModel.selectedImageJob?.artifacts.contains(where: { $0.storageUri == "/tmp/live-output.png" }) == true
        }

        #expect(viewModel.imageStatusText == "Completed • image_generate")
    }

    @Test("image edit requires a source URL before dispatch")
    @MainActor
    func imageEditRequiresASourceURLBeforeDispatch() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        viewModel.imagePromptText = "Edit the skyline"
        await viewModel.submitImageEdit()

        #expect(viewModel.imageStatusText == "Failed")
        #expect(viewModel.lastError == "Image edit source is required.")
        #expect(await client.recordedActions.contains("image.edit:melix-dev-image") == false)
        #expect(await metrics.snapshot()["desktop.image_action_latency_ms"] == nil)
    }

    @Test("image edit surfaces client failures")
    @MainActor
    func imageEditSurfacesClientFailures() async throws {
        let client = FakeControlPlaneXPCClient()
        await client.configureErrors(imageEdit: MenuBarTestError(description: "edit failed"))
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()
        viewModel.imagePromptText = "Edit the skyline"
        viewModel.imageEditSourceURL = "file:///tmp/source.png"

        await viewModel.submitImageEdit()

        #expect(await client.recordedActions.contains("image.edit:melix-dev-image"))
        #expect(viewModel.imageStatusText == "Failed")
        #expect(viewModel.lastError?.contains("edit failed") == true)
        #expect(await metrics.snapshot()["desktop.image_action_latency_ms"] == nil)
    }

    @Test("desktop foundation refresh records image refresh latency when image jobs are present")
    @MainActor
    func desktopFoundationRefreshRecordsImageRefreshLatency() async throws {
        let client = FakeControlPlaneXPCClient()
        let metrics = MenuBarMetricsStore()
        let viewModel = RuntimeViewModel(client: client, metrics: metrics)

        await viewModel.start()

        var refreshedSnapshot = makeSnapshot(
            serverState: .serverReady,
            models: [
                makeModelSummary(modelID: "melix-dev-text", state: .modelWarm),
                makeMenuBarImageModelSummary(),
            ]
        )
        refreshedSnapshot.imageJobs = [
            makeMenuBarImageJobSummary(
                jobID: "job-image-refresh",
                requestID: "req-image-refresh",
                operation: "image_generate",
                state: .imageJobRunning
            ),
        ]
        await client.configureSnapshot(refreshedSnapshot)

        await viewModel.refreshDesktopFoundation()

        #expect(await metrics.snapshot()["menu.foundation_refresh_ms"] != nil)
        #expect(await metrics.snapshot()["desktop.image_refresh_ms"] != nil)
    }

    @Test("runtime model row pairs the badge tag with its VoiceOver phrasing")
    func runtimeModelRowPairsBadgeTagWithAccessibilityLabel() {
        // Adapter-backed derived model: short "adapter" tag + explicit a11y.
        let adapterBacked = makeModelSummary(
            modelID: "melix-dev-text-lora-runtime",
            state: .modelWarm,
            runtimeMode: "adapter_backed_runtime"
        )
        let adapterRow = makeRuntimeModelRow(adapterBacked)
        #expect(adapterRow.runtimeModeText == "adapter")
        #expect(adapterRow.runtimeModeAccessibilityLabel == "Runtime mode: adapter-backed")

        // Fused derived model: short "fused" tag + explicit a11y.
        let fused = makeModelSummary(
            modelID: "melix-dev-text-lora-fused",
            state: .modelWarm,
            runtimeMode: "fused_derived_model"
        )
        let fusedRow = makeRuntimeModelRow(fused)
        #expect(fusedRow.runtimeModeText == "fused")
        #expect(fusedRow.runtimeModeAccessibilityLabel == "Runtime mode: fused derived model")

        // Base / legacy models: both fields empty so the view hides the
        // badge and VoiceOver announces nothing for this element.
        let base = makeModelSummary(modelID: "melix-dev-text", state: .modelWarm)
        let baseRow = makeRuntimeModelRow(base)
        #expect(baseRow.runtimeModeText == "")
        #expect(baseRow.runtimeModeAccessibilityLabel == "")

        // Unknown values degrade gracefully to "?" with a screen-reader
        // friendly phrasing so VoiceOver doesn't read "question mark".
        let unknown = makeModelSummary(
            modelID: "melix-dev-text",
            state: .modelWarm,
            runtimeMode: "adapter_backed_runtime_v2"
        )
        let unknownRow = makeRuntimeModelRow(unknown)
        #expect(unknownRow.runtimeModeText == "?")
        #expect(unknownRow.runtimeModeAccessibilityLabel == "Runtime mode: unrecognized")
    }
}

@MainActor
private func bindSelectedChatSessionToPrimaryServer(_ viewModel: RuntimeViewModel) throws {
    let serverSessionID = try #require(viewModel.selectedServerSession?.id)
    viewModel.bindSelectedChatSessionToServer(serverSessionID: serverSessionID)
}

@MainActor
private func waitForRuntimeViewModelCondition(
    _ description: String,
    timeout: Duration = .seconds(2),
    pollInterval: Duration = .milliseconds(10),
    condition: @escaping @MainActor () -> Bool
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if condition() {
            return
        }
        try await Task.sleep(for: pollInterval)
    }

    throw MenuBarTestError(description: description)
}

private func waitForRuntimeMetric(
    _ metrics: MenuBarMetricsStore,
    name: String,
    equals expectedValue: Double,
    timeout: Duration = .seconds(2),
    pollInterval: Duration = .milliseconds(10)
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if await metrics.snapshot()[name] == expectedValue {
            return
        }
        try await Task.sleep(for: pollInterval)
    }

    let actualValue = await metrics.snapshot()[name]
    throw MenuBarTestError(
        description: "expected metric \(name) to equal \(expectedValue), got \(String(describing: actualValue))"
    )
}

private actor EmptySnapshotControlPlaneXPCClient: ControlPlaneXPCClient {
    private(set) var recordedActions: [String] = []

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "daemon-empty"
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
        recordedActions.append("load:\(modelID)")
        return Melix_Controlplane_V1_ModelSummary()
    }

    func unloadModel(modelID: String) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("unload:\(modelID)")
        return Melix_Controlplane_V1_ModelSummary()
    }

    func updateModelSettings(
        modelID: String,
        values: [String: String]
    ) async throws -> Melix_Controlplane_V1_ModelSummary {
        recordedActions.append("settings:\(modelID)")
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

private actor SnapshotControlPlaneXPCClient: ControlPlaneXPCClient {
    private let snapshot: Melix_Controlplane_V1_ServerSnapshot

    init(snapshot: Melix_Controlplane_V1_ServerSnapshot) {
        self.snapshot = snapshot
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "daemon-snapshot"
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
        throw ControlPlaneChatExecutionError.unavailable
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        snapshot
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

private actor EventingSnapshotControlPlaneXPCClient: ControlPlaneXPCClient {
    private let snapshot: Melix_Controlplane_V1_ServerSnapshot
    private let stream: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>
    private let continuation: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>.Continuation

    init(snapshot: Melix_Controlplane_V1_ServerSnapshot) {
        self.snapshot = snapshot

        var capturedContinuation: AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent>.Continuation?
        self.stream = AsyncStream { continuation in
            capturedContinuation = continuation
        }
        self.continuation = capturedContinuation!
    }

    func handshake() async throws -> Melix_Controlplane_V1_HandshakeResponse {
        var response = Melix_Controlplane_V1_HandshakeResponse()
        response.protocolVersion = "melix.controlplane.v1"
        response.serverVersion = "0.1.0"
        response.daemonInstanceID = "daemon-eventing"
        response.snapshot = snapshot
        return response
    }

    func subscribe(lastSeenSeq: UInt64) async -> AsyncStream<Melix_Controlplane_V1_ControlPlaneEvent> {
        _ = lastSeenSeq
        return stream
    }

    func startChat(_ request: ControlPlaneChatRequest) async throws -> ControlPlaneChatExecution {
        _ = request
        throw ControlPlaneChatExecutionError.unavailable
    }

    func serverSnapshot() async throws -> Melix_Controlplane_V1_ServerSnapshot {
        snapshot
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

    func sendQueueSummary() {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "heartbeat"
        event.heartbeat = Melix_Controlplane_V1_Heartbeat()
        continuation.yield(event)
    }

    func sendModelStateChanged(modelID: String, state: Melix_Controlplane_V1_ModelState) {
        var event = Melix_Controlplane_V1_ControlPlaneEvent()
        event.eventType = "model.state_changed"
        event.modelState = Melix_Controlplane_V1_ModelStateChanged()
        event.modelState.modelID = modelID
        event.modelState.state = state
        continuation.yield(event)
    }
}

private struct ThrowingOperatorSessionStore: OperatorSessionStoring {
    let throwOnLoad: Bool
    let throwOnSave: Bool

    func load() throws -> OperatorSessionState? {
        if throwOnLoad {
            throw MenuBarTestError(description: "restore-failed")
        }
        return nil
    }

    func save(_ state: OperatorSessionState) throws {
        _ = state
        if throwOnSave {
            throw MenuBarTestError(description: "persist-failed")
        }
    }
}

private struct ThrowingServerSessionAPIKeyStore: ServerSessionAPIKeyStoring {
    let throwOnLoad: Bool
    let throwOnSave: Bool
    let loadPrimaryKeyValue: String?

    func loadPrimaryKey(serverSessionID: String) throws -> ServerSessionPrimaryAPIKeyRecord? {
        if throwOnLoad {
            throw MenuBarTestError(description: "load-key-failed")
        }
        guard let loadPrimaryKeyValue else {
            return nil
        }
        return ServerSessionPrimaryAPIKeyRecord(
            serverSessionID: serverSessionID,
            keyID: "primary",
            primaryKey: loadPrimaryKeyValue,
            updatedAt: Date()
        )
    }

    func savePrimaryKey(
        serverSessionID: String,
        primaryKey: String,
        keyID: String
    ) throws -> ServerSessionPrimaryAPIKeyRecord {
        if throwOnSave {
            throw MenuBarTestError(description: "save-key-failed")
        }
        return ServerSessionPrimaryAPIKeyRecord(
            serverSessionID: serverSessionID,
            keyID: keyID,
            primaryKey: primaryKey,
            updatedAt: Date()
        )
    }
}

private func makeSnapshot(
    serverState: Melix_Controlplane_V1_ServerState,
    models: [Melix_Controlplane_V1_ModelSummary],
    runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState] = [],
    gatewayAccess: Melix_Controlplane_V1_GatewayAccessSummary? = nil,
    gatewayConfig: Melix_Controlplane_V1_GatewayConfigSummary? = nil
) -> Melix_Controlplane_V1_ServerSnapshot {
    var snapshot = Melix_Controlplane_V1_ServerSnapshot()
    snapshot.serverState = serverState
    snapshot.models = models
    snapshot.runtimeSessions = runtimeSessions
    if let gatewayAccess {
        snapshot.gatewayAccess = gatewayAccess
    }
    if let gatewayConfig {
        snapshot.gatewayConfig = gatewayConfig
    }
    return snapshot
}

private func makeRuntimeSession(
    serverSessionID: String = "server-session-1",
    lifecycleState: Melix_Controlplane_V1_ServerSessionLifecycleState = .ready,
    powerState: Melix_Controlplane_V1_ServerSessionPowerState = .active,
    wakeReason: Melix_Controlplane_V1_ServerWakeReason = .initialBoot,
    idleTimerSeconds: UInt32 = 0,
    autoSleepEnabled: Bool = false,
    lightSleepAfterSeconds: UInt32 = 300,
    deepSleepAfterSeconds: UInt32 = 1800
) -> Melix_Controlplane_V1_ServerSessionRuntimeState {
    var runtimeSession = Melix_Controlplane_V1_ServerSessionRuntimeState()
    runtimeSession.serverSessionID = serverSessionID
    runtimeSession.lifecycleState = lifecycleState
    runtimeSession.powerState = powerState
    runtimeSession.wakeReason = wakeReason
    runtimeSession.idleTimerSeconds = idleTimerSeconds
    runtimeSession.autoSleepEnabled = autoSleepEnabled
    runtimeSession.lightSleepAfterSeconds = lightSleepAfterSeconds
    runtimeSession.deepSleepAfterSeconds = deepSleepAfterSeconds
    runtimeSession.updatedAtUnixMs = 1_717_171_717
    return runtimeSession
}

private func makeGatewayAccessSummary(
    mode: Melix_Controlplane_V1_GatewayAccessMode,
    sharedAccessEnabled: Bool,
    acceptedApiKeyCount: UInt32,
    keyHints: [String]
) -> Melix_Controlplane_V1_GatewayAccessSummary {
    var summary = Melix_Controlplane_V1_GatewayAccessSummary()
    summary.mode = mode
    summary.sharedAccessEnabled = sharedAccessEnabled
    summary.sharedAccessReady = keyHints.isEmpty == false
    summary.requiredHeader = mode == .apiKeys ? .xApiKey : .none
    summary.acceptedApiKeyCount = acceptedApiKeyCount
    summary.keys = keyHints.enumerated().map { offset, hint in
        var key = Melix_Controlplane_V1_GatewayAccessKeySummary()
        key.keyID = "key-\(offset + 1)"
        key.label = hint
        key.tokenHint = hint
        return key
    }
    return summary
}

private func makeGatewayConfigSummary(
    listener: Melix_Controlplane_V1_GatewayListenerConfigSummary
) -> Melix_Controlplane_V1_GatewayConfigSummary {
    var summary = Melix_Controlplane_V1_GatewayConfigSummary()
    summary.listeners = [listener]
    return summary
}

private func makeGatewayConfigListener(
    serverSessionID: String,
    requestedHost: String,
    requestedPort: UInt32,
    effectiveHost: String,
    effectivePort: UInt32,
    servedModelID: String,
    rateLimitPerMinute: UInt32,
    timeoutSeconds: UInt32,
    source: Melix_Controlplane_V1_GatewayConfigSource,
    activeBinding: Bool,
    requiresRestart: Bool
) -> Melix_Controlplane_V1_GatewayListenerConfigSummary {
    var listener = Melix_Controlplane_V1_GatewayListenerConfigSummary()
    listener.serverSessionID = serverSessionID
    listener.requestedHost = requestedHost
    listener.requestedPort = requestedPort
    listener.effectiveHost = effectiveHost
    listener.effectivePort = effectivePort
    listener.servedModelID = servedModelID
    listener.rateLimitPerMinute = rateLimitPerMinute
    listener.timeoutSeconds = timeoutSeconds
    listener.source = source
    listener.activeBinding = activeBinding
    listener.requiresRestart = requiresRestart
    listener.updatedAtUnixMs = 1_717_171_717_000
    return listener
}

private func makeModelSummary(
    modelID: String = "melix-dev-text",
    state: Melix_Controlplane_V1_ModelState,
    transitionReason: String = "",
    pinRequested: Bool = false,
    pinned: Bool = false,
    ttlSeconds: UInt32 = 0,
    estimatedBytes: UInt64 = 0,
    inflightRequests: UInt64 = 0,
    memoryPolicy: Melix_Controlplane_V1_MemoryResidencyPolicy = .memoryResidencyEvictable,
    memoryBudgetBytes: UInt64 = 0,
    memoryHeadroomBytes: UInt64 = 0,
    requiredBytes: UInt64 = 0,
    adaptiveThinkingMode: String = "",
    adaptiveThinkingBudgetTokens: UInt32 = 0,
    runtimeMode: String = ""
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
    model.runtimeMode = runtimeMode
    model.settings.pinOnLoad = pinRequested
    model.settings.ttlSeconds = ttlSeconds
    model.settings.memoryPolicy = memoryPolicy
    model.settings.adaptiveThinking.mode = adaptiveThinkingMode
    model.settings.adaptiveThinking.budgetTokens = adaptiveThinkingBudgetTokens
    model.residency.pinRequested = pinRequested
    model.residency.pinned = pinned
    model.residency.ttlSeconds = ttlSeconds
    model.residency.policy = memoryPolicy
    model.residency.transitionReason = transitionReason
    model.residency.memoryBudgetBytes = memoryBudgetBytes
    model.residency.memoryHeadroomBytes = memoryHeadroomBytes
    model.residency.requiredBytes = requiredBytes
    return model
}

private func makeCapabilityModelSummary(
    modelID: String,
    kind: String,
    state: Melix_Controlplane_V1_ModelState,
    features: [String]
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = kind
    model.state = state
    model.features = features
    model.maxContext = 8192
    return model
}

private func makeRuntimeModelRow(state: Melix_Controlplane_V1_ModelState) -> RuntimeModelRow {
    RuntimeModelRow(
        modelID: "melix-dev-text",
        kind: "text",
        state: state,
        stateText: "state",
        actionTitle: "action",
        maxContext: 8192,
        alias: "Melix Dev Text",
        typeOverrideText: "",
        memoryPolicyText: "Evictable",
        diskStreamingModeText: "Disabled",
        adaptiveThinkingText: "Adaptive • 192 tok",
        accelerationModeText: "Baseline",
        accelerationProfileID: "",
        toolParserFallbackText: "Off",
        residencyText: "Warm • Evictable",
        memoryText: "No live footprint reported",
        memoryAlertText: ""
    )
}

private func makeNamedModelOperationResult(
    operation: String,
    outputPath: String,
    manifestJSON: String,
    quantProfileID: String = "",
    artifactKind: String = "",
    manifestPath: String = "",
    artifactBytes: UInt64 = 0,
    smokeTestPassed: Bool = false
) -> Melix_Controlplane_V1_ModelOperationResult {
    var result = Melix_Controlplane_V1_ModelOperationResult()
    result.ok = true
    result.operation = operation
    result.jobID = "job-\(operation)"
    result.stage = "completed"
    result.pct = 1
    result.outputPath = outputPath
    result.manifestJson = manifestJSON
    if !quantProfileID.isEmpty {
        result.quantProfile = Melix_Controlplane_V1_QuantizationProfile()
        result.quantProfile.algorithm = "oq"
        result.quantProfile.schemaVersion = "melix.quant_profile.v1"
        result.quantProfile.quantProfileID = quantProfileID
        result.quantProfile.weightQuant = quantProfileID
        result.quantProfile.kvQuant = "q8"
    }
    if !artifactKind.isEmpty {
        result.artifact = Melix_Controlplane_V1_ModelOperationArtifact()
        result.artifact.schemaVersion = "melix.quantized_bundle.v1"
        result.artifact.artifactKind = artifactKind
        result.artifact.bundlePath = outputPath
        result.artifact.manifestPath = manifestPath
        result.artifact.artifactBytes = artifactBytes
        result.artifact.manifestBytes = UInt64(manifestJSON.utf8.count)
        result.artifact.servingCompatible = true
        result.artifact.smokeTestRequested = true
        result.artifact.smokeTestPassed = smokeTestPassed
        result.artifact.runtime = "mlx_text"
    }
    return result
}

private func makeRuntimeDownloadQueueEntryState(
    status: String,
    pct: Double = 0.5,
    outputDir: String = "/tmp/melix-downloads/melix-dev-text",
    selectedMirror: String = "",
    downloadedBytes: Int = 1024,
    totalBytes: Int = 2048,
    resumeUsed: Bool = false,
    resumeFromBytes: Int = 0,
    retryCount: Int = 0,
    stallDetectionCount: Int = 0,
    stallReason: String = "",
    resumeReady: Bool = false
) -> RuntimeDownloadQueueEntryState {
    RuntimeDownloadQueueEntryState(
        jobID: "model-ops-state",
        sourceModel: "melix-dev-text",
        status: status,
        stage: "download",
        pct: pct,
        outputDir: outputDir,
        outputPath: "\(outputDir)/download.artifact",
        partialPath: "\(outputDir)/download.artifact.partial",
        statePath: "\(outputDir)/download.state.json",
        selectedMirror: selectedMirror,
        downloadedBytes: downloadedBytes,
        totalBytes: totalBytes,
        resumeUsed: resumeUsed,
        resumeFromBytes: resumeFromBytes,
        retryCount: retryCount,
        stallDetectionCount: stallDetectionCount,
        stallReason: stallReason,
        resumeReady: resumeReady
    )
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
            "target_repo": "\#(targetRepo)",
            "preset_id": "balanced_adapter",
            "preset_title": "Balanced Adapter",
            "checkpoint_count": 2,
            "resume_ready": true,
            "tokens_per_second": 128.5,
            "peak_memory_gb": 5.25
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
          "preset_id": "balanced_adapter",
          "preset_title": "Balanced Adapter",
          "checkpoint_count": 2,
          "resume_ready": true,
          "tokens_per_second": 128.5,
          "peak_memory_gb": 5.25,
          "training_duration_ms": 1420.0,
          "activation_duration_ms": \#(derivedModelID.isEmpty ? "0.0" : "321.0"),
          "adapter_publish_ms": 118.0
        }
      ],
      "experiment_groups": [
        {
          "group_id": "nightly-qwen35",
          "title": "nightly-qwen35",
          "adapter_name": "melix-dev-adapter",
          "source_model": "melix-dev-text",
          "run_count": 2,
          "latest_run_id": "model-ops-0001",
          "latest_status": "completed",
          "latest_dataset_uri": "datasets/melix-dev",
          "latest_preset_id": "balanced_adapter",
          "latest_preset_title": "Balanced Adapter",
          "latest_tokens_per_second": 128.5,
          "latest_peak_memory_gb": 5.25,
          "best_run_id": "model-ops-0001",
          "best_loss": 0.33,
          "recommended_manifest_path": "/tmp/melix-train-lora/train_lora.adapter.json"
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
          "job_id": "model-ops-0009",
          "operation": "quantize",
          "source_model": "melix-dev-text",
          "status": "completed",
          "stage": "write_artifact",
          "pct": 1.0,
          "output_path": "/tmp/melix-quantize/quantize.artifact",
          "manifest": {}
        },
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
            "target_repo": "",
            "preset_id": "debug_fast",
            "preset_title": "Debug Fast",
            "checkpoint_count": 1,
            "resume_ready": true,
            "tokens_per_second": 64.0,
            "peak_memory_gb": 4.1
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
          "preset_id": "debug_fast",
          "preset_title": "Debug Fast",
          "checkpoint_count": 1,
          "resume_ready": true,
          "tokens_per_second": 64.0,
          "peak_memory_gb": 4.1,
          "training_duration_ms": 950,
          "activation_duration_ms": 0,
          "adapter_publish_ms": 0
        }
      ],
      "experiment_groups": [
        {
          "group_id": "pending-adapter",
          "title": "pending-adapter",
          "adapter_name": "pending-adapter",
          "source_model": "melix-dev-text",
          "run_count": 1,
          "latest_run_id": "model-ops-0008",
          "latest_status": "queued_for_publish",
          "latest_dataset_uri": "datasets/pending",
          "latest_preset_id": "debug_fast",
          "latest_preset_title": "Debug Fast",
          "latest_tokens_per_second": 64.0,
          "latest_peak_memory_gb": 4.1,
          "best_run_id": "model-ops-0008",
          "best_loss": 0.42,
          "recommended_manifest_path": "/tmp/melix-train-lora/pending.adapter.json"
        }
      ],
      "derived_models": []
    }
    """#
}

private func makeExperimentLineageRegistrySnapshotManifest() -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "jobs": [],
      "adapters": [],
      "experiment_groups": [
        {
          "group_id": "nightly-qwen35",
          "title": "Nightly Qwen35",
          "adapter_name": "nightly-qwen35",
          "source_model": "melix-dev-text",
          "run_count": 3,
          "latest_preset_title": "Balanced Adapter",
          "latest_resume_ready": true,
          "latest_checkpoint_count": 5,
          "best_run_id": "model-ops-0012",
          "best_loss": 0.3287,
          "recommended_manifest_path": "/tmp/melix-train-lora/model-ops-0012/train_lora.adapter.json",
          "resume_ready_run_ids": ["model-ops-0012", "model-ops-0009"],
          "checkpoint_lineage": [
            {"run_id": "model-ops-0012", "checkpoint_count": 5, "resume_ready": true},
            {"run_id": "model-ops-0009", "checkpoint_count": 3, "resume_ready": true},
            {"run_id": "model-ops-0007", "checkpoint_count": 1, "resume_ready": false}
          ]
        }
      ],
      "derived_models": []
    }
    """#
}

private func makeStringBackedExperimentGroupRegistrySnapshotManifest() -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "jobs": [],
      "adapters": [],
      "experiment_groups": [
        {
          "group_id": "",
          "title": "invalid-group",
          "adapter_name": "ignored",
          "source_model": "melix-dev-text",
          "run_count": 1,
          "latest_preset_title": "Ignored",
          "latest_tokens_per_second": "1.0",
          "latest_peak_memory_gb": "1.0",
          "latest_checkpoint_count": 1,
          "latest_resume_ready": true,
          "best_loss": "0.90",
          "recommended_manifest_path": "/tmp/ignored.adapter.json"
        },
        {
          "group_id": "string-metrics",
          "title": "String Metrics",
          "adapter_name": "melix-dev-adapter",
          "source_model": "melix-dev-text",
          "run_count": 2,
          "latest_preset_title": "Balanced Adapter",
          "latest_tokens_per_second": "128.5",
          "latest_peak_memory_gb": "5.25",
          "latest_checkpoint_count": 2,
          "latest_resume_ready": true,
          "best_loss": "0.42",
          "recommended_manifest_path": "/tmp/melix-train-lora/train_lora.adapter.json"
        }
      ],
      "derived_models": []
    }
    """#
}
