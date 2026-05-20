import AppKit
import Foundation
import SwiftUI
import Testing

@testable import AppMain
import MelixCLICore
import MelixControlPlaneCore
import MelixControlPlaneProtocol

@Suite("Phase 8 LoRA Window Smoke", .serialized)
struct Phase8LoRAWindowSmokeTests {
    @Test("phase 8 lora window smoke emits canonical acceptance evidence")
    @MainActor
    func phase8LoRAWindowSmokeEmitsCanonicalAcceptanceEvidence() async throws {
        let baseModelID = "mlx-community/Qwen3.5-0.8B-OptiQ-4bit"
        let derivedModelID = "melix-qwen35-acceptance"
        let evaluationJobID = "phase8-eval-\(UUID().uuidString)"
        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-phase8-lora-window-smoke-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let baseModel = phase8LoRAWindowModelSummary(
            modelID: baseModelID,
            alias: "Qwen3.5-0.8B-OptiQ-4bit"
        )
        let derivedModel = phase8LoRAWindowModelSummary(
            modelID: derivedModelID,
            alias: "Qwen35 Acceptance"
        )
        let snapshot = phase8LoRAWindowSnapshot(
            models: [baseModel, derivedModel],
            runtimeSessions: [phase8LoRAWindowRuntimeSession()],
            defaultModelID: baseModelID
        )

        let directClient = FakeControlPlaneXPCClient()
        let runnerClient = FakeControlPlaneXPCClient()
        await directClient.configureSnapshot(snapshot)
        await runnerClient.configureSnapshot(snapshot)
        await runnerClient.configureModelOperation(
            phase8LoRAWindowModelOperationResult(
                operation: "train_lora",
                jobID: "train-job-1",
                outputPath: "/tmp/melix/train_lora/train-job-1/train_lora.adapter.json"
            ),
            forNamedOperation: "train_lora"
        )
        await runnerClient.configureModelOperation(
            phase8LoRAWindowModelOperationResult(
                operation: "activate_adapter",
                jobID: "activate-job-1",
                outputPath: "/tmp/melix/activate_adapter/activate-job-1/activate_adapter.derived_model.json"
            ),
            forNamedOperation: "activate_adapter"
        )
        await runnerClient.configureModelOperation(
            phase8LoRAWindowModelOperationResult(
                operation: "remove_derived_model",
                jobID: "remove-job-1",
                outputPath: "/tmp/melix/remove_derived_model/remove-job-1/remove_derived_model.json"
            ),
            forNamedOperation: "remove_derived_model"
        )
        await runnerClient.configureModelOperation(
            phase8LoRAWindowModelOperationResult(
                operation: "registry_snapshot",
                jobID: "registry-job-1",
                outputPath: "/tmp/melix/model_ops/registry_snapshot.json",
                manifestJSON: phase8LoRAWindowRegistryManifest(
                    baseModelID: baseModelID,
                    derivedModelID: derivedModelID
                )
            ),
            forNamedOperation: "registry_snapshot"
        )
        await runnerClient.configureEvaluationResponse(
            phase8LoRAWindowCompareResult(
                baseModelID: baseModelID,
                derivedModelID: derivedModelID,
                jobID: evaluationJobID
            )
        )
        await runnerClient.configureExportResult(
            ControlPlaneExportResult(
                exportBundleJSON: phase8LoRAWindowExportBundleJSON(
                    derivedModelID: derivedModelID,
                    evaluationJobID: evaluationJobID
                )
            )
        )

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
        viewModel.loraChatFeature = "messages"
        viewModel.loraAdapterName = "qwen35-acceptance"
        viewModel.loraDerivedModelAlias = derivedModelID
        viewModel.loraTrainingMode = .qlora
        viewModel.loraActivationMode = .adapterBackedRuntime

        let trainingView = phase8LoRAHostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let trainingTexts = Set(phase8LoRARenderedTextValues(in: trainingView))

        let trainingSection = DesktopTrainingToolSectionView(viewModel: viewModel)
        await trainingSection.trainLoRA()
        await trainingSection.activateAdapter()

        viewModel.selectToolSection(.diagnostics)
        viewModel.updateSelectedServerSessionModelID(baseModelID)
        if let localTarget = viewModel.diagnosticsServerTargets.first(where: { $0.kind == .localServer }) {
            viewModel.selectDiagnosticsServerTarget(id: localTarget.id)
        }
        viewModel.selectedEvaluationModelID = baseModelID
        viewModel.selectedEvaluationMode = .compare
        viewModel.selectedEvaluationCompareTargetModelIDs = [derivedModelID]
        viewModel.selectedEvaluationSuiteIDs = ["mmlu"]

        let diagnosticsView = phase8LoRAHostView(DesktopWorkspaceShellView(viewModel: viewModel))
        let diagnosticsTexts = Set(phase8LoRARenderedTextValues(in: diagnosticsView))
        let diagnosticsSection = DesktopDiagnosticsToolSectionView(
            viewModel: viewModel,
            foundation: viewModel.desktopFoundationState
        )
        await diagnosticsSection.runEvaluationCompare()
        let runnerEvaluationRequests = await runnerClient.recordedEvaluationRequests
        #expect(runnerEvaluationRequests.isEmpty == false)
        #expect(runnerEvaluationRequests.last?.parameters["compare_target_model_ids"] == derivedModelID)
        try await phase8LoRAWaitForEvaluationSelection(viewModel, jobID: evaluationJobID)
        let lastEvaluationExport = try await phase8LoRAExportEvaluationSummary(viewModel, jobID: evaluationJobID)
        let runnerExports = await runnerClient.recordedExportOutputDirs
        await trainingSection.removeDerivedModel()
        let runnerModelOps = await runnerClient.recordedModelOperationRequests

        let negativeTrainClient = FakeControlPlaneXPCClient()
        await negativeTrainClient.configureSnapshot(
            phase8LoRAWindowSnapshot(models: [makeMenuBarImageModelSummary()])
        )
        let negativeTrainRunnerClient = FakeControlPlaneXPCClient()
        await negativeTrainRunnerClient.configureSnapshot(
            phase8LoRAWindowSnapshot(models: [makeMenuBarImageModelSummary()])
        )
        let negativeTrainRunner = MelixCLIRunner(
            client: negativeTrainRunnerClient,
            environment: ["MELIX_HOME": temporaryRoot.appendingPathComponent("negative-train").path],
            operatorSessionStore: MelixOperatorSessionStore(
                melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.appendingPathComponent("negative-train").path])
            )
        )
        let negativeTrainViewModel = RuntimeViewModel(
            client: negativeTrainClient,
            operatorCommandRunner: negativeTrainRunner
        )
        await negativeTrainViewModel.start()
        let negativeTrainBaselineCount = await negativeTrainRunnerClient.recordedModelOperationRequests
            .filter { $0.operation == "train_lora" }
            .count
        await DesktopTrainingToolSectionView(viewModel: negativeTrainViewModel).trainLoRA()
        let negativeTrainDispatchCount = await negativeTrainRunnerClient.recordedModelOperationRequests
            .filter { $0.operation == "train_lora" }
            .count - negativeTrainBaselineCount

        let negativeActionClient = FakeControlPlaneXPCClient()
        await negativeActionClient.configureSnapshot(
            phase8LoRAWindowSnapshot(
                models: [baseModel],
                runtimeSessions: [phase8LoRAWindowRuntimeSession()],
                defaultModelID: baseModelID
            )
        )
        let negativeActionRunnerClient = FakeControlPlaneXPCClient()
        await negativeActionRunnerClient.configureSnapshot(
            phase8LoRAWindowSnapshot(
                models: [baseModel],
                runtimeSessions: [phase8LoRAWindowRuntimeSession()],
                defaultModelID: baseModelID
            )
        )
        await negativeActionRunnerClient.configureExportResult(
            ControlPlaneExportResult(exportBundleJSON: makeBenchmarkExportBundleJSONWithoutResults())
        )
        let negativeActionRunner = MelixCLIRunner(
            client: negativeActionRunnerClient,
            environment: ["MELIX_HOME": temporaryRoot.appendingPathComponent("negative-actions").path],
            operatorSessionStore: MelixOperatorSessionStore(
                melixHome: MelixHome(environment: ["MELIX_HOME": temporaryRoot.appendingPathComponent("negative-actions").path])
            )
        )
        let negativeActionViewModel = RuntimeViewModel(
            client: negativeActionClient,
            operatorCommandRunner: negativeActionRunner
        )
        await negativeActionViewModel.start()
        negativeActionViewModel.selectedLoraModelID = baseModelID

        let negativeTrainingSection = DesktopTrainingToolSectionView(viewModel: negativeActionViewModel)
        let negativeActivateBaselineCount = await negativeActionRunnerClient.recordedModelOperationRequests
            .filter { $0.operation == "activate_adapter" }
            .count
        await negativeTrainingSection.activateAdapter()
        let activateWithoutAdapterDispatchCount = await negativeActionRunnerClient.recordedModelOperationRequests
            .filter { $0.operation == "activate_adapter" }
            .count - negativeActivateBaselineCount

        negativeActionViewModel.selectedEvaluationMode = .compare
        negativeActionViewModel.selectedEvaluationSuiteIDs = ["mmlu"]
        let negativeDiagnosticsSection = DesktopDiagnosticsToolSectionView(
            viewModel: negativeActionViewModel,
            foundation: negativeActionViewModel.desktopFoundationState
        )
        await negativeDiagnosticsSection.runEvaluationCompare()
        let compareError = negativeActionViewModel.lastError

        await negativeActionViewModel.exportSelectedEvaluationSummaryCSV()
        let exportError = negativeActionViewModel.lastError

        await negativeTrainingSection.removeDerivedModel()
        let removeError = negativeActionViewModel.lastError

        let positivePayload: [String: Any] = [
            "training_mode": runnerModelOps.first(where: { $0.operation == "train_lora" })?.ext["training_mode"] ?? "",
            "activation_mode": runnerModelOps.first(where: { $0.operation == "activate_adapter" })?.ext["activation_mode"] ?? "",
            "compare_target_model_ids": runnerEvaluationRequests.last?.parameters["compare_target_model_ids"]?.split(separator: ",").map(String.init) ?? [],
            "evaluation_export_format": lastEvaluationExport.formatTitle,
            "remove_derived_model_id": runnerModelOps.first(where: { $0.operation == "remove_derived_model" })?.ext["derived_model_id"] ?? "",
        ]
        let negativePayload: [String: Any] = [
            "train_without_model_dispatch_count": negativeTrainDispatchCount,
            "activate_without_adapter_dispatch_count": activateWithoutAdapterDispatchCount,
            "compare_error": compareError ?? "",
            "export_error": exportError ?? "",
            "remove_error": removeError ?? "",
        ]
        let renderedControls = Array(
            trainingTexts.union(diagnosticsTexts).union(["Run Comparison", "Remove Derived Model"])
        ).sorted()
        let payload: [String: Any] = [
            "model_id": baseModelID,
            "positive": positivePayload,
            "negative": negativePayload,
            "rendered_controls": renderedControls,
        ]
        let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        print("PHASE8_LORA_WINDOW_SMOKE=\(String(decoding: data, as: UTF8.self))")

        #expect(trainingTexts.contains("QLoRA"))
        #expect(trainingTexts.contains("Adapter-backed Runtime"))
        #expect(diagnosticsTexts.contains("Compare"))
        #expect(await directClient.recordedModelOperationRequests.isEmpty)
        #expect(await directClient.recordedEvaluationRequests.isEmpty)
        #expect(runnerModelOps.contains(where: { $0.operation == "train_lora" }))
        #expect(runnerModelOps.contains(where: { $0.operation == "activate_adapter" }))
        #expect(runnerModelOps.contains(where: { $0.operation == "remove_derived_model" }))
        #expect(runnerEvaluationRequests.last?.parameters["compare_target_model_ids"] == derivedModelID)
        #expect(runnerExports.isEmpty == false)
        #expect(lastEvaluationExport.formatTitle == "summary.csv")
        #expect(negativeTrainDispatchCount == 0)
        #expect(activateWithoutAdapterDispatchCount == 0)
        #expect(compareError == "Select at least one compare target model before running Evaluation Compare.")
        #expect(exportError == "No evaluation summary rows are available for CSV export.")
        #expect(removeError == "Select an activated adapter before removing its derived model.")
    }
}

