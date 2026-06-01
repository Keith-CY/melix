import Foundation
import MelixControlPlaneProtocol

public actor MetricsStore {
    private var values: [String: Double]
    private let exportPath: String?
    private let exportMinimumInterval: TimeInterval
    private var lastExportedAt: Date?
    private var pendingExportTask: Task<Void, Never>?
    private var exportGeneration: UInt64

    public init(
        exportPath: String? = nil,
        exportMinimumInterval: TimeInterval = 0.25
    ) {
        self.exportPath = exportPath
        self.exportMinimumInterval = max(0, exportMinimumInterval)
        self.lastExportedAt = nil
        self.pendingExportTask = nil
        self.exportGeneration = 0
        self.values = [
            "requests.inflight": 0,
            "workers.connected": 0,
            "http.translation_ms": 0,
            "http.shaping_ms": 0,
            "http.ttfd_ms": 0,
            "http.stream_first_event_ms": 0,
            "http.abort_ms": 0,
            "http.stream_event_count": 0,
            "http.worker_event_handle_total_us": 0,
            "http.worker_event_handle_call_count": 0,
            "http.worker_event_handle_avg_us": 0,
            "http.sse_write_total_us": 0,
            "http.sse_write_call_count": 0,
            "http.sse_write_avg_us": 0,
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
        scheduleExportIfNeeded()
    }

    public func increment(_ key: String, by amount: Double = 1) {
        values[key, default: 0] += amount
        scheduleExportIfNeeded()
    }

    public func value(forKey key: String) -> Double {
        values[key, default: 0]
    }

    public func decrement(_ key: String, by amount: Double = 1) {
        values[key, default: 0] = max(0, values[key, default: 0] - amount)
        scheduleExportIfNeeded()
    }

    public func addMicrosecondTiming(prefix: String, totalMicros: Double, callCount: Double) {
        let normalizedTotal = max(0, totalMicros)
        let normalizedCount = max(0, callCount)
        let totalKey = "\(prefix)_total_us"
        let countKey = "\(prefix)_call_count"
        let avgKey = "\(prefix)_avg_us"

        values[totalKey, default: 0] += normalizedTotal
        values[countKey, default: 0] += normalizedCount
        let cumulativeCount = values[countKey, default: 0]
        values[avgKey] = cumulativeCount > 0
            ? max(1, values[totalKey, default: 0] / cumulativeCount)
            : 0
        scheduleExportIfNeeded()
    }

    public func flushExport() {
        guard let exportPath, !exportPath.isEmpty else {
            return
        }
        pendingExportTask?.cancel()
        pendingExportTask = nil
        exportGeneration += 1
        writeExport(values: values, exportPath: exportPath)
    }

    private func scheduleExportIfNeeded() {
        guard let exportPath, !exportPath.isEmpty else {
            return
        }

        let now = Date()
        exportGeneration += 1
        let generation = exportGeneration
        let snapshot = values
        let elapsed = lastExportedAt.map { now.timeIntervalSince($0) } ?? exportMinimumInterval
        guard elapsed < exportMinimumInterval else {
            pendingExportTask?.cancel()
            pendingExportTask = nil
            writeExport(values: snapshot, exportPath: exportPath)
            return
        }

        guard pendingExportTask == nil else {
            return
        }

        let delaySeconds = exportMinimumInterval - elapsed
        let delayNanoseconds = UInt64(max(0, delaySeconds) * 1_000_000_000)
        pendingExportTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: delayNanoseconds)
            guard !Task.isCancelled else {
                return
            }
            await self?.flushScheduledExport(generation: generation)
        }
    }

    private func flushScheduledExport(generation: UInt64) {
        guard let exportPath, !exportPath.isEmpty else {
            pendingExportTask = nil
            return
        }
        pendingExportTask = nil
        guard generation <= exportGeneration else {
            writeExport(values: values, exportPath: exportPath)
            return
        }
        writeExport(values: values, exportPath: exportPath)
    }

    private func writeExport(values: [String: Double], exportPath: String) {
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
        lastExportedAt = Date()
    }
}
