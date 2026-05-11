import Foundation

public struct RunsListOptions: Equatable, Sendable {
    public let sourcePath: String
    public let json: Bool

    public init(sourcePath: String = "", json: Bool = false) {
        self.sourcePath = sourcePath
        self.json = json
    }
}

public struct RunsShowOptions: Equatable, Sendable {
    public let runID: String
    public let sourcePath: String
    public let json: Bool

    public init(runID: String, sourcePath: String = "", json: Bool = false) {
        self.runID = runID
        self.sourcePath = sourcePath
        self.json = json
    }
}

public struct RunsExportOptions: Equatable, Sendable {
    public let runID: String
    public let sourcePath: String
    public let format: String
    public let outputPath: String

    public init(runID: String, sourcePath: String = "", format: String = "json", outputPath: String = "") {
        self.runID = runID
        self.sourcePath = sourcePath
        self.format = format
        self.outputPath = outputPath
    }
}

public struct RunReportOptions: Equatable, Sendable {
    public let sourcePath: String
    public let format: String

    public init(sourcePath: String, format: String = "markdown") {
        self.sourcePath = sourcePath
        self.format = format
    }
}

struct MelixRunRecord {
    let payload: [String: Any]
    let path: String

    var runID: String { stringValue("run_id") }
    var runKind: String { stringValue("run_kind") }
    var status: String { stringValue("status") }
    var startedAtUnixMS: Int { intValue("started_at_unix_ms") }
    var durationMS: Int { intValue("duration_ms") }

    func stringValue(_ key: String) -> String {
        payload[key].map { String(describing: $0) } ?? ""
    }

    func intValue(_ key: String) -> Int {
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

    func dictionary(_ key: String) -> [String: Any] {
        payload[key] as? [String: Any] ?? [:]
    }

    func array(_ key: String) -> [[String: Any]] {
        payload[key] as? [[String: Any]] ?? []
    }

    var commandDisplay: String {
        let command = dictionary("command")
        return command["display"].map { String(describing: $0) } ?? ""
    }

    var target: [String: Any] { dictionary("target") }
    var dataset: [String: Any] { dictionary("dataset") }
    var environment: [String: Any] { dictionary("environment") }
    var metrics: [[String: Any]] { array("metrics") }
    var artifacts: [[String: Any]] { array("artifacts") }
    var knownGaps: [String] { payload["known_gaps"] as? [String] ?? [] }

    func summaryPayload() -> [String: Any] {
        [
            "run_id": runID,
            "run_kind": runKind,
            "status": status,
            "started_at_unix_ms": startedAtUnixMS,
            "duration_ms": durationMS,
            "model_id": stringField(target, "model_id", fallback: stringField(target, "base_model_id")),
            "task_kind": stringField(target, "task_kind"),
            "source_repo": stringField(target, "source_repo"),
            "suite_ids": dataset["suite_ids"] ?? [],
            "dataset_id": stringField(dataset, "dataset_id", fallback: stringField(dataset, "dataset_ref")),
            "artifact_root": stringValue("artifact_root"),
            "record_path": path,
        ]
    }
}

public struct MelixRunReportResult {
    public let payload: [String: Any]
    public let markdown: String
}

public final class MelixRunRecordStore {
    private let melixHome: MelixHome
    private let fileManager: FileManager

    public init(melixHome: MelixHome, fileManager: FileManager = .default) {
        self.melixHome = melixHome
        self.fileManager = fileManager
    }

    func loadRecords(sourcePath: String = "") throws -> [MelixRunRecord] {
        var records: [MelixRunRecord] = []
        for url in sourceRoots(sourcePath: sourcePath) {
            records.append(contentsOf: try loadRecords(at: url))
        }
        return records.sorted {
            if $0.startedAtUnixMS == $1.startedAtUnixMS {
                return $0.runID < $1.runID
            }
            return $0.startedAtUnixMS > $1.startedAtUnixMS
        }
    }

    func findRecord(runID: String, sourcePath: String = "") throws -> MelixRunRecord {
        guard let record = try loadRecords(sourcePath: sourcePath).first(where: { $0.runID == runID }) else {
            throw MelixCLIError.runtime("No run record was found for \(runID).")
        }
        return record
    }

