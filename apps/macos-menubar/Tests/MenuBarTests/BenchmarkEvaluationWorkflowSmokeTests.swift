import AppKit
import Foundation
import SwiftUI
import Testing

@testable import AppMain
import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Benchmark Evaluation Workflow Smoke", .serialized)
struct BenchmarkEvaluationWorkflowSmokeTests {
    @Test("diagnostics benchmark matrix evaluation workflow succeeds through the shared cli seam")
    @MainActor
    func diagnosticsWorkflowSucceedsThroughSharedCLISeam() async throws {
        let directClient = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        var derivedModel = ModelCatalog.devTextModel()
        derivedModel.modelID = "melix-dev-text-lora"
        snapshot.models = [ModelCatalog.devTextModel(), derivedModel]
        await directClient.configureSnapshot(snapshot)
        let runnerClient = FakeControlPlaneXPCClient()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-workflow-smoke-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        await runnerClient.configureBenchResponse(
            ControlPlaneBenchResult(
                reportPath: "/tmp/melix/bench/runs/bench-newer/bench-report.md",
                reportMarkdown: "# Melix Bench\n",
                metrics: [
                    "bench.smoke.ttft_ms": 21.10,
                    "bench.smoke.tokens_per_second": 61.20,
                ]
            )
        )
        await runnerClient.configureBenchMatrixResponse(
            ControlPlaneBenchMatrixResult(
                job: {
                    var job = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
                    job.jobID = "matrix-newer"
                    job.modelID = "melix-dev-text-lora"
                    job.taskKind = "text-generation"
                    job.suiteIds = ["smoke", "latency"]
                    job.status = "completed"
                    job.outputDir = "/tmp/melix/bench/matrix-runs/matrix-newer"
                    return job
                }(),
                summaryRows: []
            )
        )
        await runnerClient.configureEvaluationResponse(
            ControlPlaneEvaluationResult(
                job: {
                    var job = Melix_Controlplane_V1_EvaluationJobSummary()
                    job.jobID = "eval-newer"
                    job.modelID = "melix-dev-text-lora"
                    job.taskKind = "text-generation"
                    job.sourceRepo = "cais/mmlu"
                    job.suiteID = "mmlu"
                    job.datasetID = "mmlu.dev.v1"
                    job.sampleSize = 8
                    job.scoringMode = "multiple_choice_accuracy"
                    job.status = "completed"
                    job.outputDir = "/tmp/melix/evaluation/runs/eval-newer"
                    return job
                }(),
                results: []
            )
        )
        await runnerClient.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        let runner = MelixCLIRunner(
            client: runnerClient,
            environment: ["MELIX_HOME": temporaryRoot.path],
            operatorSessionStore: MelixOperatorSessionStore(
                melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
            )
        )
        let viewModel = RuntimeViewModel(
            client: directClient,
            operatorCommandRunner: runner
        )

        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedBenchmarkModelID = "melix-dev-text-lora"
        viewModel.selectedBenchmarkSuiteIDs = ["smoke", "latency"]
        viewModel.selectedEvaluationModelID = "melix-dev-text-lora"
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]

        let initialView = hostWorkflowView(DesktopWorkspaceShellView(viewModel: viewModel))
        #expect(initialView.subviews.isEmpty == false)

        await viewModel.runBench()
        await viewModel.exportSelectedBenchmarkCSV()

        viewModel.selectedBenchmarkPresentationMode = .matrix
        viewModel.selectedBenchmarkMatrixLoadBudgetMode = .requests
        viewModel.benchMatrixRequests = "12"
        await viewModel.runBenchMatrix()
        await viewModel.exportSelectedBenchmarkMatrixSummaryCSV()

        await viewModel.runEvaluation()
        await viewModel.exportSelectedEvaluationSamplesJSONL()

        let finalView = hostWorkflowView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = workflowRenderedTextValues(in: finalView)