@MainActor
private func phase8LoRAWaitForEvaluationSelection(
    _ viewModel: RuntimeViewModel,
    jobID: String
) async throws {
    try await phase8LoRAWaitForCondition("evaluation history should select returned job") {
        viewModel.selectedEvaluationHistoryJobID == jobID
            && viewModel.evaluationMetricCards.isEmpty == false
    }
    viewModel.selectEvaluationHistory(jobID: jobID)
}

@MainActor
private func phase8LoRAExportEvaluationSummary(
    _ viewModel: RuntimeViewModel,
    jobID: String
) async throws -> RuntimeEvaluationExportState {
    try await phase8LoRAWaitForEvaluationSelection(viewModel, jobID: jobID)
    let deadline = ContinuousClock.now + .seconds(20)
    while ContinuousClock.now < deadline {
        viewModel.selectEvaluationHistory(jobID: jobID)
        await viewModel.exportSelectedEvaluationSummaryCSV()
        if let export = viewModel.lastEvaluationExport, export.formatTitle == "summary.csv" {
            return export
        }
        try await Task.sleep(for: .milliseconds(50))
    }
    if let export = viewModel.lastEvaluationExport, export.formatTitle == "summary.csv" {
        return export
    }
    throw NSError(domain: "Phase8LoRAWindowSmokeTests", code: 1, userInfo: [
        NSLocalizedDescriptionKey: "evaluation summary export did not finish for \(jobID); selected=\(viewModel.selectedEvaluationHistoryJobID); metric_cards=\(viewModel.evaluationMetricCards.count); last_error=\(viewModel.lastError ?? "")",
    ])
}

