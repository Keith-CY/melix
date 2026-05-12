import Foundation
import MelixControlPlaneCore

public enum RuntimeEvidenceReportDecodeError: Error, LocalizedError, Equatable, Sendable {
    case invalidJSON(String)

    public var errorDescription: String? {
        switch self {
        case .invalidJSON(let message):
            return message
        }
    }
}

public struct RuntimeEvidenceReportSummaryItem: Identifiable, Equatable, Sendable {
    public let id: String
    public let title: String
    public let value: String
    public let detail: String
}

public struct RuntimeEvidenceReportRunRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let side: String
    public let runID: String
    public let statusText: String
    public let runKindText: String
    public let durationText: String
    public let targetText: String
    public let artifactRoot: String
    public let issueText: String
}

public struct RuntimeEvidenceReportMetricRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let metric: String
    public let resultText: String
    public let statusText: String
    public let directionText: String
    public let baselineText: String
    public let candidateText: String
    public let deltaText: String
}

public struct RuntimeEvidenceReportProbeRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let side: String
    public let kind: String
    public let runID: String
    public let component: String
    public let phase: String
    public let durationText: String
    public let statusText: String
    public let detailText: String
}

public struct RuntimeEvidenceReportTelemetryRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let side: String
    public let runID: String
    public let collectorStatusText: String
    public let powerText: String
    public let utilizationText: String
    public let memoryText: String
    public let failureText: String
}

public struct RuntimeEvidenceReportValidityRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let metric: String
    public let valueText: String
}

public struct RuntimeEvidenceReportProcessRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let side: String
    public let runID: String
    public let roleText: String
    public let nameText: String
    public let pidText: String
    public let resourceText: String
}

public struct RuntimeEvidenceReportArtifactRow: Identifiable, Equatable, Sendable {
    public let id: String
    public let kindText: String
    public let path: String
    public let detailText: String
}

public struct RuntimeEvidenceReportState: Equatable, Sendable {
    public let schemaVersion: String
    public let reportID: String
    public let generatedAtText: String
    public let reportKindText: String
    public let identityText: String
    public let summaryItems: [RuntimeEvidenceReportSummaryItem]
    public let runRows: [RuntimeEvidenceReportRunRow]
    public let metricRows: [RuntimeEvidenceReportMetricRow]
    public let probeRows: [RuntimeEvidenceReportProbeRow]
    public let telemetryRows: [RuntimeEvidenceReportTelemetryRow]
    public let evidenceValidityRows: [RuntimeEvidenceReportValidityRow]
    public let processRows: [RuntimeEvidenceReportProcessRow]
    public let artifactRows: [RuntimeEvidenceReportArtifactRow]
    public let csvArtifactRows: [RuntimeEvidenceReportArtifactRow]
    public let knownGapRows: [String]
    public let instrumentationGapRows: [String]

    public var markdownReportPath: String? {
        artifactRows.first { $0.kindText == "Markdown Report" }?.path
    }

    public func metricRows(matching query: String) -> [RuntimeEvidenceReportMetricRow] {
        let normalizedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard normalizedQuery.isEmpty == false else {
            return metricRows
        }
        return metricRows.filter { row in
            [
                row.metric,
                row.resultText,
                row.statusText,
                row.directionText,
            ]
            .contains { $0.lowercased().contains(normalizedQuery) }
        }
    }

    public func artifactRows(matching query: String) -> [RuntimeEvidenceReportArtifactRow] {
        let normalizedQuery = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard normalizedQuery.isEmpty == false else {
            return artifactRows
        }
        return artifactRows.filter { row in
            [
                row.kindText,
                row.detailText,
                row.path,
            ]
            .contains { $0.lowercased().contains(normalizedQuery) }
        }
    }

    public static func decode(json: String) throws -> RuntimeEvidenceReportState {
        try decode(data: Data(json.utf8))
    }

    public static func decode(data: Data) throws -> RuntimeEvidenceReportState {
        do {
            let payload = try JSONDecoder().decode(RuntimeEvidenceReportPayload.self, from: data)
            return RuntimeEvidenceReportState(payload: payload)
        } catch let error as RuntimeEvidenceReportDecodeError {
            throw error
        } catch {
            throw RuntimeEvidenceReportDecodeError.invalidJSON(
                "Evidence report JSON could not be decoded: \(error)"
            )
        }
    }

