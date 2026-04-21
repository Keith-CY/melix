import SwiftUI

@MainActor
public struct DesktopFoundationRootView: View {
    private let viewModel: RuntimeViewModel

    public init(viewModel: RuntimeViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        DesktopWorkspaceShellView(viewModel: viewModel)
            .frame(minWidth: 980, minHeight: 680)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    DesktopWorkspaceTitleBarTabsView(viewModel: viewModel)
                }

                ToolbarItem(placement: .primaryAction) {
                    DesktopWorkspaceTitleBarCommandCenterButton(
                        openCommandCenter: viewModel.openCommandCenter
                    )
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
                        .melixCard()
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

    private let memoryPolicyOptions = [
        ("Evictable", "evictable"),
        ("Pinned", "pinned"),
        ("TTL", "ttl"),
    ]

    private let diskStreamingModeOptions = [
        ("Disabled", "disabled"),
        ("Prefer Disk", "prefer_disk"),
        ("Require Disk", "require_disk"),
    ]

    private let cacheModeOptions = [
        ("Tiered", "tiered"),
        ("Rotating", "rotating"),
        ("Hybrid", "hybrid"),
    ]

    private let accelerationModeOptions = [
        ("Baseline", "baseline"),
        ("Speculative Decode", "speculative_decode"),
        ("Accelerated Prefill", "accelerated_prefill"),
        ("Active KV Quantized", "active_kv_quantized"),
        ("Sparse Prefill", "sparse_prefill"),
    ]

    private let adaptiveThinkingModeOptions = [
        ("Off", "off"),
        ("Adaptive", "adaptive"),
        ("Enabled", "enabled"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            List(foundation.models, id: \.modelID) { model in
                HStack {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            Text(model.modelID)
                                .font(.headline)
                            if !model.runtimeModeText.isEmpty {
                                // Capsule badge matching the pattern used in
                                // DesktopChatView and DesktopWorkspaceShellView
                                // for metadata tags. Adapter-backed and fused
                                // derived models get a visible runtime tag;
                                // base models render without a badge.
                                Text(model.runtimeModeText)
                                    .font(.caption2)
                                    .padding(.horizontal, 7)
                                    .padding(.vertical, 3)
                                    .background(.quaternary, in: Capsule())
                                    .accessibilityLabel(model.runtimeModeAccessibilityLabel)
                            }
                        }
                        Text(model.alias.isEmpty ? "\(model.kind) • \(model.stateText) • \(model.maxContext) ctx" : "\(model.alias) • \(model.stateText) • \(model.maxContext) ctx")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if !model.typeOverrideText.isEmpty {
                            Text("type override: \(model.typeOverrideText)")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                        }
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
                        if model.adaptiveThinkingText != "Off" || model.toolParserFallbackText != "Off" {
                            Text("adaptive thinking: \(model.adaptiveThinkingText) • parser fallback: \(model.toolParserFallbackText)")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                        if !model.cachePolicyText.isEmpty {
                            Text("cache policy: \(model.cachePolicyText)")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                        if !model.cacheSettingsText.isEmpty {
                            Text("cache settings: \(model.cacheSettingsText)")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                        }
                        Text("\(model.memoryPolicyText) • \(model.diskStreamingModeText) • \(model.accelerationModeText) • \(model.accelerationProfileID.isEmpty ? "no-profile" : model.accelerationProfileID)")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                    Spacer()
                    Button("Latency Profile", action: latencyProfileAction(for: model))
                    .buttonStyle(.bordered)
                    Button(model.actionTitle, action: toggleModelLoadAction(for: model))
                    .buttonStyle(.borderedProminent)
                }
                .padding(.vertical, 4)
            }
            .frame(minHeight: 260)

            DesktopRegistryRootsSectionView(viewModel: viewModel)

            GroupBox("Hugging Face Hub") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .center, spacing: 12) {
                        TextField(
                            "Repo ID or keywords",
                            text: Binding(
                                get: { viewModel.modelHubSearchQuery },
                                set: { viewModel.modelHubSearchQuery = $0 }
                            )
                        )
                        TextField(
                            "Revision",
                            text: Binding(
                                get: { viewModel.modelHubSelectedRevision },
                                set: { viewModel.modelHubSelectedRevision = $0 }
                            )
                        )
                        .frame(maxWidth: 180)
                        Toggle(
                            "MLX Only",
                            isOn: Binding(
                                get: { viewModel.modelHubSearchMLXOnly },
                                set: { viewModel.modelHubSearchMLXOnly = $0 }
                            )
                        )
                        .toggleStyle(.checkbox)
                        Button("Search", action: searchHubModelsAction())
                            .buttonStyle(.borderedProminent)
                    }

                    if viewModel.modelHubSearchResults.isEmpty {
                        Text("Search Hugging Face repos and download directly into the managed model root.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(viewModel.modelHubSearchResults) { result in
                                HStack(alignment: .top, spacing: 12) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(result.repoID)
                                            .font(.headline)
                                        Text("\(result.author) • \(result.pipelineTag) • \(result.compatibilityText)")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        Text("\(result.downloadsText) • \(result.likesText)")
                                            .font(.caption2)
                                            .foregroundStyle(.tertiary)
                                    }
                                    Spacer()
                                    Button("Details", action: inspectHubModelAction(repoID: result.repoID))
                                        .buttonStyle(.bordered)
                                    Button("Download", action: downloadHubModelAction(repoID: result.repoID))
                                        .buttonStyle(.borderedProminent)
                                }
                            }
                        }
                    }

