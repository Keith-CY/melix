import Foundation

public struct GatewayRateLimitDecision: Equatable, Sendable {
    public let allowed: Bool
    public let identity: String
    public let limitPerMinute: UInt32
    public let remaining: UInt32
    public let retryAfterSeconds: UInt32
}

public actor GatewayRateLimiter {
    private struct Window: Sendable {
        var startedAt: Date
        var count: UInt32
    }

    private var windows: [String: Window] = [:]
    private let now: @Sendable () -> Date

    public init(now: @escaping @Sendable () -> Date = Date.init) {
        self.now = now
    }

    public func admit(
        identity: String,
        limitPerMinute: UInt32
    ) -> GatewayRateLimitDecision {
        let normalizedIdentity = Self.normalizedIdentity(identity)
        let limit = max(limitPerMinute, 1)
        let currentTime = now()
        let window = windows[normalizedIdentity]
        let activeWindow: Window
        if let window, currentTime.timeIntervalSince(window.startedAt) < 60 {
            activeWindow = window
        } else {
            activeWindow = Window(startedAt: currentTime, count: 0)
        }

        guard activeWindow.count < limit else {
            let elapsed = currentTime.timeIntervalSince(activeWindow.startedAt)
            let retryAfter = UInt32(max(1, ceil(60 - elapsed)))
            windows[normalizedIdentity] = activeWindow
            return GatewayRateLimitDecision(
                allowed: false,
                identity: normalizedIdentity,
                limitPerMinute: limit,
                remaining: 0,
                retryAfterSeconds: retryAfter
            )
        }

        var updatedWindow = activeWindow
        updatedWindow.count += 1
        windows[normalizedIdentity] = updatedWindow
        return GatewayRateLimitDecision(
            allowed: true,
            identity: normalizedIdentity,
            limitPerMinute: limit,
            remaining: limit - updatedWindow.count,
            retryAfterSeconds: 0
        )
    }

    private static func normalizedIdentity(_ identity: String) -> String {
        let trimmed = identity.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? "local-trust" : trimmed
    }
}