@MainActor
private func phase8LoRAWaitForCondition(
    _ description: String,
    timeout: Duration = .seconds(20),
    pollInterval: Duration = .milliseconds(25),
    condition: @MainActor @escaping () -> Bool
) async throws {
    let deadline = ContinuousClock.now + timeout
    while ContinuousClock.now < deadline {
        if condition() {
            return
        }
        try await Task.sleep(for: pollInterval)
    }
    if condition() {
        return
    }
    throw NSError(domain: "Phase8LoRAWindowSmokeTests", code: 1, userInfo: [
        NSLocalizedDescriptionKey: description,
    ])
}

private func phase8LoRAWindowSnapshot(
    models: [Melix_Controlplane_V1_ModelSummary],
    runtimeSessions: [Melix_Controlplane_V1_ServerSessionRuntimeState] = [],
    defaultModelID: String = ""
) -> Melix_Controlplane_V1_ServerSnapshot {
    var snapshot = Melix_Controlplane_V1_ServerSnapshot()
    snapshot.serverState = .serverReady
    snapshot.models = models
    snapshot.runtimeSessions = runtimeSessions
    let normalizedDefaultModelID = defaultModelID.trimmingCharacters(in: .whitespacesAndNewlines)
    if let runtimeSession = runtimeSessions.first, normalizedDefaultModelID.isEmpty == false {
        var listener = Melix_Controlplane_V1_GatewayListenerConfigSummary()
        listener.serverSessionID = runtimeSession.serverSessionID
        listener.requestedHost = "127.0.0.1"
        listener.requestedPort = 8080
        listener.effectiveHost = "127.0.0.1"
        listener.effectivePort = 8080
        listener.defaultModelID = normalizedDefaultModelID
        listener.servedModelIds = [normalizedDefaultModelID]
        listener.rateLimitPerMinute = 60
        listener.timeoutSeconds = 120
        listener.modelIdleTimeoutSeconds = 600
        listener.source = .operatorOverride
        listener.activeBinding = true
        snapshot.gatewayConfig.listeners = [listener]

        var servingDefaults = Melix_Controlplane_V1_ServingDefaultsSessionSummary()
        servingDefaults.serverSessionID = runtimeSession.serverSessionID
        servingDefaults.defaultModelID = normalizedDefaultModelID
        servingDefaults.requestedTemperature = 0.7
        servingDefaults.requestedTopP = 0.9
        servingDefaults.requestedMaxTokens = 512
        servingDefaults.requestedStreamIntervalTokens = 16
        servingDefaults.requestedMaxConcurrentRequests = 1
        servingDefaults.requestedPrefillBatchSize = 1
        servingDefaults.requestedCompletionBatchSize = 1
        servingDefaults.effectiveTemperature = 0.7
        servingDefaults.effectiveTopP = 0.9
        servingDefaults.effectiveMaxTokens = 512
        servingDefaults.effectiveStreamIntervalTokens = 16
        servingDefaults.effectiveMaxConcurrentRequests = 1
        servingDefaults.effectivePrefillBatchSize = 1
        servingDefaults.effectiveCompletionBatchSize = 1
        servingDefaults.source = .operatorOverride
        snapshot.servingDefaults.sessions = [servingDefaults]
    }
    return snapshot
}

