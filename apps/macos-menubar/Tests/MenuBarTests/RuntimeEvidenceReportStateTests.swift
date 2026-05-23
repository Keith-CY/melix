import Foundation
import AppKit
import SwiftUI
import Testing

@testable import AppMain

@Suite("Runtime Evidence Report State", .serialized)
struct RuntimeEvidenceReportStateTests {
    @Test("decodes report json into operator evidence rows")
    func decodesReportJSONIntoOperatorEvidenceRows() throws {
        let report = try RuntimeEvidenceReportState.decode(json: makeStructuredEvidenceReportJSON())

        #expect(report.schemaVersion == "melix.benchmark_evaluation_report.v1")
        #expect(report.reportID == "report-desktop-fixture")
        #expect(report.summaryItems.map(\.id) == ["status", "gate", "runs", "evidence-validity", "hardware"])
        #expect(report.runRows.map(\.statusText).contains("Completed"))
        #expect(report.runRows.map(\.statusText).contains("Failed"))
        #expect(report.runRows.map(\.statusText).contains("Fallback"))
        #expect(report.metricRows.first?.resultText == "Fail")
        #expect(report.probeRows.contains { $0.kind == "Failed" && $0.phase == "Decode" })
        #expect(report.probeRows.contains { $0.kind == "Fallback" && $0.phase == "Fallback Enter" })
        #expect(report.probeRows.contains {
            $0.kind == "Skipped"
                && $0.phase == "Score Compute"
                && $0.durationText == "duration missing"
                && $0.detailText.contains("duration missing")
        })
        #expect(report.telemetryRows.contains { row in
            row.collectorStatusText == "Partial"
                && row.powerText.contains("17.50 W avg")
                && row.failureText.contains("powermetrics_failed")
        })
        #expect(report.evidenceValidityRows.contains {
            $0.id == "required_evidence_present" && $0.valueText == "1.0000"
        })
        #expect(report.requiredEvidenceRows.map(\.id) == [
            "required_evidence_present",
            "required_probe_phases_present",
            "required_telemetry_present",
        ])
        #expect(report.requiredEvidenceRows.allSatisfy { $0.statusText == "Present" })
        #expect(report.requiredEvidenceRows.contains {
            $0.title == "Required Telemetry"
                && $0.valueText == "1.0000"
                && $0.detailText.contains("required_telemetry_present")
        })
        #expect(report.summaryItems.first { $0.id == "evidence-validity" }?.value == "Present")
        #expect(report.processRows.contains { row in
            row.roleText == "Primary Runtime"
                && row.nameText == "mlx-runner"
                && row.resourceText.contains("CPU 12.5%")
        })
        #expect(report.metricRows(matching: "tokens").map(\.metric) == ["bench.smoke.tokens_per_second"])
        #expect(report.artifactRows(matching: "telemetry").map(\.path).contains("/tmp/telemetry_summary.csv"))
        #expect(report.markdownReportPath == "/tmp/report.md")
        #expect(report.csvArtifactRows.map(\.kindText).contains("Telemetry Summary"))
        #expect(report.artifactRows.contains { $0.kindText == "Markdown Report" })
        #expect(report.instrumentationGapRows.contains("candidate:candidate-failed:powermetrics_failed:fixture"))
    }

    @Test("decodes sparse report defaults into explicit operator gaps")
    func decodesSparseReportDefaultsIntoExplicitOperatorGaps() throws {
        let report = try RuntimeEvidenceReportState.decode(json: makeSparseStructuredEvidenceReportJSON())

        #expect(report.reportKindText == "Unknown")
        #expect(report.summaryItems.first?.value == "Unknown")
        #expect(report.summaryItems.first { $0.id == "evidence-validity" }?.value == "Missing")
        #expect(report.requiredEvidenceRows.map(\.statusText) == ["Missing", "Missing", "Missing"])
        #expect(report.metricRows.map(\.metric) == ["alpha.metric", "zeta.metric"])
        #expect(report.metricRows.first?.baselineText == "-")
        #expect(report.metricRows.first?.deltaText == "-")
        #expect(report.telemetryRows.first?.memoryText.contains("512 B") == true)
        #expect(report.telemetryRows.first?.powerText == "system power missing")
        #expect(report.telemetryRows.first?.utilizationText == "utilization telemetry missing")
        #expect(report.processRows.contains { row in
            row.roleText == "Worker 1"
                && row.nameText == "Unknown process"
                && row.resourceText.contains("512 B")
        })
        #expect(report.processRows.contains { $0.roleText == "External Provider" })
        #expect(report.runRows.first?.issueText.contains("details=1") == true)

        #expect(throws: RuntimeEvidenceReportDecodeError.self) {
            try RuntimeEvidenceReportState.decode(data: Data("{".utf8))
        }
    }

    @Test("diagnostics renders structured evidence report surfaces")
    @MainActor
    func diagnosticsRendersStructuredEvidenceReportSurfaces() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        let url = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-render-report-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: url) }
        try makeStructuredEvidenceReportJSON().write(to: url, atomically: true, encoding: .utf8)
        try await viewModel.loadEvidenceReport(from: url)
        viewModel.recordEvidenceReportOpenError("fixture open warning")

        let view = evidenceHostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 4200)
        )
        let renderedTexts = evidenceRenderedTextValues(in: view)

        #expect(renderedTexts.contains("Run Evidence Report"))
        #expect(renderedTexts.contains("Run History"))
        #expect(renderedTexts.contains("Runtime Diagnostics"))
        #expect(renderedTexts.contains("Hardware Monitor"))
        #expect(renderedTexts.contains("Evidence Artifacts"))
        #expect(renderedTexts.contains("Open CSV"))
        #expect(viewModel.evidenceReport?.markdownReportPath == "/tmp/report.md")
        #expect(viewModel.evidenceReport?.csvArtifactRows.isEmpty == false)
        #expect(renderedTexts.contains { $0.contains(url.lastPathComponent) })
        #expect(renderedTexts.contains("fixture open warning"))
        #expect(renderedTexts.contains { $0.contains("report-desktop-fixture") })
        #expect(renderedTexts.contains("Required Evidence Status"))
        #expect(renderedTexts.contains { $0.contains("Required Telemetry") && $0.contains("Present") })
        #expect(renderedTexts.contains { $0.contains("required_telemetry_present") && $0.contains("1.0000") })
        #expect(renderedTexts.contains("duration missing"))
        #expect(renderedTexts.contains("failure: failed=true, stage=decode"))
        #expect(renderedTexts.contains("fallback: fallback_count=1, fallbacks=1"))
        #expect(renderedTexts.contains { $0.contains("powermetrics_failed:fixture") })
        #expect(renderedTexts.contains { $0.contains("telemetry_summary.csv") })
    }

    @Test("diagnostics renders sparse telemetry gaps explicitly")
    @MainActor
    func diagnosticsRendersSparseTelemetryGapsExplicitly() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        try viewModel.loadEvidenceReport(json: makeSparseStructuredEvidenceReportJSON())

        let view = evidenceHostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 2600)
        )
        let renderedTexts = evidenceRenderedTextValues(in: view)

        #expect(renderedTexts.contains("Hardware Monitor"))
        #expect(renderedTexts.contains("system power missing"))
        #expect(renderedTexts.contains { $0.contains("utilization telemetry missing") && $0.contains("used 512 B") })
    }

    @Test("diagnostics renders debug bundle result state")
    @MainActor
    func diagnosticsRendersDebugBundleResultState() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.applyDiagnosticsDebugBundleResult(
            try RuntimeDiagnosticsDebugBundleState.decode(json: makeDiagnosticsDebugBundleJSON())
        )

        let view = evidenceHostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 2400)
        )
        let renderedTexts = evidenceRenderedTextValues(in: view)

        #expect(renderedTexts.contains("Debug Bundle"))
        #expect(renderedTexts.contains("Bundle Path"))
        #expect(renderedTexts.contains("/tmp/melix-debug/bench-1"))
        #expect(renderedTexts.contains("Manifest"))
        #expect(renderedTexts.contains("/tmp/melix-debug/bench-1/manifest.json"))
        #expect(renderedTexts.contains("Effective Config"))
        #expect(renderedTexts.contains("Debug bundle ready at /tmp/melix-debug/bench-1."))
    }

    @Test("diagnostics summarizes serving diagnostics queue retention and drops")
    @MainActor
    func diagnosticsSummarizesServingDiagnosticsQueueRetentionAndDrops() throws {
        let result = try RuntimeDiagnosticsDebugBundleState.decode(
            json: makeDiagnosticsDebugBundleJSON(
                servingDiagnosticsEventCount: 8,
                servingDiagnosticsDroppedEventCount: 24
            )
        )
        #expect(result.servingDiagnosticsQueueSummaryText == "8 retained / 24 dropped / 32 observed")
        #expect(result.servingDiagnosticsRetentionSummaryText == "debug mode retains up to 256 events")
        #expect(result.servingDiagnosticsDropSummaryText == "24 debug events were dropped; diagnosis may be partial.")
        #expect(result.mediaRouteReceipt?.mediaRoute == "swift_text")
        #expect(result.mediaRouteReceipt?.mediaPartsCount == 0)
        #expect(result.mediaRouteReceipt?.mediaTurnCount == 0)
        #expect(result.mediaRouteReceipt?.cacheHitCount == 0)
        #expect(result.mediaRouteReceipt?.cacheMissCount == 0)
        #expect(result.mediaRouteReceipt?.unsupportedReason == "none")

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.applyDiagnosticsDebugBundleResult(result)

        let view = evidenceHostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 2400)
        )
        let renderedTexts = evidenceRenderedTextValues(in: view)

        #expect(renderedTexts.contains("Serving Diagnostics Queue"))
        #expect(renderedTexts.contains("8 retained / 24 dropped / 32 observed"))
        #expect(renderedTexts.contains("Serving Diagnostics Retention"))
        #expect(renderedTexts.contains("debug mode retains up to 256 events"))
        #expect(renderedTexts.contains("Serving Diagnostics Drops"))
        #expect(renderedTexts.contains("24 debug events were dropped; diagnosis may be partial."))
    }

    @Test("diagnostics renders debug bundle redaction state")
    @MainActor
    func diagnosticsRendersDebugBundleRedactionState() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.applyDiagnosticsDebugBundleResult(
            try RuntimeDiagnosticsDebugBundleState.decode(json: makeDiagnosticsDebugBundleJSON())
        )

        let view = evidenceHostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: viewModel,
                foundation: viewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 2600)
        )
        let renderedTexts = evidenceRenderedTextValues(in: view)

        #expect(renderedTexts.contains("Redaction State"))
        #expect(renderedTexts.contains("Consent"))
        #expect(renderedTexts.contains("local_only"))
        #expect(renderedTexts.contains("Artifact Policy"))
        #expect(renderedTexts.contains("explicit_cli_command"))
        #expect(renderedTexts.contains("Debug JSONL"))
        #expect(renderedTexts.contains("enabled, limit 256 events"))
    }

    @Test("diagnostics debug bundle artifact helpers copy and open paths")
    @MainActor
    func diagnosticsDebugBundleArtifactHelpersCopyAndOpenPaths() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        let diagnosticsView = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        let pasteboard = RecordingPasteboard()

        #expect(RuntimeDiagnosticsArtifactClipboard.copy(" /tmp/melix-debug/bench-1/manifest.json ", to: pasteboard))
        #expect(pasteboard.string == "/tmp/melix-debug/bench-1/manifest.json")
        #expect(RuntimeDiagnosticsArtifactClipboard.copy("   ", to: pasteboard) == false)

        #expect(diagnosticsView.copyDebugBundleArtifactPath(" /tmp/melix-debug/bench-1/events.jsonl ", to: pasteboard))
        #expect(pasteboard.string == "/tmp/melix-debug/bench-1/events.jsonl")
        #expect(viewModel.diagnosticsDebugBundleMessage == "Copied debug bundle artifact path: /tmp/melix-debug/bench-1/events.jsonl.")
        #expect(viewModel.diagnosticsDebugBundleErrorMessage.isEmpty)

        #expect(diagnosticsView.copyDebugBundleArtifactPath(
            "/tmp/melix-debug/bench-1/failing-artifact.json",
            to: pasteboard,
            clipboardWriter: { _, _ in false }
        ) == false)
        #expect(viewModel.diagnosticsDebugBundleErrorMessage.contains("Could not copy"))

        var openedURL: URL?
        diagnosticsView.openDebugBundleArtifact(path: " /tmp/melix-debug/bench-1/events.jsonl ") { url in
            openedURL = url
            return true
        }
        #expect(openedURL?.path == "/tmp/melix-debug/bench-1/events.jsonl")
        #expect(viewModel.diagnosticsDebugBundleMessage == "Opened debug bundle artifact: /tmp/melix-debug/bench-1/events.jsonl.")
        #expect(viewModel.diagnosticsDebugBundleErrorMessage.isEmpty)

        #expect(diagnosticsView.copyDebugBundleArtifactPath("   ", to: pasteboard) == false)
        #expect(viewModel.diagnosticsDebugBundleErrorMessage.contains("empty"))

        diagnosticsView.openDebugBundleArtifact(path: "   ") { _ in true }
        #expect(viewModel.diagnosticsDebugBundleErrorMessage.contains("empty"))

        diagnosticsView.openDebugBundleArtifact(path: "/tmp/missing-debug-artifact.json") { _ in false }
        #expect(viewModel.diagnosticsDebugBundleErrorMessage.contains("Could not open"))

        let unknownLimitJSON = makeDiagnosticsDebugBundleJSON()
            .replacingOccurrences(
                of: #""debug_jsonl_event_limit": 256"#,
                with: #""debug_jsonl_event_limit": 0"#
            )
        let unknownLimitResult = try RuntimeDiagnosticsDebugBundleState.decode(json: unknownLimitJSON)
        #expect(unknownLimitResult.debugJSONLSummaryText == "enabled, limit unknown")
    }

    @Test("diagnostics renders debug bundle error state")
    @MainActor
    func diagnosticsRendersDebugBundleErrorState() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.updateDiagnosticsDebugBundleRunIDDraft("bench-missing-runner")
        let diagnosticsView = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        await diagnosticsView.createDebugBundle()

        let view = evidenceHostView(diagnosticsView, size: CGSize(width: 1280, height: 2000))
        let renderedTexts = evidenceRenderedTextValues(in: view)

        #expect(renderedTexts.contains("Debug Bundle"))
        #expect(renderedTexts.contains("Diagnostics CLI runner is unavailable."))
    }

    @Test("view model loads clears and records evidence report errors")
    @MainActor
    func viewModelLoadsClearsAndRecordsEvidenceReportErrors() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        let url = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-evidence-report-\(UUID().uuidString).json")
        defer { try? FileManager.default.removeItem(at: url) }

        try makeStructuredEvidenceReportJSON().write(to: url, atomically: true, encoding: .utf8)
        try await viewModel.loadEvidenceReport(from: url)

        #expect(viewModel.evidenceReport?.reportID == "report-desktop-fixture")
        #expect(viewModel.evidenceReportSourcePath == url.path)

        viewModel.recordEvidenceReportOpenError("fixture open failure")
        #expect(viewModel.evidenceReportOpenError == "fixture open failure")

        viewModel.clearEvidenceReportOpenError()
        #expect(viewModel.evidenceReportOpenError.isEmpty)

        viewModel.clearEvidenceReport()
        #expect(viewModel.evidenceReport == nil)
        #expect(viewModel.evidenceReportSourcePath.isEmpty)

        viewModel.recordEvidenceReportLoadError(RuntimeEvidenceReportDecodeError.invalidJSON("fixture decode failure"))
        #expect(viewModel.evidenceReportLoadError.contains("fixture decode failure"))
    }

    @Test("diagnostics artifact helper opens paths and reports failures")
    @MainActor
    func diagnosticsArtifactHelperOpensPathsAndReportsFailures() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        let validURL = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-helper-report-\(UUID().uuidString).json")
        let invalidURL = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("melix-helper-report-invalid-\(UUID().uuidString).json")
        defer {
            try? FileManager.default.removeItem(at: validURL)
            try? FileManager.default.removeItem(at: invalidURL)
        }

        try makeStructuredEvidenceReportJSON().write(to: validURL, atomically: true, encoding: .utf8)
        try "{".write(to: invalidURL, atomically: true, encoding: .utf8)

        let diagnosticsView = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        try await viewModel.loadEvidenceReport(from: validURL)
        #expect(viewModel.evidenceReport?.reportID == "report-desktop-fixture")
        #expect(viewModel.evidenceReportSourcePath == validURL.path)

        var openedURL: URL?
        diagnosticsView.openEvidenceArtifact(path: " /tmp/report.md ") { url in
            openedURL = url
            return true
        }
        #expect(openedURL?.path == "/tmp/report.md")
        #expect(viewModel.evidenceReportOpenError.isEmpty)

        diagnosticsView.openEvidenceArtifact(path: " ") { _ in true }
        #expect(viewModel.evidenceReportOpenError.contains("empty"))

        diagnosticsView.openEvidenceArtifact(path: "/tmp/missing-report.md") { _ in false }
        #expect(viewModel.evidenceReportOpenError.contains("Could not open"))

        do {
            try await viewModel.loadEvidenceReport(from: invalidURL)
        } catch {
            viewModel.recordEvidenceReportLoadError(error)
        }
        #expect(viewModel.evidenceReportLoadError.contains("could not be decoded"))

        viewModel.clearEvidenceReport()
        #expect(viewModel.evidenceReport == nil)
        #expect(viewModel.evidenceReportLoadError.isEmpty)
        #expect(viewModel.evidenceReportOpenError.isEmpty)
    }

    @Test("diagnostics renders empty and failed evidence report states")
    @MainActor
    func diagnosticsRendersEmptyAndFailedEvidenceReportStates() throws {
        let emptyViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        emptyViewModel.selectSurface(.tools)
        emptyViewModel.selectToolSection(.diagnostics)
        try emptyViewModel.loadEvidenceReport(json: makeEmptyStructuredEvidenceReportJSON())

        let emptyView = evidenceHostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: emptyViewModel,
                foundation: emptyViewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 2600)
        )
        let emptyTexts = evidenceRenderedTextValues(in: emptyView)

        #expect(emptyTexts.contains("Run History"))
        #expect(emptyTexts.contains("Runtime Diagnostics"))
        #expect(emptyTexts.contains("Hardware Monitor"))
        #expect(emptyTexts.contains("Evidence Artifacts"))
        #expect(emptyTexts.contains("run_evidence_missing"))

        let failedViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        failedViewModel.recordEvidenceReportLoadError(
            RuntimeEvidenceReportDecodeError.invalidJSON("fixture decode failure")
        )
        let failedView = evidenceHostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: failedViewModel,
                foundation: failedViewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 1000)
        )
        let failedTexts = evidenceRenderedTextValues(in: failedView)

        #expect(failedTexts.contains("Run Evidence Report"))

        failedViewModel.clearEvidenceReport()
        let noReportView = evidenceHostView(
            DesktopDiagnosticsToolSectionView(
                viewModel: failedViewModel,
                foundation: failedViewModel.desktopFoundationState
            ),
            size: CGSize(width: 1280, height: 1000)
        )
        let noReportTexts = evidenceRenderedTextValues(in: noReportView)

        #expect(noReportTexts.contains("Run Evidence Report"))
    }
}

