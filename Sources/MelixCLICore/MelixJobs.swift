import Foundation

private let melixJobsLogSnapshotByteLimit = 1 * 1024 * 1024

public struct JobsListOptions: Equatable, Sendable {
    public let sourcePath: String
    public let json: Bool

    public init(sourcePath: String = "", json: Bool = false) {
        self.sourcePath = sourcePath
        self.json = json
    }
}

public struct JobsShowOptions: Equatable, Sendable {
    public let jobID: String
    public let sourcePath: String
    public let json: Bool

    public init(jobID: String, sourcePath: String = "", json: Bool = false) {
        self.jobID = jobID
        self.sourcePath = sourcePath
        self.json = json
    }
}

public struct JobsArtifactsOptions: Equatable, Sendable {
    public let jobID: String
    public let sourcePath: String
    public let json: Bool

    public init(jobID: String, sourcePath: String = "", json: Bool = false) {
        self.jobID = jobID
        self.sourcePath = sourcePath
        self.json = json
    }
}

public struct JobsCancelOptions: Equatable, Sendable {
    public let jobID: String
    public let sourcePath: String
    public let json: Bool

    public init(jobID: String, sourcePath: String = "", json: Bool = false) {
        self.jobID = jobID
        self.sourcePath = sourcePath
        self.json = json
    }
}

struct MelixJobCancelResult {
    let payload: [String: Any]
}

private struct MelixModelOpsJobRecord {
    let jobID: String
    let operation: String
    let status: String
    let phase: String
    let sourceModel: String
    let outputDir: String
    let manifestPath: String
    let manifest: [String: Any]
    let createdAtUnixMS: Int
    let updatedAtUnixMS: Int
}

private struct MelixLocalTrainingQueueJobRecord {
    let job: LocalTrainingQueueJob
}

final class MelixJobStatusStore {
    private let runRecordStore: MelixRunRecordStore
    private let diagnosticsStore: MelixDiagnosticsStore
    private let melixHome: MelixHome
    private let trainingQueueStore: LocalTrainingQueueStore
    private let fileManager: FileManager

    init(
        runRecordStore: MelixRunRecordStore,
        diagnosticsStore: MelixDiagnosticsStore,
        melixHome: MelixHome,
        fileManager: FileManager = .default
    ) {
        self.runRecordStore = runRecordStore
        self.diagnosticsStore = diagnosticsStore
        self.melixHome = melixHome
        self.trainingQueueStore = LocalTrainingQueueStore(melixHome: melixHome, fileManager: fileManager)
        self.fileManager = fileManager
    }

    func list(sourcePath: String = "") throws -> [[String: Any]] {
        let runJobs = try runRecordStore.loadRecords(sourcePath: sourcePath).map(jobSummaryPayload)
        let runJobIDs = Set(runJobs.compactMap { $0["job_id"] as? String })
        let queueJobs = try loadLocalTrainingQueueJobs(sourcePath: sourcePath)
            .filter { !runJobIDs.contains($0.job.jobID) }
            .map(localTrainingQueueSummaryPayload)
        let visibleQueueJobIDs = Set(queueJobs.compactMap { $0["job_id"] as? String })
        let modelOpsJobs = try loadModelOpsTrainingJobs(sourcePath: sourcePath)
            .filter { !runJobIDs.contains($0.jobID) && !visibleQueueJobIDs.contains($0.jobID) }
            .map(modelOpsJobSummaryPayload)
        return sortJobPayloads(runJobs + queueJobs + modelOpsJobs)
    }

    func show(jobID: String, sourcePath: String = "") throws -> [String: Any] {
        if let record = try findRunRecord(jobID: jobID, sourcePath: sourcePath) {
            return jobStatusPayload(record)
        }
        if let record = try findLocalTrainingQueueJob(jobID: jobID, sourcePath: sourcePath) {
            return localTrainingQueueStatusPayload(record)
        }
        if let record = try findModelOpsTrainingJob(jobID: jobID, sourcePath: sourcePath) {
            return modelOpsJobStatusPayload(record)
        }
        throw MelixCLIError.runtime("No job was found for \(jobID).")
    }

    func artifacts(jobID: String, sourcePath: String = "") throws -> [String: Any] {
        if let record = try findRunRecord(jobID: jobID, sourcePath: sourcePath) {
            let artifacts = artifactPayloads(record)
            return [
                "schema_version": "melix.job_artifacts.v1",
                "job_id": record.runID,
                "artifact_count": artifacts.count,
                "artifacts": artifacts,
            ]
        }
        if let record = try findLocalTrainingQueueJob(jobID: jobID, sourcePath: sourcePath) {
            let artifacts = localTrainingQueueArtifactPayloads(record)
            return [
                "schema_version": "melix.job_artifacts.v1",
                "job_id": record.job.jobID,
                "artifact_count": artifacts.count,
                "artifacts": artifacts,
            ]
        }
        guard let record = try findModelOpsTrainingJob(jobID: jobID, sourcePath: sourcePath) else {
            throw MelixCLIError.runtime("No job was found for \(jobID).")
        }
        let artifacts = modelOpsArtifactPayloads(record)
        return [
            "schema_version": "melix.job_artifacts.v1",
            "job_id": record.jobID,
            "artifact_count": artifacts.count,
            "artifacts": artifacts,
        ]
    }

    func logSnapshot(jobID: String, sourcePath: String = "", follow: Bool) throws -> MelixLogSnapshot {
        if let record = try findRunRecord(jobID: jobID, sourcePath: sourcePath) {
            return try diagnosticsStore.logSnapshot(record: record, follow: follow)
        }
        if let record = try findLocalTrainingQueueJob(jobID: jobID, sourcePath: sourcePath) {
            throw MelixCLIError.runtime("No logs were found for \(record.job.jobID).")
        }
        guard let record = try findModelOpsTrainingJob(jobID: jobID, sourcePath: sourcePath) else {
            throw MelixCLIError.runtime("No job was found for \(jobID).")
        }
        guard let logURL = modelOpsLogURL(record) else {
            throw MelixCLIError.runtime("No logs were found for \(record.jobID).")
        }
        let text = try readModelOpsLogText(from: logURL, follow: follow)
        return MelixLogSnapshot(
            runID: record.jobID,
            sourcePath: record.manifestPath,
            logPath: logURL.path,
            followRequested: follow,
            activeFollowSupported: follow && isActiveStatus(record.status),
            text: MelixDiagnosticsRedaction.redactString(text)
        )
    }

