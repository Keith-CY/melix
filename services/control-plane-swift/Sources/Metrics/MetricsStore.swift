import Foundation
import MelixControlPlaneProtocol

public actor MetricsStore {
    private var values: [String: Double]
    private let exportPath: String?

    public init(exportPath: String? = nil) {
        self.exportPath = exportPath
        self.values = [
            "requests.inflight": 0,
            "workers.connected": 0,
            "http.translation_ms": 0,
            "http.shaping_ms": 0,
            "http.ttfd_ms": 0,
            "http.stream_first_event_ms": 0,
            "http.abort_ms": 0,
            "http.stream_event_count": 0,
            "http.reasoning_delta_count": 0,
            "http.tool_delta_count": 0,
            "http.preset_shaped_count": 0,
            "http.workflow_shaped_count": 0,
        ]
    }

    public func snapshot() -> Melix_Controlplane_V1_MetricsSummary {
        var summary = Melix_Controlplane_V1_MetricsSummary()
        summary.values = values
        return summary
    }

    public func set(_ value: Double, forKey key: String) {
        values[key] = value
        writeExportIfNeeded()
    }

    public func increment(_ key: String, by amount: Double = 1) {
        values[key, default: 0] += amount
        writeExportIfNeeded()
    }

    public func value(forKey key: String) -> Double {
        values[key, default: 0]
    }

    public func decrement(_ key: String, by amount: Double = 1) {
        values[key, default: 0] = max(0, values[key, default: 0] - amount)
        writeExportIfNeeded()
    }

    private func writeExportIfNeeded() {
        guard let exportPath, !exportPath.isEmpty else {
            return
        }

        let payload: [String: Any] = [
            "updated_at_unix_ms": Int(Date().timeIntervalSince1970 * 1000),
            "values": values,
        ]

        guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]) else {
            return
        }

        let url = URL(fileURLWithPath: exportPath)
        try? FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try? data.write(to: url, options: [.atomic])
    }
}
