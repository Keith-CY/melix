import Foundation
import MelixControlPlaneProtocol
import MelixWorkerProtocol

enum RegistrySnapshotSync {
    static func syncModelsIfAvailable(
        modelCatalog: ModelCatalog,
        workerRegistry: WorkerRegistry?,
        metricsStore: MetricsStore
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

        do {
            let stream = try await workerClient.convertModel(request: workerRequest)
            var discoveredModels: [Melix_Controlplane_V1_ModelSummary]?

            for try await event in stream {
                switch event.payload {
                case .manifest(let manifest):
                    discoveredModels = modelSummaries(from: manifest.manifestJson)
                case .failed:
                    return
                default:
                    break
                }
            }

            guard let discoveredModels else {
                return
            }

            await modelCatalog.syncRegistryModels(discoveredModels, reason: "worker_registry_sync")
            await metricsStore.set(
                Date().timeIntervalSince(startedAt) * 1000,
                forKey: "registry.reload_latency_ms"
            )
            await metricsStore.set(
                Double(discoveredModels.count),
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

    private static func modelSummaries(from manifestJSON: String) -> [Melix_Controlplane_V1_ModelSummary]? {
        guard
            let data = manifestJSON.data(using: .utf8),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
            let registryPayload = payload["model_registry"] as? [String: Any],
            let modelPayloads = registryPayload["models"] as? [[String: Any]]
        else {
            return nil
        }

        return modelPayloads.compactMap(modelSummary(from:))
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