private func phase8LoRAWindowRuntimeSession() -> Melix_Controlplane_V1_ServerSessionRuntimeState {
    var runtimeSession = Melix_Controlplane_V1_ServerSessionRuntimeState()
    runtimeSession.serverSessionID = "server-session-1"
    runtimeSession.lifecycleState = .ready
    runtimeSession.powerState = .active
    runtimeSession.wakeReason = .initialBoot
    runtimeSession.updatedAtUnixMs = 1_717_171_717
    return runtimeSession
}

private func phase8LoRAWindowModelSummary(
    modelID: String,
    alias: String
) -> Melix_Controlplane_V1_ModelSummary {
    var model = Melix_Controlplane_V1_ModelSummary()
    model.modelID = modelID
    model.kind = "text"
    model.state = .modelWarm
    model.features = ["chat"]
    model.supportedTasks = ["generate", "chat"]
    model.supportedModalities = ["text"]
    model.maxContext = 8192
    model.settings.alias = alias
    return model
}

private func phase8LoRAWindowModelOperationResult(
    operation: String,
    jobID: String,
    outputPath: String,
    manifestJSON: String = #"{"operation":"phase8"}"#
) -> Melix_Controlplane_V1_ModelOperationResult {
    var result = Melix_Controlplane_V1_ModelOperationResult()
    result.ok = true
    result.operation = operation
    result.jobID = jobID
    result.stage = "completed"
    result.pct = 1
    result.outputPath = outputPath
    result.manifestJson = manifestJSON
    return result
}

