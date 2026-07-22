import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Text Execution Model Resolver")
struct TextExecutionModelResolverTests {
    @Test("resolver keeps the served model when companion prerequisites are absent")
    func keepsServedModelWhenCompanionPrerequisitesAreAbsent() async throws {
        let missingCatalog = ModelCatalog(seedModels: [])
        let missingResolver = TextExecutionModelResolver(modelCatalog: missingCatalog)
        #expect(
            await missingResolver.executionModelID(
                for: "missing-model",
                requestModalities: [.text]
            ) == "missing-model"
        )

        var invalidModels: [Melix_Controlplane_V1_ModelSummary] = []

        var noRoutes = makeGemma4Model(id: "no-routes")
        noRoutes.requestRoutes = []
        invalidModels.append(noRoutes)

        var wrongTask = makeGemma4Model(id: "wrong-task")
        wrongTask.requestRoutes[0].task = .generateMultimodal
        invalidModels.append(wrongTask)

        var wrongWorkerFamily = makeGemma4Model(id: "wrong-worker-family")
        wrongWorkerFamily.requestRoutes[0].workerFamily = .vision
        invalidModels.append(wrongWorkerFamily)

        var notCompanion = makeGemma4Model(id: "not-companion")
        notCompanion.requestRoutes[0].isTextCompanion = false
        invalidModels.append(notCompanion)

        var unsupportedModality = makeGemma4Model(id: "unsupported-modality")
        unsupportedModality.requestRoutes[0].supportedModalities = [.image]
        invalidModels.append(unsupportedModality)

        var missingRequiredModality = makeGemma4Model(id: "missing-required-modality")
        missingRequiredModality.requestRoutes[0].requiresAnyModality = [.image]
        invalidModels.append(missingRequiredModality)

        var wrongRoute = makeGemma4Model(id: "wrong-route")
        wrongRoute.settings.ext["melix.capability.route_kind"] = "swift_text"
        invalidModels.append(wrongRoute)

        for falseValue in ["0", " FALSE ", "No", "off"] {
            var disabled = makeGemma4Model(id: "disabled-\(falseValue.trimmingCharacters(in: .whitespaces))")
            disabled.settings.ext["melix.vlm.text_companion.enabled"] = falseValue
            invalidModels.append(disabled)
        }

        var wrongFamily = makeGemma4Model(id: "wrong-family")
        wrongFamily.settings.ext["vision_family_id"] = "gemma3-v1"
        invalidModels.append(wrongFamily)

        var wrongBackend = makeGemma4Model(id: "wrong-backend")
        wrongBackend.settings.ext["melix.vlm.backend_id"] = "transformers"
        invalidModels.append(wrongBackend)

