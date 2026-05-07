import Foundation
import Testing

@testable import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Audio Asset Manager")
struct AudioAssetManagerTests {
    @Test("audio asset manager uses managed Melix roots by default")
    func audioAssetManagerUsesManagedMelixRootsByDefault() throws {
        let melixHomeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-audio-assets-\(UUID().uuidString)", isDirectory: true)
        let manager = AudioAssetManager(melixHomeDirectory: melixHomeDirectory)

        #expect(manager.managedModelRootURL == melixHomeDirectory.appendingPathComponent("models/default-managed", isDirectory: true))
        #expect(manager.audioRuntimePackRootURL == melixHomeDirectory.appendingPathComponent("runtime-packs/audio", isDirectory: true))
    }

    @Test("audio asset manager defaults to HOME MelixHome and ignores app support")
    func audioAssetManagerDefaultsToHomeMelixHomeAndIgnoresAppSupport() throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-audio-assets-home-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let manager = AudioAssetManager(environment: [
            "HOME": temporaryRoot.path,
            "MELIX_APP_SUPPORT_DIR": temporaryRoot.appendingPathComponent("ignored-app-support").path,
        ])
        let expectedHome = temporaryRoot.appendingPathComponent(".melix", isDirectory: true)

        #expect(
            manager.managedModelRootURL
                == expectedHome.appendingPathComponent("models/default-managed", isDirectory: true)
        )
        #expect(
            manager.audioRuntimePackRootURL
                == expectedHome.appendingPathComponent("runtime-packs/audio", isDirectory: true)
        )
    }

    @Test("audio asset manager records runtime pack and local model metadata")
    func audioAssetManagerRecordsRuntimePackAndLocalModelMetadata() throws {
        let melixHomeDirectory = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-audio-assets-\(UUID().uuidString)", isDirectory: true)
        let manager = AudioAssetManager(melixHomeDirectory: melixHomeDirectory)
        let localModelDirectory = melixHomeDirectory
            .appendingPathComponent("models/default-managed/hf/mlx-community/whisper-large-v3/main", isDirectory: true)
        try FileManager.default.createDirectory(at: localModelDirectory, withIntermediateDirectories: true)

        try manager.recordRuntimePackInstall(
            packID: "melix-audio-runtime-pack",
            version: "0.3.0",
            profiles: ["audio-stt", "audio-tts"]
        )
        try manager.recordManagedModel(
            modelID: "melix-whisper-mlx",
            revision: "main",
            sourceModelPath: "mlx-community/whisper-large-v3",
            localModelPath: localModelDirectory.path
        )

        let record = try #require(manager.runtimePackRecord(for: "audio-stt"))
        #expect(record.packID == "melix-audio-runtime-pack")
        #expect(record.version == "0.3.0")
        #expect(record.profiles == ["audio-stt", "audio-tts"])

        var model = ModelCatalog.mlxWhisperModel()
        model = manager.hydrate(model)

        #expect(model.settings.ext["melix.audio.runtime_pack_state"] == "installed")
        #expect(model.settings.ext["melix.audio.runtime_pack_id"] == "melix-audio-runtime-pack")
        #expect(model.settings.ext["melix.audio.model_state"] == "managed_local")
        #expect(model.settings.ext["melix.model_path"] == localModelDirectory.path)
    }
}
