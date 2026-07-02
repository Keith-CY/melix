import CryptoKit
import Foundation
import MelixControlPlaneCore

public final class MelixStorageMaintenanceStore {
    private let melixHome: MelixHome
    private let environment: [String: String]
    private let fileManager: FileManager

    public init(
        melixHome: MelixHome,
        environment: [String: String] = ProcessInfo.processInfo.environment,
        fileManager: FileManager = .default
    ) {
        self.melixHome = melixHome
        self.environment = environment
        self.fileManager = fileManager
    }

    public func inventory(workspaceManifestPath: String = "") throws -> [String: Any] {
        try buildInventory(workspaceManifestPath: workspaceManifestPath).payload
    }

    private func buildInventory(workspaceManifestPath: String = "") throws -> StorageInventoryBuild {
        let startedAt = storageUnixMilliseconds()
        let start = DispatchTime.now()
        let activeRoots = try loadActiveArtifactRoots()
        let manifest = try loadWorkspaceManifest(workspaceManifestPath)
        var entries: [StorageArtifactEntry] = []

        if let manifest {
            entries.append(contentsOf: artifactEntries(from: manifest, activeRoots: activeRoots))
        }
        entries.append(contentsOf: try melixOwnedEntries(activeRoots: activeRoots))
        entries = deduplicated(entries)

        let completedAt = storageUnixMilliseconds()
        let latency = elapsedMilliseconds(since: start)
        let summary = storageSummary(entries: entries)
        let inventorySeed = [
            "\(startedAt)",
            "\(entries.count)",
            entries.map(\.pathDigest).joined(separator: ","),
        ].joined(separator: "|")
        let payload: [String: Any] = [
            "schema_version": "melix.storage_inventory_receipt.v1",
            "inventory_id": stableID(prefix: "storage-inventory", seed: inventorySeed),
            "started_at_unix_ms": startedAt,
            "completed_at_unix_ms": max(completedAt, startedAt),
            "workspace_roots": manifest.map(workspaceRootPayloads) ?? [],
            "artifact_roots": manifest.map(artifactRootPayloads) ?? [],
            "artifact_entries": entries.map(\.payload),
            "summary": summary,
            "redaction_summary": [
                "schema_version": MelixDiagnosticsRedaction.schemaVersion,
                "redacted_field_count": entries.count,
            ],
            "active_artifact_summary": [
                "protected_active_artifact_count": entries.filter { $0.cleanupEligibility == "protected_active" }.count,
                "active_root_count": activeRoots.count,
            ],
            "metrics": [
                "storage_inventory_latency_ms": latency,
                "inventory_artifact_count": entries.count,
                "inventory_byte_size": summary["inventory_byte_size"] ?? 0,
                "retained_byte_size": summary["retained_byte_size"] ?? 0,
                "cleanable_byte_size": summary["cleanable_byte_size"] ?? 0,
                "protected_active_artifact_count": entries.filter { $0.cleanupEligibility == "protected_active" }.count,
            ],
        ]
        return StorageInventoryBuild(payload: payload, entries: entries)
    }

    public func cleanupPlan(workspaceManifestPath: String = "") throws -> [String: Any] {
        try inventoryAndCleanupPlan(workspaceManifestPath: workspaceManifestPath).cleanupPlan
    }

    public func inventoryAndCleanupPlan(workspaceManifestPath: String = "") throws -> (
        inventory: [String: Any],
        cleanupPlan: [String: Any]
    ) {
        let start = DispatchTime.now()
        let inventoryBuild = try buildInventory(workspaceManifestPath: workspaceManifestPath)
        let plan = cleanupPlanPayload(
            inventoryPayload: inventoryBuild.payload,
            entries: inventoryBuild.entries,
            mode: "dry_run",
            latencyMetricName: "cleanup_dry_run_latency_ms",
            latency: elapsedMilliseconds(since: start)
        )
        return (inventoryBuild.payload, plan)
    }

