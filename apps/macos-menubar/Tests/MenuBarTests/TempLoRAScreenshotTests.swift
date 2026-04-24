import AppKit
import Foundation
import SwiftUI
import Testing

@testable import AppMain
import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Temporary LoRA Screenshot Renderer", .serialized)
struct TempLoRAScreenshotTests {
    @Test("lora marketing screenshot renderer writes a system window frame")
    @MainActor
    func loraMarketingScreenshotRendererWritesSystemWindowFrame() throws {
        #expect(LoRAMarketingScreenshotStyle.systemCaptureMode == .systemWindow)

        let contentSize = CGSize(width: 360, height: 240)
        let outputURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-lora-system-window-\(UUID().uuidString).png")
        defer { try? FileManager.default.removeItem(at: outputURL) }

        try writeSystemWindowScreenshot(
            rootView: screenshotPanel(Text("System Window Probe")),
            size: contentSize,
            outputURL: outputURL,
            title: "Melix"
        )

        let capturedSize = try pngPixelSize(at: outputURL)
        #expect(capturedSize.width > Int(contentSize.width))
        #expect(capturedSize.height > Int(contentSize.height))
    }

    @Test("lora marketing screenshot renderer uses window-backed white canvas")
    @MainActor
    func loraMarketingScreenshotRendererUsesWindowBackedWhiteCanvas() throws {
        #expect(LoRAMarketingScreenshotStyle.captureMode == .windowBacked)
        #expect(LoRAMarketingScreenshotStyle.backgroundColor == .white)

        let outputURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-lora-white-canvas-\(UUID().uuidString).png")
        defer { try? FileManager.default.removeItem(at: outputURL) }

        try writeScreenshot(
            rootView: screenshotPanel(Text("Canvas Probe")),
            size: CGSize(width: 320, height: 220),
            outputURL: outputURL
        )

        let sampledColor = try samplePNGColor(at: CGPoint(x: 8, y: 8), from: outputURL)
        #expect(sampledColor.isNearWhite)
    }

