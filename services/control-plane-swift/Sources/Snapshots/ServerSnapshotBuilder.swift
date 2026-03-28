import MelixControlPlaneProtocol

public struct ServerSnapshotBuilder {
    public init() {}

    public func build(
        models: [Melix_Controlplane_V1_ModelSummary],
        metrics: Melix_Controlplane_V1_MetricsSummary,
        queues: Melix_Controlplane_V1_QueueSummary? = nil
    ) -> Melix_Controlplane_V1_ServerSnapshot {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = models
        snapshot.queues = queues ?? emptyQueueSummary()
        snapshot.cache = Melix_Controlplane_V1_CacheSummary()
        snapshot.resources = Melix_Controlplane_V1_ResourceSnapshot()
        snapshot.metrics = metrics
        return snapshot
    }

    private func emptyQueueSummary() -> Melix_Controlplane_V1_QueueSummary {
        var queue = Melix_Controlplane_V1_QueueSummary()
        queue.lanes = [
            lane(id: "text.decode.interactive", laneClass: "interactive-decode"),
            lane(id: "text.prefill.hot", laneClass: "hot-prefill"),
            lane(id: "text.prefill.background", laneClass: "background-prefill"),
        ]
        return queue
    }

    private func lane(id: String, laneClass: String) -> Melix_Controlplane_V1_QueueLaneSummary {
        var lane = Melix_Controlplane_V1_QueueLaneSummary()
        lane.laneID = id
        lane.laneClass = laneClass
        return lane
    }
}
