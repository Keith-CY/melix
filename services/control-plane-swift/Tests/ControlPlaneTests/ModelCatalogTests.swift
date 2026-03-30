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
        #expect(models.first(where: { $0.modelID == "melix-dev-embed" })?.routeClass == .workerRoutePythonEmbedding)
        #expect(models.first(where: { $0.modelID == "melix-dev-rerank" })?.routeClass == .workerRoutePythonRerank)
        #expect(models.first(where: { $0.modelID == "melix-dev-model-ops" })?.routeClass == .workerRoutePythonModelOperations)
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

        #expect(models.first(where: { $0.modelID == "melix-dev-ocr" })?.routeClass == .workerRoutePythonOcr)
        #expect(models.first(where: { $0.modelID == "melix-dev-vlm" })?.capabilityClass == .modelCapabilityVlm)
        #expect(models.first(where: { $0.modelID == "melix-dev-transcribe" })?.supportedTasks == ["transcribe"])
        #expect(models.first(where: { $0.modelID == "melix-dev-speech" })?.supportedModalities == ["text", "audio"])
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