    func cancel(jobID: String, sourcePath: String = "") throws -> MelixJobCancelResult {
        if let queueRecord = try findLocalTrainingQueueJob(jobID: jobID, sourcePath: sourcePath),
           try findRunRecord(jobID: jobID, sourcePath: sourcePath) == nil {
            return try cancel(queueRecord)
        }
        if let modelOpsRecord = try findModelOpsTrainingJob(jobID: jobID, sourcePath: sourcePath),
           try findRunRecord(jobID: jobID, sourcePath: sourcePath) == nil {
            return try cancel(modelOpsRecord)
        }
        guard let record = try findRunRecord(jobID: jobID, sourcePath: sourcePath) else {
            throw MelixCLIError.runtime("No job was found for \(jobID).")
        }
        let status = normalizedStatus(record.status)
        let phase = phase(for: record)
        let cancelable = isActiveStatus(status)
        let requestURL = cancelRequestURL(record)
        let existingRequest = loadCancelRequest(at: requestURL)

        guard cancelable else {
            return MelixJobCancelResult(payload: [
                "schema_version": "melix.job_cancel_result.v1",
                "job_id": record.runID,
                "cancel_requested": false,
                "status": record.status,
                "phase": phase,
                "reason": "job_terminal_or_not_active",
                "request_path": requestURL.path,
                "existing_request": existingRequest ?? NSNull(),
            ])
        }

        let processSignal = terminateProcessIfPresent(record)
        let requestedAt = jobCurrentUnixMilliseconds()
        let request: [String: Any] = [
            "schema_version": "melix.job_cancel_request.v1",
            "job_id": record.runID,
            "requested_at_unix_ms": requestedAt,
            "source_record_path": record.path,
            "status_at_request": record.status,
            "phase_at_request": phase,
            "process_signal": processSignal,
        ]
        try writeJSON(request, to: requestURL)
        return MelixJobCancelResult(payload: [
            "schema_version": "melix.job_cancel_result.v1",
            "job_id": record.runID,
            "cancel_requested": true,
            "status": record.status,
            "phase": phase,
            "request_path": requestURL.path,
            "request": request,
        ])
    }

    private func findRunRecord(jobID: String, sourcePath: String) throws -> MelixRunRecord? {
        try runRecordStore.loadRecords(sourcePath: sourcePath).first { $0.runID == jobID }
    }

    private func sortJobPayloads(_ payloads: [[String: Any]]) -> [[String: Any]] {
        payloads.sorted { lhs, rhs in
            let lhsUpdated = jobIntField(lhs, "updated_at_unix_ms")
            let rhsUpdated = jobIntField(rhs, "updated_at_unix_ms")
            if lhsUpdated == rhsUpdated {
                return stringField(lhs, "job_id") < stringField(rhs, "job_id")
            }
            return lhsUpdated > rhsUpdated
        }
    }

    private func jobSummaryPayload(_ record: MelixRunRecord) -> [String: Any] {
        let summary = record.summaryPayload()
        return [
            "schema_version": "melix.job_summary.v1",
            "job_id": record.runID,
            "run_kind": record.runKind,
            "status": record.status,
            "phase": phase(for: record),
            "started_at_unix_ms": record.startedAtUnixMS,
            "updated_at_unix_ms": updatedAtUnixMS(record),
            "duration_ms": record.durationMS,
            "model_id": stringField(summary, "model_id"),
            "task_kind": stringField(summary, "task_kind"),
            "suite_ids": summary["suite_ids"] ?? [],
            "dataset_id": stringField(summary, "dataset_id"),
            "artifact_root": record.artifactRoot,
            "record_path": record.path,
            "cancelable": isActiveStatus(record.status),
            "cancellation_requested": cancelRequestExists(record),
        ]
    }

    private func jobStatusPayload(_ record: MelixRunRecord) -> [String: Any] {
        var payload = jobSummaryPayload(record)
        payload["schema_version"] = "melix.job_status.v1"
        payload["command"] = record.payload["command"] as? [String: Any] ?? ["display": record.commandDisplay]
        payload["timestamps"] = [
            "started_at_unix_ms": record.startedAtUnixMS,
            "updated_at_unix_ms": updatedAtUnixMS(record),
            "ended_at_unix_ms": jobIntField(record.payload, "ended_at_unix_ms"),
            "duration_ms": record.durationMS,
        ]
        payload["progress"] = progressPayload(record) ?? NSNull()
        payload["throughput_metrics"] = throughputMetrics(record)
        payload["error"] = errorPayload(record)
        payload["logs"] = logsPayload(record)
        payload["artifacts"] = artifactPayloads(record)
        payload["cancellation"] = cancellationPayload(record)
        return payload
    }

    private func modelOpsJobSummaryPayload(_ record: MelixModelOpsJobRecord) -> [String: Any] {
        [
            "schema_version": "melix.job_summary.v1",
            "job_id": record.jobID,
            "run_kind": "training",
            "operation": record.operation,
            "status": record.status,
            "phase": record.phase,
            "started_at_unix_ms": record.createdAtUnixMS,
            "updated_at_unix_ms": record.updatedAtUnixMS,
            "duration_ms": jobIntField(record.manifest, "training_duration_ms"),
            "model_id": record.sourceModel,
            "task_kind": record.operation,
            "suite_ids": [],
            "dataset_id": stringField(record.manifest, "dataset_id"),
            "artifact_root": record.outputDir,
            "record_path": record.manifestPath,
            "cancelable": isActiveStatus(record.status),
            "cancellation_requested": modelOpsCancelRequestExists(record),
        ]
    }

