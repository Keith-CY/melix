import Foundation
import MelixWorkerProtocol

#if canImport(MLXLMCommon) && canImport(MLXLLM)
@preconcurrency import MLXLMCommon
@preconcurrency import MLXLLM

struct SwiftDFlashDraftRuntime: @unchecked Sendable {
    let modelID: String
    let directoryURL: URL?
    let configuration: DFlashDraftConfiguration
    let model: DFlashDraftModel?

    init(
        modelID: String = "",
        directoryURL: URL? = nil,
        configuration: DFlashDraftConfiguration = DFlashDraftConfiguration(),
        model: DFlashDraftModel? = nil
    ) {
        self.modelID = modelID
        self.directoryURL = directoryURL
        self.configuration = configuration
        self.model = model
    }

    static func load(directoryURL: URL, modelID: String = "") throws -> SwiftDFlashDraftRuntime {
        let configuration = try loadDFlashDraftConfiguration(directory: directoryURL)
        let model = directoryContainsSafetensors(directoryURL)
            ? try loadDFlashDraftModel(directory: directoryURL)
            : nil
        return SwiftDFlashDraftRuntime(
            modelID: modelID,
            directoryURL: directoryURL,
            configuration: configuration,
            model: model
        )
    }

    static func downloadAndLoad(modelSource: String, revision: String) async throws -> SwiftDFlashDraftRuntime {
        let directory = try await downloadModel(
            hub: defaultHubApi,
            configuration: ModelConfiguration(id: modelSource, revision: revision),
            progressHandler: { _ in }
        )
        return try load(directoryURL: directory, modelID: modelSource)
    }

    private static func directoryContainsSafetensors(_ directoryURL: URL) -> Bool {
        guard let enumerator = FileManager.default.enumerator(
            at: directoryURL,
            includingPropertiesForKeys: nil
        ) else {
            return false
        }
        for case let fileURL as URL in enumerator where fileURL.pathExtension == "safetensors" {
            return true
        }
        return false
    }
}
#endif

enum DFlashDraftSupport {
    static let runtimeKindExtKey = "melix.draft.runtime_kind"
    static let architectureExtKey = "melix.draft.architecture"
    static let unsupportedReason = "dflash_draft_runtime_unavailable"
    static let unsupportedMessage = "DFlash draft checkpoints require the native Swift MLX DFlash draft runtime."

    static func isDFlashDraftModelSpec(_ spec: Melix_Worker_V1_ModelSpec) -> Bool {
        if isDFlashRuntimeKind(spec.ext[runtimeKindExtKey]) {
            return true
        }
        if normalized(spec.ext[architectureExtKey]) == "dflashdraftmodel" {
            return true
        }
        if ["dflash", "dflash_draft"].contains(normalized(spec.modelKind)) {
            return true
        }
        if spec.features.contains(where: { normalized($0) == "dflash" || normalized($0) == "dflash_draft" }) {
            return true
        }
        return looksLikeDFlashIdentifier(spec.modelID)
    }

    static func isDFlashDraftDirectory(_ directoryURL: URL) -> Bool {
        let configURL = directoryURL.appendingPathComponent("config.json", isDirectory: false)
        guard
            let data = try? Data(contentsOf: configURL),
            let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else {
            return false
        }
        return isDFlashConfig(payload)
    }

    private static func isDFlashConfig(_ payload: [String: Any]) -> Bool {
        if let architectures = payload["architectures"] as? [Any],
           architectures.contains(where: { normalized(String(describing: $0)) == "dflashdraftmodel" }) {
            return true
        }
        if let autoMap = payload["auto_map"] as? [String: Any],
           autoMap.values.contains(where: { normalized(String(describing: $0)).contains("dflashdraftmodel") }) {
            return true
        }
        return payload["dflash_config"] is [String: Any]
    }

    private static func isDFlashRuntimeKind(_ rawValue: String?) -> Bool {
        normalized(rawValue) == "dflash"
    }

    static func looksLikeDFlashIdentifier(_ rawValue: String) -> Bool {
        let lastComponent = rawValue.split(separator: "/").last.map(String.init) ?? rawValue
        return normalized(lastComponent).contains("dflash")
    }

    private static func normalized(_ rawValue: String?) -> String {
        (rawValue ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    }
}
