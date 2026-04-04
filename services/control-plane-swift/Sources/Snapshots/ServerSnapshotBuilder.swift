import MelixControlPlaneProtocol

public struct ServerSnapshotBuilder {
    public init() {}

    public func build(
        models: [Melix_Controlplane_V1_ModelSummary],
        metrics: Melix_Controlplane_V1_MetricsSummary,
        queues: Melix_Controlplane_V1_QueueSummary? = nil,
        cache: Melix_Controlplane_V1_CacheSummary? = nil,
        sessions: [Melix_Controlplane_V1_SessionSummary] = [],
        runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState] = [],
        imageJobs: [Melix_Controlplane_V1_ImageJobSummary] = [],
        mcpTools: Melix_Controlplane_V1_MCPToolCatalogSummary? = nil,
        gatewayAccess: Melix_Controlplane_V1_GatewayAccessSummary? = nil
    ) -> Melix_Controlplane_V1_ServerSnapshot {
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = models
        snapshot.queues = queues ?? emptyQueueSummary()
        snapshot.cache = cache ?? CacheMetadataStore.emptySummary()
        snapshot.resources = Melix_Controlplane_V1_ResourceSnapshot()
        snapshot.metrics = metrics
        snapshot.sessions = sessions
        snapshot.runtimeSessions = runtimeSessions
        snapshot.imageJobs = imageJobs
        if let mcpTools {
            snapshot.mcpTools = mcpTools
        }
        if let gatewayAccess {
            // Gateway access is projected from the runtime store, never from raw secret material.
            snapshot.gatewayAccess = gatewayAccess
        }
        return snapshot
    }

    private func emptyQueueSummary() -> Melix_Controlplane_V1_QueueSummary {
        var queue = Melix_Controlplane_V1_QueueSummary()
        queue.lanes = [
            lane(id: "text.decode.interactive", laneClass: "interactive-decode"),
            lane(id: "text.prefill.hot", laneClass: "hot-prefill"),
            lane(id: "text.prefill.background", laneClass: "background-prefill"),
            lane(id: "multimodal.vision.background", laneClass: "background-vision"),
            lane(id: "multimodal.audio.transcription.background", laneClass: "background-audio-transcription"),
            lane(id: "multimodal.audio.speech.background", laneClass: "background-audio-speech"),
            lane(id: "image.generate.background", laneClass: "background-image-generate"),
            lane(id: "image.edit.background", laneClass: "background-image-edit"),
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