    public func applyCleanup(workspaceManifestPath: String = "") throws -> [String: Any] {
        let startedAt = storageUnixMilliseconds()
        let start = DispatchTime.now()
        let inventoryBuild = try buildInventory(workspaceManifestPath: workspaceManifestPath)
        let plannedEntries = inventoryBuild.entries
        let plan = cleanupPlanPayload(
            inventoryPayload: inventoryBuild.payload,
            entries: plannedEntries,
            mode: "apply",
            latencyMetricName: "cleanup_dry_run_latency_ms",
            latency: 0
        )
        let activeRoots = try loadActiveArtifactRoots()
        var deleted: [StorageArtifactEntry] = []
        let retained: [StorageArtifactEntry] = plannedEntries.filter { $0.cleanupEligibility == "retain" }
        var protected: [StorageArtifactEntry] = plannedEntries.filter {
            $0.cleanupEligibility == "protected_active" || isBlockedCleanupEligibility($0.cleanupEligibility)
        }
        var failed: [[String: Any]] = []

        for entry in plannedEntries where entry.cleanupEligibility == "cleanable" {
            do {
                guard let refreshed = refresh(entry: entry, activeRoots: activeRoots) else {
                    var missing = entry
                    missing.cleanupEligibility = "missing"
                    missing.cleanupReason = "artifact_missing_before_apply"
                    protected.append(missing)
                    continue
                }
                guard refreshed.mtimeUnixMS == entry.mtimeUnixMS,
                      refreshed.byteSize == entry.byteSize,
                      refreshed.pathDigest == entry.pathDigest else {
                    var changed = refreshed
                    changed.cleanupEligibility = "protected_active"
                    changed.cleanupReason = "changed_since_plan"
                    protected.append(changed)
                    continue
                }
                guard refreshed.cleanupEligibility == "cleanable" else {
                    protected.append(refreshed)
                    continue
                }
                try fileManager.removeItem(at: refreshed.url)
                deleted.append(refreshed)
            } catch {
                failed.append([
                    "artifact_id": entry.artifactID,
                    "artifact_kind": entry.artifactKind,
                    "path_redaction": entry.pathRedaction,
                    "path_digest": entry.pathDigest,
                    "cleanup_reason": "delete_failed",
                    "error": MelixDiagnosticsRedaction.redactString(String(describing: error)),
                ])
            }
        }

        let completedAt = storageUnixMilliseconds()
        let deletedBytes = deleted.reduce(UInt64(0)) { $0 + $1.byteSize }
        let protectedBytes = protected.reduce(UInt64(0)) { $0 + $1.byteSize }
        let retainedBytes = retained.reduce(UInt64(0)) { $0 + $1.byteSize }
        let planID = plan["cleanup_plan_id"] as? String ?? ""
        let receiptSeed = [
            "\(startedAt)",
            planID,
            deleted.map(\.pathDigest).joined(separator: ","),
            protected.map(\.pathDigest).joined(separator: ","),
            "\(failed.count)",
        ].joined(separator: "|")
        let receiptID = stableID(prefix: "storage-cleanup-receipt", seed: receiptSeed)
        let receiptURL = cleanupReceiptURL(receiptID: receiptID)
        let receipt: [String: Any] = [
            "schema_version": "melix.storage_cleanup_receipt.v1",
            "cleanup_receipt_id": receiptID,
            "cleanup_plan_id": planID,
            "started_at_unix_ms": startedAt,
            "completed_at_unix_ms": max(completedAt, startedAt),
            "receipt_path_redaction": redactedPath(receiptURL),
            "receipt_path_digest": sha256Hex(receiptURL.standardizedFileURL.path),
            "deleted_entries": deleted.map(\.payload),
            "retained_entries": retained.map(\.payload),
            "protected_entries": protected.map(\.payload),
            "failed_entries": failed,
            "summary": [
                "safe_delete_count": deleted.count,
                "deleted_entry_count": deleted.count,
                "retained_entry_count": retained.count,
                "protected_entry_count": protected.count,
                "failed_entry_count": failed.count,
                "deleted_byte_size": deletedBytes,
                "retained_byte_size": retainedBytes,
                "protected_byte_size": protectedBytes,
            ],
            "metrics": [
                "cleanup_apply_latency_ms": elapsedMilliseconds(since: start),
                "safe_delete_count": deleted.count,
                "deleted_byte_size": deletedBytes,
                "cleanup_failure_count": failed.count,
            ],
        ]
        try writeJSON(receipt, to: receiptURL)
        return receipt
    }