    private func modelOpsJobStatusPayload(_ record: MelixModelOpsJobRecord) -> [String: Any] {
        var payload = modelOpsJobSummaryPayload(record)
        payload["schema_version"] = "melix.job_status.v1"
        payload["command"] = [
            "display": modelOpsCommandDisplay(record),
        ]
        payload["timestamps"] = [
            "started_at_unix_ms": record.createdAtUnixMS,
            "updated_at_unix_ms": record.updatedAtUnixMS,
            "ended_at_unix_ms": isActiveStatus(record.status) ? 0 : record.updatedAtUnixMS,
            "duration_ms": jobIntField(record.manifest, "training_duration_ms"),
        ]
        let pct: Any = isActiveStatus(record.status) ? NSNull() : 1.0
        payload["progress"] = [
            "phase": record.phase,
            "status": record.status,
            "pct": pct,
        ]
        payload["throughput_metrics"] = modelOpsThroughputMetrics(record)
        payload["error"] = modelOpsErrorPayload(record)
        payload["logs"] = modelOpsLogsPayload(record)
        payload["artifacts"] = modelOpsArtifactPayloads(record)
        payload["cancellation"] = modelOpsCancellationPayload(record)
        return payload
    }

    private func localTrainingQueueSummaryPayload(_ record: MelixLocalTrainingQueueJobRecord) -> [String: Any] {
        let job = record.job
        return [
            "schema_version": "melix.job_summary.v1",
            "job_id": job.jobID,
            "run_kind": "training",
            "operation": "train_lora",
            "status": job.status.rawValue,
            "phase": job.status.rawValue,
            "started_at_unix_ms": job.createdAtUnixMS,
            "updated_at_unix_ms": job.updatedAtUnixMS,
            "duration_ms": 0,
            "model_id": job.modelID,
            "task_kind": "train_lora",
            "suite_ids": [],
            "dataset_id": job.datasetID,
            "artifact_root": job.runDirectory,
            "record_path": melixHome.localTrainingQueueFileURL.path,
            "cancelable": job.status.isActive,
            "cancellation_requested": job.status == .cancelRequested || fileManager.fileExists(atPath: job.cancellationRequestPath),
        ]
    }

    private func localTrainingQueueStatusPayload(_ record: MelixLocalTrainingQueueJobRecord) -> [String: Any] {
        let job = record.job
        var payload = localTrainingQueueSummaryPayload(record)
        payload["schema_version"] = "melix.job_status.v1"
        payload["command"] = [
            "display": localTrainingQueueCommandDisplay(job),
        ]
        payload["timestamps"] = [
            "started_at_unix_ms": job.createdAtUnixMS,
            "updated_at_unix_ms": job.updatedAtUnixMS,
            "ended_at_unix_ms": job.status.isTerminal ? job.updatedAtUnixMS : 0,
            "duration_ms": 0,
        ]
        let pct: Any = job.status.isTerminal ? 1.0 : NSNull()
        payload["progress"] = [
            "phase": job.status.rawValue,
            "status": job.status.rawValue,
            "duration_ms": 0,
            "pct": pct,
        ]
        payload["throughput_metrics"] = [[String: Any]]()
        payload["error"] = localTrainingQueueErrorPayload(job)
        payload["logs"] = [
            "schema_version": "melix.job_logs_ref.v1",
            "available": false,
            "path": "",
            "command": "melix jobs logs \(job.jobID) --follow",
        ]
        payload["artifacts"] = localTrainingQueueArtifactPayloads(record)
        payload["cancellation"] = localTrainingQueueCancellationPayload(job)
        payload["training_queue"] = [
            "schema_version": LocalTrainingQueueStore.schemaVersion,
            "resource_class": job.resourceClass,
            "recovery_policy": job.recoveryPolicy,
            "queue_path": melixHome.localTrainingQueueFileURL.path,
            "workspace_manifest_path": job.workspaceManifestPath,
            "dataset_version_id": job.datasetVersionID,
            "preflight_receipt_path": job.preflightReceiptPath,
        ]
        if let trainabilityPreflight = localTrainingQueueTrainabilityPreflightPayload(job) {
            payload["trainability_preflight"] = trainabilityPreflight
        }
        return payload
    }

    private func artifactPayloads(_ record: MelixRunRecord) -> [[String: Any]] {
        var artifacts: [[String: Any]] = []
        appendArtifact(
            kind: "artifact_root",
            path: record.artifactRoot,
            relativePath: "",
            into: &artifacts
        )
        appendArtifact(
            kind: "run_record",
            path: record.path,
            relativePath: "run-record.json",
            into: &artifacts
        )
        if let logPath = diagnosticsStore.resolvedLogPath(record: record) {
            appendArtifact(kind: "logs", path: logPath, relativePath: "", into: &artifacts)
        }
        appendArtifact(
            kind: "cancel_request",
            path: cancelRequestURL(record).path,
            relativePath: "cancel-request.json",
            into: &artifacts
        )

        for artifact in record.artifacts {
            appendArtifact(
                kind: stringField(artifact, "kind", fallback: "artifact"),
                path: stringField(artifact, "path"),
                relativePath: stringField(artifact, "relative_path"),
                extra: artifact,
                into: &artifacts
            )
        }
        return dedupeArtifacts(artifacts)
    }

