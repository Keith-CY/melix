import Foundation
import MelixControlPlaneProtocol

public struct DesktopDashboardCard: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let value: String
    public let detail: String

    public init(id: String, title: String, value: String, detail: String) {
        self.id = id
        self.title = title
        self.value = value
        self.detail = detail
    }
}

public struct DesktopQueueLaneRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let laneClass: String
    public let queuedRequests: UInt32
    public let activeRequests: UInt32
    public let backpressure: Double
    public let priorityScore: Double

    public init(
        id: String,
        laneClass: String,
        queuedRequests: UInt32,
        activeRequests: UInt32,
        backpressure: Double,
        priorityScore: Double
    ) {
        self.id = id
        self.laneClass = laneClass
        self.queuedRequests = queuedRequests
        self.activeRequests = activeRequests
        self.backpressure = backpressure
        self.priorityScore = priorityScore
    }
}

public struct DesktopKeyValueRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let key: String
    public let value: String

    public init(id: String, key: String, value: String) {
        self.id = id
        self.key = key
        self.value = value
    }
}

public struct DesktopLogEntry: Identifiable, Equatable, Sendable {
    public let id: String
    public let kind: String
    public let message: String
    public let detail: String
    public let level: String

    public init(kind: String, message: String, detail: String, level: String) {
        self.id = "\(kind)-\(message)-\(detail)-\(level)"
        self.kind = kind
        self.message = message
        self.detail = detail
        self.level = level
    }
}

public struct DesktopMetricRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let name: String
    public let value: String

    public init(name: String, value: String) {
        self.id = name
        self.name = name
        self.value = value
    }
}

public struct DesktopAPIReferenceRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let method: String
    public let path: String
    public let summary: String
    public let streaming: Bool

    public init(method: String, path: String, summary: String, streaming: Bool) {
        self.id = "\(method) \(path)"
        self.method = method
        self.path = path
        self.summary = summary
        self.streaming = streaming
    }
}

public struct DesktopFoundationState: Equatable, Sendable {
    public let title: String
    public let dashboardCards: [DesktopDashboardCard]
    public let queueLanes: [DesktopQueueLaneRow]
    public let models: [RuntimeModelRow]
    public let settings: [DesktopKeyValueRow]
    public let logs: [DesktopLogEntry]
    public let benchMetrics: [DesktopMetricRow]
    public let apiReference: [DesktopAPIReferenceRow]

