import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

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
            servedModelIDs: [ServerSessionRuntimeStore.defaultServerSessionID: "melix-dev-text"],
            modelSettingsByModelID: ["melix-dev-text": modelSettings]
        )
        let session = try #require(summary.sessions.first)

        #expect(session.serverSessionID == ServerSessionRuntimeStore.defaultServerSessionID)
        #expect(session.requestedTemperature == 0.7)
        #expect(session.requestedTopP == 1.0)
        #expect(session.requestedMaxTokens == 256)
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
        #expect(session.effectiveAccelerationMode == .baseline)
        #expect(session.effectiveDraftModelID.isEmpty)
        #expect(session.effectiveNumDraftTokens == 0)
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
        command.draftModelID = "melix-dev-draft"
        command.numDraftTokens = 6
        try await store.apply(command: command)

        let reloaded = GatewayServingDefaultsStore(storeURL: storeURL, defaults: [:])
        var modelSettings = Melix_Controlplane_V1_ModelSettings()
        modelSettings.defaultAccelerationMode = .unspecified
        let requested = await reloaded.requestedDefaults()
        let summary = await reloaded.summary(
            serverSessionIDs: [ServerSessionRuntimeStore.defaultServerSessionID],
            servedModelIDs: [ServerSessionRuntimeStore.defaultServerSessionID: "melix-dev-text"],
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
        #expect(requested.draftModelID == "melix-dev-draft")
        #expect(requested.numDraftTokens == 6)
        #expect(session.source == .operatorOverride)
        #expect(session.updatedAtUnixMs == 1_717_181_900_000)
        #expect(session.requestedConcurrentProcessingEnabled)
        #expect(session.requestedPrefillBatchSize == 3)
        #expect(session.requestedCompletionBatchSize == 2)
        #expect(session.requestedAccelerationMode == .speculativeDecode)
        #expect(session.requestedDraftModelID == "melix-dev-draft")
        #expect(session.requestedNumDraftTokens == 6)
        #expect(session.effectiveMaxConcurrentRequests == 2)
        #expect(session.effectivePrefillBatchSize == 2)
        #expect(session.effectiveCompletionBatchSize == 2)
        #expect(session.effectiveAccelerationMode == .speculativeDecode)
        #expect(session.effectiveDraftModelID == "melix-dev-draft")
        #expect(session.effectiveNumDraftTokens == 6)
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

        await #expect(throws: ServingDefaultsValidationError.invalidTopP) {
            try await store.apply(command: invalidTopP)
        }
        await #expect(throws: ServingDefaultsValidationError.invalidMaxConcurrentRequests) {
            try await store.apply(command: invalidConcurrency)
        }
        await #expect(throws: ServingDefaultsValidationError.invalidPrefillBatchSize) {
            try await store.apply(command: invalidPrefillBatchSize)
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
            servedModelIDs: [:],
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
            servedModelIDs: [ServerSessionRuntimeStore.defaultServerSessionID: "melix-dev-text"],
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
}
