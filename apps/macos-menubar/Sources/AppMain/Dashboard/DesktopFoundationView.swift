import AppKit
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
            .tint(MelixDesignTokens.accent)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    DesktopWorkspaceTitleBarTabsView(viewModel: viewModel)
                }

                ToolbarItem(placement: .primaryAction) {
                    DesktopWorkspaceTitleBarActionsView(viewModel: viewModel)
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
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.lg) {
            DesktopRegistryBroadsheetSection("Model Registry") {
                VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.md) {
                    HStack(alignment: .center, spacing: MelixDesignTokens.Spacing.md) {
                        DesktopRegistryTextField(
                            title: "Repo ID or keywords",
                            text: Binding(
                                get: { viewModel.modelHubSearchQuery },
                                set: { viewModel.modelHubSearchQuery = $0 }
                            )
                        )
                        DesktopRegistryTextField(
                            title: "Revision",
                            text: Binding(
                                get: { viewModel.modelHubSelectedRevision },
                                set: { viewModel.modelHubSelectedRevision = $0 }
                            )
                        )
                        .frame(maxWidth: 160)
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
                            .controlSize(.small)
                            .fixedSize(horizontal: true, vertical: false)
                    }

                    HStack(alignment: .center, spacing: MelixDesignTokens.Spacing.md) {
                        DesktopRegistrySecureField(
                            title: "Hugging Face Token",
                            text: Binding(
                                get: { viewModel.modelHubTokenDraft },
                                set: { viewModel.modelHubTokenDraft = $0 }
                            )
                        )
                        if !viewModel.modelHubTokenHint.isEmpty {
                            Text("Token saved: \(viewModel.modelHubTokenHint)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: true, vertical: false)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            DesktopModelRegistryEntriesView(viewModel: viewModel)

            DesktopRegistryRootsSectionView(viewModel: viewModel)

            if let primaryModel = viewModel.primaryModel {
                DesktopRegistryBroadsheetSection("Model Settings") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(primaryModel.displayName)
                            .font(.headline)
                        Text(primaryModel.modelID)
                            .font(.caption)
                            .foregroundStyle(.secondary)
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
                        if let disabledReason = viewModel.modelSettingsAccelerationModeDisabledReason {
                            Text(disabledReason)
                                .font(.caption)
                                .foregroundStyle(.secondary)
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
                        if let disabledReason = viewModel.modelSettingsToolParserXMLFallbackDisabledReason {
                            Text(disabledReason)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        HStack(spacing: 12) {
                            Text("Load Trust")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(viewModel.modelSettingsLoadTrustModeText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Button("Trust Remote Code", action: trustRemoteCodeForPrimaryModelAction())
                                .buttonStyle(.bordered)
                                .accessibilityLabel("Trust Remote Code")
                            Button("Clear Trust Override", action: clearPrimaryModelLoadTrustOverrideAction())
                                .buttonStyle(.bordered)
                                .accessibilityLabel("Clear Trust Override")
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
                            .disabled(
                                viewModel.modelSettingsAccelerationModeDisabledReason != nil
                                    || (viewModel.modelSettingsToolParserXMLFallbackDraft
                                        && viewModel.modelSettingsToolParserXMLFallbackDisabledReason != nil)
                            )
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
            alias: model.alias.isEmpty ? DesktopModelRegistryDefaults.latencyProfileAlias : model.alias,
            pinOnLoad: true,
            memoryPolicy: "pinned",
            diskStreamingMode: "disabled",
            accelerationMode: "speculative_decode",
            accelerationProfileID: "draft-q4"
        )
    }

    func toggleModelLoad(for model: RuntimeModelRow) async {
        if model.runtimeCacheMissing {
            await viewModel.restoreMissingRuntimeCache(modelID: model.modelID)
        } else if model.isLoaded {
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

    func trustRemoteCodeForPrimaryModelAction() -> () -> Void {
        { Task { await viewModel.trustRemoteCodeForPrimaryModel() } }
    }

    func clearPrimaryModelLoadTrustOverrideAction() -> () -> Void {
        { Task { await viewModel.clearPrimaryModelLoadTrustOverride() } }
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

private struct DesktopRegistryTextField: View {
    let title: String
    @Binding var text: String

    var body: some View {
        TextField(title, text: $text)
            .textFieldStyle(.plain)
            .font(.body)
            .padding(.vertical, MelixDesignTokens.Spacing.sm)
            .overlay(alignment: .bottom) {
                Rectangle()
                    .fill(Color.secondary.opacity(MelixDesignTokens.StrokeOpacity.interactive))
                    .frame(height: 1)
            }
    }
}

private struct DesktopRegistrySecureField: View {
    let title: String
    @Binding var text: String

    var body: some View {
        SecureField(title, text: $text)
            .textFieldStyle(.plain)
            .font(.body)
            .padding(.vertical, MelixDesignTokens.Spacing.sm)
            .overlay(alignment: .bottom) {
                Rectangle()
                    .fill(Color.secondary.opacity(MelixDesignTokens.StrokeOpacity.interactive))
                    .frame(height: 1)
            }
    }
}

private struct DesktopRegistryBroadsheetSection<Content: View>: View {
    let title: String
    @ViewBuilder let content: () -> Content

    init(_ title: String, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.sm) {
            Text(title).melixSectionLabel()
            content()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.vertical, MelixDesignTokens.Spacing.xs)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct DesktopModelRegistryEntriesView: View {
    let viewModel: RuntimeViewModel

    var entries: [RuntimeRegistryEntryState] {
        viewModel.modelRegistryEntries
    }

    var selectedCard: RuntimeHubModelCardState? {
        viewModel.selectedHubModelCard
    }

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .top, spacing: MelixDesignTokens.Spacing.lg) {
                registryList
                    .frame(minWidth: 440)
                modelCard
                    .frame(minWidth: 320, maxWidth: 380)
            }

            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.lg) {
                registryList
                modelCard
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var registryList: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.md) {
            registryGroup(.readyToRun, title: "Ready to Run")
            registryGroup(.discoverAndDownload, title: "Discover & Download")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func registryGroup(_ group: RuntimeRegistryAvailabilityGroup, title: String) -> some View {
        let groupEntries = entries.filter { $0.availabilityGroup == group }
        return DesktopRegistryBroadsheetSection(title) {
            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.sm) {
                if groupEntries.isEmpty {
                    Text(group == .readyToRun ? "No ready models found." : "No discoveries yet.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(groupEntries) { entry in
                        DesktopRegistryEntryRowView(
                            entry: entry,
                            localModel: localModel(for: entry),
                            isSelected: selectedCard?.repoID == entry.repoID,
                            inspect: entry.canInspect ? inspectHubModelAction(repoID: entry.repoID) : nil,
                            download: entry.repoID.isEmpty ? nil : downloadHubModelAction(repoID: entry.repoID),
                            latencyProfile: latencyProfileAction(for: localModel(for: entry)),
                            toggleLoad: toggleModelLoadAction(for: localModel(for: entry))
                        )
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var modelCard: some View {
        DesktopRegistryInspectorPane("Model Card") {
            if let card = selectedCard {
                DesktopHubModelCardContent(card: card)
            } else if let entry = entries.first {
                DesktopRegistryEntryCardContent(entry: entry, localModel: localModel(for: entry))
            } else {
                VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.sm) {
                    Text("No Model Selected")
                        .font(.headline)
                    Text("Registry metadata unavailable.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func localModel(for entry: RuntimeRegistryEntryState) -> RuntimeModelRow? {
        guard entry.id.hasPrefix("local:") else {
            return nil
        }
        return viewModel.desktopFoundationState.models.first { "local:\($0.modelID)" == entry.id }
    }

    private func inspectHubModelAction(repoID: String) -> () -> Void {
        { Task { await viewModel.inspectHubModel(repoID: repoID) } }
    }

    private func downloadHubModelAction(repoID: String) -> () -> Void {
        { Task { await viewModel.downloadHubModel(repoID: repoID) } }
    }

    func applyLatencyProfile(to model: RuntimeModelRow?) async {
        guard let model else {
            return
        }
        await viewModel.updateModelSettings(
            modelID: model.modelID,
            alias: model.alias.isEmpty ? DesktopModelRegistryDefaults.latencyProfileAlias : model.alias,
            pinOnLoad: true,
            memoryPolicy: "pinned",
            diskStreamingMode: "disabled",
            accelerationMode: "speculative_decode",
            accelerationProfileID: "draft-q4"
        )
    }

    func toggleModelLoad(for model: RuntimeModelRow?) async {
        guard let model else {
            return
        }
        if model.runtimeCacheMissing {
            await viewModel.restoreMissingRuntimeCache(modelID: model.modelID)
        } else if model.isLoaded {
            await viewModel.unloadModel(modelID: model.modelID)
        } else {
            await viewModel.loadModel(modelID: model.modelID)
        }
    }

    private func latencyProfileAction(for model: RuntimeModelRow?) -> (() -> Void)? {
        guard let model else {
            return nil
        }
        return {
            Task { await applyLatencyProfile(to: model) }
        }
    }

    private func toggleModelLoadAction(for model: RuntimeModelRow?) -> (() -> Void)? {
        guard let model else {
            return nil
        }
        return {
            Task { await toggleModelLoad(for: model) }
        }
    }
}

private struct DesktopRegistryInspectorPane<Content: View>: View {
    let title: String
    @ViewBuilder let content: () -> Content

    init(_ title: String, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.md) {
            Text(title).melixSectionLabel()
            content()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.leading, MelixDesignTokens.Spacing.md)
        .padding(.vertical, MelixDesignTokens.Spacing.xs)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(alignment: .leading) {
            Rectangle()
                .fill(Color.secondary.opacity(MelixDesignTokens.StrokeOpacity.interactive))
                .frame(width: 1)
        }
    }
}

private struct DesktopRegistryEntryRowView: View {
    let entry: RuntimeRegistryEntryState
    let localModel: RuntimeModelRow?
    let isSelected: Bool
    let inspect: (() -> Void)?
    let download: (() -> Void)?
    let latencyProfile: (() -> Void)?
    let toggleLoad: (() -> Void)?

    var body: some View {
        HStack(alignment: .top, spacing: MelixDesignTokens.Spacing.lg) {
            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
                HStack(alignment: .firstTextBaseline, spacing: MelixDesignTokens.Spacing.sm) {
                    Text(entry.title)
                        .font(.callout.weight(.semibold))
                        .lineLimit(1)
                        .truncationMode(.middle)
                    DesktopRegistryBadgeView(
                        title: entry.sourceText,
                        tint: DesktopRegistryVisuals.sourceColor(entry.sourceText)
                    )
                    if localModel?.runtimeCacheMissing == true {
                        DesktopRegistryBadgeView(
                            title: localModel?.runtimeCacheStatusText ?? "Cache Missing",
                            tint: MelixDesignTokens.StatusColor.warning
                        )
                    }
                }

                if !entry.subtitleText.isEmpty {
                    Text(entry.subtitleText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }

                HStack(alignment: .center, spacing: MelixDesignTokens.Spacing.xs) {
                    DesktopRegistryMetadataChipView(title: entry.taskText)
                    DesktopRegistryMetadataChipView(title: entry.statusText)
                    if !entry.sizeText.isEmpty {
                        DesktopRegistryMetadataChipView(title: entry.sizeText, monospaced: true)
                    }
                }

                HStack(alignment: .firstTextBaseline, spacing: MelixDesignTokens.Spacing.xs) {
                    Text("Run Suitability")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    DesktopRegistryBadgeView(
                        title: entry.runSuitabilityText,
                        tint: DesktopRegistryVisuals.fitColor(entry.runSuitabilityText)
                    )
                }

                if let localModel, localModel.runtimeCacheMissing {
                    Text(localModel.runtimeCacheDetailText)
                        .font(.caption2)
                        .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                        .lineLimit(2)
                }
            }

            Spacer(minLength: MelixDesignTokens.Spacing.md)

            VStack(alignment: .trailing, spacing: MelixDesignTokens.Spacing.xs) {
                if let latencyProfile {
                    Button("Latency Profile", action: latencyProfile)
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .fixedSize(horizontal: true, vertical: false)
                }
                if let localModel, let toggleLoad {
                    Button(localModel.actionTitle, action: toggleLoad)
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .fixedSize(horizontal: true, vertical: false)
                }
                if let inspect {
                    Button("Details", action: inspect)
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .fixedSize(horizontal: true, vertical: false)
                }
                if let download {
                    Button("Download", action: download)
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(!entry.canDownload)
                        .fixedSize(horizontal: true, vertical: false)
                }
            }
        }
        .padding(.horizontal, MelixDesignTokens.Spacing.md)
        .padding(.vertical, MelixDesignTokens.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .desktopRegistryRowBackground(isSelected)
    }
}

private struct DesktopRegistryRowBackground: ViewModifier {
    let isSelected: Bool

    func body(content: Content) -> some View {
        content
            .background(
                isSelected
                    ? MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.selected)
                    : Color.secondary.opacity(DesktopRegistryVisuals.rowSurfaceOpacity),
                in: RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.md, style: .continuous)
            )
    }
}

private extension View {
    func desktopRegistryRowBackground(_ isSelected: Bool) -> some View {
        modifier(DesktopRegistryRowBackground(isSelected: isSelected))
    }
}

private struct DesktopHubModelCardContent: View {
    let card: RuntimeHubModelCardState

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.md) {
            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
                HStack(alignment: .firstTextBaseline, spacing: MelixDesignTokens.Spacing.sm) {
                    Text(card.repoID)
                        .font(.headline)
                        .lineLimit(2)
                        .truncationMode(.middle)
                    DesktopRegistryBadgeView(
                        title: card.runSuitabilityText,
                        tint: DesktopRegistryVisuals.fitColor(card.runSuitabilityText)
                    )
                }
                Text("\(card.author) • \(card.pipelineTag) • \(card.compatibilityText)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            DesktopRegistryRunSuitabilityEvidenceView(
                statusText: card.runSuitabilityText,
                reasons: card.localFitReasons,
                gated: card.gated,
                recommendedAction: card.recommendedAction
            )

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: MelixDesignTokens.Spacing.sm)], spacing: MelixDesignTokens.Spacing.sm) {
                DesktopRegistryMetricTileView(title: "Artifact", value: card.estimatedArtifactBytesText)
                DesktopRegistryMetricTileView(title: "Resident", value: card.estimatedResidentBytesText)
                if !card.parameterCountText.isEmpty {
                    DesktopRegistryMetricTileView(title: "Params", value: card.parameterCountText)
                }
                if !card.quantizationSummary.isEmpty {
                    DesktopRegistryMetricTileView(title: "Quantization", value: card.quantizationSummary)
                }
            }

            if !card.summary.isEmpty {
                Text(card.summary)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(4)
            }

            DesktopRegistryTokenListView(title: "Tags", values: card.tags)
            DesktopRegistryTokenListView(title: "Base Models", values: card.baseModels)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct DesktopRegistryEntryCardContent: View {
    let entry: RuntimeRegistryEntryState
    let localModel: RuntimeModelRow?

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.md) {
            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
                HStack(alignment: .firstTextBaseline, spacing: MelixDesignTokens.Spacing.sm) {
                    Text(entry.title)
                        .font(.headline)
                        .lineLimit(2)
                        .truncationMode(.middle)
                    DesktopRegistryBadgeView(
                        title: entry.sourceText,
                        tint: DesktopRegistryVisuals.sourceColor(entry.sourceText)
                    )
                }
                if !entry.subtitleText.isEmpty {
                    Text(entry.subtitleText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }

            DesktopRegistryRunSuitabilityEvidenceView(
                statusText: entry.runSuitabilityText,
                reasons: localFitReasons,
                gated: false,
                recommendedAction: ""
            )

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: MelixDesignTokens.Spacing.sm)], spacing: MelixDesignTokens.Spacing.sm) {
                DesktopRegistryMetricTileView(title: "Source", value: entry.sourceText)
                DesktopRegistryMetricTileView(title: "Task", value: entry.taskText)
                DesktopRegistryMetricTileView(title: "Status", value: entry.statusText)
                if !entry.sizeText.isEmpty {
                    DesktopRegistryMetricTileView(title: "Size", value: entry.sizeText)
                }
            }

            if let localModel {
                VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
                    Text(localModel.residencyText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(localModel.memoryText)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    if !localModel.memoryAlertText.isEmpty {
                        Text(localModel.memoryAlertText)
                            .font(.caption2)
                            .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    }
                    DesktopMemoryFitReceiptRowsView(rows: localModel.memoryFitReceiptRows)
                    Text("\(localModel.memoryPolicyText) • \(localModel.diskStreamingModeText) • \(localModel.accelerationModeText)")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var localFitReasons: [String] {
        guard let localModel else {
            return []
        }
        var reasons = [localModel.residencyText, localModel.memoryText]
        if !localModel.runtimeCacheDetailText.isEmpty {
            reasons.append(localModel.runtimeCacheDetailText)
        }
        return reasons
    }
}

struct DesktopMemoryFitReceiptRowsView: View {
    let rows: [RuntimeMemoryFitReceiptRow]

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            ForEach(rows) { row in
                Text(Self.displayText(for: row))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
    }

    static func displayText(for row: RuntimeMemoryFitReceiptRow) -> String {
        "Fit \(row.title): \(row.statusText) • \(row.reasonText)"
    }
}

private struct DesktopRegistryRunSuitabilityEvidenceView: View {
    let statusText: String
    let reasons: [String]
    let gated: Bool
    let recommendedAction: String

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.sm) {
            HStack(alignment: .firstTextBaseline, spacing: MelixDesignTokens.Spacing.sm) {
                Text("Run Suitability")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                DesktopRegistryBadgeView(
                    title: statusText,
                    tint: DesktopRegistryVisuals.fitColor(statusText)
                )
            }

            if !recommendedAction.isEmpty {
                Text("Recommended action: \(recommendedAction)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            if gated {
                Text("Gated repository")
                    .font(.caption2)
                    .foregroundStyle(MelixDesignTokens.StatusColor.warning)
            }
            ForEach(reasons.prefix(4), id: \.self) { reason in
                Text(reason)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            if reasons.count > 4 {
                Text("\(reasons.count - 4) more run-suitability reasons hidden.")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(MelixDesignTokens.Spacing.sm)
        .background(
            Color.secondary.opacity(DesktopRegistryVisuals.metricSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.md, style: .continuous)
        )
    }
}

private struct DesktopRegistryMetricTileView: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
            Text(title).melixSectionLabel()
            Text(value.isEmpty ? "unknown" : value)
                .font(.caption.monospacedDigit())
                .foregroundStyle(Color.primary.opacity(0.72))
                .lineLimit(2)
                .truncationMode(.middle)
        }
        .padding(MelixDesignTokens.Spacing.sm)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            Color.secondary.opacity(DesktopRegistryVisuals.metricSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.md, style: .continuous)
        )
    }
}

private struct DesktopRegistryTokenListView: View {
    let title: String
    let values: [String]

    var body: some View {
        if !values.isEmpty {
            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
                Text(title).melixSectionLabel()
                Text(values.joined(separator: ", "))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }
        }
    }
}

private struct DesktopRegistryBadgeView: View {
    let title: String
    let tint: Color

    var body: some View {
        Text(title.isEmpty ? "Unknown" : title)
            .font(.caption2.weight(.semibold))
            .foregroundStyle(tint)
            .lineLimit(1)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(
                tint.opacity(MelixDesignTokens.AccentOpacity.weak),
                in: Capsule()
            )
    }
}

private struct DesktopRegistryMetadataChipView: View {
    let title: String
    var monospaced = false

    var body: some View {
        Text(title.isEmpty ? "unknown" : title)
            .font(monospaced ? .caption2.monospacedDigit() : .caption2)
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .truncationMode(.middle)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(
                Color.secondary.opacity(DesktopRegistryVisuals.chipSurfaceOpacity),
                in: Capsule()
            )
    }
}

private enum DesktopModelRegistryDefaults {
    static let latencyProfileAlias = "Melix Text Turbo"
}

private enum DesktopRegistrySourceKind {
    case local
    case managedDownload
    case huggingFace
    case unknown

    init(text: String) {
        self = .unknown
        let normalized = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if normalized == "local" {
            self = .local
        } else if normalized == "managed download" {
            self = .managedDownload
        } else if normalized == "hugging face" {
            self = .huggingFace
        }
    }
}

private enum DesktopRegistryVisuals {
    static let rowSurfaceOpacity = 0.032
    static let metricSurfaceOpacity = 0.032
    static let chipSurfaceOpacity = 0.035

    static func fitColor(_ text: String) -> Color {
        let normalized = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        switch normalized {
        case "good", "installed":
            return MelixDesignTokens.StatusColor.success
        case "heavy", "pending":
            return MelixDesignTokens.StatusColor.warning
        case "blocked":
            return MelixDesignTokens.StatusColor.error
        case "unknown":
            return MelixDesignTokens.StatusColor.info
        default:
            return .secondary
        }
    }

    static func sourceColor(_ text: String) -> Color {
        switch DesktopRegistrySourceKind(text: text) {
        case .local:
            return MelixDesignTokens.StatusColor.success
        case .managedDownload:
            return MelixDesignTokens.StatusColor.warning
        case .huggingFace:
            return MelixDesignTokens.StatusColor.info
        case .unknown:
            return .secondary
        }
    }
}

private struct DesktopRegistryRootsSectionView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        DesktopRegistryBroadsheetSection("Registry Roots") {
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
                    .foregroundStyle(root.accessible ? Color.secondary : MelixDesignTokens.StatusColor.warning)
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
                            Text(model.displayName)
                                .font(.headline)
                            Spacer()
                            Text(model.stateText)
                                .font(.caption)
                                .foregroundStyle(model.memoryAlertText.isEmpty ? Color.secondary : MelixDesignTokens.StatusColor.warning)
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
                                .foregroundStyle(MelixDesignTokens.StatusColor.error)
                        }
                        if model.loadTrustReceiptRows.isEmpty == false {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Load Trust")
                                    .font(.caption2)
                                    .fontWeight(.semibold)
                                    .foregroundStyle(.secondary)
                                ForEach(model.loadTrustReceiptRows, id: \.self) { row in
                                    Text(row)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .accessibilityElement(children: .combine)
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
                MelixSectionCard("Primary Model") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(primaryModel.displayName)
                            .font(.headline)
                        Text("\(primaryModel.modelID) • \(primaryModel.kind)")
                            .foregroundStyle(.secondary)
                        HStack(spacing: 8) {
                            Text("Quant Profile")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Picker(
                                "Quant Profile",
                                selection: Binding(
                                    get: { viewModel.selectedQuantizationProfileID },
                                    set: { viewModel.selectQuantizationProfile($0) }
                                )
                            ) {
                                ForEach(viewModel.availableQuantizationProfileIDs, id: \.self) { profileID in
                                    Text(profileID).tag(profileID)
                                }
                            }
                            .pickerStyle(.menu)
                            .frame(maxWidth: 120)
                        }
                        HStack(spacing: 8) {
                            Button("Inspect") {
                                Task { await inspectPrimaryModel() }
                            }
                            Button("Doctor") {
                                Task { await runDoctor() }
                            }
                            Button("Bench") {
                                Task { await runBench() }
                            }
                            Menu {
                                Button("Refresh Tooling") {
                                    Task { await refreshModelOpsProductState() }
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
                            } label: {
                                Image(systemName: "ellipsis.circle")
                            }
                            .menuStyle(.borderlessButton)
                            .help("More Model Actions")
                            .accessibilityLabel("More Model Actions")
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            if let info = viewModel.selectedModelInfo {
                MelixSectionCard("Model Info") {
                    DesktopModelInfoSummaryView(info: info)
                }
            }

            if let operation = viewModel.lastModelOperation {
                MelixSectionCard("Last Operation") {
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

            MelixSectionCard("Adapter Registry") {
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

            MelixSectionCard("Training History") {
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
                MelixSectionCard("Doctor Report") {
                    DesktopDoctorReportSummaryView(report: report)
                }
            }

            if let report = viewModel.lastBenchReport {
                MelixSectionCard("Bench Report") {
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
    if !info.requestedLoadTrustModeText.isEmpty {
        detailLines.append("requested trust mode: \(info.requestedLoadTrustModeText)")
    }
    if !info.effectiveLoadTrustModeText.isEmpty {
        detailLines.append("effective trust mode: \(info.effectiveLoadTrustModeText)")
    }
    if !info.loadTrustCustomLoaderText.isEmpty {
        detailLines.append("custom loader: \(info.loadTrustCustomLoaderText)")
    }
    if !info.loadTrustBlockReasonText.isEmpty {
        detailLines.append("trust block reason: \(info.loadTrustBlockReasonText)")
    }
    if !info.loadTrustReloadRequiredText.isEmpty {
        detailLines.append("trust reload: \(info.loadTrustReloadRequiredText)")
    }
    if !info.loadTrustRuntimeGuidanceText.isEmpty {
        detailLines.append("trust guidance: \(info.loadTrustRuntimeGuidanceText)")
    }
    for row in info.capabilityReceiptRows {
        detailLines.append("capability \(row)")
    }
    for row in info.memoryFitReceiptRows {
        detailLines.append("memory fit \(row.title.lowercased()): \(row.statusText) • \(row.reasonText)")
    }
    detailLines.append("pin on load: \(info.pinOnLoad ? "yes" : "no")")
    if info.ttlSeconds > 0 {
        detailLines.append("ttl seconds: \(info.ttlSeconds)")
    }
    detailLines.append("parsers: \(info.supportedParsers.joined(separator: ", "))")
    detailLines.append("modalities: \(info.supportedModalities.joined(separator: ", "))")
    if !info.supportedTasks.isEmpty {
        detailLines.append("tasks: \(info.supportedTasks.joined(separator: ", "))")
    }
    if !info.runtimeStatusText.isEmpty {
        detailLines.append("runtime status: \(info.runtimeStatusText)")
    }
    if !info.runtimePathText.isEmpty {
        detailLines.append("runtime path: \(info.runtimePathText)")
    }
    if !info.registryDescriptorPathText.isEmpty {
        detailLines.append("descriptor path: \(info.registryDescriptorPathText)")
    }
    if !info.restoreCommandText.isEmpty {
        detailLines.append("restore command: \(info.restoreCommandText)")
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
    let viewModel: RuntimeViewModel?

    init(foundation: DesktopFoundationState, viewModel: RuntimeViewModel? = nil) {
        self.foundation = foundation
        self.viewModel = viewModel
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let viewModel, viewModel.runtimeSettingRows.isEmpty == false {
                runtimeSettingsControls(viewModel)
                Text("Runtime Settings")
                    .font(.headline)
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(viewModel.runtimeSettingRows) { row in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(alignment: .firstTextBaseline) {
                                Text(row.key)
                                    .fontWeight(.semibold)
                                Spacer()
                                Text(row.currentValueText)
                                    .foregroundStyle(.primary)
                            }
                            HStack(spacing: 8) {
                                Text(row.source)
                                if row.sourceDetail.isEmpty == false {
                                    Text(row.sourceDetail)
                                }
                                Text(row.validationState.displayTitle)
                            }
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            if row.validationMessage.isEmpty == false {
                                Text(row.validationMessage)
                                    .font(.caption)
                                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                }
                if viewModel.runtimeSettingSources.isEmpty == false {
                    Text("Resolved Sources")
                        .font(.headline)
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(viewModel.runtimeSettingSources) { source in
                            HStack {
                                Text(source.key)
                                    .fontWeight(.semibold)
                                Spacer()
                                Text(source.path)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                if viewModel.runtimeSettingMetrics.isEmpty == false {
                    Text("Resolve Metrics")
                        .font(.headline)
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(viewModel.runtimeSettingMetrics) { metric in
                            HStack {
                                Text(metric.name)
                                    .fontWeight(.semibold)
                                Spacer()
                                Text(metric.valueText)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            } else {
                if let viewModel {
                    runtimeSettingsControls(viewModel)
                }
                ForEach(foundation.settings) { row in
                    HStack {
                        Text(row.key)
                            .fontWeight(.semibold)
                        Spacer()
                        Text(row.value)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            if let viewModel {
                runtimeDiscoveryInspector(viewModel)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(accessibilitySummary)
    }

    private func runtimeSettingsControls(_ viewModel: RuntimeViewModel) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Setting key")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField(
                        "Setting key",
                        text: Binding(
                            get: { viewModel.runtimeSettingKeyDraft },
                            set: { viewModel.updateRuntimeSettingDraft(key: $0, value: viewModel.runtimeSettingValueDraft) }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("Setting value")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField(
                        "Setting value",
                        text: Binding(
                            get: { viewModel.runtimeSettingValueDraft },
                            set: { viewModel.updateRuntimeSettingDraft(key: viewModel.runtimeSettingKeyDraft, value: $0) }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                }
            }
            HStack(spacing: 8) {
                DesktopSettingsOperationButton(title: "Set Setting", isEnabled: viewModel.runtimeSettingsCanSet) {
                    Task { await viewModel.setRuntimeSetting() }
                }
                DesktopSettingsOperationButton(title: "Reset Setting", isEnabled: viewModel.runtimeSettingsCanReset) {
                    Task { await viewModel.resetRuntimeSetting() }
                }
                DesktopSettingsOperationButton(title: "Validate Settings", isEnabled: viewModel.runtimeSettingsCanValidate) {
                    Task { await viewModel.validateRuntimeSettings() }
                }
                if viewModel.runtimeSettingsOperationInProgress {
                    ProgressView()
                        .controlSize(.small)
                }
            }
            if viewModel.runtimeSettingsOperationMessage.isEmpty == false {
                Text(viewModel.runtimeSettingsOperationMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.success)
                    .textSelection(.enabled)
            }
            if viewModel.runtimeSettingsOperationErrorMessage.isEmpty == false {
                Text(viewModel.runtimeSettingsOperationErrorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .textSelection(.enabled)
            }
            if let validationResult = viewModel.runtimeSettingsValidationResult, validationResult.issues.isEmpty == false {
                ForEach(validationResult.issues) { issue in
                    Text("\(issue.key): \(issue.message)")
                        .font(.caption)
                        .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                        .textSelection(.enabled)
                }
            }
        }
    }

    private func runtimeDiscoveryInspector(_ viewModel: RuntimeViewModel) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .center, spacing: 8) {
                Text("Discovery Inspector")
                    .font(.headline)
                Spacer()
                DesktopSettingsOperationButton(title: "Refresh Discovery", isEnabled: !viewModel.runtimeDiscoveryRefreshInProgress) {
                    Task { await viewModel.refreshRuntimeDiscovery() }
                }
                if viewModel.runtimeDiscoveryRefreshInProgress {
                    ProgressView()
                        .controlSize(.small)
                }
            }
            runtimeDiscoveryAliasLookupControls(viewModel)
            if viewModel.runtimeDiscoveryOperationMessage.isEmpty == false {
                Text(viewModel.runtimeDiscoveryOperationMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.success)
                    .textSelection(.enabled)
            }
            if viewModel.runtimeDiscoveryOperationErrorMessage.isEmpty == false {
                Text(viewModel.runtimeDiscoveryOperationErrorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .textSelection(.enabled)
            }
            if viewModel.runtimeDiscoveryPayloads.isEmpty {
                Text("Discovery metadata unavailable.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(viewModel.runtimeDiscoveryPayloads) { payload in
                        runtimeDiscoveryPayload(payload)
                    }
                }
            }
        }
    }

    private func runtimeDiscoveryAliasLookupControls(_ viewModel: RuntimeViewModel) -> some View {
        HStack(alignment: .bottom, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Model alias query")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                TextField(
                    "Model alias query",
                    text: Binding(
                        get: { viewModel.runtimeDiscoveryAliasQueryDraft },
                        set: { viewModel.updateRuntimeDiscoveryAliasQuery($0) }
                    )
                )
                .textFieldStyle(.roundedBorder)
            }
            DesktopSettingsOperationButton(title: "Lookup Alias", isEnabled: viewModel.runtimeDiscoveryAliasLookupCanRun) {
                Task { await viewModel.lookupRuntimeDiscoveryModelAlias() }
            }
        }
    }

    private func runtimeDiscoveryPayload(_ payload: RuntimeDiscoveryPayloadState) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(payload.endpoint.displayTitle)
                    .fontWeight(.semibold)
                Spacer()
                if payload.schemaVersion.isEmpty == false {
                    Text(payload.schemaVersion)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Button(action: { RuntimeDiscoveryClipboard.copy(payload.schemaVersion) }) {
                        Label("Copy Schema Version", systemImage: "doc.on.doc")
                    }
                    .buttonStyle(.borderless)
                    .controlSize(.small)
                }
            }
            ForEach(payload.valueRows) { row in
                discoveryKeyValueRow(row.key, row.value)
            }
            if payload.links.isEmpty == false {
                Text("Endpoint Links")
                    .font(.caption)
                    .fontWeight(.semibold)
                ForEach(payload.links) { link in
                    discoveryEndpointLinkRow(link)
                }
            }
            if payload.models.isEmpty == false {
                Text("Models")
                    .font(.caption)
                    .fontWeight(.semibold)
                ForEach(payload.models) { model in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(model.modelID)
                            .fontWeight(.medium)
                        Text([model.kind, model.supportedModalitiesText, model.supportedTasksText]
                            .filter { $0.isEmpty == false }
                            .joined(separator: " | "))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if model.capabilityReceiptText.isEmpty == false {
                            Text(model.capabilityReceiptText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                    }
                }
            }
            if let alias = payload.aliasDiscovery {
                discoveryKeyValueRow("model_alias.query", alias.query)
                discoveryKeyValueRow("model_alias.status", alias.statusDisplayTitle)
                if alias.suggestions.isEmpty == false {
                    Text("Model Alias Suggestions")
                        .font(.caption)
                        .fontWeight(.semibold)
                    ForEach(alias.suggestions) { suggestion in
                        discoveryKeyValueRow(suggestion.modelID, suggestion.displayText)
                    }
                } else if alias.emptyStateMessage.isEmpty == false {
                    Text(alias.emptyStateMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }
            if payload.instructionAreas.isEmpty == false {
                Text("Instruction Areas")
                    .font(.caption)
                    .fontWeight(.semibold)
                ForEach(payload.instructionAreas) { area in
                    discoveryKeyValueRow(area.title.isEmpty ? area.id : area.title, area.commandsText)
                }
            }
            if payload.schemaPaths.isEmpty == false {
                Text("Schema Paths")
                    .font(.caption)
                    .fontWeight(.semibold)
                ForEach(payload.schemaPaths) { path in
                    discoverySchemaPathRow(path)
                }
            }
            if payload.configSettings.isEmpty == false {
                Text("Runtime Setting Metadata")
                    .font(.caption)
                    .fontWeight(.semibold)
                ForEach(payload.configSettings) { setting in
                    discoveryKeyValueRow(
                        setting.key,
                        [setting.valueType, setting.defaultValueText, setting.environmentVariable, setting.summary]
                            .filter { $0.isEmpty == false }
                            .joined(separator: " | ")
                    )
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func discoveryKeyValueRow(_ key: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline) {
            Text(key)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Text(value)
                .font(.caption)
                .textSelection(.enabled)
        }
    }

    private func discoveryEndpointLinkRow(_ link: RuntimeDiscoveryLinkRowState) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(link.key)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Text(link.url)
                .font(.caption)
                .textSelection(.enabled)
            Button(action: { RuntimeDiscoveryClipboard.copy(link.url) }) {
                Label("Copy Endpoint", systemImage: "doc.on.doc")
            }
            .buttonStyle(.borderless)
            .controlSize(.small)
        }
    }

    private func discoverySchemaPathRow(_ path: RuntimeDiscoverySchemaPathState) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(path.key)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Text(path.path)
                .font(.caption)
                .textSelection(.enabled)
            Button(action: { RuntimeDiscoveryClipboard.copy(path.path) }) {
                Label("Copy Schema Path", systemImage: "doc.on.doc")
            }
            .buttonStyle(.borderless)
            .controlSize(.small)
            Button(action: { openRuntimeDiscoveryPath(path.path) }) {
                Label("Open Schema Path", systemImage: "folder")
            }
            .buttonStyle(.borderless)
            .controlSize(.small)
        }
    }

    var accessibilitySummary: String {
        if let viewModel, viewModel.runtimeSettingRows.isEmpty == false {
            var values = [
                "Setting key",
                "Setting value",
                "Set Setting",
                "Reset Setting",
                "Validate Settings",
                viewModel.runtimeSettingsOperationMessage,
                viewModel.runtimeSettingsOperationErrorMessage,
                "Runtime Settings",
            ]
            values.append(contentsOf: viewModel.runtimeSettingRows.flatMap { row in
                [
                    row.key,
                    row.currentValueText,
                    row.source,
                    row.sourceDetail,
                    row.validationState.displayTitle,
                    row.validationMessage,
                ]
            })
            if viewModel.runtimeSettingSources.isEmpty == false {
                values.append("Resolved Sources")
                values.append(contentsOf: viewModel.runtimeSettingSources.flatMap { [$0.key, $0.path] })
            }
            if viewModel.runtimeSettingMetrics.isEmpty == false {
                values.append("Resolve Metrics")
                values.append(contentsOf: viewModel.runtimeSettingMetrics.flatMap { [$0.name, $0.valueText] })
            }
            if let validationResult = viewModel.runtimeSettingsValidationResult {
                values.append(validationResult.summaryText)
                values.append(contentsOf: validationResult.issues.flatMap { [$0.key, $0.message, $0.source] })
            }
            values.append(contentsOf: runtimeDiscoveryAccessibilityValues(viewModel))
            return values.filter { $0.isEmpty == false }.joined(separator: " ")
        }

        var values = foundation.settings.flatMap { [$0.key, $0.value] }
        if let viewModel {
            values.append(contentsOf: runtimeDiscoveryAccessibilityValues(viewModel))
        }
        return values.filter { $0.isEmpty == false }.joined(separator: " ")
    }

    private func runtimeDiscoveryAccessibilityValues(_ viewModel: RuntimeViewModel) -> [String] {
        var values = [
            "Discovery Inspector",
            "Refresh Discovery",
            "Model alias query",
            "Lookup Alias",
            viewModel.runtimeDiscoveryAliasQueryDraft,
            viewModel.runtimeDiscoveryOperationMessage,
            viewModel.runtimeDiscoveryOperationErrorMessage,
        ]
        if viewModel.runtimeDiscoveryPayloads.isEmpty {
            values.append("Discovery metadata unavailable.")
        }
        for payload in viewModel.runtimeDiscoveryPayloads {
            values.append(payload.endpoint.displayTitle)
            values.append(payload.schemaVersion)
            if payload.schemaVersion.isEmpty == false {
                values.append("Copy Schema Version")
            }
            values.append(contentsOf: payload.valueRows.flatMap { [$0.key, $0.value] })
            values.append(contentsOf: payload.links.flatMap { [$0.key, $0.url] })
            if payload.links.isEmpty == false {
                values.append("Copy Endpoint")
            }
            values.append(contentsOf: payload.models.flatMap {
                [$0.modelID, $0.kind, $0.supportedModalitiesText, $0.supportedTasksText, $0.capabilityReceiptText]
            })
            if let alias = payload.aliasDiscovery {
                values.append(contentsOf: [
                    alias.query,
                    alias.status,
                    alias.statusDisplayTitle,
                    alias.suggestionsText,
                    alias.emptyStateMessage,
                ])
                values.append(contentsOf: alias.suggestions.flatMap {
                    [$0.modelID, $0.family, $0.aliasesText, $0.quantization, $0.displayText]
                })
                if alias.suggestions.isEmpty == false {
                    values.append("Model Alias Suggestions")
                }
            }
            values.append(contentsOf: payload.instructionAreas.flatMap { [$0.id, $0.title, $0.commandsText] })
            values.append(contentsOf: payload.schemaPaths.flatMap { [$0.key, $0.path] })
            if payload.schemaPaths.isEmpty == false {
                values.append(contentsOf: ["Copy Schema Path", "Open Schema Path"])
            }
            values.append(contentsOf: payload.configSettings.flatMap {
                [$0.key, $0.valueType, $0.defaultValueText, $0.environmentVariable, $0.summary]
            })
        }
        return values
    }
}

private struct DesktopSettingsOperationButton: NSViewRepresentable {
    let title: String
    let isEnabled: Bool
    let action: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(action: action)
    }

    func makeNSView(context: Context) -> NSButton {
        let button = NSButton(
            title: title,
            target: context.coordinator,
            action: #selector(Coordinator.performAction(_:))
        )
        button.bezelStyle = .rounded
        button.controlSize = .small
        button.setAccessibilityLabel(title)
        return button
    }

    func updateNSView(_ button: NSButton, context: Context) {
        context.coordinator.action = action
        button.title = title
        button.isEnabled = isEnabled
        button.setAccessibilityLabel(title)
    }

    final class Coordinator: NSObject {
        var action: () -> Void

        init(action: @escaping () -> Void) {
            self.action = action
        }

        @objc func performAction(_ sender: NSButton) {
            action()
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
                        .foregroundStyle(entry.level == "error" ? MelixDesignTokens.StatusColor.error : .secondary)
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

enum RuntimeDiscoveryClipboard {
    @discardableResult
    static func copy(_ value: String, to pasteboard: NSPasteboard = .general) -> Bool {
        let trimmedValue = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmedValue.isEmpty == false else {
            return false
        }
        pasteboard.clearContents()
        return pasteboard.setString(trimmedValue, forType: .string)
    }
}

@discardableResult
func openRuntimeDiscoveryPath(
    _ path: String,
    opener: (URL) -> Bool = { NSWorkspace.shared.open($0) }
) -> Bool {
    let trimmedPath = path.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmedPath.isEmpty == false else {
        return false
    }
    return opener(URL(fileURLWithPath: trimmedPath))
}
