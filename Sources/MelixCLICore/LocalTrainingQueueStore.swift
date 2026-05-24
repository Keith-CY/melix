import Foundation

public enum LocalTrainingQueueStatus: String, Codable, CaseIterable, Sendable {
    case queued
    case running
    case cancelRequested = "cancel_requested"
    case canceled
    case failed
    case succeeded

    public var isTerminal: Bool {
        switch self {
        case .canceled, .failed, .succeeded:
            return true
        case .queued, .running, .cancelRequested:
            return false
        }
    }

    public var isActive: Bool {
        !isTerminal
    }
}

public struct LocalTrainingQueueOperatorError: Codable, Equatable, Sendable {
    public var code: String
    public var message: String
    public var retriable: Bool

    public init(code: String, message: String, retriable: Bool = false) {
        self.code = code
        self.message = message
        self.retriable = retriable
    }
}

public struct LocalTrainingQueueJob: Codable, Equatable, Identifiable, Sendable {
    public static let schemaVersion = "melix.local_training_queue_job.v1"

    public var schemaVersion: String
    public var jobID: String
    public var projectID: String
    public var workspaceManifestPath: String
    public var modelID: String
    public var datasetID: String
    public var datasetVersionID: String
    public var adapterName: String
    public var trainingMode: String
    public var resourceClass: String
    public var status: LocalTrainingQueueStatus
    public var createdAtUnixMS: Int64
    public var updatedAtUnixMS: Int64
    public var preflightReceiptPath: String
    public var runDirectory: String
    public var recoveryPolicy: String
    public var cancellationRequestPath: String
    public var operatorErrors: [LocalTrainingQueueOperatorError]

    public var id: String {
        jobID
    }

    public init(
        schemaVersion: String = Self.schemaVersion,
        jobID: String,
        projectID: String = "",
        workspaceManifestPath: String = "",
        modelID: String,
        datasetID: String = "",
        datasetVersionID: String = "",
        adapterName: String,
        trainingMode: String = "",
        resourceClass: String = "exclusive_local_training",
        status: LocalTrainingQueueStatus = .queued,
        createdAtUnixMS: Int64,
        updatedAtUnixMS: Int64,
        preflightReceiptPath: String = "",
        runDirectory: String,
        recoveryPolicy: String = "manual_resume_or_cancel",
        cancellationRequestPath: String = "",
        operatorErrors: [LocalTrainingQueueOperatorError] = []
    ) {
        self.schemaVersion = schemaVersion
        self.jobID = jobID
        self.projectID = projectID
        self.workspaceManifestPath = workspaceManifestPath
        self.modelID = modelID
        self.datasetID = datasetID
        self.datasetVersionID = datasetVersionID
        self.adapterName = adapterName
        self.trainingMode = trainingMode
        self.resourceClass = resourceClass
        self.status = status
        self.createdAtUnixMS = createdAtUnixMS
        self.updatedAtUnixMS = updatedAtUnixMS
        self.preflightReceiptPath = preflightReceiptPath
        self.runDirectory = runDirectory
        self.recoveryPolicy = recoveryPolicy
        self.cancellationRequestPath = cancellationRequestPath
        self.operatorErrors = operatorErrors
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case jobID = "job_id"
        case projectID = "project_id"
        case workspaceManifestPath = "workspace_manifest_path"
        case modelID = "model_id"
        case datasetID = "dataset_id"
        case datasetVersionID = "dataset_version_id"
        case adapterName = "adapter_name"
        case trainingMode = "training_mode"
        case resourceClass = "resource_class"
        case status
        case createdAtUnixMS = "created_at_unix_ms"
        case updatedAtUnixMS = "updated_at_unix_ms"
        case preflightReceiptPath = "preflight_receipt_path"
        case runDirectory = "run_directory"
        case recoveryPolicy = "recovery_policy"
        case cancellationRequestPath = "cancellation_request_path"
        case operatorErrors = "operator_errors"
    }

