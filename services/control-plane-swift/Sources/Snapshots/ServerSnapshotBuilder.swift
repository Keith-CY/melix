import MelixControlPlaneProtocol

public struct ServerSnapshotBuilder {
    public init() {}

    public func build(
        models: [Melix_Controlplane_V1_ModelSummary],
        metrics: Melix_Controlplane_V1_MetricsSummary
    ) -> Melix_Controlplane_V1_ServerSnapshot {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = models
        snapshot.queues = emptyQueueSummary()
        snapshot.cache = Melix_Controlplane_V1_CacheSummary()
        snapshot.resources = Melix_Controlplane_V1_ResourceSnapshot()
        snapshot.metrics = metrics
        return snapshot
    }

    private func emptyQueueSummary() -> Melix_Controlplane_V1_QueueSummary {
        var queue = Melix_Controlplane_V1_QueueSummary()
        queue.lanes = [lane(id: "Q0"), lane(id: "Q1"), lane(id: "Q2"), lane(id: "Q3")]
        return queue
    }

    private func lane(id: String) -> Melix_Controlplane_V1_QueueLaneSummary {
        var lane = Melix_Controlplane_V1_QueueLaneSummary()
        lane.laneID = id
        return lane
    }
}
