import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Image Defaults Store")
struct ImageDefaultsStoreTests {
    @Test("environment initializer defaults store under MelixHome config")
    func environmentInitializerDefaultsStoreUnderMelixHomeConfig() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-image-defaults-home-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = ImageDefaultsStore(environment: [
            "HOME": temporaryRoot.path,
            "MELIX_APP_SUPPORT_DIR": temporaryRoot.appendingPathComponent("ignored-app-support").path,
        ])

        #expect(
            await store.storePath()
                == temporaryRoot.appendingPathComponent(".melix/config/image-defaults.json").path
        )
    }

    @Test("summary projects built-in defaults and role-aware image models when no operator override exists")
    func summaryProjectsBuiltInDefaultsAndRoleAwareImageModels() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-image-defaults-builtins-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        var qwen = ModelCatalog.devImageModel(environment: [
            "MELIX_DEV_IMAGE_FAMILY_ID": "qwenimage-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/qwen-image-dev",
        ])
        qwen.modelID = "melix-qwen-image"
        var fill = ModelCatalog.devImageModel(environment: [
            "MELIX_DEV_IMAGE_FAMILY_ID": "fill-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/fill-dev",
            "MELIX_DEV_IMAGE_TASK_KIND": "image-text-to-image",
        ])
        fill.modelID = "melix-fill-image"
        let store = ImageDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("image-defaults.json"),
            defaults: [:]
        )

        let summary = await store.summary(models: [qwen, fill])
        let policy = await store.resolvedDefaults(models: [qwen, fill])

        #expect(summary.requestedGenerateModelID.isEmpty)
        #expect(summary.requestedEditModelID.isEmpty)
        #expect(summary.requestedSize == "1024x1024")
        #expect(summary.requestedSteps == 28)
        #expect(summary.requestedGuidance == 7.5)
        #expect(summary.requestedStrength == 1)
        #expect(summary.effectiveGenerateModelID == qwen.modelID)
        #expect(summary.effectiveEditModelID == fill.modelID)
        #expect(summary.effectiveSize == "1024x1024")
        #expect(summary.effectiveSteps == 28)
        #expect(summary.effectiveGuidance == 7.5)
        #expect(summary.effectiveStrength == 1)
        #expect(summary.source == .builtInDefaults)
        #expect(policy.generateModelID == qwen.modelID)
        #expect(policy.editModelID == fill.modelID)
    }

    @Test("apply persists operator overrides and reloads them")
    func applyPersistsOperatorOverridesAndReloadsThem() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-image-defaults-persist-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let storeURL = temporaryRoot.appendingPathComponent("image-defaults.json")
        var qwen = ModelCatalog.devImageModel(environment: [
            "MELIX_DEV_IMAGE_FAMILY_ID": "qwenimage-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/qwen-image-dev",
        ])
        qwen.modelID = "melix-qwen-image"
        var fill = ModelCatalog.devImageModel(environment: [
            "MELIX_DEV_IMAGE_FAMILY_ID": "fill-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/fill-dev",
            "MELIX_DEV_IMAGE_TASK_KIND": "image-text-to-image",
        ])
        fill.modelID = "melix-fill-image"
        let store = ImageDefaultsStore(
            storeURL: storeURL,
            defaults: [:],
            nowUnixMS: { 1_717_181_960_000 }
        )

        try await store.apply(
            command: makeApplyImageDefaultsCommand(
                generateModelID: qwen.modelID,
                editModelID: fill.modelID,
                size: "1536x1024",
                steps: 40,
                guidance: 6.25,
                strength: 0.7,
                negativePrompt: "noise"
            ),
            models: [qwen, fill]
        )

        let reloaded = ImageDefaultsStore(storeURL: storeURL, defaults: [:])
        let summary = await reloaded.summary(models: [qwen, fill])

        #expect(summary.requestedGenerateModelID == qwen.modelID)
        #expect(summary.requestedEditModelID == fill.modelID)
        #expect(summary.requestedSize == "1536x1024")
        #expect(summary.requestedSteps == 40)
        #expect(summary.requestedGuidance == 6.25)
        #expect(summary.requestedStrength == 0.7)
        #expect(summary.requestedNegativePrompt == "noise")
        #expect(summary.effectiveGenerateModelID == qwen.modelID)
        #expect(summary.effectiveEditModelID == fill.modelID)
        #expect(summary.source == .operatorOverride)
        #expect(summary.updatedAtUnixMs == 1_717_181_960_000)
    }

    @Test("apply rejects invalid typed payload values and unsupported workflow models")
    func applyRejectsInvalidTypedPayloadValuesAndUnsupportedWorkflowModels() async throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-image-defaults-invalid-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        var qwen = ModelCatalog.devImageModel(environment: [
            "MELIX_DEV_IMAGE_FAMILY_ID": "qwenimage-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/qwen-image-dev",
        ])
        qwen.modelID = "melix-qwen-image"
        var fill = ModelCatalog.devImageModel(environment: [
            "MELIX_DEV_IMAGE_FAMILY_ID": "fill-v1",
            "MELIX_DEV_IMAGE_MODEL_PATH": "models/fill-dev",
            "MELIX_DEV_IMAGE_TASK_KIND": "image-text-to-image",
        ])
        fill.modelID = "melix-fill-image"
        let text = ModelCatalog.devTextModel()
        let store = ImageDefaultsStore(
            storeURL: temporaryRoot.appendingPathComponent("image-defaults.json"),
            defaults: [:]
        )

        await #expect(throws: ImageDefaultsValidationError.invalidSize) {
            try await store.apply(
                command: makeApplyImageDefaultsCommand(
                    generateModelID: qwen.modelID,
                    editModelID: fill.modelID,
                    size: "wide",
                    steps: 28,
                    guidance: 7.5,
                    strength: 0.8
                ),
                models: [qwen, fill, text]
            )
        }
        await #expect(throws: ImageDefaultsValidationError.invalidSteps) {
            try await store.apply(
                command: makeApplyImageDefaultsCommand(
                    generateModelID: qwen.modelID,
                    editModelID: fill.modelID,
                    size: "1024x1024",
                    steps: 0,
                    guidance: 7.5,
                    strength: 0.8
                ),
                models: [qwen, fill, text]
            )
        }
        await #expect(throws: ImageDefaultsValidationError.unsupportedGenerateModel) {
            try await store.apply(
                command: makeApplyImageDefaultsCommand(
                    generateModelID: fill.modelID,
                    editModelID: fill.modelID,
                    size: "1024x1024",
                    steps: 28,
                    guidance: 7.5,
                    strength: 0.8
                ),
                models: [qwen, fill, text]
            )
        }
        await #expect(throws: ImageDefaultsValidationError.unsupportedEditModel) {
            try await store.apply(
                command: makeApplyImageDefaultsCommand(
                    generateModelID: qwen.modelID,
                    editModelID: qwen.modelID,
                    size: "1024x1024",
                    steps: 28,
                    guidance: 7.5,
                    strength: 0.8
                ),
                models: [qwen, fill, text]
            )
        }
    }

    private func makeApplyImageDefaultsCommand(
        generateModelID: String,
        editModelID: String,
        size: String,
        steps: UInt32,
        guidance: Float,
        strength: Float,
        negativePrompt: String = ""
    ) -> Melix_Controlplane_V1_ApplyImageDefaults {
        var command = Melix_Controlplane_V1_ApplyImageDefaults()
        command.generateModelID = generateModelID
        command.editModelID = editModelID
        command.size = size
        command.steps = steps
        command.guidance = guidance
        command.strength = strength
        command.negativePrompt = negativePrompt
        return command
    }
}
