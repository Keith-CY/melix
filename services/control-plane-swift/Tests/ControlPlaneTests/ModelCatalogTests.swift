import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Model Catalog")
struct ModelCatalogTests {
    @Test("phase five development seed models expose typed capabilities and routes")
    func phaseFiveSeedModelsExposeTypedCapabilitiesAndRoutes() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let models = await catalog.listModels()

        #expect(models.map(\.modelID) == [
            "melix-dev-embed",
            "melix-dev-model-ops",
            "melix-dev-rerank",
            "melix-dev-text",
        ])
        #expect(models.first(where: { $0.modelID == "melix-dev-text" })?.capabilityClass == .modelCapabilityText)
        #expect(models.first(where: { $0.modelID == "melix-dev-text" })?.settings.adaptiveThinking.mode == "adaptive")
        #expect(models.first(where: { $0.modelID == "melix-dev-text" })?.settings.adaptiveThinking.budgetTokens == 192)
        #expect(models.first(where: { $0.modelID == "melix-dev-embed" })?.routeClass == .workerRoutePythonEmbedding)
        #expect(models.first(where: { $0.modelID == "melix-dev-embed" })?.settings.ext["embedding_backend_id"] == "bert-v1")
        #expect(models.first(where: { $0.modelID == "melix-dev-embed" })?.settings.ext["embedding_family_id"] == "bert")
        #expect(models.first(where: { $0.modelID == "melix-dev-embed" })?.settings.ext["melix.adapter_set_hash"] == "embedding-family-bert")
        #expect(models.first(where: { $0.modelID == "melix-dev-embed" })?.settings.ext["melix.capability.route_kind"] == "python_embedding")
        #expect(models.first(where: { $0.modelID == "melix-dev-embed" })?.settings.ext["embedding_pooling_mode"] == "cls")
        #expect(models.first(where: { $0.modelID == "melix-dev-embed" })?.settings.ext["embedding_dimensions"] == "8")
        #expect(models.first(where: { $0.modelID == "melix-dev-embed" })?.supportedModalities == ["text"])
        #expect(models.first(where: { $0.modelID == "melix-dev-embed" })?.supportedTasks == ["embed"])
        #expect(models.first(where: { $0.modelID == "melix-dev-rerank" })?.routeClass == .workerRoutePythonRerank)
        #expect(models.first(where: { $0.modelID == "melix-dev-rerank" })?.settings.ext["rerank_backend_id"] == "token-overlap-v1")
        #expect(models.first(where: { $0.modelID == "melix-dev-rerank" })?.settings.ext["rerank_family_id"] == "jina-v3")
        #expect(models.first(where: { $0.modelID == "melix-dev-rerank" })?.settings.ext["melix.adapter_set_hash"] == "rerank-family-jina-v3")
        #expect(models.first(where: { $0.modelID == "melix-dev-rerank" })?.settings.ext["melix.capability.class"] == "rerank")
        #expect(models.first(where: { $0.modelID == "melix-dev-rerank" })?.settings.ext["rerank_scoring_mode"] == "order-aware-overlap")
        #expect(models.first(where: { $0.modelID == "melix-dev-rerank" })?.supportedModalities == ["text"])
        #expect(models.first(where: { $0.modelID == "melix-dev-rerank" })?.supportedTasks == ["rerank"])
        #expect(models.first(where: { $0.modelID == "melix-dev-model-ops" })?.routeClass == .workerRoutePythonModelOperations)
    }

    @Test("dev rerank model reads causal-lm environment overrides")
    func devRerankModelReadsCausalLMEnvironmentOverrides() async throws {
        let model = ModelCatalog.devRerankModel(environment: [
            "MELIX_DEV_RERANK_FAMILY_ID": "causal-lm",
        ])

        #expect(model.settings.ext["rerank_backend_id"] == "token-overlap-v1")
        #expect(model.settings.ext["rerank_family_id"] == "causal-lm")
        #expect(model.settings.ext["rerank_scoring_mode"] == "yes-no-logits")
        #expect(model.settings.ext["rerank_yes_no_labels"] == "yes,no")
    }

    @Test("dev embedding model infers mxbai identity from directory name")
    func devEmbeddingModelInfersMXBaiIdentityFromDirectoryName() async throws {
        let model = ModelCatalog.devEmbeddingModel(environment: [
            "MELIX_DEV_EMBED_MODEL_PATH": "models/mxbai-embed-large-v1",
        ])

        #expect(model.settings.ext["embedding_backend_id"] == "bert-v1")
        #expect(model.settings.ext["embedding_family_id"] == "mxbai-embed")
        #expect(model.settings.ext["embedding_pooling_mode"] == "mean")
        #expect(model.settings.ext["embedding_dimensions"] == "10")
        #expect(model.settings.ext["model_architecture"] == "bert")
        #expect(model.settings.ext["detected_architecture"] == "bert")
        #expect(model.settings.ext["detected_family_id"] == "mxbai-embed")
        #expect(model.settings.ext["detected_identity_source"] == "directory_name")
        #expect(model.settings.ext["identity_override"] == "false")
    }

    @Test("dev embedding model covers bert bge and xlmr directory inference branches")
    func devEmbeddingModelCoversDirectoryInferenceBranches() async throws {
        let bge = ModelCatalog.devEmbeddingModel(environment: [
            "MELIX_DEV_EMBED_MODEL_PATH": "models/bge-m3-large",
        ])
        let xlmr = ModelCatalog.devEmbeddingModel(environment: [
            "MELIX_DEV_EMBED_MODEL_PATH": "models/xlm-r-base",
        ])
        let bert = ModelCatalog.devEmbeddingModel(environment: [
            "MELIX_DEV_EMBED_MODEL_PATH": "models/bert-base",
        ])

        #expect(bge.settings.ext["embedding_family_id"] == "bge-m3")
        #expect(bge.settings.ext["detected_family_id"] == "bge-m3")
        #expect(xlmr.settings.ext["embedding_backend_id"] == "xlmr-v1")
        #expect(xlmr.settings.ext["embedding_family_id"] == "xlmr")
        #expect(xlmr.settings.ext["model_architecture"] == "xlmr")
        #expect(bert.settings.ext["embedding_family_id"] == "bert")
        #expect(bert.settings.ext["detected_family_id"] == "bert")
    }

    @Test("dev embedding model derives backend and family from overrides")
    func devEmbeddingModelDerivesBackendAndFamilyFromOverrides() async throws {
        let familyOverride = ModelCatalog.devEmbeddingModel(environment: [
            "MELIX_DEV_EMBED_FAMILY_ID": "xlmr",
        ])
        let backendOverride = ModelCatalog.devEmbeddingModel(environment: [
            "MELIX_DEV_EMBED_MODEL_PATH": "models/bert-base",
            "MELIX_DEV_EMBED_BACKEND_ID": "xlmr-v1",
        ])

        #expect(familyOverride.settings.ext["embedding_backend_id"] == "xlmr-v1")
        #expect(familyOverride.settings.ext["embedding_family_id"] == "xlmr")
        #expect(familyOverride.settings.ext["model_architecture"] == "xlmr")
        #expect(familyOverride.settings.ext["identity_override"] == "true")
        #expect(backendOverride.settings.ext["embedding_family_id"] == "xlmr")
        #expect(backendOverride.settings.ext["model_architecture"] == "xlmr")
    }

    @Test("dev rerank model preserves detected jina identity when override is applied")
    func devRerankModelPreservesDetectedJinaIdentityWhenOverrideIsApplied() async throws {
        let model = ModelCatalog.devRerankModel(environment: [
            "MELIX_DEV_RERANK_MODEL_PATH": "models/jina-v3-reranker",
            "MELIX_DEV_RERANK_FAMILY_ID": "causal-lm",
        ])

        #expect(model.settings.ext["rerank_family_id"] == "causal-lm")
        #expect(model.settings.ext["rerank_scoring_mode"] == "yes-no-logits")
        #expect(model.settings.ext["model_architecture"] == "causal-lm")
        #expect(model.settings.ext["detected_architecture"] == "cross-encoder")
        #expect(model.settings.ext["detected_family_id"] == "jina-v3")
        #expect(model.settings.ext["detected_identity_source"] == "directory_name")
        #expect(model.settings.ext["identity_override"] == "true")
    }

    @Test("dev rerank model covers causal-lm and basic directory inference branches")
    func devRerankModelCoversDirectoryInferenceBranches() async throws {
        let causalLM = ModelCatalog.devRerankModel(environment: [
            "MELIX_DEV_RERANK_MODEL_PATH": "models/causal-lm-reranker",
        ])
        let basic = ModelCatalog.devRerankModel(environment: [
            "MELIX_DEV_RERANK_MODEL_PATH": "models/basic-reranker",
        ])

        #expect(causalLM.settings.ext["rerank_family_id"] == "causal-lm")
        #expect(causalLM.settings.ext["rerank_scoring_mode"] == "yes-no-logits")
        #expect(causalLM.settings.ext["detected_architecture"] == "causal-lm")
        #expect(basic.settings.ext["rerank_family_id"] == "basic")
        #expect(basic.settings.ext["rerank_scoring_mode"] == "set-overlap")
        #expect(basic.settings.ext["detected_architecture"] == "cross-encoder")
    }

    @Test("dev vlm model exposes family capability adapter defaults")
    func devVLMModelExposesFamilyCapabilityAdapterDefaults() async throws {
        let model = ModelCatalog.devVLMModel()

        #expect(model.routeClass == .workerRoutePythonVlm)
        #expect(model.capabilityClass == .modelCapabilityVlm)
        #expect(model.supportedModalities == ["text", "image"])
        #expect(model.supportedTasks == ["vlm", "generate"])
        #expect(model.settings.ext["vision_family_id"] == "llava-v1")
        #expect(model.settings.ext["melix.adapter_set_hash"] == "vision-family-llava-v1")
        #expect(model.settings.ext["melix.capability.route_kind"] == "python_vlm")
        #expect(model.settings.ext["melix.capability.class"] == "vlm")
        #expect(model.settings.ext["melix.capability.supported_parsers"] == "text,qwen")
        #expect(model.settings.ext["tool_parser_mode"] == "qwen")
        #expect(model.settings.ext["tool_parser_namespaces"] == "tools.vision")
        #expect(model.settings.ext["tool_parser_xml_fallback"] == "true")
    }

    @Test("model settings updates persist alias and requested residency without faking pin state")
    func modelSettingsUpdatesPersistAliasAndRequestedResidencyWithoutFakingPinState() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        var settings = Melix_Controlplane_V1_ModelSettings()
        settings.alias = "Operations Embed"
        settings.pinOnLoad = true
        settings.ttlSeconds = 900
        settings.memoryPolicy = .memoryResidencyTtl
        settings.defaultAccelerationMode = .activeKvQuantized
        settings.accelerationProfileID = "embed-q8"

        let updated = try #require(await catalog.updateSettings(id: "melix-dev-embed", settings: settings))
        let reloaded = try #require(await catalog.model(id: "melix-dev-embed"))

        #expect(updated.settings.alias == "Operations Embed")
        #expect(updated.settings.pinOnLoad)
        #expect(updated.settings.ttlSeconds == 900)
        #expect(updated.settings.memoryPolicy == .memoryResidencyTtl)
        #expect(updated.settings.defaultAccelerationMode == .activeKvQuantized)
        #expect(updated.settings.accelerationProfileID == "embed-q8")
        #expect(!updated.pinned)
        #expect(updated.residency.pinRequested)
        #expect(!updated.residency.pinned)
        #expect(reloaded == updated)
    }

    @Test("registerModel inserts derived text models as discovered catalog entries")
    func registerModelInsertsDerivedTextModelsAsDiscoveredCatalogEntries() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        var model = ModelCatalog.devTextModel()
        model.modelID = "melix-dev-text-lora-abcd1234"
        model.settings.alias = "Derived Adapter"
        model.settings.ext["melix.model_path"] = "/tmp/melix-derived/model"
        model.settings.ext["melix.adapter_set_hash"] = "adapter-derived"
        model.settings.ext["melix.derived_from_adapter"] = "true"

        let registered = await catalog.registerModel(model, reason: "test_registration")
        let loaded = try #require(await catalog.model(id: "melix-dev-text-lora-abcd1234"))

        #expect(registered.modelID == "melix-dev-text-lora-abcd1234")
        #expect(registered.state == .modelDiscovered)
        #expect(registered.residency.state == .discovered)
        #expect(loaded.settings.ext["melix.model_path"] == "/tmp/melix-derived/model")
        #expect(loaded.settings.ext["melix.adapter_set_hash"] == "adapter-derived")
    }

    @Test("syncRegistryModels replaces prior registry-discovered entries while preserving seed models")
    func syncRegistryModelsReplacesPriorRegistryDiscoveredEntriesWhilePreservingSeedModels() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())

        var firstDiscovered = Melix_Controlplane_V1_ModelSummary()
        firstDiscovered.modelID = "mlx-community/Qwen2.5-7B-Instruct/4bit"
        firstDiscovered.kind = "text"
        firstDiscovered.state = .modelDiscovered
        firstDiscovered.capabilityClass = .modelCapabilityText
        firstDiscovered.routeClass = .workerRouteSwiftText
        firstDiscovered.quantProfileID = "q4"
        firstDiscovered.maxContext = 16384
        firstDiscovered.settings.alias = "Qwen 4bit"
        firstDiscovered.settings.memoryPolicy = .memoryResidencyEvictable
        firstDiscovered.settings.ext["melix.registry_root_id"] = "root-1"
        firstDiscovered.settings.ext["melix.registry_root_path"] = "/tmp/root-1"
        firstDiscovered.settings.ext["melix.registry_relative_path"] = "mlx-community/Qwen2.5-7B-Instruct/4bit"
        firstDiscovered.settings.ext["melix.model_path"] = "/tmp/root-1/mlx-community/Qwen2.5-7B-Instruct/4bit"

        var secondDiscovered = Melix_Controlplane_V1_ModelSummary()
        secondDiscovered.modelID = "mlx-community/Qwen2.5-14B-Instruct/8bit"
        secondDiscovered.kind = "text"
        secondDiscovered.state = .modelDiscovered
        secondDiscovered.capabilityClass = .modelCapabilityText
        secondDiscovered.routeClass = .workerRouteSwiftText
        secondDiscovered.quantProfileID = "q8"
        secondDiscovered.maxContext = 32768
        secondDiscovered.settings.alias = "Qwen 14B 8bit"
        secondDiscovered.settings.memoryPolicy = .memoryResidencyEvictable
        secondDiscovered.settings.ext["melix.registry_root_id"] = "root-2"
        secondDiscovered.settings.ext["melix.registry_root_path"] = "/tmp/root-2"
        secondDiscovered.settings.ext["melix.registry_relative_path"] = "mlx-community/Qwen2.5-14B-Instruct/8bit"
        secondDiscovered.settings.ext["melix.model_path"] = "/tmp/root-2/mlx-community/Qwen2.5-14B-Instruct/8bit"

        await catalog.syncRegistryModels([firstDiscovered], reason: "worker_registry_sync")
        await catalog.syncRegistryModels([secondDiscovered], reason: "worker_registry_sync")

        let models = await catalog.listModels()
        let synced = try #require(models.first(where: { $0.modelID == secondDiscovered.modelID }))

        #expect(models.contains(where: { $0.modelID == "melix-dev-text" }))
        #expect(!models.contains(where: { $0.modelID == firstDiscovered.modelID }))
        #expect(synced.maxContext == 32768)
        #expect(synced.settings.ext["melix.registry_root_id"] == "root-2")
        #expect(synced.settings.ext["melix.model_path"] == "/tmp/root-2/mlx-community/Qwen2.5-14B-Instruct/8bit")
    }

    @Test("syncRegistryModels merges refreshed registry metadata into existing discovered entries")
    func syncRegistryModelsMergesRefreshedRegistryMetadataIntoExistingDiscoveredEntries() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())

        var initial = Melix_Controlplane_V1_ModelSummary()
        initial.modelID = "mlx-community/Qwen2.5-7B-Instruct/4bit"
        initial.kind = "text"
        initial.state = .modelDiscovered
        initial.capabilityClass = .modelCapabilityText
        initial.routeClass = .workerRouteSwiftText
        initial.quantProfileID = "q4"
        initial.maxContext = 16384
        initial.settings.memoryPolicy = .memoryResidencyEvictable
        initial.settings.ext["melix.registry_root_id"] = "root-1"

        await catalog.syncRegistryModels([initial], reason: "worker_registry_sync")
        _ = await catalog.loadModel(id: initial.modelID, dispatchHandle: "registry::existing")

        var refreshed = initial
        refreshed.kind = "embedding"
        refreshed.quantProfileID = "q8"
        refreshed.maxContext = 32768
        refreshed.features = ["embeddings"]
        refreshed.capabilityClass = .modelCapabilityEmbedding
        refreshed.routeClass = .workerRoutePythonEmbedding
        refreshed.supportedModalities = ["text"]
        refreshed.supportedTasks = ["embed"]
        refreshed.settings.alias = "Registry Embed"
        refreshed.settings.typeOverride = "embedding_override"
        refreshed.settings.ttlSeconds = 60
        refreshed.settings.pinOnLoad = true
        refreshed.settings.memoryPolicy = .memoryResidencyPinned
        refreshed.settings.defaultAccelerationMode = .activeKvQuantized
        refreshed.settings.accelerationProfileID = "embed-q8"
        refreshed.settings.adaptiveThinking.mode = "adaptive"
        refreshed.settings.adaptiveThinking.budgetTokens = 256
        refreshed.settings.ext["melix.registry_root_id"] = "root-2"
        refreshed.settings.ext["embedding_family_id"] = "mxbai-embed"

        await catalog.syncRegistryModels([refreshed], reason: "worker_registry_sync")

        let merged = try #require(await catalog.model(id: initial.modelID))

        #expect(merged.state == .modelWarm)
        #expect(merged.kind == "embedding")
        #expect(merged.quantProfileID == "q8")
        #expect(merged.maxContext == 32768)
        #expect(merged.features == ["embeddings"])
        #expect(merged.capabilityClass == .modelCapabilityEmbedding)
        #expect(merged.routeClass == .workerRoutePythonEmbedding)
        #expect(merged.supportedModalities == ["text"])
        #expect(merged.supportedTasks == ["embed"])
        #expect(merged.settings.alias == "Registry Embed")
        #expect(merged.settings.typeOverride == "embedding_override")
        #expect(merged.settings.ttlSeconds == 60)
        #expect(merged.settings.pinOnLoad)
        #expect(merged.settings.memoryPolicy == .memoryResidencyPinned)
        #expect(merged.settings.defaultAccelerationMode == .activeKvQuantized)
        #expect(merged.settings.accelerationProfileID == "embed-q8")
        #expect(merged.settings.adaptiveThinking.mode == "adaptive")
        #expect(merged.settings.adaptiveThinking.budgetTokens == 256)
        #expect(merged.settings.ext["melix.registry_root_id"] == "root-2")
        #expect(merged.settings.ext["embedding_family_id"] == "mxbai-embed")
        #expect(await catalog.dispatchHandle(for: initial.modelID) == "registry::existing")
    }

    @Test("syncRegistryModels preserves structured registry identity metadata from worker snapshots")
    func syncRegistryModelsPreservesStructuredRegistryIdentityMetadataFromWorkerSnapshots() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())

        var discovered = Melix_Controlplane_V1_ModelSummary()
        discovered.modelID = "mlx-community/Qwen2.5-7B-Instruct/4bit"
        discovered.kind = "text"
        discovered.state = .modelDiscovered
        discovered.capabilityClass = .modelCapabilityText
        discovered.routeClass = .workerRouteSwiftText
        discovered.settings.memoryPolicy = .memoryResidencyEvictable
        discovered.settings.ext["melix.registry_root_id"] = "root-1"
        discovered.settings.ext["melix.registry_relative_path"] = "huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit"
        discovered.settings.ext["melix.registry_provider_id"] = "hf-mirror"
        discovered.settings.ext["melix.registry_organization_id"] = "mlx-community"
        discovered.settings.ext["melix.registry_model_name"] = "Qwen2.5-7B-Instruct"
        discovered.settings.ext["melix.registry_variant_id"] = "q4f16"

        await catalog.syncRegistryModels([discovered], reason: "worker_registry_sync")

        let synced = try #require(await catalog.model(id: discovered.modelID))

        #expect(synced.settings.ext["melix.registry_provider_id"] == "hf-mirror")
        #expect(synced.settings.ext["melix.registry_organization_id"] == "mlx-community")
        #expect(synced.settings.ext["melix.registry_model_name"] == "Qwen2.5-7B-Instruct")
        #expect(synced.settings.ext["melix.registry_variant_id"] == "q4f16")
        #expect(synced.settings.ext["melix.registry_relative_path"] == "huggingface/mlx-community/Qwen2.5-7B-Instruct/4bit")
    }

    @Test("residency summary follows seed defaults and load-unload transitions")
    func residencySummaryFollowsSeedDefaultsAndLoadUnloadTransitions() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())
        let discovered = try #require(await catalog.model(id: "melix-dev-text"))

        #expect(discovered.residency.state == .discovered)
        #expect(discovered.residency.policy == .memoryResidencyEvictable)
        #expect(!discovered.residency.pinRequested)
        #expect(!discovered.residency.pinned)

        var pinnedSettings = discovered.settings
        pinnedSettings.pinOnLoad = true
        pinnedSettings.memoryPolicy = .memoryResidencyPinned

        let updated = try #require(await catalog.updateSettings(id: "melix-dev-text", settings: pinnedSettings))
        #expect(updated.residency.pinRequested)
        #expect(updated.residency.policy == .memoryResidencyPinned)

        let loaded = try #require(await catalog.loadModel(id: "melix-dev-text"))
        #expect(loaded.state == .modelPinned)
        #expect(loaded.residency.state == .pinned)
        #expect(loaded.residency.pinned)

        let unloaded = try #require(await catalog.unloadModel(id: "melix-dev-text"))
        #expect(unloaded.state == .modelUnloaded)
        #expect(unloaded.residency.state == .unloaded)
        #expect(unloaded.residency.policy == .memoryResidencyPinned)
    }

    @Test("residency summary maps ttl and non-terminal states")
    func residencySummaryMapsTtlAndNonTerminalStates() async throws {
        func makeSeed(
            id: String,
            state: Melix_Controlplane_V1_ModelState,
            ttlSeconds: UInt32 = 0
        ) -> Melix_Controlplane_V1_ModelSummary {
            var model = Melix_Controlplane_V1_ModelSummary()
            model.modelID = id
            model.state = state
            if ttlSeconds > 0 {
                model.settings.ttlSeconds = ttlSeconds
            }
            return model
        }

        let catalog = ModelCatalog(seedModels: [
            makeSeed(id: "ttl-loading", state: .modelLoading, ttlSeconds: 60),
            makeSeed(id: "warm", state: .modelWarm),
            makeSeed(id: "evicting", state: .modelEvicting),
            makeSeed(id: "failed", state: .modelFailed),
            makeSeed(id: "unspecified", state: .unspecified),
        ])

        let models = await catalog.listModels()
        let byID = Dictionary(uniqueKeysWithValues: models.map { ($0.modelID, $0) })

        let ttlLoading = try #require(byID["ttl-loading"])
        #expect(ttlLoading.residency.policy == .memoryResidencyTtl)
        #expect(ttlLoading.residency.state == .loading)

        let warm = try #require(byID["warm"])
        #expect(warm.residency.state == .warm)
        #expect(warm.residency.policy == .memoryResidencyEvictable)

        let evicting = try #require(byID["evicting"])
        #expect(evicting.residency.state == .evicting)

        let failed = try #require(byID["failed"])
        #expect(failed.residency.state == .failed)

        let unspecified = try #require(byID["unspecified"])
        #expect(unspecified.residency.state == .unspecified)
    }

    @Test("explicit residency transitions separate loading failure evicting and worker-reported states")
    func explicitResidencyTransitionsSeparateLoadingFailureEvictingAndWorkerReportedStates() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseFiveSeedModels())

        let loading = try #require(await catalog.beginLoad(id: "melix-dev-text"))
        #expect(loading.state == .modelLoading)
        #expect(loading.residency.state == .loading)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)

        let failed = try #require(await catalog.recordLoadFailed(id: "melix-dev-text"))
        #expect(failed.state == .modelFailed)
        #expect(failed.residency.state == .failed)

        var workerResidency = Melix_Worker_V1_ResidencyInfo()
        workerResidency.state = .pinned
        workerResidency.pinned = true

        let loaded = try #require(await catalog.recordLoadSucceeded(
            id: "melix-dev-text",
            dispatchHandle: "melix-dev-text::swift",
            workerResidency: workerResidency
        ))
        #expect(loaded.state == .modelPinned)
        #expect(loaded.residency.state == .pinned)
        #expect(loaded.pinned)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::swift")

        let evicting = try #require(await catalog.beginUnload(id: "melix-dev-text"))
        #expect(evicting.state == .modelEvicting)
        #expect(evicting.residency.state == .evicting)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)

        let unloaded = try #require(await catalog.recordUnloadSucceeded(id: "melix-dev-text"))
        #expect(unloaded.state == .modelUnloaded)
        #expect(unloaded.residency.state == .unloaded)
    }

    @Test("worker residency mappings drive ready states and dispatch-handle retention")
    func workerResidencyMappingsDriveReadyStatesAndDispatchHandleRetention() async throws {
        let cases: [(Melix_Worker_V1_ResidencyState, Melix_Controlplane_V1_ModelState, Bool)] = [
            (.warm, .modelWarm, true),
            (.loading, .modelLoading, false),
            (.evicting, .modelEvicting, false),
            (.unloaded, .modelUnloaded, false),
            (.failed, .modelFailed, false),
            (.UNRECOGNIZED(-1), .modelWarm, true),
        ]

        for (workerState, expectedState, keepsHandle) in cases {
            let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
            var workerResidency = Melix_Worker_V1_ResidencyInfo()
            workerResidency.state = workerState

            let loaded = try #require(await catalog.recordLoadSucceeded(
                id: "melix-dev-text",
                dispatchHandle: "melix-dev-text::swift",
                workerResidency: workerResidency
            ))

            #expect(loaded.state == expectedState)
            #expect(await catalog.dispatchHandle(for: "melix-dev-text") == (keepsHandle ? "melix-dev-text::swift" : nil))
            #expect(await catalog.storedDispatchHandle(for: "melix-dev-text") == (keepsHandle ? "melix-dev-text::swift" : nil))
        }
    }

    @Test("explicit transition helpers handle missing models custom handles and unload failures")
    func explicitTransitionHelpersHandleMissingModelsCustomHandlesAndUnloadFailures() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])

        #expect(await catalog.beginLoad(id: "missing-model") == nil)
        #expect(await catalog.recordLoadFailed(id: "missing-model") == nil)
        #expect(await catalog.beginUnload(id: "missing-model") == nil)
        #expect(await catalog.recordUnloadFailed(id: "missing-model") == nil)

        let loaded = try #require(await catalog.loadModel(
            id: "melix-dev-text",
            dispatchHandle: "melix-dev-text::custom"
        ))
        #expect(loaded.state == .modelWarm)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == "melix-dev-text::custom")

        let evicting = try #require(await catalog.beginUnload(id: "melix-dev-text"))
        #expect(evicting.state == .modelEvicting)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
        #expect(await catalog.storedDispatchHandle(for: "melix-dev-text") == "melix-dev-text::custom")

        let failed = try #require(await catalog.recordUnloadFailed(id: "melix-dev-text"))
        #expect(failed.state == .modelFailed)
        #expect(failed.residency.state == .failed)
        #expect(await catalog.dispatchHandle(for: "melix-dev-text") == nil)
        #expect(await catalog.storedDispatchHandle(for: "melix-dev-text") == nil)
    }

    @Test("transition reasons fall back through worker residency unload defaults and missing usage lookups")
    func transitionReasonsFallBackThroughWorkerResidencyUnloadDefaultsAndMissingUsageLookups() async throws {
        let catalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        #expect(await catalog.markModelUsed(id: "missing-model") == nil)

        var workerResidency = Melix_Worker_V1_ResidencyInfo()
        workerResidency.state = .warm
        workerResidency.transitionReason = "worker_seed_reason"

        let loaded = try #require(await catalog.recordLoadSucceeded(
            id: "melix-dev-text",
            dispatchHandle: "melix-dev-text::swift",
            workerResidency: workerResidency
        ))
        #expect(loaded.residency.transitionReason == "worker_seed_reason")

        let preservedUnload = try #require(await catalog.recordUnloadSucceeded(id: "melix-dev-text"))
        #expect(preservedUnload.residency.transitionReason == "worker_seed_reason")

        let fallbackCatalog = ModelCatalog(seedModels: [ModelCatalog.devTextModel()])
        let unloaded = try #require(await fallbackCatalog.recordUnloadSucceeded(id: "melix-dev-text"))
        #expect(unloaded.residency.transitionReason == "operator_unload")

        let failed = try #require(await catalog.recordUnloadFailed(
            id: "melix-dev-text",
            reason: "ttl_expired_failed"
        ))
        #expect(failed.residency.transitionReason == "ttl_expired_failed")
    }

    @Test("eviction plan prioritizes ttl expiry before lru and reports pin protection")
    func evictionPlanPrioritizesTtlExpiryBeforeLruAndReportsPinProtection() async throws {
        final class ClockBox: @unchecked Sendable {
            var nowUnixMs: Int64

            init(nowUnixMs: Int64) {
                self.nowUnixMs = nowUnixMs
            }
        }

        func makeTextSeed(
            id: String,
            state: Melix_Controlplane_V1_ModelState,
            ttlSeconds: UInt32 = 0,
            pinOnLoad: Bool = false
        ) -> Melix_Controlplane_V1_ModelSummary {
            var model = ModelCatalog.devTextModel()
            model.modelID = id
            model.state = state
            if ttlSeconds > 0 {
                model.settings.ttlSeconds = ttlSeconds
                model.settings.memoryPolicy = .memoryResidencyTtl
            }
            if pinOnLoad {
                model.settings.pinOnLoad = true
                model.settings.memoryPolicy = .memoryResidencyPinned
            }
            return model
        }

        let clock = ClockBox(nowUnixMs: 10_000)
        let catalog = ModelCatalog(
            seedModels: [
                makeTextSeed(id: "text-ttl", state: .modelWarm, ttlSeconds: 60),
                makeTextSeed(id: "text-lru", state: .modelWarm),
                makeTextSeed(id: "text-pinned", state: .modelPinned, pinOnLoad: true),
                makeTextSeed(id: "text-incoming", state: .modelDiscovered),
            ],
            nowUnixMs: { clock.nowUnixMs }
        )

        clock.nowUnixMs += 61_000
        let plan = await catalog.evictionPlanForLoad(id: "text-incoming")

        #expect(plan.decisions == [
            .init(modelID: "text-ttl", reason: "ttl_expired"),
            .init(modelID: "text-lru", reason: "lru_same_capability"),
        ])
        #expect(plan.pinnedProtectedModelIDs == ["text-pinned"])
    }

    @Test("eviction family falls back through route classes and kinds when capabilities are unspecified")
    func evictionFamilyFallsBackThroughRouteClassesAndKindsWhenCapabilitiesAreUnspecified() async throws {
        var routeResident = Melix_Controlplane_V1_ModelSummary()
        routeResident.modelID = "route-resident"
        routeResident.state = .modelWarm
        routeResident.routeClass = .workerRoutePythonEmbedding

        var routeTarget = Melix_Controlplane_V1_ModelSummary()
        routeTarget.modelID = "route-target"
        routeTarget.state = .modelDiscovered
        routeTarget.routeClass = .workerRoutePythonEmbedding

        let routeCatalog = ModelCatalog(seedModels: [routeResident, routeTarget])
        let routePlan = await routeCatalog.evictionPlanForLoad(id: "route-target")
        #expect(routePlan.decisions == [.init(modelID: "route-resident", reason: "lru_same_capability")])

        var kindResident = Melix_Controlplane_V1_ModelSummary()
        kindResident.modelID = "kind-resident"
        kindResident.state = .modelWarm
        kindResident.kind = "rerank"

        var kindTarget = Melix_Controlplane_V1_ModelSummary()
        kindTarget.modelID = "kind-target"
        kindTarget.state = .modelDiscovered
        kindTarget.kind = "rerank"

        let kindCatalog = ModelCatalog(seedModels: [kindResident, kindTarget])
        let kindPlan = await kindCatalog.evictionPlanForLoad(id: "kind-target")
        #expect(kindPlan.decisions == [.init(modelID: "kind-resident", reason: "lru_same_capability")])
    }

    @Test("phase six contract seed models expose multimodal routes and task visibility")
    func phaseSixContractSeedModelsExposeMultimodalRoutesAndTasks() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSixContractSeedModels())
        let models = await catalog.listModels()

        let ocrModel = try #require(models.first(where: { $0.modelID == "melix-dev-ocr" }))
        #expect(ocrModel.routeClass == .workerRoutePythonOcr)
        #expect(ocrModel.settings.ext["ocr_prompt_profile_id"] == "ocr-default-v1")
        #expect(ocrModel.settings.ext["ocr_sampling_profile_id"] == "ocr-deterministic")
        #expect(ocrModel.settings.ext["ocr_stop_sequences"] == "<ocr:end>")
        let vlmModel = try #require(models.first(where: { $0.modelID == "melix-dev-vlm" }))
        #expect(vlmModel.capabilityClass == .modelCapabilityVlm)
        #expect(vlmModel.settings.ext["vision_family_id"] == "llava-v1")
        #expect(vlmModel.settings.ext["vision_prompt_profile_id"] == "llava-chatml-v1")
        #expect(vlmModel.settings.ext["vision_tokenization_mode"] == "interleaved")
        #expect(vlmModel.settings.ext["vision_max_images_per_prompt"] == "8")
        #expect(vlmModel.settings.ext["vision_supports_tool_calls"] == "true")
        #expect(vlmModel.settings.ext["melix.multimodal_adapter_hash"] == "vision-family-llava-v1")
        #expect(models.first(where: { $0.modelID == "melix-dev-transcribe" })?.supportedTasks == ["transcribe"])
        #expect(models.first(where: { $0.modelID == "melix-dev-speech" })?.supportedModalities == ["text", "audio"])
    }

    @Test("audio seed models expose backend metadata for deterministic and mlx-audio paths")
    func audioSeedModelsExposeBackendMetadata() async throws {
        let deterministicTranscription = ModelCatalog.devTranscriptionModel()
        let deterministicSpeech = ModelCatalog.devSpeechModel()
        let whisper = ModelCatalog.mlxWhisperModel()
        let kokoro = ModelCatalog.mlxKokoroModel()

        #expect(deterministicTranscription.settings.ext["melix.audio.backend_id"] == "deterministic")
        #expect(deterministicTranscription.settings.ext["melix.audio.family_id"] == "deterministic-transcription")
        #expect(deterministicTranscription.settings.ext["melix.audio.install_profile"] == "")
        #expect(deterministicTranscription.settings.ext["melix.audio.languages"] == "und")

        #expect(deterministicSpeech.settings.ext["melix.audio.backend_id"] == "deterministic")
        #expect(deterministicSpeech.settings.ext["melix.audio.family_id"] == "deterministic-speech")
        #expect(deterministicSpeech.settings.ext["melix.audio.output_formats"] == "wav,mp3")
        #expect(deterministicSpeech.settings.ext["melix.audio.voice_mode"] == "named")
        #expect(deterministicSpeech.settings.ext["melix.audio.supports_instructions"] == "false")

        #expect(whisper.kind == "transcription")
        #expect(whisper.settings.ext["melix.audio.backend_id"] == "mlx_audio.stt")
        #expect(whisper.settings.ext["melix.audio.family_id"] == "whisper")
        #expect(whisper.settings.ext["melix.audio.install_profile"] == "audio-stt")

        #expect(kokoro.kind == "speech")
        #expect(kokoro.settings.ext["melix.audio.backend_id"] == "mlx_audio.tts")
        #expect(kokoro.settings.ext["melix.audio.family_id"] == "kokoro")
        #expect(kokoro.settings.ext["melix.audio.output_formats"] == "wav")
        #expect(kokoro.settings.ext["melix.audio.supports_instructions"] == "false")
    }

    @Test("phase seven contract seed models expose image routes and tasks")
    func phaseSevenContractSeedModelsExposeImageRoutesAndTasks() async throws {
        let catalog = ModelCatalog(seedModels: ModelCatalog.phaseSevenContractSeedModels())
        let models = await catalog.listModels()

        let imageModel = try #require(models.first(where: { $0.modelID == "melix-dev-image" }))
        #expect(imageModel.capabilityClass == .modelCapabilityImageGeneration)
        #expect(imageModel.routeClass == .workerRoutePythonImage)
        #expect(imageModel.supportedTasks == ["image_generate", "image_edit"])
        #expect(imageModel.supportedModalities == ["text", "image"])
    }
}