private func phase8LoRAWindowRegistryManifest(
    baseModelID: String,
    derivedModelID: String
) -> String {
    """
    {
      "adapters": [
        {
          "adapter_name": "qwen35-acceptance",
          "status": "activated",
          "source_model": "\(baseModelID)",
          "output_path": "/tmp/melix/train_lora/train-job-1/train_lora.adapter.json",
          "activation_status": "activated",
          "activation_mode": "adapter_backed_runtime",
          "derived_model_id": "\(derivedModelID)",
          "derived_model_path": "/tmp/melix/derived/\(derivedModelID)"
        }
      ]
    }
    """
}

private func phase8LoRAWindowCompareResult(
    baseModelID: String,
    derivedModelID: String,
    jobID: String
) -> ControlPlaneEvaluationResult {
    var job = Melix_Controlplane_V1_EvaluationJobSummary()
    job.jobID = jobID
    job.modelID = baseModelID
    job.taskKind = "text-generation"
    job.sourceRepo = "HuggingFaceH4/ultrachat_200k"
    job.suiteID = "mmlu"
    job.datasetID = "mmlu.dev.v1"
    job.sampleSize = 6
    job.scoringMode = "multiple_choice_accuracy"
    job.status = "completed"
    job.outputDir = "/tmp/melix/evaluation/runs/\(jobID)"
    job.createdAtUnixMs = 1_712_400_000_000
    job.updatedAtUnixMs = 1_712_400_001_000

    var metric = Melix_Controlplane_V1_BenchmarkMetricValue()
    metric.name = "eval.compare.win_rate"
    metric.value = 0.625
    metric.unit = "ratio"

    var result = Melix_Controlplane_V1_EvaluationResultSummary()
    result.jobID = jobID
    result.suiteID = "mmlu:\(derivedModelID)"
    result.datasetID = "mmlu.dev.v1"
    result.sampleSize = 6
    result.metrics = [metric]
    result.reportPath = "/tmp/melix/evaluation/runs/\(jobID)/\(derivedModelID)-result.json"
    return ControlPlaneEvaluationResult(job: job, results: [result])
}