    private func modelOpsArtifactPayloads(_ record: MelixModelOpsJobRecord) -> [[String: Any]] {
        var artifacts: [[String: Any]] = []
        appendArtifact(
            kind: "artifact_root",
            path: record.outputDir,
            relativePath: "",
            into: &artifacts
        )
        appendArtifact(
            kind: "adapter_manifest",
            path: record.manifestPath,
            relativePath: "train_lora.adapter.json",
            into: &artifacts
        )
        if let logURL = modelOpsLogURL(record) {
            appendArtifact(kind: "logs", path: logURL.path, relativePath: "", into: &artifacts)
        }
        appendArtifact(
            kind: "cancel_request",
            path: modelOpsCancelRequestURL(record).path,
            relativePath: "cancel-request.json",
            into: &artifacts
        )

        let artifactKeys: [(String, String)] = [
            ("adapter_package", "artifact_path"),
            ("adapter_weights", "weights_path"),
            ("adapter_config", "adapter_config_path"),
            ("dataset_manifest", "dataset_source_manifest_path"),
            ("dataset_package", "dataset_materialized_package_path"),
            ("normalized_dataset_manifest", "normalized_dataset_manifest_path"),
            ("alignment_manifest", "alignment_run_manifest_path"),
            ("policy_update_trace", "policy_update_trace_path"),
            ("latest_checkpoint", "latest_checkpoint_path"),
            ("resume_source", "resume_source_path"),
            ("resume_source_manifest", "resume_source_manifest_path"),
        ]
        for (kind, key) in artifactKeys {
            appendArtifact(
                kind: kind,
                path: stringField(record.manifest, key),
                relativePath: "",
                into: &artifacts
            )
        }
        return dedupeArtifacts(artifacts)
    }

    private func localTrainingQueueArtifactPayloads(_ record: MelixLocalTrainingQueueJobRecord) -> [[String: Any]] {
        let job = record.job
        var artifacts: [[String: Any]] = []
        appendArtifact(
            kind: "training_queue",
            path: melixHome.localTrainingQueueFileURL.path,
            relativePath: "local-training-queue.json",
            into: &artifacts
        )
        appendArtifact(
            kind: "artifact_root",
            path: job.runDirectory,
            relativePath: "",
            into: &artifacts
        )
        appendArtifact(
            kind: "cancel_request",
            path: job.cancellationRequestPath,
            relativePath: "cancel-request.json",
            into: &artifacts
        )
        appendArtifact(
            kind: "preflight_receipt",
            path: job.preflightReceiptPath,
            relativePath: "",
            into: &artifacts
        )
        return dedupeArtifacts(artifacts)
    }

    private func appendArtifact(
        kind: String,
        path: String,
        relativePath: String,
        extra: [String: Any] = [:],
        into artifacts: inout [[String: Any]]
    ) {
        let trimmedPath = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedPath.isEmpty else {
            return
        }
        let url = URL(fileURLWithPath: (trimmedPath as NSString).expandingTildeInPath)
        var payload = extra
        payload["kind"] = kind
        payload["path"] = url.path
        payload["relative_path"] = relativePath
        payload["exists"] = fileManager.fileExists(atPath: url.path)
        artifacts.append(payload)
    }

    private func dedupeArtifacts(_ artifacts: [[String: Any]]) -> [[String: Any]] {
        var seen: Set<String> = []
        var result: [[String: Any]] = []
        for artifact in artifacts {
            let key = "\(stringField(artifact, "kind"))|\(stringField(artifact, "path"))"
            if seen.insert(key).inserted {
                result.append(artifact)
            }
        }
        return result
    }

    private func logsPayload(_ record: MelixRunRecord) -> [String: Any] {
        let logPath = diagnosticsStore.resolvedLogPath(record: record) ?? ""
        return [
            "schema_version": "melix.job_logs_ref.v1",
            "available": !logPath.isEmpty,
            "path": logPath,
            "command": "melix jobs logs \(record.runID) --follow",
        ]
    }

    private func modelOpsLogsPayload(_ record: MelixModelOpsJobRecord) -> [String: Any] {
        let logPath = modelOpsLogURL(record)?.path ?? ""
        return [
            "schema_version": "melix.job_logs_ref.v1",
            "available": !logPath.isEmpty,
            "path": logPath,
            "command": "melix jobs logs \(record.jobID) --follow",
        ]
    }

