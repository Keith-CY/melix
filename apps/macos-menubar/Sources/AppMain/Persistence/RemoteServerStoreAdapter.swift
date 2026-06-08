import MelixCLICore

public protocol RemoteServerStoring: Sendable {
    func list() throws -> [RemoteServer]
    func loadAPIKey(remoteServerID: String) throws -> RemoteServerAPIKeyRecord?
    func save(_ mutation: RemoteServerMutation) throws -> RemoteServer
    func remove(id: String) throws
}

extension RemoteServerStore: RemoteServerStoring {}

public struct NullRemoteServerStore: RemoteServerStoring {
    public init() {}

    public func list() throws -> [RemoteServer] {
        []
    }

    public func loadAPIKey(remoteServerID: String) throws -> RemoteServerAPIKeyRecord? {
        nil
    }

    @discardableResult
    public func save(_ mutation: RemoteServerMutation) throws -> RemoteServer {
        RemoteServer(
            id: mutation.id,
            title: mutation.title,
            providerPreset: mutation.providerPreset,
            providerKind: mutation.providerPreset.providerKind,
            baseURL: mutation.providerPreset.fixedBaseURL ?? mutation.baseURL,
            defaultModelID: mutation.defaultModelID,
            timeoutSeconds: mutation.timeoutSeconds,
            rateLimitPerMinute: mutation.rateLimitPerMinute,
            toolSupportMode: mutation.toolSupportMode,
            credentialRef: RemoteServerStore.credentialRef(for: mutation.id),
            apiKeyHint: mutation.apiKey.isEmpty ? "" : RemoteServerAPIKeyStore.maskedHint(for: mutation.apiKey)
        )
    }

    public func remove(id: String) throws {}
}