    private init(payload: RuntimeEvidenceReportPayload) {
        schemaVersion = payload.schemaVersion
        reportID = payload.reportID
        generatedAtText = payload.generatedAt
        reportKindText = Self.titleText(payload.reportKind)
        identityText = [
            Self.shortCommit(payload.melixCommit),
            payload.gitBranch,
            payload.dirtyWorktree ? "dirty" : "clean",
        ]
        .filter { $0.isEmpty == false }
        .joined(separator: " | ")

        let runs = payload.runs.map { Self.makeRunRow($0, targets: payload.targets) }
            .sorted { lhs, rhs in
                if lhs.side == rhs.side {
                    return lhs.runID < rhs.runID
                }
                return Self.sideRank(lhs.side) < Self.sideRank(rhs.side)
            }
        runRows = runs

        metricRows = payload.metrics
            .map(Self.makeMetricRow)
            .sorted { lhs, rhs in
                if Self.resultRank(lhs.resultText) == Self.resultRank(rhs.resultText) {
                    return lhs.metric < rhs.metric
                }
                return Self.resultRank(lhs.resultText) < Self.resultRank(rhs.resultText)
            }

        probeRows = Self.makeProbeRows(payload.probeSummary)
        telemetryRows = Self.makeTelemetryRows(payload.telemetrySummary)
        evidenceValidityRows = Self.makeEvidenceValidityRows(payload.gateResult)
        processRows = Self.makeProcessRows(payload.processAttribution)
        artifactRows = Self.makeArtifactRows(payload.artifacts)
        csvArtifactRows = artifactRows.filter { $0.detailText == "CSV export" }
        knownGapRows = payload.knownGaps.sorted()
        instrumentationGapRows = payload.instrumentationGaps.sorted()

        let summary = payload.summary
        let gate = payload.gateResult
        summaryItems = [
            RuntimeEvidenceReportSummaryItem(
                id: "status",
                title: "Report Status",
                value: Self.titleText(summary.status),
                detail: "\(summary.metricCount) metrics"
            ),
            RuntimeEvidenceReportSummaryItem(
                id: "gate",
                title: "Evidence Gate",
                value: Self.titleText(gate.overallResult),
                detail: "\(gate.blockingFailures.count) blocking | \(gate.informationalResults.count) informational"
            ),
            RuntimeEvidenceReportSummaryItem(
                id: "runs",
                title: "Runs",
                value: "\(runs.count)",
                detail: "\(payload.sourceEvidenceIDs.count) evidence IDs"
            ),
            RuntimeEvidenceReportSummaryItem(
                id: "evidence-validity",
                title: "Evidence Validity",
                value: Self.evidenceValidityValue(payload.gateResult),
                detail: "\(evidenceValidityRows.count) validity metrics"
            ),
            RuntimeEvidenceReportSummaryItem(
                id: "hardware",
                title: "Hardware Telemetry",
                value: telemetryRows.isEmpty ? "Missing" : "Available",
                detail: "\(telemetryRows.filter { $0.failureText.isEmpty == false }.count) telemetry gaps"
            ),
        ]
    }

    private static func makeEvidenceValidityRows(
        _ gate: RuntimeEvidenceReportGateResultPayload
    ) -> [RuntimeEvidenceReportValidityRow] {
        gate.evidenceValidityMetrics
            .sorted { $0.key < $1.key }
            .map { key, value in
                RuntimeEvidenceReportValidityRow(
                    id: key,
                    metric: titleText(key),
                    valueText: metricValueText(value)
                )
            }
    }

    private static func evidenceValidityValue(
        _ gate: RuntimeEvidenceReportGateResultPayload
    ) -> String {
        let requiredKeys = [
            "required_evidence_present",
            "required_probe_phases_present",
            "required_telemetry_present",
        ]
        let metrics = gate.evidenceValidityMetrics
        guard metrics.isEmpty == false else {
            return "Missing"
        }
        let passed = requiredKeys.allSatisfy { (metrics[$0] ?? 0.0) >= 1.0 }
        return passed ? "Present" : "Missing"
    }

    private static func makeRunRow(
        _ run: RuntimeEvidenceReportRunPayload,
        targets: [RuntimeEvidenceReportTargetPayload]
    ) -> RuntimeEvidenceReportRunRow {
        let target = targets.first { $0.side == run.side && $0.runID == run.runID }
        let issueText = [
            run.failureSummary.compactSummary(prefix: "failure"),
            run.fallbackSummary.compactSummary(prefix: "fallback"),
        ]
        .filter { $0.isEmpty == false }
        .joined(separator: " | ")
        return RuntimeEvidenceReportRunRow(
            id: "\(run.side):\(run.runID)",
            side: titleText(run.side),
            runID: run.runID,
            statusText: titleText(run.status),
            runKindText: titleText(run.runKind),
            durationText: durationText(milliseconds: Double(run.durationMS)),
            targetText: [
                target?.targetModelID ?? "",
                target?.suiteID ?? "",
                target?.taskKind ?? "",
            ]
            .filter { $0.isEmpty == false }
            .joined(separator: " | "),
            artifactRoot: run.artifactRoot,
            issueText: issueText
        )
    }

    private static func makeMetricRow(
        _ row: RuntimeEvidenceReportMetricPayload
    ) -> RuntimeEvidenceReportMetricRow {
        RuntimeEvidenceReportMetricRow(
            id: row.metric,
            metric: row.metric,
            resultText: titleText(row.result),
            statusText: titleText(row.status),
            directionText: titleText(row.direction),
            baselineText: metricValueText(row.baseline),
            candidateText: metricValueText(row.candidate),
            deltaText: signedMetricValueText(row.delta, percent: row.deltaPercent)
        )
    }