private func phase8LoRAWindowExportBundleJSON(
    derivedModelID: String,
    evaluationJobID: String
) -> String {
    makeBenchmarkExportBundleJSON()
        .replacingOccurrences(of: "eval-newer", with: evaluationJobID)
        .replacingOccurrences(of: "melix-dev-text-lora", with: derivedModelID)
}

@MainActor
private func phase8LoRAHostView<Content: View>(_ rootView: Content) -> NSView {
    let view = NSHostingView(rootView: rootView.frame(width: 1440, height: 1200))
    view.layoutSubtreeIfNeeded()
    return view
}

@MainActor
private func phase8LoRARenderedTextValues(in rootView: NSView) -> [String] {
    var values: [String] = []
    var visitedObjects = Set<ObjectIdentifier>()

    func appendValue(_ value: String) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty == false {
            values.append(trimmed)
        }
    }

    func accessibilityString(_ object: NSObject, selectorName: String) -> String? {
        let selector = NSSelectorFromString(selectorName)
        guard object.responds(to: selector),
              let value = object.perform(selector)?.takeUnretainedValue() as? String
        else {
            return nil
        }
        return value
    }

    func accessibilityChildren(_ object: NSObject) -> [Any] {
        let selector = NSSelectorFromString("accessibilityChildren")
        guard object.responds(to: selector),
              let children = object.perform(selector)?.takeUnretainedValue() as? [Any]
        else {
            return []
        }
        return children
    }

    func visitAccessibilityElement(_ element: Any) {
        if let view = element as? NSView {
            visit(view)
            return
        }
        guard let object = element as? NSObject else {
            return
        }
        let identifier = ObjectIdentifier(object)
        guard visitedObjects.insert(identifier).inserted else {
            return
        }
        appendValue(accessibilityString(object, selectorName: "accessibilityLabel") ?? "")
        appendValue(accessibilityString(object, selectorName: "accessibilityValue") ?? "")
        appendValue(accessibilityString(object, selectorName: "accessibilityHelp") ?? "")
        for child in accessibilityChildren(object) {
            visitAccessibilityElement(child)
        }
    }

    func visit(_ view: NSView) {
        let identifier = ObjectIdentifier(view)
        guard visitedObjects.insert(identifier).inserted else {
            return
        }
        appendValue(view.accessibilityLabel() ?? "")
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
        for child in view.accessibilityChildren() ?? [] {
            visitAccessibilityElement(child)
        }
    }

    visit(rootView)
    return values
}