    func report(kind: String, sourcePath: String) throws -> MelixRunReportResult {
        let scanStart = DispatchTime.now()
        let records = try loadRecords(sourcePath: sourcePath).filter { record in
            switch kind {
            case "benchmark":
                return record.runKind.hasPrefix("benchmark")
            case "evaluation":
                return record.runKind.hasPrefix("evaluation")
            default:
                return true
            }
        }
        let scanMS = elapsedMilliseconds(since: scanStart)
        let renderStart = DispatchTime.now()
        var payload = makeReportPayload(kind: kind, records: records, scanMS: scanMS, markdownRenderMS: 0)
        _ = renderReportMarkdown(payload)
        payload["report_generation"] = [
            "record_scan_ms": scanMS,
            "markdown_render_ms": elapsedMilliseconds(since: renderStart),
        ]
        let markdown = renderReportMarkdown(payload)
        return MelixRunReportResult(payload: payload, markdown: markdown)
    }

    private func sourceRoots(sourcePath: String) -> [URL] {
        let trimmed = sourcePath.trimmingCharacters(in: .whitespacesAndNewlines)
        if !trimmed.isEmpty {
            return [URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath)]
        }
        return [
            melixHome.modelOpsJobsRootURL.appendingPathComponent("bench", isDirectory: true),
            melixHome.evaluationJobsRootURL,
        ]
    }