    private static func makeProbeRows(
        _ summary: RuntimeEvidenceReportProbeSummaryPayload
    ) -> [RuntimeEvidenceReportProbeRow] {
        [
            probeRows(for: "baseline", side: summary.baseline),
            probeRows(for: "candidate", side: summary.candidate),
        ]
        .flatMap { $0 }
        .sorted { lhs, rhs in
            if probeKindRank(lhs.kind) == probeKindRank(rhs.kind) {
                return lhs.durationText > rhs.durationText
            }
            return probeKindRank(lhs.kind) < probeKindRank(rhs.kind)
        }
    }

    private static func probeRows(
        for side: String,
        side summary: RuntimeEvidenceReportProbeSidePayload
    ) -> [RuntimeEvidenceReportProbeRow] {
        let groups: [(String, [RuntimeEvidenceReportProbePhasePayload])] = [
            ("Failed", summary.failedPhases),
            ("Fallback", summary.fallbackPhases),
            ("Skipped", summary.skippedPhases),
            ("Slowest", summary.slowestPhases),
        ]
        return groups.flatMap { kind, phases in
            phases.enumerated().map { index, phase in
                RuntimeEvidenceReportProbeRow(
                    id: "\(side):\(kind):\(phase.runID):\(phase.phase):\(index)",
                    side: titleText(side),
                    kind: kind,
                    runID: phase.runID,
                    component: titleText(phase.component),
                    phase: titleText(phase.phase),
                    durationText: durationText(milliseconds: phase.durationMS),
                    statusText: titleText(phase.status),
                    detailText: [
                        phase.errorStage.isEmpty ? "" : "stage \(phase.errorStage)",
                        phase.errorCode.isEmpty ? "" : "code \(phase.errorCode)",
                    ]
                    .filter { $0.isEmpty == false }
                    .joined(separator: " | ")
                )
            }
        }
    }

    private static func makeTelemetryRows(
        _ summary: RuntimeEvidenceReportTelemetrySummaryPayload
    ) -> [RuntimeEvidenceReportTelemetryRow] {
        [
            telemetryRows(for: "baseline", rows: summary.baseline),
            telemetryRows(for: "candidate", rows: summary.candidate),
        ]
        .flatMap { $0 }
        .sorted { lhs, rhs in
            if lhs.side == rhs.side {
                return lhs.runID < rhs.runID
            }
            return sideRank(lhs.side) < sideRank(rhs.side)
        }
    }

    private static func telemetryRows(
        for side: String,
        rows: [RuntimeEvidenceReportTelemetryPayload]
    ) -> [RuntimeEvidenceReportTelemetryRow] {
        rows.map { row in
            RuntimeEvidenceReportTelemetryRow(
                id: "\(side):\(row.runID)",
                side: titleText(side),
                runID: row.runID,
                collectorStatusText: titleText(row.collectorStatus),
                powerText: powerText(row),
                utilizationText: utilizationText(row),
                memoryText: memoryText(row),
                failureText: row.telemetryFailures.joined(separator: " | ")
            )
        }
    }

    private static func makeProcessRows(
        _ attribution: RuntimeEvidenceReportProcessAttributionPayload
    ) -> [RuntimeEvidenceReportProcessRow] {
        [
            processRows(for: "baseline", summaries: attribution.baseline),
            processRows(for: "candidate", summaries: attribution.candidate),
        ]
        .flatMap { $0 }
        .sorted { lhs, rhs in
            if lhs.side == rhs.side {
                return lhs.roleText < rhs.roleText
            }
            return sideRank(lhs.side) < sideRank(rhs.side)
        }
    }

    private static func processRows(
        for side: String,
        summaries: [RuntimeEvidenceReportProcessSummaryPayload]
    ) -> [RuntimeEvidenceReportProcessRow] {
        summaries.flatMap { summary -> [RuntimeEvidenceReportProcessRow] in
            let primary = summary.primaryRuntimeProcess.asRow(
                side: side,
                runID: summary.runID,
                fallbackRole: "primary_runtime"
            )
            let control = summary.controlPlaneProcess.asRow(
                side: side,
                runID: summary.runID,
                fallbackRole: "control_plane"
            )
            let workers = summary.workerProcesses.enumerated().compactMap { index, process in
                process.asRow(side: side, runID: summary.runID, fallbackRole: "worker_\(index + 1)")
            }
            let external = summary.externalProviderProcesses.enumerated().compactMap { index, process in
                process.asRow(side: side, runID: summary.runID, fallbackRole: "external_\(index + 1)")
            }
            return [primary, control].compactMap { $0 } + workers + external
        }
    }

