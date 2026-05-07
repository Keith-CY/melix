import Foundation

public struct ProductUpdateStatus: Equatable, Sendable {
    public let summary: String
    public let detail: String
    public let isAvailable: Bool
    public let checkSucceeded: Bool

    public init(summary: String, detail: String, isAvailable: Bool, checkSucceeded: Bool) {
        self.summary = summary
        self.detail = detail
        self.isAvailable = isAvailable
        self.checkSucceeded = checkSucceeded
    }
}

public struct ProductStartupFailureDiagnostic: Equatable, Sendable {
    public let classification: String
    public let userMessage: String
    public let detail: String

    public init(classification: String, userMessage: String, detail: String) {
        self.classification = classification
        self.userMessage = userMessage
        self.detail = detail
    }
}

public protocol ProductInstallStateProviding {
    func updateStatus() -> ProductUpdateStatus?
    func startupFailureDiagnostic(for error: any Error) -> ProductStartupFailureDiagnostic?
}

public struct FilesystemProductInstallStateProvider: ProductInstallStateProviding {
    private let fileManager: FileManager
    private let manifestURL: URL?
    private let explicitUpdateChannelURL: URL?

    public init(
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default,
        manifestURL: URL? = nil,
        updateChannelURL: URL? = nil
    ) {
        self.fileManager = fileManager
        self.manifestURL = manifestURL ?? Self.defaultManifestURL(environment: environment)
        if let updateChannelURL {
            self.explicitUpdateChannelURL = updateChannelURL
        } else if let configuredPath = environment["MELIX_UPDATE_CHANNEL_PATH"], configuredPath.isEmpty == false {
            self.explicitUpdateChannelURL = URL(fileURLWithPath: configuredPath)
        } else {
            self.explicitUpdateChannelURL = nil
        }
    }

    public func updateStatus() -> ProductUpdateStatus? {
        guard let manifest = loadManifest() else {
            return nil
        }
        guard let updateChannelURL = explicitUpdateChannelURL ?? manifest.updateChannelURL else {
            return nil
        }
        guard let channel = loadUpdateChannel(url: updateChannelURL) else {
            return ProductUpdateStatus(
                summary: "Update: check failed",
                detail: "Could not read \(updateChannelURL.path)",
                isAvailable: false,
                checkSucceeded: false
            )
        }
        guard channel.latestVersion.isEmpty == false else {
            return ProductUpdateStatus(
                summary: "Update: check failed",
                detail: "Channel metadata at \(updateChannelURL.path) does not declare latest_version",
                isAvailable: false,
                checkSucceeded: false
            )
        }
        if compareVersions(channel.latestVersion, manifest.productVersion) > 0 {
            return ProductUpdateStatus(
                summary: "Update available: \(channel.latestVersion)",
                detail: "Current \(manifest.productVersion) on \(channel.channel)",
                isAvailable: true,
                checkSucceeded: true
            )
        }
        return ProductUpdateStatus(
            summary: "Update: up to date",
            detail: "Current \(manifest.productVersion) on \(channel.channel)",
            isAvailable: false,
            checkSucceeded: true
        )
    }

    public func startupFailureDiagnostic(for error: any Error) -> ProductStartupFailureDiagnostic? {
        guard let manifest = loadManifest() else {
            return nil
        }
        let errorText = String(describing: error).lowercased()
        let controlPlaneExcerpt = logExcerpt(for: [manifest.controlPlaneStderrURL, manifest.controlPlaneStdoutURL])
        let workerExcerpt = logExcerpt(
            for: [
                manifest.pythonWorkerStderrURL,
                manifest.swiftTextWorkerStderrURL,
                manifest.pythonWorkerStdoutURL,
                manifest.swiftTextWorkerStdoutURL,
            ]
        )
        let combinedControlPlane = ([errorText, controlPlaneExcerpt].filter { !$0.isEmpty }).joined(separator: "\n")
        let combinedWorker = workerExcerpt.lowercased()

        if Self.containsAny(combinedControlPlane, patterns: Self.portConflictPatterns) {
            let message = "Startup failed: port \(manifest.httpPort) is already in use. Check \(manifest.controlPlaneStderrURL?.path ?? manifest.logsDirectoryPath) and restart Melix."
            return ProductStartupFailureDiagnostic(
                classification: "host_port_conflict",
                userMessage: message,
                detail: "Ready probe: \(manifest.readyProbeURL)"
            )
        }
        if controlPlaneExcerpt.isEmpty == false && Self.containsAny(combinedControlPlane, patterns: Self.crashPatterns) {
            let message = "Startup failed: the control plane crashed before \(manifest.readyProbeURL) became ready. Check \(manifest.controlPlaneStderrURL?.path ?? manifest.logsDirectoryPath)."
            return ProductStartupFailureDiagnostic(
                classification: "control_plane_crash",
                userMessage: message,
                detail: controlPlaneExcerpt
            )
        }
        if workerExcerpt.isEmpty == false && Self.containsAny(combinedWorker, patterns: Self.crashPatterns) {
            let workerLogPath = manifest.pythonWorkerStderrURL?.path ?? manifest.swiftTextWorkerStderrURL?.path ?? manifest.logsDirectoryPath
            let message = "Startup failed: a worker crashed before Melix became ready. Check \(workerLogPath)."
            return ProductStartupFailureDiagnostic(
                classification: "worker_crash",
                userMessage: message,
                detail: workerExcerpt
            )
        }
        let hangLogPath = manifest.controlPlaneStderrURL?.path ?? manifest.logsDirectoryPath
        let detail = controlPlaneExcerpt.isEmpty ? workerExcerpt : controlPlaneExcerpt
        return ProductStartupFailureDiagnostic(
            classification: "startup_hang",
            userMessage: "Startup failed: Melix never became ready at \(manifest.readyProbeURL). Check \(hangLogPath).",
            detail: detail
        )
    }

