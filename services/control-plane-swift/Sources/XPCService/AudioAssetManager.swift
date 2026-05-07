import Foundation

import MelixControlPlaneProtocol

public struct AudioRuntimePackRecord: Codable, Equatable, Sendable {
    public let packID: String
    public let version: String
    public let profiles: [String]

    public init(packID: String, version: String, profiles: [String]) {
        self.packID = packID
        self.version = version
        self.profiles = profiles
    }
}

public struct ManagedAudioModelRecord: Codable, Equatable, Sendable {
    public let modelID: String
    public let revision: String
    public let sourceModelPath: String
    public let localModelPath: String

    public init(
        modelID: String,
        revision: String,
        sourceModelPath: String,
        localModelPath: String
    ) {
        self.modelID = modelID
        self.revision = revision
        self.sourceModelPath = sourceModelPath
        self.localModelPath = localModelPath
    }
}

public final class AudioAssetManager: @unchecked Sendable {
    public let managedModelRootURL: URL
    public let audioRuntimePackRootURL: URL

    private let fileManager: FileManager
    private let runtimePackStateURL: URL
    private let managedModelStateURL: URL

    public init(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        melixHomeDirectory: URL? = nil
    ) {
        self.fileManager = fileManager
        let layout = MelixPathLayout(environment: environment)
        let resolvedMelixHomeDirectory = melixHomeDirectory ?? layout.rootURL
        self.managedModelRootURL = Self.resolveDirectoryURL(
            rawPath: environment["MELIX_MANAGED_MODEL_ROOT"],
            fallback: resolvedMelixHomeDirectory.appendingPathComponent("models/default-managed", isDirectory: true)
        )
        self.audioRuntimePackRootURL = Self.resolveDirectoryURL(
            rawPath: environment["MELIX_AUDIO_RUNTIME_PACK_ROOT"],
            fallback: resolvedMelixHomeDirectory.appendingPathComponent("runtime-packs/audio", isDirectory: true)
        )
        self.runtimePackStateURL = audioRuntimePackRootURL.appendingPathComponent(
            ".melix-runtime-pack-state.json",
            isDirectory: false
        )
        self.managedModelStateURL = managedModelRootURL.appendingPathComponent(
            ".melix-managed-audio-models.json",
            isDirectory: false
        )
    }

    public func runtimePackRecord(for installProfile: String) -> AudioRuntimePackRecord? {
        let normalizedProfile = normalize(installProfile)
        guard !normalizedProfile.isEmpty else {
            return nil
        }
        return try? loadRuntimePackRecords()[normalizedProfile]
    }

    public func recordRuntimePackInstall(
        packID: String,
        version: String,
        profiles: [String]
    ) throws {
        let runtimePackDirectory = audioRuntimePackRootURL
            .appendingPathComponent(packID, isDirectory: true)
            .appendingPathComponent(version, isDirectory: true)
        let normalizedProfiles = profiles.map(normalize).filter { !$0.isEmpty }.sorted()
        guard !normalizedProfiles.isEmpty else {
            return
        }
        try ensureDirectoryExists(at: runtimePackDirectory)
        try write(
            AudioRuntimePackRecord(packID: packID, version: version, profiles: normalizedProfiles),
            to: runtimePackDirectory.appendingPathComponent("runtime-pack.json", isDirectory: false)
        )
        try ensureDirectoryExists(at: audioRuntimePackRootURL)
        var records = try loadRuntimePackRecords()
        let record = AudioRuntimePackRecord(packID: packID, version: version, profiles: normalizedProfiles)
        for profile in normalizedProfiles {
            records[profile] = record
        }
        try write(records, to: runtimePackStateURL)
    }

    public func runtimePackID(for installProfile: String) -> String {
        let normalizedProfile = normalize(installProfile)
        guard !normalizedProfile.isEmpty else {
            return ""
        }
        switch normalizedProfile {
        case "audio", "audio-stt", "audio-tts":
            return "melix-audio-runtime-pack"
        default:
            return "melix-\(normalizedProfile)-runtime-pack"
        }
    }

    public func managedModelRecord(for modelID: String) -> ManagedAudioModelRecord? {
        guard !normalize(modelID).isEmpty else {
            return nil
        }
        return try? loadManagedModelRecords()[modelID]
    }

    public func recordManagedModel(
        modelID: String,
        revision: String,
        sourceModelPath: String,
        localModelPath: String
    ) throws {
        guard !normalize(modelID).isEmpty else {
            return
        }
        let localModelURL = URL(fileURLWithPath: localModelPath, isDirectory: true)
        try ensureDirectoryExists(at: localModelURL)
        try write(
            ManagedAudioModelRecord(
                modelID: modelID,
                revision: revision,
                sourceModelPath: sourceModelPath,
                localModelPath: localModelPath
            ),
            to: localModelURL.appendingPathComponent("managed-model.json", isDirectory: false)
        )
        try ensureDirectoryExists(at: managedModelRootURL)
        var records = try loadManagedModelRecords()
        records[modelID] = ManagedAudioModelRecord(
            modelID: modelID,
            revision: revision,
            sourceModelPath: sourceModelPath,
            localModelPath: localModelPath
        )
        try write(records, to: managedModelStateURL)
    }