    public func latestCleanupReceipt() throws -> [String: Any]? {
        let directory = cleanupReceiptsDirectory()
        guard isDirectory(directory) else {
            return nil
        }
        let receipts = try fileManager.contentsOfDirectory(
            at: directory,
            includingPropertiesForKeys: [.contentModificationDateKey, .isRegularFileKey],
            options: [.skipsHiddenFiles]
        ).compactMap { url -> (url: URL, modifiedAt: Date)? in
            guard url.pathExtension == "json" else {
                return nil
            }
            guard let values = try? url.resourceValues(forKeys: [.contentModificationDateKey, .isRegularFileKey]),
                  values.isRegularFile == true else {
                return nil
            }
            return (url, values.contentModificationDate ?? .distantPast)
        }.sorted {
            if $0.modifiedAt == $1.modifiedAt {
                return $0.url.lastPathComponent > $1.url.lastPathComponent
            }
            return $0.modifiedAt > $1.modifiedAt
        }
        guard let latest = receipts.first else {
            return nil
        }
        let data = try Data(contentsOf: latest.url)
        guard let payload = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw MelixCLIError.runtime("Latest storage cleanup receipt is not a JSON object.")
        }
        return payload
    }

    private func cleanupPlanPayload(
        inventoryPayload: [String: Any],
        entries: [StorageArtifactEntry],
        mode: String,
        latencyMetricName: String,
        latency: Double
    ) -> [String: Any] {
        let retained = entries.filter { $0.cleanupEligibility == "retain" }
        let cleanable = entries.filter { $0.cleanupEligibility == "cleanable" }
        let protected = entries.filter { $0.cleanupEligibility == "protected_active" }
        let blocked = entries.filter { isBlockedCleanupEligibility($0.cleanupEligibility) }
        let retainedBytes = retained.reduce(UInt64(0)) { $0 + $1.byteSize }
        let cleanableBytes = cleanable.reduce(UInt64(0)) { $0 + $1.byteSize }
        let protectedBytes = protected.reduce(UInt64(0)) { $0 + $1.byteSize }
        let blockedBytes = blocked.reduce(UInt64(0)) { $0 + $1.byteSize }
        let inventoryID = inventoryPayload["inventory_id"] as? String ?? ""
        return [
            "schema_version": "melix.storage_cleanup_plan.v1",
            "cleanup_plan_id": stableID(prefix: "storage-cleanup-plan", seed: "\(inventoryID)-\(mode)"),
            "inventory_id": inventoryID,
            "mode": mode,
            "generated_at_unix_ms": storageUnixMilliseconds(),
            "retained_entries": retained.map(\.payload),
            "cleanable_entries": cleanable.map(\.payload),
            "protected_entries": protected.map(\.payload),
            "blocked_entries": blocked.map(\.payload),
            "summary": [
                "retained_entry_count": retained.count,
                "cleanable_entry_count": cleanable.count,
                "protected_entry_count": protected.count,
                "blocked_entry_count": blocked.count,
                "retained_byte_size": retainedBytes,
                "cleanable_byte_size": cleanableBytes,
                "protected_byte_size": protectedBytes,
                "blocked_byte_size": blockedBytes,
            ],
            "metrics": [
                latencyMetricName: latency,
                "retained_byte_size": retainedBytes,
                "cleanable_byte_size": cleanableBytes,
                "protected_active_artifact_count": protected.count,
                "safe_delete_count": cleanable.count,
            ],
        ]
    }

    private func loadWorkspaceManifest(_ path: String) throws -> StorageWorkspaceManifest? {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            return nil
        }
        let url = URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath)
        let data = try Data(contentsOf: url)
        let object = try JSONSerialization.jsonObject(with: data)
        guard let payload = object as? [String: Any] else {
            throw MelixCLIError.runtime("Workspace manifest is not a JSON object.")
        }
        return StorageWorkspaceManifest(manifestURL: url, payload: payload)
    }

    private func artifactEntries(
        from manifest: StorageWorkspaceManifest,
        activeRoots: [URL]
    ) -> [StorageArtifactEntry] {
        manifest.artifacts.map { artifact in
            let root = manifest.roots[artifact.rootID]
            let baseURL = root.map { manifest.resolveRoot($0.path) } ?? manifest.manifestURL.deletingLastPathComponent()
            let resolvedArtifact = resolveManifestArtifactURL(
                baseURL: baseURL,
                relativePath: artifact.relativePath
            )
            let ownership = ownership(for: root)
            let artifactKind = artifactKind(for: artifact.artifactType)
            return makeEntry(
                artifactID: artifact.artifactID,
                artifactKind: artifactKind,
                rootKind: root?.kind ?? "unknown",
                url: resolvedArtifact.url,
                ownership: ownership,
                activeRoots: activeRoots,
                forcedCleanupEligibility: resolvedArtifact.isSafe ? nil : "blocked_unsafe_path",
                forcedCleanupReason: resolvedArtifact.isSafe ? nil : "artifact_path_outside_root",
                includeFileStats: resolvedArtifact.isSafe
            )
        }
    }

    private func melixOwnedEntries(activeRoots: [URL]) throws -> [StorageArtifactEntry] {
        var entries: [StorageArtifactEntry] = []
        entries.append(contentsOf: try filesUnder(melixHome.logsDirectoryURL, kind: "runtime_log", rootKind: "melix_logs", activeRoots: activeRoots))
        entries.append(contentsOf: try staleTempFilesUnder(melixHome.runtimeDirectoryURL, activeRoots: activeRoots))
        entries.append(contentsOf: try jobArtifactEntriesUnder(melixHome.modelOpsJobsRootURL, activeRoots: activeRoots))
        entries.append(contentsOf: try jobArtifactEntriesUnder(melixHome.evaluationJobsRootURL, activeRoots: activeRoots))
        return entries
    }

    private func filesUnder(
        _ root: URL,
        kind: String,
        rootKind: String,
        activeRoots: [URL]
    ) throws -> [StorageArtifactEntry] {
        guard isDirectory(root) else {
            return []
        }
        return shallowFiles(root).map { url in
            makeEntry(
                artifactID: stableID(prefix: kind, seed: url.path),
                artifactKind: kind,
                rootKind: rootKind,
                url: url,
                ownership: "melix_owned",
                activeRoots: activeRoots
            )
        }
    }

    private func staleTempFilesUnder(_ root: URL, activeRoots: [URL]) throws -> [StorageArtifactEntry] {
        guard isDirectory(root) else {
            return []
        }
        let files = shallowFiles(root).filter { url in
            let name = url.lastPathComponent.lowercased()
            let path = url.path.lowercased()
            return name.contains("tmp") || name.contains("temp") || path.contains("/tmp/") || path.contains("/temp/")
        }
        return files.map { url in
            makeEntry(
                artifactID: stableID(prefix: "stale-temp-file", seed: url.path),
                artifactKind: "stale_temp_file",
                rootKind: "melix_runtime",
                url: url,
                ownership: "melix_owned",
                activeRoots: activeRoots
            )
        }
    }

    private func jobArtifactEntriesUnder(_ root: URL, activeRoots: [URL]) throws -> [StorageArtifactEntry] {
        guard isDirectory(root) else {
            return []
        }
        var entries: [StorageArtifactEntry] = []
        for url in shallowFiles(root) {
            let path = url.path.lowercased()
            let kind: String?
            if path.contains("/checkpoint") {
                kind = "checkpoint"
            } else if path.hasSuffix(".log") || path.contains("/logs") {
                kind = "runtime_log"
            } else if path.contains("/export") || path.contains("/tmp") || path.contains("/temp") {
                kind = "export_intermediate"
            } else {
                kind = nil
            }
            guard let kind else {
                continue
            }
            entries.append(
                makeEntry(
                    artifactID: stableID(prefix: kind, seed: url.path),
                    artifactKind: kind,
                    rootKind: "melix_jobs",
                    url: url,
                    ownership: "melix_owned",
                    activeRoots: activeRoots
                )
            )
        }
        return entries
    }

    private func makeEntry(
        artifactID: String,
        artifactKind: String,
        rootKind: String,
        url: URL,
        ownership: String,
        activeRoots: [URL],
        forcedCleanupEligibility: String? = nil,
        forcedCleanupReason: String? = nil,
        includeFileStats: Bool = true
    ) -> StorageArtifactEntry {
        let standardizedURL = url.standardizedFileURL
        let stats = includeFileStats ? fileStats(standardizedURL) : (exists: false, byteSize: UInt64(0), mtimeUnixMS: 0)
        let active = activeRoots.first { root in path(standardizedURL, isInside: root) } != nil
        let eligibility = forcedCleanupEligibility ?? cleanupEligibility(
            artifactKind: artifactKind,
            ownership: ownership,
            exists: stats.exists,
            active: active
        )
        let reason = forcedCleanupReason ?? cleanupReason(eligibility: eligibility, artifactKind: artifactKind)
        return StorageArtifactEntry(
            artifactID: artifactID.isEmpty ? stableID(prefix: artifactKind, seed: standardizedURL.path) : artifactID,
            artifactKind: artifactKind,
            rootKind: rootKind,
            url: standardizedURL,
            pathRedaction: redactedPath(standardizedURL),
            pathDigest: sha256Hex(standardizedURL.path),
            byteSize: stats.byteSize,
            mtimeUnixMS: stats.mtimeUnixMS,
            retentionClass: retentionClass(for: artifactKind),
            ownership: ownership,
            cleanupEligibility: eligibility,
            cleanupReason: reason,
            activeProtection: [
                "protected": active,
                "reason": active ? "active_job_artifact_root" : "none",
            ]
        )
    }

    private func refresh(entry: StorageArtifactEntry, activeRoots: [URL]) -> StorageArtifactEntry? {
        guard fileManager.fileExists(atPath: entry.url.path) else {
            return nil
        }
        return makeEntry(
            artifactID: entry.artifactID,
            artifactKind: entry.artifactKind,
            rootKind: entry.rootKind,
            url: entry.url,
            ownership: entry.ownership,
            activeRoots: activeRoots
        )
    }

    private func loadActiveArtifactRoots() throws -> [URL] {
        let runRecords = (try? MelixRunRecordStore(melixHome: melixHome, fileManager: fileManager).loadRecords()) ?? []
        let recordRoots = runRecords
            .filter { isActiveStatus($0.status) }
            .compactMap { nonEmptyURL($0.artifactRoot) }
        let queueRoots = (try? LocalTrainingQueueStore(melixHome: melixHome, fileManager: fileManager).list())?
            .filter { $0.status.isActive }
            .compactMap { nonEmptyURL($0.runDirectory) } ?? []
        return storageUniqueURLs(recordRoots + queueRoots)
    }

    private func storageSummary(entries: [StorageArtifactEntry]) -> [String: Any] {
        let retained = entries.filter { $0.cleanupEligibility == "retain" }
        let cleanable = entries.filter { $0.cleanupEligibility == "cleanable" }
        let protected = entries.filter { $0.cleanupEligibility == "protected_active" }
        let blocked = entries.filter { isBlockedCleanupEligibility($0.cleanupEligibility) }
        return [
            "artifact_count": entries.count,
            "inventory_byte_size": entries.reduce(UInt64(0)) { $0 + $1.byteSize },
            "retained_entry_count": retained.count,
            "cleanable_entry_count": cleanable.count,
            "protected_entry_count": protected.count,
            "blocked_entry_count": blocked.count,
            "retained_byte_size": retained.reduce(UInt64(0)) { $0 + $1.byteSize },
            "cleanable_byte_size": cleanable.reduce(UInt64(0)) { $0 + $1.byteSize },
            "protected_byte_size": protected.reduce(UInt64(0)) { $0 + $1.byteSize },
            "blocked_byte_size": blocked.reduce(UInt64(0)) { $0 + $1.byteSize },
        ]
    }

    private func workspaceRootPayloads(_ manifest: StorageWorkspaceManifest) -> [[String: Any]] {
        manifest.roots.values
            .filter { $0.kind.lowercased().contains("workspace") }
            .sorted { $0.rootID < $1.rootID }
            .map { root in
                [
                    "root_id": root.rootID,
                    "root_kind": root.kind,
                    "path_redaction": redactedPath(manifest.resolveRoot(root.path)),
                    "path_digest": sha256Hex(manifest.resolveRoot(root.path).path),
                ]
            }
    }

    private func artifactRootPayloads(_ manifest: StorageWorkspaceManifest) -> [[String: Any]] {
        manifest.roots.values.sorted { $0.rootID < $1.rootID }.map { root in
            [
                "root_id": root.rootID,
                "root_kind": root.kind,
                "ownership": ownership(for: root),
                "path_redaction": redactedPath(manifest.resolveRoot(root.path)),
                "path_digest": sha256Hex(manifest.resolveRoot(root.path).path),
            ]
        }
    }

    private func deduplicated(_ entries: [StorageArtifactEntry]) -> [StorageArtifactEntry] {
        var seen: Set<String> = []
        var result: [StorageArtifactEntry] = []
        for entry in entries {
            let key = "\(entry.pathDigest)::\(entry.artifactKind)"
            if seen.insert(key).inserted {
                result.append(entry)
            }
        }
        return result.sorted {
            if $0.artifactKind == $1.artifactKind {
                return $0.pathRedaction < $1.pathRedaction
            }
            return $0.artifactKind < $1.artifactKind
        }
    }

    private func shallowFiles(_ root: URL, maxDepth: Int = 4) -> [URL] {
        var results: [URL] = []
        func walk(_ directory: URL, depth: Int) {
            guard depth <= maxDepth else {
                return
            }
            guard let children = try? fileManager.contentsOfDirectory(
                at: directory,
                includingPropertiesForKeys: [.isDirectoryKey],
                options: [.skipsHiddenFiles]
            ) else {
                return
            }
            for child in children {
                let isDirectory = (try? child.resourceValues(forKeys: [.isDirectoryKey]))?.isDirectory ?? false
                if isDirectory {
                    walk(child, depth: depth + 1)
                } else {
                    results.append(child)
                }
            }
        }
        walk(root, depth: 0)
        return results
    }

    private func fileStats(_ url: URL) -> (exists: Bool, byteSize: UInt64, mtimeUnixMS: Int) {
        var isDirectory = ObjCBool(false)
        guard fileManager.fileExists(atPath: url.path, isDirectory: &isDirectory) else {
            return (false, 0, 0)
        }
        if isDirectory.boolValue {
            let files = shallowFiles(url, maxDepth: 8)
            var totalSize: UInt64 = 0
            var maxMtimeUnixMS = 0
            for file in files {
                let stats = regularFileStats(file)
                totalSize += stats.byteSize
                maxMtimeUnixMS = max(maxMtimeUnixMS, stats.mtimeUnixMS)
            }
            return (true, totalSize, maxMtimeUnixMS)
        }
        let stats = regularFileStats(url)
        return (true, stats.byteSize, stats.mtimeUnixMS)
    }

    private func regularFileStats(_ url: URL) -> (byteSize: UInt64, mtimeUnixMS: Int) {
        guard let attributes = try? fileManager.attributesOfItem(atPath: url.path) else {
            return (0, 0)
        }
        let size = (attributes[.size] as? NSNumber)?.uint64Value ?? 0
        let mtime = ((attributes[.modificationDate] as? Date)?.timeIntervalSince1970 ?? 0) * 1000
        return (size, Int(mtime))
    }

    private func isDirectory(_ url: URL) -> Bool {
        var isDirectory = ObjCBool(false)
        return fileManager.fileExists(atPath: url.path, isDirectory: &isDirectory) && isDirectory.boolValue
    }

    private func path(_ url: URL, isInside root: URL) -> Bool {
        let path = url.standardizedFileURL.path
        let rootPath = root.standardizedFileURL.path
        return path == rootPath || path.hasPrefix(rootPath + "/")
    }

    private func nonEmptyURL(_ path: String) -> URL? {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.isEmpty == false else {
            return nil
        }
        return URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath)
    }

    private func artifactKind(for artifactType: String) -> String {
        switch artifactType {
        case "WORKSPACE_ARTIFACT_TYPE_RAW_INPUTS":
            return "raw_file"
        case "WORKSPACE_ARTIFACT_TYPE_CLEANED_DATA":
            return "cleaned_segment"
        case "WORKSPACE_ARTIFACT_TYPE_DATASET_VERSION":
            return "dataset_version"
        case "WORKSPACE_ARTIFACT_TYPE_ADAPTER":
            return "adapter_output"
        case "WORKSPACE_ARTIFACT_TYPE_LOG":
            return "runtime_log"
        case "WORKSPACE_ARTIFACT_TYPE_EXPORT":
            return "export_intermediate"
        case "WORKSPACE_ARTIFACT_TYPE_REPORT", "WORKSPACE_ARTIFACT_TYPE_EVIDENCE_BUNDLE":
            return "evidence_bundle"
        default:
            return "unknown"
        }
    }

    private func ownership(for root: StorageArtifactRoot?) -> String {
        guard let root else {
            return "external_read_only"
        }
        if root.melixOwned == false {
            return "external_read_only"
        }
        return root.kind.lowercased().contains("workspace") ? "workspace_owned" : "melix_owned"
    }

    private func retentionClass(for artifactKind: String) -> String {
        switch artifactKind {
        case "raw_file", "dataset_version", "adapter_output", "evidence_bundle":
            return "retained_evidence"
        case "cleaned_segment", "checkpoint", "export_intermediate", "runtime_log", "stale_temp_file":
            return "derived_cache"
        default:
            return "unknown"
        }
    }

    private func cleanupEligibility(
        artifactKind: String,
        ownership: String,
        exists: Bool,
        active: Bool
    ) -> String {
        guard exists else {
            return "missing"
        }
        guard ownership != "external_read_only" else {
            return "blocked_external"
        }
        guard artifactKind != "unknown" else {
            return "blocked_unknown"
        }
        guard active == false else {
            return "protected_active"
        }
        switch artifactKind {
        case "cleaned_segment", "checkpoint", "export_intermediate", "runtime_log", "stale_temp_file":
            return "cleanable"
        default:
            return "retain"
        }
    }

    private func cleanupReason(eligibility: String, artifactKind: String) -> String {
        switch eligibility {
        case "retain":
            return "\(artifactKind)_retained_by_policy"
        case "cleanable":
            return "\(artifactKind)_derived_inactive"
        case "protected_active":
            return "active_job_artifact_root"
        case "blocked_external":
            return "external_read_only_root"
        case "missing":
            return "artifact_missing"
        case "blocked_unsafe_path":
            return "artifact_path_outside_root"
        default:
            return "unknown_artifact_or_ownership"
        }
    }

    private func resolveManifestArtifactURL(baseURL: URL, relativePath: String) -> (url: URL, isSafe: Bool) {
        let rootURL = baseURL.standardizedFileURL
        let trimmed = relativePath.trimmingCharacters(in: .whitespacesAndNewlines)
        let candidate = rootURL.appendingPathComponent(trimmed).standardizedFileURL
        guard isSafeManifestRelativePath(trimmed),
              path(candidate, isInside: rootURL),
              candidate.path != rootURL.path else {
            return (candidate, false)
        }
        return (candidate, true)
    }

    private func isSafeManifestRelativePath(_ path: String) -> Bool {
        guard path.isEmpty == false,
              path.hasPrefix("/") == false,
              path.hasPrefix("//") == false,
              path.contains("\\") == false,
              path.contains("\0") == false else {
            return false
        }
        if path.count >= 2 {
            let driveSeparatorIndex = path.index(after: path.startIndex)
            if path[driveSeparatorIndex] == ":" {
                return false
            }
        }
        return true
    }

    private func redactedPath(_ url: URL) -> String {
        let path = url.standardizedFileURL.path
        let roots = [
            (melixHome.rootURL.standardizedFileURL.path, "$MELIX_HOME"),
            (environment["MELIX_PROJECT_ROOT"] ?? "", "$MELIX_PROJECT_ROOT"),
        ]
        for (root, label) in roots where root.isEmpty == false {
            if path == root {
                return label
            }
            if path.hasPrefix(root + "/") {
                return label + String(path.dropFirst(root.count))
            }
        }
        return "<redacted-path>/\(url.lastPathComponent)"
    }

    private func cleanupReceiptURL(receiptID: String) -> URL {
        cleanupReceiptsDirectory()
            .appendingPathComponent("\(receiptID).json")
    }

    private func cleanupReceiptsDirectory() -> URL {
        melixHome.rootURL
            .appendingPathComponent("storage-cleanup", isDirectory: true)
            .appendingPathComponent("cleanup-receipts", isDirectory: true)
    }

    private func writeJSON(_ payload: [String: Any], to url: URL) throws {
        var data = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
        data.append(0x0a)
        try fileManager.createDirectory(
            at: url.deletingLastPathComponent(),
            withIntermediateDirectories: true,
            attributes: [.posixPermissions: MelixHome.directoryPermissions]
        )
        try data.write(to: url, options: [.atomic])
        try? fileManager.setAttributes([.posixPermissions: MelixHome.filePermissions], ofItemAtPath: url.path)
    }
}

