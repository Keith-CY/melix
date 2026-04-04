import Foundation

public struct ConnectionLifecyclePolicy: Sendable, Equatable {
    private static let defaultKeepaliveIntervalSeconds: TimeInterval = 15
    private static let defaultDisconnectGraceSeconds: TimeInterval = 5
    private static let defaultRetryBackoffSeconds: TimeInterval = 0.5
    private static let defaultRetryLimit: Int = 0
    private static let defaultResumeBufferLimit: Int = 512

    public let keepaliveInterval: TimeInterval?
    public let disconnectGracePeriod: TimeInterval
    public let retryBackoff: TimeInterval
    public let retryLimit: Int
    public let resumeBufferLimit: Int

    public init(
        keepaliveInterval: TimeInterval? = 15,
        disconnectGracePeriod: TimeInterval = 5,
        retryBackoff: TimeInterval = 0.5,
        retryLimit: Int = 0,
        resumeBufferLimit: Int = 512
    ) {
        self.keepaliveInterval = keepaliveInterval
        self.disconnectGracePeriod = disconnectGracePeriod
        self.retryBackoff = retryBackoff
        self.retryLimit = retryLimit
        self.resumeBufferLimit = max(1, resumeBufferLimit)
    }

    public static func fromEnvironment(
        _ environment: [String: String] = ProcessInfo.processInfo.environment
    ) -> ConnectionLifecyclePolicy {
        ConnectionLifecyclePolicy(
            keepaliveInterval: keepaliveInterval(from: environment["MELIX_CONNECTION_KEEPALIVE_INTERVAL_SECONDS"]),
            disconnectGracePeriod: positiveTimeInterval(
                from: environment["MELIX_CONNECTION_DISCONNECT_GRACE_SECONDS"],
                defaultValue: defaultDisconnectGraceSeconds
            ),
            retryBackoff: positiveTimeInterval(
                from: environment["MELIX_CONNECTION_RETRY_BACKOFF_SECONDS"],
                defaultValue: defaultRetryBackoffSeconds
            ),
            retryLimit: nonNegativeInt(
                from: environment["MELIX_CONNECTION_RETRY_LIMIT"],
                defaultValue: defaultRetryLimit
            ),
            resumeBufferLimit: positiveInt(
                from: environment["MELIX_CONNECTION_RESUME_BUFFER_LIMIT"],
                defaultValue: defaultResumeBufferLimit
            )
        )
    }

    private static func keepaliveInterval(from rawValue: String?) -> TimeInterval? {
        guard let rawValue else {
            return defaultKeepaliveIntervalSeconds
        }
        guard let parsed = Double(rawValue) else {
            return defaultKeepaliveIntervalSeconds
        }
        guard parsed > 0 else {
            return nil
        }
        return parsed
    }

    private static func positiveTimeInterval(from rawValue: String?, defaultValue: TimeInterval) -> TimeInterval {
        guard let rawValue, let parsed = Double(rawValue), parsed > 0 else {
            return defaultValue
        }
        return parsed
    }

    private static func nonNegativeInt(from rawValue: String?, defaultValue: Int) -> Int {
        guard let rawValue, let parsed = Int(rawValue), parsed >= 0 else {
            return defaultValue
        }
        return parsed
    }

    private static func positiveInt(from rawValue: String?, defaultValue: Int) -> Int {
        guard let rawValue, let parsed = Int(rawValue), parsed > 0 else {
            return defaultValue
        }
        return parsed
    }
}

public enum ConnectionLifecycleEvent: Sendable, Equatable {
    case active
    case disconnectGraceStarted(timeoutMs: Double)
    case resumed(recoveryLatencyMs: Double)
    case retrying(attempt: Int)
    case terminalFailure(code: String, message: String)
    case cancelled
    case completed
}
