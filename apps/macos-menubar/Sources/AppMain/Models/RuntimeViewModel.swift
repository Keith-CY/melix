import Foundation
import MelixControlPlaneProtocol

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
public final class RuntimeViewModel {
    public private(set) var statusTitle = "Melix Starting"
    public private(set) var serverStateText = "Starting"
    public private(set) var models: [RuntimeModelRow] = []
    public private(set) var lastError: String?

    public var onStateChanged: (@MainActor @Sendable () -> Void)?

    private let client: any ControlPlaneXPCClient
    private let metrics: MenuBarMetricsStore
    private var subscriptionTask: Task<Void, Never>?
    private var lastSeenSeq: UInt64 = 0

    public init(
        client: any ControlPlaneXPCClient,
        metrics: MenuBarMetricsStore = MenuBarMetricsStore()
    ) {
        self.client = client
        self.metrics = metrics
    }

    deinit {
        subscriptionTask?.cancel()
    }

    public var primaryModel: RuntimeModelRow? {
        models.first { $0.modelID == "melix-dev-text" } ?? models.first
    }

    public func start() async {
        let handshakeStartedAt = Date()

        do {
            let response = try await client.handshake()
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

    public func loadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }

        let startedAt = Date()
        do {
            let model = try await client.loadModel(modelID: modelID)
            await metrics.record(
                name: "menu.model_load_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            upsert(model: model)
        } catch {
            lastError = String(describing: error)
        }
        notifyStateChanged()
    }

    public func unloadPrimaryModel() async {
        guard let modelID = primaryModel?.modelID else {
            return
        }

        let startedAt = Date()
        do {
            let model = try await client.unloadModel(modelID: modelID)
            await metrics.record(
                name: "menu.model_unload_ms",
                valueMs: Date().timeIntervalSince(startedAt) * 1_000
            )
            upsert(model: model)
        } catch {
            lastError = String(describing: error)
        }
        notifyStateChanged()
    }

    private func consume(event: Melix_Controlplane_V1_ControlPlaneEvent) async {
        handle(event: event)
    }

    private func handle(event: Melix_Controlplane_V1_ControlPlaneEvent) {
        lastSeenSeq = max(lastSeenSeq, event.seq)

        switch event.payload {
        case .modelState(let stateChanged):
            var model = existingModelSummary(for: stateChanged.modelID)
            model.modelID = stateChanged.modelID
            model.state = stateChanged.state
            upsert(model: model)
        default:
            break
        }

        notifyStateChanged()
    }

    private func apply(snapshot: Melix_Controlplane_V1_ServerSnapshot) {
        serverStateText = Self.serverStateText(snapshot.serverState)
        statusTitle = "Melix \(serverStateText)"
        models = snapshot.models
            .sorted { $0.modelID < $1.modelID }
            .map(Self.makeModelRow)
        notifyStateChanged()
    }

    private func upsert(model: Melix_Controlplane_V1_ModelSummary) {
        let row = Self.makeModelRow(model)
        if let index = models.firstIndex(where: { $0.modelID == model.modelID }) {
            models[index] = row
        } else {
            models.append(row)
            models.sort { $0.modelID < $1.modelID }
        }
    }

    private func existingModelSummary(for modelID: String) -> Melix_Controlplane_V1_ModelSummary {
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

    private func notifyStateChanged() {
        onStateChanged?()
    }

    private static func makeModelRow(_ model: Melix_Controlplane_V1_ModelSummary) -> RuntimeModelRow {
        RuntimeModelRow(
            modelID: model.modelID,
            kind: model.kind,
            state: model.state,
            stateText: modelStateText(model.state),
            actionTitle: actionTitle(for: model.state),
            maxContext: model.maxContext
        )
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
}
