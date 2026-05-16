import Foundation

public enum RuntimeJobsPayloadDecoder {
    public static func decodeList(_ data: Data) throws -> [RuntimeJobSummaryState] {
        try JSONDecoder().decode([RuntimeJobSummaryState].self, from: data)
    }

    public static func decodeDetail(_ data: Data) throws -> RuntimeJobDetailState {
        try JSONDecoder().decode(RuntimeJobDetailState.self, from: data)
    }

    public static func decodeLogSnapshot(_ data: Data) throws -> RuntimeJobLogSnapshotState {
        try JSONDecoder().decode(RuntimeJobLogSnapshotState.self, from: data)
    }

    public static func decodeArtifactSnapshot(_ data: Data) throws -> RuntimeJobArtifactSnapshotState {
        try JSONDecoder().decode(RuntimeJobArtifactSnapshotState.self, from: data)
    }
}

public struct RuntimeJobSummaryState: Decodable, Equatable, Identifiable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let runKind: String
    public let operation: String
    public let status: String
    public let phase: String
    public let startedAtUnixMS: Int64
    public let updatedAtUnixMS: Int64
    public let durationMS: Int64
    public let modelID: String
    public let taskKind: String
    public let suiteIDs: [String]
    public let datasetID: String
    public let artifactRoot: String
    public let recordPath: String
    public let cancelable: Bool
    public let cancellationRequested: Bool

    public var id: String {
        jobID
    }

    public var isActive: Bool {
        switch normalizedStatus {
        case "active", "in_progress", "pending", "processing", "queued", "running", "started":
            return true
        default:
            return false
        }
    }

    public var isTerminal: Bool {
        switch normalizedStatus {
        case "cancelled", "canceled", "complete", "completed", "done", "error", "failed", "skipped", "success",
             "succeeded":
            return true
        default:
            return false
        }
    }

    private var normalizedStatus: String {
        status.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .replacingOccurrences(of: "-", with: "_")
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = container.decodeFlexibleString(forKey: .schemaVersion)
        jobID = container.decodeFlexibleString(forKey: .jobID)
        runKind = container.decodeFlexibleString(forKey: .runKind)
        operation = container.decodeFlexibleString(forKey: .operation)
        status = container.decodeFlexibleString(forKey: .status)
        phase = container.decodeFlexibleString(forKey: .phase)
        startedAtUnixMS = container.decodeFlexibleInt64(forKey: .startedAtUnixMS)
        updatedAtUnixMS = container.decodeFlexibleInt64(forKey: .updatedAtUnixMS)
        durationMS = container.decodeFlexibleInt64(forKey: .durationMS)
        modelID = container.decodeFlexibleString(forKey: .modelID)
        taskKind = container.decodeFlexibleString(forKey: .taskKind)
        suiteIDs = container.decodeFlexibleStringArray(forKey: .suiteIDs)
        datasetID = container.decodeFlexibleString(forKey: .datasetID)
        artifactRoot = container.decodeFlexibleString(forKey: .artifactRoot)
        recordPath = container.decodeFlexibleString(forKey: .recordPath)
        cancelable = container.decodeFlexibleBool(forKey: .cancelable)
        cancellationRequested = container.decodeFlexibleBool(forKey: .cancellationRequested)
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case runKind = "run_kind"
        case operation
        case status
        case phase
        case startedAtUnixMS = "started_at_unix_ms"
        case updatedAtUnixMS = "updated_at_unix_ms"
        case durationMS = "duration_ms"
        case modelID = "model_id"
        case taskKind = "task_kind"
        case suiteIDs = "suite_ids"
        case datasetID = "dataset_id"
        case artifactRoot = "artifact_root"
        case recordPath = "record_path"
        case cancelable
        case cancellationRequested = "cancellation_requested"
    }
}

public struct RuntimeJobDetailState: Decodable, Equatable, Sendable {
    public let summary: RuntimeJobSummaryState
    public let commandDisplay: String
    public let timestamps: RuntimeJobTimestampsState
    public let progress: RuntimeJobProgressState?
    public let throughputMetrics: [RuntimeJobMetricState]
    public let error: RuntimeJobErrorState?
    public let logs: RuntimeJobLogReferenceState
    public let artifacts: [RuntimeJobArtifactState]
    public let cancellation: RuntimeJobCancellationState

    public init(from decoder: Decoder) throws {
        summary = try RuntimeJobSummaryState(from: decoder)
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let command = try? container.decode(RuntimeJobCommandState.self, forKey: .command)
        commandDisplay = command?.display ?? ""
        timestamps = (try? container.decode(RuntimeJobTimestampsState.self, forKey: .timestamps))
            ?? RuntimeJobTimestampsState(
                startedAtUnixMS: summary.startedAtUnixMS,
                updatedAtUnixMS: summary.updatedAtUnixMS,
                endedAtUnixMS: 0,
                durationMS: summary.durationMS
            )
        progress = try? container.decodeIfPresent(RuntimeJobProgressState.self, forKey: .progress)
        throughputMetrics = (try? container.decode([RuntimeJobMetricState].self, forKey: .throughputMetrics)) ?? []
        error = try? container.decodeIfPresent(RuntimeJobErrorState.self, forKey: .error)
        logs = (try? container.decode(RuntimeJobLogReferenceState.self, forKey: .logs)) ?? RuntimeJobLogReferenceState()
        artifacts = (try? container.decode([RuntimeJobArtifactState].self, forKey: .artifacts)) ?? []
        cancellation = (try? container.decode(RuntimeJobCancellationState.self, forKey: .cancellation))
            ?? RuntimeJobCancellationState(cancelable: summary.cancelable, requested: summary.cancellationRequested)
    }