private struct StorageArtifactEntry {
    var artifactID: String
    var artifactKind: String
    var rootKind: String
    var url: URL
    var pathRedaction: String
    var pathDigest: String
    var byteSize: UInt64
    var mtimeUnixMS: Int
    var retentionClass: String
    var ownership: String
    var cleanupEligibility: String
    var cleanupReason: String
    var activeProtection: [String: Any]

    var payload: [String: Any] {
        [
            "artifact_id": artifactID,
            "artifact_kind": artifactKind,
            "root_kind": rootKind,
            "path_redaction": pathRedaction,
            "path_digest": pathDigest,
            "byte_size": byteSize,
            "mtime_unix_ms": mtimeUnixMS,
            "retention_class": retentionClass,
            "ownership": ownership,
            "active_protection": activeProtection,
            "cleanup_eligibility": cleanupEligibility,
            "cleanup_reason": cleanupReason,
        ]
    }

    init(
        artifactID: String,
        artifactKind: String,
        rootKind: String,
        url: URL,
        pathRedaction: String,
        pathDigest: String,
        byteSize: UInt64,
        mtimeUnixMS: Int,
        retentionClass: String,
        ownership: String,
        cleanupEligibility: String,
        cleanupReason: String,
        activeProtection: [String: Any]
    ) {
        self.artifactID = artifactID
        self.artifactKind = artifactKind
        self.rootKind = rootKind
        self.url = url
        self.pathRedaction = pathRedaction
        self.pathDigest = pathDigest
        self.byteSize = byteSize
        self.mtimeUnixMS = mtimeUnixMS
        self.retentionClass = retentionClass
        self.ownership = ownership
        self.cleanupEligibility = cleanupEligibility
        self.cleanupReason = cleanupReason
        self.activeProtection = activeProtection
    }
}