    private func modelOpsLogURL(_ record: MelixModelOpsJobRecord) -> URL? {
        let candidates = [
            stringField(record.manifest, "log_path"),
            stringField(record.manifest, "logs_path"),
            stringField(record.manifest, "stdout_path"),
            stringField(record.manifest, "stderr_path"),
            URL(fileURLWithPath: record.outputDir).appendingPathComponent("logs.txt").path,
            URL(fileURLWithPath: record.outputDir).appendingPathComponent("run.log").path,
            URL(fileURLWithPath: record.outputDir).appendingPathComponent("\(record.jobID).log").path,
            melixHome.logsDirectoryURL.appendingPathComponent("\(record.jobID).log").path,
            melixHome.logsDirectoryURL.appendingPathComponent("\(record.jobID).txt").path,
        ]
        for candidate in candidates {
            let trimmed = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else {
                continue
            }
            let url = URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath)
            if fileManager.fileExists(atPath: url.path) {
                return url
            }
        }
        return nil
    }

    private func cancellationPayload(_ record: MelixRunRecord) -> [String: Any] {
        let requestURL = cancelRequestURL(record)
        let request = loadCancelRequest(at: requestURL)
        let requested = request != nil
        return [
            "schema_version": "melix.job_cancellation_state.v1",
            "cancelable": isActiveStatus(record.status),
            "requested": requested,
            "request_path": requestURL.path,
            "request": request ?? NSNull(),
        ]
    }

    private func modelOpsCancellationPayload(_ record: MelixModelOpsJobRecord) -> [String: Any] {
        let requestURL = modelOpsCancelRequestURL(record)
        let request = loadCancelRequest(at: requestURL)
        return [
            "schema_version": "melix.job_cancellation_state.v1",
            "cancelable": isActiveStatus(record.status),
            "requested": request != nil,
            "request_path": requestURL.path,
            "request": request ?? NSNull(),
        ]
    }

    private func localTrainingQueueCancellationPayload(_ job: LocalTrainingQueueJob) -> [String: Any] {
        let request = loadCancelRequest(at: URL(fileURLWithPath: job.cancellationRequestPath))
        return [
            "schema_version": "melix.job_cancellation_state.v1",
            "cancelable": job.status.isActive,
            "requested": job.status == .cancelRequested || request != nil,
            "request_path": job.cancellationRequestPath,
            "request": request ?? NSNull(),
        ]
    }

    private func modelOpsErrorPayload(_ record: MelixModelOpsJobRecord) -> Any {
        let code = stringField(record.manifest, "error_code")
        let message = stringField(record.manifest, "error_message")
        if !code.isEmpty || !message.isEmpty {
            return [
                "code": code,
                "message": message,
            ]
        }
        let status = normalizedStatus(record.status)
        if ["failed", "error"].contains(status) {
            return ["message": "Job status was \(record.status)."]
        }
        return NSNull()
    }

    private func localTrainingQueueErrorPayload(_ job: LocalTrainingQueueJob) -> Any {
        guard let first = job.operatorErrors.first else {
            return NSNull()
        }
        var payload: [String: Any] = [
            "code": first.code,
            "message": first.message,
            "retriable": first.retriable,
        ]
        if !first.remediation.isEmpty {
            payload["remediation"] = first.remediation
        }
        return payload
    }

    private func localTrainingQueueTrainabilityPreflightPayload(_ job: LocalTrainingQueueJob) -> [String: Any]? {
        let trimmedPath = job.preflightReceiptPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedPath.isEmpty else {
            return nil
        }
        let url = URL(fileURLWithPath: (trimmedPath as NSString).expandingTildeInPath)
        guard var payload = loadJSONPayload(at: url),
              stringField(payload, "schema_version") == "melix.trainability_preflight.v1"
        else {
            return nil
        }
        payload["receipt_path"] = url.path
        return payload
    }

    private func modelOpsThroughputMetrics(_ record: MelixModelOpsJobRecord) -> [[String: Any]] {
        let tokensPerSecond = modelOpsDoubleField(record.manifest, "training.tokens_per_second")
        guard tokensPerSecond > 0 else {
            return []
        }
        return [[
            "name": "training.tokens_per_second",
            "value": tokensPerSecond,
            "unit": "tokens_per_second",
        ]]
    }

    private func modelOpsCommandDisplay(_ record: MelixModelOpsJobRecord) -> String {
        var parts = ["melix", "lora", "train"]
        if !record.sourceModel.isEmpty {
            parts.append(contentsOf: ["--model-id", record.sourceModel])
        }
        let adapterName = stringField(record.manifest, "adapter_name")
        if !adapterName.isEmpty {
            parts.append(contentsOf: ["--adapter-name", adapterName])
        }
        let datasetURI = stringField(record.manifest, "dataset_uri")
        if !datasetURI.isEmpty {
            parts.append(contentsOf: ["--dataset-uri", datasetURI])
        }
        return parts.joined(separator: " ")
    }

    private func localTrainingQueueCommandDisplay(_ job: LocalTrainingQueueJob) -> String {
        var parts = ["melix", "lora", "train"]
        if !job.modelID.isEmpty {
            parts.append(contentsOf: ["--model-id", job.modelID])
        }
        if !job.adapterName.isEmpty {
            parts.append(contentsOf: ["--adapter-name", job.adapterName])
        }
        if !job.datasetID.isEmpty {
            parts.append(contentsOf: ["--dataset-uri", job.datasetID])
        }
        return parts.joined(separator: " ")
    }

    private func errorPayload(_ record: MelixRunRecord) -> Any {
        if let error = record.payload["error"] as? [String: Any] {
            return error
        }
        let status = normalizedStatus(record.status)
        if ["failed", "error"].contains(status) {
            return ["message": "Run status was \(record.status)."]
        }
        return NSNull()
    }

    private func progressPayload(_ record: MelixRunRecord) -> [String: Any]? {
        if let progress = record.payload["progress"] as? [String: Any] {
            return progress
        }
        if let probes = record.payload["probes"] as? [[String: Any]],
           let latest = probes.last {
            return [
                "phase": stringField(latest, "phase", fallback: phase(for: record)),
                "status": stringField(latest, "status", fallback: record.status),
                "duration_ms": latest["duration_ms"] ?? NSNull(),
            ]
        }
        return nil
    }

    private func throughputMetrics(_ record: MelixRunRecord) -> [[String: Any]] {
        record.metrics.filter { metric in
            let name = stringField(metric, "name").lowercased()
            return name.contains("throughput")
                || name.contains("tokens_per_second")
                || name.contains("requests_per_second")
                || name.contains("tok/s")
        }
    }

    private func phase(for record: MelixRunRecord) -> String {
        for key in ["phase", "stage", "current_phase", "current_stage"] {
            let value = stringField(record.payload, key)
            if !value.isEmpty {
                return value
            }
        }
        if let progress = record.payload["progress"] as? [String: Any] {
            for key in ["phase", "stage"] {
                let value = stringField(progress, key)
                if !value.isEmpty {
                    return value
                }
            }
        }
        if let probes = record.payload["probes"] as? [[String: Any]],
           let latest = probes.last {
            let value = stringField(latest, "phase")
            if !value.isEmpty {
                return value
            }
        }
        return record.status.isEmpty ? "unknown" : record.status
    }

    private func updatedAtUnixMS(_ record: MelixRunRecord) -> Int {
        let explicit = jobIntField(record.payload, "updated_at_unix_ms")
        if explicit > 0 {
            return explicit
        }
        let ended = jobIntField(record.payload, "ended_at_unix_ms")
        if ended > 0 {
            return ended
        }
        return record.startedAtUnixMS
    }

    private func cancelRequestURL(_ record: MelixRunRecord) -> URL {
        URL(fileURLWithPath: record.path)
            .deletingLastPathComponent()
            .appendingPathComponent("cancel-request.json")
    }

    private func cancelRequestExists(_ record: MelixRunRecord) -> Bool {
        fileManager.fileExists(atPath: cancelRequestURL(record).path)
    }

    private func cancel(_ record: MelixLocalTrainingQueueJobRecord) throws -> MelixJobCancelResult {
        let job = record.job
        let requestURL = URL(fileURLWithPath: job.cancellationRequestPath)
        let existingRequest = loadCancelRequest(at: requestURL)
        guard job.status.isActive else {
            return MelixJobCancelResult(payload: [
                "schema_version": "melix.job_cancel_result.v1",
                "job_id": job.jobID,
                "cancel_requested": false,
                "status": job.status.rawValue,
                "phase": job.status.rawValue,
                "reason": "job_terminal_or_not_active",
                "request_path": requestURL.path,
                "existing_request": existingRequest ?? NSNull(),
            ])
        }

        let updated = try trainingQueueStore.requestCancel(jobID: job.jobID)
        let request = loadCancelRequest(at: URL(fileURLWithPath: updated.cancellationRequestPath)) ?? [:]
        return MelixJobCancelResult(payload: [
            "schema_version": "melix.job_cancel_result.v1",
            "job_id": updated.jobID,
            "cancel_requested": true,
            "status": updated.status.rawValue,
            "phase": updated.status.rawValue,
            "request_path": updated.cancellationRequestPath,
            "request": request,
        ])
    }

    private func cancel(_ record: MelixModelOpsJobRecord) throws -> MelixJobCancelResult {
        let requestURL = modelOpsCancelRequestURL(record)
        let existingRequest = loadCancelRequest(at: requestURL)
        guard isActiveStatus(record.status) else {
            return MelixJobCancelResult(payload: [
                "schema_version": "melix.job_cancel_result.v1",
                "job_id": record.jobID,
                "cancel_requested": false,
                "status": record.status,
                "phase": record.phase,
                "reason": "job_terminal_or_not_active",
                "request_path": requestURL.path,
                "existing_request": existingRequest ?? NSNull(),
            ])
        }

        let requestedAt = jobCurrentUnixMilliseconds()
        let request: [String: Any] = [
            "schema_version": "melix.job_cancel_request.v1",
            "job_id": record.jobID,
            "requested_at_unix_ms": requestedAt,
            "source_manifest_path": record.manifestPath,
            "status_at_request": record.status,
            "phase_at_request": record.phase,
            "process_signal": [
                "pid": NSNull(),
                "sent": false,
                "reason": "pid_not_recorded",
            ],
        ]
        try writeJSON(request, to: requestURL)
        return MelixJobCancelResult(payload: [
            "schema_version": "melix.job_cancel_result.v1",
            "job_id": record.jobID,
            "cancel_requested": true,
            "status": record.status,
            "phase": record.phase,
            "request_path": requestURL.path,
            "request": request,
        ])
    }

    private func modelOpsCancelRequestURL(_ record: MelixModelOpsJobRecord) -> URL {
        URL(fileURLWithPath: record.outputDir).appendingPathComponent("cancel-request.json")
    }

    private func modelOpsCancelRequestExists(_ record: MelixModelOpsJobRecord) -> Bool {
        fileManager.fileExists(atPath: modelOpsCancelRequestURL(record).path)
    }

    private func loadCancelRequest(at url: URL) -> [String: Any]? {
        loadJSONPayload(at: url)
    }

    private func loadJSONPayload(at url: URL) -> [String: Any]? {
        guard let data = try? Data(contentsOf: url),
              let object = try? JSONSerialization.jsonObject(with: data),
              let payload = object as? [String: Any]
        else {
            return nil
        }
        return payload
    }

    private func terminateProcessIfPresent(_ record: MelixRunRecord) -> [String: Any] {
        guard let pid = persistedPID(record) else {
            return [
                "pid": NSNull(),
                "sent": false,
                "reason": "pid_not_recorded",
            ]
        }
        return [
            "pid": pid,
            "sent": false,
            "reason": "direct_process_signal_disabled",
        ]
    }

    private func persistedPID(_ record: MelixRunRecord) -> Int? {
        for key in ["pid", "process_id"] {
            let value = jobIntField(record.payload, key)
            if value > 0 {
                return value
            }
        }
        for containerKey in ["process", "worker", "runtime"] {
            if let payload = record.payload[containerKey] as? [String: Any] {
                for key in ["pid", "process_id"] {
                    let value = jobIntField(payload, key)
                    if value > 0 {
                        return value
                    }
                }
            }
        }
        return nil
    }

    private func findModelOpsTrainingJob(jobID: String, sourcePath: String) throws -> MelixModelOpsJobRecord? {
        try loadModelOpsTrainingJobs(sourcePath: sourcePath).first { $0.jobID == jobID }
    }

    private func findLocalTrainingQueueJob(
        jobID: String,
        sourcePath: String
    ) throws -> MelixLocalTrainingQueueJobRecord? {
        try loadLocalTrainingQueueJobs(sourcePath: sourcePath).first { $0.job.jobID == jobID }
    }

    private func loadLocalTrainingQueueJobs(sourcePath: String) throws -> [MelixLocalTrainingQueueJobRecord] {
        let trimmed = sourcePath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty else {
            return []
        }
        return try trainingQueueStore.list().map(MelixLocalTrainingQueueJobRecord.init(job:))
    }

    private func loadModelOpsTrainingJobs(sourcePath: String) throws -> [MelixModelOpsJobRecord] {
        var records: [MelixModelOpsJobRecord] = []
        for root in modelOpsSourceRoots(sourcePath: sourcePath) {
            records.append(contentsOf: try loadModelOpsTrainingJobs(at: root))
        }

        var seen: Set<String> = []
        var unique: [MelixModelOpsJobRecord] = []
        for record in records.sorted(by: modelOpsJobSort) {
            let key = "\(record.jobID)|\(record.manifestPath)"
            if seen.insert(key).inserted {
                unique.append(record)
            }
        }
        return unique
    }

    private func modelOpsSourceRoots(sourcePath: String) -> [URL] {
        let trimmed = sourcePath.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            return [melixHome.modelOpsJobsRootURL]
        }
        let url = URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath)
        return jobUniqueURLs([
            url,
            url.appendingPathComponent("jobs", isDirectory: true)
                .appendingPathComponent("model-ops", isDirectory: true),
            url.appendingPathComponent("model-ops", isDirectory: true),
        ])
    }

    private func loadModelOpsTrainingJobs(at root: URL) throws -> [MelixModelOpsJobRecord] {
        var records: [MelixModelOpsJobRecord] = []
        if let direct = try loadModelOpsTrainingManifest(
            root.appendingPathComponent("train_lora.adapter.json")
        ) {
            records.append(direct)
        }

        let trainRoots: [URL]
        if root.lastPathComponent == "train_lora" {
            trainRoots = [root]
        } else {
            trainRoots = [root.appendingPathComponent("train_lora", isDirectory: true)]
        }
        for trainRoot in trainRoots {
            records.append(contentsOf: try loadModelOpsTrainingJobsFromTrainRoot(trainRoot))
        }
        return records
    }

    private func loadModelOpsTrainingJobsFromTrainRoot(_ trainRoot: URL) throws -> [MelixModelOpsJobRecord] {
        var isDirectory = ObjCBool(false)
        guard fileManager.fileExists(atPath: trainRoot.path, isDirectory: &isDirectory), isDirectory.boolValue else {
            return []
        }
        let children = try fileManager.contentsOfDirectory(
            at: trainRoot,
            includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        )
        var records: [MelixModelOpsJobRecord] = []
        for child in children where child.lastPathComponent.hasPrefix("model-ops-") && isDirectoryURL(child) {
            if let record = try loadModelOpsTrainingManifest(child.appendingPathComponent("train_lora.adapter.json")) {
                records.append(record)
            }
        }
        return records
    }

    private func loadModelOpsTrainingManifest(_ url: URL) throws -> MelixModelOpsJobRecord? {
        guard fileManager.fileExists(atPath: url.path) else {
            return nil
        }
        let data = try Data(contentsOf: url)
        guard let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return nil
        }
        let operation = stringField(payload, "operation")
        guard operation.trimmingCharacters(in: .whitespacesAndNewlines) == "train_lora" else {
            return nil
        }
        let jobID = stringField(payload, "job_id", fallback: modelOpsJobID(from: url))
        guard !jobID.isEmpty else {
            return nil
        }
        let modifiedAt = fileModificationUnixMilliseconds(url)
        let createdAt = positiveOrFallback(jobIntField(payload, "created_at_unix_ms"), modifiedAt)
        let updatedAt = positiveOrFallback(jobIntField(payload, "updated_at_unix_ms"), modifiedAt)
        return MelixModelOpsJobRecord(
            jobID: jobID,
            operation: operation,
            status: stringField(payload, "status", fallback: "completed"),
            phase: stringField(payload, "phase", fallback: "write_manifest"),
            sourceModel: stringField(payload, "source_model", fallback: stringField(payload, "model_id")),
            outputDir: url.deletingLastPathComponent().path,
            manifestPath: url.path,
            manifest: payload,
            createdAtUnixMS: createdAt,
            updatedAtUnixMS: updatedAt
        )
    }

    private func modelOpsJobID(from manifestURL: URL) -> String {
        for component in manifestURL.pathComponents.reversed() where component.hasPrefix("model-ops-") {
            return component
        }
        return ""
    }

    private func modelOpsJobSort(_ lhs: MelixModelOpsJobRecord, _ rhs: MelixModelOpsJobRecord) -> Bool {
        if lhs.updatedAtUnixMS == rhs.updatedAtUnixMS {
            return lhs.jobID < rhs.jobID
        }
        return lhs.updatedAtUnixMS > rhs.updatedAtUnixMS
    }

    private func isDirectoryURL(_ url: URL) -> Bool {
        var isDirectory = ObjCBool(false)
        return fileManager.fileExists(atPath: url.path, isDirectory: &isDirectory) && isDirectory.boolValue
    }

    private func fileModificationUnixMilliseconds(_ url: URL) -> Int {
        let values = try? url.resourceValues(forKeys: [.contentModificationDateKey])
        return Int((values?.contentModificationDate ?? Date()).timeIntervalSince1970 * 1000)
    }

    private func readModelOpsLogText(from url: URL, follow: Bool) throws -> String {
        var data = try readModelOpsLogData(from: url)
        guard follow else {
            return String(decoding: data, as: UTF8.self)
        }

        let deadline = Date().addingTimeInterval(1.0)
        var stablePolls = 0
        while Date() < deadline && stablePolls < 2 {
            Thread.sleep(forTimeInterval: 0.2)
            let next = try readModelOpsLogData(from: url)
            if next.count > data.count {
                data = next
                stablePolls = 0
            } else {
                stablePolls += 1
            }
        }
        return String(decoding: data, as: UTF8.self)
    }

    private func readModelOpsLogData(from url: URL) throws -> Data {
        let attributes = try fileManager.attributesOfItem(atPath: url.path)
        let fileSize = (attributes[.size] as? NSNumber)?.uint64Value ?? 0
        let offset = fileSize > UInt64(melixJobsLogSnapshotByteLimit)
            ? fileSize - UInt64(melixJobsLogSnapshotByteLimit)
            : 0
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        if offset > 0 {
            try handle.seek(toOffset: offset)
        }
        let data = handle.readDataToEndOfFile()
        guard offset > 0 else {
            return data
        }
        var snapshot = Data("Log snapshot truncated to last \(melixJobsLogSnapshotByteLimit) bytes.\n".utf8)
        snapshot.append(data)
        return snapshot
    }

    private func writeJSON(_ payload: [String: Any], to url: URL) throws {
        try fileManager.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: MelixHome.directoryPermissions]
        )
        var data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
        data.append(0x0a)
        try data.write(to: url, options: [.atomic])
        try? fileManager.setAttributes([.posixPermissions: MelixHome.filePermissions], ofItemAtPath: url.path)
    }
}