                    if let card = viewModel.selectedHubModelCard {
                        Divider()
                        VStack(alignment: .leading, spacing: 6) {
                            Text(card.repoID)
                                .font(.headline)
                            Text("\(card.author) • \(card.pipelineTag) • \(card.compatibilityText)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            if !card.summary.isEmpty {
                                Text(card.summary)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            if !card.tags.isEmpty {
                                Text("Tags: \(card.tags.joined(separator: ", "))")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                            }
                            if !card.baseModels.isEmpty {
                                Text("Base Models: \(card.baseModels.joined(separator: ", "))")
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            if let primaryModel = viewModel.primaryModel {
                GroupBox("Model Settings") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(primaryModel.modelID)
                            .font(.headline)
                        HStack(spacing: 12) {
                            TextField(
                                "Alias",
                                text: Binding(
                                    get: { viewModel.modelSettingsAliasDraft },
                                    set: { viewModel.modelSettingsAliasDraft = $0 }
                                )
                            )
                            TextField(
                                "Type Override",
                                text: Binding(
                                    get: { viewModel.modelSettingsTypeOverrideDraft },
                                    set: { viewModel.modelSettingsTypeOverrideDraft = $0 }
                                )
                            )
                        }
                        HStack(spacing: 12) {
                            TextField(
                                "TTL Seconds",
                                text: Binding(
                                    get: { viewModel.modelSettingsTTLDraft },
                                    set: { viewModel.modelSettingsTTLDraft = $0 }
                                )
                            )
                            Toggle(
                                "Pin On Load",
                                isOn: Binding(
                                    get: { viewModel.modelSettingsPinOnLoadDraft },
                                    set: { viewModel.modelSettingsPinOnLoadDraft = $0 }
                                )
                            )
                            .toggleStyle(.checkbox)
                        }
                        HStack(spacing: 12) {
                            Picker(
                                "Memory Policy",
                                selection: Binding(
                                    get: { viewModel.modelSettingsMemoryPolicyDraft },
                                    set: { viewModel.modelSettingsMemoryPolicyDraft = $0 }
                                )
                            ) {
                                ForEach(memoryPolicyOptions, id: \.1) { option in
                                    Text(option.0).tag(option.1)
                                }
                            }
                            TextField(
                                "Memory Budget Bytes",
                                text: Binding(
                                    get: { viewModel.modelSettingsMemoryBudgetDraft },
                                    set: { viewModel.modelSettingsMemoryBudgetDraft = $0 }
                                )
                            )
                            Picker(
                                "Acceleration",
                                selection: Binding(
                                    get: { viewModel.modelSettingsAccelerationModeDraft },
                                    set: { viewModel.modelSettingsAccelerationModeDraft = $0 }
                                )
                            ) {
                                ForEach(accelerationModeOptions, id: \.1) { option in
                                    Text(option.0).tag(option.1)
                                }
                            }
                            Picker(
                                "Disk Streaming",
                                selection: Binding(
                                    get: { viewModel.modelSettingsDiskStreamingModeDraft },
                                    set: { viewModel.modelSettingsDiskStreamingModeDraft = $0 }
                                )
                            ) {
                                ForEach(diskStreamingModeOptions, id: \.1) { option in
                                    Text(option.0).tag(option.1)
                                }
                            }
                        }
                        HStack(spacing: 12) {
                            Picker(
                                "Cache Mode",
                                selection: Binding(
                                    get: { viewModel.modelSettingsCacheModeDraft },
                                    set: { viewModel.modelSettingsCacheModeDraft = $0 }
                                )
                            ) {
                                ForEach(cacheModeOptions, id: \.1) { option in
                                    Text(option.0).tag(option.1)
                                }
                            }
                            TextField(
                                "Cache Budget Bytes",
                                text: Binding(
                                    get: { viewModel.modelSettingsCacheMemoryBudgetDraft },
                                    set: { viewModel.modelSettingsCacheMemoryBudgetDraft = $0 }
                                )
                            )
                            TextField(
                                "Cache Budget %",
                                text: Binding(
                                    get: { viewModel.modelSettingsCacheMemoryBudgetPctDraft },
                                    set: { viewModel.modelSettingsCacheMemoryBudgetPctDraft = $0 }
                                )
                            )
                        }
                        HStack(spacing: 12) {
                            TextField(
                                "Cache Block Tokens",
                                text: Binding(
                                    get: { viewModel.modelSettingsCacheBlockSizeTokensDraft },
                                    set: { viewModel.modelSettingsCacheBlockSizeTokensDraft = $0 }
                                )
                            )
                            TextField(
                                "Cache Directory",
                                text: Binding(
                                    get: { viewModel.modelSettingsCacheDirectoryDraft },
                                    set: { viewModel.modelSettingsCacheDirectoryDraft = $0 }
                                )
                            )
                            TextField(
                                "Multimodal Cache Budget",
                                text: Binding(
                                    get: { viewModel.modelSettingsMultimodalCacheBudgetDraft },
                                    set: { viewModel.modelSettingsMultimodalCacheBudgetDraft = $0 }
                                )
                            )
                        }
                        HStack(spacing: 12) {
                            TextField(
                                "Acceleration Profile",
                                text: Binding(
                                    get: { viewModel.modelSettingsAccelerationProfileIDDraft },
                                    set: { viewModel.modelSettingsAccelerationProfileIDDraft = $0 }
                                )
                            )
                            Picker(
                                "Adaptive Thinking",
                                selection: Binding(
                                    get: { viewModel.modelSettingsAdaptiveThinkingModeDraft },
                                    set: { viewModel.modelSettingsAdaptiveThinkingModeDraft = $0 }
                                )
                            ) {
                                ForEach(adaptiveThinkingModeOptions, id: \.1) { option in
                                    Text(option.0).tag(option.1)
                                }
                            }
                        }
                        HStack(spacing: 12) {
                            TextField(
                                "Adaptive Budget",
                                text: Binding(
                                    get: { viewModel.modelSettingsAdaptiveThinkingBudgetDraft },
                                    set: { viewModel.modelSettingsAdaptiveThinkingBudgetDraft = $0 }
                                )
                            )
                            Toggle(
                                "Parser XML Fallback",
                                isOn: Binding(
                                    get: { viewModel.modelSettingsToolParserXMLFallbackDraft },
                                    set: { viewModel.modelSettingsToolParserXMLFallbackDraft = $0 }
                                )
                            )
                            .toggleStyle(.checkbox)
                        }
                        if primaryModel.kind == "ocr" {
                            HStack(spacing: 12) {
                                TextField(
                                    "OCR Sampling Profile",
                                    text: Binding(
                                        get: { viewModel.modelSettingsOCRSamplingProfileDraft },
                                        set: { viewModel.modelSettingsOCRSamplingProfileDraft = $0 }
                                    )
                                )
                                TextField(
                                    "OCR Temperature",
                                    text: Binding(
                                        get: { viewModel.modelSettingsOCRTemperatureDraft },
                                        set: { viewModel.modelSettingsOCRTemperatureDraft = $0 }
                                    )
                                )
                            }
                            HStack(spacing: 12) {
                                TextField(
                                    "OCR Top P",
                                    text: Binding(
                                        get: { viewModel.modelSettingsOCRTopPDraft },
                                        set: { viewModel.modelSettingsOCRTopPDraft = $0 }
                                    )
                                )
                                TextField(
                                    "OCR Max Tokens",
                                    text: Binding(
                                        get: { viewModel.modelSettingsOCRMaxTokensDraft },
                                        set: { viewModel.modelSettingsOCRMaxTokensDraft = $0 }
                                    )
                                )
                            }
                        }
                        HStack {
                            Button("Apply Settings", action: applyPrimaryModelSettingsAction())
                            .buttonStyle(.borderedProminent)
                            Button("Reset Draft", action: resetPrimaryModelSettingsAction())
                            .buttonStyle(.bordered)
                            Spacer()
                            Button("Inspect", action: inspectPrimaryModelAction())
                            .buttonStyle(.bordered)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
    }

    func applyLatencyProfile(to model: RuntimeModelRow) async {
        await viewModel.updateModelSettings(
            modelID: model.modelID,
            alias: model.alias.isEmpty ? "Melix Text Turbo" : model.alias,
            pinOnLoad: true,
            memoryPolicy: "pinned",
            diskStreamingMode: "disabled",
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

    func latencyProfileAction(for model: RuntimeModelRow) -> () -> Void {
        { Task { await applyLatencyProfile(to: model) } }
    }

    func toggleModelLoadAction(for model: RuntimeModelRow) -> () -> Void {
        { Task { await toggleModelLoad(for: model) } }
    }

    func applyPrimaryModelSettingsAction() -> () -> Void {
        { Task { await viewModel.applyPrimaryModelSettings() } }
    }

    func resetPrimaryModelSettingsAction() -> () -> Void {
        { viewModel.resetPrimaryModelSettingsDrafts() }
    }

    func inspectPrimaryModelAction() -> () -> Void {
        { Task { await viewModel.inspectPrimaryModel() } }
    }

    func searchHubModelsAction() -> () -> Void {
        { Task { await viewModel.searchModelHub() } }
    }

    func inspectHubModelAction(repoID: String) -> () -> Void {
        { Task { await viewModel.inspectHubModel(repoID: repoID) } }
    }

    func downloadHubModelAction(repoID: String) -> () -> Void {
        { Task { await viewModel.downloadHubModel(repoID: repoID) } }
    }

    func addRegistryRoot() async {
        await viewModel.addRegistryRoot()
    }

    func removeRegistryRoot(_ root: RuntimeRegistryRootState) async {
        await viewModel.removeRegistryRoot(rootID: root.id)
    }

    func moveRegistryRootUp(_ root: RuntimeRegistryRootState) async {
        await viewModel.moveRegistryRootUp(rootID: root.id)
    }

    func moveRegistryRootDown(_ root: RuntimeRegistryRootState) async {
        await viewModel.moveRegistryRootDown(rootID: root.id)
    }

    func rescanRegistryRoots() async {
        await viewModel.rescanRegistryRoots()
    }
}

private struct DesktopRegistryRootsSectionView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        GroupBox("Registry Roots") {
            VStack(alignment: .leading, spacing: 12) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(viewModel.registryRootSummaryText)
                            .font(.headline)
                        Text("Last scanned: \(viewModel.registryScannedAtText)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    Spacer()
                    Button("Rescan") {
                        Task { await viewModel.rescanRegistryRoots() }
                    }
                    .buttonStyle(.bordered)
                }

                HStack(spacing: 12) {
                    TextField(
                        "Add Registry Root",
                        text: Binding(
                            get: { viewModel.registryRootPathDraft },
                            set: { viewModel.registryRootPathDraft = $0 }
                        )
                    )
                    Button("Add Root") {
                        Task { await viewModel.addRegistryRoot() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.canAddRegistryRoot == false)
                }

                DesktopRegistryRootsListView(viewModel: viewModel)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct DesktopRegistryRootsListView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        let registryRoots: [RuntimeRegistryRootState] = viewModel.registryRoots

        if registryRoots.isEmpty {
            Text(
                viewModel.registryHasConfiguredRootOverride
                ? "No registry roots are configured yet."
                : "No registry snapshot has been loaded yet."
            )
            .foregroundStyle(.secondary)
        } else {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(registryRoots.enumerated()), id: \.element.id) { index, root in
                    DesktopRegistryRootRowView(
                        root: root,
                        isFirst: index == 0,
                        isLast: index == registryRoots.count - 1,
                        moveUp: { Task { await viewModel.moveRegistryRootUp(rootID: root.id) } },
                        moveDown: { Task { await viewModel.moveRegistryRootDown(rootID: root.id) } },
                        remove: { Task { await viewModel.removeRegistryRoot(rootID: root.id) } }
                    )
                }
            }
        }
    }
}

private struct DesktopRegistryRootRowView: View {
    let root: RuntimeRegistryRootState
    let isFirst: Bool
    let isLast: Bool
    let moveUp: () -> Void
    let moveDown: () -> Void
    let remove: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(root.rootPath)
                    .font(.headline)
                Text("#\(root.rootOrder) • \(root.statusText)")
                    .font(.caption)
                    .foregroundStyle(root.accessible ? Color.secondary : Color.orange)
                Text(root.detailText)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            Spacer()
            Button("Up", action: moveUp)
                .buttonStyle(.bordered)
                .disabled(isFirst)
            Button("Down", action: moveDown)
                .buttonStyle(.bordered)
                .disabled(isLast)
            Button("Remove", action: remove)
                .buttonStyle(.bordered)
        }
        .padding(.vertical, 2)
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
                            Button("Convert") {
                                Task { await convertPrimaryModel() }
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
                    DesktopModelInfoSummaryView(info: info)
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
                        if !operation.targetRepo.isEmpty {
                            Text("target repo \(operation.targetRepo)")
                                .foregroundStyle(.secondary)
                        }
                        if !operation.sourceArtifactKind.isEmpty {
                            Text("source artifact \(operation.sourceArtifactKind)")
                                .foregroundStyle(.secondary)
                        }
                        if !operation.conversionTargetFormat.isEmpty {
                            Text("target format \(operation.conversionTargetFormat)")
                                .foregroundStyle(.secondary)
                        }
                        if !operation.artifactRuntime.isEmpty {
                            Text(
                                "runtime \(operation.artifactRuntime) • serving \(operation.servingCompatible ? "compatible" : "not verified")"
                            )
                            .foregroundStyle(.secondary)
                        }
                        if !operation.linkedQuantizationProfileID.isEmpty {
                            Text("linked quant \(operation.linkedQuantizationProfileID)")
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
                    DesktopDoctorReportSummaryView(report: report)
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

    func convertPrimaryModel() async {
        await viewModel.convertPrimaryModel()
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

struct DesktopModelInfoSummaryView: View {
    let info: RuntimeModelInfoState

    var body: some View {
        let content = desktopModelInfoSummaryContent(info)
        VStack(alignment: .leading, spacing: 6) {
            Text(content.headline)
                .font(.headline)
            Text(content.maxContext)
            ForEach(Array(content.detailLines.enumerated()), id: \.offset) { _, line in
                Text(line)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct DesktopDoctorReportSummaryView: View {
    let report: RuntimeDoctorReportState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !report.healthStatusText.isEmpty {
                Text("Status: \(report.healthStatusText)")
                    .font(.headline)
            }
            if report.findings.isEmpty == false {
                ForEach(report.findings) { finding in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(finding.severityText) • \(finding.code)")
                            .font(.caption.weight(.semibold))
                        Text(finding.summary)
                            .font(.caption)
                        if !finding.detail.isEmpty {
                            Text(finding.detail)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            ScrollView {
                Text(report.markdown)
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct DesktopModelInfoSummaryContent: Equatable {
    let headline: String
    let maxContext: String
    let detailLines: [String]
}

func desktopModelInfoSummaryContent(
    _ info: RuntimeModelInfoState
) -> DesktopModelInfoSummaryContent {
    var detailLines: [String] = []
    if !info.aliasText.isEmpty {
        detailLines.append("alias: \(info.aliasText)")
    }
    if !info.typeOverrideText.isEmpty {
        detailLines.append("type override: \(info.typeOverrideText)")
    }
    if !info.backendID.isEmpty {
        detailLines.append("backend: \(info.backendID)")
    }
    if !info.familyID.isEmpty {
        detailLines.append("family: \(info.familyID)")
    }
    if !info.audioInstallProfileText.isEmpty {
        detailLines.append("audio install profile: \(info.audioInstallProfileText)")
    }
    if !info.audioLanguagesText.isEmpty {
        detailLines.append("audio languages: \(info.audioLanguagesText)")
    }
    if !info.audioVoiceModeText.isEmpty {
        detailLines.append("voice mode: \(info.audioVoiceModeText)")
    }
    if !info.audioOutputFormatsText.isEmpty {
        detailLines.append("audio formats: \(info.audioOutputFormatsText)")
    }
    if !info.audioSupportsInstructionsText.isEmpty {
        detailLines.append("instruction support: \(info.audioSupportsInstructionsText)")
    }
    if !info.audioVoiceLocalesText.isEmpty {
        detailLines.append("voice locales: \(info.audioVoiceLocalesText)")
    }
    if !info.audioDefaultLocaleText.isEmpty {
        detailLines.append("default locale: \(info.audioDefaultLocaleText)")
    }
    if !info.audioPackagedDefaultLocaleText.isEmpty {
        detailLines.append("packaged default locale: \(info.audioPackagedDefaultLocaleText)")
    }
    if !info.audioLocalePolicyText.isEmpty {
        detailLines.append("locale policy: \(info.audioLocalePolicyText)")
    }
    if !info.audioVoiceCatalogSummaryText.isEmpty {
        detailLines.append("voice catalog: \(info.audioVoiceCatalogSummaryText)")
    }
    if !info.audioRuntimePackStateText.isEmpty {
        detailLines.append("runtime pack state: \(info.audioRuntimePackStateText)")
    }
    if !info.audioRuntimePackIDText.isEmpty {
        detailLines.append("runtime pack id: \(info.audioRuntimePackIDText)")
    }
    if !info.audioModelStateText.isEmpty {
        detailLines.append("audio model state: \(info.audioModelStateText)")
    }
    if !info.defaultWorkflowRole.isEmpty {
        detailLines.append("default workflow: \(info.defaultWorkflowRole)")
    }
    if !info.detectedIdentitySource.isEmpty {
        detailLines.append("identity source: \(info.detectedIdentitySource)")
    }
    detailLines.append("memory policy: \(info.memoryPolicyText)")
    if !info.memoryBudgetText.isEmpty {
        detailLines.append("memory budget: \(info.memoryBudgetText)")
    }
    detailLines.append("disk streaming: \(info.diskStreamingModeText)")
    if !info.cacheModeText.isEmpty {
        detailLines.append("cache mode: \(info.cacheModeText)")
    }
    if !info.cacheCompatibilityText.isEmpty {
        detailLines.append("cache compatibility: \(info.cacheCompatibilityText)")
    }
    if !info.cacheCompatibilityReasonText.isEmpty {
        detailLines.append("cache detail: \(info.cacheCompatibilityReasonText)")
    }
    if !info.cacheDirectoryText.isEmpty {
        detailLines.append("cache directory: \(info.cacheDirectoryText)")
    }
    if !info.cacheRootText.isEmpty {
        detailLines.append("cache root: \(info.cacheRootText)")
    }
    if !info.cacheBlockSizeText.isEmpty {
        detailLines.append("cache block size: \(info.cacheBlockSizeText)")
    }
    if !info.cacheBudgetText.isEmpty {
        detailLines.append("cache budget: \(info.cacheBudgetText)")
    }
    if !info.multimodalCacheBudgetText.isEmpty {
        detailLines.append("multimodal cache budget: \(info.multimodalCacheBudgetText)")
    }
    if !info.initialCacheBlocksText.isEmpty {
        detailLines.append("initial cache blocks: \(info.initialCacheBlocksText)")
    }
    detailLines.append("adaptive thinking: \(info.adaptiveThinkingText)")
    detailLines.append("acceleration: \(info.accelerationModeText) • \(info.accelerationProfileID.isEmpty ? "no-profile" : info.accelerationProfileID)")
    detailLines.append("parser fallback: \(info.toolParserFallbackText)")
    detailLines.append("pin on load: \(info.pinOnLoad ? "yes" : "no")")
    if info.ttlSeconds > 0 {
        detailLines.append("ttl seconds: \(info.ttlSeconds)")
    }
    detailLines.append("parsers: \(info.supportedParsers.joined(separator: ", "))")
    detailLines.append("modalities: \(info.supportedModalities.joined(separator: ", "))")
    if !info.supportedTasks.isEmpty {
        detailLines.append("tasks: \(info.supportedTasks.joined(separator: ", "))")
    }
    if !info.modelRevision.isEmpty {
        detailLines.append("revision: \(info.modelRevision)")
    }
    if !info.modelPath.isEmpty {
        detailLines.append("source path: \(info.modelPath)")
    }
    if !info.ocrPromptProfileText.isEmpty {
        detailLines.append("ocr prompt profile: \(info.ocrPromptProfileText)")
    }
    if !info.generationConfigSourceText.isEmpty {
        detailLines.append("generation config: \(info.generationConfigSourceText)")
    }
    let generationDefaultParts = [
        info.generationConfigTemperatureText.isEmpty ? nil : "temp \(info.generationConfigTemperatureText)",
        info.generationConfigTopPText.isEmpty ? nil : "top-p \(info.generationConfigTopPText)",
        info.generationConfigMaxTokensText.isEmpty ? nil : "max \(info.generationConfigMaxTokensText)",
    ].compactMap { $0 }
    if !generationDefaultParts.isEmpty {
        detailLines.append("generation defaults: \(generationDefaultParts.joined(separator: " • "))")
    }
    if !info.ocrSamplingProfileText.isEmpty {
        detailLines.append("ocr sampling profile: \(info.ocrSamplingProfileText)")
    }
    let ocrSamplingParts = [
        info.ocrSamplingProfileText.isEmpty ? nil : info.ocrSamplingProfileText,
        info.ocrTemperatureText.isEmpty ? nil : "temp \(info.ocrTemperatureText)",
        info.ocrTopPText.isEmpty ? nil : "top-p \(info.ocrTopPText)",
        info.ocrMaxTokensText.isEmpty ? nil : "max \(info.ocrMaxTokensText)",
    ].compactMap { $0 }
    if !ocrSamplingParts.isEmpty {
        detailLines.append("ocr sampling defaults: \(ocrSamplingParts.joined(separator: " • "))")
    }
    if !info.ocrStopSequencesText.isEmpty {
        detailLines.append("ocr stop sequences: \(info.ocrStopSequencesText)")
    }
    return DesktopModelInfoSummaryContent(
        headline: "\(info.modelID) • \(info.modelKind)",
        maxContext: "max context \(info.maxContext)",
        detailLines: detailLines
    )
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
        List {
            if foundation.apiSurfaces.isEmpty {
                Text("No API reference has been published by the control plane yet.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(foundation.apiSurfaces) { surface in
                    Section {
                        let surfaceEndpoints = foundation.apiReference.filter { $0.surfaceID == surface.id }
                        if surfaceEndpoints.isEmpty {
                            Text(surface.compatibilityNote.isEmpty ? "No routes are currently published for this surface." : surface.compatibilityNote)
                                .foregroundStyle(.secondary)
                        } else {
                            ForEach(surfaceEndpoints) { endpoint in
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
                    } header: {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(surface.title)
                                Spacer()
                                Text(surface.statusText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Text(surface.summary)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .textCase(nil)
                    }
                }
            }
        }
    }
}