private struct StorageInventoryBuild {
    let payload: [String: Any]
    let entries: [StorageArtifactEntry]
}

private struct StorageWorkspaceManifest {
    let manifestURL: URL
    let payload: [String: Any]
    let roots: [String: StorageArtifactRoot]
    let artifacts: [StorageManifestArtifact]

    init(manifestURL: URL, payload: [String: Any]) {
        self.manifestURL = manifestURL
        self.payload = payload
        let roots = (payload["artifact_roots"] as? [[String: Any]] ?? [])
            .map(StorageArtifactRoot.init(payload:))
        self.roots = Dictionary(uniqueKeysWithValues: roots.map { ($0.rootID, $0) })
        artifacts = (payload["artifacts"] as? [[String: Any]] ?? [])
            .map(StorageManifestArtifact.init(payload:))
    }

    func resolveRoot(_ rawPath: String) -> URL {
        let path = rawPath.trimmingCharacters(in: .whitespacesAndNewlines)
        guard path.isEmpty == false else {
            return manifestURL.deletingLastPathComponent()
        }
        if path.hasPrefix("/") {
            return URL(fileURLWithPath: path, isDirectory: true)
        }
        return manifestURL.deletingLastPathComponent().appendingPathComponent(path, isDirectory: true)
    }
}