func renderJobList(_ jobs: [[String: Any]]) -> String {
    guard !jobs.isEmpty else {
        return "No jobs found.\n"
    }
    let rows = jobs.map { job in
        [
            stringField(job, "job_id"),
            stringField(job, "run_kind"),
            stringField(job, "status"),
            stringField(job, "phase"),
            stringField(job, "model_id", fallback: "-"),
            jobSuiteLabel(job["suite_ids"]),
            stringField(job, "started_at_unix_ms"),
            stringField(job, "artifact_root", fallback: "-"),
        ].joined(separator: "\t")
    }
    return ([
        "job_id\trun_kind\tstatus\tphase\tmodel_id\tsuites\tstarted_at_unix_ms\tartifact_root",
    ] + rows).joined(separator: "\n") + "\n"
}

func renderJobStatus(_ payload: [String: Any]) -> String {
    var lines = [
        "Job: \(stringField(payload, "job_id"))",
        "Status: \(stringField(payload, "status"))",
        "Phase: \(stringField(payload, "phase"))",
        "Started: \(stringField(payload, "started_at_unix_ms"))",
        "Record: \(stringField(payload, "record_path"))",
    ]
    if let error = payload["error"] as? [String: Any] {
        let code = stringField(error, "code")
        let message = stringField(error, "message")
        let errorText = [code, message].filter { !$0.isEmpty }.joined(separator: ": ")
        if !errorText.isEmpty {
            lines.append("Error: \(errorText)")
        }
        let remediation = stringField(error, "remediation")
        if !remediation.isEmpty {
            lines.append("Remediation: \(remediation)")
        }
    }
    if let trainingQueue = payload["training_queue"] as? [String: Any] {
        let recoveryPolicy = stringField(trainingQueue, "recovery_policy")
        if !recoveryPolicy.isEmpty {
            lines.append("Recovery: \(recoveryPolicy)")
        }
        let preflightReceiptPath = stringField(trainingQueue, "preflight_receipt_path")
        if !preflightReceiptPath.isEmpty {
            lines.append("Preflight: \(preflightReceiptPath)")
        }
    }
    if let preflight = payload["trainability_preflight"] as? [String: Any],
       let checks = preflight["checks"] as? [[String: Any]] {
        for check in checks {
            let status = stringField(check, "status").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard status == "blocked" || status == "error" else {
                continue
            }
            let code = stringField(check, "code")
            let message = stringField(check, "operator_message")
            let checkText = [code, message].filter { !$0.isEmpty }.joined(separator: ": ")
            if !checkText.isEmpty {
                lines.append("Preflight Check: \(checkText)")
            }
            let remediation = stringField(check, "remediation")
            if !remediation.isEmpty {
                lines.append("Preflight Remediation: \(remediation)")
            }
        }
    }
    if let logs = payload["logs"] as? [String: Any],
       !stringField(logs, "path").isEmpty {
        lines.append("Logs: \(stringField(logs, "path"))")
    }
    if let cancellation = payload["cancellation"] as? [String: Any],
       (cancellation["requested"] as? Bool) == true {
        lines.append("Cancellation: requested")
    }
    return lines.joined(separator: "\n") + "\n"
}

