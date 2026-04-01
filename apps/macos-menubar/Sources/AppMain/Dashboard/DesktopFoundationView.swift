import SwiftUI

@MainActor
public struct DesktopFoundationRootView: View {
    private let viewModel: RuntimeViewModel

    public init(viewModel: RuntimeViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        let foundation = viewModel.desktopFoundationState

        TabView {
            DesktopDashboardTabView(foundation: foundation)
                .tabItem {
                    Label("Dashboard", systemImage: "gauge.with.dots.needle.67percent")
                }

            DesktopModelsTabView(foundation: foundation, viewModel: viewModel)
                .tabItem {
                    Label("Models", systemImage: "cube.transparent")
                }

            DesktopToolsTabView(viewModel: viewModel)
                .tabItem {
                    Label("Tools", systemImage: "wrench.and.screwdriver")
                }

            DesktopSettingsTabView(foundation: foundation)
                .tabItem {
                    Label("Settings", systemImage: "slider.horizontal.3")
                }

            DesktopLogsTabView(foundation: foundation)
                .tabItem {
                    Label("Logs", systemImage: "doc.text.magnifyingglass")
                }

            DesktopBenchTabView(foundation: foundation)
                .tabItem {
                    Label("Bench", systemImage: "speedometer")
                }

            DesktopChatTabView(viewModel: viewModel)
                .tabItem {
                    Label("Chat", systemImage: "message")
                }

            DesktopImageTabView(viewModel: viewModel)
                .tabItem {
                    Label("Image", systemImage: "photo.on.rectangle")
                }

            DesktopAPIReferenceTabView(foundation: foundation)
                .tabItem {
                    Label("API", systemImage: "chevron.left.forwardslash.chevron.right")
                }
        }
        .frame(minWidth: 980, minHeight: 680)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button("Refresh") {
                    Task { await viewModel.refreshDesktopFoundation() }
                }
            }
        }
    }
}

struct DesktopDashboardTabView: View {
    let foundation: DesktopFoundationState

