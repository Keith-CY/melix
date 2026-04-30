import Foundation
import Testing

@testable import MelixCLICore

@Suite("Remote Server Store")
struct RemoteServerStoreTests {
    @Test("provider preset metadata covers titles provider kinds fixed URLs and aliases")
    func providerPresetMetadataCoversTitlesKindsFixedURLsAndAliases() {
        #expect(RemoteServerProviderPreset.kimi.title == "Kimi")
        #expect(RemoteServerProviderPreset.gemini.title == "Gemini")
        #expect(RemoteServerProviderPreset.deepseek.title == "DeepSeek")
        #expect(RemoteServerProviderPreset.glm.title == "GLM")
        #expect(RemoteServerProviderPreset.custom.title == "Custom")
        #expect(RemoteServerProviderPreset.gemini.providerKind == "gemini-generative-language")
        #expect(RemoteServerProviderPreset.custom.providerKind == "openai-compatible")
        #expect(RemoteServerProviderPreset.kimi.fixedBaseURL == "https://api.kimi.com/coding/v1")
        #expect(RemoteServerProviderPreset.deepseek.fixedBaseURL == "https://api.deepseek.com/v1")
        #expect(RemoteServerProviderPreset.glm.fixedBaseURL == "https://open.bigmodel.cn/api/paas/v4")
        #expect(RemoteServerProviderPreset.custom.fixedBaseURL == nil)
        #expect(RemoteServerProviderPreset.custom.isBaseURLEditable)
        #expect(RemoteServerProviderPreset.normalized(" sub2api ") == .custom)
        #expect(RemoteServerProviderPreset.normalized("openai-compatible") == .custom)
        #expect(RemoteServerProviderPreset.normalized("unknown") == nil)
        #expect(RemoteServerAPIKeyStore.maskedHint(for: "") == "")
        #expect(RemoteServerAPIKeyStore.maskedHint(for: "short") == "saved")
    }

    @Test("persists remote server state with redacted credential hint and keeps api key in secrets")
    func persistsRemoteServerStateWithRedactedCredentialHintAndSecrets() throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-remote-server-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let home = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let store = RemoteServerStore(melixHome: home)
        let secretStore = RemoteServerAPIKeyStore(melixHome: home)

        let created = try store.save(
            RemoteServerMutation(
                id: "sub2api",
                title: "sub2api",
                providerKind: "openai-compatible",
                baseURL: "https://sub2api.example/v1/",
                defaultModelID: "gemini-2.5-flash",
                timeoutSeconds: 90,
                rateLimitPerMinute: 30,
                apiKey: "sk-live-secret-value"
            )
        )

        #expect(created.id == "sub2api")
        #expect(created.baseURL == "https://sub2api.example/v1")
        #expect(created.credentialRef == "remote-server-api-key:sub2api")
        #expect(created.apiKeyHint.hasPrefix("sk-l"))
        #expect(created.apiKeyHint.hasSuffix("alue"))

        let visibleState = try String(contentsOf: home.remoteServersFileURL, encoding: .utf8)
        #expect(visibleState.contains("sub2api"))
        #expect(visibleState.contains("gemini-2.5-flash"))
        #expect(visibleState.contains("sk-live-secret-value") == false)

        let secretState = try String(contentsOf: home.remoteServerAPIKeysFileURL, encoding: .utf8)
        #expect(secretState.contains("sk-live-secret-value"))
        #expect(try secretStore.loadAPIKey(remoteServerID: "sub2api")?.apiKey == "sk-live-secret-value")
        #expect(try store.loadAPIKey(remoteServerID: "sub2api")?.apiKey == "sk-live-secret-value")

        let updated = try store.save(
            RemoteServerMutation(
                id: "sub2api",
                title: "sub2api prod",
                providerKind: "openai-compatible",
                baseURL: "https://sub2api.example/v1",
                defaultModelID: "kimi-2.6",
                timeoutSeconds: 120,
                rateLimitPerMinute: 45,
                apiKey: ""
            )
        )

