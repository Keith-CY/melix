import MelixControlPlaneProtocol

public actor MetricsStore {
    public init() {}

    public func snapshot() -> Melix_Controlplane_V1_MetricsSummary {
        var summary = Melix_Controlplane_V1_MetricsSummary()
        summary.values = [
            "requests.inflight": 0,
            "workers.connected": 0,
        ]
        return summary
    }
}
