import AppKit
import Foundation
import SwiftUI
import MelixCLICore

private let phase8BaseChatPrompt = "Reply with BASE_OK"
private let phase8DerivedChatPrompt = "Reply with DERIVED_OK"
private let phase8AdapterName = "phase8-acceptance"
private let phase8DerivedAlias = "phase8-acceptance-derived"
private let phase8WindowUISchemaVersion = "melix.phase8.window_ui_acceptance.v1"
private let phase8BenchContextLength: UInt32 = 1024
private let phase8BenchGenerationLength: UInt32 = 64
private let phase8BenchBatchSize: UInt32 = 1
private let phase8BenchSampleSize = "4"
private let phase8MatrixCacheProfile = "cold"
private let phase8MatrixReasoningMode = "disabled"
private let phase8MatrixStructuredOutputMode = "plain_text"
private let phase8MatrixConcurrencyLevel: UInt32 = 1
private let phase8MatrixRequests: UInt32 = 4
private let phase8EvaluationSampleSize: UInt32 = 4
private let phase8EvaluationScoringMode = "multiple_choice_accuracy"

public enum Phase8WindowUIAcceptanceError: Error, LocalizedError {
    case missingCLIEvidenceBundle(String)
    case missingCLIWorkflowRunner
    case missingManagedReceipt
    case missingAdapterManifestPath
    case missingDerivedModelID
    case missingServerSession(String)
    case timeout(String)
    case workflowFailed(String)
    case screenshotRenderFailed(String)

    public var errorDescription: String? {
        switch self {
        case .missingCLIEvidenceBundle(let path):
            return "Missing CLI evidence bundle at \(path)."
        case .missingCLIWorkflowRunner:
            return "Phase 8 Window UI acceptance requires a CLI workflow runner."
        case .missingManagedReceipt:
            return "Window UI acceptance could not resolve a managed model receipt."
        case .missingAdapterManifestPath:
            return "Window UI acceptance could not resolve the adapter manifest path from the LoRA training receipt."
        case .missingDerivedModelID:
            return "Window UI acceptance could not resolve the derived model id after activation."
        case .missingServerSession(let serverSessionID):
            return "Window UI acceptance could not find server session \(serverSessionID)."
        case .timeout(let description):
            return "Window UI acceptance timed out while waiting for \(description)."
        case .workflowFailed(let detail):
            return detail
        case .screenshotRenderFailed(let reason):
            return "Window UI acceptance screenshot rendering failed: \(reason)"
        }
    }
}

public struct Phase8WindowUIAcceptanceConfig: Equatable, Sendable {
    public let repoRoot: String
    public let melixHome: String
    public let modelID: String
    public let localModelPath: String
    public let trainingFixture: String
    public let benchSuites: [String]
    public let matrixSuites: [String]
    public let evaluationSuites: [String]
    public let evaluationDataset: String
    public let serverSessionID: String
    public let cliEvidenceBundlePath: String
    public let timestamp: String

    public init(
        repoRoot: String,
        melixHome: String,
        modelID: String,
        localModelPath: String,
        trainingFixture: String,
        benchSuites: [String],
        matrixSuites: [String],
        evaluationSuites: [String],
        evaluationDataset: String,
        serverSessionID: String,
        cliEvidenceBundlePath: String,
        timestamp: String
    ) {
        self.repoRoot = repoRoot
        self.melixHome = melixHome
        self.modelID = modelID
        self.localModelPath = localModelPath
        self.trainingFixture = trainingFixture
        self.benchSuites = benchSuites
        self.matrixSuites = matrixSuites
        self.evaluationSuites = evaluationSuites
        self.evaluationDataset = evaluationDataset
        self.serverSessionID = serverSessionID
        self.cliEvidenceBundlePath = cliEvidenceBundlePath
        self.timestamp = timestamp
    }