    public func managedModelDirectoryURL(
        sourceModelPath: String,
        revision: String
    ) -> URL {
        let normalizedSourceModelPath = normalize(sourceModelPath)
        let normalizedRevision = normalize(revision).isEmpty ? "managed" : normalize(revision)
        var directory = managedModelRootURL
        if normalizedSourceModelPath.isEmpty {
            return directory.appendingPathComponent(normalizedRevision, isDirectory: true)
        }
        for component in normalizedSourceModelPath.split(separator: "/") {
            directory.appendPathComponent(String(component), isDirectory: true)
        }
        return directory.appendingPathComponent(normalizedRevision, isDirectory: true)
    }

    public func hydrate(_ model: Melix_Controlplane_V1_ModelSummary) -> Melix_Controlplane_V1_ModelSummary {
        let backendID = normalize(model.settings.ext["melix.audio.backend_id"])
        guard !backendID.isEmpty else {
            return model
        }

        var hydrated = model
        hydrated.settings.ext["melix.audio.managed_model_root"] = managedModelRootURL.path
        hydrated.settings.ext["melix.audio.runtime_pack_root"] = audioRuntimePackRootURL.path

        let installProfile = normalize(model.settings.ext["melix.audio.install_profile"])
        if installProfile.isEmpty {
            hydrated.settings.ext["melix.audio.runtime_pack_state"] = "not_required"
            hydrated.settings.ext.removeValue(forKey: "melix.audio.runtime_pack_id")
            hydrated.settings.ext.removeValue(forKey: "melix.audio.runtime_pack_version")
        } else if let runtimePackRecord = runtimePackRecord(for: installProfile) {
            hydrated.settings.ext["melix.audio.runtime_pack_state"] = "installed"
            hydrated.settings.ext["melix.audio.runtime_pack_id"] = runtimePackRecord.packID
            hydrated.settings.ext["melix.audio.runtime_pack_version"] = runtimePackRecord.version
        } else {
            hydrated.settings.ext["melix.audio.runtime_pack_state"] = "missing"
            hydrated.settings.ext["melix.audio.runtime_pack_id"] = runtimePackID(for: installProfile)
            hydrated.settings.ext.removeValue(forKey: "melix.audio.runtime_pack_version")
        }

        if let managedModelRecord = managedModelRecord(for: model.modelID) {
            hydrated.settings.ext["melix.audio.model_state"] = "managed_local"
            hydrated.settings.ext["melix.model_path"] = managedModelRecord.localModelPath
            hydrated.settings.ext["melix.model_revision"] = managedModelRecord.revision
            hydrated.settings.ext["melix.audio.source_model_path"] = managedModelRecord.sourceModelPath
        } else {
            let existingModelPath = normalize(hydrated.settings.ext["melix.model_path"])
            hydrated.settings.ext["melix.audio.model_state"] = existingModelPath.isEmpty ? "catalog_default" : "catalog_override"
        }

        return hydrated
    }

    private func loadRuntimePackRecords() throws -> [String: AudioRuntimePackRecord] {
        try load([String: AudioRuntimePackRecord].self, from: runtimePackStateURL)
    }

    private func loadManagedModelRecords() throws -> [String: ManagedAudioModelRecord] {
        try load([String: ManagedAudioModelRecord].self, from: managedModelStateURL)
    }

    private func load<Value: Decodable>(
        _: Value.Type,
        from url: URL
    ) throws -> Value where Value: ExpressibleByDictionaryLiteral {
        guard fileManager.fileExists(atPath: url.path) else {
            return [:]
        }
        let data = try Data(contentsOf: url)
        return try JSONDecoder().decode(Value.self, from: data)
    }

    private func write<Value: Encodable>(_ value: Value, to url: URL) throws {
        try ensureDirectoryExists(at: url.deletingLastPathComponent())
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        let data = try encoder.encode(value)
        try data.write(to: url, options: .atomic)
    }

    private func ensureDirectoryExists(at url: URL) throws {
        try fileManager.createDirectory(at: url, withIntermediateDirectories: true)
    }

    private static func resolveDirectoryURL(rawPath: String?, fallback: URL) -> URL {
        guard let rawPath else {
            return fallback
        }
        let normalizedPath = rawPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !normalizedPath.isEmpty else {
            return fallback
        }
        return URL(fileURLWithPath: normalizedPath, isDirectory: true)
    }

    private func normalize(_ value: String?) -> String {
        value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }
}
