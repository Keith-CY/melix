import MelixControlPlaneProtocol

public actor MetricsStore {
    private var values: [String: Double]

    public init() {
        self.values = [
            "requests.inflight": 0,
            "workers.connected": 0,
            "http.translation_ms": 0,
            "http.ttfd_ms": 0,
            "http.abort_ms": 0,
            "http.stream_event_count": 0,
        ]
    }

    public func snapshot() -> Melix_Controlplane_V1_MetricsSummary {
        var summary = Melix_Controlplane_V1_MetricsSummary()
        summary.values = values
        return summary
    }

    public func set(_ value: Double, forKey key: String) {
        values[key] = value
    }

    public func increment(_ key: String, by amount: Double = 1) {
        values[key, default: 0] += amount
    }

    public func decrement(_ key: String, by amount: Double = 1) {
        values[key, default: 0] = max(0, values[key, default: 0] - amount)
    }
}