    private func loadRecords(at url: URL) throws -> [MelixRunRecord] {
        var isDirectory = ObjCBool(false)
        guard fileManager.fileExists(atPath: url.path, isDirectory: &isDirectory) else {
            return []
        }
        if !isDirectory.boolValue {
            return try loadRecordFile(url).map { [$0] } ?? []
        }
        var records: [MelixRunRecord] = []
        if let rootRecord = try loadRecordFile(url.appendingPathComponent("run-record.json")) {
            records.append(rootRecord)
        }
        guard let enumerator = fileManager.enumerator(
            at: url,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else {
            return records
        }
        for case let candidateURL as URL in enumerator where candidateURL.lastPathComponent == "run-record.json" {
            if candidateURL.path == url.appendingPathComponent("run-record.json").path {
                continue
            }
            if let record = try loadRecordFile(candidateURL) {
                records.append(record)
            }
        }
        return records
    }

    private func loadRecordFile(_ url: URL) throws -> MelixRunRecord? {
        guard fileManager.fileExists(atPath: url.path) else {
            return nil
        }
        let data = try Data(contentsOf: url)
        let object = try JSONSerialization.jsonObject(with: data)
        guard let payload = object as? [String: Any],
              stringField(payload, "schema_version") == "melix.run_record.v1"
        else {
            return nil
        }
        return MelixRunRecord(payload: payload, path: url.path)
    }
}

func renderRunRecordList(_ records: [MelixRunRecord]) -> String {
    guard !records.isEmpty else {
        return "No run records found.\n"
    }
    let rows = records.map { record in
        let summary = record.summaryPayload()
        return [
            record.runID,
            record.runKind,
            record.status,
            stringField(summary, "model_id", fallback: "-"),
            stringField(summary, "task_kind", fallback: "-"),
            suiteLabel(summary["suite_ids"]),
            stringField(summary, "dataset_id", fallback: "-"),
            String(record.startedAtUnixMS),
            stringField(summary, "artifact_root", fallback: "-"),
        ].joined(separator: "\t")
    }
    return ([
        "run_id\trun_kind\tstatus\tmodel_id\ttask_kind\tsuites\tdataset\tstarted_at_unix_ms\tartifact_root",
    ] + rows).joined(separator: "\n") + "\n"
}

func renderRunRecordMarkdown(_ record: MelixRunRecord) -> String {
    var lines: [String] = [
        "# Melix Run \(record.runID)",
        "",
        "## Environment",
        "- Platform: \(markdownInline(stringField(record.environment, "platform", fallback: "unknown")))",
        "- macOS: \(markdownInline(stringField(record.environment, "macos_version", fallback: "unknown")))",
        "- Machine: \(markdownInline(stringField(record.environment, "machine", fallback: "unknown")))",
        "- Processor: \(markdownInline(stringField(record.environment, "processor", fallback: "unknown")))",
        "",
        "## Target And Input",
        "- Run kind: \(markdownInline(record.runKind))",
        "- Status: \(markdownInline(record.status))",
        "- Model: \(markdownInline(stringField(record.target, "model_id", fallback: stringField(record.target, "base_model_id", fallback: "-"))))",
        "- Task: \(markdownInline(stringField(record.target, "task_kind", fallback: "-")))",
        "- Source: \(markdownInline(stringField(record.target, "source_repo", fallback: "-")))",
        "- Suites: \(markdownInline(suiteLabel(record.dataset["suite_ids"])))",
        "- Dataset: \(markdownInline(stringField(record.dataset, "dataset_id", fallback: stringField(record.dataset, "dataset_ref", fallback: "-"))))",
        "",
    ]
    lines.append(contentsOf: metricMarkdownLines(record.metrics))
    lines.append(contentsOf: [
        "",
        "## Reproduction Command",
        "```bash",
        record.commandDisplay,
        "```",
        "",
    ])
    lines.append(contentsOf: artifactMarkdownLines(record.artifacts))
    lines.append(contentsOf: knownGapMarkdownLines(record.knownGaps))
    return lines.joined(separator: "\n") + "\n"
}

func makeReportPayload(
    kind: String,
    records: [MelixRunRecord],
    scanMS: Double,
    markdownRenderMS: Double
) -> [String: Any] {
    let completed = records.filter { $0.status == "completed" }.count
    let failed = records.filter { $0.status == "failed" || $0.status == "error" }.count
    return [
        "schema_version": "melix.run_report.v1",
        "report_kind": kind,
        "generated_at_unix_ms": Int(Date().timeIntervalSince1970 * 1000),
        "run_count": records.count,
        "environment": records.map { environmentSummary($0) },
        "model_backend_matrix": records.map { modelBackendRow($0) },
        "dataset_task_matrix": records.map { datasetTaskRow($0) },
        "metrics": records.flatMap { metricRows($0) },
        "pass_fail_summary": [
            "completed": completed,
            "failed": failed,
            "other": max(records.count - completed - failed, 0),
        ],
        "reproduction_commands": records.map { ["run_id": $0.runID, "command": $0.commandDisplay] },
        "artifact_links": records.flatMap { artifactRows($0) },
        "known_gaps": records.flatMap { record in
            record.knownGaps.map { ["run_id": record.runID, "gap": $0] }
        },
        "report_generation": [
            "record_scan_ms": scanMS,
            "markdown_render_ms": markdownRenderMS,
        ],
    ]
}

func renderReportMarkdown(_ payload: [String: Any]) -> String {
    let kind = stringField(payload, "report_kind", fallback: "runs")
    var lines: [String] = [
        "# Melix \(kind == "benchmark" ? "Benchmark" : kind == "evaluation" ? "Evaluation" : "Run") Report",
        "",
        "## Environment",
    ]
    lines.append(contentsOf: tableLines(
        headers: ["Run", "Platform", "macOS", "Machine", "Processor"],
        rows: (payload["environment"] as? [[String: Any]] ?? []).map {
            [
                stringField($0, "run_id"),
                stringField($0, "platform"),
                stringField($0, "macos_version"),
                stringField($0, "machine"),
                stringField($0, "processor"),
            ]
        }
    ))
    lines.append(contentsOf: [
        "",
        "## Model/Backend Matrix",
    ])
    lines.append(contentsOf: tableLines(
        headers: ["Run", "Kind", "Model", "Source", "Task", "Runtime", "Status"],
        rows: (payload["model_backend_matrix"] as? [[String: Any]] ?? []).map {
            [
                stringField($0, "run_id"),
                stringField($0, "run_kind"),
                stringField($0, "model_id"),
                stringField($0, "source_repo"),
                stringField($0, "task_kind"),
                stringField($0, "runtime_backend"),
                stringField($0, "status"),
            ]
        }
    ))
    lines.append(contentsOf: [
        "",
        "## Dataset/Task Matrix",
    ])
    lines.append(contentsOf: tableLines(
        headers: ["Run", "Suites", "Dataset", "Sample Size", "Scoring"],
        rows: (payload["dataset_task_matrix"] as? [[String: Any]] ?? []).map {
            [
                stringField($0, "run_id"),
                stringField($0, "suite_ids"),
                stringField($0, "dataset_id"),
                stringField($0, "sample_size"),
                stringField($0, "scoring_mode"),
            ]
        }
    ))
    lines.append(contentsOf: [
        "",
        "## Metrics Table",
    ])
    lines.append(contentsOf: tableLines(
        headers: ["Run", "Metric", "Value", "Unit"],
        rows: (payload["metrics"] as? [[String: Any]] ?? []).map {
            [
                stringField($0, "run_id"),
                stringField($0, "name"),
                stringField($0, "value"),
                stringField($0, "unit"),
            ]
        }
    ))
    let summary = payload["pass_fail_summary"] as? [String: Any] ?? [:]
    lines.append(contentsOf: [
        "",
        "## Pass/Fail Summary",
        "- Completed: \(stringField(summary, "completed", fallback: "0"))",
        "- Failed: \(stringField(summary, "failed", fallback: "0"))",
        "- Other: \(stringField(summary, "other", fallback: "0"))",
        "",
        "## Reproduction Commands",
    ])
    for command in payload["reproduction_commands"] as? [[String: Any]] ?? [] {
        lines.append(contentsOf: [
            "### \(stringField(command, "run_id"))",
            "```bash",
            stringField(command, "command"),
            "```",
            "",
        ])
    }
    lines.append("## Artifact Links")
    lines.append(contentsOf: tableLines(
        headers: ["Run", "Kind", "Path"],
        rows: (payload["artifact_links"] as? [[String: Any]] ?? []).map {
            [
                stringField($0, "run_id"),
                stringField($0, "kind"),
                stringField($0, "path"),
            ]
        }
    ))
    lines.append(contentsOf: [
        "",
        "## Known Gaps",
    ])
    let gaps = payload["known_gaps"] as? [[String: Any]] ?? []
    let generation = payload["report_generation"] as? [String: Any] ?? [:]
    if gaps.isEmpty && generation.isEmpty {
        lines.append("- None.")
    } else {
        for gap in gaps {
            lines.append("- \(markdownInline(stringField(gap, "run_id"))): \(markdownInline(stringField(gap, "gap")))")
        }
    }
    if generation.isEmpty == false {
        let recordScanMS = stringField(generation, "record_scan_ms", fallback: "0")
        let markdownRenderMS = stringField(generation, "markdown_render_ms", fallback: "0")
        lines.append(
            "- Report generation probe: record_scan_ms=\(recordScanMS), markdown_render_ms=\(markdownRenderMS)."
        )
    }
    return lines.joined(separator: "\n") + "\n"
}

func runRecordJSONString(_ value: Any) throws -> String {
    let data = try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys])
    return (String(data: data, encoding: .utf8) ?? "") + "\n"
}