    @Test("render current lora workspace screenshots")
    @MainActor
    func renderCurrentLoRAWorkspaceScreenshots() async throws {
        let outputRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("artifacts/lora-marketing-screenshots/2026-04-24-polish", isDirectory: true)
        let windowOutputRoot = outputRoot.appendingPathComponent("window", isDirectory: true)
        try FileManager.default.createDirectory(at: outputRoot, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: windowOutputRoot, withIntermediateDirectories: true)

        let baseModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let derivedModelID = "melix-qwen35-acceptance"

        let directClient = FakeControlPlaneXPCClient()
        let runnerClient = FakeControlPlaneXPCClient()
        let snapshot = makeLoRAScreenshotSnapshot(
            models: [
                makeLoRAModelSummary(modelID: baseModelID, alias: "Qwen3.5-0.8B-OptiQ-4bit"),
                makeLoRAModelSummary(modelID: derivedModelID, alias: "Qwen35 Acceptance"),
            ],
            runtimeSessions: [makeLoRAServerRuntimeSession()]
        )
        await directClient.configureSnapshot(snapshot)
        await runnerClient.configureSnapshot(snapshot)
        await runnerClient.configureModelOperation(
            makeLoRAModelOperationResult(
                operation: "train_lora",
                outputPath: "/tmp/melix/train_lora/train-job-1/train_lora.adapter.json",
                manifestJSON: #"{"operation":"train_lora","job_id":"train-job-1","adapter_name":"qwen35-acceptance","output_path":"/tmp/melix/train_lora/train-job-1/train_lora.adapter.json"}"#
            ),
            forNamedOperation: "train_lora"
        )
        await runnerClient.configureModelOperation(
            makeLoRAModelOperationResult(
                operation: "activate_adapter",
                outputPath: "/tmp/melix/activate_adapter/activate-job-1/activate_adapter.derived_model.json",
                manifestJSON: #"{"operation":"activate_adapter","job_id":"activate-job-1","derived_model_id":"melix-qwen35-acceptance","derived_model_path":"/tmp/melix/activate_adapter/activate-job-1/activate_adapter.derived_model.json"}"#
            ),
            forNamedOperation: "activate_adapter"
        )
        await runnerClient.configureModelOperation(
            makeLoRAModelOperationResult(
                operation: "remove_derived_model",
                outputPath: "/tmp/melix/remove_derived_model/remove-job-1/remove_derived_model.json",
                manifestJSON: #"{"operation":"remove_derived_model","job_id":"remove-job-1","derived_model_id":"melix-qwen35-acceptance"}"#
            ),
            forNamedOperation: "remove_derived_model"
        )
        await runnerClient.configureModelOperation(
            makeLoRAModelOperationResult(
                operation: "registry_snapshot",
                outputPath: "/tmp/melix/model_ops/registry_snapshot.json",
                manifestJSON: makeLoRARegistrySnapshotManifest(
                    baseModelID: baseModelID,
                    derivedModelID: derivedModelID
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        await runnerClient.configureBenchResponse(
            ControlPlaneBenchResult(
                reportPath: "/tmp/melix/bench/runs/bench-newer/bench-report.md",
                reportMarkdown: "# Melix Bench\n\n- bench.smoke.tokens_per_second: 61.20 tok/s\n",
                metrics: [
                    "bench.smoke.ttft_ms": 21.10,
                    "bench.smoke.tokens_per_second": 61.20,
                    "bench.latency.p95_ms": 39.70,
                ]
            )
        )
        await runnerClient.configureBenchMatrixResponse(makeLoRABenchMatrixResult(modelID: derivedModelID))
        await runnerClient.configureEvaluationResponse(
            makeLoRAEvaluationCompareResult(baseModelID: baseModelID, derivedModelID: derivedModelID)
        )
        await runnerClient.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSON())
        )

        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-lora-polish-screenshots-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let operatorStore = MelixOperatorSessionStore(
            melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        )
        let runner = MelixCLIRunner(
            client: runnerClient,
            environment: ["MELIX_HOME": temporaryRoot.path],
            operatorSessionStore: operatorStore
        )
        let viewModel = RuntimeViewModel(
            client: directClient,
            operatorCommandRunner: runner
        )

        await viewModel.start()
        await viewModel.refreshModelOpsProductState()
        viewModel.selectSurface(.tools)
        viewModel.selectToolSection(.training)
        viewModel.selectedLoraModelID = baseModelID
        viewModel.loraDatasetSourceKind = .huggingFaceDataset
        viewModel.loraHFDatasetPath = "HuggingFaceH4/ultrachat_200k"
        viewModel.loraHFTrainSplit = "train_sft"
        viewModel.loraHFValidSplit = "test_sft"
        viewModel.loraChatFeature = "messages"
        viewModel.loraAdapterName = "qwen35-acceptance"
        viewModel.loraDerivedModelAlias = derivedModelID
        viewModel.loraExperimentGroupID = "phase8-acceptance"
        viewModel.loraTrainingMode = .qlora
        viewModel.loraActivationMode = .adapterBackedRuntime
        viewModel.loraTargetRepo = "melix/qwen35-acceptance"

        try writeScreenshot(
            rootView: DesktopFoundationRootView(viewModel: viewModel),
            size: CGSize(width: 1440, height: 960),
            outputURL: outputRoot.appendingPathComponent("01-tools-training-overview.png")
        )
        try writeSystemWindowScreenshot(
            rootView: DesktopFoundationRootView(viewModel: viewModel),
            size: CGSize(width: 1440, height: 960),
            outputURL: windowOutputRoot.appendingPathComponent("01-tools-training-overview-window.png"),
            title: "Melix"
        )

        try writeScreenshot(
            rootView: screenshotPanel(DesktopTrainingToolSectionView(viewModel: viewModel)),
            size: CGSize(width: 1280, height: 1380),
            outputURL: outputRoot.appendingPathComponent("02-training-detail.png")
        )

        let trainingSection = DesktopTrainingToolSectionView(viewModel: viewModel)
        await trainingSection.trainLoRA()
        await trainingSection.activateAdapter()

        try writeScreenshot(
            rootView: screenshotPanel(DesktopTrainingToolSectionView(viewModel: viewModel)),
            size: CGSize(width: 1280, height: 1540),
            outputURL: outputRoot.appendingPathComponent("03-training-history-activation.png")
        )

        viewModel.selectToolSection(.diagnostics)
        viewModel.selectedBenchmarkTargetMode = .catalogModel
        viewModel.selectedBenchmarkModelID = derivedModelID
        viewModel.selectedBenchmarkSuiteIDs = ["smoke", "latency"]
        viewModel.benchRepeats = "2"
        viewModel.selectedBenchContextLengths = [1024, 4096]
        viewModel.selectedBenchBatchSizes = [1, 2]

        let diagnosticsSection = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        await diagnosticsSection.runBenchmark()
        diagnosticsSection.selectBenchmarkHistory(jobID: "bench-newer")

        try writeScreenshot(
            rootView: screenshotPanel(
                DesktopDiagnosticsToolSectionView(
                    viewModel: viewModel,
                    foundation: viewModel.desktopFoundationState
                )
            ),
            size: CGSize(width: 1280, height: 1680),
            outputURL: outputRoot.appendingPathComponent("04-diagnostics-benchmark.png")
        )
        try writeSystemWindowScreenshot(
            rootView: screenshotPanel(
                DesktopDiagnosticsToolSectionView(
                    viewModel: viewModel,
                    foundation: viewModel.desktopFoundationState
                )
            ),
            size: CGSize(width: 1280, height: 1100),
            outputURL: windowOutputRoot.appendingPathComponent("04-diagnostics-benchmark-window.png"),
            title: "Melix"
        )

        viewModel.selectedBenchmarkPresentationMode = .matrix
        viewModel.selectedBenchmarkSuiteIDs = ["smoke", "latency"]
        await diagnosticsSection.runBenchmarkMatrix()
        diagnosticsSection.selectBenchmarkMatrixHistory(jobID: "matrix-newer")

        try writeScreenshot(
            rootView: screenshotPanel(
                DesktopDiagnosticsToolSectionView(
                    viewModel: viewModel,
                    foundation: viewModel.desktopFoundationState
                )
            ),
            size: CGSize(width: 1280, height: 1720),
            outputURL: outputRoot.appendingPathComponent("05-diagnostics-matrix.png")
        )
        try writeSystemWindowScreenshot(
            rootView: screenshotPanel(
                DesktopDiagnosticsToolSectionView(
                    viewModel: viewModel,
                    foundation: viewModel.desktopFoundationState
                )
            ),
            size: CGSize(width: 1280, height: 1100),
            outputURL: windowOutputRoot.appendingPathComponent("05-diagnostics-matrix-window.png"),
            title: "Melix"
        )

        viewModel.selectedEvaluationTargetMode = .catalogModel
        viewModel.selectedEvaluationModelID = baseModelID
        viewModel.selectedEvaluationMode = .compare
        viewModel.selectedEvaluationCompareTargetModelIDs = [derivedModelID]
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        await diagnosticsSection.runEvaluationCompare()
        diagnosticsSection.selectEvaluationHistory(jobID: "eval-compare-1")

        try writeScreenshot(
            rootView: screenshotPanel(
                DesktopDiagnosticsToolSectionView(
                    viewModel: viewModel,
                    foundation: viewModel.desktopFoundationState
                )
            ),
            size: CGSize(width: 1280, height: 1720),
            outputURL: outputRoot.appendingPathComponent("06-diagnostics-evaluation.png")
        )

        for name in [
            "01-tools-training-overview.png",
            "02-training-detail.png",
            "03-training-history-activation.png",
            "04-diagnostics-benchmark.png",
            "05-diagnostics-matrix.png",
            "06-diagnostics-evaluation.png",
        ] {
            #expect(
                FileManager.default.fileExists(
                    atPath: outputRoot.appendingPathComponent(name).path
                )
            )
        }
        for name in [
            "01-tools-training-overview-window.png",
            "04-diagnostics-benchmark-window.png",
            "05-diagnostics-matrix-window.png",
        ] {
            #expect(
                FileManager.default.fileExists(
                    atPath: windowOutputRoot.appendingPathComponent(name).path
                )
            )
        }
    }
}

