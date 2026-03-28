import Foundation
import MelixControlPlaneProtocol
import Observation

public actor MenuBarMetricsStore {
    private var values: [String: Double] = [:]

    public init() {}

    public func record(name: String, valueMs: Double) {
        values[name] = valueMs
    }

    public func snapshot() -> [String: Double] {
        values
    }
}

public struct RuntimeModelRow: Equatable, Sendable {
    public let modelID: String
    public let kind: String
    public let state: Melix_Controlplane_V1_ModelState
    public let stateText: String
    public let actionTitle: String
    public let maxContext: UInt32

    public var isLoaded: Bool {
        switch state {
        case .modelWarm, .modelPinned:
            return true
        default:
            return false
        }
    }
}

@MainActor
@Observable
public final class RuntimeViewModel {
    public private(set) var statusTitle = "Melix Starting"
    public private(set) var serverStateText = "Starting"
    public private(set) var models: [RuntimeModelRow] = []
    public private(set) var lastError: String?
    public private(set) var protocolVersion = "melix.controlplane.v1"
    public private(set) var serverVersion = "0.1.0"
    public private(set) var daemonInstanceID = ""
    public private(set) var features: [String] = []

    public var onStateChanged: (@MainActor @Sendable () -> Void)?

    private let client: any ControlPlaneXPCClient
    private let metrics: MenuBarMetricsStore
    private var subscriptionTask: Task<Void, Never>?
    private var lastSeenSeq: UInt64 = 0
    private var latestSnapshot = Melix_Controlplane_V1_ServerSnapshot()
    private var recentEvents: [DesktopLogEntry] = []

    public init(
        client: any ControlPlaneXPCClient,
        metrics: MenuBarMetricsStore = MenuBarMetricsStore()
    ) {
        self.client = client
        self.metrics = metrics
    }

    public var primaryModel: RuntimeModelRow? {
        models.first { $0.modelID == "melix-dev-text" } ?? models.first
    }

    public var desktopFoundationState: DesktopFoundationState {
        DesktopFoundationState.build(
            statusTitle: statusTitle,
            serverStateText: serverStateText,
            snapshot: latestSnapshot,
            protocolVersion: protocolVersion,
            serverVersion: serverVersion,
            daemonInstanceID: daemonInstanceID,
            features: features,
            lastError: lastError,
            recentEvents: recentEvents
        )
    }

    public func start() async {
        let handshakeStartedAt = Date()

        do {
            let response = try await client.handshake()
            protocolVersion = response.protocolVersion
            serverVersion = response.serverVersion
            daemonInstanceID = response.daemonInstanceID
            features = response.features
            await metrics.record(
                name: "menu.handshake_ms",
                valueMs: Date().timeIntervalSince(handshakeStartedAt) * 1_000
            )

            let hydrationStartedAt = Date()
            apply(snapshot: response.snapshot)
            await metrics.record(
                name: "menu.hydration_ms",
                valueMs: Date().timeIntervalSince(hydrationStartedAt) * 1_000
            )

            let stream = await client.subscribe(lastSeenSeq: lastSeenSeq)
            subscriptionTask?.cancel()
            subscriptionTask = Task { [weak self] in
                for await event in stream {
                    await self?.consume(event: event)
                }
            }
        } catch {
            lastError = String(describing: error)
            statusTitle = "Melix Error"
            notifyStateChanged()
        }
    }

