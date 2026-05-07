import Foundation

public struct MelixPathLayout: Equatable, Sendable {
    public let rootURL: URL
    public let configDirectoryURL: URL
    public let stateDirectoryURL: URL
    public let secretsDirectoryURL: URL
    public let modelsDirectoryURL: URL
    public let managedModelRootURL: URL
    public let runtimeDirectoryURL: URL
    public let logsDirectoryURL: URL
    public let installDirectoryURL: URL
    public let jobsDirectoryURL: URL
    public let modelOpsJobsRootURL: URL
    public let evaluationJobsRootURL: URL
    public let audioRuntimePackRootURL: URL

    public let gatewayConfigStoreURL: URL
    public let gatewayServingDefaultsStoreURL: URL
    public let imageDefaultsStoreURL: URL
    public let persistentAuthSessionsURL: URL

    public init(environment: [String: String] = ProcessInfo.processInfo.environment) {
        let rootURL = Self.resolveRootURL(environment: environment)
        self.rootURL = rootURL
        self.configDirectoryURL = rootURL.appendingPathComponent("config", isDirectory: true)
        self.stateDirectoryURL = rootURL.appendingPathComponent("state", isDirectory: true)
        self.secretsDirectoryURL = rootURL.appendingPathComponent("secrets", isDirectory: true)
        self.modelsDirectoryURL = rootURL.appendingPathComponent("models", isDirectory: true)
        self.managedModelRootURL = Self.resolveDirectoryURL(
            environment["MELIX_MANAGED_MODEL_ROOT"],
            fallback: modelsDirectoryURL.appendingPathComponent("default-managed", isDirectory: true)
        )
        self.runtimeDirectoryURL = Self.resolveDirectoryURL(
            environment["MELIX_RUNTIME_DIR"],
            fallback: rootURL.appendingPathComponent("run", isDirectory: true)
        )
        self.logsDirectoryURL = Self.resolveDirectoryURL(
            environment["MELIX_LOGS_DIR"],
            fallback: rootURL.appendingPathComponent("logs", isDirectory: true)
        )
        self.installDirectoryURL = rootURL.appendingPathComponent("install", isDirectory: true)
        self.jobsDirectoryURL = rootURL.appendingPathComponent("jobs", isDirectory: true)
        self.modelOpsJobsRootURL = Self.resolveDirectoryURL(
            environment["MELIX_MODEL_OPS_JOBS_ROOT"],
            fallback: jobsDirectoryURL.appendingPathComponent("model-ops", isDirectory: true)
        )
        self.evaluationJobsRootURL = Self.resolveDirectoryURL(
            environment["MELIX_EVALUATION_JOBS_ROOT"],
            fallback: jobsDirectoryURL.appendingPathComponent("evaluation", isDirectory: true)
        )
        self.audioRuntimePackRootURL = Self.resolveDirectoryURL(
            environment["MELIX_AUDIO_RUNTIME_PACK_ROOT"],
            fallback: rootURL
                .appendingPathComponent("runtime-packs", isDirectory: true)
                .appendingPathComponent("audio", isDirectory: true)
        )

        self.gatewayConfigStoreURL = Self.resolveFileURL(
            environment["MELIX_GATEWAY_CONFIG_STORE_PATH"],
            fallback: configDirectoryURL.appendingPathComponent("gateway-config.json", isDirectory: false)
        )
        self.gatewayServingDefaultsStoreURL = Self.resolveFileURL(
            environment["MELIX_GATEWAY_SERVING_DEFAULTS_STORE_PATH"],
            fallback: configDirectoryURL.appendingPathComponent("gateway-serving-defaults.json", isDirectory: false)
        )
        self.imageDefaultsStoreURL = Self.resolveFileURL(
            environment["MELIX_IMAGE_DEFAULTS_STORE_PATH"],
            fallback: configDirectoryURL.appendingPathComponent("image-defaults.json", isDirectory: false)
        )
        self.persistentAuthSessionsURL = stateDirectoryURL.appendingPathComponent(
            "persistent-auth-sessions.json",
            isDirectory: false
        )
    }

    public static func resolveRootURL(environment: [String: String]) -> URL {
        if let overriddenPath = nonEmptyPath(environment["MELIX_HOME"]) {
            return standardizedURL(overriddenPath, isDirectory: true)
        }

        if let homePath = nonEmptyPath(environment["HOME"]) {
            return standardizedURL(homePath, isDirectory: true)
                .appendingPathComponent(".melix", isDirectory: true)
        }

        return standardizedURL(NSHomeDirectory(), isDirectory: true)
            .appendingPathComponent(".melix", isDirectory: true)
    }

    private static func resolveDirectoryURL(_ rawPath: String?, fallback: URL) -> URL {
        guard let path = nonEmptyPath(rawPath) else {
            return fallback
        }
        return standardizedURL(path, isDirectory: true)
    }

    private static func resolveFileURL(_ rawPath: String?, fallback: URL) -> URL {
        guard let path = nonEmptyPath(rawPath) else {
            return fallback
        }
        return standardizedURL(path, isDirectory: false)
    }

    private static func nonEmptyPath(_ rawPath: String?) -> String? {
        let path = rawPath?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return path.isEmpty ? nil : path
    }

    private static func standardizedURL(_ path: String, isDirectory: Bool) -> URL {
        let expanded = (path as NSString).expandingTildeInPath
        return URL(fileURLWithPath: expanded, isDirectory: isDirectory)
    }
}