private enum LoRAMarketingScreenshotCaptureMode {
    case offscreenHostingView
    case windowBacked
    case systemWindow
}

private enum LoRAMarketingScreenshotStyle {
    static let captureMode: LoRAMarketingScreenshotCaptureMode = .windowBacked
    static let systemCaptureMode: LoRAMarketingScreenshotCaptureMode = .systemWindow
    static let backgroundColor: NSColor = .white
}

@MainActor
private var retainedLoRAMarketingScreenshotWindows: [NSWindow] = []

@MainActor
private func screenshotPanel<Content: View>(_ content: Content) -> some View {
    ZStack(alignment: .topLeading) {
        Color(nsColor: LoRAMarketingScreenshotStyle.backgroundColor)
        ScrollView(showsIndicators: false) {
            VStack(alignment: .leading, spacing: 0) {
                content
                    .frame(maxWidth: 1060, alignment: .leading)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.horizontal, 32)
                    .padding(.vertical, 28)
            }
        }
    }
}

private struct SampledPNGColor {
    let red: CGFloat
    let green: CGFloat
    let blue: CGFloat
    let alpha: CGFloat

    var isNearWhite: Bool {
        red >= 0.98 && green >= 0.98 && blue >= 0.98 && alpha >= 0.99
    }
}

private func samplePNGColor(at point: CGPoint, from url: URL) throws -> SampledPNGColor {
    let data = try Data(contentsOf: url)
    guard let image = NSImage(data: data),
          let tiff = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff)
    else {
        Issue.record("Failed to decode PNG for \(url.lastPathComponent)")
        return SampledPNGColor(red: 0, green: 0, blue: 0, alpha: 0)
    }

    let x = max(0, min(Int(point.x), bitmap.pixelsWide - 1))
    let y = max(0, min(Int(point.y), bitmap.pixelsHigh - 1))
    guard let color = bitmap.colorAt(x: x, y: y)?.usingColorSpace(.deviceRGB) else {
        Issue.record("Failed to sample PNG color for \(url.lastPathComponent)")
        return SampledPNGColor(red: 0, green: 0, blue: 0, alpha: 0)
    }

    return SampledPNGColor(
        red: color.redComponent,
        green: color.greenComponent,
        blue: color.blueComponent,
        alpha: color.alphaComponent
    )
}