    public static func build(
        statusTitle: String,
        serverStateText: String,
        snapshot: Melix_Controlplane_V1_ServerSnapshot,
        protocolVersion: String,
        serverVersion: String,
        daemonInstanceID: String,
        features: [String],
        lastError: String?,
        recentEvents: [DesktopLogEntry]
    ) -> DesktopFoundationState {
        let loadedModels = snapshot.models.filter { model in
            switch model.state {
            case .modelWarm, .modelPinned:
                return true
            default:
                return false
            }
        }

        let dashboardCards = [
            DesktopDashboardCard(
                id: "server",
                title: "Server",
                value: serverStateText,
                detail: "\(snapshot.queues.activeRequests) active / \(snapshot.queues.queuedRequests) queued"
            ),
            DesktopDashboardCard(
                id: "models",
                title: "Models",
                value: "\(loadedModels.count)/\(snapshot.models.count)",
                detail: "loaded / discovered"
            ),
            DesktopDashboardCard(
                id: "sessions",
                title: "Sessions",
                value: "\(snapshot.sessions.count)",
                detail: "tracked branches"
            ),
            DesktopDashboardCard(
                id: "cache",
                title: "Cache",
                value: "\(formatBytes(snapshot.cache.l1Bytes)) / \(formatBytes(snapshot.cache.l2Bytes))",
                detail: "L1 / L2"
            ),
            DesktopDashboardCard(
                id: "backpressure",
                title: "Backpressure",
                value: formatDouble(snapshot.queues.backpressure),
                detail: "scheduler pressure"
            ),
            DesktopDashboardCard(
                id: "memory",
                title: "Memory",
                value: formatBytes(snapshot.resources.memoryUsedBytes),
                detail: "of \(formatBytes(snapshot.resources.memoryTotalBytes))"
            ),
        ]

        let queueLanes = snapshot.queues.lanes
            .sorted { $0.laneID < $1.laneID }
            .map { lane in
                DesktopQueueLaneRow(
                    id: lane.laneID,
                    laneClass: lane.laneClass,
                    queuedRequests: lane.queuedRequests,
                    activeRequests: lane.activeRequests,
                    backpressure: lane.backpressure,
                    priorityScore: lane.priorityScore
                )
            }

        let settings = [
            DesktopKeyValueRow(id: "protocol", key: "Protocol", value: protocolVersion),
            DesktopKeyValueRow(id: "server-version", key: "Server Version", value: serverVersion),
            DesktopKeyValueRow(id: "daemon-id", key: "Daemon Instance", value: daemonInstanceID.isEmpty ? "unknown" : daemonInstanceID),
            DesktopKeyValueRow(id: "features", key: "Features", value: features.isEmpty ? "none" : features.sorted().joined(separator: ", ")),
            DesktopKeyValueRow(id: "socket", key: "Control Plane", value: "local XPC"),
            DesktopKeyValueRow(id: "api-surface", key: "API Surface", value: "text phase-4 foundation"),
        ]

        let benchMetrics = snapshot.metrics.values
            .sorted { $0.key < $1.key }
            .map { key, value in
                DesktopMetricRow(name: key, value: formatDouble(value))
            }

        var logs = recentEvents
        if let lastError, !lastError.isEmpty, logs.contains(where: { $0.message == lastError }) == false {
            logs.insert(
                DesktopLogEntry(kind: "error", message: lastError, detail: "view-model", level: "error"),
                at: 0
            )
        }
        for recentError in snapshot.recentErrors.reversed() {
            logs.insert(
                DesktopLogEntry(
                    kind: recentError.code.isEmpty ? "recent-error" : recentError.code,
                    message: recentError.message,
                    detail: "control-plane",
                    level: "error"
                ),
                at: 0
            )
        }

        return DesktopFoundationState(
            title: statusTitle,
            dashboardCards: dashboardCards,
            queueLanes: queueLanes,
            models: snapshot.models
                .sorted { $0.modelID < $1.modelID }
                .map(makeRuntimeModelRow),
            settings: settings,
            logs: Array(logs.prefix(40)),
            benchMetrics: benchMetrics,
            apiReference: APIReferenceCatalog.phaseFourFoundation
        )
    }
}

enum APIReferenceCatalog {
    static let phaseFourFoundation: [DesktopAPIReferenceRow] = [
        DesktopAPIReferenceRow(
            method: "GET",
            path: "/v1/models",
            summary: "List local models and their runtime state.",
            streaming: false
        ),
        DesktopAPIReferenceRow(
            method: "POST",
            path: "/v1/chat/completions",
            summary: "OpenAI-style chat completions over the shared text runtime.",
            streaming: true
        ),
        DesktopAPIReferenceRow(
            method: "POST",
            path: "/v1/completions",
            summary: "Prompt-style completions mapped onto the same text runtime.",
            streaming: true
        ),
        DesktopAPIReferenceRow(
            method: "POST",
            path: "/v1/responses",
            summary: "Responses-style text execution with reasoning and tool deltas.",
            streaming: true
        ),
        DesktopAPIReferenceRow(
            method: "POST",
            path: "/v1/messages",
            summary: "Message-oriented execution over the Phase 4 text surface.",
            streaming: true
        ),
    ]
}

private func formatDouble(_ value: Double) -> String {
    String(format: "%.2f", value)
}

private func formatBytes(_ bytes: UInt64) -> String {
    let formatter = ByteCountFormatter()
    formatter.countStyle = .binary
    formatter.allowedUnits = [.useKB, .useMB, .useGB]
    formatter.includesUnit = true
    formatter.includesCount = true
    return formatter.string(fromByteCount: Int64(bytes))
}