    private static func makeArtifactRows(
        _ artifacts: RuntimeEvidenceReportArtifactsPayload
    ) -> [RuntimeEvidenceReportArtifactRow] {
        var rows: [RuntimeEvidenceReportArtifactRow] = []
        appendArtifact(&rows, kind: "Report JSON", path: artifacts.reportJSONPath, detail: "Structured report")
        appendArtifact(&rows, kind: "Markdown Report", path: artifacts.markdownReportPath, detail: "Markdown report")
        appendArtifact(&rows, kind: "Evidence JSON", path: artifacts.evidenceJSONPath, detail: "Structured evidence")
        for (name, path) in artifacts.csvExportPaths.sorted(by: { $0.key < $1.key }) {
            appendArtifact(&rows, kind: titleText(name), path: path, detail: "CSV export")
        }
        appendArtifact(&rows, kind: "Probe Timeline", path: artifacts.probeTimelinePath, detail: "Probe data")
        appendArtifact(&rows, kind: "Telemetry JSONL", path: artifacts.telemetryJSONLPath, detail: "Hardware samples")
        for (index, path) in artifacts.rawOutputPaths.enumerated() {
            appendArtifact(&rows, kind: "Raw Output \(index + 1)", path: path, detail: "Run artifact")
        }
        appendArtifact(&rows, kind: "Logs", path: artifacts.logsPath, detail: "Logs")
        appendArtifact(&rows, kind: "Coverage", path: artifacts.coveragePath, detail: "Coverage")
        return rows
    }

    private static func appendArtifact(
        _ rows: inout [RuntimeEvidenceReportArtifactRow],
        kind: String,
        path: String,
        detail: String
    ) {
        let trimmedPath = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmedPath.isEmpty == false else {
            return
        }
        rows.append(
            RuntimeEvidenceReportArtifactRow(
                id: "\(kind):\(trimmedPath)",
                kindText: kind,
                path: trimmedPath,
                detailText: detail
            )
        )
    }

    fileprivate static func titleText(_ raw: String) -> String {
        let words = raw
            .replacingOccurrences(of: "_", with: " ")
            .replacingOccurrences(of: "-", with: " ")
            .split(separator: " ")
        guard words.isEmpty == false else {
            return "Unknown"
        }
        return words.map { word in
            word.prefix(1).uppercased() + word.dropFirst()
        }
        .joined(separator: " ")
    }

    private static func shortCommit(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.count > 12 else {
            return trimmed
        }
        return String(trimmed.prefix(12))
    }

    private static func sideRank(_ side: String) -> Int {
        switch side.lowercased() {
        case "baseline":
            return 0
        case "candidate":
            return 1
        default:
            return 2
        }
    }

    private static func resultRank(_ result: String) -> Int {
        switch result.lowercased() {
        case "fail":
            return 0
        case "informational":
            return 1
        case "pass":
            return 2
        default:
            return 3
        }
    }

    private static func probeKindRank(_ kind: String) -> Int {
        switch kind.lowercased() {
        case "failed":
            return 0
        case "fallback":
            return 1
        case "skipped":
            return 2
        default:
            return 3
        }
    }

    private static func metricValueText(_ value: Double?) -> String {
        guard let value else {
            return "-"
        }
        return String(format: "%.4f", value)
    }

    private static func signedMetricValueText(_ value: Double?, percent: Double?) -> String {
        guard let value else {
            return "-"
        }
        if let percent {
            return String(format: "%+.4f (%+.2f%%)", value, percent)
        }
        return String(format: "%+.4f", value)
    }

    private static func durationText(milliseconds: Double) -> String {
        if milliseconds >= 1_000 {
            return String(format: "%.2f s", milliseconds / 1_000)
        }
        return String(format: "%.2f ms", milliseconds)
    }

    private static func powerText(_ row: RuntimeEvidenceReportTelemetryPayload) -> String {
        let average = row.averageSystemPowerW.map { String(format: "%.2f W avg", $0) } ?? "system power missing"
        let peak = row.peakSystemPowerW.map { String(format: "%.2f W peak", $0) } ?? ""
        return [average, peak].filter { $0.isEmpty == false }.joined(separator: " | ")
    }

    private static func utilizationText(_ row: RuntimeEvidenceReportTelemetryPayload) -> String {
        [
            row.averageCPUUtilizationPercent.map { String(format: "CPU %.1f%%", $0) } ?? "",
            row.averageGPUUtilizationPercent.map { String(format: "GPU %.1f%%", $0) } ?? "",
            row.averageGPUFrequencyMHz.map { String(format: "GPU %.0f MHz", $0) } ?? "",
        ]
        .filter { $0.isEmpty == false }
        .joined(separator: " | ")
    }

    private static func memoryText(_ row: RuntimeEvidenceReportTelemetryPayload) -> String {
        [
            row.memoryUsedBytes.map { "used \(byteText($0))" } ?? "",
            row.memoryTotalBytes.map { "total \(byteText($0))" } ?? "",
            row.peakProcessMemoryBytes.map { "process peak \(byteText($0))" } ?? "",
        ]
        .filter { $0.isEmpty == false }
        .joined(separator: " | ")
    }

    fileprivate static func byteText(_ bytes: Int64) -> String {
        let value = Double(bytes)
        if value >= 1_073_741_824 {
            return String(format: "%.2f GB", value / 1_073_741_824)
        }
        if value >= 1_048_576 {
            return String(format: "%.2f MB", value / 1_048_576)
        }
        if value >= 1_024 {
            return String(format: "%.2f KB", value / 1_024)
        }
        return "\(bytes) B"
    }
}