    public init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? Self.schemaVersion
        guard schemaVersion == Self.schemaVersion else {
            throw MelixCLIError.requestFailed(
                code: "training_queue_restore_failed",
                message: "Unsupported local training queue job schema: \(schemaVersion)."
            )
        }
        self.init(
            schemaVersion: schemaVersion,
            jobID: try container.decode(String.self, forKey: .jobID),
            projectID: try container.decodeIfPresent(String.self, forKey: .projectID) ?? "",
            workspaceManifestPath: try container.decodeIfPresent(String.self, forKey: .workspaceManifestPath) ?? "",
            modelID: try container.decodeIfPresent(String.self, forKey: .modelID) ?? "",
            datasetID: try container.decodeIfPresent(String.self, forKey: .datasetID) ?? "",
            datasetVersionID: try container.decodeIfPresent(String.self, forKey: .datasetVersionID) ?? "",
            adapterName: try container.decodeIfPresent(String.self, forKey: .adapterName) ?? "",
            trainingMode: try container.decodeIfPresent(String.self, forKey: .trainingMode) ?? "",
            resourceClass: try container.decodeIfPresent(String.self, forKey: .resourceClass) ?? "exclusive_local_training",
            status: try container.decodeIfPresent(LocalTrainingQueueStatus.self, forKey: .status) ?? .queued,
            createdAtUnixMS: try container.decodeFlexibleInt64IfPresent(forKey: .createdAtUnixMS) ?? 0,
            updatedAtUnixMS: try container.decodeFlexibleInt64IfPresent(forKey: .updatedAtUnixMS) ?? 0,
            preflightReceiptPath: try container.decodeIfPresent(String.self, forKey: .preflightReceiptPath) ?? "",
            runDirectory: try container.decodeIfPresent(String.self, forKey: .runDirectory) ?? "",
            recoveryPolicy: try container.decodeIfPresent(String.self, forKey: .recoveryPolicy) ?? "manual_resume_or_cancel",
            cancellationRequestPath: try container.decodeIfPresent(String.self, forKey: .cancellationRequestPath) ?? "",
            operatorErrors: try container.decodeIfPresent([LocalTrainingQueueOperatorError].self, forKey: .operatorErrors) ?? []
        )
    }
}

public struct LocalTrainingQueueAdmissionRequest: Sendable {
    public var modelID: String
    public var datasetURI: String
    public var adapterName: String
    public var trainingMode: String
    public var resourceClass: String
    public var runDirectory: String
    public var parameters: [String: String]

    public init(
        modelID: String,
        datasetURI: String,
        adapterName: String,
        trainingMode: String = "",
        resourceClass: String = "exclusive_local_training",
        runDirectory: String = "",
        parameters: [String: String] = [:]
    ) {
        self.modelID = modelID
        self.datasetURI = datasetURI
        self.adapterName = adapterName
        self.trainingMode = trainingMode
        self.resourceClass = resourceClass
        self.runDirectory = runDirectory
        self.parameters = parameters
    }
}

public final class LocalTrainingQueueStore: @unchecked Sendable {
    public static let schemaVersion = "melix.local_training_queue.v1"

    private let melixHome: MelixHome
    private let fileManager: FileManager
    private let lock = NSLock()

    public init(melixHome: MelixHome, fileManager: FileManager = .default) {
        self.melixHome = melixHome
        self.fileManager = fileManager
    }

    public func list() throws -> [LocalTrainingQueueJob] {
        try withLock {
            try loadDocumentUnlocked().jobs.sorted(by: jobSort)
        }
    }

    public func get(jobID: String) throws -> LocalTrainingQueueJob? {
        let normalizedJobID = jobID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard normalizedJobID.isEmpty == false else {
            throw MelixCLIError.missingRequired("job_id must not be empty.")
        }
        return try withLock {
            try loadDocumentUnlocked().jobs.first { $0.jobID == normalizedJobID }
        }
    }