private func pngPixelSize(at url: URL) throws -> (width: Int, height: Int) {
    let data = try Data(contentsOf: url)
    guard let image = NSImage(data: data),
          let tiff = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff)
    else {
        Issue.record("Failed to decode PNG for \(url.lastPathComponent)")
        return (0, 0)
    }
    return (bitmap.pixelsWide, bitmap.pixelsHigh)
}

@MainActor
private func writeScreenshot<Content: View>(
    rootView: Content,
    size: CGSize,
    outputURL: URL,
    afterLayout: ((NSView) -> Void)? = nil
) throws {
    let hostingView = NSHostingView(
        rootView: rootView
            .frame(width: size.width, height: size.height)
            .background(Color(nsColor: LoRAMarketingScreenshotStyle.backgroundColor))
    )
    hostingView.frame = CGRect(origin: .zero, size: size)
    hostingView.wantsLayer = true
    hostingView.layer?.backgroundColor = LoRAMarketingScreenshotStyle.backgroundColor.cgColor

    let window = NSWindow(
        contentRect: CGRect(origin: .zero, size: size),
        styleMask: [.borderless],
        backing: .buffered,
        defer: false
    )
    window.backgroundColor = LoRAMarketingScreenshotStyle.backgroundColor
    window.isOpaque = true
    window.contentView = hostingView
    window.layoutIfNeeded()
    window.displayIfNeeded()

    hostingView.layoutSubtreeIfNeeded()
    afterLayout?(hostingView)
    hostingView.layoutSubtreeIfNeeded()

    guard let bitmap = hostingView.bitmapImageRepForCachingDisplay(in: hostingView.bounds) else {
        Issue.record("Failed to allocate bitmap for \(outputURL.lastPathComponent)")
        return
    }
    bitmap.size = size
    hostingView.cacheDisplay(in: hostingView.bounds, to: bitmap)

    guard let data = bitmap.representation(using: .png, properties: [:]) else {
        Issue.record("Failed to encode bitmap for \(outputURL.lastPathComponent)")
        return
    }
    try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try data.write(to: outputURL)
    retainedLoRAMarketingScreenshotWindows.append(window)
}

@MainActor
private func writeSystemWindowScreenshot<Content: View>(
    rootView: Content,
    size: CGSize,
    outputURL: URL,
    title: String
) throws {
    let hostingView = NSHostingView(
        rootView: rootView
            .frame(width: size.width, height: size.height)
            .background(Color(nsColor: LoRAMarketingScreenshotStyle.backgroundColor))
    )
    hostingView.frame = CGRect(origin: .zero, size: size)
    hostingView.wantsLayer = true
    hostingView.layer?.backgroundColor = LoRAMarketingScreenshotStyle.backgroundColor.cgColor

    let window = NSWindow(
        contentRect: CGRect(origin: .zero, size: size),
        styleMask: [.titled, .closable, .miniaturizable, .resizable],
        backing: .buffered,
        defer: false
    )
    window.title = title
    window.titleVisibility = .visible
    window.titlebarAppearsTransparent = false
    window.backgroundColor = LoRAMarketingScreenshotStyle.backgroundColor
    window.contentView = hostingView
    window.hasShadow = true
    window.isOpaque = true
    window.isReleasedWhenClosed = false
    window.setContentSize(size)
    window.center()
    window.orderFrontRegardless()
    window.displayIfNeeded()

    hostingView.layoutSubtreeIfNeeded()
    pumpMainRunLoopForRendering()

    try FileManager.default.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    try runSystemWindowCapture(windowNumber: window.windowNumber, outputURL: outputURL)

    window.orderOut(nil)
    retainedLoRAMarketingScreenshotWindows.append(window)
}