private struct RuntimeEvidenceReportPayload: Decodable {
    let schemaVersion: String
    let reportID: String
    let generatedAt: String
    let melixCommit: String
    let gitBranch: String
    let dirtyWorktree: Bool
    let sourceEvidenceIDs: [String]
    let reportKind: String
    let summary: RuntimeEvidenceReportSummaryPayload
    let runs: [RuntimeEvidenceReportRunPayload]
    let targets: [RuntimeEvidenceReportTargetPayload]
    let metrics: [RuntimeEvidenceReportMetricPayload]
    let probeSummary: RuntimeEvidenceReportProbeSummaryPayload
    let telemetrySummary: RuntimeEvidenceReportTelemetrySummaryPayload
    let processAttribution: RuntimeEvidenceReportProcessAttributionPayload
    let gateResult: RuntimeEvidenceReportGateResultPayload
    let artifacts: RuntimeEvidenceReportArtifactsPayload
    let knownGaps: [String]
    let instrumentationGaps: [String]

    enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case reportID = "report_id"
        case generatedAt = "generated_at"
        case melixCommit = "melix_commit"
        case gitBranch = "git_branch"
        case dirtyWorktree = "dirty_worktree"
        case sourceEvidenceIDs = "source_evidence_ids"
        case reportKind = "report_kind"
        case summary
        case runs
        case targets
        case metrics
        case probeSummary = "probe_summary"
        case telemetrySummary = "telemetry_summary"
        case processAttribution = "process_attribution"
        case gateResult = "gate_result"
        case artifacts
        case knownGaps = "known_gaps"
        case instrumentationGaps = "instrumentation_gaps"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try container.decodeIfPresent(String.self, forKey: .schemaVersion) ?? ""
        reportID = try container.decodeIfPresent(String.self, forKey: .reportID) ?? ""
        generatedAt = try container.decodeIfPresent(String.self, forKey: .generatedAt) ?? ""
        melixCommit = try container.decodeIfPresent(String.self, forKey: .melixCommit) ?? ""
        gitBranch = try container.decodeIfPresent(String.self, forKey: .gitBranch) ?? ""
        dirtyWorktree = try container.decodeIfPresent(Bool.self, forKey: .dirtyWorktree) ?? false
        sourceEvidenceIDs = try container.decodeIfPresent([String].self, forKey: .sourceEvidenceIDs) ?? []
        reportKind = try container.decodeIfPresent(String.self, forKey: .reportKind) ?? ""
        summary = try container.decodeIfPresent(RuntimeEvidenceReportSummaryPayload.self, forKey: .summary) ?? .empty
        runs = try container.decodeIfPresent([RuntimeEvidenceReportRunPayload].self, forKey: .runs) ?? []
        targets = try container.decodeIfPresent([RuntimeEvidenceReportTargetPayload].self, forKey: .targets) ?? []
        metrics = try container.decodeIfPresent([RuntimeEvidenceReportMetricPayload].self, forKey: .metrics) ?? []
        probeSummary = try container.decodeIfPresent(RuntimeEvidenceReportProbeSummaryPayload.self, forKey: .probeSummary) ?? .empty
        telemetrySummary = try container.decodeIfPresent(RuntimeEvidenceReportTelemetrySummaryPayload.self, forKey: .telemetrySummary) ?? .empty
        processAttribution = try container.decodeIfPresent(RuntimeEvidenceReportProcessAttributionPayload.self, forKey: .processAttribution) ?? .empty
        gateResult = try container.decodeIfPresent(RuntimeEvidenceReportGateResultPayload.self, forKey: .gateResult) ?? .empty
        artifacts = try container.decodeIfPresent(RuntimeEvidenceReportArtifactsPayload.self, forKey: .artifacts) ?? .empty
        knownGaps = try container.decodeIfPresent([String].self, forKey: .knownGaps) ?? []
        instrumentationGaps = try container.decodeIfPresent([String].self, forKey: .instrumentationGaps) ?? []
    }
}

private struct RuntimeEvidenceReportSummaryPayload: Decodable {
    let status: String
    let metricCount: Int

    static let empty = RuntimeEvidenceReportSummaryPayload(status: "", metricCount: 0)

    enum CodingKeys: String, CodingKey {
        case status
        case metricCount = "metric_count"
    }
}

private struct RuntimeEvidenceReportRunPayload: Decodable {
    let side: String
    let runID: String
    let traceID: String
    let runKind: String
    let status: String
    let durationMS: Int64
    let artifactRoot: String
    let failureSummary: [String: StructuredJSONValue]
    let fallbackSummary: [String: StructuredJSONValue]

    enum CodingKeys: String, CodingKey {
        case side
        case runID = "run_id"
        case traceID = "trace_id"
        case runKind = "run_kind"
        case status
        case durationMS = "duration_ms"
        case artifactRoot = "artifact_root"
        case failureSummary = "failure_summary"
        case fallbackSummary = "fallback_summary"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        side = try container.decodeIfPresent(String.self, forKey: .side) ?? ""
        runID = try container.decodeIfPresent(String.self, forKey: .runID) ?? ""
        traceID = try container.decodeIfPresent(String.self, forKey: .traceID) ?? ""
        runKind = try container.decodeIfPresent(String.self, forKey: .runKind) ?? ""
        status = try container.decodeIfPresent(String.self, forKey: .status) ?? ""
        durationMS = try container.decodeIfPresent(Int64.self, forKey: .durationMS) ?? 0
        artifactRoot = try container.decodeIfPresent(String.self, forKey: .artifactRoot) ?? ""
        failureSummary = try container.decodeIfPresent([String: StructuredJSONValue].self, forKey: .failureSummary) ?? [:]
        fallbackSummary = try container.decodeIfPresent([String: StructuredJSONValue].self, forKey: .fallbackSummary) ?? [:]
    }
}

