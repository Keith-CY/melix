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
    case paused = "Paused"
    case sleeping = "Sleeping"
    case stopping = "Stopping"
    case stopped = "Stopped"
    case error = "Error"
    case unavailable = "Unavailable"
}

public enum DesktopServerPowerState: String, Codable, Sendable {
    case active = "Active"
    case lightSleep = "Light Sleep"
    case deepSleep = "Deep Sleep"
    case stopped = "Stopped"
    case unavailable = "Unavailable"
}

public enum DesktopServerWakeReason: String, Codable, Sendable {
    case unspecified = "Unspecified"
    case initialBoot = "Initial Boot"
    case operatorResume = "Operator Resume"
    case requestActivity = "Request Activity"
    case toolActivity = "Tool Activity"
    case policyApply = "Policy Apply"
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
    public var powerState: DesktopServerPowerState
    public var wakeReason: DesktopServerWakeReason
    public var idleTimerSeconds: Int
    public var autoSleepEnabled: Bool
    public var lightSleepAfterSeconds: Int
    public var deepSleepAfterSeconds: Int
    public var lastError: String
    public var lastKnownModelStateText: String
    public var activeAuthSessionCount: Int
    public var rememberedAuthSessionCount: Int
    public var expiredRememberedSessionCount: Int
    public var authSessionRetentionSeconds: Int
    public var lastAuthSessionSignOutLatencyMs: Double
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
        powerState: DesktopServerPowerState = .unavailable,
        wakeReason: DesktopServerWakeReason = .unspecified,
        idleTimerSeconds: Int = 0,
        autoSleepEnabled: Bool = false,
        lightSleepAfterSeconds: Int = 0,
        deepSleepAfterSeconds: Int = 0,
        lastError: String = "",
        lastKnownModelStateText: String = "",
        activeAuthSessionCount: Int = 0,
        rememberedAuthSessionCount: Int = 0,
        expiredRememberedSessionCount: Int = 0,
        authSessionRetentionSeconds: Int = 0,
        lastAuthSessionSignOutLatencyMs: Double = 0,
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
        self.powerState = powerState
        self.wakeReason = wakeReason
        self.idleTimerSeconds = idleTimerSeconds
        self.autoSleepEnabled = autoSleepEnabled
        self.lightSleepAfterSeconds = lightSleepAfterSeconds
        self.deepSleepAfterSeconds = deepSleepAfterSeconds
        self.lastError = lastError
        self.lastKnownModelStateText = lastKnownModelStateText
        self.activeAuthSessionCount = activeAuthSessionCount
        self.rememberedAuthSessionCount = rememberedAuthSessionCount
        self.expiredRememberedSessionCount = expiredRememberedSessionCount
        self.authSessionRetentionSeconds = authSessionRetentionSeconds
        self.lastAuthSessionSignOutLatencyMs = lastAuthSessionSignOutLatencyMs
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