        #expect(updated.title == "sub2api prod")
        #expect(updated.defaultModelID == "kimi-2.6")
        #expect(try secretStore.loadAPIKey(remoteServerID: "sub2api")?.apiKey == "sk-live-secret-value")

        try store.remove(id: "sub2api")

        #expect(try store.list().isEmpty)
        #expect(try secretStore.loadAPIKey(remoteServerID: "sub2api") == nil)
    }

    @Test("rejects blank remote server fields without crashing")
    func rejectsBlankRemoteServerFieldsWithoutCrashing() throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-remote-server-validation-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let store = RemoteServerStore(melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path]))

        #expect(throws: MelixCLIError.missingRequired("remote_server_id must not be empty.")) {
            try store.get(id: " ")
        }
        #expect(throws: MelixCLIError.missingRequired("base_url must not be empty.")) {
            try store.save(
                RemoteServerMutation(
                    id: "custom",
                    title: "Custom",
                    providerPreset: .custom,
                    providerKind: "openai-compatible",
                    baseURL: " ",
                    defaultModelID: "model",
                    apiKey: ""
                )
            )
        }
        #expect(throws: MelixCLIError.missingRequired("api_key must not be empty.")) {
            try RemoteServerAPIKeyStore(melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path]))
                .saveAPIKey(" ", remoteServerID: "custom")
        }
        #expect(throws: MelixCLIError.missingRequired("remote_server_id must not be empty.")) {
            try RemoteServerAPIKeyStore(melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path]))
                .saveAPIKey("sk-live", remoteServerID: " ")
        }
    }

    @Test("provider presets resolve fixed base URLs and keep legacy OpenAI compatible state as custom")
    func providerPresetsResolveFixedBaseURLsAndMigrateLegacyState() throws {
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-remote-server-presets-\(UUID().uuidString)", isDirectory: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let home = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let store = RemoteServerStore(melixHome: home)

        let kimi = try store.save(
            RemoteServerMutation(
                id: "kimi",
                title: "Kimi",
                providerPreset: .kimi,
                providerKind: "ignored-by-preset",
                baseURL: "https://operator-input.example/v1",
                defaultModelID: "kimi-2.6",
                apiKey: "sk-kimi-secret"
            )
        )

        #expect(kimi.providerPreset == .kimi)
        #expect(kimi.providerKind == "openai-compatible")
        #expect(kimi.baseURL == "https://api.kimi.com/coding/v1")

        let visibleState = try String(contentsOf: home.remoteServersFileURL, encoding: .utf8)
        #expect(visibleState.contains(#""provider_preset" : "kimi""#))
        #expect(visibleState.contains("operator-input.example") == false)
        #expect(visibleState.contains("sk-kimi-secret") == false)

        try FileManager.default.createDirectory(
            at: home.remoteServersFileURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try """
        {
          "schema_version": 1,
          "servers": [
            {
              "id": "legacy",
              "title": "Legacy",
              "provider_kind": "openai-compatible",
              "base_url": "https://sub2api.example/v1",
              "default_model_id": "gemini-2.5-flash",
              "timeout_seconds": 60,
              "rate_limit_per_minute": 0,
              "credential_ref": "remote-server-api-key:legacy",
              "api_key_hint": "sk-l...gacy",
              "health_status": "unknown",
              "created_at": "2026-04-27T00:00:00Z",
              "updated_at": "2026-04-27T00:00:00Z"
            }
          ]
        }
        """.write(to: home.remoteServersFileURL, atomically: true, encoding: .utf8)

        let legacy = try #require(try store.get(id: "legacy"))
        #expect(legacy.providerPreset == .custom)
        #expect(legacy.providerKind == "openai-compatible")
        #expect(legacy.baseURL == "https://sub2api.example/v1")
    }
}