private struct RuntimeEvidenceReportTargetPayload: Decodable {
    let side: String
    let runID: String
    let targetModelID: String
    let taskKind: String
    let suiteID: String

    enum CodingKeys: String, CodingKey {
        case side
        case runID = "run_id"
        case targetModelID = "target_model_id"
        case taskKind = "task_kind"
        case suiteID = "suite_id"
    }
}

private struct RuntimeEvidenceReportMetricPayload: Decodable {
    let metric: String
    let baseline: Double?
    let candidate: Double?
    let delta: Double?
    let deltaPercent: Double?
    let direction: String
    let status: String
    let result: String

    enum CodingKeys: String, CodingKey {
        case metric
        case baseline
        case candidate
        case delta
        case deltaPercent = "delta_percent"
        case direction
        case status
        case result
    }
}

private struct RuntimeEvidenceReportProbeSummaryPayload: Decodable {
    let baseline: RuntimeEvidenceReportProbeSidePayload
    let candidate: RuntimeEvidenceReportProbeSidePayload

    static let empty = RuntimeEvidenceReportProbeSummaryPayload(
        baseline: .empty,
        candidate: .empty
    )
}

private struct RuntimeEvidenceReportProbeSidePayload: Decodable {
    let probeCount: Int
    let slowestPhases: [RuntimeEvidenceReportProbePhasePayload]
    let failedPhases: [RuntimeEvidenceReportProbePhasePayload]
    let skippedPhases: [RuntimeEvidenceReportProbePhasePayload]
    let fallbackPhases: [RuntimeEvidenceReportProbePhasePayload]

    static let empty = RuntimeEvidenceReportProbeSidePayload(
        probeCount: 0,
        slowestPhases: [],
        failedPhases: [],
        skippedPhases: [],
        fallbackPhases: []
    )

    enum CodingKeys: String, CodingKey {
        case probeCount = "probe_count"
        case slowestPhases = "slowest_phases"
        case failedPhases = "failed_phases"
        case skippedPhases = "skipped_phases"
        case fallbackPhases = "fallback_phases"
    }

    init(
        probeCount: Int,
        slowestPhases: [RuntimeEvidenceReportProbePhasePayload],
        failedPhases: [RuntimeEvidenceReportProbePhasePayload],
        skippedPhases: [RuntimeEvidenceReportProbePhasePayload],
        fallbackPhases: [RuntimeEvidenceReportProbePhasePayload]
    ) {
        self.probeCount = probeCount
        self.slowestPhases = slowestPhases
        self.failedPhases = failedPhases
        self.skippedPhases = skippedPhases
        self.fallbackPhases = fallbackPhases
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        probeCount = try container.decodeIfPresent(Int.self, forKey: .probeCount) ?? 0
        slowestPhases = try container.decodeIfPresent([RuntimeEvidenceReportProbePhasePayload].self, forKey: .slowestPhases) ?? []
        failedPhases = try container.decodeIfPresent([RuntimeEvidenceReportProbePhasePayload].self, forKey: .failedPhases) ?? []
        skippedPhases = try container.decodeIfPresent([RuntimeEvidenceReportProbePhasePayload].self, forKey: .skippedPhases) ?? []
        fallbackPhases = try container.decodeIfPresent([RuntimeEvidenceReportProbePhasePayload].self, forKey: .fallbackPhases) ?? []
    }
}

private struct RuntimeEvidenceReportProbePhasePayload: Decodable {
    let runID: String
    let component: String
    let phase: String
    let durationMS: Double
    let status: String
    let errorStage: String
    let errorCode: String

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case component
        case phase
        case durationMS = "duration_ms"
        case status
        case errorStage = "error_stage"
        case errorCode = "error_code"
    }
}

private struct RuntimeEvidenceReportTelemetrySummaryPayload: Decodable {
    let baseline: [RuntimeEvidenceReportTelemetryPayload]
    let candidate: [RuntimeEvidenceReportTelemetryPayload]

    static let empty = RuntimeEvidenceReportTelemetrySummaryPayload(baseline: [], candidate: [])
}