func renderJobArtifacts(_ payload: [String: Any]) -> String {
    let artifacts = payload["artifacts"] as? [[String: Any]] ?? []
    guard !artifacts.isEmpty else {
        return "No artifacts found for \(stringField(payload, "job_id")).\n"
    }
    let rows = artifacts.map { artifact in
        [
            stringField(artifact, "kind"),
            stringField(artifact, "exists"),
            stringField(artifact, "path"),
        ].joined(separator: "\t")
    }
    return (["kind\texists\tpath"] + rows).joined(separator: "\n") + "\n"
}

private func normalizedStatus(_ status: String) -> String {
    status.trimmingCharacters(in: .whitespacesAndNewlines)
        .lowercased()
        .replacingOccurrences(of: "-", with: "_")
}

private func isActiveStatus(_ status: String) -> Bool {
    switch normalizedStatus(status) {
    case "active", "in_progress", "pending", "processing", "queued", "running", "started":
        return true
    default:
        return false
    }
}

private func jobIntField(_ payload: [String: Any], _ key: String) -> Int {
    if let value = payload[key] as? Int {
        return value
    }
    if let value = payload[key] as? NSNumber {
        return value.intValue
    }
    if let value = payload[key] as? String, let parsed = Int(value) {
        return parsed
    }
    return 0
}

