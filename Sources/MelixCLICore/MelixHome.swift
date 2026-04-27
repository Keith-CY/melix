import Foundation

public enum MelixHomeError: Error, Equatable {
    case invalidPath(String)
}

public struct MelixHome: Equatable, Sendable {
    public static let directoryPermissions = 0o700
    public static let filePermissions = 0o600

    public let rootURL: URL
    public let stateDirectoryURL: URL
    public let secretsDirectoryURL: URL
    public let operatorSessionFileURL: URL
    public let remoteServersFileURL: URL
    public let evaluationPromptsFileURL: URL
    public let serverSessionAPIKeysFileURL: URL
    public let remoteServerAPIKeysFileURL: URL
    public let huggingFaceTokenFileURL: URL

    public init(environment: [String: String] = ProcessInfo.processInfo.environment) {
        let homePath = Self.resolveHomePath(environment: environment)
        self.rootURL = URL(fileURLWithPath: homePath, isDirectory: true)
        self.stateDirectoryURL = rootURL.appendingPathComponent("state", isDirectory: true)
        self.secretsDirectoryURL = rootURL.appendingPathComponent("secrets", isDirectory: true)
        self.operatorSessionFileURL = stateDirectoryURL.appendingPathComponent("operator-session.json")
        self.remoteServersFileURL = stateDirectoryURL.appendingPathComponent("remote-servers.json")
        self.evaluationPromptsFileURL = stateDirectoryURL.appendingPathComponent("evaluation-prompts.json")
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

    private static func resolveHomePath(environment: [String: String]) -> String {
        if let overriddenPath = environment["MELIX_HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           overriddenPath.isEmpty == false
        {
            return overriddenPath
        }

        if let appSupportPath = environment["MELIX_APP_SUPPORT_DIR"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           appSupportPath.isEmpty == false
        {
            return appSupportPath
        }

        let homePath = environment["HOME"]?.trimmingCharacters(in: .whitespacesAndNewlines)
        if let homePath, homePath.isEmpty == false {
            return URL(fileURLWithPath: homePath, isDirectory: true)
                .appendingPathComponent(".melix", isDirectory: true)
                .path
        }

        return URL(fileURLWithPath: NSHomeDirectory(), isDirectory: true)
            .appendingPathComponent(".melix", isDirectory: true)
            .path
    }
}