    public func refreshDesktopFoundation() async {
        let startedAt = Date()

        do {
            let snapshot = try await client.serverSnapshot()
            apply(snapshot: snapshot)
            await metrics.record(
                name: "menu.foundation_refresh_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
        } catch {
            recordLocalError(String(describing: error))
            notifyStateChanged()
        }
    }

    public func loadModel(modelID: String) async {
        let startedAt = Date()
        do {
            let model = try await client.loadModel(modelID: modelID)
            await metrics.record(
                name: "menu.model_load_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            upsert(model: model)
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func loadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await loadModel(modelID: modelID)
    }

    public func unloadModel(modelID: String) async {
        let startedAt = Date()
        do {
            let model = try await client.unloadModel(modelID: modelID)
            await metrics.record(
                name: "menu.model_unload_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            upsert(model: model)
        } catch {
            recordLocalError(String(describing: error))
        }
        notifyStateChanged()
    }

    public func unloadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }
        await unloadModel(modelID: modelID)
    }

    private func consume(event: Melix_Controlplane_V1_ControlPlaneEvent) async {
        handle(event: event)
    }

    private func handle(event: Melix_Controlplane_V1_ControlPlaneEvent) {
        lastSeenSeq = max(lastSeenSeq, event.seq)
        record(event: event)

        switch event.payload {
        case .serverState(let serverStateChanged):
            latestSnapshot.serverState = serverStateChanged.state
            serverStateText = Self.serverStateText(serverStateChanged.state)
            statusTitle = "Melix \(serverStateText)"
        case .modelState(let stateChanged):
            var model = existingModelSummary(for: stateChanged.modelID)
            model.modelID = stateChanged.modelID
            model.state = stateChanged.state
            upsert(model: model)
        case .sessionState(let sessionStateChanged):
            upsert(session: sessionStateChanged.state)
        case .cacheStats(let cacheStats):
            latestSnapshot.cache = cacheStats.summary
        case .resourcePressure(let resourcePressure):
            latestSnapshot.resources = resourcePressure.resources
        case .log(let logEvent):
            if logEvent.level.lowercased() == "error" {
                lastError = logEvent.message
            }
        default:
            break
        }

        notifyStateChanged()
    }

    private func apply(snapshot: Melix_Controlplane_V1_ServerSnapshot) {
        latestSnapshot = snapshot
        serverStateText = Self.serverStateText(snapshot.serverState)
        statusTitle = "Melix \(serverStateText)"
        models = snapshot.models
            .sorted { $0.modelID < $1.modelID }
            .map(makeRuntimeModelRow)
        notifyStateChanged()
    }

    private func upsert(model: Melix_Controlplane_V1_ModelSummary) {
        let row = makeRuntimeModelRow(model)
        var modelSummary = model
        if modelSummary.features.isEmpty {
            modelSummary.features = ["chat"]
        }
        if let snapshotIndex = latestSnapshot.models.firstIndex(where: { $0.modelID == model.modelID }) {
            latestSnapshot.models[snapshotIndex] = modelSummary
        } else {
            latestSnapshot.models.append(modelSummary)
            latestSnapshot.models.sort { $0.modelID < $1.modelID }
        }
        if let index = models.firstIndex(where: { $0.modelID == model.modelID }) {
            models[index] = row
        } else {
            models.append(row)
            models.sort { $0.modelID < $1.modelID }
        }
    }

    private func upsert(session: Melix_Controlplane_V1_SessionState) {
        var summary = Melix_Controlplane_V1_SessionSummary()
        summary.sessionID = session.sessionID
        summary.activeBranchID = session.activeBranchID
        summary.branchCount = UInt32(session.branches.count)
        summary.latestRequestID = session.latestRequestID
        summary.latestSnapshotID = session.latestSnapshotID

        if let index = latestSnapshot.sessions.firstIndex(where: { $0.sessionID == session.sessionID }) {
            latestSnapshot.sessions[index] = summary
        } else {
            latestSnapshot.sessions.append(summary)
            latestSnapshot.sessions.sort { $0.sessionID < $1.sessionID }
        }
    }

    private func existingModelSummary(for modelID: String) -> Melix_Controlplane_V1_ModelSummary {
        if let model = latestSnapshot.models.first(where: { $0.modelID == modelID }) {
            return model
        }

        if let row = models.first(where: { $0.modelID == modelID }) {
            var model = Melix_Controlplane_V1_ModelSummary()
            model.modelID = row.modelID
            model.kind = row.kind
            model.state = row.state
            model.maxContext = row.maxContext
            model.features = ["chat"]
            return model
        }

        var model = Melix_Controlplane_V1_ModelSummary()
        model.modelID = modelID
        model.kind = "text"
        model.state = .modelDiscovered
        model.maxContext = 8192
        model.features = ["chat"]
        return model
    }

    private func recordLocalError(_ message: String) {
        lastError = message
        recentEvents.insert(
            DesktopLogEntry(kind: "error", message: message, detail: "local", level: "error"),
            at: 0
        )
        trimRecentEvents()
    }

    private func record(event: Melix_Controlplane_V1_ControlPlaneEvent) {
        let entry = DesktopLogEntry(
            kind: event.eventType,
            message: Self.eventMessage(for: event),
            detail: event.source.isEmpty ? "control-plane" : event.source,
            level: Self.eventLevel(for: event)
        )
        recentEvents.insert(entry, at: 0)
        trimRecentEvents()
    }

    private func trimRecentEvents() {
        if recentEvents.count > 40 {
            recentEvents.removeSubrange(40...)
        }
    }

    private func notifyStateChanged() {
        onStateChanged?()
    }

    private static func serverStateText(_ state: Melix_Controlplane_V1_ServerState) -> String {
        switch state {
        case .serverBooting:
            return "Booting"
        case .serverReady:
            return "Ready"
        case .serverDegraded:
            return "Degraded"
        case .serverDraining:
            return "Draining"
        case .serverStopped:
            return "Stopped"
        case .serverFailed:
            return "Failed"
        default:
            return "Unknown"
        }
    }

    private static func modelStateText(_ state: Melix_Controlplane_V1_ModelState) -> String {
        switch state {
        case .modelDiscovered:
            return "Discovered"
        case .modelWarm:
            return "Warm"
        case .modelPinned:
            return "Pinned"
        case .modelUnloaded:
            return "Unloaded"
        case .modelLoading:
            return "Loading"
        case .modelFailed:
            return "Failed"
        default:
            return "Unknown"
        }
    }

    private static func actionTitle(for state: Melix_Controlplane_V1_ModelState) -> String {
        switch state {
        case .modelWarm, .modelPinned:
            return "Unload"
        default:
            return "Load"
        }
    }

    private static func eventLevel(for event: Melix_Controlplane_V1_ControlPlaneEvent) -> String {
        switch event.payload {
        case .log(let logEvent):
            return logEvent.level
        case .resourcePressure:
            return "warning"
        default:
            return "info"
        }
    }

    private static func eventMessage(for event: Melix_Controlplane_V1_ControlPlaneEvent) -> String {
        switch event.payload {
        case .serverState(let serverStateChanged):
            return "Server is now \(serverStateText(serverStateChanged.state))"
        case .modelState(let modelStateChanged):
            return "\(modelStateChanged.modelID) -> \(modelStateText(modelStateChanged.state))"
        case .requestProgress(let progress):
            return "\(progress.requestID) \(String(describing: progress.phase).lowercased())"
        case .sessionState(let sessionStateChanged):
            return "Session \(sessionStateChanged.state.sessionID) updated"
        case .cacheStats:
            return "Cache summary updated"
        case .log(let logEvent):
            return logEvent.message
        case .resourcePressure(let resourcePressure):
            return "Resource pressure in \(resourcePressure.scope)"
        case .heartbeat:
            return "Heartbeat"
        default:
            return event.eventType
        }
    }
}

func makeRuntimeModelRow(_ model: Melix_Controlplane_V1_ModelSummary) -> RuntimeModelRow {
    RuntimeModelRow(
        modelID: model.modelID,
        kind: model.kind,
        state: model.state,
        stateText: runtimeModelStateText(model.state),
        actionTitle: runtimeActionTitle(for: model.state),
        maxContext: model.maxContext
    )
}

private func runtimeModelStateText(_ state: Melix_Controlplane_V1_ModelState) -> String {
    switch state {
    case .modelDiscovered:
        return "Discovered"
    case .modelWarm:
        return "Warm"
    case .modelPinned:
        return "Pinned"
    case .modelUnloaded:
        return "Unloaded"
    case .modelLoading:
        return "Loading"
    case .modelFailed:
        return "Failed"
    default:
        return "Unknown"
    }
}

private func runtimeActionTitle(for state: Melix_Controlplane_V1_ModelState) -> String {
    switch state {
    case .modelWarm, .modelPinned:
        return "Unload"
    default:
        return "Load"
    }
}