func writeRunRecordOutput(_ text: String, outputPath: String) throws -> String {
    let trimmed = outputPath.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
        return text
    }
    let url = URL(fileURLWithPath: (trimmed as NSString).expandingTildeInPath)
    try FileManager.default.createDirectory(
        at: url.deletingLastPathComponent(),
        withIntermediateDirectories: true,
        attributes: nil
    )
    try text.write(to: url, atomically: true, encoding: .utf8)
    return url.path + "\n"
}

private func environmentSummary(_ record: MelixRunRecord) -> [String: Any] {
    [
        "run_id": record.runID,
        "platform": stringField(record.environment, "platform"),
        "macos_version": stringField(record.environment, "macos_version"),
        "machine": stringField(record.environment, "machine"),
        "processor": stringField(record.environment, "processor"),
    ]
}

private func modelBackendRow(_ record: MelixRunRecord) -> [String: Any] {
    [
        "run_id": record.runID,
        "run_kind": record.runKind,
        "model_id": stringField(record.target, "model_id", fallback: stringField(record.target, "base_model_id")),
        "source_repo": stringField(record.target, "source_repo"),
        "task_kind": stringField(record.target, "task_kind"),
        "runtime_backend": stringField(record.target, "runtime_backend"),
        "status": record.status,
    ]
}