    private enum CodingKeys: String, CodingKey {
        case command
        case timestamps
        case progress
        case throughputMetrics = "throughput_metrics"
        case error
        case logs
        case artifacts
        case cancellation
    }
}

public struct RuntimeJobTimestampsState: Decodable, Equatable, Sendable {
    public let startedAtUnixMS: Int64
    public let updatedAtUnixMS: Int64
    public let endedAtUnixMS: Int64
    public let durationMS: Int64

    public init(
        startedAtUnixMS: Int64 = 0,
        updatedAtUnixMS: Int64 = 0,
        endedAtUnixMS: Int64 = 0,
        durationMS: Int64 = 0
    ) {
        self.startedAtUnixMS = startedAtUnixMS
        self.updatedAtUnixMS = updatedAtUnixMS
        self.endedAtUnixMS = endedAtUnixMS
        self.durationMS = durationMS
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        startedAtUnixMS = container.decodeFlexibleInt64(forKey: .startedAtUnixMS)
        updatedAtUnixMS = container.decodeFlexibleInt64(forKey: .updatedAtUnixMS)
        endedAtUnixMS = container.decodeFlexibleInt64(forKey: .endedAtUnixMS)
        durationMS = container.decodeFlexibleInt64(forKey: .durationMS)
    }

    private enum CodingKeys: String, CodingKey {
        case startedAtUnixMS = "started_at_unix_ms"
        case updatedAtUnixMS = "updated_at_unix_ms"
        case endedAtUnixMS = "ended_at_unix_ms"
        case durationMS = "duration_ms"
    }
}

public struct RuntimeJobProgressState: Decodable, Equatable, Sendable {
    public let phase: String
    public let status: String
    public let durationMS: Int64
    public let pct: Double?

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        phase = container.decodeFlexibleString(forKey: .phase)
        status = container.decodeFlexibleString(forKey: .status)
        durationMS = container.decodeFlexibleInt64(forKey: .durationMS)
        pct = container.decodeFlexibleOptionalDouble(forKey: .pct)
    }

    private enum CodingKeys: String, CodingKey {
        case phase
        case status
        case durationMS = "duration_ms"
        case pct
    }
}

public struct RuntimeJobMetricState: Decodable, Equatable, Sendable {
    public let name: String
    public let value: Double
    public let unit: String

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = container.decodeFlexibleString(forKey: .name)
        value = container.decodeFlexibleDouble(forKey: .value)
        unit = container.decodeFlexibleString(forKey: .unit)
    }

    private enum CodingKeys: String, CodingKey {
        case name
        case value
        case unit
    }
}

public struct RuntimeJobErrorState: Decodable, Equatable, Sendable {
    public let code: String
    public let message: String

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        code = container.decodeFlexibleString(forKey: .code)
        message = container.decodeFlexibleString(forKey: .message)
    }

    private enum CodingKeys: String, CodingKey {
        case code
        case message
    }
}

public struct RuntimeJobLogReferenceState: Decodable, Equatable, Sendable {
    public let schemaVersion: String
    public let available: Bool
    public let path: String
    public let command: String

    public init(schemaVersion: String = "", available: Bool = false, path: String = "", command: String = "") {
        self.schemaVersion = schemaVersion
        self.available = available
        self.path = path
        self.command = command
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = container.decodeFlexibleString(forKey: .schemaVersion)
        available = container.decodeFlexibleBool(forKey: .available)
        path = container.decodeFlexibleString(forKey: .path)
        command = container.decodeFlexibleString(forKey: .command)
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case available
        case path
        case command
    }
}

public struct RuntimeJobArtifactState: Decodable, Equatable, Identifiable, Sendable {
    public let kind: String
    public let path: String
    public let relativePath: String
    public let exists: Bool

    public var id: String {
        "\(kind)|\(path)"
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        kind = container.decodeFlexibleString(forKey: .kind)
        path = container.decodeFlexibleString(forKey: .path)
        relativePath = container.decodeFlexibleString(forKey: .relativePath)
        exists = container.decodeFlexibleBool(forKey: .exists)
    }

    private enum CodingKeys: String, CodingKey {
        case kind
        case path
        case relativePath = "relative_path"
        case exists
    }
}