    @discardableResult
    public func admit(_ request: LocalTrainingQueueAdmissionRequest) throws -> LocalTrainingQueueJob {
        try withLock {
            var document = try loadDocumentUnlocked()
            if let active = document.jobs.first(where: { $0.status.isActive && isExclusive($0.resourceClass) }) {
                document.metrics.admissionRefusalCount += 1
                document.updatedAtUnixMS = currentUnixMilliseconds()
                try saveDocumentUnlocked(document)
                throw MelixCLIError.requestFailed(
                    code: "training_queue_busy",
                    message: "Local training queue is busy with \(active.jobID)."
                )
            }

            let now = currentUnixMilliseconds()
            let jobID = nextJobID(document.jobs)
            let runDirectory = normalizedRunDirectory(
                request.runDirectory,
                jobID: jobID
            )
            let job = LocalTrainingQueueJob(
                jobID: jobID,
                projectID: normalizedParameter("project_id", request.parameters),
                workspaceManifestPath: normalizedParameter("workspace_manifest_path", request.parameters),
                modelID: request.modelID,
                datasetID: normalizedDatasetID(request),
                datasetVersionID: normalizedParameter("dataset_version_id", request.parameters),
                adapterName: request.adapterName,
                trainingMode: request.trainingMode,
                resourceClass: request.resourceClass.isEmpty ? "exclusive_local_training" : request.resourceClass,
                status: .queued,
                createdAtUnixMS: now,
                updatedAtUnixMS: now,
                preflightReceiptPath: normalizedParameter("preflight_receipt_path", request.parameters),
                runDirectory: runDirectory,
                recoveryPolicy: normalizedParameter("recovery_policy", request.parameters, fallback: "manual_resume_or_cancel"),
                cancellationRequestPath: URL(fileURLWithPath: runDirectory)
                    .appendingPathComponent("cancel-request.json")
                    .path
            )
            document.jobs.append(job)
            document.updatedAtUnixMS = now
            document.metrics.queueAdmissionLatencyMS = 0
            recomputeMetrics(&document)
            try saveDocumentUnlocked(document)
            return job
        }
    }

    @discardableResult
    public func markRunning(jobID: String) throws -> LocalTrainingQueueJob {
        try update(jobID: jobID, status: .running)
    }

    @discardableResult
    public func markSucceeded(jobID: String) throws -> LocalTrainingQueueJob {
        try update(jobID: jobID, status: .succeeded)
    }

    @discardableResult
    public func markFailed(
        jobID: String,
        code: String,
        message: String,
        retriable: Bool = false
    ) throws -> LocalTrainingQueueJob {
        try update(
            jobID: jobID,
            status: .failed,
            operatorError: LocalTrainingQueueOperatorError(code: code, message: message, retriable: retriable)
        )
    }

    @discardableResult
    public func requestCancel(jobID: String) throws -> LocalTrainingQueueJob {
        try withLock {
            var document = try loadDocumentUnlocked()
            guard let index = document.jobs.firstIndex(where: { $0.jobID == jobID }) else {
                throw MelixCLIError.requestFailed(
                    code: "training_queue_job_not_found",
                    message: "No local training queue job was found for \(jobID)."
                )
            }
            let current = document.jobs[index]
            guard current.status.isActive else {
                throw MelixCLIError.requestFailed(
                    code: "training_queue_state_invalid",
                    message: "Local training queue job \(jobID) is already terminal."
                )
            }
            let now = currentUnixMilliseconds()
            var updated = current
            updated.status = .cancelRequested
            updated.updatedAtUnixMS = now
            document.jobs[index] = updated
            document.updatedAtUnixMS = now
            document.metrics.cancellationLatencyMS = 0
            recomputeMetrics(&document)
            try writeCancellationRequest(updated)
            try saveDocumentUnlocked(document)
            return updated
        }
    }

    public func snapshot() throws -> [String: Any] {
        let document = try withLock {
            try loadDocumentUnlocked()
        }
        return try Self.jsonObject(from: document)
    }

    private func update(
        jobID: String,
        status: LocalTrainingQueueStatus,
        operatorError: LocalTrainingQueueOperatorError? = nil
    ) throws -> LocalTrainingQueueJob {
        try withLock {
            var document = try loadDocumentUnlocked()
            guard let index = document.jobs.firstIndex(where: { $0.jobID == jobID }) else {
                throw MelixCLIError.requestFailed(
                    code: "training_queue_job_not_found",
                    message: "No local training queue job was found for \(jobID)."
                )
            }
            var job = document.jobs[index]
            guard !job.status.isTerminal || job.status == status else {
                throw MelixCLIError.requestFailed(
                    code: "training_queue_state_invalid",
                    message: "Local training queue job \(jobID) is already terminal."
                )
            }
            job.status = status
            job.updatedAtUnixMS = currentUnixMilliseconds()
            if let operatorError {
                job.operatorErrors.append(operatorError)
            }
            document.jobs[index] = job
            document.updatedAtUnixMS = job.updatedAtUnixMS
            recomputeMetrics(&document)
            try saveDocumentUnlocked(document)
            return job
        }
    }