        #expect(finalView.subviews.isEmpty == false)
        #expect(renderedTexts.contains("Matrix"))
        #expect(renderedTexts.contains("Requests"))
        #expect(renderedTexts.contains("multiple_choice_accuracy"))
        #expect(renderedTexts.contains("sandboxed"))
        #expect(renderedTexts.contains(where: { $0.contains("Matrix summary.csv exported:") }))
        #expect(renderedTexts.contains(where: { $0.contains("Evaluation export (samples.jsonl):") }))
        #expect(viewModel.benchmarkHistory.isEmpty == false)
        #expect(viewModel.benchmarkChartPoints.isEmpty == false)
        #expect(viewModel.benchmarkMatrixHistory.isEmpty == false)
        #expect(viewModel.benchmarkMatrixSummaryRows.isEmpty == false)
        #expect(viewModel.evaluationHistory.isEmpty == false)
        #expect(viewModel.evaluationSamplePreview.isEmpty == false)
        #expect(FileManager.default.fileExists(atPath: try #require(viewModel.lastBenchmarkCSVExport).outputPath))
        #expect(FileManager.default.fileExists(atPath: try #require(viewModel.lastBenchmarkMatrixExport).outputPath))
        #expect(FileManager.default.fileExists(atPath: try #require(viewModel.lastEvaluationExport).outputPath))
        #expect(await directClient.recordedBenchRequests.isEmpty)
        #expect(await directClient.recordedBenchMatrixRequests.isEmpty)
        #expect(await directClient.recordedEvaluationRequests.isEmpty)
        #expect(await directClient.recordedExportOutputDirs.isEmpty)
        #expect(await runnerClient.recordedBenchRequests.isEmpty == false)
        #expect(await runnerClient.recordedBenchMatrixRequests.isEmpty == false)
        #expect(await runnerClient.recordedEvaluationRequests.isEmpty == false)
        #expect(await runnerClient.recordedExportOutputDirs.isEmpty == false)
    }

    @Test("diagnostics benchmark matrix evaluation workflow renders negative cli states")
    @MainActor
    func diagnosticsWorkflowRendersNegativeCLIStates() async throws {
        let directClient = FakeControlPlaneXPCClient()
        var snapshot = Melix_Controlplane_V1_ServerSnapshot()
        snapshot.serverState = .serverReady
        snapshot.models = [ModelCatalog.devTextModel()]
        await directClient.configureSnapshot(snapshot)
        let runnerClient = FakeControlPlaneXPCClient()
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-workflow-negative-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let runner = MelixCLIRunner(
            client: runnerClient,
            environment: ["MELIX_HOME": temporaryRoot.path],
            operatorSessionStore: MelixOperatorSessionStore(
                melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
            )
        )
        let viewModel = RuntimeViewModel(
            client: directClient,
            operatorCommandRunner: runner
        )

        await viewModel.start()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedBenchmarkModelID = "melix-dev-text"
        viewModel.selectedBenchmarkSuiteIDs = ["smoke"]
        viewModel.selectedEvaluationModelID = "melix-dev-text"
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]

        viewModel.selectedBenchmarkPresentationMode = .matrix
        viewModel.selectedBenchmarkMatrixLoadBudgetMode = .requests
        viewModel.benchMatrixRequests = "0"
        await viewModel.runBenchMatrix()
        #expect(viewModel.lastError == "Set a positive requests value before running Matrix.")

        await runnerClient.configureErrors(bench: MenuBarTestError(description: "benchmark exploded"))
        viewModel.selectedBenchmarkPresentationMode = .standard
        await viewModel.runBench()
        #expect(viewModel.lastError == "benchmark exploded")

        await runnerClient.configureErrors(bench: nil)
        await runnerClient.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: "{not-json")
        )
        await viewModel.exportSelectedEvaluationSamplesJSONL()
        #expect(viewModel.lastError?.contains("Benchmark export bundle could not be decoded") == true)

        let hostedView = hostWorkflowView(DesktopWorkspaceShellView(viewModel: viewModel))
        let renderedTexts = workflowRenderedTextValues(in: hostedView)
        #expect(hostedView.subviews.isEmpty == false)
        #expect(renderedTexts.contains(where: { $0.contains("Benchmark export bundle could not be decoded") }))
    }
}

@MainActor
private func hostWorkflowView<Content: View>(_ rootView: Content) -> NSView {
    let controller = NSHostingController(rootView: rootView)
    let view = controller.view
    view.frame = NSRect(x: 0, y: 0, width: 1200, height: 800)
    view.layoutSubtreeIfNeeded()
    return view
}

@MainActor
private func workflowRenderedTextValues(in rootView: NSView) -> [String] {
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