private struct RuntimeEvidenceReportTelemetryPayload: Decodable {
    let runID: String
    let collectorStatus: String
    let telemetryFailures: [String]
    let averageCPUUtilizationPercent: Double?
    let averageGPUUtilizationPercent: Double?
    let averageGPUFrequencyMHz: Double?
    let averageSystemPowerW: Double?
    let peakSystemPowerW: Double?
    let memoryUsedBytes: Int64?
    let memoryTotalBytes: Int64?
    let peakProcessMemoryBytes: Int64?

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case collectorStatus = "collector_status"
        case telemetryFailures = "telemetry_failures"
        case averageCPUUtilizationPercent = "average_cpu_utilization_percent"
        case averageGPUUtilizationPercent = "average_gpu_utilization_percent"
        case averageGPUFrequencyMHz = "average_gpu_frequency_mhz"
        case averageSystemPowerW = "average_system_power_w"
        case peakSystemPowerW = "peak_system_power_w"
        case memoryUsedBytes = "memory_used_bytes"
        case memoryTotalBytes = "memory_total_bytes"
        case peakProcessMemoryBytes = "peak_process_memory_bytes"
    }
}

private struct RuntimeEvidenceReportProcessAttributionPayload: Decodable {
    let baseline: [RuntimeEvidenceReportProcessSummaryPayload]
    let candidate: [RuntimeEvidenceReportProcessSummaryPayload]

    static let empty = RuntimeEvidenceReportProcessAttributionPayload(baseline: [], candidate: [])
}

private struct RuntimeEvidenceReportProcessSummaryPayload: Decodable {
    let runID: String
    let primaryRuntimeProcess: RuntimeEvidenceReportProcessPayload
    let controlPlaneProcess: RuntimeEvidenceReportProcessPayload
    let workerProcesses: [RuntimeEvidenceReportProcessPayload]
    let externalProviderProcesses: [RuntimeEvidenceReportProcessPayload]

    enum CodingKeys: String, CodingKey {
        case runID = "run_id"
        case primaryRuntimeProcess = "primary_runtime_process"
        case controlPlaneProcess = "control_plane_process"
        case workerProcesses = "worker_processes"
        case externalProviderProcesses = "external_provider_processes"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        runID = try container.decodeIfPresent(String.self, forKey: .runID) ?? ""
        primaryRuntimeProcess = try container.decodeIfPresent(RuntimeEvidenceReportProcessPayload.self, forKey: .primaryRuntimeProcess) ?? .empty
        controlPlaneProcess = try container.decodeIfPresent(RuntimeEvidenceReportProcessPayload.self, forKey: .controlPlaneProcess) ?? .empty
        workerProcesses = try container.decodeIfPresent([RuntimeEvidenceReportProcessPayload].self, forKey: .workerProcesses) ?? []
        externalProviderProcesses = try container.decodeIfPresent([RuntimeEvidenceReportProcessPayload].self, forKey: .externalProviderProcesses) ?? []
    }
}

private struct RuntimeEvidenceReportProcessPayload: Decodable {
    let pid: Int?
    let name: String
    let role: String
    let port: Int?
    let peakMemoryBytes: Int64?
    let averageCPUPercent: Double?
    let sampleCount: Int?

    static let empty = RuntimeEvidenceReportProcessPayload(
        pid: nil,
        name: "",
        role: "",
        port: nil,
        peakMemoryBytes: nil,
        averageCPUPercent: nil,
        sampleCount: nil
    )

    enum CodingKeys: String, CodingKey {
        case pid
        case name
        case role
        case port
        case peakMemoryBytes = "peak_memory_bytes"
        case averageCPUPercent = "avg_cpu_percent"
        case sampleCount = "sample_count"
    }

    func asRow(
        side: String,
        runID: String,
        fallbackRole: String
    ) -> RuntimeEvidenceReportProcessRow? {
        let effectiveName = name.trimmingCharacters(in: .whitespacesAndNewlines)
        let effectiveRole = role.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? fallbackRole : role
        guard effectiveName.isEmpty == false || pid != nil else {
            return nil
        }
        let pidText = pid.map { "pid \($0)" } ?? "pid unknown"
        let portText = port.map { "port \($0)" } ?? ""
        let memoryText = peakMemoryBytes.map { "peak \(RuntimeEvidenceReportState.byteText($0))" } ?? ""
        let cpuText = averageCPUPercent.map { String(format: "CPU %.1f%%", $0) } ?? ""
        let samplesText = sampleCount.map { "\($0) samples" } ?? ""
        return RuntimeEvidenceReportProcessRow(
            id: "\(side):\(runID):\(effectiveRole):\(pidText)",
            side: RuntimeEvidenceReportState.titleText(side),
            runID: runID,
            roleText: RuntimeEvidenceReportState.titleText(effectiveRole),
            nameText: effectiveName.isEmpty ? "Unknown process" : effectiveName,
            pidText: [pidText, portText].filter { $0.isEmpty == false }.joined(separator: " | "),
            resourceText: [memoryText, cpuText, samplesText].filter { $0.isEmpty == false }.joined(separator: " | ")
        )
    }
}

private struct RuntimeEvidenceReportGateResultPayload: Decodable {
    let overallResult: String
    let blockingFailures: [RuntimeEvidenceReportMetricPayload]
    let informationalResults: [RuntimeEvidenceReportMetricPayload]
    let evidenceValidityMetrics: [String: Double]

    static let empty = RuntimeEvidenceReportGateResultPayload(
        overallResult: "",
        blockingFailures: [],
        informationalResults: [],
        evidenceValidityMetrics: [:]
    )