private func datasetTaskRow(_ record: MelixRunRecord) -> [String: Any] {
    [
        "run_id": record.runID,
        "suite_ids": suiteLabel(record.dataset["suite_ids"]),
        "dataset_id": stringField(record.dataset, "dataset_id", fallback: stringField(record.dataset, "dataset_ref")),
        "sample_size": stringField(record.dataset, "sample_size"),
        "scoring_mode": stringField(record.dataset, "scoring_mode"),
    ]
}

private func metricRows(_ record: MelixRunRecord) -> [[String: Any]] {
    record.metrics.map { metric in
        [
            "run_id": record.runID,
            "name": stringField(metric, "name"),
            "value": stringField(metric, "value"),
            "unit": stringField(metric, "unit"),
        ]
    }
}

private func artifactRows(_ record: MelixRunRecord) -> [[String: Any]] {
    record.artifacts.map { artifact in
        [
            "run_id": record.runID,
            "kind": stringField(artifact, "kind"),
            "path": stringField(artifact, "path"),
        ]
    }
}

private func metricMarkdownLines(_ metrics: [[String: Any]]) -> [String] {
    var lines = ["## Metrics"]
    lines.append(contentsOf: tableLines(
        headers: ["Metric", "Value", "Unit"],
        rows: metrics.map { [stringField($0, "name"), stringField($0, "value"), stringField($0, "unit")] }
    ))
    return lines
}

private func artifactMarkdownLines(_ artifacts: [[String: Any]]) -> [String] {
    var lines = ["## Artifact Links"]
    lines.append(contentsOf: tableLines(
        headers: ["Kind", "Path"],
        rows: artifacts.map { [stringField($0, "kind"), stringField($0, "path")] }
    ))
    return lines
}

private func knownGapMarkdownLines(_ gaps: [String]) -> [String] {
    var lines = ["", "## Known Gaps"]
    if gaps.isEmpty {
        lines.append("- None.")
    } else {
        lines.append(contentsOf: gaps.map { "- \(markdownInline($0))" })
    }
    return lines
}

private func tableLines(headers: [String], rows: [[String]]) -> [String] {
    guard !rows.isEmpty else {
        return ["No rows."]
    }
    let header = "| " + headers.map(markdownTableCell).joined(separator: " | ") + " |"
    let divider = "| " + headers.map { _ in "---" }.joined(separator: " | ") + " |"
    let body = rows.map { row in
        "| " + row.map(markdownTableCell).joined(separator: " | ") + " |"
    }
    return [header, divider] + body
}

private func suiteLabel(_ value: Any?) -> String {
    if let values = value as? [String] {
        return values.isEmpty ? "-" : values.joined(separator: ",")
    }
    if let values = value as? [Any] {
        let rendered = values.map { String(describing: $0) }.filter { !$0.isEmpty }
        return rendered.isEmpty ? "-" : rendered.joined(separator: ",")
    }
    let rendered = value.map { String(describing: $0) } ?? ""
    return rendered.isEmpty ? "-" : rendered
}

private func stringField(_ payload: [String: Any], _ key: String, fallback: String = "") -> String {
    guard let value = payload[key] else {
        return fallback
    }
    if let string = value as? String {
        return string.isEmpty ? fallback : string
    }
    if let values = value as? [String] {
        return values.isEmpty ? fallback : values.joined(separator: ",")
    }
    if let values = value as? [Any] {
        let rendered = values.map { String(describing: $0) }.filter { !$0.isEmpty }
        return rendered.isEmpty ? fallback : rendered.joined(separator: ",")
    }
    return String(describing: value)
}

private func markdownTableCell(_ value: String) -> String {
    markdownInline(value.isEmpty ? "-" : value)
        .replacingOccurrences(of: "|", with: "\\|")
        .replacingOccurrences(of: "\n", with: " ")
}

private func markdownInline(_ value: String) -> String {
    value.replacingOccurrences(of: "`", with: "\\`")
}