    public init(environment: [String: String]) {
        let melixHome = MelixHome(environment: environment)
        self.repoRoot = Self.normalized(environment["MELIX_REPO_ROOT"]) ?? FileManager.default.currentDirectoryPath
        self.melixHome = melixHome.rootURL.path
        self.modelID = Self.normalized(environment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MODEL_ID"])
            ?? "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        self.localModelPath = Self.normalized(environment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_LOCAL_MODEL_PATH"]) ?? ""
        self.trainingFixture = Self.normalized(environment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TRAINING_FIXTURE"])
            ?? "services/mlx-worker-python/fixtures/training/melix-dev-dataset.v1"
        self.benchSuites = Self.parseList(
            environment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_BENCH_SUITES"],
            defaultValues: ["smoke", "latency"]
        )
        self.matrixSuites = Self.parseList(
            environment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_MATRIX_SUITES"],
            defaultValues: ["smoke"]
        )
        self.evaluationSuites = Self.parseList(
            environment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_SUITES"],
            defaultValues: ["mmlu"]
        )
        self.evaluationDataset = Self.normalized(environment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_EVALUATION_DATASET"])
            ?? "mmlu.dev.v1"
        self.serverSessionID = Self.normalized(environment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_SERVER_SESSION_ID"])
            ?? "server-session-1"
        self.cliEvidenceBundlePath = Self.normalized(environment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_CLI_BUNDLE_PATH"])
            ?? Self.discoverLatestCLIBundlePath(melixHome: melixHome.rootURL)
        self.timestamp = Self.normalized(environment["MELIX_PHASE8_WINDOW_UI_ACCEPTANCE_TIMESTAMP"])
            ?? Self.defaultTimestamp()
    }

    private static func parseList(_ value: String?, defaultValues: [String]) -> [String] {
        let parsed = value?
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { $0.isEmpty == false } ?? []
        return parsed.isEmpty ? defaultValues : parsed
    }

    private static func normalized(_ value: String?) -> String? {
        guard let value else {
            return nil
        }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private static func discoverLatestCLIBundlePath(melixHome: URL) -> String {
        let cliRoot = melixHome
            .appendingPathComponent("acceptance", isDirectory: true)
            .appendingPathComponent("phase8", isDirectory: true)
            .appendingPathComponent("cli", isDirectory: true)
        let fileManager = FileManager.default
        guard
            let entries = try? fileManager.contentsOfDirectory(
                at: cliRoot,
                includingPropertiesForKeys: [.isDirectoryKey, .nameKey],
                options: [.skipsHiddenFiles]
            )
        else {
            return cliRoot.appendingPathComponent("bundle.json").path
        }

        let latestBundle = entries
            .filter { (try? $0.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) == true }
            .sorted { $0.lastPathComponent > $1.lastPathComponent }
            .map { $0.appendingPathComponent("bundle.json") }
            .first

        return latestBundle?.path ?? cliRoot.appendingPathComponent("bundle.json").path
    }

    private static func defaultTimestamp() -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd'T'HHmmss'Z'"
        return formatter.string(from: Date())
    }
}

public struct Phase8WindowUIAcceptanceResult: Codable, Equatable, Sendable {
    public let bundlePath: String
    public let screenshotPath: String
    public let cliEvidenceBundlePath: String
    public let modelID: String
}

private struct Phase8WindowUIAcceptanceUIState: Codable, Equatable, Sendable {
    let selectedSurface: String
    let selectedToolSection: String
    let selectedServerSessionID: String
    let selectedServerLifecycle: String
}

private struct Phase8WindowUIAcceptanceBundle: Codable, Equatable, Sendable {
    let schemaVersion: String
    let surface: String
    let timestamp: String
    let repoRoot: String
    let melixHome: String
    let modelID: String
    let managedModelPath: String
    let sourceKind: String
    let sourceLocator: String
    let serverSessionID: String
    let derivedModelID: String
    let trainingFixture: String
    let benchmarkSuites: [String]
    let matrixSuites: [String]
    let evaluationSuites: [String]
    let evaluationDataset: String
    let cliEvidenceBundlePath: String
    let screenshotPath: String
    let baseChatAssistantText: String
    let derivedChatAssistantText: String
    let loraTrainJobID: String
    let loraActivateJobID: String
    let benchJobID: String
    let benchCSVPath: String
    let benchMatrixJobID: String
    let benchMatrixSummaryCSVPath: String
    let benchMatrixRequestsCSVPath: String
    let evaluationJobID: String
    let evaluationSummaryCSVPath: String
    let evaluationSamplesCSVPath: String
    let evaluationSamplesJSONLPath: String
    let timings: [String: Double]
    let uiState: Phase8WindowUIAcceptanceUIState
}

@MainActor
public protocol Phase8WindowUIRendering: Sendable {
    func render(viewModel: RuntimeViewModel, to outputURL: URL, size: CGSize) throws
}

@MainActor
public struct LivePhase8WindowUIRenderer: Phase8WindowUIRendering {
    public init() {}

    public func render(viewModel: RuntimeViewModel, to outputURL: URL, size: CGSize) throws {
        let hostingView = NSHostingView(
            rootView: DesktopFoundationRootView(viewModel: viewModel)
                .frame(width: size.width, height: size.height)
        )
        hostingView.frame = CGRect(origin: .zero, size: size)
        hostingView.layoutSubtreeIfNeeded()

        guard let bitmap = hostingView.bitmapImageRepForCachingDisplay(in: hostingView.bounds) else {
            throw Phase8WindowUIAcceptanceError.screenshotRenderFailed(
                "NSHostingView could not allocate a bitmap snapshot."
            )
        }
        bitmap.size = size
        hostingView.cacheDisplay(in: hostingView.bounds, to: bitmap)

        guard let data = bitmap.representation(using: .png, properties: [:]) else {
            throw Phase8WindowUIAcceptanceError.screenshotRenderFailed("Bitmap snapshot could not be encoded as PNG.")
        }
        try FileManager.default.createDirectory(
            at: outputURL.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try data.write(to: outputURL)
    }
}

@MainActor
public final class Phase8WindowUIAcceptanceRunner {
    private let viewModel: RuntimeViewModel
    private let cliWorkflowRunner: any MelixCLIWorkflowRunning
    private let config: Phase8WindowUIAcceptanceConfig
    private let renderer: any Phase8WindowUIRendering
    private let fileManager: FileManager
    private let screenshotSize = CGSize(width: 1440, height: 960)

    public init(
        viewModel: RuntimeViewModel,
        cliWorkflowRunner: any MelixCLIWorkflowRunning,
        config: Phase8WindowUIAcceptanceConfig,
        renderer: any Phase8WindowUIRendering = LivePhase8WindowUIRenderer(),
        fileManager: FileManager = .default
    ) throws {
        self.viewModel = viewModel
        self.cliWorkflowRunner = cliWorkflowRunner
        self.config = config
        self.renderer = renderer
        self.fileManager = fileManager
    }

    public func run() async throws -> Phase8WindowUIAcceptanceResult {
        let cliBundleURL = URL(fileURLWithPath: config.cliEvidenceBundlePath)
        guard fileManager.fileExists(atPath: cliBundleURL.path) else {
            throw Phase8WindowUIAcceptanceError.missingCLIEvidenceBundle(cliBundleURL.path)
        }

        let bundleRoot = URL(fileURLWithPath: config.melixHome, isDirectory: true)
            .appendingPathComponent("acceptance", isDirectory: true)
            .appendingPathComponent("phase8", isDirectory: true)
            .appendingPathComponent("window-ui", isDirectory: true)
            .appendingPathComponent(config.timestamp, isDirectory: true)
        let bundleURL = bundleRoot.appendingPathComponent("bundle.json")
        let screenshotURL = bundleRoot.appendingPathComponent("window-ui.png")
        let exportsRoot = bundleRoot.appendingPathComponent("exports", isDirectory: true)
        try fileManager.createDirectory(at: bundleRoot, withIntermediateDirectories: true)
        try fileManager.createDirectory(at: exportsRoot, withIntermediateDirectories: true)

        await viewModel.start()
        try await waitFor("initial desktop foundation state") {
            self.viewModel.serverSessions.isEmpty == false || self.viewModel.models.isEmpty == false
        }

        var timings: [String: Double] = [:]
        let materializeStartedAt = Date()
        let materializeReceipt = try await materializeModel()
        timings["phase8.ui.managed_materialize_ms"] = elapsedMS(since: materializeStartedAt)
        viewModel.selectedLoraModelID = materializeReceipt.modelID
        let managedModelRootPath = resolvedManagedModelRootPath()
        var registryRootPaths = viewModel.registryConfiguredRootPaths
        if registryRootPaths.contains(managedModelRootPath) == false {
            registryRootPaths.append(managedModelRootPath)
        }
        await viewModel.refreshModelRegistry(
            modelID: "melix-dev-text",
            registryRootsOverride: registryRootPaths,
            rescan: true
        )
        try await waitFor(managedModelVisibilityDescription(modelID: materializeReceipt.modelID)) {
            self.viewModel.serverModelOptions.contains(where: { $0.modelID == materializeReceipt.modelID })
        }

        let serverSessionID = try await prepareServerSession(modelID: materializeReceipt.modelID)
        let sessionRebindStartedAt = Date()
        await viewModel.startSelectedServerSession()
        try await waitFor("interactive server session readiness") {
            self.viewModel.selectedServerSession?.id == serverSessionID
                && self.viewModel.selectedServerSession?.isInteractiveReady == true
        }
        timings["phase8.ui.session_rebind_ms"] = elapsedMS(since: sessionRebindStartedAt)

        let baseChatStartedAt = Date()
        let baseChatReceipt = try await runChat(modelID: materializeReceipt.modelID, message: phase8BaseChatPrompt)
        timings["phase8.ui.base_chat_roundtrip_ms"] = elapsedMS(since: baseChatStartedAt)

        viewModel.loraDatasetURI = config.trainingFixture
        viewModel.loraAdapterName = phase8AdapterName
        viewModel.loraDerivedModelAlias = phase8DerivedAlias

        let loraTrainStartedAt = Date()
        let loraTrainManifest = try await runLoraTrain(modelID: materializeReceipt.modelID)
        timings["phase8.ui.lora_train_ms"] = elapsedMS(since: loraTrainStartedAt)
        let loraTrainJobID = loraTrainManifest.jobID ?? ""
        let adapterManifestPath = try resolveAdapterManifestPath(from: loraTrainManifest)

        let loraActivateStartedAt = Date()
        let loraActivateManifest = try await runLoraActivate(
            modelID: materializeReceipt.modelID,
            adapterPath: adapterManifestPath
        )
        timings["phase8.ui.lora_activate_ms"] = elapsedMS(since: loraActivateStartedAt)
        let loraActivateJobID = loraActivateManifest.jobID ?? ""
        let derivedModelID = try deriveActivatedModelID(from: loraActivateManifest)

        await viewModel.refreshDesktopFoundation()
        let derivedChatStartedAt = Date()
        let derivedChatReceipt = try await runChat(modelID: derivedModelID, message: phase8DerivedChatPrompt)
        timings["phase8.ui.derived_chat_roundtrip_ms"] = elapsedMS(since: derivedChatStartedAt)

        viewModel.updateSelectedServerSessionModelID(materializeReceipt.modelID)
        viewModel.selectedBenchmarkModelID = materializeReceipt.modelID
        viewModel.selectedBenchmarkSuiteIDs = Set(config.benchSuites)
        viewModel.benchRepeats = "1"
        let benchRunStartedAt = Date()
        let benchRunPayload = try await runBench(modelID: materializeReceipt.modelID)
        timings["phase8.ui.bench_run_ms"] = elapsedMS(since: benchRunStartedAt)
        let benchJobID = try benchmarkJobID(from: benchRunPayload.reportPath)
        let benchCSVPath = try await exportBenchCSV(
            jobID: benchJobID,
            outputURL: exportsRoot.appendingPathComponent("bench.csv")
        )

        viewModel.selectedBenchmarkPresentationMode = .matrix
        viewModel.selectedBenchmarkSuiteIDs = Set(config.matrixSuites)
        viewModel.benchMatrixRepeats = "1"
        viewModel.benchMatrixRequests = "4"
        viewModel.benchMatrixAllowLargeMatrix = false
        let benchMatrixStartedAt = Date()
        let benchMatrixPayload = try await runBenchMatrix(modelID: materializeReceipt.modelID)
        timings["phase8.ui.bench_matrix_run_ms"] = elapsedMS(since: benchMatrixStartedAt)
        let benchMatrixJobID = benchMatrixPayload.job.jobID
        let benchMatrixSummaryCSVPath = try await exportBenchMatrixSummaryCSV(
            jobID: benchMatrixJobID,
            outputURL: exportsRoot.appendingPathComponent("bench-matrix-summary.csv")
        )
        let benchMatrixRequestsCSVPath = try await exportBenchMatrixRequestsCSV(
            jobID: benchMatrixJobID,
            outputURL: exportsRoot.appendingPathComponent("bench-matrix-requests.csv")
        )

        viewModel.updateSelectedServerSessionModelID(derivedModelID)
        viewModel.selectedEvaluationModelID = derivedModelID
        viewModel.selectedEvaluationSuiteIDs = Set(config.evaluationSuites)
        viewModel.evaluationSampleSize = "4"
        let evaluationStartedAt = Date()
        let evaluationJobID = try await runEvaluation(modelID: derivedModelID)
        timings["phase8.ui.evaluation_run_ms"] = elapsedMS(since: evaluationStartedAt)
        let evaluationSummaryCSVPath = try await exportEvaluationSummaryCSV(
            jobID: evaluationJobID,
            outputURL: exportsRoot.appendingPathComponent("evaluation-summary.csv")
        )
        let evaluationSamplesCSVPath = try await exportEvaluationSamplesCSV(
            jobID: evaluationJobID,
            outputURL: exportsRoot.appendingPathComponent("evaluation-samples.csv")
        )
        let evaluationSamplesJSONLPath = try await exportEvaluationSamplesJSONL(
            jobID: evaluationJobID,
            outputURL: exportsRoot.appendingPathComponent("evaluation-samples.jsonl")
        )

        await viewModel.refreshDesktopFoundation()
        viewModel.selectSurface(.server)
        viewModel.selectServerSession(id: serverSessionID)

        let renderStartedAt = Date()
        do {
            try renderer.render(viewModel: viewModel, to: screenshotURL, size: screenshotSize)
        } catch {
            throw Phase8WindowUIAcceptanceError.screenshotRenderFailed(String(describing: error))
        }
        timings["phase8.ui.snapshot_render_ms"] = elapsedMS(since: renderStartedAt)
        timings["phase8.ui.cli_bridge_ms"] = totalCLIBridgeMS(from: timings)

        let bundle = Phase8WindowUIAcceptanceBundle(
            schemaVersion: phase8WindowUISchemaVersion,
            surface: "window_ui",
            timestamp: config.timestamp,
            repoRoot: config.repoRoot,
            melixHome: config.melixHome,
            modelID: materializeReceipt.modelID,
            managedModelPath: materializeReceipt.managedModelPath,
            sourceKind: materializeReceipt.sourceKind,
            sourceLocator: materializeReceipt.sourceLocator,
            serverSessionID: serverSessionID,
            derivedModelID: derivedModelID,
            trainingFixture: config.trainingFixture,
            benchmarkSuites: config.benchSuites,
            matrixSuites: config.matrixSuites,
            evaluationSuites: config.evaluationSuites,
            evaluationDataset: config.evaluationDataset,
            cliEvidenceBundlePath: config.cliEvidenceBundlePath,
            screenshotPath: screenshotURL.path,
            baseChatAssistantText: baseChatReceipt.assistantText,
            derivedChatAssistantText: derivedChatReceipt.assistantText,
            loraTrainJobID: loraTrainJobID,
            loraActivateJobID: loraActivateJobID,
            benchJobID: benchJobID,
            benchCSVPath: benchCSVPath,
            benchMatrixJobID: benchMatrixJobID,
            benchMatrixSummaryCSVPath: benchMatrixSummaryCSVPath,
            benchMatrixRequestsCSVPath: benchMatrixRequestsCSVPath,
            evaluationJobID: evaluationJobID,
            evaluationSummaryCSVPath: evaluationSummaryCSVPath,
            evaluationSamplesCSVPath: evaluationSamplesCSVPath,
            evaluationSamplesJSONLPath: evaluationSamplesJSONLPath,
            timings: timings,
            uiState: Phase8WindowUIAcceptanceUIState(
                selectedSurface: viewModel.selectedSurface.rawValue,
                selectedToolSection: viewModel.selectedToolSection.rawValue,
                selectedServerSessionID: viewModel.selectedServerSession?.id ?? "",
                selectedServerLifecycle: viewModel.selectedServerSession?.lifecycle.rawValue ?? ""
            )
        )

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        encoder.keyEncodingStrategy = .convertToSnakeCase
        try encoder.encode(bundle).write(to: bundleURL)

        return Phase8WindowUIAcceptanceResult(
            bundlePath: bundleURL.path,
            screenshotPath: screenshotURL.path,
            cliEvidenceBundlePath: config.cliEvidenceBundlePath,
            modelID: materializeReceipt.modelID
        )
    }

    private func materializeModel() async throws -> ManagedModelReceipt {
        if config.localModelPath.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false {
            let receipt = try await cliWorkflowRunner.importModel(
                path: config.localModelPath,
                modelID: config.modelID,
                modelKind: "text",
                revision: "main"
            )
            _ = try await cliWorkflowRunner.run(.modelRootsRescan(.init(json: true)))
            return receipt
        }

        await viewModel.downloadHubModel(repoID: config.modelID)
        guard
            let manifestJSON = viewModel.lastModelOperation?.manifestJson.data(using: .utf8),
            let receipt = try? JSONDecoder().decode(ManagedModelReceipt.self, from: manifestJSON)
        else {
            throw Phase8WindowUIAcceptanceError.missingManagedReceipt
        }
        return receipt
    }

    private func prepareServerSession(modelID: String) async throws -> String {
        await viewModel.refreshDesktopFoundation()
        if viewModel.serverSessions.isEmpty {
            viewModel.createServerSession()
            try await waitFor("server session creation") {
                self.viewModel.serverSessions.isEmpty == false
            }
        }

        let serverSessionID: String
        if viewModel.serverSessions.contains(where: { $0.id == config.serverSessionID }) {
            serverSessionID = config.serverSessionID
        } else if let first = viewModel.serverSessions.first?.id {
            serverSessionID = first
        } else {
            throw Phase8WindowUIAcceptanceError.missingServerSession(config.serverSessionID)
        }

        viewModel.selectServerSession(id: serverSessionID)
        try await waitFor("server session selection") {
            self.viewModel.selectedServerSession?.id == serverSessionID
        }
        viewModel.updateSelectedServerSessionModelID(modelID)
        return serverSessionID
    }

    private func runChat(modelID: String, message: String) async throws -> ChatRunReceipt {
        try await cliWorkflowRunner.decodeJSON(
            ChatRunReceipt.self,
            command: .chatRun(.init(modelID: modelID, message: message, systemPrompt: "", serverSessionID: "", json: true))
        )
    }

    private func runLoraTrain(modelID: String) async throws -> MelixCLIModelOperationManifestPayload {
        try await cliWorkflowRunner.decodeJSON(
            MelixCLIModelOperationManifestPayload.self,
            command: .loraTrain(
                .init(
                    modelID: modelID,
                    datasetSourceKind: viewModel.loraDatasetSourceKind.rawValue,
                    datasetURI: normalizedString(viewModel.loraDatasetURI) ?? config.trainingFixture,
                    adapterName: normalizedString(viewModel.loraAdapterName) ?? phase8AdapterName,
                    targetRepo: normalizedString(viewModel.loraTargetRepo) ?? "",
                    trainingMode: "",
                    parameters: loraTrainingParameters(),
                    json: true
                )
            )
        )
    }

    private func runLoraActivate(
        modelID: String,
        adapterPath: String
    ) async throws -> MelixCLIModelOperationManifestPayload {
        try await cliWorkflowRunner.decodeJSON(
            MelixCLIModelOperationManifestPayload.self,
            command: .loraActivate(
                .init(
                    modelID: modelID,
                    adapterPath: adapterPath,
                    derivedModelAlias: normalizedString(viewModel.loraDerivedModelAlias) ?? "",
                    json: true
                )
            )
        )
    }

    private func deriveActivatedModelID(from manifest: MelixCLIModelOperationManifestPayload) throws -> String {
        guard let derivedModelID = manifest.derivedModelID, derivedModelID.isEmpty == false else {
            throw Phase8WindowUIAcceptanceError.missingDerivedModelID
        }
        return derivedModelID
    }

    private func resolveAdapterManifestPath(
        from manifest: MelixCLIModelOperationManifestPayload
    ) throws -> String {
        if let artifactPath = normalizedString(manifest.artifactPath) {
            return artifactPath
        }
        if let outputPath = normalizedString(manifest.outputPath),
           outputPath.hasSuffix(".json") {
            return outputPath
        }

        let weightsPath = normalizedString(manifest.weightsPath)
            ?? {
                guard let outputPath = normalizedString(manifest.outputPath),
                      outputPath.hasSuffix(".json") == false else {
                    return nil
                }
                return outputPath
            }()
        guard let weightsPath else {
            throw Phase8WindowUIAcceptanceError.missingAdapterManifestPath
        }

        var jobRoot = URL(fileURLWithPath: weightsPath).deletingLastPathComponent()
        if jobRoot.lastPathComponent == "adapter" {
            jobRoot.deleteLastPathComponent()
        }
        return jobRoot.appendingPathComponent("train_lora.adapter.json").path
    }

    private func runBench(modelID: String) async throws -> MelixCLIBenchRunPayload {
        try await cliWorkflowRunner.decodeJSON(
            MelixCLIBenchRunPayload.self,
            command: .benchRun(
                .init(
                    modelID: modelID,
                    suites: config.benchSuites,
                    contextLengths: [phase8BenchContextLength],
                    generationLength: phase8BenchGenerationLength,
                    batchSizes: [phase8BenchBatchSize],
                    repeats: 1,
                    parameters: ["sample_size": phase8BenchSampleSize],
                    json: true
                )
            )
        )
    }

    private func benchmarkJobID(from reportPath: String) throws -> String {
        guard let normalized = normalizedString(reportPath) else {
            throw Phase8WindowUIAcceptanceError.workflowFailed(
                "Benchmark run did not return a report_path with a job directory."
            )
        }
        let jobID = URL(fileURLWithPath: normalized)
            .deletingLastPathComponent()
            .lastPathComponent
            .trimmingCharacters(in: .whitespacesAndNewlines)
        guard jobID.isEmpty == false else {
            throw Phase8WindowUIAcceptanceError.workflowFailed(
                "Benchmark run did not return a report_path with a job directory."
            )
        }
        return jobID
    }

    private func exportBenchCSV(jobID: String, outputURL: URL) async throws -> String {
        let response = try await cliWorkflowRunner.decodeJSON(
            MelixCLIExportResponse.self,
            command: .benchExportCSV(.init(jobID: jobID, outputPath: outputURL.path, json: true))
        )
        return try resolveExportPath(response.outputPath, description: "benchmark csv")
    }

    private func runBenchMatrix(modelID: String) async throws -> MelixCLIBenchmarkMatrixRunPayload {
        try await cliWorkflowRunner.decodeJSON(
            MelixCLIBenchmarkMatrixRunPayload.self,
            command: .benchMatrixRun(
                .init(
                    modelID: modelID,
                    taskKind: "text-generation",
                    suites: config.matrixSuites,
                    contextLengths: [phase8BenchContextLength],
                    generationLengths: [phase8BenchGenerationLength],
                    batchSizes: [phase8BenchBatchSize],
                    cacheProfiles: [phase8MatrixCacheProfile],
                    reasoningModes: [phase8MatrixReasoningMode],
                    structuredOutputModes: [phase8MatrixStructuredOutputMode],
                    concurrencyLevels: [phase8MatrixConcurrencyLevel],
                    repeats: 1,
                    requests: phase8MatrixRequests,
                    durationSeconds: 0,
                    allowLargeMatrix: false,
                    json: true
                )
            )
        )
    }

    private func exportBenchMatrixSummaryCSV(jobID: String, outputURL: URL) async throws -> String {
        let response = try await cliWorkflowRunner.decodeJSON(
            MelixCLIExportResponse.self,
            command: .benchMatrixExportSummaryCSV(.init(jobID: jobID, outputPath: outputURL.path, json: true))
        )
        return try resolveExportPath(response.outputPath, description: "benchmark matrix summary csv")
    }

    private func exportBenchMatrixRequestsCSV(jobID: String, outputURL: URL) async throws -> String {
        let response = try await cliWorkflowRunner.decodeJSON(
            MelixCLIExportResponse.self,
            command: .benchMatrixExportRequestsCSV(.init(jobID: jobID, outputPath: outputURL.path, json: true))
        )
        return try resolveExportPath(response.outputPath, description: "benchmark matrix requests csv")
    }

    private func runEvaluation(modelID: String) async throws -> String {
        let payloads = try await cliWorkflowRunner.decodeJSON(
            [MelixCLIEvaluationRunPayload].self,
            command: .evalRun(
                .init(
                    modelID: modelID,
                    suites: config.evaluationSuites,
                    datasetID: config.evaluationDataset,
                    sampleSize: phase8EvaluationSampleSize,
                    parameters: [
                        "scoring_mode": phase8EvaluationScoringMode,
                    ],
                    json: true
                )
            )
        )
        guard let jobID = payloads.first?.job.jobID, jobID.isEmpty == false else {
            throw Phase8WindowUIAcceptanceError.workflowFailed("Evaluation run did not return any job payloads.")
        }
        return jobID
    }

    private func exportEvaluationSummaryCSV(jobID: String, outputURL: URL) async throws -> String {
        let response = try await cliWorkflowRunner.decodeJSON(
            MelixCLIExportResponse.self,
            command: .evalExportSummaryCSV(.init(jobID: jobID, outputPath: outputURL.path, json: true))
        )
        return try resolveExportPath(response.outputPath, description: "evaluation summary csv")
    }

    private func exportEvaluationSamplesCSV(jobID: String, outputURL: URL) async throws -> String {
        let response = try await cliWorkflowRunner.decodeJSON(
            MelixCLIExportResponse.self,
            command: .evalExportSamplesCSV(.init(jobID: jobID, outputPath: outputURL.path, json: true))
        )
        return try resolveExportPath(response.outputPath, description: "evaluation samples csv")
    }

    private func exportEvaluationSamplesJSONL(jobID: String, outputURL: URL) async throws -> String {
        let response = try await cliWorkflowRunner.decodeJSON(
            MelixCLIExportResponse.self,
            command: .evalExportSamplesJSONL(.init(jobID: jobID, outputPath: outputURL.path, json: true))
        )
        return try resolveExportPath(response.outputPath, description: "evaluation samples jsonl")
    }

    private func resolveExportPath(_ outputPath: String, description: String) throws -> String {
        guard let normalized = normalizedString(outputPath) else {
            throw Phase8WindowUIAcceptanceError.workflowFailed("Window UI acceptance did not produce \(description).")
        }
        guard fileManager.fileExists(atPath: normalized) else {
            throw Phase8WindowUIAcceptanceError.workflowFailed(
                "Window UI acceptance expected \(description) at \(normalized), but the file was missing."
            )
        }
        return normalized
    }

    private func waitFor(
        _ description: String,
        timeout: Duration = .seconds(30),
        pollInterval: Duration = .milliseconds(50),
        condition: @escaping @MainActor () -> Bool
    ) async throws {
        let baselineError = viewModel.lastError
        let baselineCLIWorkflowFailure = viewModel.lastCLIWorkflowFailure
        let deadline = ContinuousClock.now + timeout
        while ContinuousClock.now < deadline {
            if condition() {
                return
            }
            if let failure = viewModel.lastCLIWorkflowFailure,
               failure != baselineCLIWorkflowFailure {
                throw Phase8WindowUIAcceptanceError.workflowFailed(failure.detail)
            }
            if let lastError = viewModel.lastError,
               lastError != baselineError {
                throw Phase8WindowUIAcceptanceError.workflowFailed(lastError)
            }
            try await Task.sleep(for: pollInterval)
        }
        throw Phase8WindowUIAcceptanceError.timeout(description)
    }

    private func elapsedMS(since startedAt: Date) -> Double {
        Date().timeIntervalSince(startedAt) * 1_000
    }

    private func totalCLIBridgeMS(from timings: [String: Double]) -> Double {
        [
            "phase8.ui.managed_materialize_ms",
            "phase8.ui.session_rebind_ms",
            "phase8.ui.base_chat_roundtrip_ms",
            "phase8.ui.derived_chat_roundtrip_ms",
            "phase8.ui.lora_train_ms",
            "phase8.ui.lora_activate_ms",
            "phase8.ui.bench_run_ms",
            "phase8.ui.bench_matrix_run_ms",
            "phase8.ui.evaluation_run_ms",
        ].reduce(0) { partial, key in
            partial + (timings[key] ?? 0)
        }
    }

    private func loraTrainingParameters() -> [String: String] {
        var parameters: [String: String] = [:]

        if viewModel.loraDatasetSourceKind == .huggingFaceDataset {
            assignNormalized(viewModel.loraHFDatasetPath, for: "hf_dataset_path", into: &parameters)
            assignNormalized(viewModel.loraHFDatasetName, for: "hf_dataset_name", into: &parameters)
            assignNormalized(viewModel.loraHFDatasetRevision, for: "hf_dataset_revision", into: &parameters)
            assignNormalized(viewModel.loraHFTrainSplit, for: "hf_train_split", into: &parameters)
            assignNormalized(viewModel.loraHFValidSplit, for: "hf_valid_split", into: &parameters)
            assignNormalized(viewModel.loraChatFeature, for: "chat_feature", into: &parameters)
            assignNormalized(viewModel.loraPromptFeature, for: "prompt_feature", into: &parameters)
            assignNormalized(viewModel.loraCompletionFeature, for: "completion_feature", into: &parameters)
            assignNormalized(viewModel.loraTextFeature, for: "text_feature", into: &parameters)
        }

        assignNormalized(viewModel.loraRank, for: "rank", into: &parameters)
        assignNormalized(viewModel.loraAlpha, for: "alpha", into: &parameters)
        assignNormalized(viewModel.loraDropout, for: "dropout", into: &parameters)
        assignNormalized(viewModel.loraTargetModules, for: "target_modules", into: &parameters)
        assignNormalized(viewModel.loraNumLayers, for: "num_layers", into: &parameters)
        assignNormalized(viewModel.loraBatchSize, for: "batch_size", into: &parameters)
        assignNormalized(viewModel.loraEpochs, for: "epochs", into: &parameters)
        assignNormalized(viewModel.loraLearningRate, for: "learning_rate", into: &parameters)
        assignNormalized(viewModel.loraMaxSeqLength, for: "max_seq_length", into: &parameters)
        assignNormalized(viewModel.loraDerivedModelAlias, for: "derived_model_alias", into: &parameters)
        parameters["response_only"] = viewModel.loraResponseOnly ? "true" : "false"
        parameters["mask_prompt"] = viewModel.loraMaskPrompt ? "true" : "false"
        parameters["gradient_checkpointing"] = viewModel.loraGradientCheckpointing ? "true" : "false"
        return parameters
    }

    private func normalizedString(_ value: String?) -> String? {
        guard let value else {
            return nil
        }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    private func assignNormalized(
        _ value: String,
        for key: String,
        into parameters: inout [String: String]
    ) {
        guard let normalized = normalizedString(value) else {
            return
        }
        parameters[key] = normalized
    }

    private func ensureOperationRecorded(
        _ operation: String,
        description: String,
        timeout: Duration = .seconds(2),
        pollInterval: Duration = .milliseconds(50)
    ) async throws {
        let deadline = ContinuousClock.now + timeout
        while ContinuousClock.now < deadline {
            if viewModel.lastModelOperation?.operation == operation {
                return
            }
            if let failure = viewModel.lastCLIWorkflowFailure {
                throw Phase8WindowUIAcceptanceError.workflowFailed(failure.detail)
            }
            if let lastError = viewModel.lastError, lastError.isEmpty == false {
                throw Phase8WindowUIAcceptanceError.workflowFailed(lastError)
            }
            try await Task.sleep(for: pollInterval)
        }
        let detail = [
            "expected_operation=\(operation)",
            "last_model_operation=\(viewModel.lastModelOperation?.operation ?? "nil")",
            "selected_lora_model_id=\(viewModel.selectedLoraModelID)",
            "lora_capable_models=\(viewModel.loraCapableModels.map { $0.modelID }.joined(separator: ","))",
            "last_error=\(viewModel.lastError ?? "nil")",
            "cli_failure=\(viewModel.lastCLIWorkflowFailure?.detail ?? "nil")",
        ].joined(separator: " ")
        throw Phase8WindowUIAcceptanceError.timeout("\(description) (\(detail))")
    }

    private func resolvedManagedModelRootPath() -> String {
        let environment = ProcessInfo.processInfo.environment
        if let explicit = environment["MELIX_MANAGED_MODEL_ROOT"]?.trimmingCharacters(in: .whitespacesAndNewlines),
           explicit.isEmpty == false {
            return explicit
        }
        return URL(fileURLWithPath: config.melixHome, isDirectory: true)
            .appendingPathComponent("models/default-managed", isDirectory: true)
            .path
    }

    private func managedModelVisibilityDescription(modelID: String) -> String {
        [
            "managed model visibility",
            "model_id=\(modelID)",
            "server_model_options=\(viewModel.serverModelOptions.map(\.modelID).joined(separator: ","))",
            "registry_models=\(viewModel.registryCatalogModels.map(\.modelID).joined(separator: ","))",
            "registry_roots=\(viewModel.registryConfiguredRootPaths.joined(separator: ","))",
            "last_error=\(viewModel.lastError ?? "nil")",
        ].joined(separator: " ")
    }
}