    enum CodingKeys: String, CodingKey {
        case overallResult = "overall_result"
        case blockingFailures = "blocking_failures"
        case informationalResults = "informational_results"
        case evidenceValidityMetrics = "evidence_validity_metrics"
    }

    init(
        overallResult: String,
        blockingFailures: [RuntimeEvidenceReportMetricPayload],
        informationalResults: [RuntimeEvidenceReportMetricPayload],
        evidenceValidityMetrics: [String: Double]
    ) {
        self.overallResult = overallResult
        self.blockingFailures = blockingFailures
        self.informationalResults = informationalResults
        self.evidenceValidityMetrics = evidenceValidityMetrics
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        overallResult = try container.decodeIfPresent(String.self, forKey: .overallResult) ?? ""
        blockingFailures = try container.decodeIfPresent(
            [RuntimeEvidenceReportMetricPayload].self,
            forKey: .blockingFailures
        ) ?? []
        informationalResults = try container.decodeIfPresent(
            [RuntimeEvidenceReportMetricPayload].self,
            forKey: .informationalResults
        ) ?? []
        evidenceValidityMetrics = try container.decodeIfPresent(
            [String: Double].self,
            forKey: .evidenceValidityMetrics
        ) ?? [:]
    }
}

private struct RuntimeEvidenceReportArtifactsPayload: Decodable {
    let evidenceJSONPath: String
    let reportJSONPath: String
    let markdownReportPath: String
    let csvExportPaths: [String: String]
    let probeTimelinePath: String
    let telemetryJSONLPath: String
    let rawOutputPaths: [String]
    let logsPath: String
    let coveragePath: String

    static let empty = RuntimeEvidenceReportArtifactsPayload(
        evidenceJSONPath: "",
        reportJSONPath: "",
        markdownReportPath: "",
        csvExportPaths: [:],
        probeTimelinePath: "",
        telemetryJSONLPath: "",
        rawOutputPaths: [],
        logsPath: "",
        coveragePath: ""
    )

    enum CodingKeys: String, CodingKey {
        case evidenceJSONPath = "evidence_json_path"
        case reportJSONPath = "report_json_path"
        case markdownReportPath = "markdown_report_path"
        case csvExportPaths = "csv_export_paths"
        case probeTimelinePath = "probe_timeline_path"
        case telemetryJSONLPath = "telemetry_jsonl_path"
        case rawOutputPaths = "raw_output_paths"
        case logsPath = "logs_path"
        case coveragePath = "coverage_path"
    }

    init(
        evidenceJSONPath: String,
        reportJSONPath: String,
        markdownReportPath: String,
        csvExportPaths: [String: String],
        probeTimelinePath: String,
        telemetryJSONLPath: String,
        rawOutputPaths: [String],
        logsPath: String,
        coveragePath: String
    ) {
        self.evidenceJSONPath = evidenceJSONPath
        self.reportJSONPath = reportJSONPath
        self.markdownReportPath = markdownReportPath
        self.csvExportPaths = csvExportPaths
        self.probeTimelinePath = probeTimelinePath
        self.telemetryJSONLPath = telemetryJSONLPath
        self.rawOutputPaths = rawOutputPaths
        self.logsPath = logsPath
        self.coveragePath = coveragePath
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        evidenceJSONPath = try container.decodeIfPresent(String.self, forKey: .evidenceJSONPath) ?? ""
        reportJSONPath = try container.decodeIfPresent(String.self, forKey: .reportJSONPath) ?? ""
        markdownReportPath = try container.decodeIfPresent(String.self, forKey: .markdownReportPath) ?? ""
        csvExportPaths = try container.decodeIfPresent([String: String].self, forKey: .csvExportPaths) ?? [:]
        probeTimelinePath = try container.decodeIfPresent(String.self, forKey: .probeTimelinePath) ?? ""
        telemetryJSONLPath = try container.decodeIfPresent(String.self, forKey: .telemetryJSONLPath) ?? ""
        rawOutputPaths = try container.decodeIfPresent([String].self, forKey: .rawOutputPaths) ?? []
        logsPath = try container.decodeIfPresent(String.self, forKey: .logsPath) ?? ""
        coveragePath = try container.decodeIfPresent(String.self, forKey: .coveragePath) ?? ""
    }
}

private extension [String: StructuredJSONValue] {
    func compactSummary(prefix: String) -> String {
        let parts = sorted(by: { $0.key < $1.key }).compactMap { key, value -> String? in
            switch value {
            case .bool(false), .null:
                return nil
            case .string(let string):
                return string.isEmpty ? nil : "\(key)=\(string)"
            case .number(let number):
                return number == 0 ? nil : "\(key)=\(String(format: "%.0f", number))"
            case .bool(true):
                return "\(key)=true"
            case .array(let values):
                return values.isEmpty ? nil : "\(key)=\(values.count)"
            case .object(let object):
                return object.isEmpty ? nil : "\(key)=\(object.count)"
            }
        }
        guard parts.isEmpty == false else {
            return ""
        }
        return "\(prefix): \(parts.joined(separator: ", "))"
    }
}
