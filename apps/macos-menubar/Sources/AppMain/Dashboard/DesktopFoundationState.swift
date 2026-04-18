import Foundation
import MelixControlPlaneCore
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
        let sanitizedMessage = RichOutputSanitizer.sanitized(message)
        let sanitizedDetail = RichOutputSanitizer.sanitized(detail)
        self.id = "\(kind)-\(sanitizedMessage)-\(sanitizedDetail)-\(level)"
        self.kind = kind
        self.message = sanitizedMessage
        self.detail = sanitizedDetail
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
    public let surfaceID: String
    public let surfaceTitle: String
    public let method: String
    public let path: String
    public let summary: String
    public let streaming: Bool

    public init(
        id: String,
        surfaceID: String,
        surfaceTitle: String,
        method: String,
        path: String,
        summary: String,
        streaming: Bool
    ) {
        self.id = id
        self.surfaceID = surfaceID
        self.surfaceTitle = surfaceTitle
        self.method = method
        self.path = path
        self.summary = summary
        self.streaming = streaming
    }
}

public struct DesktopAPISurfaceRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let summary: String
    public let statusText: String
    public let compatibilityNote: String
    public let endpointIDs: [String]
    public let shipped: Bool

    public init(
        id: String,
        title: String,
        summary: String,
        statusText: String,
        compatibilityNote: String,
        endpointIDs: [String],
        shipped: Bool
    ) {
        self.id = id
        self.title = title
        self.summary = summary
        self.statusText = statusText
        self.compatibilityNote = compatibilityNote
        self.endpointIDs = endpointIDs
        self.shipped = shipped
    }
}

public struct DesktopFoundationState: Equatable, Sendable {
    public let title: String
    public let serverStateText: String
    public let connectionStateText: String
    public let connectionDetailText: String
    public let dashboardCards: [DesktopDashboardCard]
    public let queueLanes: [DesktopQueueLaneRow]
    public let models: [RuntimeModelRow]
    public let settings: [DesktopKeyValueRow]
    public let logs: [DesktopLogEntry]
    public let benchMetrics: [DesktopMetricRow]
    public let apiSurfaces: [DesktopAPISurfaceRow]
    public let apiReference: [DesktopAPIReferenceRow]