public struct RuntimeJobLogSnapshotState: Decodable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let sourcePath: String
    public let logPath: String
    public let followRequested: Bool
    public let activeFollowSupported: Bool
    public let content: String
    public let redactionSchemaVersion: String
    public let redactedFieldCount: Int

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = container.decodeFlexibleString(forKey: .schemaVersion)
        let runID = container.decodeFlexibleString(forKey: .runID)
        let decodedJobID = container.decodeFlexibleString(forKey: .jobID)
        jobID = runID.isEmpty ? decodedJobID : runID
        sourcePath = container.decodeFlexibleString(forKey: .sourcePath)
        logPath = container.decodeFlexibleString(forKey: .logPath)
        followRequested = container.decodeFlexibleBool(forKey: .followRequested)
        activeFollowSupported = container.decodeFlexibleBool(forKey: .activeFollowSupported)
        content = container.decodeFlexibleString(forKey: .content)
        redactionSchemaVersion = container.decodeFlexibleString(forKey: .redactionSchemaVersion)
        redactedFieldCount = Int(container.decodeFlexibleInt64(forKey: .redactedFieldCount))
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case runID = "run_id"
        case jobID = "job_id"
        case sourcePath = "source_path"
        case logPath = "log_path"
        case followRequested = "follow_requested"
        case activeFollowSupported = "active_follow_supported"
        case content
        case redactionSchemaVersion = "redaction_schema_version"
        case redactedFieldCount = "redacted_field_count"
    }
}

public struct RuntimeJobArtifactSnapshotState: Decodable, Equatable, Sendable {
    public let schemaVersion: String
    public let jobID: String
    public let artifactCount: Int
    public let artifacts: [RuntimeJobArtifactState]

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = container.decodeFlexibleString(forKey: .schemaVersion)
        jobID = container.decodeFlexibleString(forKey: .jobID)
        artifactCount = Int(container.decodeFlexibleInt64(forKey: .artifactCount))
        artifacts = (try? container.decode([RuntimeJobArtifactState].self, forKey: .artifacts)) ?? []
    }

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case artifactCount = "artifact_count"
        case artifacts
    }
}

public struct RuntimeJobCancellationState: Decodable, Equatable, Sendable {
    public let cancelable: Bool
    public let requested: Bool
    public let requestPath: String

    public init(cancelable: Bool = false, requested: Bool = false, requestPath: String = "") {
        self.cancelable = cancelable
        self.requested = requested
        self.requestPath = requestPath
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        cancelable = container.decodeFlexibleBool(forKey: .cancelable)
        requested = container.decodeFlexibleBool(forKey: .requested)
        requestPath = container.decodeFlexibleString(forKey: .requestPath)
    }

    private enum CodingKeys: String, CodingKey {
        case cancelable
        case requested
        case requestPath = "request_path"
    }
}

private struct RuntimeJobCommandState: Decodable {
    let display: String

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        display = container.decodeFlexibleString(forKey: .display)
    }

    private enum CodingKeys: String, CodingKey {
        case display
    }
}

private extension KeyedDecodingContainer {
    func decodeFlexibleString(forKey key: Key) -> String {
        if let value = try? decode(String.self, forKey: key) {
            return value
        }
        if let value = try? decode(Int64.self, forKey: key) {
            return String(value)
        }
        if let value = try? decode(Int.self, forKey: key) {
            return String(value)
        }
        if let value = try? decode(Double.self, forKey: key) {
            return String(value)
        }
        if let value = try? decode(Bool.self, forKey: key) {
            return String(value)
        }
        return ""
    }

    func decodeFlexibleStringArray(forKey key: Key) -> [String] {
        if let values = try? decode([String].self, forKey: key) {
            return values
        }
        if let values = try? decode([Int].self, forKey: key) {
            return values.map(String.init)
        }
        if let value = try? decode(String.self, forKey: key) {
            return value.isEmpty ? [] : [value]
        }
        return []
    }

    func decodeFlexibleInt64(forKey key: Key) -> Int64 {
        if let value = try? decode(Int64.self, forKey: key) {
            return value
        }
        if let value = try? decode(Int.self, forKey: key) {
            return Int64(value)
        }
        if let value = try? decode(Double.self, forKey: key) {
            return Int64(value)
        }
        if let value = try? decode(String.self, forKey: key),
           let parsed = Int64(value.trimmingCharacters(in: .whitespacesAndNewlines)) {
            return parsed
        }
        return 0
    }

    func decodeFlexibleDouble(forKey key: Key) -> Double {
        decodeFlexibleOptionalDouble(forKey: key) ?? 0
    }

    func decodeFlexibleOptionalDouble(forKey key: Key) -> Double? {
        if let value = try? decode(Double.self, forKey: key) {
            return value
        }
        if let value = try? decode(Int.self, forKey: key) {
            return Double(value)
        }
        if let value = try? decode(Int64.self, forKey: key) {
            return Double(value)
        }
        if let value = try? decode(String.self, forKey: key),
           let parsed = Double(value.trimmingCharacters(in: .whitespacesAndNewlines)) {
            return parsed
        }
        return nil
    }

    func decodeFlexibleBool(forKey key: Key) -> Bool {
        if let value = try? decode(Bool.self, forKey: key) {
            return value
        }
        if let value = try? decode(Int.self, forKey: key) {
            return value != 0
        }
        if let value = try? decode(String.self, forKey: key) {
            switch value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
            case "1", "true", "yes":
                return true
            default:
                return false
            }
        }
        return false
    }
}