    private func loadDocumentUnlocked() throws -> LocalTrainingQueueDocument {
        guard fileManager.fileExists(atPath: melixHome.localTrainingQueueFileURL.path) else {
            return LocalTrainingQueueDocument()
        }
        do {
            let data = try Data(contentsOf: melixHome.localTrainingQueueFileURL)
            return try Self.decoder.decode(LocalTrainingQueueDocument.self, from: data)
        } catch let error as MelixCLIError {
            throw error
        } catch {
            throw MelixCLIError.requestFailed(
                code: "training_queue_restore_failed",
                message: "Failed to restore local training queue: \(error.localizedDescription)"
            )
        }
    }

    private func saveDocumentUnlocked(_ document: LocalTrainingQueueDocument) throws {
        do {
            let data = try Self.encoder.encode(document)
            try melixHome.writeAtomically(data, to: melixHome.localTrainingQueueFileURL)
        } catch let error as MelixCLIError {
            throw error
        } catch {
            throw MelixCLIError.requestFailed(
                code: "training_queue_admission_failed",
                message: "Failed to persist local training queue: \(error.localizedDescription)"
            )
        }
    }

    private func writeCancellationRequest(_ job: LocalTrainingQueueJob) throws {
        let payload: [String: Any] = [
            "schema_version": "melix.job_cancel_request.v1",
            "job_id": job.jobID,
            "requested_at_unix_ms": job.updatedAtUnixMS,
            "source_queue_path": melixHome.localTrainingQueueFileURL.path,
            "status_at_request": job.status.rawValue,
            "phase_at_request": job.status.rawValue,
            "process_signal": [
                "pid": NSNull(),
                "sent": false,
                "reason": "local_training_queue_only",
            ],
        ]
        do {
            try fileManager.createDirectory(
                at: URL(fileURLWithPath: job.runDirectory, isDirectory: true),
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: MelixHome.directoryPermissions]
            )
            var data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
            data.append(0x0a)
            try melixHome.writeAtomically(data, to: URL(fileURLWithPath: job.cancellationRequestPath))
        } catch {
            throw MelixCLIError.requestFailed(
                code: "training_queue_cancel_failed",
                message: "Failed to persist cancellation request for \(job.jobID): \(error.localizedDescription)"
            )
        }
    }

    private func normalizedRunDirectory(_ value: String, jobID: String) -> String {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
            return URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath).path
        }
        return melixHome.modelOpsJobsRootURL
            .appendingPathComponent("train_lora", isDirectory: true)
            .appendingPathComponent(jobID, isDirectory: true)
            .path
    }

    private func isExclusive(_ resourceClass: String) -> Bool {
        let normalized = resourceClass.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return normalized.isEmpty
            || normalized == "exclusive_local_training"
            || normalized == "local_apple_silicon_training"
            || normalized == "local_training"
    }

    private func recomputeMetrics(_ document: inout LocalTrainingQueueDocument) {
        document.metrics.queuedJobCount = document.jobs.filter { $0.status == .queued }.count
        document.metrics.runningJobCount = document.jobs.filter { $0.status == .running || $0.status == .cancelRequested }.count
        document.metrics.queueRestoreLatencyMS = 0
    }

    private func nextJobID(_ jobs: [LocalTrainingQueueJob]) -> String {
        let maxID = jobs.compactMap { job -> Int? in
            guard job.jobID.hasPrefix("training-queue-") else {
                return nil
            }
            return Int(job.jobID.dropFirst("training-queue-".count))
        }.max() ?? 0
        return String(format: "training-queue-%04d", maxID + 1)
    }

    private func jobSort(_ lhs: LocalTrainingQueueJob, _ rhs: LocalTrainingQueueJob) -> Bool {
        if lhs.updatedAtUnixMS == rhs.updatedAtUnixMS {
            return lhs.jobID < rhs.jobID
        }
        return lhs.updatedAtUnixMS > rhs.updatedAtUnixMS
    }

    private func withLock<Value>(_ work: () throws -> Value) throws -> Value {
        lock.lock()
        defer { lock.unlock() }
        return try work()
    }

    private static func jsonObject<Value: Encodable>(from value: Value) throws -> [String: Any] {
        let data = try encoder.encode(value)
        return (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    private static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
        return encoder
    }()

    private static let decoder = JSONDecoder()
}

private struct LocalTrainingQueueDocument: Codable, Equatable, Sendable {
    var schemaVersion: String
    var queueID: String
    var updatedAtUnixMS: Int64
    var jobs: [LocalTrainingQueueJob]
    var metrics: LocalTrainingQueueMetrics