@MainActor
private func evidenceHostView<Content: View>(_ rootView: Content, size: CGSize) -> NSView {
    let controller = NSHostingController(rootView: rootView)
    let view = controller.view
    view.frame = NSRect(origin: .zero, size: size)
    view.layoutSubtreeIfNeeded()
    return view
}

@MainActor
private func evidenceRenderedTextValues(in rootView: NSView) -> [String] {
    var values: [String] = []

    func appendValue(_ value: String) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty == false {
            values.append(trimmed)
        }
    }

    func visit(_ view: NSView) {
        if let textField = view as? NSTextField {
            appendValue(textField.stringValue)
        }
        if let button = view as? NSButton {
            appendValue(button.title)
        }
        if let popup = view as? NSPopUpButton {
            appendValue(popup.title)
        }
        if let segmented = view as? NSSegmentedControl {
            for index in 0..<segmented.segmentCount {
                appendValue(segmented.label(forSegment: index) ?? "")
            }
        }
        for subview in view.subviews {
            visit(subview)
        }
    }

    visit(rootView)
    return values
}

private func makeSparseStructuredEvidenceReportJSON() -> String {
    #"""
    {
      "schema_version": "melix.benchmark_evaluation_report.v1",
      "report_id": "report-sparse-fixture",
      "generated_at": "2026-05-08T13:00:00Z",
      "melix_commit": "abc",
      "git_branch": "",
      "dirty_worktree": true,
      "source_evidence_ids": [],
      "runs": [
        {
          "side": "baseline",
          "run_id": "sparse-run",
          "trace_id": "sparse-run:trace",
          "run_kind": "",
          "status": "",
          "duration_ms": 5,
          "artifact_root": "",
          "failure_summary": {"details": {"code": "missing"}},
          "fallback_summary": {"fallback_count": 0}
        }
      ],
      "metrics": [
        {
          "metric": "zeta.metric",
          "direction": "",
          "status": "",
          "result": "unknown_result"
        },
        {
          "metric": "alpha.metric",
          "direction": "",
          "status": "",
          "result": "unknown_result"
        }
      ],
      "telemetry_summary": {
        "baseline": [
          {
            "run_id": "sparse-run",
            "collector_status": "unsupported",
            "telemetry_failures": ["missing_powermetrics"],
            "memory_used_bytes": 512
          }
        ],
        "candidate": []
      },
      "process_attribution": {
        "baseline": [
          {
            "run_id": "sparse-run",
            "worker_processes": [
              {
                "pid": 301,
                "name": "",
                "role": "",
                "peak_memory_bytes": 512,
                "avg_cpu_percent": 0.0,
                "sample_count": 0
              }
            ],
            "external_provider_processes": [
              {
                "pid": 302,
                "name": "remote-provider",
                "role": "external_provider"
              }
            ]
          }
        ],
        "candidate": []
      }
    }
    """#
}

private func makeStructuredEvidenceReportJSON() -> String {
    #"""
    {
      "schema_version": "melix.benchmark_evaluation_report.v1",
      "report_id": "report-desktop-fixture",
      "generated_at": "2026-05-08T12:00:00Z",
      "generator_name": "worker.productization.benchmark_evaluation_report",
      "generator_version": "2026-05-08.plan4",
      "melix_commit": "abcdef1234567890",
      "git_branch": "codex/report-json-export",
      "dirty_worktree": false,
      "source_evidence_ids": ["baseline-completed", "candidate-failed", "candidate-fallback"],
      "report_kind": "comparison",
      "summary": {
        "status": "warning",
        "metric_count": 3,
        "warning_count": 1,
        "missing_count": 1,
        "not_comparable_count": 0
      },
      "runs": [
        {
          "side": "baseline",
          "run_id": "baseline-completed",
          "trace_id": "baseline-completed:trace",
          "run_kind": "benchmark",
          "status": "completed",
          "started_at": 1779000000000,
          "ended_at": 1779000001200,
          "duration_ms": 1200,
          "command": "melix bench",
          "operator": "desktop",
          "artifact_root": "/tmp/baseline-completed",
          "failure_summary": {"failed": false},
          "fallback_summary": {"fallback_count": 0}
        },
        {
          "side": "candidate",
          "run_id": "candidate-failed",
          "trace_id": "candidate-failed:trace",
          "run_kind": "evaluation",
          "status": "failed",
          "started_at": 1779000000000,
          "ended_at": 1779000002400,
          "duration_ms": 2400,
          "command": "melix eval",
          "operator": "desktop",
          "artifact_root": "/tmp/candidate-failed",
          "failure_summary": {"failed": true, "stage": "decode"},
          "fallback_summary": {"fallback_count": 0}
        },
        {
          "side": "candidate",
          "run_id": "candidate-fallback",
          "trace_id": "candidate-fallback:trace",
          "run_kind": "benchmark",
          "status": "fallback",
          "started_at": 1779000000000,
          "ended_at": 1779000001800,
          "duration_ms": 1800,
          "command": "melix bench",
          "operator": "desktop",
          "artifact_root": "/tmp/candidate-fallback",
          "failure_summary": {"failed": false},
          "fallback_summary": {"fallback_count": 1, "fallbacks": ["provider_retry"]}
        }
      ],
      "targets": [
        {
          "side": "baseline",
          "run_id": "baseline-completed",
          "target_model_id": "mlx-community/test-model",
          "hf_repo_id": "mlx-community/test-model",
          "task_kind": "text-generation",
          "model_snapshot": "model-sha",
          "adapter_id": "",
          "adapter_snapshot": "",
          "runtime_kind": "mlx",
          "runtime_config": {},
          "dataset_ref": "fixture.dataset",
          "dataset_revision": "dataset-sha",
          "suite_id": "smoke",
          "sample_count": 1,
          "input_digest": "input-sha",
          "prompt_template_digest": "prompt-sha",
          "generation_config": {}
        },
        {
          "side": "candidate",
          "run_id": "candidate-failed",
          "target_model_id": "mlx-community/test-model",
          "hf_repo_id": "mlx-community/test-model",
          "task_kind": "event-extraction",
          "model_snapshot": "model-sha",
          "adapter_id": "adapter-a",
          "adapter_snapshot": "adapter-sha",
          "runtime_kind": "mlx",
          "runtime_config": {},
          "dataset_ref": "fixture.dataset",
          "dataset_revision": "dataset-sha",
          "suite_id": "event_extraction",
          "sample_count": 1,
          "input_digest": "input-sha",
          "prompt_template_digest": "prompt-sha",
          "generation_config": {}
        },
        {
          "side": "candidate",
          "run_id": "candidate-fallback",
          "target_model_id": "mlx-community/test-model",
          "hf_repo_id": "mlx-community/test-model",
          "task_kind": "text-generation",
          "model_snapshot": "model-sha",
          "adapter_id": "",
          "adapter_snapshot": "",
          "runtime_kind": "mlx",
          "runtime_config": {},
          "dataset_ref": "fixture.dataset",
          "dataset_revision": "dataset-sha",
          "suite_id": "smoke",
          "sample_count": 1,
          "input_digest": "input-sha",
          "prompt_template_digest": "prompt-sha",
          "generation_config": {}
        }
      ],
      "metrics": [
        {
          "metric": "bench.smoke.decode_ms",
          "baseline": 10.0,
          "current": 12.0,
          "candidate": 12.0,
          "delta": 2.0,
          "delta_percent": 20.0,
          "delta_pct": 20.0,
          "direction": "lower_is_better",
          "status": "warning",
          "gate_policy": {"direction": "lower_is_better", "warning_threshold_pct": 5.0, "required": true},
          "result": "fail"
        },
        {
          "metric": "eval.event_extraction.failure_count",
          "baseline": 0.0,
          "current": 1.0,
          "candidate": 1.0,
          "delta": 1.0,
          "delta_percent": 100.0,
          "delta_pct": 100.0,
          "direction": "lower_is_better",
          "status": "missing",
          "gate_policy": {"direction": "lower_is_better", "warning_threshold_pct": 5.0, "required": true},
          "result": "informational"
        },
        {
          "metric": "bench.smoke.tokens_per_second",
          "baseline": 50.0,
          "current": 55.0,
          "candidate": 55.0,
          "delta": 5.0,
          "delta_percent": 10.0,
          "delta_pct": 10.0,
          "direction": "higher_is_better",
          "status": "ok",
          "gate_policy": {"direction": "higher_is_better", "warning_threshold_pct": 5.0, "required": true},
          "result": "pass"
        }
      ],
      "probe_summary": {
        "baseline": {
          "schema_version": "melix.probe_summary.v1",
          "probe_count": 2,
          "component_duration_ms": {"runtime": 9.0},
          "slowest_phases": [
            {
              "run_id": "baseline-completed",
              "trace_id": "baseline-completed:trace",
              "span_id": "baseline-completed:decode",
              "parent_span_id": "baseline-completed:prefill",
              "component": "runtime",
              "phase": "decode",
              "duration_ms": 9.0,
              "status": "completed",
              "error_stage": "",
              "error_code": ""
            }
          ],
          "failed_phases": [],
          "skipped_phases": [],
          "fallback_phases": []
        },
        "candidate": {
          "schema_version": "melix.probe_summary.v1",
          "probe_count": 3,
          "component_duration_ms": {"runtime": 17.5},
          "slowest_phases": [
            {
              "run_id": "candidate-failed",
              "trace_id": "candidate-failed:trace",
              "span_id": "candidate-failed:decode",
              "parent_span_id": "candidate-failed:prefill",
              "component": "runtime",
              "phase": "decode",
              "duration_ms": 17.5,
              "status": "failed",
              "error_stage": "decode",
              "error_code": "runtime_error"
            }
          ],
          "failed_phases": [
            {
              "run_id": "candidate-failed",
              "trace_id": "candidate-failed:trace",
              "span_id": "candidate-failed:decode",
              "parent_span_id": "candidate-failed:prefill",
              "component": "runtime",
              "phase": "decode",
              "duration_ms": 17.5,
              "status": "failed",
              "error_stage": "decode",
              "error_code": "runtime_error"
            }
          ],
          "skipped_phases": [
            {
              "run_id": "candidate-failed",
              "trace_id": "candidate-failed:trace",
              "span_id": "candidate-failed:score",
              "parent_span_id": "candidate-failed:decode",
              "component": "worker",
              "phase": "score_compute",
              "duration_ms": 0.0,
              "status": "skipped",
              "error_stage": "",
              "error_code": ""
            }
          ],
          "fallback_phases": [
            {
              "run_id": "candidate-fallback",
              "trace_id": "candidate-fallback:trace",
              "span_id": "candidate-fallback:fallback_enter",
              "parent_span_id": "candidate-fallback:dispatch",
              "component": "runtime",
              "phase": "fallback_enter",
              "duration_ms": 0.001,
              "status": "completed",
              "error_stage": "",
              "error_code": ""
            }
          ]
        }
      },
      "telemetry_summary": {
        "hardware_banner": "Apple Silicon / macOS telemetry",
        "baseline": [
          {
            "side": "baseline",
            "run_id": "baseline-completed",
            "run_kind": "benchmark",
            "collector_status": "collected",
            "time_series_path": "/tmp/baseline/telemetry-samples.jsonl",
            "telemetry_failures": [],
            "average_cpu_utilization_percent": 42.0,
            "average_gpu_utilization_percent": 55.0,
            "average_gpu_frequency_mhz": 900.0,
            "average_system_power_w": 14.5,
            "peak_system_power_w": 16.0,
            "memory_used_bytes": 1073741824,
            "memory_total_bytes": 34359738368,
            "peak_process_memory_bytes": 536870912
          }
        ],
        "candidate": [
          {
            "side": "candidate",
            "run_id": "candidate-failed",
            "run_kind": "evaluation",
            "collector_status": "partial",
            "time_series_path": "/tmp/candidate/telemetry-samples.jsonl",
            "telemetry_failures": ["powermetrics_failed:fixture"],
            "average_cpu_utilization_percent": 48.0,
            "average_gpu_utilization_percent": 61.0,
            "average_gpu_frequency_mhz": 980.0,
            "average_system_power_w": 17.5,
            "peak_system_power_w": 19.0,
            "memory_used_bytes": 2147483648,
            "memory_total_bytes": 34359738368,
            "peak_process_memory_bytes": 805306368
          }
        ]
      },
      "process_attribution": {
        "baseline": [],
        "candidate": [
          {
            "side": "candidate",
            "run_id": "candidate-failed",
            "run_kind": "evaluation",
            "primary_runtime_process": {
              "pid": 101,
              "name": "mlx-runner",
              "role": "primary_runtime",
              "port": 12434,
              "peak_memory_bytes": 805306368,
              "avg_cpu_percent": 12.5,
              "sample_count": 4
            },
            "control_plane_process": {
              "pid": 102,
              "name": "melix-control",
              "role": "control_plane",
              "port": 11434,
              "peak_memory_bytes": 134217728,
              "avg_cpu_percent": 2.5,
              "sample_count": 4
            },
            "worker_processes": [
              {
                "pid": 103,
                "name": "melix-worker",
                "role": "worker",
                "port": 0,
                "peak_memory_bytes": 268435456,
                "avg_cpu_percent": 4.5,
                "sample_count": 4
              }
            ],
            "external_provider_processes": [],
            "process_tree_summary": {"roles": ["primary_runtime", "control_plane", "worker"]}
          }
        ]
      },
      "comparison": {
        "baseline_report_id": "baseline-completed",
        "current_report_id": "candidate-failed",
        "comparison_dimensions": [],
        "metric_deltas": [],
        "probe_deltas": [],
        "telemetry_deltas": [],
        "regressions": [],
        "improvements": [],
        "unchanged": [],
        "comparison_validity": "valid"
      },
      "gate_result": {
        "overall_result": "fail",
        "gate_results": [],
        "informational_results": [
          {
            "metric": "eval.event_extraction.failure_count",
            "baseline": 0.0,
            "current": 1.0,
            "delta": 1.0,
            "delta_percent": 100.0,
            "direction": "lower_is_better",
            "status": "missing",
            "gate_policy": {"direction": "lower_is_better", "warning_threshold_pct": 5.0, "required": true},
            "result": "informational"
          }
        ],
        "known_gaps": [],
        "blocking_failures": [
          {
            "metric": "bench.smoke.decode_ms",
            "baseline": 10.0,
            "current": 12.0,
            "delta": 2.0,
            "delta_percent": 20.0,
            "direction": "lower_is_better",
            "status": "warning",
            "gate_policy": {"direction": "lower_is_better", "warning_threshold_pct": 5.0, "required": true},
            "result": "fail"
          }
        ],
        "required_evidence_present": true,
        "required_probe_phases_present": true,
        "required_telemetry_present": true,
        "evidence_validity_metrics": {
          "source_evidence_count": 2.0,
          "required_evidence_present": 1.0,
          "required_probe_phases_present": 1.0,
          "required_telemetry_present": 1.0,
          "known_gap_count": 0.0,
          "blocking_failure_count": 1.0
        }
      },
      "artifacts": {
        "evidence_json_path": "/tmp/evidence.json",
        "report_json_path": "/tmp/report.json",
        "markdown_report_path": "/tmp/report.md",
        "csv_export_paths": {
          "runs": "/tmp/runs.csv",
          "metrics": "/tmp/metrics.csv",
          "telemetry_summary": "/tmp/telemetry_summary.csv",
          "processes": "/tmp/processes.csv"
        },
        "probe_timeline_path": "/tmp/probes.jsonl",
        "telemetry_jsonl_path": "/tmp/telemetry-samples.jsonl",
        "raw_output_paths": ["/tmp/baseline-completed", "/tmp/candidate-failed"],
        "logs_path": "/tmp/logs",
        "screenshots_path": "",
        "coverage_path": "/tmp/coverage"
      },
      "known_gaps": [],
      "instrumentation_gaps": ["candidate:candidate-failed:powermetrics_failed:fixture"],
      "operator_notes": [],
      "non_blocking_warnings": ["candidate:candidate-failed:powermetrics_failed:fixture"],
      "rows": []
    }
    """#
}

private func makeEmptyStructuredEvidenceReportJSON() -> String {
    #"""
    {
      "schema_version": "melix.benchmark_evaluation_report.v1",
      "report_id": "report-empty-fixture",
      "generated_at": "2026-05-08T12:30:00Z",
      "generator_name": "worker.productization.benchmark_evaluation_report",
      "generator_version": "2026-05-08.plan4",
      "melix_commit": "abcdef1234567890",
      "git_branch": "codex/report-json-export",
      "dirty_worktree": false,
      "source_evidence_ids": [],
      "report_kind": "comparison",
      "summary": {
        "status": "missing",
        "metric_count": 0,
        "warning_count": 0,
        "missing_count": 0,
        "not_comparable_count": 0
      },
      "runs": [],
      "targets": [],
      "metrics": [],
      "probe_summary": {
        "baseline": {
          "schema_version": "melix.probe_summary.v1",
          "probe_count": 0,
          "component_duration_ms": {},
          "slowest_phases": [],
          "failed_phases": [],
          "skipped_phases": [],
          "fallback_phases": []
        },
        "candidate": {
          "schema_version": "melix.probe_summary.v1",
          "probe_count": 0,
          "component_duration_ms": {},
          "slowest_phases": [],
          "failed_phases": [],
          "skipped_phases": [],
          "fallback_phases": []
        }
      },
      "telemetry_summary": {
        "hardware_banner": "Apple Silicon / macOS telemetry",
        "baseline": [],
        "candidate": []
      },
      "process_attribution": {
        "baseline": [],
        "candidate": []
      },
      "comparison": {
        "baseline_report_id": "",
        "current_report_id": "",
        "comparison_dimensions": [],
        "metric_deltas": [],
        "probe_deltas": [],
        "telemetry_deltas": [],
        "regressions": [],
        "improvements": [],
        "unchanged": [],
        "comparison_validity": "partial"
      },
      "gate_result": {
        "overall_result": "informational",
        "gate_results": [],
        "informational_results": [],
        "known_gaps": ["run_evidence_missing"],
        "blocking_failures": [],
        "required_evidence_present": false,
        "required_probe_phases_present": false,
        "required_telemetry_present": false,
        "evidence_validity_metrics": {
          "required_evidence_present": 0.0,
          "required_probe_phases_present": 0.0,
          "required_telemetry_present": 0.0
        }
      },
      "artifacts": {
        "evidence_json_path": "",
        "report_json_path": "",
        "markdown_report_path": "",
        "csv_export_paths": {},
        "probe_timeline_path": "",
        "telemetry_jsonl_path": "",
        "raw_output_paths": [],
        "logs_path": "",
        "screenshots_path": "",
        "coverage_path": ""
      },
      "known_gaps": ["run_evidence_missing"],
      "instrumentation_gaps": [],
      "operator_notes": [],
      "non_blocking_warnings": [],
      "rows": []
    }
    """#
}
