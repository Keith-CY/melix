import Foundation
import MelixControlPlaneCore

public enum MelixHomeError: Error, Equatable {
    case invalidPath(String)
}

public struct MelixHome: Equatable, Sendable {
    public static let directoryPermissions = 0o700
    public static let filePermissions = 0o600

    public let rootURL: URL
    public let configDirectoryURL: URL
    public let stateDirectoryURL: URL
    public let secretsDirectoryURL: URL
    public let managedModelRootURL: URL
    public let modelOpsJobsRootURL: URL
    public let evaluationJobsRootURL: URL
    public let audioRuntimePackRootURL: URL
    public let runtimeDirectoryURL: URL
    public let logsDirectoryURL: URL
    public let installDirectoryURL: URL
    public let operatorSessionFileURL: URL
    public let serverSessionsFileURL: URL
    public let modelRootsFileURL: URL
    public let downloadQueueFileURL: URL
    public let remoteServersFileURL: URL
    public let evaluationPromptsFileURL: URL
    public let loraTrainingJobsFileURL: URL
    public let serverSessionAPIKeysFileURL: URL
    public let remoteServerAPIKeysFileURL: URL
    public let huggingFaceTokenFileURL: URL

    public init(environment: [String: String] = ProcessInfo.processInfo.environment) {
        let layout = MelixPathLayout(environment: environment)
        self.rootURL = layout.rootURL
        self.configDirectoryURL = layout.configDirectoryURL
        self.stateDirectoryURL = layout.stateDirectoryURL
        self.secretsDirectoryURL = layout.secretsDirectoryURL
        self.managedModelRootURL = layout.managedModelRootURL
        self.modelOpsJobsRootURL = layout.modelOpsJobsRootURL
        self.evaluationJobsRootURL = layout.evaluationJobsRootURL
        self.audioRuntimePackRootURL = layout.audioRuntimePackRootURL
        self.runtimeDirectoryURL = layout.runtimeDirectoryURL
        self.logsDirectoryURL = layout.logsDirectoryURL
        self.installDirectoryURL = layout.installDirectoryURL
        self.operatorSessionFileURL = stateDirectoryURL.appendingPathComponent("operator-session.json")
        self.serverSessionsFileURL = configDirectoryURL.appendingPathComponent("server-sessions.json")
        self.modelRootsFileURL = configDirectoryURL.appendingPathComponent("model-roots.json")
        self.downloadQueueFileURL = stateDirectoryURL.appendingPathComponent("download-queue.json")
        self.remoteServersFileURL = configDirectoryURL.appendingPathComponent("remote-servers.json")
        self.evaluationPromptsFileURL = configDirectoryURL.appendingPathComponent("evaluation-prompts.json")
        self.loraTrainingJobsFileURL = stateDirectoryURL.appendingPathComponent("lora-training-jobs.json")
        self.serverSessionAPIKeysFileURL = secretsDirectoryURL.appendingPathComponent("server-session-api-keys.json")
        self.remoteServerAPIKeysFileURL = secretsDirectoryURL.appendingPathComponent("remote-server-api-keys.json")
        self.huggingFaceTokenFileURL = secretsDirectoryURL.appendingPathComponent("huggingface-token.json")
    }

    public func ensureDirectoryExists(at directoryURL: URL) throws {
        let fileManager = FileManager.default
        var isDirectory = ObjCBool(false)
        if fileManager.fileExists(atPath: directoryURL.path, isDirectory: &isDirectory) {
            guard isDirectory.boolValue else {
                throw MelixHomeError.invalidPath("Expected directory at \(directoryURL.path)")
            }
        } else {
            try fileManager.createDirectory(
                at: directoryURL,
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: Self.directoryPermissions]
            )
        }
        try fileManager.setAttributes([.posixPermissions: Self.directoryPermissions], ofItemAtPath: directoryURL.path)
    }

    public func writeAtomically(_ data: Data, to fileURL: URL) throws {
        let fileManager = FileManager.default
        try ensureDirectoryExists(at: rootURL)
        try ensureDirectoryExists(at: fileURL.deletingLastPathComponent())

        let temporaryURL = fileURL
            .deletingLastPathComponent()
            .appendingPathComponent(".\(fileURL.lastPathComponent).\(UUID().uuidString).tmp")
        defer {
            try? fileManager.removeItem(at: temporaryURL)
        }

        try data.write(to: temporaryURL, options: [])
        try fileManager.setAttributes([.posixPermissions: Self.filePermissions], ofItemAtPath: temporaryURL.path)

        if fileManager.fileExists(atPath: fileURL.path) {
            _ = try fileManager.replaceItemAt(fileURL, withItemAt: temporaryURL)
        } else {
            try fileManager.moveItem(at: temporaryURL, to: fileURL)
        }

        try fileManager.setAttributes([.posixPermissions: Self.filePermissions], ofItemAtPath: fileURL.path)
    }
}