        let catalog = ModelCatalog(seedModels: invalidModels)
        let resolver = TextExecutionModelResolver(modelCatalog: catalog)
        for model in invalidModels {
            let resolvedID = await resolver.executionModelID(
                for: model.modelID,
                requestModalities: [.text]
            )
            #expect(resolvedID == model.modelID)
            #expect(await catalog.model(id: "\(model.modelID)#text") == nil)
        }
    }

    @Test("resolver materializes one normalized Swift text companion and reuses it")
    func materializesAndReusesNormalizedCompanion() async throws {
        var source = makeGemma4Model(id: "gemma4-source")
        source.kind = "vlm"
        source.state = .modelWarm
        source.pinned = true
        source.inflightRequests = 7
        source.estimatedBytes = 99
        source.features = ["vision"]
        source.maxContext = 32_768
        source.settings.alias = "Gemma 4"
        source.settings.memoryPolicy = .memoryResidencyPinned
        source.settings.defaultAccelerationMode = .speculativeDecode
        source.settings.accelerationProfileID = "fast"
        source.settings.ext["melix.acceleration.target_capability"] = "target"
        source.settings.ext["melix.acceleration.drafter_capability"] = "draft"
        source.settings.ext["melix.acceleration.valid_draft_model_ids"] = "draft-model"
        source.settings.ext["melix.speculative_head.configured"] = "true"
        source.settings.ext["melix.speculative_head.configured_layers"] = "4"
        source.settings.ext["melix.speculative_head.indexed_layers"] = "4"
        source.settings.ext["melix.speculative_head.runtime_available"] = "true"
        source.settings.ext["melix.speculative_head.artifact_available"] = "true"
        source.settings.ext.removeValue(forKey: "melix.visibility")

        let catalog = ModelCatalog(seedModels: [source])
        let resolver = TextExecutionModelResolver(modelCatalog: catalog)
        let firstID = await resolver.executionModelID(for: source.modelID, requestModalities: [])
        let first = try #require(await catalog.model(id: firstID))
        let secondID = await resolver.executionModelID(for: source.modelID, requestModalities: [.text])
        let second = try #require(await catalog.model(id: secondID))

        #expect(firstID == "gemma4-source#text")
        #expect(secondID == firstID)
        #expect(second == first)
        #expect(first.kind == "text")
        #expect(first.state == .modelDiscovered)
        #expect(first.pinned == false)
        #expect(first.inflightRequests == 0)
        #expect(first.estimatedBytes == 0)
        #expect(first.capabilityClass == .modelCapabilityText)
        #expect(first.routeClass == .workerRouteSwiftText)
        #expect(first.features == ["vision", "chat"])
        #expect(first.maxContext == 32_768)
        #expect(first.supportedModalities == ["text"])
        #expect(first.supportedTasks == ["generate"])
        #expect(first.requestRoutes.count == 1)
        #expect(first.requestRoutes[0].isTextCompanion)
        #expect(first.settings.alias == "Gemma 4 text")
        #expect(first.settings.memoryPolicy == .memoryResidencyEvictable)
        #expect(first.settings.defaultAccelerationMode == .baseline)
        #expect(first.settings.accelerationProfileID.isEmpty)
        #expect(first.settings.ext["melix.companion.source_model_id"] == source.modelID)
        #expect(first.settings.ext["melix.companion.role"] == "text_only")
        #expect(first.settings.ext["melix.visibility"] == "internal")
        #expect(ModelCatalogPresentation.isUserVisible(first) == false)
        #expect(first.settings.ext["melix.capability.route_kind"] == "swift_text")
        #expect(first.settings.ext["melix.capability.class"] == "text")
        #expect(first.settings.ext["melix.capability.supported_modalities"] == "text")
        #expect(first.settings.ext["melix.capability.supported_tasks"] == "generate")
        #expect(first.settings.ext["melix.capability.supported_parsers"] == "text")
        #expect(first.settings.ext["melix.acceleration.supported_modes"] == "baseline")
        #expect(first.settings.ext["melix.acceleration.target_capability"] == nil)
        #expect(first.settings.ext["melix.acceleration.drafter_capability"] == nil)
        #expect(first.settings.ext["melix.acceleration.valid_draft_model_ids"] == nil)
        #expect(first.settings.ext["melix.speculative_head.configured"] == nil)
        #expect(first.settings.ext["melix.speculative_head.configured_layers"] == nil)
        #expect(first.settings.ext["melix.speculative_head.indexed_layers"] == nil)
        #expect(first.settings.ext["melix.speculative_head.runtime_available"] == nil)
        #expect(first.settings.ext["melix.speculative_head.artifact_available"] == nil)
        #expect(await resolver.servedModelID(forExecutionModelID: firstID) == source.modelID)
        #expect(await resolver.servedModelID(forExecutionModelID: source.modelID) == source.modelID)
        #expect(await resolver.servedModelID(forExecutionModelID: "missing-model") == "missing-model")

        var routeClassFallback = makeGemma4Model(id: "gemma4-route-class-fallback")
        routeClassFallback.settings.alias = ""
        routeClassFallback.settings.ext.removeValue(forKey: "melix.capability.route_kind")
        await catalog.registerModel(routeClassFallback, reason: "test_model_registered")
        let routeClassFallbackID = await resolver.executionModelID(
            for: routeClassFallback.modelID,
            requestModalities: [.text]
        )
        let routeClassCompanion = try #require(await catalog.model(id: routeClassFallbackID))
        #expect(routeClassCompanion.settings.alias == "gemma4-route-class-fallback text")

        var capabilityFallback = makeGemma4Model(id: "gemma4-capability-fallback")
        capabilityFallback.routeClass = .unspecified
        capabilityFallback.settings.ext.removeValue(forKey: "melix.capability.route_kind")
        capabilityFallback.settings.ext["melix.capability.class"] = "vlm"
        await catalog.registerModel(capabilityFallback, reason: "test_model_registered")
        #expect(
            await resolver.executionModelID(
                for: capabilityFallback.modelID,
                requestModalities: [.text]
            ) == "gemma4-capability-fallback#text"
        )
    }

    @Test("context inference accepts supported top-level and nested keys")
    func infersSupportedContextWindowKeys() throws {
        let cases: [(String, String, UInt32, String)] = [
            ("top-max-position", "{\"max_position_embeddings\": 131072}", 131_072, "config.max_position_embeddings"),
            ("top-max-seq-len", "{\"max_seq_len\": \"65536\"}", 65_536, "config.max_seq_len"),
            ("top-max-seq-length", "{\"max_seq_length\": 32768}", 32_768, "config.max_seq_length"),
            ("top-seq-length", "{\"seq_length\": 16384}", 16_384, "config.seq_length"),
            ("top-n-positions", "{\"n_positions\": 8192}", 8_192, "config.n_positions"),
            ("text-config", "{\"text_config\": {\"max_position_embeddings\": 262144}}", 262_144, "config.text_config.max_position_embeddings"),
            ("language-config", "{\"language_config\": {\"max_seq_len\": 4096}}", 4_096, "config.language_config.max_seq_len"),
            ("llm-config", "{\"llm_config\": {\"n_positions\": \" 2048 \"}}", 2_048, "config.llm_config.n_positions"),
        ]

        for (name, config, tokens, source) in cases {
            let directory = try makeConfigDirectory(name: name, contents: config)
            let inference = try #require(
                TextExecutionModelResolver.loadInferredTextMaxContext(fromModelPath: directory.path)
            )
            #expect(inference == TextContextWindowInference(tokens: tokens, source: source))
        }
    }

    @Test("context inference rejects missing malformed and invalid config values")
    func rejectsInvalidContextWindowConfigurations() throws {
        let missingDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-text-resolver-missing-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: missingDirectory, withIntermediateDirectories: true)
        #expect(TextExecutionModelResolver.loadInferredTextMaxContext(fromModelPath: missingDirectory.path) == nil)

        let invalidConfigs = [
            "not-json",
            "[]",
            "{\"max_position_embeddings\": 0}",
            "{\"max_position_embeddings\": -1}",
            "{\"max_position_embeddings\": 4294967296}",
            "{\"max_position_embeddings\": \"not-a-number\"}",
            "{\"max_position_embeddings\": {\"value\": 8192}}",
            "{\"text_config\": \"not-an-object\"}",
            "{}",
        ]
        for (index, config) in invalidConfigs.enumerated() {
            let directory = try makeConfigDirectory(name: "invalid-\(index)", contents: config)
            #expect(TextExecutionModelResolver.loadInferredTextMaxContext(fromModelPath: directory.path) == nil)
        }
    }

    @Test("resolver caches context inference by model path across companion ids")
    func cachesContextInferenceByModelPath() async throws {
        let directory = try makeConfigDirectory(
            name: "cache",
            contents: "{\"text_config\": {\"max_position_embeddings\": 131072}}"
        )
        var first = makeGemma4Model(id: "gemma4-cache-first")
        first.maxContext = 8_192
        first.settings.ext["melix.model_path"] = directory.path
        var second = makeGemma4Model(id: "gemma4-cache-second")
        second.maxContext = 8_192
        second.settings.ext["melix.model_path"] = directory.path

        let catalog = ModelCatalog(seedModels: [first, second])
        let resolver = TextExecutionModelResolver(modelCatalog: catalog)
        async let firstID = resolver.executionModelID(for: first.modelID, requestModalities: [.text])
        async let secondID = resolver.executionModelID(for: second.modelID, requestModalities: [.text])
        let resolvedIDs = await [firstID, secondID]
        for resolvedID in resolvedIDs {
            let companion = try #require(await catalog.model(id: resolvedID))
            #expect(companion.maxContext == 131_072)
            #expect(companion.settings.ext["melix.context_window.source"] == "config.text_config.max_position_embeddings")
        }

        try "{\"text_config\": {\"max_position_embeddings\": 4096}}".write(
            to: directory.appendingPathComponent("config.json"),
            atomically: true,
            encoding: .utf8
        )
        var third = makeGemma4Model(id: "gemma4-cache-third")
        third.maxContext = 8_192
        third.settings.ext["melix.model_path"] = directory.path
        await catalog.registerModel(third, reason: "test_model_registered")

        let thirdID = await resolver.executionModelID(for: third.modelID, requestModalities: [.text])
        let thirdCompanion = try #require(await catalog.model(id: thirdID))
        #expect(thirdCompanion.maxContext == 131_072)
        #expect(thirdCompanion.settings.ext["melix.context_window.source"] == "config.text_config.max_position_embeddings")
    }

    private func makeGemma4Model(id: String) -> Melix_Controlplane_V1_ModelSummary {
        var model = ModelCatalog.devVLMModel()
        model.modelID = id
        model.settings.ext["vision_family_id"] = " Gemma4-V1 "
        model.settings.ext["melix.vlm.backend_id"] = " MLX_VLM "
        model.settings.ext.removeValue(forKey: "melix.vlm.text_companion.enabled")
        return model
    }

    private func makeConfigDirectory(name: String, contents: String) throws -> URL {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-text-resolver-\(name)-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        try contents.write(
            to: directory.appendingPathComponent("config.json"),
            atomically: true,
            encoding: .utf8
        )
        return directory
    }
}