private func modelOpsDoubleField(_ payload: [String: Any], _ key: String) -> Double {
    if let value = payload[key] as? Double {
        return value
    }
    if let value = payload[key] as? NSNumber {
        return value.doubleValue
    }
    if let value = payload[key] as? String, let parsed = Double(value) {
        return parsed
    }
    return 0
}

private func positiveOrFallback(_ value: Int, _ fallback: Int) -> Int {
    value > 0 ? value : fallback
}

private func jobUniqueURLs(_ urls: [URL]) -> [URL] {
    var seen: Set<String> = []
    var result: [URL] = []
    for url in urls {
        let path = url.standardizedFileURL.path
        if seen.insert(path).inserted {
            result.append(url)
        }
    }
    return result
}

private func jobSuiteLabel(_ value: Any?) -> String {
    if let values = value as? [String] {
        return values.isEmpty ? "-" : values.joined(separator: ",")
    }
    if let values = value as? [Any] {
        let labels = values.map { String(describing: $0) }.filter { !$0.isEmpty }
        return labels.isEmpty ? "-" : labels.joined(separator: ",")
    }
    if let value = value {
        let label = String(describing: value)
        return label.isEmpty ? "-" : label
    }
    return "-"
}

private func jobCurrentUnixMilliseconds() -> Int {
    Int(Date().timeIntervalSince1970 * 1000)
}