    public var persistentSessionSummaryText: String {
        let retentionText = authSessionRetentionSeconds > 0 ? " TTL \(authSessionRetentionSeconds)s." : ""
        if rememberedAuthSessionCount > 0 {
            let expiredText = expiredRememberedSessionCount > 0
                ? " \(expiredRememberedSessionCount) expired pruned."
                : ""
            return "\(rememberedAuthSessionCount) remembered sessions active, \(activeAuthSessionCount) total active.\(expiredText)\(retentionText)"
        }
        if activeAuthSessionCount > 0 {
            return "\(activeAuthSessionCount) gateway sessions active.\(retentionText)"
        }
        return "No remembered gateway sessions.\(retentionText)"
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case modelID = "model_id"
        case host
        case port
        case authMode = "auth_mode"
        case authTokenHint = "auth_token_hint"
        case sharedAccessState = "shared_access_state"
        case accessKeyCount = "access_key_count"
        case accessKeyHints = "access_key_hints"
        case rateLimitPerMinute = "rate_limit_per_minute"
        case timeoutSeconds = "timeout_seconds"
        case servingDefaults = "serving_defaults"
        case lifecycle
        case powerState = "power_state"
        case wakeReason = "wake_reason"
        case idleTimerSeconds = "idle_timer_seconds"
        case autoSleepEnabled = "auto_sleep_enabled"
        case lightSleepAfterSeconds = "light_sleep_after_seconds"
        case deepSleepAfterSeconds = "deep_sleep_after_seconds"
        case lastError = "last_error"
        case lastKnownModelStateText = "last_known_model_state_text"
        case activeAuthSessionCount = "active_auth_session_count"
        case rememberedAuthSessionCount = "remembered_auth_session_count"
        case expiredRememberedSessionCount = "expired_remembered_session_count"
        case authSessionRetentionSeconds = "auth_session_retention_seconds"
        case lastAuthSessionSignOutLatencyMs = "last_auth_session_sign_out_latency_ms"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        title = try container.decode(String.self, forKey: .title)
        modelID = try container.decode(String.self, forKey: .modelID)
        host = try container.decodeIfPresent(String.self, forKey: .host) ?? "127.0.0.1"
        port = try container.decodeIfPresent(Int.self, forKey: .port) ?? 8080
        authMode = try container.decodeIfPresent(DesktopServerAuthMode.self, forKey: .authMode) ?? .none
        authTokenHint = try container.decodeIfPresent(String.self, forKey: .authTokenHint) ?? ""
        sharedAccessState = try container.decodeIfPresent(DesktopSharedAccessState.self, forKey: .sharedAccessState) ?? .localOnly
        accessKeyCount = try container.decodeIfPresent(Int.self, forKey: .accessKeyCount) ?? 0
        accessKeyHints = try container.decodeIfPresent([String].self, forKey: .accessKeyHints) ?? []
        rateLimitPerMinute = try container.decodeIfPresent(Int.self, forKey: .rateLimitPerMinute) ?? 120
        timeoutSeconds = try container.decodeIfPresent(Int.self, forKey: .timeoutSeconds) ?? 120
        servingDefaults = try container.decodeIfPresent(DesktopServerServingDefaultsState.self, forKey: .servingDefaults)
            ?? DesktopServerServingDefaultsState()
        lifecycle = try container.decodeIfPresent(DesktopServerSessionLifecycle.self, forKey: .lifecycle) ?? .draft
        powerState = try container.decodeIfPresent(DesktopServerPowerState.self, forKey: .powerState) ?? .unavailable
        wakeReason = try container.decodeIfPresent(DesktopServerWakeReason.self, forKey: .wakeReason) ?? .unspecified
        idleTimerSeconds = try container.decodeIfPresent(Int.self, forKey: .idleTimerSeconds) ?? 0
        autoSleepEnabled = try container.decodeIfPresent(Bool.self, forKey: .autoSleepEnabled) ?? false
        lightSleepAfterSeconds = try container.decodeIfPresent(Int.self, forKey: .lightSleepAfterSeconds) ?? 0
        deepSleepAfterSeconds = try container.decodeIfPresent(Int.self, forKey: .deepSleepAfterSeconds) ?? 0
        lastError = try container.decodeIfPresent(String.self, forKey: .lastError) ?? ""
        lastKnownModelStateText = try container.decodeIfPresent(String.self, forKey: .lastKnownModelStateText) ?? ""
        activeAuthSessionCount = try container.decodeIfPresent(Int.self, forKey: .activeAuthSessionCount) ?? 0
        rememberedAuthSessionCount = try container.decodeIfPresent(Int.self, forKey: .rememberedAuthSessionCount) ?? 0
        expiredRememberedSessionCount = try container.decodeIfPresent(Int.self, forKey: .expiredRememberedSessionCount) ?? 0
        authSessionRetentionSeconds = try container.decodeIfPresent(Int.self, forKey: .authSessionRetentionSeconds) ?? 0
        lastAuthSessionSignOutLatencyMs = try container.decodeIfPresent(Double.self, forKey: .lastAuthSessionSignOutLatencyMs) ?? 0
        createdAt = try container.decodeIfPresent(Date.self, forKey: .createdAt) ?? Date()
        updatedAt = try container.decodeIfPresent(Date.self, forKey: .updatedAt) ?? Date()
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(title, forKey: .title)
        try container.encode(modelID, forKey: .modelID)
        try container.encode(host, forKey: .host)
        try container.encode(port, forKey: .port)
        try container.encode(authMode, forKey: .authMode)
        try container.encode(authTokenHint, forKey: .authTokenHint)
        try container.encode(sharedAccessState, forKey: .sharedAccessState)
        try container.encode(accessKeyCount, forKey: .accessKeyCount)
        try container.encode(accessKeyHints, forKey: .accessKeyHints)
        try container.encode(rateLimitPerMinute, forKey: .rateLimitPerMinute)
        try container.encode(timeoutSeconds, forKey: .timeoutSeconds)
        try container.encode(servingDefaults, forKey: .servingDefaults)
        try container.encode(lifecycle, forKey: .lifecycle)
        try container.encode(powerState, forKey: .powerState)
        try container.encode(wakeReason, forKey: .wakeReason)
        try container.encode(idleTimerSeconds, forKey: .idleTimerSeconds)
        try container.encode(autoSleepEnabled, forKey: .autoSleepEnabled)
        try container.encode(lightSleepAfterSeconds, forKey: .lightSleepAfterSeconds)
        try container.encode(deepSleepAfterSeconds, forKey: .deepSleepAfterSeconds)
        try container.encode(lastError, forKey: .lastError)
        try container.encode(lastKnownModelStateText, forKey: .lastKnownModelStateText)
        try container.encode(activeAuthSessionCount, forKey: .activeAuthSessionCount)
        try container.encode(rememberedAuthSessionCount, forKey: .rememberedAuthSessionCount)
        try container.encode(expiredRememberedSessionCount, forKey: .expiredRememberedSessionCount)
        try container.encode(authSessionRetentionSeconds, forKey: .authSessionRetentionSeconds)
        try container.encode(lastAuthSessionSignOutLatencyMs, forKey: .lastAuthSessionSignOutLatencyMs)
        try container.encode(createdAt, forKey: .createdAt)
        try container.encode(updatedAt, forKey: .updatedAt)
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
    case info
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

public extension DesktopServerSessionState {
    var isInteractiveReady: Bool {
        lifecycle == .running || lifecycle == .sleeping
    }

    var retainsGatewayAccessConfiguration: Bool {
        switch lifecycle {
        case .starting, .running, .paused, .sleeping:
            return true
        default:
            return false
        }
    }

    var canStart: Bool {
        switch lifecycle {
        case .draft, .stopped, .error, .unavailable:
            return true
        default:
            return false
        }
    }

    var canPause: Bool {
        lifecycle == .running
    }

    var canResume: Bool {
        lifecycle == .paused
    }

    var canWake: Bool {
        lifecycle == .sleeping
    }

    var canStop: Bool {
        switch lifecycle {
        case .starting, .running, .paused, .sleeping, .error:
            return true
        default:
            return false
        }
    }

    var lifecycleSummaryText: String {
        "\(lifecycle.rawValue) • \(powerState.rawValue)"
    }

    var idlePolicySummaryText: String {
        guard autoSleepEnabled else {
            return "Auto sleep disabled."
        }

        let lightSummary = lightSleepAfterSeconds > 0 ? "light after \(lightSleepAfterSeconds)s" : "light sleep threshold unset"
        let deepSummary = deepSleepAfterSeconds > 0 ? "deep after \(deepSleepAfterSeconds)s" : "deep sleep threshold unset"
        return "Auto sleep enabled • \(lightSummary) • \(deepSummary)"
    }

    var runtimeDetailText: String {
        let idleSummary = idleTimerSeconds > 0 ? "Idle \(idleTimerSeconds)s" : "Idle timer idle"
        return "\(lifecycleSummaryText) • Wake \(wakeReason.rawValue) • \(idleSummary)"
    }

    var lifecycleBannerState: DesktopBannerState? {
        switch lifecycle {
        case .draft:
            return nil
        case .starting:
            return DesktopBannerState(
                title: "\(title) Is Starting",
                detail: "Preparing \(listenerLabel) for \(modelID). Requests stay queued until the session reaches Running.",
                severity: .info
            )
        case .running:
            return nil
        case .paused:
            return DesktopBannerState(
                title: "\(title) Is Paused",
                detail: "Resume the session to accept prompts and API requests. \(idlePolicySummaryText)",
                severity: .warning
            )
        case .sleeping:
            return DesktopBannerState(
                title: "\(title) Is Sleeping",
                detail: "\(powerState.rawValue) mode is active. The next request can wake the session automatically, or you can wake it manually now.",
                severity: .info
            )
        case .stopping:
            return DesktopBannerState(
                title: "\(title) Is Stopping",
                detail: "Melix is draining the session and closing \(listenerLabel).",
                severity: .info
            )
        case .stopped:
            return DesktopBannerState(
                title: "\(title) Is Stopped",
                detail: "Start the session to serve \(modelID) at \(listenerLabel).",
                severity: .warning
            )
        case .error:
            return DesktopBannerState(
                title: "\(title) Needs Recovery",
                detail: lastError.isEmpty ? "The session entered an error state." : lastError,
                severity: .critical
            )
        case .unavailable:
            return DesktopBannerState(
                title: "\(title) Is Unavailable",
                detail: "Bind the session to an available text model before serving requests.",
                severity: .warning
            )
        }
    }

    var chatWorkspaceNoticeState: DesktopBannerState? {
        switch lifecycle {
        case .running:
            return nil
        case .sleeping:
            return DesktopBannerState(
                title: "\(title) Will Wake On Demand",
                detail: "You can send the next prompt immediately. Melix will wake the session from \(powerState.rawValue.lowercased()) first.",
                severity: .info
            )
        case .paused:
            return DesktopBannerState(
                title: "\(title) Is Paused",
                detail: "Resume the bound server session before sending prompts from this chat.",
                severity: .warning
            )
        case .starting:
            return DesktopBannerState(
                title: "\(title) Is Starting",
                detail: "Chat stays read-only until the server session finishes booting.",
                severity: .info
            )
        case .stopping:
            return DesktopBannerState(
                title: "\(title) Is Stopping",
                detail: "This chat stays read-only while the bound server session drains.",
                severity: .warning
            )
        case .stopped:
            return DesktopBannerState(
                title: "\(title) Is Stopped",
                detail: "Start the bound server session before sending prompts from this chat.",
                severity: .warning
            )
        case .error:
            return DesktopBannerState(
                title: "\(title) Needs Recovery",
                detail: lastError.isEmpty ? "The bound server session failed." : lastError,
                severity: .critical
            )
        case .draft, .unavailable:
            return DesktopBannerState(
                title: "No Active Server Session",
                detail: "Choose a valid server session and start it before sending prompts from this chat.",
                severity: .warning
            )
        }
    }
}