    init(
        schemaVersion: String = LocalTrainingQueueStore.schemaVersion,
        queueID: String = "local-training",
        updatedAtUnixMS: Int64 = currentUnixMilliseconds(),
        jobs: [LocalTrainingQueueJob] = [],
        metrics: LocalTrainingQueueMetrics = LocalTrainingQueueMetrics()
    ) {
        self.schemaVersion = schemaVersion
        self.queueID = queueID
        self.updatedAtUnixMS = updatedAtUnixMS
        self.jobs = jobs
        self.metrics = metrics
    }

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case queueID = "queue_id"
        case updatedAtUnixMS = "updated_at_unix_ms"
        case jobs
        case metrics
    }

    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? LocalTrainingQueueStore.schemaVersion
        guard schemaVersion == LocalTrainingQueueStore.schemaVersion else {
            throw MelixCLIError.requestFailed(
                code: "training_queue_restore_failed",
                message: "Unsupported local training queue schema: \(schemaVersion)."
            )
        }
        self.init(
            schemaVersion: schemaVersion,
            queueID: try container.decodeIfPresent(String.self, forKey: .queueID) ?? "local-training",
            updatedAtUnixMS: try container.decodeFlexibleInt64IfPresent(forKey: .updatedAtUnixMS) ?? 0,
            jobs: try container.decodeIfPresent([LocalTrainingQueueJob].self, forKey: .jobs) ?? [],
            metrics: try container.decodeIfPresent(LocalTrainingQueueMetrics.self, forKey: .metrics) ?? LocalTrainingQueueMetrics()
        )
    }
}

private struct LocalTrainingQueueMetrics: Codable, Equatable, Sendable {
    var queueAdmissionLatencyMS: Double
    var queueRestoreLatencyMS: Double
    var queuedJobCount: Int
    var runningJobCount: Int
    var cancellationLatencyMS: Double
    var admissionRefusalCount: Int

    init(
        queueAdmissionLatencyMS: Double = 0,
        queueRestoreLatencyMS: Double = 0,
        queuedJobCount: Int = 0,
        runningJobCount: Int = 0,
        cancellationLatencyMS: Double = 0,
        admissionRefusalCount: Int = 0
    ) {
        self.queueAdmissionLatencyMS = queueAdmissionLatencyMS
        self.queueRestoreLatencyMS = queueRestoreLatencyMS
        self.queuedJobCount = queuedJobCount
        self.runningJobCount = runningJobCount
        self.cancellationLatencyMS = cancellationLatencyMS
        self.admissionRefusalCount = admissionRefusalCount
    }

    enum CodingKeys: String, CodingKey {
        case queueAdmissionLatencyMS = "queue_admission_latency_ms"
        case queueRestoreLatencyMS = "queue_restore_latency_ms"
        case queuedJobCount = "queued_job_count"
        case runningJobCount = "running_job_count"
        case cancellationLatencyMS = "cancellation_latency_ms"
        case admissionRefusalCount = "admission_refusal_count"
    }
}

private func normalizedParameter(
    _ key: String,
    _ parameters: [String: String],
    fallback: String = ""
) -> String {
    let value = parameters[key]?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    return value.isEmpty ? fallback : value
}

private func normalizedDatasetID(_ request: LocalTrainingQueueAdmissionRequest) -> String {
    let explicit = normalizedParameter("dataset_id", request.parameters)
    if !explicit.isEmpty {
        return explicit
    }
    if request.datasetURI.isEmpty {
        return normalizedParameter("hf_dataset_path", request.parameters)
    }
    return request.datasetURI
}

private func currentUnixMilliseconds() -> Int64 {
    Int64(Date().timeIntervalSince1970 * 1000)
}

private extension KeyedDecodingContainer {
    func decodeFlexibleInt64IfPresent(forKey key: Key) throws -> Int64? {
        if let value = try? decodeIfPresent(Int64.self, forKey: key) {
            return value
        }
        if let value = try? decodeIfPresent(Int.self, forKey: key) {
            return Int64(value)
        }
        if let value = try? decodeIfPresent(Double.self, forKey: key) {
            return Int64(value)
        }
        if let value = try? decodeIfPresent(String.self, forKey: key) {
            return Int64(value.trimmingCharacters(in: .whitespacesAndNewlines))
        }
        return nil
    }
}