private struct StorageArtifactRoot {
    let rootID: String
    let kind: String
    let path: String
    let melixOwned: Bool

    init(payload: [String: Any]) {
        rootID = payload["root_id"] as? String ?? ""
        kind = payload["kind"] as? String ?? ""
        path = payload["path"] as? String ?? ""
        melixOwned = payload["melix_owned"] as? Bool ?? false
    }
}

private struct StorageManifestArtifact {
    let artifactID: String
    let artifactType: String
    let rootID: String
    let relativePath: String

    init(payload: [String: Any]) {
        artifactID = payload["artifact_id"] as? String ?? ""
        artifactType = payload["artifact_type"] as? String ?? ""
        rootID = payload["root_id"] as? String ?? ""
        relativePath = payload["relative_path"] as? String ?? ""
    }
}

private func isActiveStatus(_ status: String) -> Bool {
    switch status.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() {
    case "active", "in_progress", "in-progress", "pending", "processing", "queued", "running", "started":
        return true
    default:
        return false
    }
}

private func isBlockedCleanupEligibility(_ eligibility: String) -> Bool {
    switch eligibility {
    case "blocked_external", "blocked_unknown", "blocked_unsafe_path", "missing":
        return true
    default:
        return false
    }
}

private func storageUnixMilliseconds() -> Int {
    Int(Date().timeIntervalSince1970 * 1000)
}

private func stableID(prefix: String, seed: String) -> String {
    "\(prefix)-\(sha256Hex(seed).prefix(12))"
}

private func sha256Hex(_ value: String) -> String {
    SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined()
}

private func storageUniqueURLs(_ urls: [URL]) -> [URL] {
    var seen: Set<String> = []
    var result: [URL] = []
    for url in urls {
        let path = url.standardizedFileURL.path
        if seen.insert(path).inserted {
            result.append(url.standardizedFileURL)
        }
    }
    return result
}
