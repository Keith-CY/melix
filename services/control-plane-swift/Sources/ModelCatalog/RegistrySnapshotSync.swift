import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

enum RegistrySnapshotSync {
    private struct ParsedRegistrySnapshot {
        let roots: [ModelCatalog.RegistryRootState]
        let models: [Melix_Controlplane_V1_ModelSummary]
        let scannedAtUnixMs: Int64
    }

    static func syncModelsIfAvailable(
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry?,
        metricsStore: MetricsStore,
        rescan: Bool = false
    ) async {
        guard
            let workerRegistry,
            let workerClient = await workerRegistry.client(for: .pythonModelOperations) as? any ModelOperationsWorkerClientProtocol
        else {
            return
        }

        let startedAt = Date()
        var workerRequest = Melix_Worker_V1_ConvertModelRequest()
        workerRequest.sourceModel = await sourceModelID(for: modelCatalog)
        workerRequest.generateManifest = true
        workerRequest.ext["operation"] = "registry_snapshot"
        let configuredRoots = await modelCatalog.configuredRegistryRootOverride()
        if let configuredRoots,
           let encodedRoots = encodedRegistryRoots(configuredRoots) {
            workerRequest.ext["melix.registry_roots_json"] = encodedRoots
        }
        if rescan {
            workerRequest.ext["melix.registry_rescan"] = "true"
        }

        do {
            let stream = try await workerClient.convertModel(request: workerRequest)
            var manifestJSON: String?

            for try await event in stream {
                switch event.payload {
                case .manifest(let manifest):
                    manifestJSON = manifest.manifestJson
                case .failed:
                    return
                default:
                    break
                }
            }

            guard
                let manifestJSON,
                await applyManifestJSON(
                    manifestJSON,
                    modelCatalog: modelCatalog,
                    reason: "worker_registry_sync",
                    configuredRootPaths: configuredRoots
                )
            else {
                return
            }

            let discoveredCount = await modelCatalog.listModels().filter {
                $0.settings.ext["melix.registry_root_id"]?.isEmpty == false
            }.count
            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "registry.reload_latency_ms"
            )
            await metricsStore.set(
                Double(discoveredCount),
                forKey: "registry.discovered_model_count"
            )
        } catch {
            return
        }
    }

    static func publicMetadata(from metadata: [String: String]) -> [String: String]? {
        let filtered = metadata.reduce(into: [String: String]()) { partial, item in
            let (key, rawValue) = item
            let value = rawValue.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !value.isEmpty else {
                return
            }
            guard key.hasPrefix("melix.registry_") || key == "melix.model_path" else {
                return
            }
            partial[key] = value
        }
        return filtered.isEmpty ? nil : filtered
    }

    private static func sourceModelID(for modelCatalog: ModelCatalog) async -> String {
        if await modelCatalog.model(id: "melix-dev-model-ops") != nil {
            return "melix-dev-model-ops"
        }
        return "melix-dev-text"
    }

    static func requestedRoots(from metadata: [String: String]) -> [String]? {
        if
            let rawJSON = metadata["melix.registry_roots_json"]?.trimmingCharacters(in: .whitespacesAndNewlines),
            rawJSON.isEmpty == false,
            let data = rawJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [Any]
        {
            let roots = payload.compactMap { element -> String? in
                let value = String(describing: element).trimmingCharacters(in: .whitespacesAndNewlines)
                return value.isEmpty ? nil : value
            }
            return roots
        }

        if
            let legacy = metadata["melix.registry_roots"]?.trimmingCharacters(in: .whitespacesAndNewlines),
            legacy.isEmpty == false
        {
            let roots = legacy
                .split(separator: ":")
                .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { $0.isEmpty == false }
            return roots
        }

        return nil
    }

    static func applyManifestJSON(
        _ manifestJSON: String,
        modelCatalog: ModelCatalog,
        reason: String,
        configuredRootPaths: [String]? = nil
    ) async -> Bool {
        guard let snapshot = parsedRegistrySnapshot(from: manifestJSON) else {
            return false
        }
        await modelCatalog.syncRegistryModels(snapshot.models, reason: reason)
        await modelCatalog.recordRegistrySnapshot(
            roots: snapshot.roots,
            scannedAtUnixMs: snapshot.scannedAtUnixMs,
            configuredRootPaths: configuredRootPaths
        )
        return true
    }

    private static func parsedRegistrySnapshot(from manifestJSON: String) -> ParsedRegistrySnapshot? {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let registryPayload = payload["model_registry"] as? [String: Any]
        else {
            return nil
        }

        let scannedAtUnixMs = int64Value(from: registryPayload["scanned_at_unix_ms"])
        let roots = (registryPayload["roots"] as? [[String: Any]] ?? [])
            .enumerated()
            .compactMap { index, payload in
                rootState(from: payload, fallbackOrder: index + 1)
            }
        let registryModels = (registryPayload["models"] as? [[String: Any]] ?? []).compactMap(modelSummary(from:))
        let derivedModels = (payload["derived_models"] as? [[String: Any]] ?? []).compactMap(derivedModelSummary(from:))
        var seenModelIDs = Set<String>()
        let models = (registryModels + derivedModels).filter { model in
            seenModelIDs.insert(model.modelID).inserted
        }
        return ParsedRegistrySnapshot(
            roots: roots,
            models: models,
            scannedAtUnixMs: scannedAtUnixMs
        )
    }

    private static func rootState(
        from payload: [String: Any],
        fallbackOrder: Int
    ) -> ModelCatalog.RegistryRootState? {
        let rootID = String(describing: payload["root_id"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let rootPath = String(describing: payload["root_path"] ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard rootID.isEmpty == false, rootPath.isEmpty == false else {
            return nil
        }
        let discoveredModelIDs = (payload["discovered_model_ids"] as? [Any] ?? [])
            .compactMap { element in
                let value = String(describing: element).trimmingCharacters(in: .whitespacesAndNewlines)
                return value.isEmpty ? nil : value
            }
        return ModelCatalog.RegistryRootState(
            rootID: rootID,
            rootPath: rootPath,
            rootOrder: Int(uint32Value(from: payload["root_order"])) == 0 ? fallbackOrder : Int(uint32Value(from: payload["root_order"])),
            accessible: boolValue(from: payload["accessible"]),
            errorCode: String(describing: payload["error_code"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines),
            errorMessage: String(describing: payload["error_message"] ?? "").trimmingCharacters(in: .whitespacesAndNewlines),
            discoveredModelIDs: discoveredModelIDs
        )
    }

    private static func modelSummary(
        from payload: [String: Any]
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard
            let modelID = payload["model_id"] as? String,
            !modelID.isEmpty
        else {
            return nil
        }

        let modelKind = ((payload["model_kind"] as? String) ?? "text")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let quantProfileID = ((payload["quant_profile_id"] as? String) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let modelPath = ((payload["model_path"] as? String) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let maxContext = uint32Value(from: payload["max_context"])
        let metadata = stringDictionary(from: payload["ext"])

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = modelID
        model.kind = modelKind.isEmpty ? "text" : modelKind
        model.state = .modelDiscovered
        model.quantProfileID = quantProfileID
        model.maxContext = maxContext
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext = metadata
        if !modelPath.isEmpty && model.settings.ext["melix.model_path"] == nil {
            model.settings.ext["melix.model_path"] = modelPath
        }

        let capabilityIdentifier = metadata["melix.capability.class"]
        let routeKind = metadata["melix.capability.route_kind"]
        model.capabilityClass = capabilityClass(identifier: capabilityIdentifier, kind: model.kind)
        model.routeClass = routeClass(routeKind: routeKind, kind: model.kind)
        model.supportedModalities = supportedModalities(metadata: metadata, kind: model.kind)
        model.supportedTasks = supportedTasks(metadata: metadata, kind: model.kind)
        return model
    }

    private static func derivedModelSummary(
        from payload: [String: Any]
    ) -> Melix_Controlplane_V1_ModelSummary? {
        guard
            let modelID = payload["model_id"] as? String,
            let modelPath = payload["model_path"] as? String
        else {
            return nil
        }

        let normalizedModelID = modelID.trimmingCharacters(in: .whitespacesAndNewlines)
        let normalizedModelPath = modelPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedModelID.isEmpty, !normalizedModelPath.isEmpty else {
            return nil
        }

        var metadata = stringDictionary(from: payload["ext"])
        metadata["melix.model_path"] = normalizedModelPath
        metadata["melix.derived_from_adapter"] = "true"
        if let sourceModel = payload["source_model"] as? String {
            let normalizedSourceModel = sourceModel.trimmingCharacters(in: .whitespacesAndNewlines)
            if !normalizedSourceModel.isEmpty {
                metadata["melix.derived_from_model_id"] = normalizedSourceModel
            }
        }
        if let sourceModelRevision = payload["source_model_revision"] as? String {
            let normalizedSourceModelRevision = sourceModelRevision.trimmingCharacters(in: .whitespacesAndNewlines)
            if !normalizedSourceModelRevision.isEmpty {
                metadata["melix.derived_from_model_revision"] = normalizedSourceModelRevision
            }
        }
        if let alias = payload["derived_model_alias"] as? String {
            let normalizedAlias = alias.trimmingCharacters(in: .whitespacesAndNewlines)
            if !normalizedAlias.isEmpty {
                metadata["melix.derived_model_alias"] = normalizedAlias
            }
        }
        if let activationMode = payload["activation_mode"] as? String {
            let normalizedActivationMode = activationMode.trimmingCharacters(in: .whitespacesAndNewlines)
            if !normalizedActivationMode.isEmpty {
                metadata["melix.activation_mode"] = normalizedActivationMode
            }
        }
        if let adapterManifestPath = payload["adapter_manifest_path"] as? String {
            let normalizedAdapterManifestPath = adapterManifestPath.trimmingCharacters(in: .whitespacesAndNewlines)
            if !normalizedAdapterManifestPath.isEmpty {
                metadata["melix.adapter_manifest_path"] = normalizedAdapterManifestPath
            }
        }
        if let adapterSetHash = payload["adapter_set_hash"] as? String {
            let normalizedAdapterSetHash = adapterSetHash.trimmingCharacters(in: .whitespacesAndNewlines)
            if !normalizedAdapterSetHash.isEmpty {
                metadata["melix.adapter_set_hash"] = normalizedAdapterSetHash
            }
        }
        if payload["remove_supported"] != nil {
            metadata["melix.remove_supported"] = boolValue(from: payload["remove_supported"]) ? "true" : "false"
        }
        if metadata["melix.capability.class"] == nil {
            metadata["melix.capability.class"] = "text"
        }
        if metadata["melix.capability.route_kind"] == nil {
            metadata["melix.capability.route_kind"] = "python_text_compatibility"
        }
        if metadata["melix.capability.supported_modalities"] == nil {
            metadata["melix.capability.supported_modalities"] = "text"
        }
        if metadata["melix.capability.supported_tasks"] == nil {
            metadata["melix.capability.supported_tasks"] = "generate"
        }
        if metadata["melix.capability.supported_parsers"] == nil {
            metadata["melix.capability.supported_parsers"] = "text"
        }

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = normalizedModelID
        model.kind = "text"
        model.state = .modelDiscovered
        model.maxContext = uint32Value(from: payload["max_context"]) == 0 ? 8192 : uint32Value(from: payload["max_context"])
        model.settings.memoryPolicy = .memoryResidencyEvictable
        model.settings.ext = metadata
        model.capabilityClass = capabilityClass(identifier: metadata["melix.capability.class"], kind: model.kind)
        model.routeClass = routeClass(routeKind: metadata["melix.capability.route_kind"], kind: model.kind)
        model.supportedModalities = supportedModalities(metadata: metadata, kind: model.kind)
        model.supportedTasks = supportedTasks(metadata: metadata, kind: model.kind)
        return model
    }

    private static func stringDictionary(from value: Any?) -> [String: String] {
        guard let dictionary = value as? [String: Any] else {
            return [:]
        }
        return dictionary.reduce(into: [:]) { normalized, item in
            let (key, rawValue) = item
            let normalizedKey = key.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !normalizedKey.isEmpty else {
                return
            }
            normalized[normalizedKey] = String(describing: rawValue)
        }
    }

    private static func uint32Value(from value: Any?) -> UInt32 {
        if let number = value as? NSNumber {
            return number.uint32Value
        }
        return UInt32(String(describing: value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0
    }

    private static func int64Value(from value: Any?) -> Int64 {
        if let number = value as? NSNumber {
            return number.int64Value
        }
        return Int64(String(describing: value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)) ?? 0
    }

    private static func boolValue(from value: Any?) -> Bool {
        if let number = value as? NSNumber {
            return number.boolValue
        }
        let normalized = String(describing: value ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return ["1", "true", "yes", "on"].contains(normalized)
    }

    static func encodedRegistryRoots(_ roots: [String]) -> String? {
        guard let data = try? JSONSerialization.data(
            withJSONObject: roots,
            options: [.sortedKeys, .withoutEscapingSlashes]
        ) else {
            return nil
        }
        return String(decoding: data, as: UTF8.self)
    }

    private static func capabilityClass(
        identifier: String?,
        kind: String
    ) -> Melix_Controlplane_V1_ModelCapabilityClass {
        let mapping: [String: Melix_Controlplane_V1_ModelCapabilityClass] = [
            "embedding": .modelCapabilityEmbedding,
            "rerank": .modelCapabilityRerank,
            "model_operations": .modelCapabilityModelOperations,
            "model_ops": .modelCapabilityModelOperations,
            "ocr": .modelCapabilityOcr,
            "vlm": .modelCapabilityVlm,
            "transcription": .modelCapabilityTranscription,
            "speech": .modelCapabilitySpeech,
            "image_generation": .modelCapabilityImageGeneration,
            "image": .modelCapabilityImageGeneration,
            "text": .modelCapabilityText,
        ]
        return mapping[normalizedMetadataValue(identifier)] ?? mapping[normalizedMetadataValue(kind)] ?? .modelCapabilityText
    }

    private static func routeClass(
        routeKind: String?,
        kind: String
    ) -> Melix_Controlplane_V1_WorkerRouteClass {
        let mapping: [String: Melix_Controlplane_V1_WorkerRouteClass] = [
            "python_embedding": .workerRoutePythonEmbedding,
            "python_rerank": .workerRoutePythonRerank,
            "python_model_operations": .workerRoutePythonModelOperations,
            "python_ocr": .workerRoutePythonOcr,
            "python_vlm": .workerRoutePythonVlm,
            "python_transcription": .workerRoutePythonTranscription,
            "python_speech": .workerRoutePythonSpeech,
            "python_image": .workerRoutePythonImage,
            "python_text_compatibility": .workerRoutePythonTextCompatibility,
            "swift_text": .workerRouteSwiftText,
            "embedding": .workerRoutePythonEmbedding,
            "rerank": .workerRoutePythonRerank,
            "model_ops": .workerRoutePythonModelOperations,
            "ocr": .workerRoutePythonOcr,
            "vlm": .workerRoutePythonVlm,
            "transcription": .workerRoutePythonTranscription,
            "speech": .workerRoutePythonSpeech,
            "image": .workerRoutePythonImage,
            "text": .workerRouteSwiftText,
        ]
        return mapping[normalizedMetadataValue(routeKind)] ?? mapping[normalizedMetadataValue(kind)] ?? .workerRouteSwiftText
    }

    private static func supportedModalities(
        metadata: [String: String],
        kind: String
    ) -> [String] {
        let configured = splitMetadataValues(metadata["melix.capability.supported_modalities"])
        if !configured.isEmpty {
            return configured
        }
        let defaults: [String: [String]] = [
            "ocr": ["text", "image"],
            "vlm": ["text", "image"],
            "image": ["text", "image"],
            "transcription": ["audio", "text"],
            "speech": ["text", "audio"],
        ]
        return defaults[normalizedMetadataValue(kind)] ?? ["text"]
    }

    private static func supportedTasks(
        metadata: [String: String],
        kind: String
    ) -> [String] {
        let configured = splitMetadataValues(metadata["melix.capability.supported_tasks"])
        if !configured.isEmpty {
            return configured
        }
        let defaults: [String: [String]] = [
            "embedding": ["embed"],
            "rerank": ["rerank"],
            "ocr": ["ocr", "generate"],
            "vlm": ["vlm", "generate"],
            "transcription": ["transcribe"],
            "speech": ["speak"],
            "image": ["image_generate", "image_edit"],
            "model_ops": ["quantize", "download", "upload"],
        ]
        return defaults[normalizedMetadataValue(kind)] ?? ["generate"]
    }

    private static func splitMetadataValues(_ rawValue: String?) -> [String] {
        normalizedMetadataValue(rawValue)
            .split(separator: ",")
            .map { String($0).trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
    }

    private static func normalizedMetadataValue(_ rawValue: String?) -> String {
        (rawValue ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }
}
