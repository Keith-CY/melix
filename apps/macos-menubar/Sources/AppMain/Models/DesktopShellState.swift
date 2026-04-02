import Foundation

public enum DesktopSurface: String, CaseIterable, Identifiable, Codable, Sendable {
    case chat = "Chat"
    case image = "Image"
    case server = "Server"
    case tools = "Tools"
    case api = "API"

    public var id: String {
        rawValue
    }

    public var symbolName: String {
        switch self {
        case .chat:
            return "message"
        case .image:
            return "photo.on.rectangle"
        case .server:
            return "network"
        case .tools:
            return "wrench.and.screwdriver"
        case .api:
            return "chevron.left.forwardslash.chevron.right"
        }
    }
}

public enum DesktopToolSection: String, CaseIterable, Identifiable, Codable, Sendable {
    case modelsLibrary = "Models Library"
    case downloads = "Downloads"
    case training = "Training"
    case diagnostics = "Diagnostics"
    case logs = "Logs"
    case settings = "Settings"

    public var id: String {
        rawValue
    }

    public var symbolName: String {
        switch self {
        case .modelsLibrary:
            return "square.stack.3d.up"
        case .downloads:
            return "arrow.down.circle"
        case .training:
            return "figure.strengthtraining.traditional"
        case .diagnostics:
            return "stethoscope"
        case .logs:
            return "doc.text.magnifyingglass"
        case .settings:
            return "slider.horizontal.3"
        }
    }
}

public enum DesktopServerAuthMode: String, CaseIterable, Identifiable, Codable, Sendable {
    case none = "None"
    case bearerToken = "Bearer Token"
    case apiKeys = "API Keys"

    public var id: String {
        rawValue
    }
}

public enum DesktopSharedAccessState: String, Codable, Sendable {
    case localOnly = "Local Only"
    case configuredDisabled = "Configured, Disabled"
    case enabled = "Enabled"
}

public enum DesktopServerSessionLifecycle: String, Codable, Sendable {
    case draft = "Draft"
    case starting = "Starting"
    case running = "Running"
    case stopping = "Stopping"
    case stopped = "Stopped"
    case error = "Error"
    case unavailable = "Unavailable"
}

public struct DesktopServerServingDefaultsState: Codable, Equatable, Sendable {
    public var temperature: Double
    public var topP: Double
    public var maxTokens: Int
    public var maxConcurrentRequests: Int

    public init(
        temperature: Double = 0.7,
        topP: Double = 1.0,
        maxTokens: Int = 1024,
        maxConcurrentRequests: Int = 4
    ) {
        self.temperature = temperature
        self.topP = topP
        self.maxTokens = maxTokens
        self.maxConcurrentRequests = maxConcurrentRequests
    }
}

public struct DesktopServerSessionState: Codable, Identifiable, Equatable, Sendable {
    public let id: String
    public var title: String
    public var modelID: String
    public var host: String
    public var port: Int
    public var authMode: DesktopServerAuthMode
    public var authTokenHint: String
    public var sharedAccessState: DesktopSharedAccessState
    public var accessKeyCount: Int
    public var accessKeyHints: [String]
    public var rateLimitPerMinute: Int
    public var timeoutSeconds: Int
    public var servingDefaults: DesktopServerServingDefaultsState
    public var lifecycle: DesktopServerSessionLifecycle
    public var lastError: String
    public var lastKnownModelStateText: String
    public var createdAt: Date
    public var updatedAt: Date

    public init(
        id: String,
        title: String,
        modelID: String,
        host: String = "127.0.0.1",
        port: Int = 8080,
        authMode: DesktopServerAuthMode = .none,
        authTokenHint: String = "",
        sharedAccessState: DesktopSharedAccessState = .localOnly,
        accessKeyCount: Int = 0,
        accessKeyHints: [String] = [],
        rateLimitPerMinute: Int = 120,
        timeoutSeconds: Int = 120,
        servingDefaults: DesktopServerServingDefaultsState = DesktopServerServingDefaultsState(),
        lifecycle: DesktopServerSessionLifecycle = .draft,
        lastError: String = "",
        lastKnownModelStateText: String = "",
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.modelID = modelID
        self.host = host
        self.port = port
        self.authMode = authMode
        self.authTokenHint = authTokenHint
        self.sharedAccessState = sharedAccessState
        self.accessKeyCount = accessKeyCount
        self.accessKeyHints = accessKeyHints
        self.rateLimitPerMinute = rateLimitPerMinute
        self.timeoutSeconds = timeoutSeconds
        self.servingDefaults = servingDefaults
        self.lifecycle = lifecycle
        self.lastError = lastError
        self.lastKnownModelStateText = lastKnownModelStateText
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    public var baseURL: String {
        "http://\(host):\(port)/v1"
    }

    public var integrationAuthValue: String {
        switch authMode {
        case .none:
            return "not-required"
        case .bearerToken:
            let placeholder = authTokenHint.isEmpty ? "melix-api-key" : authTokenHint
            return "<\(placeholder)>"
        case .apiKeys:
            let placeholder = authTokenHint.isEmpty
                ? (accessKeyHints.first ?? "melix-shared-key")
                : authTokenHint
            return "<\(placeholder)>"
        }
    }

    public var accessKeyHintsText: String {
        accessKeyHints.isEmpty ? "No key hints configured." : accessKeyHints.joined(separator: ", ")
    }

    public var sharedAccessSummaryText: String {
        switch sharedAccessState {
        case .localOnly:
            return "Local trust only."
        case .configuredDisabled:
            return "Shared access is configured but disabled."
        case .enabled:
            let suffix = accessKeyCount == 1 ? "key" : "keys"
            return "Shared access is enabled for \(accessKeyCount) \(suffix)."
        }
    }

    public var listenerLabel: String {
        "\(host):\(port)"
    }

    public var isRunning: Bool {
        lifecycle == .running
    }
}

public struct DesktopChatSessionState: Identifiable, Equatable, Sendable {
    public let id: String
    public var title: String
    public var serverSessionID: String
    public var branchID: String
    public var branchTitle: String
    public var transcript: [DesktopChatTranscriptEntry]
    public var statusText: String
    public var usageText: String
    public var requestID: String
    public var isStreaming: Bool
    public var exportPath: String
    public var createdAt: Date
    public var updatedAt: Date

    public init(
        id: String,
        title: String,
        serverSessionID: String,
        branchID: String = "main",
        branchTitle: String = "Main",
        transcript: [DesktopChatTranscriptEntry] = [],
        statusText: String = "Idle",
        usageText: String = "",
        requestID: String = "",
        isStreaming: Bool = false,
        exportPath: String = "",
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.title = title
        self.serverSessionID = serverSessionID
        self.branchID = branchID
        self.branchTitle = branchTitle
        self.transcript = transcript
        self.statusText = statusText
        self.usageText = usageText
        self.requestID = requestID
        self.isStreaming = isStreaming
        self.exportPath = exportPath
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }

    public var summaryText: String {
        transcript.last?.body.isEmpty == false ? transcript.last?.body ?? "" : statusText
    }
}

public enum DesktopBannerSeverity: Sendable {
    case warning
    case critical
}

public struct DesktopBannerState: Equatable, Sendable {
    public let title: String
    public let detail: String
    public let severity: DesktopBannerSeverity

    public init(title: String, detail: String, severity: DesktopBannerSeverity) {
        self.title = title
        self.detail = detail
        self.severity = severity
    }
}