    public static func build(
        statusTitle: String,
        serverStateText: String,
        connectionStateText: String,
        connectionDetailText: String,
        snapshot: Melix_Controlplane_V1_ServerSnapshot,
        protocolVersion: String,
        serverVersion: String,
        daemonInstanceID: String,
        features: [String],
        productUpdateSummary: String?,
        productUpdateDetail: String?,
        lastError: String?,
        recentEvents: [DesktopLogEntry]
    ) -> DesktopFoundationState {
        let apiSurfaces = resolvedAPISurfaces(from: snapshot.apiOnboarding)
        let apiReference = resolvedAPIReference(
            from: snapshot.apiOnboarding,
            surfaces: apiSurfaces
        )
        let loadedModels = snapshot.models.filter { model in
            switch model.state {
            case .modelWarm, .modelPinned:
                return true
            default:
                return false
            }
        }
        let pinnedModels = snapshot.models.filter { model in
            model.residency.pinned || model.pinned || model.state == .modelPinned
        }
        let pinRequestedModels = snapshot.models.filter { model in
            model.residency.pinRequested || model.settings.pinOnLoad
        }
        let ttlManagedModels = snapshot.models.filter { model in
            let ttl = max(model.residency.ttlSeconds, model.settings.ttlSeconds)
            return ttl > 0
        }
        let evictionTTLCount = metricValue(snapshot.metrics, key: "control_plane.model_eviction_ttl_count")
        let evictionLRUCount = metricValue(snapshot.metrics, key: "control_plane.model_eviction_lru_same_capability_count")
        let evictionOtherCount = metricValue(snapshot.metrics, key: "control_plane.model_eviction_other_count")
        let evictionProtectedCount = metricValue(snapshot.metrics, key: "control_plane.model_eviction_last_pinned_protected_count")
        let evictionFallbackCount = Double(snapshot.models.filter { model in
            isEvictionReason(model.residency.transitionReason)
        }.count)
        let evictionCount = max(
            evictionTTLCount + evictionLRUCount + evictionOtherCount,
            evictionFallbackCount
        )
        let modelGuardAlerts = snapshot.models.filter { model in
            isMemoryProtectionReason(model.residency.transitionReason)
        }
        let recentGuardAlerts = snapshot.recentErrors.filter { error in
            isMemoryProtectionReason(error.code) || isMemoryProtectionReason(error.message)
        }
        let guardCount = max(Double(modelGuardAlerts.count), Double(recentGuardAlerts.count))
        let guardDetail = recentGuardAlerts.first?.message
            ?? modelGuardAlerts.first.map { formatTransitionReason($0.residency.transitionReason) }
            ?? "No active memory guard failures"

        let dashboardCards = [
            DesktopDashboardCard(
                id: "server",
                title: "Server",
                value: serverStateText,
                detail: "\(snapshot.queues.activeRequests) active / \(snapshot.queues.queuedRequests) queued"
            ),
            DesktopDashboardCard(
                id: "connection",
                title: "Connection",
                value: connectionStateText,
                detail: connectionDetailText
            ),
            DesktopDashboardCard(
                id: "models",
                title: "Models",
                value: "\(loadedModels.count)/\(snapshot.models.count)",
                detail: "loaded / discovered"
            ),
            DesktopDashboardCard(
                id: "residency",
                title: "Residency",
                value: "\(pinnedModels.count) pinned",
                detail: "\(loadedModels.count) loaded • \(pinRequestedModels.count) requested • \(ttlManagedModels.count) ttl"
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
                id: "evictions",
                title: "Evictions",
                value: String(Int(evictionCount)),
                detail: "ttl \(Int(evictionTTLCount)) • lru \(Int(evictionLRUCount)) • protected \(Int(evictionProtectedCount))"
            ),
            DesktopDashboardCard(
                id: "memory",
                title: "Memory",
                value: formatBytes(snapshot.resources.memoryUsedBytes),
                detail: "of \(formatBytes(snapshot.resources.memoryTotalBytes))"
            ),
            DesktopDashboardCard(
                id: "guards",
                title: "Memory Guards",
                value: String(Int(guardCount)),
                detail: guardDetail
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

        var settings = [
            DesktopKeyValueRow(id: "protocol", key: "Protocol", value: protocolVersion),
            DesktopKeyValueRow(id: "server-version", key: "Server Version", value: serverVersion),
            DesktopKeyValueRow(id: "daemon-id", key: "Daemon Instance", value: daemonInstanceID.isEmpty ? "unknown" : daemonInstanceID),
            DesktopKeyValueRow(id: "features", key: "Features", value: features.isEmpty ? "none" : features.sorted().joined(separator: ", ")),
            DesktopKeyValueRow(id: "connection", key: "Connection", value: connectionStateText),
            DesktopKeyValueRow(id: "stream", key: "Event Stream", value: connectionDetailText),
            DesktopKeyValueRow(id: "socket", key: "Control Plane", value: "local XPC"),
            DesktopKeyValueRow(
                id: "api-surface",
                key: "API Surface",
                value: apiSurfaces.isEmpty ? "not published" : "\(apiSurfaces.count) published surfaces"
            ),
        ]
        if let productUpdateSummary, productUpdateSummary.isEmpty == false {
            settings.append(
                DesktopKeyValueRow(id: "product-update", key: "Update", value: productUpdateSummary)
            )
            if let productUpdateDetail, productUpdateDetail.isEmpty == false {
                settings.append(
                    DesktopKeyValueRow(id: "product-update-detail", key: "Update Detail", value: productUpdateDetail)
                )
            }
        }
        settings.append(
            DesktopKeyValueRow(
                id: "embedding-model",
                key: "Embedding Model",
                value: snapshot.toolingSettings.embedding.modelID.isEmpty
                    ? "not configured"
                    : snapshot.toolingSettings.embedding.modelID
            )
        )
        if snapshot.toolingSettings.embedding.modelID.isEmpty == false {
            settings.append(
                DesktopKeyValueRow(
                    id: "embedding-preload",
                    key: "Embedding Preload",
                    value: embeddingToolingDetail(snapshot.toolingSettings.embedding)
                )
            )
        }
        settings.append(
            DesktopKeyValueRow(
                id: "tool-parser-modes",
                key: "Built-in Tool Parsers",
                value: snapshot.toolingSettings.builtinToolParserModes.isEmpty
                    ? "none"
                    : snapshot.toolingSettings.builtinToolParserModes.joined(separator: ", ")
            )
        )
        settings.append(
            DesktopKeyValueRow(
                id: "mcp-default-parser",
                key: "MCP Default Parser",
                value: snapshot.toolingSettings.mcpDefaultParserMode.isEmpty
                    ? "not configured"
                    : snapshot.toolingSettings.mcpDefaultParserMode
            )
        )
        settings.append(
            DesktopKeyValueRow(
                id: "mcp-config-path",
                key: "MCP Config",
                value: snapshot.toolingSettings.mcpConfigPath.isEmpty
                    ? "not configured"
                    : snapshot.toolingSettings.mcpConfigPath
            )
        )
        settings.append(
            DesktopKeyValueRow(
                id: "mcp-summary",
                key: "MCP Summary",
                value: "\(snapshot.toolingSettings.mcpEnabledSourceCount) enabled sources • \(snapshot.toolingSettings.mcpResolvedToolCount) tools"
            )
        )
        for configPath in snapshot.toolingSettings.configPaths {
            settings.append(
                DesktopKeyValueRow(
                    id: "config-path-\(configPath.pathID)",
                    key: toolingConfigPathLabel(configPath.pathID),
                    value: configPath.path
                )
            )
        }
        settings.append(
            DesktopKeyValueRow(
                id: "boot-arguments",
                key: "Boot Arguments",
                value: snapshot.toolingSettings.additionalArguments.isEmpty
                    ? "none"
                    : snapshot.toolingSettings.additionalArguments.joined(separator: " ")
            )
        )

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
            serverStateText: serverStateText,
            connectionStateText: connectionStateText,
            connectionDetailText: connectionDetailText,
            dashboardCards: dashboardCards,
            queueLanes: queueLanes,
            models: snapshot.models
                .sorted { $0.modelID < $1.modelID }
                .map(makeRuntimeModelRow),
            settings: settings,
            logs: Array(logs.prefix(40)),
            benchMetrics: benchMetrics,
            apiSurfaces: apiSurfaces,
            apiReference: apiReference
        )
    }
}

private func metricValue(
    _ metrics: Melix_Controlplane_V1_MetricsSummary,
    key: String
) -> Double {
    metrics.values[key] ?? 0
}

private func isEvictionReason(_ reason: String) -> Bool {
    let normalized = reason.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard !normalized.isEmpty else {
        return false
    }
    return normalized.contains("ttl_expired")
        || normalized.contains("lru_same_capability")
        || normalized.contains("operator_unload")
}

private func isMemoryProtectionReason(_ reason: String) -> Bool {
    let normalized = reason.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard !normalized.isEmpty else {
        return false
    }
    return normalized.contains("memory_budget")
        || normalized.contains("prefill_memory_guard")
        || normalized.contains("quadratic_prefill_guard")
}

private func formatTransitionReason(_ reason: String) -> String {
    let separatorNormalized = reason.replacingOccurrences(of: "_", with: " ")
    guard let first = separatorNormalized.first else {
        return "Unknown"
    }
    return String(first).uppercased() + separatorNormalized.dropFirst()
}

private func embeddingToolingDetail(
    _ summary: Melix_Controlplane_V1_EmbeddingToolingSummary
) -> String {
    var parts: [String] = []
    parts.append(modelStateText(summary.modelState))
    parts.append(summary.preloaded ? "preloaded" : "not preloaded")
    if !summary.familyID.isEmpty || !summary.backendID.isEmpty {
        let identity = [summary.familyID, summary.backendID]
            .filter { !$0.isEmpty }
            .joined(separator: " / ")
        if !identity.isEmpty {
            parts.append(identity)
        }
    }
    return parts.joined(separator: " • ")
}

private func modelStateText(
    _ state: Melix_Controlplane_V1_ModelState
) -> String {
    switch state {
    case .modelDiscovered:
        return "Discovered"
    case .modelWarm:
        return "Warm"
    case .modelPinned:
        return "Pinned"
    case .modelLoading:
        return "Loading"
    case .modelEvicting:
        return "Evicting"
    case .modelUnloaded:
        return "Unloaded"
    case .modelFailed:
        return "Failed"
    default:
        return "Unknown"
    }
}

private func toolingConfigPathLabel(_ pathID: String) -> String {
    switch pathID {
    case "gateway_config_store_path":
        return "Gateway Config Store"
    case "gateway_serving_defaults_store_path":
        return "Serving Defaults Store"
    case "control_plane_metrics_path":
        return "Control Plane Metrics"
    default:
        return pathID.replacingOccurrences(of: "_", with: " ")
    }
}

private func resolvedAPISurfaces(
    from summary: Melix_Controlplane_V1_APIOnboardingSummary
) -> [DesktopAPISurfaceRow] {
    summary.surfaces.map { surface in
        let shipped = surface.status == .shipped
        return DesktopAPISurfaceRow(
            id: surface.surfaceID,
            title: surface.title,
            summary: surface.summary,
            statusText: apiSurfaceStatusText(surface.status),
            compatibilityNote: surface.compatibilityNote,
            endpointIDs: surface.endpointIds,
            shipped: shipped
        )
    }
}

private func resolvedAPIReference(
    from summary: Melix_Controlplane_V1_APIOnboardingSummary,
    surfaces: [DesktopAPISurfaceRow]
) -> [DesktopAPIReferenceRow] {
    let surfacesByID = Dictionary(uniqueKeysWithValues: surfaces.map { ($0.id, $0) })
    let surfaceOrder = Dictionary(uniqueKeysWithValues: surfaces.enumerated().map { ($1.id, $0) })

    return summary.endpoints
        .sorted { lhs, rhs in
            let lhsOrder = surfaceOrder[lhs.surfaceID] ?? .max
            let rhsOrder = surfaceOrder[rhs.surfaceID] ?? .max
            if lhsOrder != rhsOrder {
                return lhsOrder < rhsOrder
            }
            if lhs.method != rhs.method {
                return lhs.method < rhs.method
            }
            return lhs.path < rhs.path
        }
        .map { endpoint in
            let surfaceTitle = surfacesByID[endpoint.surfaceID]?.title ?? endpoint.surfaceID
            return DesktopAPIReferenceRow(
                id: endpoint.endpointID,
                surfaceID: endpoint.surfaceID,
                surfaceTitle: surfaceTitle,
                method: endpoint.method,
                path: endpoint.path,
                summary: endpoint.summary,
                streaming: endpoint.streaming
            )
        }
}

private func apiSurfaceStatusText(
    _ status: Melix_Controlplane_V1_APIOnboardingSurfaceStatus
) -> String {
    switch status {
    case .shipped:
        return "Shipped"
    case .compatibilityOnly:
        return "Compatibility Only"
    default:
        return "Unknown"
    }
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
