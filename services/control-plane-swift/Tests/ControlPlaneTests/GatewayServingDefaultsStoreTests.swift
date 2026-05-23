import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol
import MelixWorkerProtocol

@Suite("Gateway Serving Defaults Store")
struct GatewayServingDefaultsStoreTests {
    @Test("environment initializer defaults store under MelixHome config")
    func environmentInitializerDefaultsStoreUnderMelixHomeConfig() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-serving-defaults-home-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayServingDefaultsStore(environment: [
            "HOME": temporaryRoot.path,
            "MELIX_APP_SUPPORT_DIR": temporaryRoot.appendingPathComponent("ignored-app-support").path,
        ])

        #expect(
            await store.storePath()
                == temporaryRoot.appendingPathComponent(".melix/config/gateway-serving-defaults.json").path
        )
    }

    @Test("serving acceleration profiles expose stable ids defaults and raw mappings")
    func servingAccelerationProfilesExposeStableIDsDefaultsAndRawMappings() {
        let profiles = ServingAccelerationProfiles.all

        #expect(profiles.map(\.id) == ["balanced", "throughput", "low-memory", "long-session"])
        #expect(ServingAccelerationProfiles.allowedProfileList == "balanced, throughput, low-memory, long-session")
        #expect(ServingAccelerationProfiles.normalizeProfileID(" LOW_MEMORY ") == "low-memory")
        #expect(ServingAccelerationProfiles.normalizeProfileID("long_session") == "long-session")
        #expect(ServingAccelerationProfiles.normalizeProfileID("unknown") == nil)
        #expect(ServingAccelerationProfiles.normalizeProfileID(" ") == nil)
        #expect(ServingAccelerationProfiles.profile(id: nil).id == "balanced")
        #expect(ServingAccelerationProfiles.profile(id: "missing").id == "balanced")

        for profile in profiles {
            #expect(ServingAccelerationProfiles.profile(id: profile.id) == profile)
            #expect(profile.id.isEmpty == false)
            #expect(profile.label.isEmpty == false)
            #expect(profile.intent.isEmpty == false)
        }

        let throughput = ServingAccelerationProfiles.profile(id: "throughput")
        #expect(throughput.accelerationMode == .speculativeDecode)
        #expect(throughput.numDraftTokens == 6)
        #expect(throughput.concurrentProcessingEnabled)
        #expect(throughput.maxConcurrentRequests == 8)
        #expect(throughput.prefillBatchSize == 4)
        #expect(throughput.completionBatchSize == 4)

        let lowMemory = ServingAccelerationProfiles.profile(id: "low-memory")
        #expect(lowMemory.accelerationMode == .baseline)
        #expect(lowMemory.draftModelID.isEmpty)
        #expect(lowMemory.numDraftTokens == 0)
        #expect(lowMemory.concurrentProcessingEnabled == false)
        #expect(lowMemory.maxConcurrentRequests == 1)
        #expect(lowMemory.prefillBatchSize == 1)
        #expect(lowMemory.completionBatchSize == 1)

        let longSession = ServingAccelerationProfiles.profile(id: "long-session")
        #expect(longSession.accelerationMode == .baseline)
        #expect(longSession.concurrentProcessingEnabled)
        #expect(longSession.maxConcurrentRequests == 2)
        #expect(longSession.prefillBatchSize == 2)
        #expect(longSession.completionBatchSize == 1)

        #expect(ServingAccelerationProfiles.controlPlaneAccelerationMode(rawValue: "speculative_decode") == .speculativeDecode)
        #expect(ServingAccelerationProfiles.controlPlaneAccelerationMode(rawValue: "accelerated_prefill") == .acceleratedPrefill)
        #expect(ServingAccelerationProfiles.controlPlaneAccelerationMode(rawValue: "active_kv_quantized") == .activeKvQuantized)
        #expect(ServingAccelerationProfiles.controlPlaneAccelerationMode(rawValue: "sparse_prefill") == .sparsePrefill)
        #expect(ServingAccelerationProfiles.controlPlaneAccelerationMode(rawValue: "baseline") == .baseline)
        #expect(ServingAccelerationProfiles.controlPlaneAccelerationMode(rawValue: "") == .baseline)
        #expect(ServingAccelerationProfiles.controlPlaneAccelerationMode(rawValue: "future_mode") == .unspecified)

        #expect(ServingAccelerationProfiles.controlPlaneRawValue(.speculativeDecode) == "speculative_decode")
        #expect(ServingAccelerationProfiles.controlPlaneRawValue(.acceleratedPrefill) == "accelerated_prefill")
        #expect(ServingAccelerationProfiles.controlPlaneRawValue(.activeKvQuantized) == "active_kv_quantized")
        #expect(ServingAccelerationProfiles.controlPlaneRawValue(.sparsePrefill) == "sparse_prefill")
        #expect(ServingAccelerationProfiles.controlPlaneRawValue(.baseline) == "baseline")
        #expect(ServingAccelerationProfiles.controlPlaneRawValue(.unspecified) == "baseline")

        #expect(ServingAccelerationProfiles.workerRawValue(.speculativeDecode) == "speculative_decode")
        #expect(ServingAccelerationProfiles.workerRawValue(.acceleratedPrefill) == "accelerated_prefill")
        #expect(ServingAccelerationProfiles.workerRawValue(.activeKvQuantized) == "active_kv_quantized")
        #expect(ServingAccelerationProfiles.workerRawValue(.sparsePrefill) == "sparse_prefill")
        #expect(ServingAccelerationProfiles.workerRawValue(.baseline) == "baseline")
        #expect(ServingAccelerationProfiles.workerRawValue(.unspecified) == "baseline")
    }

    @Test("summary projects built-in defaults when no operator override exists")
    func summaryProjectsBuiltInDefaultsWhenNoOperatorOverrideExists() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-serving-defaults-builtins-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        var modelSettings = Melix_Controlplane_V1_ModelSettings()
        modelSettings.ext["melix.generation_config.temperature"] = "0.2"
        modelSettings.ext["melix.generation_config.top_p"] = "0.88"
        modelSettings.ext["melix.generation_config.max_tokens"] = "512"

        let store = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )
        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            defaultModelIDs: [ServerSessionRuntimeStore.defaultServerSessionID: "melix-dev-text"],
            modelSettingsByModelID: ["melix-dev-text": modelSettings]
        )
        let session = try #require(summary.sessions.first)

        #expect(session.serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
        #expect(session.requestedTemperature == 0.7)
        #expect(session.requestedTopP == 1.0)
        #expect(session.requestedMaxTokens == 32_768)
        #expect(session.requestedStreamIntervalTokens == 1)
        #expect(session.requestedMaxConcurrentRequests == 4)
        #expect(session.requestedConcurrentProcessingEnabled)
        #expect(session.requestedPrefillBatchSize == 2)
        #expect(session.requestedCompletionBatchSize == 2)
        #expect(session.effectiveTemperature == 0.2)
        #expect(session.effectiveTopP == 0.88)
        #expect(session.effectiveMaxTokens == 512)
        #expect(session.effectiveStreamIntervalTokens == 1)
        #expect(session.effectiveMaxConcurrentRequests == 2)
        #expect(session.effectiveConcurrentProcessingEnabled)
        #expect(session.effectivePrefillBatchSize == 2)
        #expect(session.effectiveCompletionBatchSize == 2)
        #expect(session.requestedAccelerationMode == .baseline)
        #expect(session.requestedDraftModelID.isEmpty)
        #expect(session.requestedNumDraftTokens == 0)
        #expect(session.requestedAccelerationProfile == "balanced")
        #expect(session.effectiveAccelerationMode == .baseline)
        #expect(session.effectiveDraftModelID.isEmpty)
        #expect(session.effectiveNumDraftTokens == 0)
        #expect(session.effectiveAccelerationProfile == "balanced")
        #expect(session.accelerationProfileIntent == ServingAccelerationProfiles.profile(id: "balanced").intent)
        #expect(session.source == .builtInDefaults)
        #expect(session.modelOverrideApplied)
    }

    @Test("apply persists operator overrides and reloads them")
    func applyPersistsOperatorOverridesAndReloadsThem() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-serving-defaults-persist-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("gateway-serving-defaults.json")
        let store = GatewayServingDefaultsStore(
            storeURL: storeURL,
            defaults: [:],
            nowUnixMS: { 1_717_181_900_000 }
        )

        var command = Melix_Controlplane_V1_ApplyServingDefaults()
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        command.temperature = 0.4
        command.topP = 0.91
        command.maxTokens = 640
        command.streamIntervalTokens = 3
        command.maxConcurrentRequests = 6
        command.concurrentProcessingEnabled = true
        command.prefillBatchSize = 3
        command.completionBatchSize = 2
        command.accelerationMode = .speculativeDecode
        command.accelerationProfile = "throughput"
        command.draftModelID = "melix-dev-draft"
        command.numDraftTokens = 6
        try await store.apply(command: command)

        let reloaded = GatewayServingDefaultsStore(storeURL: storeURL, defaults: [:])
        var modelSettings = Melix_Controlplane_V1_ModelSettings()
        modelSettings.defaultAccelerationMode = .unspecified
        let requested = await reloaded.requestedDefaults()
        let summary = await reloaded.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            defaultModelIDs: [ServerSessionRuntimeStore.defaultServerSessionID: "melix-dev-text"],
            modelSettingsByModelID: ["melix-dev-text": modelSettings]
        )
        let session = try #require(summary.sessions.first)

        #expect(requested.temperature == 0.4)
        #expect(requested.topP == 0.91)
        #expect(requested.maxTokens == 640)
        #expect(requested.streamIntervalTokens == 3)
        #expect(requested.maxConcurrentRequests == 6)
        #expect(requested.concurrentProcessingEnabled == true)
        #expect(requested.prefillBatchSize == 3)
        #expect(requested.completionBatchSize == 2)
        #expect(requested.accelerationMode == .speculativeDecode)
        #expect(requested.accelerationProfile == "throughput")
        #expect(requested.draftModelID == "melix-dev-draft")
        #expect(requested.numDraftTokens == 6)
        #expect(session.source == .operatorOverride)
        #expect(session.updatedAtUnixMs == 1_717_181_900_000)
        #expect(session.requestedConcurrentProcessingEnabled)
        #expect(session.requestedPrefillBatchSize == 3)
        #expect(session.requestedCompletionBatchSize == 2)
        #expect(session.requestedAccelerationMode == .speculativeDecode)
        #expect(session.requestedAccelerationProfile == "throughput")
        #expect(session.requestedDraftModelID == "melix-dev-draft")
        #expect(session.requestedNumDraftTokens == 6)
        #expect(session.effectiveMaxConcurrentRequests == 2)
        #expect(session.effectivePrefillBatchSize == 2)
        #expect(session.effectiveCompletionBatchSize == 2)
        #expect(session.effectiveAccelerationMode == .speculativeDecode)
        #expect(session.effectiveAccelerationProfile == "throughput")
        #expect(session.effectiveDraftModelID == "melix-dev-draft")
        #expect(session.effectiveNumDraftTokens == 6)
    }

    @Test("environment profile defaults resolve before explicit environment overrides")
    func environmentProfileDefaultsResolveBeforeExplicitEnvironmentOverrides() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-serving-defaults-profile-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [
                "MELIX_GATEWAY_ACCELERATION_PROFILE": "low_memory",
                "MELIX_GATEWAY_MAX_CONCURRENT_REQUESTS": "3",
            ]
        )
        let requested = await store.requestedDefaults()
        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            defaultModelIDs: [:],
            modelSettingsByModelID: [:]
        )
        let session = try #require(summary.sessions.first)

        #expect(requested.accelerationProfile == "low-memory")
        #expect(requested.concurrentProcessingEnabled == false)
        #expect(requested.maxConcurrentRequests == 3)
        #expect(requested.prefillBatchSize == 1)
        #expect(requested.completionBatchSize == 1)
        #expect(session.requestedAccelerationProfile == "low-memory")
        #expect(session.effectiveAccelerationProfile == "low-memory")
        #expect(session.effectiveConcurrentProcessingEnabled == false)
        #expect(session.effectiveMaxConcurrentRequests == 1)
        #expect(session.source == .environmentDefaults)
    }

    @Test("apply rejects invalid typed payload values")
    func applyRejectsInvalidTypedPayloadValues() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-serving-defaults-invalid-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )

        var invalidTopP = Melix_Controlplane_V1_ApplyServingDefaults()
        invalidTopP.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        invalidTopP.temperature = 0.3
        invalidTopP.topP = 0
        invalidTopP.maxTokens = 128
        invalidTopP.streamIntervalTokens = 1
        invalidTopP.maxConcurrentRequests = 2
        invalidTopP.concurrentProcessingEnabled = true
        invalidTopP.prefillBatchSize = 2
        invalidTopP.completionBatchSize = 2

        var invalidConcurrency = invalidTopP
        invalidConcurrency.topP = 0.9
        invalidConcurrency.maxConcurrentRequests = 0

        var invalidPrefillBatchSize = invalidTopP
        invalidPrefillBatchSize.topP = 0.9
        invalidPrefillBatchSize.prefillBatchSize = 0

        var invalidAccelerationProfile = invalidTopP
        invalidAccelerationProfile.topP = 0.9
        invalidAccelerationProfile.accelerationProfile = "fastest"

        await #expect(throws: ServingDefaultsValidationError.invalidTopP) {
            try await store.apply(command: invalidTopP)
        }
        await #expect(throws: ServingDefaultsValidationError.invalidMaxConcurrentRequests) {
            try await store.apply(command: invalidConcurrency)
        }
        await #expect(throws: ServingDefaultsValidationError.invalidPrefillBatchSize) {
            try await store.apply(command: invalidPrefillBatchSize)
        }
        await #expect(throws: ServingDefaultsValidationError.invalidAccelerationProfile) {
            try await store.apply(command: invalidAccelerationProfile)
        }
    }

    @Test("summary collapses batching defaults when concurrent processing is disabled")
    func summaryCollapsesBatchingDefaultsWhenConcurrentProcessingIsDisabled() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-serving-defaults-disabled-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )

        var command = Melix_Controlplane_V1_ApplyServingDefaults()
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        command.temperature = 0.4
        command.topP = 0.9
        command.maxTokens = 256
        command.streamIntervalTokens = 2
        command.maxConcurrentRequests = 6
        command.concurrentProcessingEnabled = false
        command.prefillBatchSize = 4
        command.completionBatchSize = 3
        try await store.apply(command: command)

        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            defaultModelIDs: [:],
            modelSettingsByModelID: [:]
        )
        let session = try #require(summary.sessions.first)

        #expect(session.requestedConcurrentProcessingEnabled == false)
        #expect(session.requestedPrefillBatchSize == 4)
        #expect(session.requestedCompletionBatchSize == 3)
        #expect(session.effectiveConcurrentProcessingEnabled == false)
        #expect(session.effectiveMaxConcurrentRequests == 1)
        #expect(session.effectivePrefillBatchSize == 1)
        #expect(session.effectiveCompletionBatchSize == 1)
    }

    @Test("summary projects gateway override receipts for suppressed stale settings")
    func summaryProjectsGatewayOverrideReceiptsForSuppressedStaleSettings() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-serving-defaults-override-receipts-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )

        var command = Melix_Controlplane_V1_ApplyServingDefaults()
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        command.temperature = 0.4
        command.topP = 0.9
        command.maxTokens = 256
        command.streamIntervalTokens = 2
        command.maxConcurrentRequests = 6
        command.concurrentProcessingEnabled = true
        command.prefillBatchSize = 3
        command.completionBatchSize = 2
        command.accelerationMode = .speculativeDecode
        command.draftModelID = "melix-dev-draft"
        command.numDraftTokens = 6
        try await store.apply(command: command)

        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            defaultModelIDs: [:],
            modelSettingsByModelID: [:]
        )
        let session = try #require(summary.sessions.first)

        #expect(session.effectiveMaxConcurrentRequests == 2)
        #expect(session.effectivePrefillBatchSize == 2)
        #expect(session.effectiveCompletionBatchSize == 2)
        #expect(session.effectiveAccelerationMode == .baseline)
        #expect(session.effectiveDraftModelID.isEmpty)
        #expect(session.effectiveNumDraftTokens == 0)
        #expect(session.overrideReceiptSchema == "melix.gateway_override_receipt.v1")
        #expect(session.suppressedOverrides == "max_concurrent_requests,prefill_batch_size,speculative_decode")
        #expect(session.batchDisabledReason == "incompatible_batch_size")
        #expect(session.speculativeDisabledReason == "unsupported_route")
        #expect(session.multimodalRoutePolicy == "auto")
        #expect(session.effectiveMultimodalRoute == "swift_text")
        #expect(session.speculativeRoutePolicy == "auto")
        #expect(session.effectiveSpeculativeMode == "baseline")
        #expect(session.cacheQuantizationDisabledReason == "not_configurable")
        #expect(session.pagedCacheDisabledReason == "not_configurable")
    }

    @Test("summary projects model acceleration overrides over speculative gateway defaults")
    func summaryProjectsModelAccelerationOverridesOverSpeculativeGatewayDefaults() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-serving-defaults-accel-override-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )

        var command = Melix_Controlplane_V1_ApplyServingDefaults()
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        command.temperature = 0.4
        command.topP = 0.9
        command.maxTokens = 256
        command.streamIntervalTokens = 2
        command.maxConcurrentRequests = 4
        command.concurrentProcessingEnabled = true
        command.prefillBatchSize = 2
        command.completionBatchSize = 2
        command.accelerationMode = .speculativeDecode
        command.draftModelID = "melix-dev-draft"
        command.numDraftTokens = 6
        try await store.apply(command: command)

        var modelSettings = Melix_Controlplane_V1_ModelSettings()
        modelSettings.defaultAccelerationMode = .baseline

        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            defaultModelIDs: [ServerSessionRuntimeStore.defaultServerSessionID: "melix-dev-text"],
            modelSettingsByModelID: ["melix-dev-text": modelSettings]
        )
        let session = try #require(summary.sessions.first)

        #expect(session.requestedAccelerationMode == .speculativeDecode)
        #expect(session.requestedDraftModelID == "melix-dev-draft")
        #expect(session.requestedNumDraftTokens == 6)
        #expect(session.effectiveAccelerationMode == .baseline)
        #expect(session.effectiveDraftModelID.isEmpty)
        #expect(session.effectiveNumDraftTokens == 0)
        #expect(session.modelOverrideApplied)
    }

    @Test("summary receipts mirror effective speculative defaults")
    func summaryReceiptsMirrorEffectiveSpeculativeDefaults() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-serving-defaults-speculative-receipts-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )

        var command = Melix_Controlplane_V1_ApplyServingDefaults()
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        command.temperature = 0.4
        command.topP = 0.9
        command.maxTokens = 256
        command.streamIntervalTokens = 2
        command.maxConcurrentRequests = 4
        command.concurrentProcessingEnabled = true
        command.prefillBatchSize = 2
        command.completionBatchSize = 2
        command.accelerationMode = .speculativeDecode
        command.draftModelID = "melix-dev-draft"
        command.numDraftTokens = 6
        try await store.apply(command: command)

        var modelSettings = Melix_Controlplane_V1_ModelSettings()
        modelSettings.defaultAccelerationMode = .unspecified

        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            defaultModelIDs: [ServerSessionRuntimeStore.defaultServerSessionID: "melix-dev-text"],
            modelSettingsByModelID: ["melix-dev-text": modelSettings]
        )
        let session = try #require(summary.sessions.first)

        #expect(session.effectiveAccelerationMode == .speculativeDecode)
        #expect(session.effectiveSpeculativeMode == "speculative_decode")
        #expect(session.effectiveDraftModelID == "melix-dev-draft")
        #expect(session.effectiveNumDraftTokens == 6)
        #expect(session.speculativeDisabledReason.isEmpty)
        #expect(!session.suppressedOverrides.split(separator: ",").contains("speculative_decode"))
    }

    @Test("summary persists route policies as effective override receipts")
    func summaryPersistsRoutePoliciesAsEffectiveOverrideReceipts() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-serving-defaults-route-policy-receipts-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = GatewayServingDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("gateway-serving-defaults.json"),
            defaults: [:]
        )

        var command = Melix_Controlplane_V1_ApplyServingDefaults()
        command.serverSessionID = ServerSessionRuntimeStore.defaultServerSessionID
        command.temperature = 0.4
        command.topP = 0.9
        command.maxTokens = 256
        command.streamIntervalTokens = 2
        command.maxConcurrentRequests = 4
        command.concurrentProcessingEnabled = true
        command.prefillBatchSize = 2
        command.completionBatchSize = 2
        command.accelerationMode = .speculativeDecode
        command.draftModelID = "melix-dev-draft"
        command.numDraftTokens = 6
        command.multimodalRoutePolicy = "off"
        command.speculativeRoutePolicy = "off"
        try await store.apply(command: command)

        var modelSettings = Melix_Controlplane_V1_ModelSettings()
        modelSettings.defaultAccelerationMode = .unspecified

        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            defaultModelIDs: [ServerSessionRuntimeStore.defaultServerSessionID: "melix-dev-text"],
            modelSettingsByModelID: ["melix-dev-text": modelSettings]
        )
        let session = try #require(summary.sessions.first)

        #expect(session.multimodalRoutePolicy == "off")
        #expect(session.speculativeRoutePolicy == "off")
        #expect(session.effectiveMultimodalRoute == "off")
        #expect(session.effectiveSpeculativeMode == "baseline")
        #expect(session.speculativeDisabledReason == "operator_disabled")
        #expect(session.suppressedOverrides.split(separator: ",").contains("speculative_decode"))
    }

    @Test("summary loads legacy serving default records without route policies")
    func summaryLoadsLegacyServingDefaultRecordsWithoutRoutePolicies() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-serving-defaults-legacy-route-policy-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("gateway-serving-defaults.json")
        try Data(
            """
            {
              "schema_version": 1,
              "sessions": [
                {
                  "server_session_id": "\(ServerSessionRuntimeStore.defaultServerSessionID)",
                  "temperature": 0.4,
                  "top_p": 0.9,
                  "max_tokens": 256,
                  "stream_interval_tokens": 2,
                  "max_concurrent_requests": 2,
                  "concurrent_processing_enabled": true,
                  "prefill_batch_size": 2,
                  "completion_batch_size": 2,
                  "acceleration_mode": 1,
                  "draft_model_id": "",
                  "num_draft_tokens": 0,
                  "acceleration_profile": "balanced",
                  "source": 4,
                  "updated_at_unix_ms": 12345
                }
              ]
            }
            """.utf8
        ).write(to: storeURL)

        let store = GatewayServingDefaultsStore(
            storeURL: storeURL,
            defaults: [:]
        )
        let summary = await store.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            defaultModelIDs: [:],
            modelSettingsByModelID: [:]
        )
        let session = try #require(summary.sessions.first)

        #expect(session.source == .operatorOverride)
        #expect(session.multimodalRoutePolicy == "auto")
        #expect(session.speculativeRoutePolicy == "auto")
        #expect(session.effectiveMultimodalRoute == "swift_text")
    }
}