@MainActor
private func pumpMainRunLoopForRendering() {
    for _ in 0..<8 {
        RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.05))
    }
}

private func runSystemWindowCapture(windowNumber: Int, outputURL: URL) throws {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/sbin/screencapture")
    process.arguments = [
        "-x",
        "-t",
        "png",
        "-l",
        "\(windowNumber)",
        outputURL.path,
    ]

    let errorPipe = Pipe()
    process.standardError = errorPipe
    try process.run()
    process.waitUntilExit()

    guard process.terminationStatus == 0 else {
        let errorData = errorPipe.fileHandleForReading.readDataToEndOfFile()
        let message = String(data: errorData, encoding: .utf8) ?? "unknown screencapture error"
        throw NSError(
            domain: "MelixLoRAMarketingScreenshot",
            code: Int(process.terminationStatus),
            userInfo: [NSLocalizedDescriptionKey: message]
        )
    }
}

private func makeLoRAScreenshotSnapshot(
    models: [Melix_Controlplane_V1_ModelSummary],
    runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState]
) -> Melix_Controlplane_V1_ServerSnapshot {
    var snapshot = Melix_Controlplane_V1_ServerSnapshot()
    snapshot.serverState = .serverReady
    snapshot.models = models
    snapshot.runtimeSessions = runtimeSessions
    return snapshot
}

private func makeLoRAServerRuntimeSession() -> Melix_Controlplane_V1_ServerSessionRuntimeState {
    var runtimeSession = Melix_Controlplane_V1_ServerSessionRuntimeState()
    runtimeSession.serverSessionID = "server-session-1"
    runtimeSession.lifecycleState = .ready
    runtimeSession.powerState = .active
    runtimeSession.wakeReason = .initialBoot
    runtimeSession.idleTimerSeconds = 42
    runtimeSession.autoSleepEnabled = true
    runtimeSession.lightSleepAfterSeconds = 300
    runtimeSession.deepSleepAfterSeconds = 1800
    runtimeSession.updatedAtUnixMs = 1_717_171_717
    return runtimeSession
}

private func makeLoRAModelSummary(modelID: String, alias: String) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = "text"
    model.state = Melix_Controlplane_V1_ModelState.modelWarm
    model.features = ["chat", "tools", "reasoning", "sandboxed"]
    model.settings.alias = alias
    return model
}

private func makeLoRAModelOperationResult(
    operation: String,
    outputPath: String,
    manifestJSON: String
) -> Melix_Controlplane_V1_ModelOperationResult {
    var result = Melix_Controlplane_V1_ModelOperationResult()
    result.operation = operation
    result.jobID = "\(operation)-job"
    result.outputPath = outputPath
    result.manifestJson = manifestJSON
    return result
}