    var body: some View {
        let modelRows: [RuntimeModelRow] = foundation.models

        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Text(foundation.title)
                    .font(.largeTitle)
                    .bold()

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 12)], spacing: 12) {
                    ForEach(foundation.dashboardCards) { card in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(card.title)
                                .font(.headline)
                            Text(card.value)
                                .font(.title3)
                                .bold()
                            Text(card.detail)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 12))
                    }
                }

                GroupBox("Scheduler Lanes") {
                    VStack(spacing: 10) {
                        ForEach(foundation.queueLanes) { lane in
                            HStack {
                                VStack(alignment: .leading) {
                                    Text(lane.id)
                                        .font(.headline)
                                    Text(lane.laneClass)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Text("queued \(lane.queuedRequests)")
                                    .monospacedDigit()
                                Text("active \(lane.activeRequests)")
                                    .monospacedDigit()
                                Text("bp \(String(format: "%.2f", lane.backpressure))")
                                    .monospacedDigit()
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                GroupBox("Residency And Memory") {
                    DesktopResidencyRowsSection(models: modelRows)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(20)
        }
    }
}

struct DesktopModelsTabView: View {
    let foundation: DesktopFoundationState
    let viewModel: RuntimeViewModel

    var body: some View {
        List(foundation.models, id: \.modelID) { model in
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.modelID)
                        .font(.headline)
                    Text(model.alias.isEmpty ? "\(model.kind) • \(model.stateText) • \(model.maxContext) ctx" : "\(model.alias) • \(model.stateText) • \(model.maxContext) ctx")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(model.residencyText)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text(model.memoryText)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    if !model.memoryAlertText.isEmpty {
                        Text(model.memoryAlertText)
                            .font(.caption2)
                            .foregroundStyle(.red)
                    }
                    Text("\(model.memoryPolicyText) • \(model.accelerationModeText) • \(model.accelerationProfileID.isEmpty ? "no-profile" : model.accelerationProfileID)")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
                Spacer()
                Button("Latency Profile") {
                    Task { await applyLatencyProfile(to: model) }
                }
                .buttonStyle(.bordered)
                Button(model.actionTitle) {
                    Task { await toggleModelLoad(for: model) }
                }
                .buttonStyle(.borderedProminent)
            }
            .padding(.vertical, 4)
        }
    }

    func applyLatencyProfile(to model: RuntimeModelRow) async {
        await viewModel.updateModelSettings(
            modelID: model.modelID,
            alias: model.alias.isEmpty ? "Melix Text Turbo" : model.alias,
            pinOnLoad: true,
            memoryPolicy: "pinned",
            accelerationMode: "speculative_decode",
            accelerationProfileID: "draft-q4"
        )
    }

    func toggleModelLoad(for model: RuntimeModelRow) async {
        if model.isLoaded {
            await viewModel.unloadModel(modelID: model.modelID)
        } else {
            await viewModel.loadModel(modelID: model.modelID)
        }
    }
}

private struct DesktopResidencyRowsSection: View {
    let models: [RuntimeModelRow]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if models.isEmpty {
                Text("No models discovered.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(models, id: \RuntimeModelRow.id) { (model: RuntimeModelRow) in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(model.modelID)
                                .font(.headline)
                            Spacer()
                            Text(model.stateText)
                                .font(.caption)
                                .foregroundStyle(model.memoryAlertText.isEmpty ? Color.secondary : Color.orange)
                        }
                        Text(model.residencyText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(model.memoryText)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                        if !model.memoryAlertText.isEmpty {
                            Text(model.memoryAlertText)
                                .font(.caption2)
                                .foregroundStyle(.red)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
    }
}

struct DesktopToolsTabView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let primaryModel = viewModel.primaryModel {
                GroupBox("Primary Model") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(primaryModel.modelID)
                            .font(.headline)
                        Text(primaryModel.alias.isEmpty ? primaryModel.kind : primaryModel.alias)
                            .foregroundStyle(.secondary)
                        HStack(spacing: 8) {
                            Text("Quant Profile")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Picker(
                                "Quant Profile",
                                selection: Binding(
                                    get: { viewModel.selectedQuantizationProfileID },
                                    set: { viewModel.selectedQuantizationProfileID = $0 }
                                )
                            ) {
                                ForEach(viewModel.availableQuantizationProfileIDs, id: \.self) { profileID in
                                    Text(profileID).tag(profileID)
                                }
                            }
                            .pickerStyle(.menu)
                            .frame(maxWidth: 120)
                        }
                        HStack {
                            Button("Inspect") {
                                Task { await inspectPrimaryModel() }
                            }
                            Button("Refresh Tooling") {
                                Task { await refreshModelOpsProductState() }
                            }
                            Button("Doctor") {
                                Task { await runDoctor() }
                            }
                            Button("Bench") {
                                Task { await runBench() }
                            }
                            Button("Quantize") {
                                Task { await quantizePrimaryModel() }
                            }
                            Button("Train LoRA") {
                                Task { await trainPrimaryModel() }
                            }
                            Button("Activate Adapter") {
                                Task { await activateLatestAdapter() }
                            }
                            .disabled(viewModel.latestAdapterPackage == nil)
                            Button("Publish Adapter") {
                                Task { await publishLatestAdapter() }
                            }
                            .disabled(viewModel.latestAdapterPackage == nil)
                            Button("Download") {
                                Task { await downloadPrimaryModel() }
                            }
                            Button("Upload") {
                                Task { await uploadPrimaryModel() }
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            if let info = viewModel.selectedModelInfo {
                GroupBox("Model Info") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("\(info.modelID) • \(info.modelKind)")
                            .font(.headline)
                        Text("max context \(info.maxContext)")
                        Text("parsers: \(info.supportedParsers.joined(separator: ", "))")
                            .foregroundStyle(.secondary)
                        Text("modalities: \(info.supportedModalities.joined(separator: ", "))")
                            .foregroundStyle(.secondary)
                        if !info.ocrPromptProfileText.isEmpty {
                            Text("ocr prompt profile: \(info.ocrPromptProfileText)")
                                .foregroundStyle(.secondary)
                        }
                        if !info.ocrSamplingProfileText.isEmpty {
                            Text("ocr sampling profile: \(info.ocrSamplingProfileText)")
                                .foregroundStyle(.secondary)
                        }
                        if !info.ocrStopSequencesText.isEmpty {
                            Text("ocr stop sequences: \(info.ocrStopSequencesText)")
                                .foregroundStyle(.secondary)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            if let operation = viewModel.lastModelOperation {
                GroupBox("Last Operation") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("\(operation.operation) • \(operation.modelID)")
                            .font(.headline)
                        Text("job \(operation.jobID)")
                        Text("stage \(operation.stage) • \(String(format: "%.0f%%", operation.pct * 100))")
                        if !operation.quantProfileID.isEmpty {
                            Text("quant profile \(operation.quantProfileID)")
                                .foregroundStyle(.secondary)
                        }
                        if !operation.artifactKind.isEmpty {
                            Text("artifact \(operation.artifactKind) • \(operation.artifactBytes) bytes")
                                .foregroundStyle(.secondary)
                        }
                        if operation.calibrationSampleCount > 0 {
                            Text("calibration samples \(operation.calibrationSampleCount)")
                                .foregroundStyle(.secondary)
                        }
                        if !operation.manifestPath.isEmpty {
                            Text(operation.manifestPath)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if operation.smokeTestPassed {
                            Text("smoke validation passed")
                                .foregroundStyle(.secondary)
                        }
                        Text(operation.outputPath)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if !operation.manifestJson.isEmpty {
                            Text(operation.manifestJson)
                                .font(.caption.monospaced())
                                .textSelection(.enabled)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            GroupBox("Adapter Registry") {
                VStack(alignment: .leading, spacing: 8) {
                    if viewModel.adapterPackages.isEmpty {
                        Text("No adapter packages discovered yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(viewModel.adapterPackages) { adapter in
                            VStack(alignment: .leading, spacing: 4) {
                                Text("\(adapter.adapterName) • \(adapter.statusText)")
                                    .font(.headline)
                                Text("\(adapter.sourceModel) • \(adapter.datasetURI)")
                                    .foregroundStyle(.secondary)
                                if !adapter.publishedRepo.isEmpty {
                                    Text("published to \(adapter.publishedRepo)")
                                } else if !adapter.targetRepo.isEmpty {
                                    Text("target repo \(adapter.targetRepo)")
                                }
                                if !adapter.derivedModelID.isEmpty {
                                    Text("derived model \(adapter.derivedModelID)")
                                }
                                Text(adapter.outputPath)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                if !adapter.derivedModelPath.isEmpty {
                                    Text(adapter.derivedModelPath)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Text("activation \(adapter.activationStatusText) • export \(adapter.exportabilityText) • publish \(adapter.publishedStateText)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text("response-only \(adapter.responseOnlyEnabled ? "on" : "off") • grad ckpt \(adapter.gradientCheckpointingEnabled ? "on" : "off")")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text("train \(adapter.trainingDurationText) • activate \(adapter.activationDurationText) • publish \(adapter.publishDurationText)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Training History") {
                VStack(alignment: .leading, spacing: 8) {
                    if viewModel.trainingHistory.isEmpty {
                        Text("No training jobs recorded yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(viewModel.trainingHistory) { job in
                            VStack(alignment: .leading, spacing: 4) {
                                Text("\(job.adapterName) • \(job.statusText)")
                                    .font(.headline)
                                Text("\(job.modelID) • \(job.datasetURI)")
                                    .foregroundStyle(.secondary)
                                Text("job \(job.jobID) • \(job.stageText)")
                                if !job.targetRepo.isEmpty {
                                    Text("target repo \(job.targetRepo)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Text(job.outputPath)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            if let report = viewModel.lastDoctorReport {
                GroupBox("Doctor Report") {
                    ScrollView {
                        Text(report.markdown)
                            .font(.caption.monospaced())
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            if let report = viewModel.lastBenchReport {
                GroupBox("Bench Report") {
                    VStack(alignment: .leading, spacing: 6) {
                        if !report.reportPath.isEmpty {
                            Text(report.reportPath)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        ForEach(report.metrics) { metric in
                            HStack {
                                Text(metric.name)
                                Spacer()
                                Text(metric.value)
                                    .monospacedDigit()
                                    .foregroundStyle(.secondary)
                            }
                        }
                        if !report.markdown.isEmpty {
                            Text(report.markdown)
                                .font(.caption.monospaced())
                                .textSelection(.enabled)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            Spacer()
        }
        .padding(20)
    }

    func inspectPrimaryModel() async {
        await viewModel.inspectPrimaryModel()
    }

    func quantizePrimaryModel() async {
        await viewModel.quantizePrimaryModel()
    }

    func trainPrimaryModel() async {
        await viewModel.trainPrimaryModel()
    }

    func activateLatestAdapter() async {
        await viewModel.activateLatestAdapter()
    }

    func publishLatestAdapter() async {
        await viewModel.publishLatestAdapter()
    }

    func refreshModelOpsProductState() async {
        await viewModel.refreshModelOpsProductState()
    }

    func downloadPrimaryModel() async {
        await viewModel.downloadPrimaryModel()
    }

    func uploadPrimaryModel() async {
        await viewModel.uploadPrimaryModel()
    }

    func runDoctor() async {
        await viewModel.runDoctor()
    }

    func runBench() async {
        await viewModel.runBench()
    }
}

struct DesktopSettingsTabView: View {
    let foundation: DesktopFoundationState

    var body: some View {
        List(foundation.settings) { row in
            HStack {
                Text(row.key)
                    .fontWeight(.semibold)
                Spacer()
                Text(row.value)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

struct DesktopLogsTabView: View {
    let foundation: DesktopFoundationState

    var body: some View {
        List(foundation.logs) { entry in
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(entry.kind)
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.quaternary, in: Capsule())
                    Spacer()
                    Text(entry.level.uppercased())
                        .font(.caption2)
                        .foregroundStyle(entry.level == "error" ? .red : .secondary)
                }
                Text(entry.message)
                    .font(.body)
                Text(entry.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 4)
        }
    }
}

struct DesktopBenchTabView: View {
    let foundation: DesktopFoundationState

    var body: some View {
        List(foundation.benchMetrics) { row in
            HStack {
                Text(row.name)
                    .fontWeight(.medium)
                Spacer()
                Text(row.value)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }
        }
    }
}

struct DesktopAPIReferenceTabView: View {
    let foundation: DesktopFoundationState

    var body: some View {
        List(foundation.apiReference) { endpoint in
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Text(endpoint.method)
                        .font(.caption)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(.quaternary, in: Capsule())
                    Text(endpoint.path)
                        .font(.headline)
                    Spacer()
                    Text(endpoint.streaming ? "SSE" : "JSON")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Text(endpoint.summary)
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 4)
        }
    }
}
