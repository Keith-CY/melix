import Dispatch
import Foundation
import MelixControlPlaneProtocol

struct TextContextWindowInference: Sendable, Equatable {
    let tokens: UInt32
    let source: String
}

private actor TextContextWindowInferenceCache {
    private enum Entry {
        case loading(Task<TextContextWindowInference?, Never>)
        case loaded(TextContextWindowInference?)
    }

    private let queue = DispatchQueue(
        label: "dev.melix.text-execution-model.context-window-inference",
        qos: .utility
    )
    private var entries: [String: Entry] = [:]

    func value(
        for modelPath: String,
        load: @escaping @Sendable () -> TextContextWindowInference?
    ) async -> TextContextWindowInference? {
        if let entry = entries[modelPath] {
            switch entry {
            case .loading(let task):
                return await task.value
            case .loaded(let value):
                return value
            }
        }

        let queue = queue
        let task = Task(priority: .utility) {
            await withCheckedContinuation { continuation in
                queue.async {
                    continuation.resume(returning: load())
                }
            }
        }
        entries[modelPath] = .loading(task)
        let value = await task.value
        entries[modelPath] = .loaded(value)
        return value
    }
}

actor TextExecutionModelResolver {
    private let modelCatalog: ModelCatalog
    private let contextWindowInferenceCache = TextContextWindowInferenceCache()

    init(modelCatalog: ModelCatalog) {
        self.modelCatalog = modelCatalog
    }

    func executionModelID(
        for servedModelID: String,
        requestModalities: Set<Melix_Controlplane_V1_RouteModality>
    ) async -> String {
        guard
            let source = await modelCatalog.model(id: servedModelID),
            let companionRoute = textCompanionRoute(
                for: source,
                requestModalities: requestModalities
            ),
            shouldMaterializeTextCompanion(for: source)
        else {
            return servedModelID
        }

        let companionID = "\(servedModelID)#text"
        if await modelCatalog.model(id: companionID) == nil {
            let companion = await makeTextCompanionModel(
                from: source,
                companionID: companionID,
                route: companionRoute
            )
            await modelCatalog.registerModel(companion, reason: "text_companion_registered")
        }
        return companionID
    }

    func servedModelID(forExecutionModelID executionModelID: String) async -> String {
        guard
            let executionModel = await modelCatalog.model(id: executionModelID),
            normalizedIdentifier(executionModel.settings.ext["melix.companion.role"]) == "text_only",
            let sourceModelID = executionModel.settings.ext["melix.companion.source_model_id"]?
                .trimmingCharacters(in: .whitespacesAndNewlines),
            !sourceModelID.isEmpty
        else {
            return executionModelID
        }
        return sourceModelID
    }

    private func textCompanionRoute(
        for model: Melix_Controlplane_V1_ModelSummary,
        requestModalities: Set<Melix_Controlplane_V1_RouteModality>
    ) -> Melix_Controlplane_V1_RequestRouteDeclaration? {
        let effectiveModalities = requestModalities.isEmpty ? Set([.text]) : requestModalities
        return model.requestRoutes.first { route in
            guard route.task == .generateText,
                  route.workerFamily == .text,
                  route.isTextCompanion
            else {
                return false
            }
            let supported = Set(route.supportedModalities.filter { $0 != .unspecified })
            guard effectiveModalities.isSubset(of: supported) else {
                return false
            }
            let required = Set(route.requiresAnyModality.filter { $0 != .unspecified })
            return required.isEmpty || !effectiveModalities.isDisjoint(with: required)
        }
    }

    private func shouldMaterializeTextCompanion(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> Bool {
        guard modelRouteKind(for: model) == .pythonVLM else {
            return false
        }
        guard !isFalse(model.settings.ext["melix.vlm.text_companion.enabled"]) else {
            return false
        }
        guard normalizedIdentifier(model.settings.ext["vision_family_id"]) == "gemma4-v1" else {
            return false
        }
        return normalizedIdentifier(model.settings.ext["melix.vlm.backend_id"]) == "mlx_vlm"
    }

    private func makeTextCompanionModel(
        from source: Melix_Controlplane_V1_ModelSummary,
        companionID: String,
        route: Melix_Controlplane_V1_RequestRouteDeclaration
    ) async -> Melix_Controlplane_V1_ModelSummary {
        var companion = source
        companion.modelID = companionID
        companion.kind = "text"
        companion.state = .modelDiscovered
        companion.pinned = false
        companion.inflightRequests = 0
        companion.estimatedBytes = 0
        companion.capabilityClass = .modelCapabilityText
        companion.routeClass = .workerRouteSwiftText
        companion.features = source.features.contains("chat") ? source.features : source.features + ["chat"]
        if let inferredContext = await inferredTextMaxContext(fromModelPath: source.settings.ext["melix.model_path"]) {
            companion.maxContext = max(companion.maxContext, inferredContext.tokens)
            companion.settings.ext["melix.context_window.source"] = inferredContext.source
        }
        companion.supportedModalities = ["text"]
        companion.supportedTasks = ["generate"]
        companion.requestRoutes = [route]
        companion.settings.alias = source.settings.alias.isEmpty
            ? "\(source.modelID) text"
            : "\(source.settings.alias) text"
        companion.settings.memoryPolicy = .memoryResidencyEvictable
        companion.settings.defaultAccelerationMode = .baseline
        companion.settings.accelerationProfileID = ""
        companion.settings.ext["melix.companion.source_model_id"] = source.modelID
        companion.settings.ext["melix.companion.role"] = "text_only"
        companion.settings.ext["melix.visibility"] = "internal"
        companion.settings.ext["melix.capability.route_kind"] = WorkerRouteKind.swiftText.metadataIdentifier
        companion.settings.ext["melix.capability.class"] = "text"
        companion.settings.ext["melix.capability.supported_modalities"] = "text"
        companion.settings.ext["melix.capability.supported_tasks"] = "generate"
        companion.settings.ext["melix.capability.supported_parsers"] = "text"
        companion.settings.ext["melix.acceleration.supported_modes"] = "baseline"
        companion.settings.ext.removeValue(forKey: "melix.acceleration.target_capability")
        companion.settings.ext.removeValue(forKey: "melix.acceleration.drafter_capability")
        companion.settings.ext.removeValue(forKey: "melix.acceleration.valid_draft_model_ids")
        companion.settings.ext.removeValue(forKey: "melix.speculative_head.configured")
        companion.settings.ext.removeValue(forKey: "melix.speculative_head.configured_layers")
        companion.settings.ext.removeValue(forKey: "melix.speculative_head.indexed_layers")
        companion.settings.ext.removeValue(forKey: "melix.speculative_head.runtime_available")
        companion.settings.ext.removeValue(forKey: "melix.speculative_head.artifact_available")
        return companion
    }

    private func inferredTextMaxContext(fromModelPath modelPath: String?) async -> TextContextWindowInference? {
        let trimmedPath = modelPath?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !trimmedPath.isEmpty else {
            return nil
        }
        return await contextWindowInferenceCache.value(for: trimmedPath) {
            Self.loadInferredTextMaxContext(fromModelPath: trimmedPath)
        }
    }

    static func loadInferredTextMaxContext(fromModelPath modelPath: String) -> TextContextWindowInference? {
        let configURL = URL(fileURLWithPath: modelPath, isDirectory: true)
            .appendingPathComponent("config.json")
        guard let data = try? Data(contentsOf: configURL),
              let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return nil
        }
        let contextKeys = ["max_position_embeddings", "max_seq_len", "max_seq_length", "seq_length", "n_positions"]
        for key in contextKeys {
            if let value = uint32ConfigValue(root[key]) {
                return TextContextWindowInference(tokens: value, source: "config.\(key)")
            }
        }
        for nestedKey in ["text_config", "language_config", "llm_config"] {
            for key in contextKeys {
                if let object = root[nestedKey] as? [String: Any],
                   let value = uint32ConfigValue(object[key]) {
                    return TextContextWindowInference(
                        tokens: value,
                        source: "config.\(nestedKey).\(key)"
                    )
                }
            }
        }
        return nil
    }

    private static func uint32ConfigValue(_ value: Any?) -> UInt32? {
        switch value {
        case let number as NSNumber:
            let intValue = number.uint64Value
            guard intValue > 0, intValue <= UInt64(UInt32.max) else {
                return nil
            }
            return UInt32(intValue)
        case let string as String:
            return UInt32(string.trimmingCharacters(in: .whitespacesAndNewlines))
        default:
            return nil
        }
    }

    private func modelRouteKind(
        for model: Melix_Controlplane_V1_ModelSummary
    ) -> WorkerRouteKind? {
        if let route = WorkerRouteKind(metadataIdentifier: model.settings.ext["melix.capability.route_kind"]) {
            return route
        }
        if let route = WorkerRouteKind(routeClass: model.routeClass) {
            return route
        }
        return WorkerRouteKind(capabilityIdentifier: model.settings.ext["melix.capability.class"])
    }

    private func isFalse(_ value: String?) -> Bool {
        switch normalizedIdentifier(value) {
        case "0", "false", "no", "off":
            return true
        default:
            return false
        }
    }

    private func normalizedIdentifier(_ value: String?) -> String {
        (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }
}