    private func loadManifest() -> ProductInstallManifest? {
        guard let manifestURL else {
            return nil
        }
        guard let data = fileManager.contents(atPath: manifestURL.path) else {
            return nil
        }
        return try? JSONDecoder().decode(ProductInstallManifest.self, from: data)
    }

    private func loadUpdateChannel(url: URL) -> ProductUpdateChannel? {
        guard let data = fileManager.contents(atPath: url.path) else {
            return nil
        }
        return try? JSONDecoder().decode(ProductUpdateChannel.self, from: data)
    }

    private func logExcerpt(for urls: [URL?]) -> String {
        for url in urls {
            guard let url else {
                continue
            }
            guard let data = fileManager.contents(atPath: url.path) else {
                continue
            }
            let payload = String(decoding: data, as: UTF8.self)
                .split(whereSeparator: \.isNewline)
                .map(String.init)
                .last?
                .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if payload.isEmpty == false {
                return payload
            }
        }
        return ""
    }

    private static func containsAny(_ haystack: String, patterns: [String]) -> Bool {
        patterns.contains { haystack.contains($0) }
    }

    private static let portConflictPatterns = [
        "address already in use",
        "eaddrinuse",
        "bind() failed",
        "port is already in use",
    ]

    private static let crashPatterns = [
        "fatal error",
        "traceback",
        "uncaught",
        "assertion failed",
        "terminated",
        "abort trap",
    ]

    private static func defaultManifestURL(environment: [String: String]) -> URL? {
        if let configuredPath = environment["MELIX_PRODUCT_MANIFEST_PATH"], configuredPath.isEmpty == false {
            return URL(fileURLWithPath: configuredPath)
        }
        return MelixHome(environment: environment)
            .installDirectoryURL
            .appendingPathComponent("install-manifest.json")
    }
}

private struct ProductInstallManifest: Decodable {
    let productVersion: String
    let updateChannelPath: String?
    let readyProbeURL: String
    let httpPort: Int
    let logsDirectoryPath: String
    let controlPlaneStdoutPath: String?
    let controlPlaneStderrPath: String?
    let pythonWorkerStdoutPath: String?
    let pythonWorkerStderrPath: String?
    let swiftTextWorkerStdoutPath: String?
    let swiftTextWorkerStderrPath: String?

    enum CodingKeys: String, CodingKey {
        case productVersion = "product_version"
        case updateChannelPath = "update_channel_path"
        case readyProbeURL = "ready_probe_url"
        case httpPort = "http_port"
        case logsDirectoryPath = "logs_dir"
        case controlPlaneStdoutPath = "control_plane_stdout_path"
        case controlPlaneStderrPath = "control_plane_stderr_path"
        case pythonWorkerStdoutPath = "python_worker_stdout_path"
        case pythonWorkerStderrPath = "python_worker_stderr_path"
        case swiftTextWorkerStdoutPath = "swift_text_worker_stdout_path"
        case swiftTextWorkerStderrPath = "swift_text_worker_stderr_path"
    }

    var updateChannelURL: URL? {
        updateChannelPath.flatMap { URL(fileURLWithPath: $0) }
    }

    var controlPlaneStdoutURL: URL? {
        controlPlaneStdoutPath.flatMap { URL(fileURLWithPath: $0) }
    }

    var controlPlaneStderrURL: URL? {
        controlPlaneStderrPath.flatMap { URL(fileURLWithPath: $0) }
    }

    var pythonWorkerStdoutURL: URL? {
        pythonWorkerStdoutPath.flatMap { URL(fileURLWithPath: $0) }
    }

    var pythonWorkerStderrURL: URL? {
        pythonWorkerStderrPath.flatMap { URL(fileURLWithPath: $0) }
    }

    var swiftTextWorkerStdoutURL: URL? {
        swiftTextWorkerStdoutPath.flatMap { URL(fileURLWithPath: $0) }
    }

    var swiftTextWorkerStderrURL: URL? {
        swiftTextWorkerStderrPath.flatMap { URL(fileURLWithPath: $0) }
    }
}

private struct ProductUpdateChannel: Decodable {
    let channel: String
    let latestVersion: String

    enum CodingKeys: String, CodingKey {
        case channel
        case latestVersion = "latest_version"
    }
}

private func compareVersions(_ left: String, _ right: String) -> Int {
    let leftParts = normalizedVersionParts(left)
    let rightParts = normalizedVersionParts(right)
    let width = max(leftParts.count, rightParts.count)
    let normalizedLeft = leftParts + Array(repeating: 0, count: width - leftParts.count)
    let normalizedRight = rightParts + Array(repeating: 0, count: width - rightParts.count)
    for (leftValue, rightValue) in zip(normalizedLeft, normalizedRight) {
        if leftValue < rightValue {
            return -1
        }
        if leftValue > rightValue {
            return 1
        }
    }
    return 0
}

private func normalizedVersionParts(_ value: String) -> [Int] {
    var cleaned = value.trimmingCharacters(in: .whitespacesAndNewlines)
    if cleaned.hasPrefix("v") {
        cleaned.removeFirst()
    }
    if let buildIndex = cleaned.firstIndex(of: "+") {
        cleaned = String(cleaned[..<buildIndex])
    }
    if let prereleaseIndex = cleaned.firstIndex(of: "-") {
        cleaned = String(cleaned[..<prereleaseIndex])
    }
    let parts = cleaned.split(separator: ".").map { Int($0.prefix { $0.isNumber }) ?? 0 }
    return parts.isEmpty ? [0] : parts
}