private func makeLoRARegistrySnapshotManifest(
    baseModelID: String,
    derivedModelID: String
) -> String {
    #"""
    {
      "operation": "registry_snapshot",
      "jobs": [
        {
          "job_id": "train-job-1",
          "operation": "train_lora",
          "source_model": "\#(baseModelID)",
          "status": "completed",
          "stage": "write_artifact",
          "pct": 1.0,
          "output_path": "/tmp/melix/train_lora/train-job-1/train_lora.adapter.json",
          "manifest": {
            "adapter_name": "qwen35-acceptance",
            "dataset_uri": "HuggingFaceH4/ultrachat_200k",
            "target_repo": "melix/qwen35-acceptance"
          }
        }
      ],
      "adapters": [
        {
          "adapter_id": "qwen35-acceptance@train-job-1",
          "job_id": "train-job-1",
          "adapter_name": "qwen35-acceptance",
          "source_model": "\#(baseModelID)",
          "dataset_uri": "HuggingFaceH4/ultrachat_200k",
          "output_path": "/tmp/melix/train_lora/train-job-1/train_lora.adapter.json",
          "activation_status": "activated",
          "derived_model_id": "\#(derivedModelID)",
          "derived_model_path": "/tmp/melix/activate_adapter/activate-job-1/activate_adapter.derived_model.json",
          "exportable_state": "ready",
          "published_state": "published",
          "target_repo": "melix/qwen35-acceptance",
          "published_repo": "melix/qwen35-acceptance",
          "status": "activated",
          "response_only": true,
          "gradient_checkpointing": true,
          "training_duration_ms": 1420.0,
          "activation_duration_ms": 321.0,
          "adapter_publish_ms": 118.0,
          "experiment_group_id": "phase8-acceptance"
        }
      ],
      "derived_models": [
        {
          "model_id": "\#(derivedModelID)",
          "model_path": "/tmp/melix/activate_adapter/activate-job-1/activate_adapter.derived_model.json",
          "adapter_set_hash": "adapter-alpha",
          "source_model": "\#(baseModelID)",
          "activation_mode": "adapter_backed_runtime",
          "status": "activated"
        }
      ],
      "experiment_groups": [
        {
          "group_id": "phase8-acceptance",
          "source_model": "\#(baseModelID)",
          "adapter_count": 1,
          "latest_job_id": "train-job-1",
          "latest_status": "activated",
          "last_updated_unix_ms": 1712400001000
        }
      ]
    }
    """#
}

private func makeLoRABenchMatrixResult(modelID: String) -> ControlPlaneBenchMatrixResult {
    var job = Melix_Controlplane_V1_BenchmarkMatrixJobSummary()
    job.jobID = "matrix-newer"
    job.modelID = modelID
    job.taskKind = "text-generation"
    job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
    job.suiteIds = ["smoke", "latency"]
    job.benchmarkMode = "matrix"
    job.status = "completed"
    job.outputDir = "/tmp/melix/bench/matrix-runs/matrix-newer"
    job.createdAtUnixMs = 1_712_250_000_000
    job.updatedAtUnixMs = 1_712_250_000_500

    var row = Melix_Controlplane_V1_BenchmarkMatrixSummaryRow()
    row.jobID = "matrix-newer"
    row.taskKind = "text-generation"
    row.sourceRepo = "HuggingFaceH4/ultrachat_200k"
    row.modelID = modelID
    row.suiteID = "smoke"
    row.contextLength = 1024
    row.generationLength = 128
    row.batchSize = 2
    row.cacheProfile = "warm"
    row.reasoningMode = "enabled"
    row.structuredOutputMode = "json_schema"
    row.concurrencyLevel = 1
    row.repeats = 3
    row.requests = 8
    row.ttftMeanMs = 24.4
    row.requestLatencyMeanMs = 33.8
    row.prefillTokensPerSecondMean = 310
    row.decodeTokensPerSecondMean = 62
    row.throughputRequestsPerSecond = 4.8
    row.throughputTokensPerSecond = 256
    row.successRate = 1
    row.peakMemoryBytesMax = 2_048_000_000
    row.queueWaitMeanMs = 2.3
    row.queueWaitP95Ms = 3.1
    row.createdAtUnixMs = 1_712_250_000_000
    return ControlPlaneBenchMatrixResult(job: job, summaryRows: [row])
}

private func makeLoRAEvaluationCompareResult(
    baseModelID: String,
    derivedModelID: String
) -> ControlPlaneEvaluationResult {
    var job = Melix_Controlplane_V1_EvaluationJobSummary()
    job.jobID = "eval-compare-1"
    job.modelID = baseModelID
    job.taskKind = "text-generation"
    job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
    job.suiteID = "mmlu"
    job.datasetID = "mmlu.dev.v1"
    job.sampleSize = 6
    job.scoringMode = "multiple_choice_accuracy"
    job.status = "completed"
    job.outputDir = "/tmp/melix/evaluation/runs/eval-compare-1"
    job.createdAtUnixMs = 1_712_400_000_000
    job.updatedAtUnixMs = 1_712_400_001_000

    var metric = Melix_Controlplane_V1_BenchmarkMetricValue()
    metric.name = "eval.compare.win_rate"
    metric.value = 0.625
    metric.unit = "ratio"

    var result = Melix_Controlplane_V1_EvaluationResultSummary()
    result.jobID = "eval-compare-1"
    result.suiteID = "mmlu:\(derivedModelID)"
    result.datasetID = "mmlu.dev.v1"
    result.sampleSize = 6
    result.metrics = [metric]
    result.reportPath = "/tmp/melix/evaluation/runs/eval-compare-1/\(derivedModelID)-result.json"
    return ControlPlaneEvaluationResult(job: job, results: [result])
}
