import AppKit
import Charts
import MelixCLICore
import MelixControlPlaneCore
import SwiftUI
import UniformTypeIdentifiers

@MainActor
struct DesktopWorkspaceShellView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        let foundation = viewModel.desktopFoundationState

        VStack(spacing: 0) {
            if let banner = viewModel.desktopBannerState {
                DesktopShellBannerView(banner: banner) {
                    viewModel.dismissDesktopBanner(id: banner.id)
                }
            }

            Group {
                switch viewModel.selectedSurface {
                case .chat:
                    DesktopChatTabView(
                        viewModel: viewModel,
                        showsSidebar: paneVisibilityBinding(.sidebar, for: .chat),
                        showsInspector: paneVisibilityBinding(.inspector, for: .chat)
                    )
                case .image:
                    DesktopImageTabView(
                        viewModel: viewModel,
                        showsSidebar: paneVisibilityBinding(.sidebar, for: .image),
                        showsInspector: paneVisibilityBinding(.inspector, for: .image)
                    )
                case .server:
                    DesktopServerWorkspaceView(
                        viewModel: viewModel,
                        showsSidebar: paneVisibilityBinding(.sidebar, for: .server),
                        showsInspector: paneVisibilityBinding(.inspector, for: .server)
                    )
                case .tools:
                    DesktopToolsWorkspaceView(
                        viewModel: viewModel,
                        foundation: foundation,
                        showsSidebar: paneVisibilityBinding(.sidebar, for: .tools),
                        showsInspector: paneVisibilityBinding(.inspector, for: .tools)
                    )
                case .api:
                    DesktopAPIWorkspaceView(
                        viewModel: viewModel,
                        foundation: foundation,
                        showsSidebar: paneVisibilityBinding(.sidebar, for: .api),
                        showsInspector: paneVisibilityBinding(.inspector, for: .api)
                    )
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .animation(DesktopWorkspacePaneAnimation.animation, value: viewModel.desktopPaneVisibility)
        }
        .padding(.top, DesktopShellChromeMetrics.workspaceTitleBarContentTopInset)
        .sheet(item: Binding(
            get: { viewModel.pendingAudioSetupPrompt },
            set: { newValue in
                if newValue == nil {
                    viewModel.dismissAudioSetupPrompt()
                }
            }
        )) { prompt in
            DesktopAudioSetupPromptView(
                prompt: prompt,
                openDownloads: {
                    viewModel.selectToolSection(.downloads)
                },
                cancel: viewModel.dismissAudioSetupPrompt,
                performPrimaryAction: {
                    Task { await viewModel.performPendingAudioSetupAction() }
                }
            )
        }
        .background(Color(nsColor: .windowBackgroundColor))
    }

    private func paneVisibilityBinding(
        _ role: DesktopPaneRole,
        for surface: DesktopSurface
    ) -> Binding<Bool> {
        Binding(
            get: { viewModel.isDesktopPaneVisible(role, for: surface) },
            set: { viewModel.setDesktopPaneVisible(role, visible: $0, for: surface) }
        )
    }
}

private struct DesktopAudioSetupPromptView: View {
    let prompt: RuntimeAudioSetupPromptState
    let openDownloads: @MainActor () -> Void
    let cancel: @MainActor () -> Void
    let performPrimaryAction: @MainActor () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "waveform.badge.exclamationmark")
                    .font(.title2)
                    .foregroundStyle(MelixDesignTokens.accent)
                VStack(alignment: .leading, spacing: 6) {
                    Text(prompt.title)
                        .font(.title2.weight(.semibold))
                    Text(prompt.detail)
                        .foregroundStyle(.secondary)
                    Text(prompt.alias)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                }
            }

            HStack {
                Button("Open Downloads") {
                    openDownloads()
                    cancel()
                }
                .buttonStyle(.bordered)

                Spacer()

                Button("Not Now", action: cancel)
                    .buttonStyle(.bordered)
                Button(prompt.primaryActionTitle, action: performPrimaryAction)
                    .buttonStyle(.borderedProminent)
            }
        }
        .padding(24)
        .frame(width: 460)
    }
}

private struct DesktopShellBannerView: View {
    let banner: DesktopBannerState
    let dismiss: @MainActor () -> Void

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: bannerSymbolName)
                .foregroundStyle(bannerSeverityColor)
            VStack(alignment: .leading, spacing: 4) {
                Text(banner.title)
                    .font(.headline)
                    .foregroundStyle(.primary)
                Text(banner.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if banner.isDismissible {
                Button(action: dismiss) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .help("Dismiss Banner")
                .accessibilityLabel("Dismiss Banner")
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .background(bannerSeverityColor.opacity(MelixDesignTokens.AccentOpacity.weak))
    }

    private var bannerSymbolName: String {
        switch banner.severity {
        case .info:
            return "moon.stars.fill"
        case .warning:
            return "exclamationmark.circle.fill"
        case .critical:
            return "exclamationmark.triangle.fill"
        }
    }

    private var bannerSeverityColor: Color {
        switch banner.severity {
        case .info:
            return MelixDesignTokens.StatusColor.info
        case .warning:
            return MelixDesignTokens.StatusColor.warning
        case .critical:
            return MelixDesignTokens.StatusColor.error
        }
    }
}

struct DesktopInlineNoticeCardView: View {
    let notice: DesktopBannerState

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: symbolName)
                .foregroundStyle(accentColor)
            VStack(alignment: .leading, spacing: 6) {
                Text(notice.title)
                    .font(.headline)
                Text(notice.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
        }
        .padding(14)
        .background(accentColor.opacity(0.12), in: RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(accentColor.opacity(0.22), lineWidth: 1)
        )
    }

    private var accentColor: Color {
        switch notice.severity {
        case .info:
            return MelixDesignTokens.StatusColor.info
        case .warning:
            return MelixDesignTokens.StatusColor.warning
        case .critical:
            return MelixDesignTokens.StatusColor.error
        }
    }

    private var symbolName: String {
        switch notice.severity {
        case .info:
            return "moon.stars.fill"
        case .warning:
            return "pause.circle.fill"
        case .critical:
            return "exclamationmark.triangle.fill"
        }
    }
}

struct DesktopCommandCenterView: View {
    static let downloadRecoveryOverflowActionTitle = "View All Downloads"

    static func downloadRecoveryOverflowText(totalCount: Int) -> String? {
        let hiddenRecoveryCount = max(0, totalCount - 2)
        guard hiddenRecoveryCount > 0 else { return nil }
        return "+\(hiddenRecoveryCount) more stalled \(hiddenRecoveryCount == 1 ? "download" : "downloads")"
    }

    let foundation: DesktopFoundationState
    let chatSessions: [DesktopChatSessionState]
    let serverSessions: [DesktopServerSessionState]
    private let viewModel: RuntimeViewModel?

    init(
        foundation: DesktopFoundationState,
        chatSessions: [DesktopChatSessionState],
        serverSessions: [DesktopServerSessionState]
    ) {
        self.foundation = foundation
        self.chatSessions = chatSessions
        self.serverSessions = serverSessions
        self.viewModel = nil
    }

    init(viewModel: RuntimeViewModel) {
        self.foundation = viewModel.desktopFoundationState
        self.chatSessions = viewModel.chatSessions
        self.serverSessions = viewModel.serverSessions
        self.viewModel = viewModel
    }

    var body: some View {
        let foundation = liveFoundation
        let chatSessions = liveChatSessions
        let serverSessions = liveServerSessions

        ScrollView {
            VStack(alignment: .leading, spacing: DesktopCommandCenterVisuals.sectionSpacing) {
                DesktopCommandCenterHeaderView(
                    foundation: foundation,
                    lastError: viewModel?.lastError
                )

                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: DesktopCommandCenterVisuals.columnSpacing) {
                        VStack(alignment: .leading, spacing: DesktopCommandCenterVisuals.sectionSpacing) {
                            DesktopCommandCenterRuntimePanel(foundation: foundation)
                            DesktopCommandCenterPressurePanel(foundation: foundation)
                            DesktopCommandCenterActivityPanel(foundation: foundation)
                        }
                        .frame(minWidth: DesktopCommandCenterVisuals.primaryColumnMinimumWidth)

                        VStack(alignment: .leading, spacing: DesktopCommandCenterVisuals.sectionSpacing) {
                            DesktopCommandCenterRecoveryPanel(
                                viewModel: viewModel,
                                serverSessions: serverSessions
                            )
                            DesktopCommandCenterWorkflowPanel(viewModel: viewModel)
                            DesktopCommandCenterSessionSummaryPanel(
                                chatSessions: chatSessions,
                                serverSessions: serverSessions
                            )
                        }
                        .frame(width: DesktopCommandCenterVisuals.secondaryColumnWidth)
                    }

                    VStack(alignment: .leading, spacing: DesktopCommandCenterVisuals.sectionSpacing) {
                        DesktopCommandCenterRuntimePanel(foundation: foundation)
                        DesktopCommandCenterRecoveryPanel(
                            viewModel: viewModel,
                            serverSessions: serverSessions
                        )
                        DesktopCommandCenterPressurePanel(foundation: foundation)
                        DesktopCommandCenterWorkflowPanel(viewModel: viewModel)
                        DesktopCommandCenterActivityPanel(foundation: foundation)
                        DesktopCommandCenterSessionSummaryPanel(
                            chatSessions: chatSessions,
                            serverSessions: serverSessions
                        )
                    }
                }
            }
            .padding(DesktopCommandCenterVisuals.contentPadding)
            .frame(
                maxWidth: DesktopCommandCenterVisuals.maxContentWidth,
                alignment: .leading
            )
        }
        .background(MelixDesignTokens.Palette.backgroundBase.color)
    }

    private var liveFoundation: DesktopFoundationState {
        viewModel?.desktopFoundationState ?? foundation
    }

    private var liveChatSessions: [DesktopChatSessionState] {
        viewModel?.chatSessions ?? chatSessions
    }

    private var liveServerSessions: [DesktopServerSessionState] {
        viewModel?.serverSessions ?? serverSessions
    }
}

enum DesktopCommandCenterVisuals {
    static let repositoryDesignSystemPath = "docs/design-system/README.md"
    static let appleLayoutGuidanceURL = "https://developer.apple.com/design/human-interface-guidelines/layout"
    static let visualDirection = "Digital Broadsheet Command Center"
    static let operatorLabel = "Melix Operator"
    static let windowTitle = "Command Center"
    static let runtimeSectionTitle = "Runtime"
    static let pressureSectionTitle = "Resource And Queue Pressure"
    static let recoverySectionTitle = "Recovery"
    static let workflowSectionTitle = "Workflow"
    static let activitySectionTitle = "Recent Activity"
    static let sessionSummarySectionTitle = "Session Summary"
    static let primaryModelTitle = "Primary Model"
    static let maxContentWidth: CGFloat = 1120
    static let primaryColumnMinimumWidth: CGFloat = 520
    static let secondaryColumnWidth: CGFloat = 320
    static let contentPadding = MelixDesignTokens.Spacing.huge
    static let sectionSpacing = MelixDesignTokens.Spacing.xl
    static let columnSpacing = MelixDesignTokens.Spacing.huge
    static let panelCornerRadius = MelixDesignTokens.Radius.xl
    static let statusSymbolName = "command.circle"
    static let recoverySymbolName = "arrow.clockwise.circle"
}

private struct DesktopCommandCenterHeaderView: View {
    let foundation: DesktopFoundationState
    let lastError: String?

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: MelixDesignTokens.Spacing.lg) {
            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.sm) {
                Text(DesktopCommandCenterVisuals.operatorLabel).melixSectionLabel()
                Text(DesktopCommandCenterVisuals.windowTitle)
                    .font(MelixDesignTokens.Typography.largeTitle)
                Text(foundation.title)
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }

            Spacer(minLength: MelixDesignTokens.Spacing.lg)

            HStack(alignment: .center, spacing: MelixDesignTokens.Spacing.sm) {
                Image(systemName: healthSymbolName)
                    .foregroundStyle(healthTint)
                Text(healthLabel)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(healthTint)
            }
            .padding(.horizontal, MelixDesignTokens.Spacing.md)
            .padding(.vertical, MelixDesignTokens.Spacing.sm)
            .background(
                healthTint.opacity(MelixDesignTokens.AccentOpacity.weak),
                in: Capsule()
            )
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var healthLabel: String {
        switch resolvedHealthState {
        case .runtimeReady:
            return "Runtime Ready"
        case .runtimeWarning:
            return "Runtime Warning"
        case .recoveryAvailable:
            return "Recovery Available"
        case .needsAttention:
            return "Needs Attention"
        case .runtimeState:
            return "Runtime State"
        }
    }

    private var healthSymbolName: String {
        switch resolvedHealthState {
        case .needsAttention:
            return "exclamationmark.triangle.fill"
        case .runtimeWarning:
            return "exclamationmark.triangle"
        case .recoveryAvailable:
            return "pause.circle.fill"
        case .runtimeReady, .runtimeState:
            return DesktopCommandCenterVisuals.statusSymbolName
        }
    }

    private var healthTint: Color {
        switch resolvedHealthState {
        case .needsAttention:
            return MelixDesignTokens.StatusColor.error
        case .runtimeWarning, .recoveryAvailable:
            return MelixDesignTokens.StatusColor.warning
        case .runtimeReady:
            return MelixDesignTokens.StatusColor.success
        case .runtimeState:
            return MelixDesignTokens.StatusColor.info
        }
    }

    private var resolvedHealthState: DesktopFoundationHealthState {
        if let lastError, !lastError.isEmpty {
            return .needsAttention
        }
        return foundation.healthState
    }
}

private struct DesktopCommandCenterPanel<Content: View>: View {
    let title: String
    let symbolName: String
    @ViewBuilder let content: () -> Content

    init(_ title: String, symbolName: String, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.symbolName = symbolName
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.md) {
            HStack(alignment: .center, spacing: MelixDesignTokens.Spacing.sm) {
                Image(systemName: symbolName)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.accent)
                Text(title).melixSectionLabel()
            }

            content()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(MelixDesignTokens.Spacing.panelInset)
        .frame(maxWidth: .infinity, alignment: .leading)
        .melixCard(radius: DesktopCommandCenterVisuals.panelCornerRadius)
    }
}

private struct DesktopCommandCenterRuntimePanel: View {
    let foundation: DesktopFoundationState

    var body: some View {
        DesktopCommandCenterPanel(
            DesktopCommandCenterVisuals.runtimeSectionTitle,
            symbolName: "gauge.with.dots.needle.67percent"
        ) {
            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.lg) {
                HStack(alignment: .top, spacing: MelixDesignTokens.Spacing.xxl) {
                    VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
                        Text(foundation.serverStateText)
                            .font(.title3.weight(.semibold))
                        Text(foundation.connectionStateText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(foundation.connectionDetailText)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                            .lineLimit(2)
                    }

                    Spacer(minLength: MelixDesignTokens.Spacing.md)

                    DesktopCommandCenterPrimaryModelView(model: foundation.models.first)
                        .frame(maxWidth: 300, alignment: .leading)
                }

                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 118), spacing: MelixDesignTokens.Spacing.md)],
                    spacing: MelixDesignTokens.Spacing.md
                ) {
                    ForEach(foundation.dashboardCards.filter { commandCenterMetricIDs.contains($0.id) }) { card in
                        DesktopCommandCenterMetricView(card: card)
                    }
                }
            }
        }
    }

    private var commandCenterMetricIDs: Set<String> {
        ["server", "connection", "backpressure", "memory"]
    }
}

private struct DesktopCommandCenterPrimaryModelView: View {
    let model: RuntimeModelRow?

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
            Text(DesktopCommandCenterVisuals.primaryModelTitle).melixSectionLabel()
            if let model {
                Text(model.displayName)
                    .font(.headline)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text("\(model.modelID) • \(model.stateText)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text("\(model.memoryPolicyText) • \(model.memoryText)")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .lineLimit(2)
            } else {
                Text("No model discovered.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }
}

private struct DesktopCommandCenterMetricView: View {
    let card: DesktopDashboardCard

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
            Text(card.title).melixSectionLabel()
            Text(card.value)
                .font(.headline.monospacedDigit())
                .lineLimit(1)
                .truncationMode(.middle)
            Text(card.detail)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DesktopCommandCenterPressurePanel: View {
    let foundation: DesktopFoundationState

    var body: some View {
        DesktopCommandCenterPanel(
            DesktopCommandCenterVisuals.pressureSectionTitle,
            symbolName: "waveform.path.ecg"
        ) {
            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.md) {
                ForEach(foundation.queueLanes) { lane in
                    DesktopCommandCenterQueueLaneView(lane: lane)
                }
                if foundation.queueLanes.isEmpty {
                    Text("No active queue pressure.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

private struct DesktopCommandCenterQueueLaneView: View {
    let lane: DesktopQueueLaneRow

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
            HStack(alignment: .firstTextBaseline) {
                Text(lane.id)
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                Text("bp \(String(format: "%.2f", lane.backpressure))")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            Text("\(lane.laneClass) • active \(lane.activeRequests) • queued \(lane.queuedRequests)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

private struct DesktopCommandCenterRecoveryPanel: View {
    let viewModel: RuntimeViewModel?
    let serverSessions: [DesktopServerSessionState]

    var body: some View {
        let recoverySessions = serverSessions.filter {
            $0.lifecycle == .error || $0.lifecycle == .stopped || $0.lifecycle == .unavailable
        }
        let recoverableDownloads = viewModel?.recoverableDownloads ?? []
        let hasLatestError = (viewModel?.lastError ?? "").isEmpty == false
        let hasRecovery = recoverableDownloads.isEmpty == false
            || recoverySessions.isEmpty == false
            || hasLatestError

        DesktopCommandCenterPanel(
            DesktopCommandCenterVisuals.recoverySectionTitle,
            symbolName: DesktopCommandCenterVisuals.recoverySymbolName
        ) {
            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.md) {
                if let lastError = viewModel?.lastError, !lastError.isEmpty {
                    DesktopCommandCenterAlertRow(
                        title: "Latest Error",
                        detail: lastError,
                        tint: MelixDesignTokens.StatusColor.error
                    )
                }

                ForEach(recoverableDownloads.prefix(2)) { entry in
                    DesktopCommandCenterDownloadRecoveryRow(
                        entry: entry,
                        resume: {
                            Task { await viewModel?.resumeDownload(jobID: entry.jobID) }
                        }
                    )
                }

                if let viewModel,
                   let overflowText = DesktopCommandCenterView.downloadRecoveryOverflowText(
                    totalCount: recoverableDownloads.count
                   ) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(overflowText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Button(DesktopCommandCenterView.downloadRecoveryOverflowActionTitle) {
                            viewModel.selectSurface(.tools)
                            viewModel.selectToolSection(.downloads)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .fixedSize(horizontal: true, vertical: false)
                    }
                }

                ForEach(recoverySessions) { session in
                    DesktopCommandCenterServerRecoveryRow(session: session)
                }

                if !hasRecovery {
                    Text("No recovery items.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

private struct DesktopCommandCenterAlertRow: View {
    let title: String
    let detail: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
            HStack(alignment: .firstTextBaseline, spacing: MelixDesignTokens.Spacing.xs) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(tint)
                Text(title)
                    .font(.headline)
            }
            Text(detail)
                .font(.caption)
                .foregroundStyle(tint)
                .lineLimit(3)
        }
    }
}

private struct DesktopCommandCenterDownloadRecoveryRow: View {
    let entry: RuntimeDownloadQueueEntryState
    let resume: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.sm) {
            HStack(alignment: .firstTextBaseline, spacing: MelixDesignTokens.Spacing.sm) {
                VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
                    Text(entry.sourceModel)
                        .font(.headline)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Text(entry.progressText)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Spacer(minLength: MelixDesignTokens.Spacing.sm)

                Button(action: resume) {
                    Label(entry.resumeActionTitle, systemImage: "arrow.clockwise")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .fixedSize(horizontal: true, vertical: false)
            }

            if !entry.transferDetailText.isEmpty {
                Text(entry.transferDetailText)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .lineLimit(2)
            }
        }
    }
}

private struct DesktopCommandCenterServerRecoveryRow: View {
    let session: DesktopServerSessionState

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
            Text(session.title)
                .font(.headline)
                .lineLimit(1)
            Text("\(session.lifecycle.rawValue) • \(session.effectiveBaseURL)")
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.middle)
            if !session.lastError.isEmpty {
                Text(session.lastError)
                    .font(.caption2)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .lineLimit(2)
            }
        }
    }
}

private struct DesktopCommandCenterWorkflowPanel: View {
    let viewModel: RuntimeViewModel?

    var body: some View {
        DesktopCommandCenterPanel(
            DesktopCommandCenterVisuals.workflowSectionTitle,
            symbolName: "point.3.connected.trianglepath.dotted"
        ) {
            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.md) {
                if let operation = viewModel?.lastModelOperation {
                    VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
                        Text(operation.operation)
                            .font(.headline)
                            .lineLimit(1)
                        Text("\(operation.modelID) • \(operation.stage)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                        Text(operation.outputPath)
                            .font(.caption2.monospaced())
                            .foregroundStyle(.tertiary)
                            .lineLimit(2)
                            .truncationMode(.middle)
                    }
                } else {
                    Text("No model operation recorded.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

private struct DesktopCommandCenterActivityPanel: View {
    let foundation: DesktopFoundationState

    var body: some View {
        DesktopCommandCenterPanel(
            DesktopCommandCenterVisuals.activitySectionTitle,
            symbolName: "list.bullet.rectangle"
        ) {
            VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.md) {
                ForEach(foundation.logs.prefix(8)) { entry in
                    DesktopCommandCenterActivityRow(entry: entry)
                }
                if foundation.logs.isEmpty {
                    Text("No recent activity.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
        }
    }
}

private struct DesktopCommandCenterActivityRow: View {
    let entry: DesktopLogEntry

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
            HStack(alignment: .firstTextBaseline, spacing: MelixDesignTokens.Spacing.sm) {
                Text(entry.kind)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                Text(entry.level)
                    .font(.caption2.monospaced())
                    .foregroundStyle(
                        entry.level == "error"
                            ? MelixDesignTokens.StatusColor.error
                            : MelixDesignTokens.Palette.foregroundTertiary.color
                    )
            }
            Text(entry.message)
                .font(.body)
                .lineLimit(2)
            Text(entry.detail)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
    }
}

private struct DesktopCommandCenterSessionSummaryPanel: View {
    let chatSessions: [DesktopChatSessionState]
    let serverSessions: [DesktopServerSessionState]

    var body: some View {
        DesktopCommandCenterPanel(
            DesktopCommandCenterVisuals.sessionSummarySectionTitle,
            symbolName: "rectangle.stack"
        ) {
            HStack(alignment: .top, spacing: MelixDesignTokens.Spacing.xxl) {
                DesktopCommandCenterSessionMetricView(
                    title: "Chat Sessions",
                    value: "\(chatSessions.count)",
                    detail: chatSessions.first?.summaryText ?? "No chat sessions"
                )
                DesktopCommandCenterSessionMetricView(
                    title: "Server Sessions",
                    value: "\(serverSessions.count)",
                    detail: serverSessions.first?.effectiveListenerLabel ?? "No listener configured"
                )
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

private struct DesktopCommandCenterSessionMetricView: View {
    let title: String
    let value: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.xs) {
            Text(title).melixSectionLabel()
            Text(value)
                .font(.title3.weight(.semibold).monospacedDigit())
            Text(detail)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DesktopServerWorkspaceView: View {
    let viewModel: RuntimeViewModel
    @Binding var showsSidebar: Bool
    @Binding var showsInspector: Bool
    @State private var showsAdvanced = DesktopServerWorkspaceDefaults.showsAdvancedServingDefaults

    init(
        viewModel: RuntimeViewModel,
        showsSidebar: Binding<Bool>,
        showsInspector: Binding<Bool>
    ) {
        self.viewModel = viewModel
        _showsSidebar = showsSidebar
        _showsInspector = showsInspector
    }

    var body: some View {
        HStack(spacing: 0) {
            DesktopWorkspacePaneSlot(
                role: .sidebar,
                isVisible: showsSidebar,
                idealWidth: 260
            ) {
                DesktopServerSessionSidebar(viewModel: viewModel)
            }

            DesktopServerSessionEditor(
                viewModel: viewModel,
                showsSidebar: $showsSidebar,
                showsInspector: $showsInspector,
                showsAdvanced: $showsAdvanced
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            DesktopWorkspacePaneSlot(
                role: .inspector,
                isVisible: showsInspector,
                idealWidth: 300
            ) {
                DesktopServerSessionInspector(viewModel: viewModel)
            }
        }
    }
}

enum DesktopServerWorkspaceDefaults {
    static let showsAdvancedServingDefaults = false
    static let advancedServingDefaultsTitle = "Advanced Serving Defaults"
}

private struct DesktopServerOverviewCardsView: View {
    let session: DesktopServerSessionState

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 10)], spacing: 10) {
            DesktopServerMetricCard(title: "Port", value: "\(session.effectivePort)", detail: session.gatewayConfigSourceText)
            DesktopServerMetricCard(title: "Context", value: "\(session.servingDefaults.effectiveMaxTokens)", detail: "max tokens")
            DesktopServerMetricCard(title: "Acceleration", value: desktopAccelerationModeText(session.servingDefaults.effectiveAccelerationMode), detail: "serving mode")
            DesktopServerMetricCard(title: "Profile", value: servingAccelerationProfileLabel(session.servingDefaults.effectiveAccelerationProfile), detail: "acceleration defaults")
            DesktopServerMetricCard(title: "State", value: session.lifecycle.rawValue, detail: session.powerState.rawValue)
            DesktopServerMetricCard(title: "Base URL", value: session.effectiveBaseURL, detail: "effective listener")
        }
    }
}

private struct DesktopServerMetricCard: View {
    let title: String
    let value: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            DesktopPassiveStaticTextLabel(
                title: title,
                font: .systemFont(ofSize: NSFont.smallSystemFontSize, weight: .semibold),
                textColor: .secondaryLabelColor
            )
            DesktopPassiveStaticTextLabel(
                title: value,
                font: title == "Base URL"
                    ? .monospacedSystemFont(ofSize: NSFont.smallSystemFontSize, weight: .regular)
                    : .systemFont(ofSize: NSFont.systemFontSize, weight: .semibold),
                textColor: .labelColor
            )
            DesktopPassiveStaticTextLabel(
                title: detail,
                font: .systemFont(ofSize: NSFont.smallSystemFontSize),
                textColor: .secondaryLabelColor
            )
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .melixCard()
    }
}

private struct DesktopServerSessionSidebar: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Servers")
                    .font(.headline)
                Spacer()
                Menu {
                    Button("Add Local Server") {
                        viewModel.beginServerCreation(kind: .localServer)
                    }
                    Button("Add Remote Server") {
                        viewModel.beginServerCreation(kind: .remoteServer)
                    }
                } label: {
                    Image(systemName: "plus")
                }
                .menuStyle(.borderlessButton)
                .focusable(false)
                .help("New Server")
                .accessibilityLabel("New Server")
            }

            if viewModel.serverTargets.isEmpty {
                ContentUnavailableView(
                    "No Servers",
                    systemImage: "network.slash",
                    description: Text("Create a local or remote server target.")
                )
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(viewModel.serverTargets) { target in
                            Button {
                                viewModel.selectServerTarget(id: target.id)
                            } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack {
                                        Text(target.title)
                                            .font(.headline)
                                            .lineLimit(1)
                                        Spacer()
                                        Text(target.badgeText)
                                            .font(.caption.weight(.semibold))
                                            .foregroundStyle(MelixDesignTokens.accent)
                                            .padding(.horizontal, 7)
                                            .padding(.vertical, 3)
                                            .background(
                                                MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.capsule),
                                                in: Capsule()
                                            )
                                    }
                                    Text(target.detailText)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(1)
                                    Text(target.statusText)
                                        .font(.caption)
                                        .foregroundStyle(target.isRunning ? MelixDesignTokens.StatusColor.success : .secondary)
                                        .lineLimit(1)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(12)
                                .background(
                                    viewModel.selectedServerTarget?.id == target.id
                                    ? MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.selected)
                                    : Color.secondary.opacity(0.06),
                                    in: RoundedRectangle(cornerRadius: 12)
                                )
                            }
                            .buttonStyle(.plain)
                            .focusable(false)
                        }
                    }
                }
            }

            Spacer()
        }
        .padding(20)
    }
}

private struct DesktopRemoteServerEditor: View {
    let viewModel: RuntimeViewModel

    private var selectedRemoteServer: RemoteServer? {
        viewModel.remoteServers.first { $0.id == viewModel.selectedRemoteServerID }
    }

    var body: some View {
        MelixSectionCard("Remote Server") {
            VStack(alignment: .leading, spacing: 12) {
                if let selectedRemoteServer {
                    HStack(alignment: .center, spacing: 10) {
                        Image(systemName: "network.badge.shield.half.filled")
                            .foregroundStyle(MelixDesignTokens.accent)
                        VStack(alignment: .leading, spacing: 3) {
                            Text(selectedRemoteServer.title)
                                .font(.headline)
                            Text("\(selectedRemoteServer.defaultModelID) • key \(selectedRemoteServer.apiKeyHint.isEmpty ? "not saved" : selectedRemoteServer.apiKeyHint)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                    }
                }

                HStack(alignment: .top, spacing: 12) {
                    TextField(
                        "Remote Server ID",
                        text: Binding(
                            get: { viewModel.remoteServerIDDraft },
                            set: { viewModel.remoteServerIDDraft = $0 }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                    .disabled(viewModel.isRemoteServerIDEditable == false)

                    TextField(
                        "Session Name",
                        text: Binding(
                            get: { viewModel.remoteServerTitleDraft },
                            set: { viewModel.remoteServerTitleDraft = $0 }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                }

                HStack(alignment: .top, spacing: 12) {
                    Picker(
                        "Provider",
                        selection: Binding(
                            get: { viewModel.remoteServerProviderPresetDraft },
                            set: { viewModel.selectRemoteServerProviderPreset($0) }
                        )
                    ) {
                        ForEach(RemoteServerProviderPreset.allCases) { providerPreset in
                            Text(providerPreset.title).tag(providerPreset)
                        }
                    }
                    .pickerStyle(.menu)

                    TextField(
                        "Default Model",
                        text: Binding(
                            get: { viewModel.remoteServerDefaultModelIDDraft },
                            set: { viewModel.remoteServerDefaultModelIDDraft = $0 }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                }

                TextField(
                    viewModel.isRemoteServerBaseURLEditable ? "Base URL" : "Base URL (preset)",
                    text: Binding(
                        get: { viewModel.remoteServerBaseURLDraft },
                        set: { viewModel.remoteServerBaseURLDraft = $0 }
                    )
                )
                .textFieldStyle(.roundedBorder)
                .disabled(viewModel.isRemoteServerBaseURLEditable == false)

                SecureField(
                    selectedRemoteServer?.apiKeyHint.isEmpty == false ? "Replace API Key" : "API Key",
                    text: Binding(
                        get: { viewModel.remoteServerAPIKeyDraft },
                        set: { viewModel.remoteServerAPIKeyDraft = $0 }
                    )
                )
                .textFieldStyle(.roundedBorder)

                HStack(alignment: .top, spacing: 12) {
                    TextField(
                        "Timeout (s)",
                        value: Binding(
                            get: { viewModel.remoteServerTimeoutSecondsDraft },
                            set: { viewModel.remoteServerTimeoutSecondsDraft = $0 }
                        ),
                        format: .number
                    )
                    .textFieldStyle(.roundedBorder)

                    TextField(
                        "Rate limit / min",
                        value: Binding(
                            get: { viewModel.remoteServerRateLimitPerMinuteDraft },
                            set: { viewModel.remoteServerRateLimitPerMinuteDraft = $0 }
                        ),
                        format: .number
                    )
                    .textFieldStyle(.roundedBorder)
                }

                HStack {
                    Button("New") {
                        viewModel.prepareNewRemoteServerDraft()
                    }
                    .buttonStyle(.bordered)

                    Button("Save Remote Server") {
                        viewModel.saveRemoteServerDraft()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.canSaveRemoteServerDraft == false)

                    Button("Remove") {
                        viewModel.removeSelectedRemoteServer()
                    }
                    .buttonStyle(.bordered)
                    .disabled(viewModel.selectedRemoteServerID.isEmpty)

                    Spacer()
                }
            }
        }
    }
}

private struct DesktopServerCreationEditor: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if viewModel.selectedServerCreationKind == .localServer {
                MelixSectionCard("New Local Session") {
                    localServerCreationContent
                }
            } else {
                DesktopRemoteServerEditor(viewModel: viewModel)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var localServerCreationContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            if viewModel.serverModelOptions.isEmpty {
                if viewModel.isRefreshingServerModelOptions {
                    ContentUnavailableView(
                        "Scanning Ready to Run Models",
                        systemImage: "magnifyingglass",
                        description: Text("Scanning configured model roots and Hugging Face cache snapshots.")
                    )
                } else {
                    ContentUnavailableView(
                        "No Ready to Run Models",
                        systemImage: "shippingbox",
                        description: Text("Rescan model roots or download a model before creating a local server.")
                    )
                }
            } else {
                TextField(
                    "Session Name",
                    text: Binding(
                        get: { viewModel.newLocalServerTitleDraft },
                        set: { viewModel.newLocalServerTitleDraft = $0 }
                    )
                )
                .textFieldStyle(.roundedBorder)

                Picker(
                    "Served Model",
                    selection: Binding(
                        get: { viewModel.newLocalServerModelID },
                        set: { viewModel.newLocalServerModelID = $0 }
                    )
                ) {
                    ForEach(viewModel.serverModelOptions, id: \.modelID) { model in
                        Text(model.displayNameWithID).tag(model.modelID)
                    }
                }
                .pickerStyle(.menu)

                HStack(alignment: .top, spacing: 12) {
                    TextField(
                        "Host",
                        text: Binding(
                            get: { viewModel.newLocalServerHostDraft },
                            set: { viewModel.newLocalServerHostDraft = $0 }
                        )
                    )
                    .textFieldStyle(.roundedBorder)

                    TextField(
                        "Port",
                        value: Binding(
                            get: { viewModel.newLocalServerPortDraft },
                            set: { viewModel.newLocalServerPortDraft = $0 }
                        ),
                        format: .number
                    )
                    .textFieldStyle(.roundedBorder)
                    .frame(maxWidth: 120)
                }

                HStack {
                    Spacer()
                    Button("Cancel") {
                        viewModel.cancelServerCreation()
                    }
                    .buttonStyle(.bordered)

                    Button("Save") {
                        viewModel.createLocalServerFromDraft()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.canCreateLocalServerFromDraft == false)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DesktopServerLoRAAdapterSection: View {
    let viewModel: RuntimeViewModel

    private var selectedAdapterOption: RuntimeServerAdapterOptionState? {
        viewModel.serverAdapterOptions.first(where: \.isSelected)
    }

    var body: some View {
        MelixSectionCard("LoRA Adapter") {
            VStack(alignment: .leading, spacing: 12) {
                if viewModel.serverAdapterOptions.isEmpty {
                    Text("No LoRA adapters are available.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                } else {
                    Picker(
                        "Adapter",
                        selection: Binding(
                            get: { selectedAdapterOption?.id ?? "" },
                            set: { id in
                                guard id.isEmpty == false else {
                                    return
                                }
                                viewModel.applyServerAdapterPackage(id: id)
                            }
                        )
                    ) {
                        Text("Base model").tag("")
                        ForEach(viewModel.serverAdapterOptions) { option in
                            Text(option.title).tag(option.id)
                        }
                    }
                    .pickerStyle(.menu)

                    adapterStateSummary
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private var adapterStateSummary: some View {
        if let option = selectedAdapterOption {
            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 8) {
                    Text("Serving derived model")
                        .font(.headline)
                    Text("LoRA active")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(MelixDesignTokens.accent)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(
                            MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.capsule),
                            in: Capsule()
                        )
                }
                Text(option.title)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Text(option.derivedModelID)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text("Activation: \(option.activationStatusText)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.selected),
                in: RoundedRectangle(cornerRadius: 10)
            )
        } else {
            VStack(alignment: .leading, spacing: 8) {
                Text("The selected server model is being served directly.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                ForEach(viewModel.serverAdapterOptions) { option in
                    HStack(alignment: .center, spacing: 10) {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(option.title)
                                .font(.caption.weight(.semibold))
                            Text(option.detailText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                        Spacer()
                        if option.isServeable {
                            Button(option.actionTitle) {
                                viewModel.applyServerAdapterPackage(id: option.id)
                            }
                            .buttonStyle(.borderedProminent)
                        } else {
                            Button(option.actionTitle) {
                                viewModel.applyServerAdapterPackage(id: option.id)
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                }
            }
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 10))
        }
    }
}

private struct DesktopServerSessionEditor: View {
    let viewModel: RuntimeViewModel
    @Binding var showsSidebar: Bool
    @Binding var showsInspector: Bool
    @Binding var showsAdvanced: Bool

    private let servingAccelerationModeOptions = [
        ("None", "baseline"),
        ("Speculative Decode", "speculative_decode"),
        ("Accelerated Prefill", "accelerated_prefill"),
        ("Active KV Quantized", "active_kv_quantized"),
        ("Sparse Prefill", "sparse_prefill"),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                DesktopWorkspaceHeader(
                    title: "Server",
                    subtitle: "Choose model, configure listener, then start the server session."
                ) {}

                if viewModel.isCreatingServerTarget {
                    DesktopServerCreationEditor(viewModel: viewModel)
                } else if viewModel.selectedServerTarget?.kind == .remoteServer {
                    DesktopRemoteServerEditor(viewModel: viewModel)
                } else if let session = viewModel.selectedServerSession,
                          viewModel.selectedServerTarget?.kind == .localServer {
                    if let notice = session.lifecycleBannerState {
                        DesktopInlineNoticeCardView(notice: notice)
                    }

                    DesktopServerOverviewCardsView(session: session)

                    MelixSectionCard("Basic Configuration") {
                        VStack(alignment: .leading, spacing: 12) {
                            Picker(
                                "Served Model",
                                selection: Binding(
                                    get: { session.modelID },
                                    set: { viewModel.updateSelectedServerSessionModelID($0) }
                                )
                            ) {
                                ForEach(viewModel.serverModelOptions, id: \.modelID) { model in
                                    Text(model.displayNameWithID).tag(model.modelID)
                                }
                            }
                            if viewModel.serverModelOptions.isEmpty {
                                Text(viewModel.isRefreshingServerModelOptions
                                    ? "Scanning Ready to Run model roots..."
                                    : "No Ready to Run models are available. Rescan model roots or download a model before starting a local server.")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

                            HStack {
                                TextField(
                                    "Host",
                                    text: Binding(
                                        get: { viewModel.selectedServerSession?.host ?? MelixGatewayDefaults.host },
                                        set: { viewModel.updateSelectedServerSessionHost($0) }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)

                                TextField(
                                    "Port",
                                    value: Binding(
                                        get: { viewModel.selectedServerSession?.port ?? MelixGatewayDefaults.port },
                                        set: { viewModel.updateSelectedServerSessionPort($0) }
                                    ),
                                    format: .number
                                )
                                .textFieldStyle(.roundedBorder)
                                .frame(maxWidth: 120)
                            }

                            DesktopServerGatewayAccessSummaryView(session: session)

                            HStack {
                                TextField(
                                    "Rate limit / min",
                                    value: Binding(
                                        get: { viewModel.selectedServerSession?.rateLimitPerMinute ?? 120 },
                                        set: { viewModel.updateSelectedServerSessionRateLimit($0) }
                                    ),
                                    format: .number
                                )
                                .textFieldStyle(.roundedBorder)

                                TextField(
                                    "Timeout (s)",
                                    value: Binding(
                                        get: { viewModel.selectedServerSession?.timeoutSeconds ?? 120 },
                                        set: { viewModel.updateSelectedServerSessionTimeout($0) }
                                    ),
                                    format: .number
                                )
                                .textFieldStyle(.roundedBorder)
                            }

                            Text(
                                session.gatewayConfigRequiresRestart
                                    ? "Requested listener differs from the active binding. Restart required."
                                    : "Listener config source: \(session.gatewayConfigSourceText)"
                            )
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    DesktopServerLoRAAdapterSection(viewModel: viewModel)

                    MelixSectionCard("Serving Defaults") {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(servingDefaultsCompactSummary(for: session))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            if let disabledReason = viewModel.selectedServerAccelerationModeDisabledReason {
                                Text(disabledReason)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            DesktopServingAccelerationProfilePicker(viewModel: viewModel)
                            DesktopServingAccelerationProfileSummary(servingDefaults: session.servingDefaults)
                            DisclosureGroup(DesktopServerWorkspaceDefaults.advancedServingDefaultsTitle, isExpanded: $showsAdvanced) {
                                advancedServingDefaultsForm(for: session)
                                    .padding(.top, 12)
                            }
                        }
                    }

                    MelixSectionCard("Lifecycle Controls") {
                        VStack(alignment: .leading, spacing: 12) {
                            Text(session.runtimeDetailText)
                                .font(.caption)
                                .foregroundStyle(.secondary)

                            HStack {
                                Button("Start") {
                                    Task { await viewModel.startSelectedServerSession() }
                                }
                                .buttonStyle(.borderedProminent)
                                .disabled(session.canStart == false)

                                Button("Stop") {
                                    Task { await viewModel.stopSelectedServerSession() }
                                }
                                .buttonStyle(.bordered)
                                .disabled(session.canStop == false)

                                Menu {
                                    Button("Pause") {
                                        Task { await viewModel.pauseSelectedServerSession() }
                                    }
                                    .disabled(session.canPause == false)
                                    Button("Resume") {
                                        Task { await viewModel.resumeSelectedServerSession() }
                                    }
                                    .disabled(session.canResume == false)
                                    Button("Wake") {
                                        Task { await viewModel.wakeSelectedServerSession() }
                                    }
                                    .disabled(session.canWake == false)
                                    Button("Apply Gateway Config") {
                                        Task { await viewModel.applySelectedServerGatewayConfig() }
                                    }
                                    Button("Apply Idle Policy") {
                                        Task { await viewModel.applySelectedServerIdlePolicy() }
                                    }
                                } label: {
                                    Image(systemName: "ellipsis.circle")
                                }
                                .menuStyle(.borderlessButton)
                                .help("More Server Actions")
                                .accessibilityLabel("More Server Actions")
                            }

                            Toggle(
                                "Auto Sleep",
                                isOn: Binding(
                                    get: { viewModel.selectedServerSession?.autoSleepEnabled ?? false },
                                    set: { viewModel.updateSelectedServerSessionAutoSleepEnabled($0) }
                                )
                            )

                            HStack {
                                TextField(
                                    "Light sleep after (s)",
                                    value: Binding(
                                        get: { viewModel.selectedServerSession?.lightSleepAfterSeconds ?? 0 },
                                        set: { viewModel.updateSelectedServerSessionLightSleepAfterSeconds($0) }
                                    ),
                                    format: .number
                                )
                                .textFieldStyle(.roundedBorder)

                                TextField(
                                    "Deep sleep after (s)",
                                    value: Binding(
                                        get: { viewModel.selectedServerSession?.deepSleepAfterSeconds ?? 0 },
                                        set: { viewModel.updateSelectedServerSessionDeepSleepAfterSeconds($0) }
                                    ),
                                    format: .number
                                )
                                .textFieldStyle(.roundedBorder)

                            }

                            Text(session.idlePolicySummaryText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                } else {
                    ContentUnavailableView(
                        "No Server Selected",
                        systemImage: "server.rack",
                        description: Text("Choose a server from the list or create a new one.")
                    )
                }

                Spacer()
            }
            .padding(20)
        }
    }

    private func servingDefaultsCompactSummary(for session: DesktopServerSessionState) -> String {
        let servingDefaults = session.servingDefaults
        return "Source: \(servingDefaults.sourceText) • requested temp \(String(format: "%.2f", servingDefaults.temperature)) • top_p \(String(format: "%.2f", servingDefaults.topP)) • max \(servingDefaults.maxTokens) • stream \(servingDefaults.streamIntervalTokens) • sequences \(servingDefaults.maxConcurrentRequests)"
    }

    @ViewBuilder
    private func advancedServingDefaultsForm(for session: DesktopServerSessionState) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                                    TextField(
                                        "Temperature",
                                        value: Binding(
                                            get: { viewModel.selectedServerSession?.servingDefaults.temperature ?? 0.7 },
                                            set: { viewModel.updateSelectedServerSessionTemperature($0) }
                                        ),
                                        format: .number
                                    )
                                    .textFieldStyle(.roundedBorder)

                                    TextField(
                                        "Top P",
                                        value: Binding(
                                            get: { viewModel.selectedServerSession?.servingDefaults.topP ?? 1.0 },
                                            set: { viewModel.updateSelectedServerSessionTopP($0) }
                                        ),
                                        format: .number
                                    )
                                    .textFieldStyle(.roundedBorder)
                                }

                                HStack {
                                    TextField(
                                        "Max tokens",
                                        value: Binding(
                                            get: { viewModel.selectedServerSession?.servingDefaults.maxTokens ?? 256 },
                                            set: { viewModel.updateSelectedServerSessionMaxTokens($0) }
                                        ),
                                        format: .number
                                    )
                                    .textFieldStyle(.roundedBorder)

                                    TextField(
                                        "Stream interval",
                                        value: Binding(
                                            get: { viewModel.selectedServerSession?.servingDefaults.streamIntervalTokens ?? 1 },
                                            set: { viewModel.updateSelectedServerSessionStreamIntervalTokens($0) }
                                        ),
                                        format: .number
                                    )
                                    .textFieldStyle(.roundedBorder)
                                }

                                HStack {
                                    TextField(
                                        "Max concurrent sequences",
                                        value: Binding(
                                            get: { viewModel.selectedServerSession?.servingDefaults.maxConcurrentRequests ?? 4 },
                                            set: { viewModel.updateSelectedServerSessionMaxConcurrentRequests($0) }
                                        ),
                                        format: .number
                                    )
                                    .textFieldStyle(.roundedBorder)
                                }

                                Toggle(
                                    "Concurrent processing",
                                    isOn: Binding(
                                        get: { viewModel.selectedServerSession?.servingDefaults.concurrentProcessingEnabled ?? true },
                                        set: { viewModel.updateSelectedServerSessionConcurrentProcessingEnabled($0) }
                                    )
                                )

                                HStack {
                                    TextField(
                                        "Prefill batch size",
                                        value: Binding(
                                            get: { viewModel.selectedServerSession?.servingDefaults.prefillBatchSize ?? 2 },
                                            set: { viewModel.updateSelectedServerSessionPrefillBatchSize($0) }
                                        ),
                                        format: .number
                                    )
                                    .textFieldStyle(.roundedBorder)

                                    TextField(
                                        "Completion batch size",
                                        value: Binding(
                                            get: { viewModel.selectedServerSession?.servingDefaults.completionBatchSize ?? 2 },
                                            set: { viewModel.updateSelectedServerSessionCompletionBatchSize($0) }
                                        ),
                                        format: .number
                                    )
                                    .textFieldStyle(.roundedBorder)
                                }

                                Picker(
                                    "Acceleration Mode",
                                    selection: Binding(
                                        get: { viewModel.selectedServerSession?.servingDefaults.accelerationMode ?? "baseline" },
                                        set: { viewModel.updateSelectedServerSessionAccelerationMode($0) }
                                    )
                                ) {
                                    ForEach(servingAccelerationModeOptions, id: \.1) { option in
                                        Text(option.0).tag(option.1)
                                    }
                                }
                                .pickerStyle(.menu)
                                .frame(maxWidth: 280, alignment: .leading)

                                serverAccelerationModeConfiguration(
                                    mode: viewModel.selectedServerSession?.servingDefaults.accelerationMode ?? session.servingDefaults.accelerationMode
                                )

                                HStack {
                                    Button("Apply Serving Defaults", action: viewModel.applySelectedServerServingDefaultsFromUI)
                                    .buttonStyle(.bordered)

                                    let servingDefaults = session.servingDefaults
                                    Text(
                                        "Source: \(servingDefaults.sourceText) • Effective temp \(servingDefaults.effectiveTemperature, format: .number.precision(.fractionLength(2))) • top_p \(servingDefaults.effectiveTopP, format: .number.precision(.fractionLength(2))) • max \(servingDefaults.effectiveMaxTokens) • stream \(servingDefaults.effectiveStreamIntervalTokens) • concurrent \(servingDefaults.effectiveConcurrentProcessingEnabled ? "on" : "off") • sequences \(servingDefaults.effectiveMaxConcurrentRequests) • prefill \(servingDefaults.effectivePrefillBatchSize) • completion \(servingDefaults.effectiveCompletionBatchSize) • accel \(desktopAccelerationModeText(servingDefaults.effectiveAccelerationMode))\(servingDefaults.effectiveDraftModelID.isEmpty ? "" : " • draft \(servingDefaults.effectiveDraftModelID)")\(servingDefaults.effectiveNumDraftTokens > 0 ? " • draft tokens \(servingDefaults.effectiveNumDraftTokens)" : "")\(servingDefaults.modelOverrideApplied ? " • model override applied" : "")"
                                    )
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                }
                            }
    }

    @ViewBuilder
    private func serverAccelerationModeConfiguration(mode: String) -> some View {
        switch mode {
        case "speculative_decode":
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    TextField(
                        "Draft model id",
                        text: Binding(
                            get: { viewModel.selectedServerSession?.servingDefaults.draftModelID ?? "" },
                            set: { viewModel.updateSelectedServerSessionDraftModelID($0) }
                        )
                    )
                    .textFieldStyle(.roundedBorder)

                    TextField(
                        "Num draft tokens",
                        value: Binding(
                            get: { viewModel.selectedServerSession?.servingDefaults.numDraftTokens ?? 0 },
                            set: { viewModel.updateSelectedServerSessionNumDraftTokens($0) }
                        ),
                        format: .number
                    )
                    .textFieldStyle(.roundedBorder)
                }
                Text("Draft model settings apply only when Speculative Decode is selected.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(10)
            .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 10))
        case "accelerated_prefill":
            accelerationModeReadOnlyCard("Uses the backend accelerated prefill profile for this server session.")
        case "active_kv_quantized":
            accelerationModeReadOnlyCard("Uses the backend active KV quantization profile for this server session.")
        case "sparse_prefill":
            accelerationModeReadOnlyCard("Uses the backend sparse prefill profile for this server session.")
        default:
            accelerationModeReadOnlyCard("No additional acceleration settings are enabled for this server session.")
        }
    }

    private func accelerationModeReadOnlyCard(_ text: String) -> some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(.secondary)
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color.secondary.opacity(0.04), in: RoundedRectangle(cornerRadius: 10))
    }
}

private struct DesktopServerSessionInspector: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Inspector")
                .font(.headline)

            if let session = viewModel.selectedServerSession {
                GroupBox("Status") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(session.lifecycleSummaryText)
                            .font(.headline)
                        Text(session.lastKnownModelStateText.isEmpty ? session.modelID : "\(session.modelID) • \(session.lastKnownModelStateText)")
                            .foregroundStyle(.secondary)
                        Text(session.runtimeDetailText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                GroupBox("Listener") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Requested: \(session.baseURL)")
                            .font(.body.monospaced())
                        Text("Effective: \(session.effectiveBaseURL)")
                            .font(.body.monospaced())
                        Text(
                            session.gatewayConfigRequiresRestart
                                ? "\(session.gatewayConfigSourceText) • restart required to move the live listener"
                                : session.gatewayConfigSourceText
                        )
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        HStack {
                            Button("Copy URL") {
                                copyToPasteboard(session.effectiveBaseURL)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                DesktopServerGatewayAccessSummaryView(session: session)

                GroupBox("Power Policy") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(session.idlePolicySummaryText)
                            .font(.headline)
                        Text("Wake reason: \(session.wakeReason.rawValue)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                DesktopBoundAgentIntegrationPanel(viewModel: viewModel)

                if !session.lastError.isEmpty {
                    GroupBox("Error") {
                        Text(session.lastError)
                            .foregroundStyle(MelixDesignTokens.StatusColor.error)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            } else {
                Text("Server status and copy actions appear here.")
                    .foregroundStyle(.secondary)
            }

            Spacer()
        }
        .padding(20)
    }
}

private struct DesktopToolsWorkspaceView: View {
    let viewModel: RuntimeViewModel
    let foundation: DesktopFoundationState
    @Binding var showsSidebar: Bool
    @Binding var showsInspector: Bool

    init(
        viewModel: RuntimeViewModel,
        foundation: DesktopFoundationState,
        showsSidebar: Binding<Bool>,
        showsInspector: Binding<Bool>
    ) {
        self.viewModel = viewModel
        self.foundation = foundation
        _showsSidebar = showsSidebar
        _showsInspector = showsInspector
    }

    var body: some View {
        let workspaceBackground = toolsWorkspaceBackground

        HStack(spacing: 0) {
            DesktopWorkspacePaneSlot(
                role: .sidebar,
                isVisible: showsSidebar,
                idealWidth: 250
            ) {
                DesktopToolsCategorySidebarView(
                    selectedToolSection: viewModel.selectedToolSection,
                    selectToolSection: viewModel.selectToolSection
                )
                .padding(20)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    DesktopWorkspaceHeader(title: viewModel.selectedToolSection.rawValue) {}

                    switch viewModel.selectedToolSection {
                    case .modelsLibrary:
                        DesktopModelsTabView(foundation: foundation, viewModel: viewModel)
                    case .downloads:
                        DesktopDownloadsToolSectionView(viewModel: viewModel)
                    case .training:
                        DesktopTrainingToolSectionView(viewModel: viewModel)
                    case .workflowRecipes:
                        DesktopWorkflowRecipesToolSectionView(viewModel: viewModel)
                    case .syntheticDatasets:
                        DesktopSyntheticDatasetToolSectionView(viewModel: viewModel)
                    case .batchRuns:
                        DesktopBatchRunsToolSectionView(viewModel: viewModel)
                    case .jobs:
                        DesktopJobsToolSectionView(viewModel: viewModel)
                    case .diagnostics:
                        DesktopDiagnosticsToolSectionView(viewModel: viewModel, foundation: foundation)
                    case .logs:
                        DesktopLogsTabView(foundation: foundation)
                    case .settings:
                        DesktopSettingsTabView(foundation: foundation, viewModel: viewModel)
                    }
                }
                .padding(20)
            }
            .background(workspaceBackground)
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            DesktopWorkspacePaneSlot(
                role: .inspector,
                isVisible: showsInspector,
                idealWidth: 300
            ) {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Inspector")
                        .font(.headline)

                    if let primaryModel = viewModel.primaryModel {
                        GroupBox("Primary Model") {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(primaryModel.displayName)
                                    .font(.headline)
                                Text("\(primaryModel.modelID) • \(primaryModel.stateText)")
                                    .foregroundStyle(.secondary)
                                Text(primaryModel.memoryText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }

                    if let operation = viewModel.lastModelOperation {
                        GroupBox("Last Operation") {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(operation.operation)
                                    .font(.headline)
                                Text(operation.outputPath)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }

                    Spacer()
                }
                .padding(20)
            }
        }
        .background(workspaceBackground)
    }

    private var toolsWorkspaceBackground: Color {
        switch viewModel.selectedToolSection {
        case .training, .diagnostics:
            return DesktopLoRAVisualPolish.pageBackgroundColor
        case .modelsLibrary, .downloads, .workflowRecipes, .syntheticDatasets, .batchRuns, .jobs, .logs, .settings:
            return Color(nsColor: .windowBackgroundColor)
        }
    }
}

struct DesktopToolsCategorySidebarView: View {
    let selectedToolSection: DesktopToolSection
    let selectToolSection: (DesktopToolSection) -> Void

    static func accessibilityLabel(category: DesktopToolCategory, section: DesktopToolSection) -> String {
        "\(category.rawValue) \(section.rawValue)"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Tools")
                .font(.headline)
            ForEach(DesktopToolCategory.allCases) { category in
                VStack(alignment: .leading, spacing: 6) {
                    Text(category.rawValue)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)
                    ForEach(category.sections) { section in
                        Button {
                            selectToolSection(section)
                        } label: {
                            Label(section.rawValue, systemImage: section.symbolName)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 10)
                                .background(
                                    selectedToolSection == section
                                    ? MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.selected)
                                    : Color.secondary.opacity(0.06),
                                    in: RoundedRectangle(cornerRadius: 12)
                                )
                        }
                        .buttonStyle(.plain)
                        .help(section.rawValue)
                        .accessibilityLabel(Self.accessibilityLabel(category: category, section: section))
                    }
                }
            }
            Spacer()
        }
    }
}

struct DesktopDownloadsToolSectionView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Model ingress and artifact publishing stay under Tools, not Server.")
                .foregroundStyle(.secondary)

            MelixSectionCard("Packaging Target") {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(viewModel.modelOperationTargetModelID.isEmpty ? "No model selected" : viewModel.modelOperationTargetModelID)
                            .font(.headline)
                        Text(viewModel.modelOperationTargetDetailText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    Spacer(minLength: 12)

                    Picker(
                        "Quant Mode",
                        selection: Binding(
                            get: { viewModel.selectedQuantizationMode },
                            set: { viewModel.selectedQuantizationMode = $0 }
                        )
                    ) {
                        ForEach(RuntimeQuantizationMode.allCases) { mode in
                            Text(mode.title).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)
                    .frame(width: 128)

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

                    if viewModel.hasExplicitModelOperationTarget {
                        Button("Use Primary Model") {
                            viewModel.usePrimaryModelOperationTarget()
                        }
                        .buttonStyle(.bordered)
                    }
                }
            }

            if viewModel.audioSetupActions.isEmpty == false {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(viewModel.audioSetupActions) { action in
                        DesktopAudioSetupNoticeRow(
                            action: action,
                            performAction: { viewModel.presentAudioSetupPrompt(action) }
                        )
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            HStack {
                Button("Quantize Model") {
                    Task { await viewModel.quantizePrimaryModel() }
                }
                .buttonStyle(.bordered)
                .fixedSize(horizontal: true, vertical: false)

                Button("Convert Model") {
                    Task { await viewModel.convertPrimaryModel() }
                }
                .buttonStyle(.bordered)
                .fixedSize(horizontal: true, vertical: false)

                Button("Download Model") {
                    Task { await viewModel.downloadPrimaryModel() }
                }
                .buttonStyle(.borderedProminent)
                .fixedSize(horizontal: true, vertical: false)

                Button("Upload Artifact") {
                    Task { await viewModel.uploadPrimaryModel() }
                }
                .buttonStyle(.bordered)
                .fixedSize(horizontal: true, vertical: false)
            }

            MelixSectionCard("Download Queue") {
                VStack(alignment: .leading, spacing: 12) {
                    HStack {
                        Text("Registry-backed queue state survives shell restart and can resume partial transfers.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Spacer()
                        Button("Refresh Queue") {
                            Task { await viewModel.refreshDownloadQueueState() }
                        }
                        .buttonStyle(.bordered)
                    }

                    if viewModel.downloadQueue.isEmpty {
                        Text("No downloads recorded yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(viewModel.downloadQueue) { entry in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack(alignment: .firstTextBaseline) {
                                    VStack(alignment: .leading, spacing: 2) {
                                        Text(entry.sourceModel)
                                            .font(.headline)
                                        Text(entry.statusText)
                                            .font(.caption.weight(.semibold))
                                            .foregroundStyle(entry.resumeReady ? MelixDesignTokens.StatusColor.warning : .secondary)
                                    }
                                    Spacer()
                                    if entry.resumeReady {
                                        Button(entry.resumeActionTitle) {
                                            Task { await viewModel.resumeDownload(jobID: entry.jobID) }
                                        }
                                        .buttonStyle(.borderedProminent)
                                    }
                                }

                                Text(entry.progressText)
                                    .font(.caption.monospacedDigit())
                                if entry.transferDetailText.isEmpty == false {
                                    Text(entry.transferDetailText)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                if entry.outputDir.isEmpty == false {
                                    Text(entry.outputDir)
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(.tertiary)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                            .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            if let operation = viewModel.lastModelOperation {
                MelixSectionCard("Recent Transfer") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("\(operation.operation) • \(operation.modelID)")
                            .font(.headline)
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
                        Text(operation.outputPath)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        }
    }

}

struct DesktopWorkflowRecipesToolSectionView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .bottom, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Task filter")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField(
                        "Task filter",
                        text: Binding(
                            get: { viewModel.workflowRecipeTaskFilterDraft },
                            set: { viewModel.updateWorkflowRecipeTaskFilter($0) }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                }
                Button("Refresh Catalog", action: refreshCatalogAction)
                .buttonStyle(.borderedProminent)
                .disabled(viewModel.workflowRecipeCatalogInProgress)

                VStack(alignment: .leading, spacing: 4) {
                    Text("URI to inspect")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField(
                        "URI to inspect",
                        text: Binding(
                            get: { viewModel.workflowRecipeURIInspectDraft },
                            set: { viewModel.updateWorkflowRecipeURIInspectDraft($0) }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                }
                Button("Inspect URI", action: inspectURIAction)
                    .buttonStyle(.bordered)
                    .disabled(viewModel.workflowRecipeURIInspectCanRun == false)

                if viewModel.workflowRecipeCatalogInProgress
                    || viewModel.workflowRecipeDetailInProgress
                    || viewModel.workflowRecipeURIInspectInProgress
                    || viewModel.workflowRecipeInitPreviewInProgress
                {
                    ProgressView()
                        .controlSize(.small)
                }
            }

            if viewModel.workflowRecipeCatalog.availableTaskFilters.isEmpty == false {
                HStack(spacing: 8) {
                    ForEach(viewModel.workflowRecipeCatalog.availableTaskFilters, id: \.self) { task in
                        Button(task) {
                            applyTaskFilter(task)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                    Button("Clear", action: clearTaskFilter)
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }

            if viewModel.workflowRecipeCatalogMessage.isEmpty == false {
                Text(viewModel.workflowRecipeCatalogMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.success)
                    .textSelection(.enabled)
            }
            if viewModel.workflowRecipeCatalogErrorMessage.isEmpty == false {
                Text(viewModel.workflowRecipeCatalogErrorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .textSelection(.enabled)
            }
            if viewModel.workflowRecipeURIInspectMessage.isEmpty == false {
                Text(viewModel.workflowRecipeURIInspectMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.success)
                    .textSelection(.enabled)
            }
            if viewModel.workflowRecipeURIInspectErrorMessage.isEmpty == false {
                Text(viewModel.workflowRecipeURIInspectErrorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .textSelection(.enabled)
            }
            if viewModel.workflowRecipeInitPreviewMessage.isEmpty == false {
                Text(viewModel.workflowRecipeInitPreviewMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.success)
                    .textSelection(.enabled)
            }
            if viewModel.workflowRecipeInitPreviewErrorMessage.isEmpty == false {
                Text(viewModel.workflowRecipeInitPreviewErrorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .textSelection(.enabled)
            }
            if viewModel.workflowRecipeSetEditorMessage.isEmpty == false {
                Text(viewModel.workflowRecipeSetEditorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.success)
                    .textSelection(.enabled)
            }
            if viewModel.workflowRecipeSetEditorErrorMessage.isEmpty == false {
                Text(viewModel.workflowRecipeSetEditorErrorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .textSelection(.enabled)
            }
            if viewModel.workflowRecipePlanMessage.isEmpty == false {
                Text(viewModel.workflowRecipePlanMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.success)
                    .textSelection(.enabled)
            }
            if viewModel.workflowRecipePlanErrorMessage.isEmpty == false {
                Text(viewModel.workflowRecipePlanErrorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .textSelection(.enabled)
            }
            if viewModel.workflowRecipeApplyMessage.isEmpty == false {
                Text(viewModel.workflowRecipeApplyMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.success)
                    .textSelection(.enabled)
            }
            if viewModel.workflowRecipeApplyErrorMessage.isEmpty == false {
                Text(viewModel.workflowRecipeApplyErrorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .textSelection(.enabled)
            }

            MelixSectionCard("URI Inspect") {
                uriInspectionPanel
            }

            MelixSectionCard("Recipe Init Preview") {
                recipeInitPreviewPanel
            }

            MelixSectionCard("Recipe Variables") {
                recipeVariablesPanel
            }

            MelixSectionCard("Planned Pipeline") {
                recipePlanPanel
            }

            MelixSectionCard("Recipe Apply") {
                recipeApplyPanel
            }

            HStack(alignment: .top, spacing: 14) {
                MelixSectionCard("Recipe Catalog") {
                    recipeCatalogList
                }
                .frame(minWidth: 280, maxWidth: 360, alignment: .topLeading)

                MelixSectionCard("Recipe Detail") {
                    recipeDetail
                }
                .frame(maxWidth: .infinity, alignment: .topLeading)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(accessibilitySummary)
    }

    private var recipeCatalogList: some View {
        VStack(alignment: .leading, spacing: 10) {
            if viewModel.workflowRecipeFilteredRecipes.isEmpty {
                Text("No workflow recipes match this filter.")
                    .foregroundStyle(.secondary)
            } else {
                ForEach(viewModel.workflowRecipeFilteredRecipes) { recipe in
                    Button {
                        selectRecipeAction(recipe.id)
                    } label: {
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(alignment: .firstTextBaseline) {
                                Text(recipe.title)
                                    .font(.headline)
                                    .lineLimit(2)
                                Spacer(minLength: 8)
                                Text("v\(recipe.version)")
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                            Text(recipe.id)
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                                .truncationMode(.middle)
                            if recipe.taskText.isEmpty == false {
                                Text(recipe.taskText)
                                    .font(.caption2)
                                    .foregroundStyle(.tertiary)
                                    .lineLimit(1)
                            }
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(
                            viewModel.selectedWorkflowRecipeID == recipe.id
                                ? MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.selected)
                                : Color.secondary.opacity(0.05),
                            in: RoundedRectangle(cornerRadius: 8)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    func refreshCatalogAction() {
        Task { await viewModel.refreshWorkflowRecipeCatalog() }
    }

    func applyTaskFilter(_ task: String) {
        viewModel.updateWorkflowRecipeTaskFilter(task)
    }

    func clearTaskFilter() {
        viewModel.updateWorkflowRecipeTaskFilter("")
    }

    func selectRecipeAction(_ recipeID: String) {
        Task { await viewModel.selectWorkflowRecipe(recipeID: recipeID) }
    }

    func inspectURIAction() {
        Task { await viewModel.inspectWorkflowRecipeURI() }
    }

    func previewRecipeInitAction() {
        Task { await viewModel.previewWorkflowRecipeInitFromInspectedURI() }
    }

    func addRecipeVariableAction() {
        viewModel.addWorkflowRecipeSetDraft()
    }

    func applyRecipeVariableDraft(key: String, value: String) {
        viewModel.updateWorkflowRecipeSetKeyDraft(key)
        viewModel.updateWorkflowRecipeSetValueDraft(value)
        viewModel.addWorkflowRecipeSetDraft()
    }

    func removeRecipeVariableAction(_ key: String) {
        viewModel.removeWorkflowRecipeSetValue(key: key)
    }

    func clearRecipeVariablesAction() {
        viewModel.clearWorkflowRecipeSetValues()
    }

    func planRecipeAction() {
        Task { await viewModel.planWorkflowRecipe() }
    }

    func applyRecipeAction() {
        Task { await viewModel.applyWorkflowRecipe() }
    }

    private var uriInspectionPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .bottom, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Recipe init task")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField(
                        "Recipe init task",
                        text: Binding(
                            get: { viewModel.workflowRecipeInitTaskDraft },
                            set: { viewModel.updateWorkflowRecipeInitTaskDraft($0) }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                }
                Button("Preview Recipe Init", action: previewRecipeInitAction)
                    .buttonStyle(.bordered)
                    .disabled(viewModel.workflowRecipeInitPreviewCanRun == false)
            }

            if let inspection = viewModel.workflowRecipeURIInspection {
                HStack(alignment: .firstTextBaseline) {
                    Text(inspection.summaryText)
                        .font(.headline)
                    Spacer()
                    if inspection.schemaVersion.isEmpty == false {
                        Text(inspection.schemaVersion)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                }
                if inspection.normalizedLocator.isEmpty == false {
                    Text(inspection.normalizedLocator)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                if inspection.candidates.isEmpty {
                    Text("No URI candidates found.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(inspection.candidates) { candidate in
                        workflowRecipeURICandidateRow(candidate)
                    }
                }
            } else {
                Text("Inspect a URI to see candidate workflow inputs.")
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func workflowRecipeURICandidateRow(_ candidate: RuntimeWorkflowURICandidateState) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(candidate.kind)
                    .font(.caption.weight(.semibold))
                Text(candidate.confidenceText)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                Spacer()
                Text(candidate.taskKind)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
            Text([candidate.sourceKind, candidate.repoID, candidate.revision]
                .filter { $0.isEmpty == false }
                .joined(separator: " | "))
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(candidate.normalizedLocator)
                .font(.caption.monospaced())
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.middle)
                .textSelection(.enabled)
            if candidate.reasonText.isEmpty == false {
                Text(candidate.reasonText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if candidate.generatedCommandText.isEmpty == false {
                Text(candidate.generatedCommandText)
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
            }
            if candidate.warningText.isEmpty == false {
                Text(candidate.warningText)
                    .font(.caption2)
                    .foregroundStyle(MelixDesignTokens.StatusColor.warning)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
    }

    private var recipeInitPreviewPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let preview = viewModel.workflowRecipeInitPreview {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(preview.recipe.title)
                            .font(.headline)
                        Spacer()
                        Text("v\(preview.recipe.version)")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    Text(preview.recipe.id)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                    if preview.recipe.description.isEmpty == false {
                        Text(preview.recipe.description)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if let inspectionSummary = preview.inspection?.summaryText,
                       inspectionSummary.isEmpty == false
                    {
                        Text(inspectionSummary)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }

                workflowRecipeKeyValueRows("Provenance", rows: preview.provenanceRows)
                workflowRecipeInputRows(preview.recipe.inputRows)
                workflowRecipeKeyValueRows("Preflight", rows: preview.recipe.preflightRows)
                workflowRecipePipelineRows(preview.recipe.pipelineSteps)
                workflowRecipeKeyValueRows("Outputs", rows: preview.recipe.outputRows)
            } else {
                Text("Preview recipe init from an inspected URI before applying a workflow.")
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var recipeVariablesPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .bottom, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Variable key")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField(
                        "Variable key",
                        text: Binding(
                            get: { viewModel.workflowRecipeSetKeyDraft },
                            set: { viewModel.updateWorkflowRecipeSetKeyDraft($0) }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                }
                VStack(alignment: .leading, spacing: 4) {
                    Text("Variable value")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField(
                        "Variable value",
                        text: Binding(
                            get: { viewModel.workflowRecipeSetValueDraft },
                            set: { viewModel.updateWorkflowRecipeSetValueDraft($0) }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                }
                Button("Add --set", action: addRecipeVariableAction)
                    .buttonStyle(.bordered)
                    .disabled(viewModel.workflowRecipeSetEditorCanAdd == false)
                Button("Clear Variables", action: clearRecipeVariablesAction)
                    .buttonStyle(.bordered)
                    .disabled(viewModel.workflowRecipeSetRows.isEmpty)
            }

            if viewModel.workflowRecipeSetRows.isEmpty {
                Text("No recipe variables configured.")
                    .foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(viewModel.workflowRecipeSetRows) { row in
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(row.key)
                                    .font(.caption.weight(.semibold))
                                Text(row.argumentText)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                            Spacer()
                            Text(row.value)
                                .font(.caption)
                                .lineLimit(1)
                                .truncationMode(.middle)
                            Button("Remove") {
                                removeRecipeVariableAction(row.key)
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var recipePlanPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .bottom, spacing: 10) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Plan output path")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField(
                        "Plan output path",
                        text: Binding(
                            get: { viewModel.workflowRecipePlanOutputPathDraft },
                            set: { viewModel.updateWorkflowRecipePlanOutputPathDraft($0) }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                }
                Button("Plan Recipe", action: planRecipeAction)
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.workflowRecipePlanCanRun == false)
            }

            if let plan = viewModel.workflowRecipePlan {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(plan.summaryText)
                            .font(.headline)
                        Spacer()
                        if plan.schemaVersion.isEmpty == false {
                            Text(plan.schemaVersion)
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                        }
                    }
                    Text(plan.recipeDigest)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                    if plan.pipelineSchemaVersion.isEmpty == false {
                        Text(plan.pipelineSchemaVersion)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }

                if plan.pipelineJSONText.isEmpty == false {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Pipeline JSON")
                            .font(.caption.weight(.semibold))
                        Text(plan.pipelineJSONText)
                            .font(.caption.monospaced())
                            .lineLimit(10)
                            .textSelection(.enabled)
                    }
                }

                workflowRecipePipelineRows(plan.pipelineSteps)
                workflowRecipeArtifactRows(plan.artifactRows)
                workflowRecipeMetricRows("Planning Metrics", rows: plan.metrics)
            } else {
                Text("Plan a selected recipe to inspect pipeline JSON and dry-run receipts.")
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var recipeApplyPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .bottom, spacing: 12) {
                Toggle(
                    "Dry Run",
                    isOn: Binding(
                        get: { viewModel.workflowRecipeApplyDryRun },
                        set: { viewModel.updateWorkflowRecipeApplyDryRun($0) }
                    )
                )
                .toggleStyle(.checkbox)

                Toggle(
                    "Resume",
                    isOn: Binding(
                        get: { viewModel.workflowRecipeApplyResume },
                        set: { viewModel.updateWorkflowRecipeApplyResume($0) }
                    )
                )
                .toggleStyle(.checkbox)

                VStack(alignment: .leading, spacing: 4) {
                    Text("From step")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextField(
                        "From step",
                        text: Binding(
                            get: { viewModel.workflowRecipeApplyFromStepDraft },
                            set: { viewModel.updateWorkflowRecipeApplyFromStepDraft($0) }
                        )
                    )
                    .textFieldStyle(.roundedBorder)
                    .frame(minWidth: 180)
                }

                Button("Apply Recipe", action: applyRecipeAction)
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.workflowRecipeApplyCanRun == false)
            }

            if let result = viewModel.workflowRecipeApplyResult {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline) {
                        Text("Recipe Apply Result")
                            .font(.headline)
                        Spacer()
                        if result.schemaVersion.isEmpty == false {
                            Text(result.schemaVersion)
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                        }
                    }
                    Text(result.summaryText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if result.traceID.isEmpty == false {
                        Text(result.traceID)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                }

                workflowRecipePathRows([
                    ("Receipt Directory", result.receiptDir),
                    ("Summary Path", result.summaryPath),
                    ("Pipeline Hash", result.pipelineHash),
                    ("Inputs Hash", result.inputsHash),
                ])
                workflowRecipeKeyValueRows("Recipe", rows: result.recipeRows)
                workflowRecipeApplyStepRows(result.stepRows)
                workflowRecipeMetricRows("Apply Metrics", rows: result.metrics)
            } else {
                Text("Apply a selected recipe through the existing pipeline runner.")
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var recipeDetail: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let detail = viewModel.selectedWorkflowRecipeDetail {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(detail.title)
                            .font(.headline)
                        Spacer()
                        Text("v\(detail.version)")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    Text(detail.id)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                    if detail.description.isEmpty == false {
                        Text(detail.description)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if detail.taskText.isEmpty == false {
                        Text(detail.taskText)
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }

                workflowRecipeInputRows(detail.inputRows)
                workflowRecipeKeyValueRows("Preflight", rows: detail.preflightRows)
                workflowRecipePipelineRows(detail.pipelineSteps)
                workflowRecipeKeyValueRows("Outputs", rows: detail.outputRows)
            } else {
                Text("Select a recipe to inspect its inputs, preflight, pipeline, and outputs.")
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func workflowRecipeInputRows(_ rows: [RuntimeWorkflowRecipeInputRowState]) -> some View {
        Group {
            if rows.isEmpty == false {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Inputs")
                        .font(.caption.weight(.semibold))
                    ForEach(rows) { row in
                        HStack(alignment: .firstTextBaseline) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(row.name)
                                    .font(.caption.weight(.semibold))
                                Text([row.valueType, row.requirementText, row.uriKind]
                                    .filter { $0.isEmpty == false }
                                    .joined(separator: " | "))
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            if row.defaultValueText.isEmpty == false {
                                Text(row.defaultValueText)
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
    }

    private func workflowRecipeKeyValueRows(
        _ title: String,
        rows: [RuntimeWorkflowRecipeKeyValueRowState]
    ) -> some View {
        Group {
            if rows.isEmpty == false {
                VStack(alignment: .leading, spacing: 6) {
                    Text(title)
                        .font(.caption.weight(.semibold))
                    ForEach(rows) { row in
                        HStack(alignment: .firstTextBaseline) {
                            Text(row.name)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(row.valueText)
                                .font(.caption)
                                .textSelection(.enabled)
                        }
                    }
                }
            }
        }
    }

    private func workflowRecipePipelineRows(_ rows: [RuntimeWorkflowRecipePipelineStepState]) -> some View {
        Group {
            if rows.isEmpty == false {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Pipeline")
                        .font(.caption.weight(.semibold))
                    ForEach(rows) { step in
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(step.id) • \(step.command)")
                                .font(.caption.weight(.semibold))
                            if step.argumentSummaryText.isEmpty == false {
                                Text(step.argumentSummaryText)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                            }
                        }
                    }
                }
            }
        }
    }

    private func workflowRecipeArtifactRows(_ rows: [RuntimeWorkflowRecipeArtifactRowState]) -> some View {
        Group {
            if rows.isEmpty == false {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Dry-run Receipts")
                        .font(.caption.weight(.semibold))
                    ForEach(rows) { row in
                        HStack(alignment: .firstTextBaseline) {
                            Text(row.kind)
                                .font(.caption.weight(.semibold))
                            Spacer()
                            Text(row.path)
                                .font(.caption.monospaced())
                                .lineLimit(1)
                                .truncationMode(.middle)
                                .textSelection(.enabled)
                        }
                    }
                }
            }
        }
    }

    private func workflowRecipeMetricRows(_ title: String, rows: [RuntimeWorkflowRecipeMetricState]) -> some View {
        Group {
            if rows.isEmpty == false {
                VStack(alignment: .leading, spacing: 6) {
                    Text(title)
                        .font(.caption.weight(.semibold))
                    ForEach(rows) { row in
                        HStack(alignment: .firstTextBaseline) {
                            Text(row.name)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(row.valueText)
                                .font(.caption.monospacedDigit())
                        }
                    }
                }
            }
        }
    }

    private func workflowRecipePathRows(_ rows: [(String, String)]) -> some View {
        let visibleRows = rows.filter { $0.1.isEmpty == false }
        return Group {
            if visibleRows.isEmpty == false {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(visibleRows, id: \.0) { label, value in
                        HStack(alignment: .firstTextBaseline) {
                            Text(label)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(value)
                                .font(.caption.monospaced())
                                .lineLimit(1)
                                .truncationMode(.middle)
                                .textSelection(.enabled)
                        }
                    }
                }
            }
        }
    }

    private func workflowRecipeApplyStepRows(_ rows: [RuntimeWorkflowRecipeApplyStepRowState]) -> some View {
        Group {
            if rows.isEmpty == false {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Apply Steps")
                        .font(.caption.weight(.semibold))
                    ForEach(rows) { row in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack(alignment: .firstTextBaseline) {
                                Text("\(row.id) • \(row.command)")
                                    .font(.caption.weight(.semibold))
                                Spacer()
                                Text(row.status)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(.secondary)
                            }
                            if row.receiptPath.isEmpty == false {
                                Text(row.receiptPath)
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                    .textSelection(.enabled)
                            }
                            if row.artifactText.isEmpty == false {
                                Text(row.artifactText)
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                }
            }
        }
    }

    var accessibilitySummary: String {
        var values = [
            "Workflow Recipes",
            "Task filter",
            viewModel.workflowRecipeTaskFilterDraft,
            viewModel.workflowRecipeURIInspectDraft,
            viewModel.workflowRecipeInitTaskDraft,
            "Refresh Catalog",
            "URI to inspect",
            "Inspect URI",
            "Recipe init task",
            "Preview Recipe Init",
            "Recipe Init Preview",
            "Recipe Variables",
            "Variable key",
            "Variable value",
            "Add --set",
            "Clear Variables",
            "Planned Pipeline",
            "Plan output path",
            "Plan Recipe",
            "Recipe Apply",
            "Dry Run",
            "Resume",
            "From step",
            "Apply Recipe",
            viewModel.workflowRecipeCatalogMessage,
            viewModel.workflowRecipeCatalogErrorMessage,
            viewModel.workflowRecipeURIInspectMessage,
            viewModel.workflowRecipeURIInspectErrorMessage,
            viewModel.workflowRecipeInitPreviewMessage,
            viewModel.workflowRecipeInitPreviewErrorMessage,
            viewModel.workflowRecipeSetKeyDraft,
            viewModel.workflowRecipeSetValueDraft,
            viewModel.workflowRecipeSetArgumentSummaryText,
            viewModel.workflowRecipeSetEditorMessage,
            viewModel.workflowRecipeSetEditorErrorMessage,
            viewModel.workflowRecipePlanOutputPathDraft,
            viewModel.workflowRecipePlanMessage,
            viewModel.workflowRecipePlanErrorMessage,
            viewModel.workflowRecipeApplyDryRun ? "Dry Run enabled" : "Dry Run disabled",
            viewModel.workflowRecipeApplyResume ? "Resume enabled" : "Resume disabled",
            viewModel.workflowRecipeApplyFromStepDraft,
            viewModel.workflowRecipeApplyMessage,
            viewModel.workflowRecipeApplyErrorMessage,
        ]
        values.append(contentsOf: viewModel.workflowRecipeCatalog.availableTaskFilters)
        if let inspection = viewModel.workflowRecipeURIInspection {
            values.append(contentsOf: [
                inspection.schemaVersion,
                inspection.originalURI,
                inspection.normalizedLocator,
                inspection.summaryText,
            ])
            if inspection.candidates.isEmpty {
                values.append("No URI candidates found.")
            }
            values.append(contentsOf: inspection.candidates.flatMap {
                [
                    $0.kind,
                    $0.sourceKind,
                    $0.taskKind,
                    $0.confidenceText,
                    $0.normalizedLocator,
                    $0.repoID,
                    $0.revision,
                    $0.reasonText,
                    $0.warningText,
                    $0.recommendedNextAction,
                    $0.generatedCommandText,
                ]
            })
            values.append(contentsOf: inspection.metrics.flatMap { [$0.name, $0.valueText] })
        } else {
            values.append("Inspect a URI to see candidate workflow inputs.")
        }
        if let preview = viewModel.workflowRecipeInitPreview {
            values.append(contentsOf: [
                preview.recipe.id,
                preview.recipe.version,
                preview.recipe.title,
                preview.recipe.description,
                preview.recipe.taskText,
                preview.recipe.digest,
                preview.source,
                preview.sourceURIDigest,
                preview.inspection?.summaryText ?? "",
            ])
            values.append(contentsOf: preview.provenanceRows.flatMap { [$0.name, $0.valueText] })
            values.append(contentsOf: preview.recipe.inputRows.flatMap {
                [$0.name, $0.valueType, $0.requirementText, $0.defaultValueText, $0.uriKind]
            })
            values.append(contentsOf: preview.recipe.preflightRows.flatMap { [$0.name, $0.valueText] })
            values.append(contentsOf: preview.recipe.pipelineSteps.flatMap { [$0.id, $0.command, $0.argumentSummaryText] })
            values.append(contentsOf: preview.recipe.outputRows.flatMap { [$0.name, $0.valueText] })
        } else {
            values.append("Preview recipe init from an inspected URI before applying a workflow.")
        }
        if viewModel.workflowRecipeSetRows.isEmpty {
            values.append("No recipe variables configured.")
        }
        values.append(contentsOf: viewModel.workflowRecipeSetRows.flatMap { [$0.key, $0.value, $0.argumentText] })
        if let plan = viewModel.workflowRecipePlan {
            values.append(contentsOf: [
                plan.schemaVersion,
                plan.recipeID,
                plan.recipeVersion,
                plan.recipeDigest,
                plan.pipelineSchemaVersion,
                plan.summaryText,
                "Pipeline JSON",
                plan.pipelineJSONText,
                "Dry-run Receipts",
            ])
            values.append(contentsOf: plan.pipelineSteps.flatMap { [$0.id, $0.command, $0.argumentSummaryText] })
            values.append(contentsOf: plan.artifactRows.flatMap { [$0.kind, $0.path] })
            values.append(contentsOf: plan.metrics.flatMap { [$0.name, $0.valueText] })
        } else {
            values.append("Plan a selected recipe to inspect pipeline JSON and dry-run receipts.")
        }
        if let result = viewModel.workflowRecipeApplyResult {
            values.append(contentsOf: [
                "Recipe Apply Result",
                result.schemaVersion,
                result.name,
                result.traceID,
                result.status,
                result.receiptDir,
                result.summaryPath,
                result.pipelineHash,
                result.inputsHash,
                result.summaryText,
                "Receipt Directory",
                "Summary Path",
            ])
            values.append(contentsOf: result.recipeRows.flatMap { [$0.name, $0.valueText] })
            values.append(contentsOf: result.stepRows.flatMap {
                [$0.id, $0.command, $0.status, $0.receiptPath, $0.artifactText, $0.commandID, $0.argsHash]
            })
            values.append(contentsOf: result.metrics.flatMap { [$0.name, $0.valueText] })
        } else {
            values.append("Apply a selected recipe through the existing pipeline runner.")
        }
        if viewModel.workflowRecipeFilteredRecipes.isEmpty {
            values.append("No workflow recipes match this filter.")
        }
        values.append(contentsOf: viewModel.workflowRecipeFilteredRecipes.flatMap {
            [$0.id, $0.version, $0.title, $0.taskText, $0.digest]
        })
        if let detail = viewModel.selectedWorkflowRecipeDetail {
            values.append(contentsOf: [
                detail.id,
                detail.version,
                detail.title,
                detail.description,
                detail.taskText,
                detail.digest,
            ])
            values.append(contentsOf: detail.inputRows.flatMap {
                [$0.name, $0.valueType, $0.requirementText, $0.defaultValueText, $0.uriKind]
            })
            values.append(contentsOf: detail.preflightRows.flatMap { [$0.name, $0.valueText] })
            values.append(contentsOf: detail.pipelineSteps.flatMap { [$0.id, $0.command, $0.argumentSummaryText] })
            values.append(contentsOf: detail.outputRows.flatMap { [$0.name, $0.valueText] })
        } else {
            values.append("Select a recipe to inspect its inputs, preflight, pipeline, and outputs.")
        }
        return values.filter { $0.isEmpty == false }.joined(separator: " ")
    }
}

struct DesktopSyntheticDatasetToolSectionView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Synthetic Dataset Studio")
                .font(.title3.weight(.semibold))

            if viewModel.syntheticDatasetPreviewMessage.isEmpty == false {
                Text(viewModel.syntheticDatasetPreviewMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.success)
                    .textSelection(.enabled)
            }
            if viewModel.syntheticDatasetPreviewErrorMessage.isEmpty == false {
                Text(viewModel.syntheticDatasetPreviewErrorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .textSelection(.enabled)
            }
            if viewModel.syntheticDatasetCreateMessage.isEmpty == false {
                Text(viewModel.syntheticDatasetCreateMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.success)
                    .textSelection(.enabled)
            }
            if viewModel.syntheticDatasetCreateErrorMessage.isEmpty == false {
                Text(viewModel.syntheticDatasetCreateErrorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .textSelection(.enabled)
            }

            HStack(alignment: .top, spacing: 14) {
                MelixSectionCard("Dataset Identity") {
                    VStack(alignment: .leading, spacing: 10) {
                        formField(
                            "Dataset ID",
                            text: Binding(
                                get: { viewModel.syntheticDatasetIDDraft },
                                set: { viewModel.updateSyntheticDatasetIDDraft($0) }
                            )
                        )
                        formField(
                            "Dataset Name",
                            text: Binding(
                                get: { viewModel.syntheticDatasetNameDraft },
                                set: { viewModel.updateSyntheticDatasetNameDraft($0) }
                            )
                        )
                        formField(
                            "Records",
                            text: Binding(
                                get: { viewModel.syntheticDatasetNumRecordsDraft },
                                set: { viewModel.updateSyntheticDatasetNumRecordsDraft($0) }
                            )
                        )
                    }
                }

                MelixSectionCard("Output") {
                    VStack(alignment: .leading, spacing: 10) {
                        formField(
                            "Output Kind",
                            text: Binding(
                                get: { viewModel.syntheticDatasetOutputKindDraft },
                                set: { viewModel.updateSyntheticDatasetOutputKindDraft($0) }
                            )
                        )
                        formField(
                            "Output Format",
                            text: Binding(
                                get: { viewModel.syntheticDatasetOutputFormatDraft },
                                set: { viewModel.updateSyntheticDatasetOutputFormatDraft($0) }
                            )
                        )
                        formField(
                            "Output Directory",
                            text: Binding(
                                get: { viewModel.syntheticDatasetOutputDirDraft },
                                set: { viewModel.updateSyntheticDatasetOutputDirDraft($0) }
                            )
                        )
                    }
                }
            }

            HStack(alignment: .top, spacing: 14) {
                MelixSectionCard("Provider") {
                    VStack(alignment: .leading, spacing: 10) {
                        formField(
                            "Provider Endpoint",
                            text: Binding(
                                get: { viewModel.syntheticDatasetProviderEndpointDraft },
                                set: { viewModel.updateSyntheticDatasetProviderEndpointDraft($0) }
                            )
                        )
                        formField(
                            "Provider Name",
                            text: Binding(
                                get: { viewModel.syntheticDatasetProviderNameDraft },
                                set: { viewModel.updateSyntheticDatasetProviderNameDraft($0) }
                            )
                        )
                        formField(
                            "Provider Type",
                            text: Binding(
                                get: { viewModel.syntheticDatasetProviderTypeDraft },
                                set: { viewModel.updateSyntheticDatasetProviderTypeDraft($0) }
                            )
                        )
                    }
                }

                MelixSectionCard("Model") {
                    VStack(alignment: .leading, spacing: 10) {
                        formField(
                            "Model Alias",
                            text: Binding(
                                get: { viewModel.syntheticDatasetModelAliasDraft },
                                set: { viewModel.updateSyntheticDatasetModelAliasDraft($0) }
                            )
                        )
                        formField(
                            "Model",
                            text: Binding(
                                get: { viewModel.syntheticDatasetModelDraft },
                                set: { viewModel.updateSyntheticDatasetModelDraft($0) }
                            )
                        )
                    }
                }
            }

            MelixSectionCard("Columns") {
                columnEditorPanel
            }

            MelixSectionCard("Generation Controls") {
                generationControlsPanel
            }

            if viewModel.syntheticDatasetErrorStates.isEmpty == false {
                MelixSectionCard("Error States") {
                    errorStatesPanel
                }
            }

            MelixSectionCard("Preview") {
                previewPanel
            }

            MelixSectionCard("Create Package") {
                createPanel
            }

            MelixSectionCard("Validation") {
                if viewModel.syntheticDatasetBaseFormValidationMessages.isEmpty {
                    Text("Ready to configure columns before preview or create.")
                        .font(.caption)
                        .foregroundStyle(MelixDesignTokens.StatusColor.success)
                } else {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(viewModel.syntheticDatasetBaseFormValidationMessages) { message in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(message.field)
                                    .font(.caption.weight(.semibold))
                                Text(message.message)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    func addColumnAction() {
        viewModel.addSyntheticDatasetColumnDraft()
    }

    func removeColumn(id: String) {
        viewModel.removeSyntheticDatasetColumn(id: id)
    }

    func previewDatasetAction() {
        Task { await viewModel.previewSyntheticDataset() }
    }

    func createDatasetAction() {
        Task { await viewModel.createSyntheticDataset() }
    }

    private var columnEditorPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .bottom, spacing: 10) {
                formField(
                    "Column Name",
                    text: Binding(
                        get: { viewModel.syntheticDatasetColumnNameDraft },
                        set: { viewModel.updateSyntheticDatasetColumnNameDraft($0) }
                    )
                )
                formField(
                    "Column Type",
                    text: Binding(
                        get: { viewModel.syntheticDatasetColumnTypeDraft },
                        set: { viewModel.updateSyntheticDatasetColumnTypeDraft($0) }
                    )
                )
                formField(
                    "JSON or Path",
                    text: Binding(
                        get: { viewModel.syntheticDatasetColumnPayloadDraft },
                        set: { viewModel.updateSyntheticDatasetColumnPayloadDraft($0) }
                    )
                )
                Button("Add Column", action: addColumnAction)
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.syntheticDatasetColumnDraftCanAdd == false)
            }

            if viewModel.syntheticDatasetColumnEditorErrorMessage.isEmpty == false {
                Text(viewModel.syntheticDatasetColumnEditorErrorMessage)
                    .font(.caption)
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                    .textSelection(.enabled)
            }

            if viewModel.syntheticDatasetColumnDraftValidationMessages.isEmpty == false {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(viewModel.syntheticDatasetColumnDraftValidationMessages) { message in
                        Text("\(message.field): \(message.message)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            if viewModel.syntheticDatasetColumns.isEmpty {
                Text("No synthetic columns configured.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(viewModel.syntheticDatasetColumns) { column in
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Text(column.commandArgument)
                                .font(.caption.monospaced())
                                .lineLimit(1)
                                .truncationMode(.middle)
                                .textSelection(.enabled)
                            Spacer()
                            Button("Remove Column") {
                                removeColumn(id: column.id)
                            }
                            .buttonStyle(.bordered)
                        }
                    }
                }
            }
        }
    }

    private var generationControlsPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 10) {
                formField(
                    "Seed Source Kind",
                    text: Binding(
                        get: { viewModel.syntheticDatasetSeedSourceKindDraft },
                        set: { viewModel.updateSyntheticDatasetSeedSourceKindDraft($0) }
                    )
                )
                formField(
                    "Seed Source Path",
                    text: Binding(
                        get: { viewModel.syntheticDatasetSeedSourcePathDraft },
                        set: { viewModel.updateSyntheticDatasetSeedSourcePathDraft($0) }
                    )
                )
            }

            HStack(alignment: .top, spacing: 10) {
                formField(
                    "Validation Ratio",
                    text: Binding(
                        get: { viewModel.syntheticDatasetValidationRatioDraft },
                        set: { viewModel.updateSyntheticDatasetValidationRatioDraft($0) }
                    )
                )
                formField(
                    "Resume",
                    text: Binding(
                        get: { viewModel.syntheticDatasetResumeModeDraft },
                        set: { viewModel.updateSyntheticDatasetResumeModeDraft($0) }
                    )
                )
                Toggle(
                    "DataDesigner Telemetry",
                    isOn: Binding(
                        get: { viewModel.syntheticDatasetDataDesignerTelemetryEnabled },
                        set: { viewModel.updateSyntheticDatasetDataDesignerTelemetryEnabled($0) }
                    )
                )
                .toggleStyle(.checkbox)
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            if viewModel.syntheticDatasetGenerationControlValidationMessages.isEmpty == false {
                VStack(alignment: .leading, spacing: 4) {
                    ForEach(viewModel.syntheticDatasetGenerationControlValidationMessages) { message in
                        Text("\(message.field): \(message.message)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            Text(viewModel.syntheticDatasetGenerationControlCommandArguments.joined(separator: " "))
                .font(.caption.monospaced())
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .textSelection(.enabled)
        }
    }

    private var errorStatesPanel: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(viewModel.syntheticDatasetErrorStates) { state in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(state.title)
                            .font(.caption.weight(.semibold))
                        Text(state.source)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                    Text(state.detail)
                        .font(.caption)
                        .foregroundStyle(MelixDesignTokens.StatusColor.error)
                        .textSelection(.enabled)
                    Text(state.recoveryHint)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var previewPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Button("Preview Dataset", action: previewDatasetAction)
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.syntheticDatasetCanPreview == false)
                if viewModel.syntheticDatasetPreviewInProgress {
                    ProgressView()
                        .controlSize(.small)
                }
            }

            if let preview = viewModel.syntheticDatasetPreview {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(preview.summaryText)
                            .font(.headline)
                        Spacer()
                        if preview.schemaVersion.isEmpty == false {
                            Text(preview.schemaVersion)
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                        }
                    }
                    Text([preview.outputKind, preview.outputFormat]
                        .filter { $0.isEmpty == false }
                        .joined(separator: " | "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if preview.artifactRows.isEmpty == false {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Artifacts")
                            .font(.caption.weight(.semibold))
                        ForEach(preview.artifactRows) { row in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(row.name)
                                    .font(.caption.weight(.semibold))
                                Text(row.path)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                }

                if preview.previewRows.isEmpty {
                    Text("Preview returned no rows.")
                        .foregroundStyle(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Preview Rows")
                            .font(.caption.weight(.semibold))
                        ForEach(preview.previewRows) { row in
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Row \(row.index)")
                                    .font(.caption.weight(.semibold))
                                Text(row.summaryText)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(.secondary)
                                    .lineLimit(3)
                                    .textSelection(.enabled)
                            }
                            .padding(10)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
                        }
                    }
                }
            } else {
                Text("Run a preview to inspect generated rows before creating a package.")
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var createPanel: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline, spacing: 10) {
                Button("Create Dataset", action: createDatasetAction)
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.syntheticDatasetCanCreate == false)
                if viewModel.syntheticDatasetCreateInProgress {
                    ProgressView()
                        .controlSize(.small)
                }
            }

            if let result = viewModel.syntheticDatasetCreateResult {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(result.summaryText)
                            .font(.headline)
                        Spacer()
                        if result.schemaVersion.isEmpty == false {
                            Text(result.schemaVersion)
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                        }
                    }
                    Text([result.outputKind, result.outputFormat]
                        .filter { $0.isEmpty == false }
                        .joined(separator: " | "))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if result.manifestRows.isEmpty {
                    Text("Create result did not include manifest fields.")
                        .foregroundStyle(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Package Manifest")
                            .font(.caption.weight(.semibold))
                        ForEach(result.manifestRows) { row in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(row.name)
                                    .font(.caption.weight(.semibold))
                                Text(row.valueText)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                }

                if result.artifactRows.isEmpty {
                    Text("Create result did not include artifact paths.")
                        .foregroundStyle(.secondary)
                } else {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Artifacts")
                            .font(.caption.weight(.semibold))
                        ForEach(result.artifactRows) { row in
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(row.name)
                                    .font(.caption.weight(.semibold))
                                Text(row.path)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                }
            } else {
                Text("Create a package after previewing the request shape and validation state.")
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func formField(_ label: String, text: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
            TextField(label, text: text)
                .textFieldStyle(.roundedBorder)
        }
    }

    var accessibilitySummary: String {
        var values = [
            "Synthetic Dataset Studio",
            "Dataset Identity",
            "Dataset ID",
            viewModel.normalizedSyntheticDatasetID,
            "Dataset Name",
            viewModel.normalizedSyntheticDatasetName,
            "Records",
            viewModel.syntheticDatasetNumRecordsDraft,
            "Output",
            "Output Kind",
            viewModel.normalizedSyntheticDatasetOutputKind,
            "Output Format",
            viewModel.normalizedSyntheticDatasetOutputFormat,
            "Output Directory",
            viewModel.normalizedSyntheticDatasetOutputDir,
            "Provider",
            "Provider Endpoint",
            viewModel.normalizedSyntheticDatasetProviderEndpoint,
            "Provider Name",
            viewModel.normalizedSyntheticDatasetProviderName,
            "Provider Type",
            viewModel.normalizedSyntheticDatasetProviderType,
            "Model",
            "Model Alias",
            viewModel.normalizedSyntheticDatasetModelAlias,
            viewModel.normalizedSyntheticDatasetModel,
            "Columns",
            "Column Name",
            viewModel.normalizedSyntheticDatasetColumnName,
            "Column Type",
            viewModel.normalizedSyntheticDatasetColumnType,
            "JSON or Path",
            viewModel.normalizedSyntheticDatasetColumnPayload,
            "Add Column",
            "Generation Controls",
            "Seed Source Kind",
            viewModel.normalizedSyntheticDatasetSeedSourceKind,
            "Seed Source Path",
            viewModel.normalizedSyntheticDatasetSeedSourcePath,
            "Validation Ratio",
            viewModel.normalizedSyntheticDatasetValidationRatio,
            "Resume",
            viewModel.normalizedSyntheticDatasetResumeMode,
            "DataDesigner Telemetry",
            viewModel.syntheticDatasetDataDesignerTelemetryEnabled ? "enabled" : "disabled",
            "Preview",
            "Preview Dataset",
            viewModel.syntheticDatasetPreviewMessage,
            viewModel.syntheticDatasetPreviewErrorMessage,
            "Create Package",
            "Create Dataset",
            viewModel.syntheticDatasetCreateMessage,
            viewModel.syntheticDatasetCreateErrorMessage,
            "Validation",
        ]
        if viewModel.syntheticDatasetColumnEditorErrorMessage.isEmpty == false {
            values.append(viewModel.syntheticDatasetColumnEditorErrorMessage)
        }
        values.append(contentsOf: viewModel.syntheticDatasetColumnDraftValidationMessages.flatMap {
            [$0.field, $0.message]
        })
        if viewModel.syntheticDatasetColumns.isEmpty {
            values.append("No synthetic columns configured.")
        } else {
            values.append(contentsOf: viewModel.syntheticDatasetColumnCommandArguments)
            values.append("Remove Column")
        }
        values.append(contentsOf: viewModel.syntheticDatasetGenerationControlValidationMessages.flatMap {
            [$0.field, $0.message]
        })
        values.append(contentsOf: viewModel.syntheticDatasetGenerationControlCommandArguments)
        if viewModel.syntheticDatasetErrorStates.isEmpty == false {
            values.append("Error States")
            values.append(contentsOf: viewModel.syntheticDatasetErrorStates.flatMap {
                [$0.source, $0.title, $0.detail, $0.recoveryHint]
            })
        }
        if let preview = viewModel.syntheticDatasetPreview {
            values.append(contentsOf: [
                preview.schemaVersion,
                preview.datasetID,
                preview.datasetName,
                preview.outputKind,
                preview.outputFormat,
                String(preview.sampleCount),
                String(preview.previewCount),
            ])
            values.append(contentsOf: preview.artifactRows.flatMap { [$0.name, $0.path] })
            if preview.previewRows.isEmpty {
                values.append("Preview returned no rows.")
            } else {
                values.append(contentsOf: preview.previewRows.flatMap { row in
                    ["Row \(row.index)", row.summaryText]
                })
            }
        } else {
            values.append("Run a preview to inspect generated rows before creating a package.")
        }
        if let result = viewModel.syntheticDatasetCreateResult {
            values.append(contentsOf: [
                result.schemaVersion,
                result.datasetID,
                result.datasetName,
                result.outputKind,
                result.outputFormat,
                String(result.rowCount),
                String(result.sampleCount),
            ])
            if result.manifestRows.isEmpty {
                values.append("Create result did not include manifest fields.")
            } else {
                values.append("Package Manifest")
                values.append(contentsOf: result.manifestRows.flatMap { [$0.name, $0.valueText] })
            }
            if result.artifactRows.isEmpty {
                values.append("Create result did not include artifact paths.")
            } else {
                values.append(contentsOf: result.artifactRows.flatMap { [$0.name, $0.path] })
            }
        } else {
            values.append("Create a package after previewing the request shape and validation state.")
        }
        if viewModel.syntheticDatasetBaseFormValidationMessages.isEmpty {
            values.append("Ready to configure columns before preview or create.")
        } else {
            values.append(contentsOf: viewModel.syntheticDatasetBaseFormValidationMessages.flatMap {
                [$0.field, $0.message]
            })
        }
        return values
            .filter { $0.isEmpty == false }
            .joined(separator: " ")
    }
}

struct DesktopBatchRunsToolSectionView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Batch runs coordinate model-list driven benchmark and evaluation workflows with explicit preflight state.")
                .foregroundStyle(.secondary)

            MelixSectionCard("Batch Inputs") {
                VStack(alignment: .leading, spacing: 12) {
                    Text("Batch Inputs")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .accessibilityLabel("Batch Inputs")
                    Text(viewModel.batchRunSetupSummaryText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)

                    HStack(alignment: .top, spacing: 12) {
                        batchTextEditor(
                            title: "Model List",
                            text: Binding(
                                get: { viewModel.batchRunModelListText },
                                set: { viewModel.updateBatchRunModelListText($0) }
                            ),
                            prompt: "01 | mlx-community/Qwen3-8B"
                        )

                        batchTextEditor(
                            title: "Config",
                            text: Binding(
                                get: { viewModel.batchRunConfigText },
                                set: { viewModel.updateBatchRunConfigText($0) }
                            ),
                            prompt: "run_id: smoke-batch"
                        )
                    }

                    validationMessages
                    batchRunOperations
                    selectedReportSummary
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func batchTextEditor(title: String, text: Binding<String>, prompt: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .accessibilityLabel(title)
            TextEditor(text: text)
                .font(.system(.caption, design: .monospaced))
                .frame(minHeight: 96)
                .overlay(alignment: .topLeading) {
                    if text.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        Text(prompt)
                            .font(.caption.monospaced())
                            .foregroundStyle(.tertiary)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 8)
                            .allowsHitTesting(false)
                    }
                }
                .scrollContentBackground(.hidden)
                .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private var validationMessages: some View {
        if viewModel.batchRunSetupValidationMessages.isEmpty {
            Label("Batch input is ready for preflight.", systemImage: "checkmark.circle")
                .font(.caption)
                .foregroundStyle(MelixDesignTokens.StatusColor.success)
                .textSelection(.enabled)
        } else {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(viewModel.batchRunSetupValidationMessages) { message in
                    Label(message.message, systemImage: symbolName(for: message.severity))
                        .font(.caption)
                        .foregroundStyle(color(for: message.severity))
                        .textSelection(.enabled)
                }
            }
        }
    }

    private var batchRunOperations: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                DesktopJobsOperationButton(
                    title: "Run Preflight",
                    isEnabled: viewModel.batchRunPreflightCanRun
                ) {
                    Task { await viewModel.requestBatchRunPreflight() }
                }
                DesktopJobsOperationButton(
                    title: "Refresh Status",
                    isEnabled: viewModel.batchRunStatusCanRefresh
                ) {
                    Task { await viewModel.requestBatchRunStatus() }
                }
                DesktopBatchRunMissingOnlyToggle(isOn: viewModel.batchRunResumeMissingOnly) {
                    viewModel.updateBatchRunResumeMissingOnly($0)
                }
                DesktopJobsOperationButton(
                    title: "Resume Batch",
                    isEnabled: viewModel.batchRunResumeCanRun
                ) {
                    Task { await viewModel.requestBatchRunResume() }
                }

                batchRunOperationStatus
            }

            Text(viewModel.batchRunResumeSummaryText)
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
            if viewModel.batchRunResumeDisabledReason.isEmpty == false {
                Label(viewModel.batchRunResumeDisabledReason, systemImage: "info.circle")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
        }
    }

    @ViewBuilder
    private var batchRunOperationStatus: some View {
        if viewModel.batchRunPreflightInProgress {
            Text("Running batch preflight")
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        } else if viewModel.batchRunStatusInProgress {
            Text("Refreshing batch status")
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        } else if viewModel.batchRunResumeInProgress {
            Text("Resuming batch")
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        } else if viewModel.batchRunPreflightErrorMessage.isEmpty == false {
            Label(viewModel.batchRunPreflightErrorMessage, systemImage: "xmark.octagon")
                .font(.caption)
                .foregroundStyle(MelixDesignTokens.StatusColor.error)
                .textSelection(.enabled)
        } else if viewModel.batchRunStatusErrorMessage.isEmpty == false {
            Label(viewModel.batchRunStatusErrorMessage, systemImage: "xmark.octagon")
                .font(.caption)
                .foregroundStyle(MelixDesignTokens.StatusColor.error)
                .textSelection(.enabled)
        } else if viewModel.batchRunResumeErrorMessage.isEmpty == false {
            Label(viewModel.batchRunResumeErrorMessage, systemImage: "xmark.octagon")
                .font(.caption)
                .foregroundStyle(MelixDesignTokens.StatusColor.error)
                .textSelection(.enabled)
        }
    }

    @ViewBuilder
    private var selectedReportSummary: some View {
        if let report = viewModel.selectedBatchRunReport {
            VStack(alignment: .leading, spacing: 8) {
                Text("Selected Preflight Report")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                HStack(spacing: 10) {
                    Text(report.runID)
                        .font(.subheadline.weight(.semibold))
                        .textSelection(.enabled)
                    Text(report.statusTitle)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(report.preflightStatus == "ready"
                                         ? MelixDesignTokens.StatusColor.success
                                         : MelixDesignTokens.StatusColor.warning)
                        .textSelection(.enabled)
                    Text("\(report.modelCount) model\(report.modelCount == 1 ? "" : "s")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                    Text("\(report.blockerCount) blocker\(report.blockerCount == 1 ? "" : "s")")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                preflightReadinessSection(report)
                batchStatusSection(report)
                reportSummarySection(title: "Effective Config", rows: report.effectiveConfigRows)
                reportSummarySection(title: "Isolation Summary", rows: report.isolationSummaryRows)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func preflightReadinessSection(_ report: RuntimeBatchRunReportState) -> some View {
        let categories = report.preflightReadinessCategories
        if categories.isEmpty == false {
            VStack(alignment: .leading, spacing: 6) {
                Text("Preflight Readiness")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                ForEach(categories) { category in
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(category.category)
                                .font(.caption.weight(.semibold))
                                .textSelection(.enabled)
                            Text(category.readinessText)
                                .font(.caption)
                                .foregroundStyle(category.blockerCount == 0
                                                 ? MelixDesignTokens.StatusColor.success
                                                 : MelixDesignTokens.StatusColor.warning)
                                .textSelection(.enabled)
                        }
                        ForEach(category.checks) { check in
                            VStack(alignment: .leading, spacing: 2) {
                                HStack(spacing: 8) {
                                    Text(check.name)
                                        .font(.caption.weight(.semibold))
                                        .textSelection(.enabled)
                                    Text(check.status)
                                        .font(.caption)
                                        .foregroundStyle(check.isReady
                                                         ? MelixDesignTokens.StatusColor.success
                                                         : MelixDesignTokens.StatusColor.warning)
                                        .textSelection(.enabled)
                                    Text(check.detail)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .textSelection(.enabled)
                                }
                                if check.isBlocking && check.blockingReasonText.isEmpty == false {
                                    Text(check.blockingReasonText)
                                        .font(.caption)
                                        .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                                        .textSelection(.enabled)
                                }
                            }
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func batchStatusSection(_ report: RuntimeBatchRunReportState) -> some View {
        if let summary = report.statusSummary {
            VStack(alignment: .leading, spacing: 6) {
                Text("Batch Status")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                HStack(spacing: 8) {
                    Text(summary.statusTitle)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(summary.status == "failed"
                                         ? MelixDesignTokens.StatusColor.error
                                         : MelixDesignTokens.StatusColor.success)
                        .textSelection(.enabled)
                    Text(summary.countsText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
                Text(summary.manifestPath)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .textSelection(.enabled)
                ForEach(report.manifestStatusRows.prefix(6)) { row in
                    VStack(alignment: .leading, spacing: 3) {
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text(row.modelIndex)
                                .font(.caption.weight(.semibold))
                                .textSelection(.enabled)
                            Text(row.repoID)
                                .font(.caption)
                                .textSelection(.enabled)
                            Text(row.status)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(row.status == "failed"
                                                 ? MelixDesignTokens.StatusColor.error
                                                 : MelixDesignTokens.StatusColor.success)
                                .textSelection(.enabled)
                            if row.durationText.isEmpty == false {
                                Text(row.durationText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                        }
                        HStack(spacing: 8) {
                            if row.benchmarkJobID.isEmpty == false {
                                Text(row.benchmarkJobID)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                            if row.evaluationJobID.isEmpty == false {
                                Text(row.evaluationJobID)
                                    .font(.caption.monospaced())
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                            if row.failureCategory.isEmpty == false {
                                Text(row.failureCategory)
                                    .font(.caption)
                                    .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                                    .textSelection(.enabled)
                            }
                            if row.recoverability.isEmpty == false {
                                Text(row.recoverability)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func reportSummarySection(title: String, rows: [RuntimeBatchRunSummaryRowState]) -> some View {
        if rows.isEmpty == false {
            VStack(alignment: .leading, spacing: 6) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                ForEach(rows) { row in
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(row.title)
                            .font(.caption.weight(.semibold))
                            .textSelection(.enabled)
                        Text(row.detail)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                            .textSelection(.enabled)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func symbolName(for severity: RuntimeBatchRunValidationSeverity) -> String {
        switch severity {
        case .info:
            return "info.circle"
        case .warning:
            return "exclamationmark.triangle"
        case .error:
            return "xmark.octagon"
        }
    }

    private func color(for severity: RuntimeBatchRunValidationSeverity) -> Color {
        switch severity {
        case .info:
            return .secondary
        case .warning:
            return MelixDesignTokens.StatusColor.warning
        case .error:
            return MelixDesignTokens.StatusColor.error
        }
    }
}

struct DesktopJobsToolSectionView: View {
    let viewModel: RuntimeViewModel

    static let emptyStateTitle = "No Jobs Yet"
    static let emptyStateDetail = "Run a benchmark, evaluation, training, or synthetic workflow to populate Jobs."

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Operator workflow jobs stay visible across benchmark, evaluation, training, and synthetic runs.")
                .foregroundStyle(.secondary)

            if viewModel.runtimeJobs.isEmpty {
                MelixSectionCard("Jobs List") {
                    VStack(alignment: .leading, spacing: 10) {
                        jobsOperationBar
                        DesktopJobsInlineEmptyStateView(
                            title: Self.emptyStateTitle,
                            detail: Self.emptyStateDetail,
                            symbolName: "tray"
                        )
                    }
                }
            } else {
                HStack(alignment: .top, spacing: 14) {
                    jobsList
                        .frame(minWidth: 280, maxWidth: .infinity, alignment: .topLeading)
                    selectedJobSummary
                        .frame(minWidth: 260, maxWidth: .infinity, alignment: .topLeading)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var jobsOperationBar: some View {
        HStack(spacing: 8) {
            DesktopJobsOperationButton(
                title: "Refresh Jobs",
                isEnabled: viewModel.runtimeJobsRefreshInProgress == false
            ) {
                Task { await viewModel.refreshRuntimeJobs() }
            }

            DesktopJobsOperationButton(
                title: "Refresh Detail",
                isEnabled: viewModel.selectedRuntimeJobID.isEmpty == false
                    && viewModel.selectedRuntimeJobDetailRefreshInProgress == false
            ) {
                Task { await viewModel.refreshSelectedRuntimeJobDetail() }
            }

            DesktopJobsOperationButton(
                title: "Fetch Logs",
                isEnabled: viewModel.selectedRuntimeJobID.isEmpty == false
                    && viewModel.selectedRuntimeJobLogsRefreshInProgress == false
            ) {
                Task { await viewModel.refreshSelectedRuntimeJobLogs() }
            }

            DesktopJobsOperationButton(
                title: "Refresh Artifacts",
                isEnabled: viewModel.selectedRuntimeJobID.isEmpty == false
                    && viewModel.selectedRuntimeJobArtifactsRefreshInProgress == false
            ) {
                Task { await viewModel.refreshSelectedRuntimeJobArtifacts() }
            }

            DesktopJobsOperationButton(
                title: "Request Cancel",
                isEnabled: viewModel.selectedRuntimeJobCanRequestCancellation
            ) {
                Task { await viewModel.requestSelectedRuntimeJobCancellation() }
            }
        }
    }

    private var jobsList: some View {
        MelixSectionCard("Jobs List") {
            VStack(alignment: .leading, spacing: 8) {
                jobsOperationBar

                Text(queueSummaryText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)

                ForEach(viewModel.runtimeJobs) { job in
                    Button {
                        viewModel.selectRuntimeJob(id: job.id)
                    } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(alignment: .firstTextBaseline, spacing: 10) {
                                Text(job.jobID)
                                    .font(.subheadline.weight(.semibold))
                                    .lineLimit(1)
                                    .textSelection(.enabled)
                                Spacer(minLength: 12)
                                Text(job.status)
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(statusColor(for: job))
                                    .textSelection(.enabled)
                                    .padding(.horizontal, 8)
                                    .padding(.vertical, 4)
                                    .background(Color.secondary.opacity(0.08), in: Capsule())
                            }

                            Text(jobSubtitle(for: job))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                                .textSelection(.enabled)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .background(
                            viewModel.selectedRuntimeJobID == job.id
                                ? MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.selected)
                                : Color.secondary.opacity(0.06),
                            in: RoundedRectangle(cornerRadius: 10)
                        )
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Job \(job.jobID)")
                }
            }
        }
    }

    @ViewBuilder
    private var selectedJobSummary: some View {
        if let detail = viewModel.selectedRuntimeJobDetail {
            MelixSectionCard("Job Detail") {
                VStack(alignment: .leading, spacing: 12) {
                    selectedJobHeader(detail.summary)

                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), spacing: 10)], spacing: 10) {
                        DesktopJobSummaryField(title: "Run", value: detail.summary.runKind)
                        DesktopJobSummaryField(title: "Status", value: detail.summary.status)
                        DesktopJobSummaryField(title: "Phase", value: detail.summary.phase)
                        DesktopJobSummaryField(title: "Started", value: timestampText(detail.timestamps.startedAtUnixMS))
                        DesktopJobSummaryField(title: "Updated", value: timestampText(detail.timestamps.updatedAtUnixMS))
                        DesktopJobSummaryField(title: "Ended", value: timestampText(detail.timestamps.endedAtUnixMS))
                        DesktopJobSummaryField(title: "Duration", value: durationText(detail.timestamps.durationMS))
                        DesktopJobSummaryField(title: "Model", value: detail.summary.modelID)
                        DesktopJobSummaryField(title: "Task", value: detail.summary.taskKind)
                    }

                    if let error = detail.error {
                        DesktopJobDetailBlock(title: "Error", values: [error.code, error.message])
                    }

                    DesktopJobDetailBlock(
                        title: "Logs",
                        values: [
                            detail.logs.available ? "available" : "unavailable",
                            detail.logs.path,
                            detail.logs.command,
                        ]
                    )

                    cancelRequestBlock
                    fetchedLogBlock
                    fetchedArtifactsBlock

                    if detail.artifacts.isEmpty == false {
                        VStack(alignment: .leading, spacing: 8) {
                            ForEach(detail.artifacts) { artifact in
                                DesktopJobDetailBlock(
                                    title: "Artifact",
                                    values: [
                                        artifact.kind,
                                        artifact.path,
                                        artifact.relativePath,
                                        artifact.exists ? "exists" : "missing",
                                    ]
                                )
                            }
                        }
                    }
                }
            }
        } else if let job = viewModel.selectedRuntimeJob {
            MelixSectionCard("Selected Job") {
                VStack(alignment: .leading, spacing: 10) {
                    selectedJobHeader(job)

                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), spacing: 10)], spacing: 10) {
                        DesktopJobSummaryField(title: "Run", value: job.runKind)
                        DesktopJobSummaryField(title: "Status", value: job.status)
                        DesktopJobSummaryField(title: "Phase", value: job.phase)
                        DesktopJobSummaryField(title: "Model", value: job.modelID)
                        DesktopJobSummaryField(title: "Task", value: job.taskKind)
                        DesktopJobSummaryField(title: "Artifacts", value: job.artifactRoot)
                    }

                    cancelRequestBlock
                    fetchedLogBlock
                    fetchedArtifactsBlock
                }
            }
        }
    }

    @ViewBuilder
    private var cancelRequestBlock: some View {
        DesktopJobDetailBlock(
            title: "Cancel Request",
            values: [
                viewModel.selectedRuntimeJobCancellationStatusText,
                viewModel.selectedRuntimeJobCancelResult?.requestPath
                    ?? viewModel.selectedRuntimeJobDetail?.cancellation.requestPath
                    ?? "",
            ]
        )
    }

    @ViewBuilder
    private var fetchedLogBlock: some View {
        if let snapshot = viewModel.selectedRuntimeJobLogSnapshot {
            DesktopJobDetailBlock(
                title: "Fetched Logs",
                values: [
                    snapshot.logPath,
                    snapshot.content,
                    snapshot.redactedFieldCount == 0 ? "" : "redacted fields \(snapshot.redactedFieldCount)",
                ]
            )
        }
    }

    @ViewBuilder
    private var fetchedArtifactsBlock: some View {
        if let snapshot = viewModel.selectedRuntimeJobArtifactSnapshot, snapshot.artifacts.isEmpty == false {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(snapshot.artifacts) { artifact in
                    DesktopJobDetailBlock(
                        title: "Fetched Artifact",
                        values: [
                            artifact.kind,
                            artifact.path,
                            artifact.relativePath,
                            artifact.exists ? "exists" : "missing",
                        ]
                    )
                }
            }
        }
    }

    private func selectedJobHeader(_ job: RuntimeJobSummaryState) -> some View {
        Text(job.jobID)
            .font(.headline)
            .textSelection(.enabled)
    }

    private func jobSubtitle(for job: RuntimeJobSummaryState) -> String {
        [job.runKind, job.phase, job.modelID]
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { $0.isEmpty == false }
            .joined(separator: " • ")
    }

    private func statusColor(for job: RuntimeJobSummaryState) -> Color {
        if job.isTerminal {
            return MelixDesignTokens.StatusColor.success
        }
        if job.isActive {
            return MelixDesignTokens.StatusColor.warning
        }
        return .secondary
    }

    private func timestampText(_ unixMS: Int64) -> String {
        unixMS == 0 ? "N/A" : String(unixMS)
    }

    private func durationText(_ durationMS: Int64) -> String {
        durationMS == 0 ? "N/A" : "\(durationMS) ms"
    }

    private var queueSummaryText: String {
        "Queue IDs: \(viewModel.runtimeJobs.map(\.id).joined(separator: ", "))"
    }
}

private struct DesktopJobsInlineEmptyStateView: View {
    let title: String
    let detail: String
    let symbolName: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: symbolName)
                    .foregroundStyle(MelixDesignTokens.accent)
                Text(title)
                    .font(.headline)
                    .textSelection(.enabled)
            }
            Text(detail)
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
    }
}

private struct DesktopJobsOperationButton: NSViewRepresentable {
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
        button.bezelStyle = NSButton.BezelStyle.rounded
        button.controlSize = NSControl.ControlSize.small
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

private struct DesktopBatchRunMissingOnlyToggle: NSViewRepresentable {
    let isOn: Bool
    let action: (Bool) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(action: action)
    }

    func makeNSView(context: Context) -> NSButton {
        let button = NSButton(
            title: "Missing Only",
            target: context.coordinator,
            action: #selector(Coordinator.performAction(_:))
        )
        button.setButtonType(.switch)
        button.controlSize = .small
        button.setAccessibilityLabel("Missing Only")
        return button
    }

    func updateNSView(_ button: NSButton, context: Context) {
        context.coordinator.action = action
        button.title = "Missing Only"
        button.state = isOn ? .on : .off
        button.setAccessibilityLabel("Missing Only")
    }

    final class Coordinator: NSObject {
        var action: (Bool) -> Void

        init(action: @escaping (Bool) -> Void) {
            self.action = action
        }

        @MainActor
        @objc func performAction(_ sender: NSButton) {
            action(sender.state == .on)
        }
    }
}

private struct DesktopJobSummaryField: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(value.isEmpty ? "N/A" : value)
                .font(.caption)
                .textSelection(.enabled)
                .lineLimit(2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DesktopJobDetailBlock: View {
    let title: String
    let values: [String]

    private var visibleValues: [String] {
        values
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { $0.isEmpty == false }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            ForEach(visibleValues, id: \.self) { value in
                Text(value)
                    .font(.caption)
                    .textSelection(.enabled)
                    .lineLimit(3)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

enum DesktopDownloadsLayoutMetrics {
    static let compactAudioNoticeHeightBudget: CGFloat = 34
}

struct DesktopAudioSetupNoticeRow: View {
    let action: RuntimeAudioSetupActionState
    let performAction: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            Label("Audio Setup Required", systemImage: "waveform.badge.exclamationmark")
                .font(.caption.weight(.semibold))
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)

            Text(action.detail)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.tail)

            Spacer(minLength: 8)

            Button(action.actionTitle, action: performAction)
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .fixedSize(horizontal: true, vertical: false)
        }
        .padding(.horizontal, 10)
        .frame(height: DesktopDownloadsLayoutMetrics.compactAudioNoticeHeightBudget)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 12))
    }
}

struct DesktopTrainingToolSectionView: View {
    let viewModel: RuntimeViewModel
    @State private var showsAdvanced = DesktopTrainingWorkspaceDefaults.showsAdvancedParameters
    @State private var showsDatasetMapping = false

    init(
        viewModel: RuntimeViewModel,
        showsAdvanced: Bool = DesktopTrainingWorkspaceDefaults.showsAdvancedParameters,
        showsDatasetMapping: Bool = false
    ) {
        self.viewModel = viewModel
        _showsAdvanced = State(initialValue: showsAdvanced)
        _showsDatasetMapping = State(initialValue: showsDatasetMapping)
    }

    static func summaryItems(for viewModel: RuntimeViewModel) -> [DesktopTrainingSummaryItem] {
        [
            DesktopTrainingSummaryItem(
                title: "Base Model",
                value: viewModel.selectedLoraModelID,
                detail: viewModel.loraTrainingMode.title
            ),
            DesktopTrainingSummaryItem(
                title: "Dataset",
                value: datasetSummaryValue(for: viewModel),
                detail: datasetSummaryDetail(for: viewModel)
            ),
            DesktopTrainingSummaryItem(
                title: "Preset",
                value: viewModel.selectedLoraTrainingPreset.title,
                detail: experimentGroupSummary(for: viewModel)
            ),
            DesktopTrainingSummaryItem(
                title: "Activation",
                value: viewModel.loraActivationMode.title,
                detail: viewModel.loraTargetRepo.isEmpty ? "Target repo pending" : viewModel.loraTargetRepo
            ),
        ]
    }

    private static func datasetSummaryValue(for viewModel: RuntimeViewModel) -> String {
        switch viewModel.loraDatasetSourceKind {
        case .localPackage:
            return viewModel.loraDatasetURI.isEmpty ? "Dataset pending" : viewModel.loraDatasetURI
        case .huggingFaceDataset:
            return viewModel.loraHFDatasetPath.isEmpty ? "HF dataset pending" : viewModel.loraHFDatasetPath
        }
    }

    private static func datasetSummaryDetail(for viewModel: RuntimeViewModel) -> String {
        switch viewModel.loraDatasetSourceKind {
        case .localPackage:
            return "Local package dataset"
        case .huggingFaceDataset:
            let config = viewModel.loraHFDatasetName.isEmpty ? "default config" : viewModel.loraHFDatasetName
            return "Hugging Face dataset • \(config)"
        }
    }

    private static func experimentGroupSummary(for viewModel: RuntimeViewModel) -> String {
        viewModel.loraExperimentGroupID.isEmpty ? "Auto experiment grouping" : viewModel.loraExperimentGroupID
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Train adapters from a local package or a controlled Hugging Face dataset, then activate the saved adapter into a derived text model.")
                .foregroundStyle(.secondary)

            DesktopEditorialSectionCard("Primary Model") {
                primaryModelContent
            }

            DesktopEditorialSectionCard("Workflow Snapshot") {
                workflowSnapshotContent
            }

            DesktopEditorialSectionCard("Saved Jobs") {
                savedJobsContent
            }

            DesktopEditorialSectionCard("Run Draft") {
                trainingConfigurationContent
            }

            DesktopEditorialSectionCard("Adapter Registry") {
                adapterRegistryContent
            }

            DesktopEditorialSectionCard("Experiment Groups") {
                experimentGroupsContent
            }

            DesktopEditorialSectionCard("Training History") {
                trainingJobsContent
            }
        }
    }

    private var primaryModelContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            DesktopPassiveHeadlineButton(title: primaryModelTitle)

            Text(primaryModelDetailText)
                .font(.caption)
                .foregroundStyle(.secondary)

            workflowActionBar

            Text(workflowActionHelperText)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var workflowSnapshotContent: some View {
        VStack(alignment: .leading, spacing: 14) {
            workflowStatusContent

            Divider()

            selectedConfigurationContent
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var workflowActionBar: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Button("Train LoRA", action: startTrainLoRATask)
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.isLoraWorkflowActionInProgress)

                Button("Activate Adapter", action: startActivateAdapterTask)
                    .buttonStyle(.bordered)
                    .disabled(viewModel.selectedAdapterPackage == nil || viewModel.isLoraWorkflowActionInProgress)

                Menu {
                    Button("Publish Adapter", action: startPublishAdapterTask)
                        .disabled(viewModel.selectedAdapterPackage == nil || viewModel.isLoraWorkflowActionInProgress)

                    Button("Remove Derived Model", action: startRemoveDerivedModelTask)
                        .disabled(
                            (viewModel.selectedAdapterPackage?.derivedModelID.isEmpty ?? true)
                            || viewModel.isLoraWorkflowActionInProgress
                        )
                } label: {
                    Image(systemName: "ellipsis.circle")
                }
                .menuStyle(.borderlessButton)
                .menuIndicator(.hidden)
                .help("More LoRA Actions")
                .accessibilityLabel("More LoRA Actions")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var workflowActionHelperText: String {
        if viewModel.isLoraWorkflowActionInProgress {
            return "One LoRA action is currently running. Wait for it to finish before starting another workflow."
        }
        if let adapter = viewModel.selectedAdapterPackage {
            return adapter.derivedModelID.isEmpty
                ? "Activate the selected adapter when you want to expose it as a runtime target."
                : "The selected adapter already has a derived runtime target available."
        }
        return "Start training first, then activate or publish the resulting adapter package."
    }

    private var primaryModelTitle: String {
        viewModel.selectedLoraModelID.isEmpty ? "No Base Model Selected" : viewModel.selectedLoraModelID
    }

    private var primaryModelDetailText: String {
        let datasetMode = viewModel.loraDatasetSourceKind.title
        let trainingMode = viewModel.loraTrainingMode.title
        let activation = viewModel.loraActivationMode.title
        if let adapter = viewModel.selectedAdapterPackage {
            return "\(trainingMode) • \(datasetMode) • \(activation) • \(adapter.activationStatusText.lowercased())"
        }
        return "\(trainingMode) • \(datasetMode) • \(activation)"
    }

    private var selectedConfigurationContent: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: 14)], spacing: 14) {
            ForEach(Self.summaryItems(for: viewModel)) { item in
                DesktopTrainingSummaryValueView(item: item)
            }
        }
    }

    @ViewBuilder
    private var workflowStatusContent: some View {
        if let status = viewModel.loraWorkflowStatus {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: status.phase.symbolName)
                        .font(.system(size: 15, weight: .semibold))
                        .foregroundStyle(workflowStatusColor(for: status.phase))
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(alignment: .center, spacing: 8) {
                            Text(status.title)
                                .font(.headline)
                            if status.phase == .running {
                                ProgressView()
                                    .controlSize(.small)
                            }
                            Spacer(minLength: 12)
                            Text(status.phase.badgeTitle)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(Color.secondary.opacity(0.08), in: Capsule())
                        }
                        if !status.detail.isEmpty {
                            Text(status.detail)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
        } else {
            DesktopInlineEmptyStateView(
                title: idleWorkflowTitle,
                detail: idleWorkflowDetail,
                symbolName: idleWorkflowSymbolName
            )
        }
    }

    private var trainingConfigurationContent: some View {
        VStack(alignment: .leading, spacing: 18) {
            DesktopEditorialSubsection(
                "Core Setup",
                detail: "Define the next run target, dataset, and activation path."
            ) {
                coreTrainingSetupContent
            }

            if viewModel.loraDatasetSourceKind == .huggingFaceDataset {
                Divider()

                DesktopExpandableSettingRow(
                    title: "Dataset Mapping",
                    detail: datasetMappingSummaryText,
                    isExpanded: showsDatasetMapping
                ) {
                    showsDatasetMapping.toggle()
                }

                if showsDatasetMapping {
                    datasetMappingContent
                }
            }

            Divider()

            DesktopExpandableSettingRow(
                title: DesktopTrainingWorkspaceDefaults.advancedParametersTitle,
                detail: advancedParametersSummaryText,
                isExpanded: showsAdvanced
            ) {
                showsAdvanced.toggle()
            }

            if showsAdvanced {
                advancedParametersContent
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var savedJobsContent: some View {
        VStack(alignment: .leading, spacing: 14) {
            savedJobsActionBar

            if viewModel.loraTrainingJobs.isEmpty {
                DesktopInlineEmptyStateView(
                    title: "No Saved LoRA Jobs",
                    detail: "Save the current run draft to make it reusable across app restarts.",
                    symbolName: "tray.and.arrow.down"
                )
            } else {
                HStack(alignment: .top, spacing: 14) {
                    savedJobsList
                        .frame(minWidth: 240, maxWidth: .infinity, alignment: .topLeading)
                    savedJobDetail
                        .frame(minWidth: 280, maxWidth: .infinity, alignment: .topLeading)
                }
            }

            Divider()

            importExportContent
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var savedJobsActionBar: some View {
        HStack(spacing: 10) {
            Button("Save Draft") {
                viewModel.saveCurrentLoraTrainingJobDraft()
            }
            .buttonStyle(.borderedProminent)
            .disabled(viewModel.isLoraWorkflowActionInProgress)

            Button("Load Job") {
                viewModel.loadSelectedLoraTrainingJob()
            }
            .buttonStyle(.bordered)
            .disabled(viewModel.selectedLoraTrainingJob == nil || viewModel.isLoraWorkflowActionInProgress)

            Button("Duplicate") {
                viewModel.duplicateSelectedLoraTrainingJob()
            }
            .buttonStyle(.bordered)
            .disabled(viewModel.selectedLoraTrainingJob == nil || viewModel.isLoraWorkflowActionInProgress)

            Button("Rerun") {
                startRerunSavedJobTask()
            }
            .buttonStyle(.bordered)
            .disabled(viewModel.selectedLoraTrainingJob == nil || viewModel.isLoraWorkflowActionInProgress)

            Menu {
                Button("Cancel Job") {
                    viewModel.cancelSelectedLoraTrainingJob()
                }
                .disabled(viewModel.selectedLoraTrainingJob == nil || viewModel.isLoraWorkflowActionInProgress)

                Button("Delete Job") {
                    viewModel.deleteSelectedLoraTrainingJob()
                }
                .disabled(viewModel.selectedLoraTrainingJob == nil || viewModel.isLoraWorkflowActionInProgress)
            } label: {
                Image(systemName: "ellipsis.circle")
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .help("More Saved Job Actions")
            .accessibilityLabel("More Saved Job Actions")
        }
    }

    private var savedJobsList: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(viewModel.loraTrainingJobs) { job in
                Button {
                    viewModel.selectLoraTrainingJob(id: job.id)
                } label: {
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(alignment: .firstTextBaseline) {
                            DesktopPassiveHeadlineButton(title: job.title)
                            Spacer()
                            DesktopPassiveCaptionLabel(
                                title: job.status.rawValue.capitalized,
                                foregroundStyle: savedJobStatusColor(job.status)
                            )
                        }
                        Text("\(job.config.trainingMode.uppercased()) • \(job.config.adapterName)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(savedJobDatasetText(job))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
                    .background(
                        viewModel.selectedLoraTrainingJobID == job.id
                            ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                            : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                        in: RoundedRectangle(cornerRadius: 12)
                    )
                }
                .buttonStyle(.plain)
            }
        }
    }

    @ViewBuilder
    private var savedJobDetail: some View {
        if let job = viewModel.selectedLoraTrainingJob {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .firstTextBaseline) {
                    DesktopPassiveHeadlineButton(title: job.title)
                    Spacer()
                    Text(job.id)
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }

                Text(savedJobSummaryText(job))
                    .font(.caption)
                    .foregroundStyle(.secondary)

                if !job.lastRunJobID.isEmpty {
                    DesktopPassiveCaptionLabel(title: "Last run: \(job.lastRunJobID)")
                }

                if !job.outputPath.isEmpty || !job.manifestPath.isEmpty {
                    DisclosureGroup("Output And Manifest") {
                        VStack(alignment: .leading, spacing: 5) {
                            if !job.outputPath.isEmpty {
                                Text(job.outputPath)
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                            if !job.manifestPath.isEmpty, job.manifestPath != job.outputPath {
                                Text(job.manifestPath)
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                        }
                        .padding(.top, 4)
                    }
                    .font(.caption)
                }

                if !job.terminalMessage.isEmpty {
                    Text(job.terminalMessage)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if !job.latestOutputText.isEmpty {
                    DisclosureGroup("Latest Output") {
                        Text(job.latestOutputText)
                            .font(.caption2.monospaced())
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                            .lineLimit(8)
                            .padding(.top, 4)
                    }
                    .font(.caption)
                }

                let adapterCapabilityItems = savedJobAdapterCapabilityItems(job)
                if adapterCapabilityItems.isEmpty == false {
                    VStack(alignment: .leading, spacing: 6) {
                        DesktopPassiveCaptionLabel(title: "Adapter Capability")
                        ForEach(adapterCapabilityItems) { item in
                            VStack(alignment: .leading, spacing: 2) {
                                DesktopPassiveCaptionLabel(title: item.title)
                                Text(item.value)
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                    .font(.caption)
                }

                let followUpArtifacts = savedJobFollowUpArtifactItems(job)
                if followUpArtifacts.isEmpty == false {
                    VStack(alignment: .leading, spacing: 6) {
                        DesktopPassiveCaptionLabel(title: "Follow-up Artifacts")
                        ForEach(followUpArtifacts) { item in
                            VStack(alignment: .leading, spacing: 2) {
                                DesktopPassiveCaptionLabel(title: item.title)
                                Text(item.value)
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                            }
                        }
                    }
                    .font(.caption)
                }

                followUpActionsContent
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
        } else {
            DesktopInlineEmptyStateView(
                title: "No Saved Job Selected",
                detail: "Select a saved LoRA job to inspect its config and output state.",
                symbolName: "sidebar.leading"
            )
        }
    }

    private var followUpActionsContent: some View {
        VStack(alignment: .leading, spacing: 8) {
            DesktopPassiveCaptionLabel(title: "Follow-up Actions")
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 8)], spacing: 8) {
                ForEach(RuntimeLoraTrainingJobFollowUpAction.allCases) { action in
                    Button {
                        viewModel.prepareSelectedLoraTrainingJobFollowUp(action)
                    } label: {
                        DesktopPassiveCaptionLabel(title: action.title)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }
            }
        }
    }

    private var importExportContent: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                DesktopPassiveCaptionLabel(title: "Import Config Path")
                HStack(spacing: 8) {
                    TextField("Import Config Path", text: stringBinding(\.loraTrainingJobImportPath))
                        .textFieldStyle(.roundedBorder)
                    Button("Import") {
                        viewModel.importLoraTrainingJobConfigFromPath()
                    }
                    .buttonStyle(.bordered)
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)

            VStack(alignment: .leading, spacing: 6) {
                DesktopPassiveCaptionLabel(title: "Export Config Path")
                HStack(spacing: 8) {
                    TextField("Export Config Path", text: stringBinding(\.loraTrainingJobExportPath))
                        .textFieldStyle(.roundedBorder)
                    Button("Export") {
                        viewModel.exportSelectedLoraTrainingJobConfigToPath()
                    }
                    .buttonStyle(.bordered)
                    .disabled(viewModel.selectedLoraTrainingJob == nil)
                }
            }
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
    }

    private var coreTrainingSetupContent: some View {
        LazyVGrid(
            columns: [
                GridItem(.flexible(minimum: 260), spacing: 16, alignment: .top),
                GridItem(.flexible(minimum: 260), spacing: 16, alignment: .top),
            ],
            alignment: .leading,
            spacing: 16
        ) {
            DesktopEditorialFieldGroup(
                "Run Identity",
                detail: "Choose the base model and the adapter name for the next artifact."
            ) {
                VStack(alignment: .leading, spacing: 12) {
                    DesktopEditorialField("Base Model") {
                        Picker("Base Model", selection: stringBinding(\.selectedLoraModelID)) {
                            ForEach(viewModel.loraCapableModels, id: \.modelID) { model in
                                Text(model.displayNameWithID).tag(model.modelID)
                            }
                        }
                        .labelsHidden()
                        .pickerStyle(.menu)
                    }

                    DesktopEditorialField("Adapter Name") {
                        TextField("Adapter Name", text: stringBinding(\.loraAdapterName))
                            .textFieldStyle(.roundedBorder)
                    }
                }
            }

            DesktopEditorialFieldGroup(
                "Dataset & Mode",
                detail: "Select the dataset source, the training mode, and the preset."
            ) {
                VStack(alignment: .leading, spacing: 12) {
                    DesktopEditorialField("Dataset Source") {
                        Picker("Dataset Source", selection: datasetSourceBinding()) {
                            ForEach(RuntimeLoraDatasetSourceKind.allCases) { source in
                                Text(source.title).tag(source)
                            }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .frame(maxWidth: 340, alignment: .leading)
                    }

                    DesktopEditorialField(viewModel.loraDatasetSourceKind == .localPackage ? "Dataset URI" : "HF Dataset Path") {
                        if viewModel.loraDatasetSourceKind == .localPackage {
                            TextField("Dataset URI", text: stringBinding(\.loraDatasetURI))
                                .textFieldStyle(.roundedBorder)
                        } else {
                            TextField("HF Dataset Path", text: stringBinding(\.loraHFDatasetPath))
                                .textFieldStyle(.roundedBorder)
                        }
                    }

                    DesktopEditorialField("Training Mode") {
                        ViewThatFits(in: .horizontal) {
                            trainingModePicker
                                .pickerStyle(.segmented)
                                .frame(maxWidth: 640, alignment: .leading)
                            trainingModePicker
                                .pickerStyle(.menu)
                                .frame(maxWidth: 220, alignment: .leading)
                        }
                    }

                    DesktopEditorialField("Preset") {
                        Picker("Preset", selection: trainingPresetBinding()) {
                            ForEach(RuntimeLoraTrainingPreset.allCases) { preset in
                                Text(preset.title).tag(preset)
                            }
                        }
                        .labelsHidden()
                        .pickerStyle(.menu)
                    }
                }
            }

            if viewModel.loraTrainingMode.isAlignmentMode {
                DesktopEditorialFieldGroup(
                    "Alignment Controls",
                    detail: "Capture policy-alignment lineage and mode-specific controls for preference or reward-backed runs."
                ) {
                    VStack(alignment: .leading, spacing: 12) {
                        DesktopEditorialField("Reference Model Path") {
                            TextField("Optional reference model path", text: stringBinding(\.loraReferenceModelPath))
                                .textFieldStyle(.roundedBorder)
                        }

                        if viewModel.loraTrainingMode == .grpo {
                            DesktopEditorialField("GRPO Candidate Count") {
                                TextField("Candidates per prompt", text: stringBinding(\.loraGRPOCandidateCount))
                                    .textFieldStyle(.roundedBorder)
                            }
                        }

                        if viewModel.loraTrainingMode == .rlhf {
                            DesktopEditorialField("Reward Model Manifest") {
                                TextField("Reward model manifest path", text: stringBinding(\.loraRewardModelManifestPath))
                                    .textFieldStyle(.roundedBorder)
                            }
                        }

                        if viewModel.loraTrainingMode == .grpo || viewModel.loraTrainingMode == .rlhf {
                            DesktopEditorialField("KL Penalty") {
                                TextField("Optional KL penalty", text: stringBinding(\.loraKLPenalty))
                                    .textFieldStyle(.roundedBorder)
                            }
                        }
                    }
                }
            }

            DesktopEditorialFieldGroup(
                "Delivery",
                detail: "Define activation, routing, and experiment lineage for the resulting adapter."
            ) {
                VStack(alignment: .leading, spacing: 12) {
                    DesktopEditorialField("Activation Mode") {
                        Picker("Activation Mode", selection: activationModeBinding()) {
                            ForEach(RuntimeLoraActivationMode.allCases) { mode in
                                Text(mode.title).tag(mode)
                            }
                        }
                        .labelsHidden()
                        .pickerStyle(.segmented)
                        .frame(maxWidth: 360, alignment: .leading)
                    }

                    DesktopEditorialField(
                        "Experiment Group",
                        detail: "Leave blank to derive from the base model and adapter name."
                    ) {
                        TextField("Optional group id", text: stringBinding(\.loraExperimentGroupID))
                            .textFieldStyle(.roundedBorder)
                    }

                    DesktopEditorialField("Target Repo") {
                        TextField("Target Repo", text: stringBinding(\.loraTargetRepo))
                            .textFieldStyle(.roundedBorder)
                    }
                }
            }
        }
    }

    private var datasetMappingContent: some View {
        DesktopEditorialSubsection(
            "Dataset Mapping",
            detail: "Only expand when the dataset schema or split layout changes."
        ) {
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 14), GridItem(.flexible(), spacing: 14)], spacing: 12) {
                DesktopEditorialField("Config / Name") {
                    TextField("Config / Name", text: stringBinding(\.loraHFDatasetName))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Revision") {
                    TextField("Revision", text: stringBinding(\.loraHFDatasetRevision))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Train Split") {
                    TextField("Train Split", text: stringBinding(\.loraHFTrainSplit))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Valid Split") {
                    TextField("Valid Split", text: stringBinding(\.loraHFValidSplit))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Text Feature") {
                    TextField("Text Feature", text: stringBinding(\.loraTextFeature))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Prompt Feature") {
                    TextField("Prompt Feature", text: stringBinding(\.loraPromptFeature))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Completion Feature") {
                    TextField("Completion Feature", text: stringBinding(\.loraCompletionFeature))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Chat Feature") {
                    TextField("Chat Feature", text: stringBinding(\.loraChatFeature))
                        .textFieldStyle(.roundedBorder)
                }
            }
        }
    }

    private var trainingModePicker: some View {
        Picker("Training Mode", selection: trainingModeBinding()) {
            ForEach(RuntimeLoraTrainingMode.allCases) { mode in
                Text(mode.title).tag(mode)
            }
        }
        .labelsHidden()
    }

    private var advancedParametersContent: some View {
        VStack(alignment: .leading, spacing: 14) {
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 14), GridItem(.flexible(), spacing: 14)], spacing: 12) {
                DesktopEditorialField("Rank") {
                    TextField("Rank", text: stringBinding(\.loraRank))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Alpha") {
                    TextField("Alpha", text: stringBinding(\.loraAlpha))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Dropout") {
                    TextField("Dropout", text: stringBinding(\.loraDropout))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Batch Size") {
                    TextField("Batch Size", text: stringBinding(\.loraBatchSize))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Epochs") {
                    TextField("Epochs", text: stringBinding(\.loraEpochs))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Max Steps") {
                    TextField("Optional max steps", text: stringBinding(\.loraMaxSteps))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Learning Rate") {
                    TextField("Learning Rate", text: stringBinding(\.loraLearningRate))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Max Seq Length") {
                    TextField("Max Seq Length", text: stringBinding(\.loraMaxSeqLength))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Sample Limit") {
                    TextField("Optional sample limit", text: stringBinding(\.loraSampleLimit))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Gradient Accumulation") {
                    TextField("Optional accumulation steps", text: stringBinding(\.loraGradientAccumulation))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Target Modules") {
                    TextField("Target Modules", text: stringBinding(\.loraTargetModules))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Num Layers") {
                    TextField("Num Layers", text: stringBinding(\.loraNumLayers))
                        .textFieldStyle(.roundedBorder)
                }
                DesktopEditorialField("Derived Model Alias") {
                    TextField("Derived Model Alias", text: stringBinding(\.loraDerivedModelAlias))
                        .textFieldStyle(.roundedBorder)
                }
            }

            DesktopEditorialFieldGroup("Behavior Flags") {
                VStack(alignment: .leading, spacing: 10) {
                    Toggle("Response Only", isOn: boolBinding(\.loraResponseOnly))
                    Toggle("Mask Prompt", isOn: boolBinding(\.loraMaskPrompt))
                    Toggle("Gradient Checkpointing", isOn: boolBinding(\.loraGradientCheckpointing))
                }
            }
        }
        .padding(.top, 4)
    }

    @ViewBuilder
    private var adapterRegistryContent: some View {
        if viewModel.adapterPackages.isEmpty {
            DesktopInlineEmptyStateView(
                title: "No Adapter Packages Yet",
                detail: "Train a LoRA run or refresh registry snapshots to inspect saved adapters and activation targets.",
                symbolName: "shippingbox"
            )
        } else {
            VStack(alignment: .leading, spacing: 14) {
                adapterActivationContent

                Divider()

                adaptersContent
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private var adapterActivationContent: some View {
        if viewModel.adapterPackages.isEmpty {
            DesktopInlineEmptyStateView(
                title: "No Adapter Packages Yet",
                detail: "Train a LoRA run or refresh registry snapshots to inspect saved adapters and activation targets.",
                symbolName: "shippingbox"
            )
        } else {
            VStack(alignment: .leading, spacing: 10) {
                Picker("Selected Adapter", selection: stringBinding(\.selectedAdapterPackageID)) {
                    ForEach(viewModel.adapterPackages) { adapter in
                        Text("\(adapter.adapterName) • \(adapter.statusText)").tag(adapter.id)
                    }
                }
                .pickerStyle(.menu)

                if let adapter = viewModel.selectedAdapterPackage {
                    Text(adapter.adapterName)
                        .font(.headline)
                    Text("\(adapter.statusText) • \(adapter.activationStatusText) • \(adapter.exportabilityText)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("\(adapter.experimentSummaryText) • \(adapter.performanceSummaryText)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    if !adapter.targetRepo.isEmpty {
                        Text("Target repo: \(adapter.targetRepo)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if !adapter.publishedRepo.isEmpty {
                        Text("Published repo: \(adapter.publishedRepo)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    if !adapter.derivedModelID.isEmpty {
                        Text("Derived model: \(adapter.derivedModelID)")
                            .font(.caption.weight(.semibold))
                    }
                    if !adapter.derivedModelPath.isEmpty || !adapter.outputPath.isEmpty {
                        DisclosureGroup("Artifact Paths") {
                            VStack(alignment: .leading, spacing: 6) {
                                if !adapter.derivedModelPath.isEmpty {
                                    Text(adapter.derivedModelPath)
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(.secondary)
                                        .textSelection(.enabled)
                                }
                                if !adapter.outputPath.isEmpty {
                                    Text("Adapter manifest: \(adapter.outputPath)")
                                        .font(.caption2.monospaced())
                                        .foregroundStyle(.secondary)
                                        .textSelection(.enabled)
                                }
                            }
                            .padding(.top, 4)
                        }
                        .font(.caption)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
        }
    }

    @ViewBuilder
    private var experimentGroupsContent: some View {
        if viewModel.loraExperimentGroups.isEmpty {
            DesktopInlineEmptyStateView(
                title: "No Grouped LoRA Runs Yet",
                detail: "Run multiple experiments with the same adapter family to unlock resume and best-checkpoint recommendations.",
                symbolName: "square.stack.3d.forward.dottedline"
            )
        } else {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(Array(viewModel.loraExperimentGroups.enumerated()), id: \.element.id) { index, group in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(alignment: .top, spacing: 12) {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(group.title.isEmpty ? group.groupID : group.title)
                                    .font(.headline)
                                Text("\(group.runCount) runs • \(group.latestPresetTitle)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            Spacer()
                            Button("Use Group") {
                                viewModel.loraExperimentGroupID = group.groupID
                                viewModel.loraResumeFromManifestPath = ""
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                            Button("Resume From Best") {
                                viewModel.loraExperimentGroupID = group.groupID
                                viewModel.loraResumeFromManifestPath = group.recommendedManifestPath
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                            .disabled(group.recommendedManifestPath.isEmpty)
                        }
                        Text(group.experimentSummaryText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(group.performanceSummaryText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text("Best loss \(String(format: "%.3f", group.bestLoss))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if !group.recommendedManifestPath.isEmpty {
                            DisclosureGroup("Best checkpoint manifest") {
                                Text(group.recommendedManifestPath)
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                                    .padding(.top, 4)
                            }
                            .font(.caption)
                        }
                        Text(group.resumeReadySummaryText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if !group.checkpointLineage.isEmpty {
                            DisclosureGroup("Checkpoint lineage") {
                                VStack(alignment: .leading, spacing: 2) {
                                    ForEach(group.checkpointLineage) { entry in
                                        Text("\(entry.runID) • \(entry.checkpointCount) checkpoints • \(entry.resumeReady ? "resume ready" : "resume unavailable")")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                .padding(.top, 4)
                            }
                            .font(.caption)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityElement(children: .contain)

                    if index < viewModel.loraExperimentGroups.count - 1 {
                        Divider()
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var adaptersContent: some View {
        if viewModel.adapterPackages.isEmpty {
            DesktopInlineEmptyStateView(
                title: "No Saved Adapters Yet",
                detail: "Completed LoRA runs will land here with target repo, activation readiness, and performance summaries.",
                symbolName: "tray"
            )
        } else {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(Array(viewModel.adapterPackages.enumerated()), id: \.element.id) { index, adapter in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(adapter.adapterName)
                                .font(.headline)
                            Spacer()
                            Text(adapter.statusText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Text(adapter.sourceModel)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if !adapter.datasetURI.isEmpty {
                            Text(adapter.datasetURI)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Text("\(adapter.experimentSummaryText) • \(adapter.performanceSummaryText)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if !adapter.targetRepo.isEmpty {
                            Text("Target repo: \(adapter.targetRepo)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        if !adapter.outputPath.isEmpty {
                            DisclosureGroup("Manifest path") {
                                Text(adapter.outputPath)
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                                    .padding(.top, 4)
                            }
                            .font(.caption)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityElement(children: .contain)

                    if index < viewModel.adapterPackages.count - 1 {
                        Divider()
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var trainingJobsContent: some View {
        if viewModel.trainingHistory.isEmpty {
            DesktopInlineEmptyStateView(
                title: "No Training Jobs Yet",
                detail: "Run LoRA training to capture loss, throughput, memory, and checkpoint lineage across experiments.",
                symbolName: "chart.line.uptrend.xyaxis"
            )
        } else {
            VStack(alignment: .leading, spacing: 12) {
                ForEach(Array(viewModel.trainingHistory.enumerated()), id: \.element.id) { index, entry in
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(entry.adapterName)
                                .font(.headline)
                            Spacer()
                            Text(entry.statusText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Text(entry.stageText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if !entry.datasetURI.isEmpty {
                            Text(entry.datasetURI)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Text("\(entry.experimentSummaryText) • \(entry.performanceSummaryText)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if !entry.outputPath.isEmpty {
                            DisclosureGroup("Run artifact path") {
                                Text(entry.outputPath)
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.secondary)
                                    .textSelection(.enabled)
                                    .padding(.top, 4)
                            }
                            .font(.caption)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityElement(children: .contain)

                    if index < viewModel.trainingHistory.count - 1 {
                        Divider()
                    }
                }
            }
        }
    }

    private var idleWorkflowTitle: String {
        if let adapter = viewModel.selectedAdapterPackage {
            return adapter.derivedModelID.isEmpty ? "Ready to Activate" : "Adapter Ready"
        }
        if viewModel.loraExperimentGroups.isEmpty == false {
            return "Resume-Ready Runs Available"
        }
        return "Ready to Train"
    }

    private var idleWorkflowDetail: String {
        if let adapter = viewModel.selectedAdapterPackage {
            if adapter.derivedModelID.isEmpty {
                return "Select Activate Adapter to attach \(adapter.adapterName) to the current base model."
            }
            return "\(adapter.adapterName) is already available as \(adapter.derivedModelID)."
        }
        if let group = viewModel.loraExperimentGroups.first {
            return group.resumeReadySummaryText
        }
        return "Configure the dataset, preset, and adapter settings, then start a LoRA run."
    }

    private var idleWorkflowSymbolName: String {
        if let adapter = viewModel.selectedAdapterPackage {
            return adapter.derivedModelID.isEmpty ? "bolt.horizontal.circle" : "checkmark.circle"
        }
        if viewModel.loraExperimentGroups.isEmpty == false {
            return "arrow.trianglehead.branch"
        }
        return "sparkles"
    }

    private func workflowStatusColor(for phase: RuntimeLoraWorkflowPhase) -> Color {
        switch phase {
        case .running:
            return MelixDesignTokens.accent
        case .succeeded:
            return MelixDesignTokens.StatusColor.success
        case .failed:
            return MelixDesignTokens.StatusColor.error
        }
    }

    private var advancedParametersSummaryText: String {
        "Rank \(viewModel.loraRank) • Alpha \(viewModel.loraAlpha) • Dropout \(viewModel.loraDropout) • Batch \(viewModel.loraBatchSize) • Epochs \(viewModel.loraEpochs)"
    }

    private var datasetMappingSummaryText: String {
        let config = viewModel.loraHFDatasetName.isEmpty ? "default config" : viewModel.loraHFDatasetName
        let train = viewModel.loraHFTrainSplit.isEmpty ? "train split pending" : viewModel.loraHFTrainSplit
        let valid = viewModel.loraHFValidSplit.isEmpty ? "valid split pending" : viewModel.loraHFValidSplit
        return "\(config) • train \(train) • valid \(valid)"
    }

    private func savedJobStatusColor(_ status: LoraTrainingJobStatus) -> Color {
        switch status {
        case .draft:
            return .secondary
        case .running:
            return MelixDesignTokens.accent
        case .succeeded:
            return MelixDesignTokens.StatusColor.success
        case .failed:
            return MelixDesignTokens.StatusColor.error
        case .canceled:
            return MelixDesignTokens.StatusColor.warning
        }
    }

    private func savedJobDatasetText(_ job: LoraTrainingJobRecord) -> String {
        if job.config.datasetSourceKind == RuntimeLoraDatasetSourceKind.huggingFaceDataset.rawValue {
            return job.config.hfDatasetPath.isEmpty ? "HF dataset pending" : job.config.hfDatasetPath
        }
        return job.config.datasetURI.isEmpty ? "Dataset pending" : job.config.datasetURI
    }

    private func savedJobSummaryText(_ job: LoraTrainingJobRecord) -> String {
        let model = job.config.modelID.isEmpty ? "No base model" : job.config.modelID
        let activation = job.config.activationMode.replacingOccurrences(of: "_", with: " ")
        return "\(model) • \(job.config.trainingMode.uppercased()) • \(activation)"
    }

    private func savedJobAdapterCapabilityItems(_ job: LoraTrainingJobRecord) -> [DesktopTrainingSummaryItem] {
        guard let receipt = RuntimeViewModel.adapterCapabilityReceipt(from: job) else {
            return []
        }
        return [
            DesktopTrainingSummaryItem(title: "Family", value: receipt.adapterFamily, detail: ""),
            DesktopTrainingSummaryItem(title: "Algorithm", value: receipt.adapterAlgorithm, detail: ""),
            DesktopTrainingSummaryItem(title: "Backend Support", value: receipt.backendSupportText, detail: ""),
            DesktopTrainingSummaryItem(title: "Unsupported Reason", value: receipt.unsupportedReason, detail: ""),
            DesktopTrainingSummaryItem(title: "LoRA-like", value: receipt.loraLikeText, detail: ""),
            DesktopTrainingSummaryItem(title: "Mergeable", value: receipt.mergeableText, detail: ""),
            DesktopTrainingSummaryItem(title: "ReLoRA-compatible", value: receipt.reloraCompatibleText, detail: ""),
            DesktopTrainingSummaryItem(title: "Quantized Base", value: receipt.quantizedBaseSupportedText, detail: ""),
        ].filter { item in
            item.value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        }
    }

    private func savedJobFollowUpArtifactItems(_ job: LoraTrainingJobRecord) -> [DesktopTrainingSummaryItem] {
        let artifacts = job.followUpArtifacts
        return [
            DesktopTrainingSummaryItem(title: "Adapter Manifest", value: artifacts.adapterManifestPath, detail: ""),
            DesktopTrainingSummaryItem(title: "Derived Model", value: artifacts.derivedModelID, detail: ""),
            DesktopTrainingSummaryItem(title: "Derived Model Path", value: artifacts.derivedModelPath, detail: ""),
            DesktopTrainingSummaryItem(title: "Quantized Artifact", value: artifacts.quantizedArtifactPath, detail: ""),
            DesktopTrainingSummaryItem(title: "Converted Artifact", value: artifacts.convertedArtifactPath, detail: ""),
            DesktopTrainingSummaryItem(title: "Benchmark Job", value: artifacts.benchmarkJobID, detail: ""),
            DesktopTrainingSummaryItem(title: "Evaluation Job", value: artifacts.evaluationJobID, detail: ""),
            DesktopTrainingSummaryItem(title: "Published Repo", value: artifacts.publishedRepo, detail: ""),
            DesktopTrainingSummaryItem(title: "Memory Fit", value: artifacts.memoryFitSummaryText, detail: ""),
        ].filter { item in
            item.value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        }
    }

    private func stringBinding(_ keyPath: ReferenceWritableKeyPath<RuntimeViewModel, String>) -> Binding<String> {
        Binding(
            get: { viewModel[keyPath: keyPath] },
            set: { viewModel[keyPath: keyPath] = $0 }
        )
    }

    private func boolBinding(_ keyPath: ReferenceWritableKeyPath<RuntimeViewModel, Bool>) -> Binding<Bool> {
        Binding(
            get: { viewModel[keyPath: keyPath] },
            set: { viewModel[keyPath: keyPath] = $0 }
        )
    }

    private func datasetSourceBinding() -> Binding<RuntimeLoraDatasetSourceKind> {
        Binding(
            get: { viewModel.loraDatasetSourceKind },
            set: { viewModel.loraDatasetSourceKind = $0 }
        )
    }

    private func trainingModeBinding() -> Binding<RuntimeLoraTrainingMode> {
        Binding(
            get: { viewModel.loraTrainingMode },
            set: { viewModel.loraTrainingMode = $0 }
        )
    }

    private func trainingPresetBinding() -> Binding<RuntimeLoraTrainingPreset> {
        Binding(
            get: { viewModel.selectedLoraTrainingPreset },
            set: { viewModel.applyLoraTrainingPreset($0) }
        )
    }

    private func activationModeBinding() -> Binding<RuntimeLoraActivationMode> {
        Binding(
            get: { viewModel.loraActivationMode },
            set: { viewModel.loraActivationMode = $0 }
        )
    }

    func trainLoRA() async {
        await viewModel.trainPrimaryModel()
    }

    func activateAdapter() async {
        await viewModel.activateLatestAdapter()
    }

    func publishAdapter() async {
        await viewModel.publishLatestAdapter()
    }

    func removeDerivedModel() async {
        await viewModel.removeSelectedDerivedModel()
    }

    private func startTrainLoRATask() {
        Task { await trainLoRA() }
    }

    private func startRerunSavedJobTask() {
        Task { await viewModel.rerunSelectedLoraTrainingJob() }
    }

    private func startActivateAdapterTask() {
        Task { await activateAdapter() }
    }

    private func startPublishAdapterTask() {
        Task { await publishAdapter() }
    }

    private func startRemoveDerivedModelTask() {
        Task { await removeDerivedModel() }
    }
}

enum DesktopTrainingWorkspaceDefaults {
    static let showsAdvancedParameters = false
    static let advancedParametersTitle = "Advanced Training Parameters"
}

enum DesktopLoRAVisualPolish {
    static let pageBackgroundColorSpec = MelixDesignTokens.Palette.backgroundBase
    static let pageBackgroundNSColor = pageBackgroundColorSpec.nsColor
    static let pageBackgroundColor = Color(nsColor: pageBackgroundNSColor)
    static let sectionSurfaceOpacity = 0.04
    static let metricSurfaceOpacity = 0.032
    static let selectedHistorySurfaceOpacity = MelixDesignTokens.AccentOpacity.selected
    static let chartFillOpacity = 0.24
}

struct DesktopTrainingSummaryItem: Equatable, Identifiable {
    let title: String
    let value: String
    let detail: String

    var id: String {
        title
    }
}

private struct DesktopEditorialSectionCard<Content: View>: View {
    let title: String
    @ViewBuilder let content: () -> Content

    init(_ title: String, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: MelixDesignTokens.Spacing.md) {
            DesktopPassiveSectionLabel(title: title)
            content()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(MelixDesignTokens.Spacing.panelInset)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: 14, style: .continuous)
        )
    }
}

private struct DesktopPassiveSectionLabel: View {
    let title: String

    var body: some View {
        TextField("", text: .constant(title))
            .textFieldStyle(.plain)
            .allowsHitTesting(false)
            .melixSectionLabel()
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DesktopEditorialSubsection<Content: View>: View {
    let title: String
    let detail: String?
    @ViewBuilder let content: () -> Content

    init(_ title: String, detail: String? = nil, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.detail = detail
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                if let detail, detail.isEmpty == false {
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            content()
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DesktopTrainingSummaryValueView: View {
    let item: DesktopTrainingSummaryItem

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(item.title).melixSectionLabel()
            Text(item.value)
                .font(.headline)
                .lineLimit(1)
                .truncationMode(.middle)
            Text(item.detail)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            Color.secondary.opacity(DesktopLoRAVisualPolish.metricSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: 10, style: .continuous)
        )
    }
}

private struct DesktopEditorialFieldGroup<Content: View>: View {
    let title: String
    let detail: String?
    @ViewBuilder let content: () -> Content

    init(_ title: String, detail: String? = nil, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.detail = detail
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            DesktopPassiveHeadlineButton(title: title)
            if let detail, detail.isEmpty == false {
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            content()
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            Color.secondary.opacity(DesktopLoRAVisualPolish.metricSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: 12, style: .continuous)
        )
    }
}

private struct DesktopEditorialField<Content: View>: View {
    let title: String
    let detail: String?
    @ViewBuilder let content: () -> Content

    init(_ title: String, detail: String? = nil, @ViewBuilder content: @escaping () -> Content) {
        self.title = title
        self.detail = detail
        self.content = content
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            content()
            if let detail, detail.isEmpty == false {
                Text(detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DesktopEditorialMetricItem: Identifiable {
    let title: String
    let value: String
    let detail: String

    var id: String {
        "\(title)|\(value)|\(detail)"
    }
}

private struct DesktopEditorialMetricCardView: View {
    let item: DesktopEditorialMetricItem

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(item.title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(item.value)
                .font(.headline)
                .monospacedDigit()
            if item.detail.isEmpty == false {
                Text(item.detail)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            Color.secondary.opacity(DesktopLoRAVisualPolish.metricSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: 12, style: .continuous)
        )
    }
}

private struct DesktopPassiveHeadlineButton: View {
    let title: String

    var body: some View {
        TextField("", text: .constant(title))
            .textFieldStyle(.plain)
            .allowsHitTesting(false)
            .font(.headline)
            .foregroundStyle(.primary)
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DesktopPassiveCaptionLabel: View {
    let title: String
    let foregroundStyle: Color?

    init(title: String, foregroundStyle: Color? = nil) {
        self.title = title
        self.foregroundStyle = foregroundStyle
    }

    var body: some View {
        DesktopPassiveStaticTextLabel(
            title: title,
            font: .systemFont(ofSize: NSFont.smallSystemFontSize, weight: .semibold),
            textColor: foregroundStyle.map(NSColor.init) ?? .secondaryLabelColor
        )
            .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct DesktopServingAccelerationProfilePicker: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            DesktopPassiveStaticTextLabel(
                title: "Acceleration Profile",
                font: .systemFont(ofSize: NSFont.smallSystemFontSize, weight: .semibold),
                textColor: .secondaryLabelColor
            )
            Picker(
                "Acceleration Profile",
                selection: Binding(
                    get: { viewModel.selectedServerSession?.servingDefaults.accelerationProfile ?? ServingAccelerationProfiles.defaultProfileID },
                    set: { viewModel.updateSelectedServerSessionAccelerationProfile($0) }
                )
            ) {
                ForEach(viewModel.servingAccelerationProfileOptions, id: \.id) { profile in
                    Text(profile.label).tag(profile.id)
                }
            }
            .pickerStyle(.menu)
            .frame(maxWidth: 280, alignment: .leading)
        }
    }
}

struct DesktopServingAccelerationProfileSummary: View {
    let servingDefaults: DesktopServerServingDefaultsState

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            DesktopPassiveStaticTextLabel(
                title: "Requested profile: \(servingAccelerationProfileLabel(servingDefaults.accelerationProfile))",
                font: .systemFont(ofSize: NSFont.smallSystemFontSize),
                textColor: .secondaryLabelColor
            )
            DesktopPassiveStaticTextLabel(
                title: "Effective profile: \(servingAccelerationProfileLabel(servingDefaults.effectiveAccelerationProfile))",
                font: .systemFont(ofSize: NSFont.smallSystemFontSize),
                textColor: .secondaryLabelColor
            )
            DesktopPassiveStaticTextLabel(
                title: "Intent: \(servingDefaults.accelerationProfileIntent)",
                font: .systemFont(ofSize: NSFont.smallSystemFontSize),
                textColor: .secondaryLabelColor,
                lineBreakMode: .byWordWrapping,
                maximumNumberOfLines: 2
            )
            DesktopPassiveStaticTextLabel(
                title: "Resolved defaults: \(desktopAccelerationModeText(servingDefaults.effectiveAccelerationMode)) • sequences \(servingDefaults.effectiveMaxConcurrentRequests) • prefill \(servingDefaults.effectivePrefillBatchSize) • completion \(servingDefaults.effectiveCompletionBatchSize)",
                font: .systemFont(ofSize: NSFont.smallSystemFontSize),
                textColor: .secondaryLabelColor,
                lineBreakMode: .byWordWrapping,
                maximumNumberOfLines: 2
            )
        }
    }
}

private struct DesktopPassiveStaticTextLabel: NSViewRepresentable {
    let title: String
    let font: NSFont
    let textColor: NSColor
    let lineBreakMode: NSLineBreakMode
    let maximumNumberOfLines: Int

    init(
        title: String,
        font: NSFont,
        textColor: NSColor,
        lineBreakMode: NSLineBreakMode = .byTruncatingTail,
        maximumNumberOfLines: Int = 1
    ) {
        self.title = title
        self.font = font
        self.textColor = textColor
        self.lineBreakMode = lineBreakMode
        self.maximumNumberOfLines = maximumNumberOfLines
    }

    func makeNSView(context: Context) -> NSTextField {
        let label = NSTextField(labelWithString: title)
        label.font = font
        label.textColor = textColor
        label.lineBreakMode = lineBreakMode
        label.maximumNumberOfLines = maximumNumberOfLines
        label.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return label
    }

    func updateNSView(_ label: NSTextField, context: Context) {
        label.stringValue = title
        label.font = font
        label.textColor = textColor
        label.lineBreakMode = lineBreakMode
        label.maximumNumberOfLines = maximumNumberOfLines
    }
}

private struct DesktopExpandableSettingRow: View {
    let title: String
    let detail: String
    let isExpanded: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: isExpanded ? "chevron.down.circle.fill" : "chevron.right.circle")
                    .foregroundStyle(MelixDesignTokens.accent)
                VStack(alignment: .leading, spacing: 4) {
                    Text(title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.primary)
                    Text(detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(12)
            .background(
                Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                in: RoundedRectangle(cornerRadius: 10)
            )
        }
        .buttonStyle(.plain)
    }
}

private struct DesktopInlineEmptyStateView: View {
    let title: String
    let detail: String
    let symbolName: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Image(systemName: symbolName)
                    .foregroundStyle(MelixDesignTokens.accent)
                Text(title)
                    .font(.headline)
            }
            Text(detail)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
    }
}

enum DesktopDiagnosticsStage: String, CaseIterable, Identifiable {
    case benchmark
    case matrix
    case evaluation

    var id: String { rawValue }

    var title: String {
        switch self {
        case .benchmark:
            return "Benchmark"
        case .matrix:
            return "Matrix"
        case .evaluation:
            return "Evaluation"
        }
    }
}

struct DesktopDiagnosticsRunMonitorView: View {
    let monitor: RuntimeDiagnosticsRunMonitorState

    private var accentColor: Color {
        switch monitor.phase {
        case .running:
            return MelixDesignTokens.accent
        case .completed:
            return MelixDesignTokens.StatusColor.success
        case .failed:
            return MelixDesignTokens.StatusColor.error
        }
    }

    private var symbolName: String {
        switch monitor.phase {
        case .running:
            return "gauge.with.dots.needle.67percent"
        case .completed:
            return "checkmark.circle.fill"
        case .failed:
            return "exclamationmark.triangle.fill"
        }
    }

    private var metricText: String {
        monitor.primaryMetricText.isEmpty ? "Collecting metrics" : monitor.primaryMetricText
    }

    private var artifactText: String {
        monitor.artifactText.isEmpty ? "Artifact pending" : monitor.artifactText
    }

    private var progressValue: Double {
        monitor.progressFraction ?? (monitor.phase == .completed ? 1 : 0)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 10) {
                Image(systemName: symbolName)
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundStyle(accentColor)
                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 8) {
                        Text(monitor.title)
                            .font(.headline)
                        if monitor.phase == .running {
                            ProgressView()
                                .controlSize(.small)
                        }
                    }
                    Text("\(monitor.targetText) • \(monitor.suiteText)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }
                Spacer(minLength: 12)
                Text(monitor.statusText)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(accentColor)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(accentColor.opacity(0.12), in: Capsule())
            }

            VStack(alignment: .leading, spacing: 6) {
                ProgressView(value: progressValue)
                    .tint(accentColor)
                Text(monitor.progressText.isEmpty ? monitor.statusText : monitor.progressText)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            if monitor.steps.isEmpty == false {
                DesktopDiagnosticsRunStepTimelineView(steps: monitor.steps, accentColor: accentColor)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 150), spacing: 10)], spacing: 10) {
                DesktopDiagnosticsRunMonitorTile(title: "Elapsed") {
                    elapsedText
                }
                DesktopDiagnosticsRunMonitorTile(title: "Primary Metric", value: metricText)
                DesktopDiagnosticsRunMonitorTile(title: "Artifact", value: artifactText)
            }

            if monitor.recentEvents.isEmpty == false {
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(Array(monitor.recentEvents.enumerated()), id: \.offset) { _, event in
                        Text(event)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                            .textSelection(.enabled)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } else if monitor.detailText.isEmpty == false {
                Text(monitor.detailText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder
    private var elapsedText: some View {
        if monitor.phase == .running, let startedAt = monitor.startedAt {
            TimelineView(.periodic(from: startedAt, by: 1)) { context in
                Text(Self.elapsedText(since: startedAt, now: context.date))
            }
        } else {
            Text(monitor.elapsedText)
        }
    }

    private static func elapsedText(since startedAt: Date, now: Date) -> String {
        let seconds = max(0, now.timeIntervalSince(startedAt))
        if seconds < 10 {
            return String(format: "%.1fs", seconds)
        }
        if seconds < 60 {
            return "\(Int(seconds.rounded()))s"
        }
        let minutes = Int(seconds) / 60
        let remainder = Int(seconds) % 60
        return "\(minutes)m \(remainder)s"
    }
}

private struct DesktopDiagnosticsRunStepTimelineView: View {
    let steps: [RuntimeDiagnosticsRunStepState]
    let accentColor: Color

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), spacing: 8)], spacing: 8) {
            ForEach(steps) { step in
                HStack(spacing: 6) {
                    Image(systemName: symbolName(for: step.phase))
                        .font(.system(size: 12, weight: .semibold))
                        .foregroundStyle(color(for: step.phase))
                        .frame(width: 16, height: 16)
                    Text(step.title)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(step.phase == .pending ? .secondary : .primary)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
                .background(color(for: step.phase).opacity(step.phase == .pending ? 0.06 : 0.12), in: RoundedRectangle(cornerRadius: 8))
            }
        }
    }

    private func symbolName(for phase: RuntimeDiagnosticsRunStepState.Phase) -> String {
        switch phase {
        case .pending:
            return "circle"
        case .running:
            return "arrow.triangle.2.circlepath"
        case .completed:
            return "checkmark.circle.fill"
        case .failed:
            return "xmark.circle.fill"
        }
    }

    private func color(for phase: RuntimeDiagnosticsRunStepState.Phase) -> Color {
        switch phase {
        case .pending:
            return .secondary
        case .running:
            return accentColor
        case .completed:
            return MelixDesignTokens.StatusColor.success
        case .failed:
            return MelixDesignTokens.StatusColor.error
        }
    }
}

private struct DesktopDiagnosticsRunMonitorTile<Content: View>: View {
    let title: String
    let content: Content

    init(title: String, value: String) where Content == Text {
        self.title = title
        self.content = Text(value)
    }

    init(title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(title)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            content
                .font(.caption.weight(.semibold))
                .lineLimit(2)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(10)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
    }
}

struct DesktopDiagnosticsToolSectionView: View {
    static let emptyBenchmarkTitle = "No Benchmark Results Yet"
    static let emptyBenchmarkDetail = "Run Benchmark to capture latency and throughput history."
    static let emptyEvaluationTitle = "No Evaluation Results Yet"
    static let emptyEvaluationDetail = "Run Evaluation to inspect scores and sample previews."

    private enum EvidenceRowLimit {
        static let metrics = 6
        static let runs = 8
        static let probes = 10
        static let telemetry = 8
        static let processes = 8
        static let artifacts = 12
        static let gaps = 6
    }

    let viewModel: RuntimeViewModel
    let foundation: DesktopFoundationState
    @State private var selectedStage: DesktopDiagnosticsStage
    @State private var evidenceReportFilter = ""

    init(viewModel: RuntimeViewModel, foundation: DesktopFoundationState) {
        self.viewModel = viewModel
        self.foundation = foundation
        _selectedStage = State(initialValue: Self.initialStage(for: viewModel))
    }

    static func initialStage(for viewModel: RuntimeViewModel) -> DesktopDiagnosticsStage {
        if let preferredStage = viewModel.preferredDiagnosticsStage {
            switch preferredStage {
            case .benchmark:
                return .benchmark
            case .matrix:
                return .matrix
            case .evaluation:
                return .evaluation
            }
        }
        if viewModel.selectedBenchmarkPresentationMode == .matrix {
            return .matrix
        }
        if viewModel.selectedEvaluationMode == .compare
            || viewModel.selectedEvaluationHistoryJobID.isEmpty == false
            || viewModel.selectedEvaluationSemanticJudgeRemoteServerID.isEmpty == false
            || viewModel.evaluationSemanticJudgeModelID.isEmpty == false {
            return .evaluation
        }
        if viewModel.benchmarkHistory.isEmpty == false {
            return .benchmark
        }
        if viewModel.benchmarkMatrixHistory.isEmpty == false {
            return .matrix
        }
        if viewModel.evaluationHistory.isEmpty == false
            && viewModel.benchmarkHistory.isEmpty
            && viewModel.benchmarkMatrixHistory.isEmpty {
            return .evaluation
        }
        return .benchmark
    }

    func inspectPrimaryModel() async {
        await viewModel.inspectPrimaryModel()
    }

    func runDoctor() async {
        await viewModel.runDoctor()
    }

    func runBenchmark() async {
        applyDiagnosticsStage(.benchmark)
        await viewModel.runBench()
    }

    func refreshBenchmarkResults() async {
        await viewModel.refreshBenchmarkHistory()
    }

    func exportBenchmarkCSV() async {
        await viewModel.exportSelectedBenchmarkCSV()
    }

    func runBenchmarkMatrix() async {
        applyDiagnosticsStage(.matrix)
        await viewModel.runBenchMatrix()
    }

    func refreshBenchmarkMatrixResults() async {
        await viewModel.refreshBenchmarkHistory()
    }

    func exportBenchmarkMatrixSummaryCSV() async {
        await viewModel.exportSelectedBenchmarkMatrixSummaryCSV()
    }

    func exportBenchmarkMatrixRequestsCSV() async {
        await viewModel.exportSelectedBenchmarkMatrixRequestsCSV()
    }

    func runEvaluation() async {
        applyDiagnosticsStage(.evaluation)
        await viewModel.runEvaluation()
    }

    func runEvaluationCompare() async {
        applyDiagnosticsStage(.evaluation)
        viewModel.selectedEvaluationMode = .compare
        await viewModel.runEvaluation()
    }

    func refreshEvaluationResults() async {
        await viewModel.refreshEvaluationHistory()
    }

    func exportEvaluationSummaryCSV() async {
        await viewModel.exportSelectedEvaluationSummaryCSV()
    }

    func exportEvaluationSamplesCSV() async {
        await viewModel.exportSelectedEvaluationSamplesCSV()
    }

    func exportEvaluationSamplesJSONL() async {
        await viewModel.exportSelectedEvaluationSamplesJSONL()
    }

    func refreshTooling() async {
        await viewModel.refreshModelOpsProductState()
    }

    func toggleBenchmarkSuiteSelection(_ suiteID: String) {
        viewModel.toggleBenchmarkSuite(suiteID)
    }

    func selectBenchmarkHistory(jobID: String) {
        viewModel.selectBenchmarkHistory(jobID: jobID)
    }

    func selectBenchmarkMatrixHistory(jobID: String) {
        viewModel.selectBenchmarkMatrixHistory(jobID: jobID)
    }

    func toggleEvaluationSuiteSelection(_ suiteID: String) {
        viewModel.toggleEvaluationSuite(suiteID)
    }

    func selectEvaluationHistory(jobID: String) {
        viewModel.selectEvaluationHistory(jobID: jobID)
    }

    func refreshDiagnosticsHistoryIfNeeded() async {
        if viewModel.benchmarkHistory.isEmpty && viewModel.benchmarkMatrixHistory.isEmpty && viewModel.evaluationHistory.isEmpty {
            switch Self.initialStage(for: viewModel) {
            case .benchmark:
                await viewModel.refreshBenchmarkHistory()
            case .matrix:
                viewModel.selectedBenchmarkPresentationMode = .matrix
                await viewModel.refreshBenchmarkHistory()
            case .evaluation:
                await viewModel.refreshEvaluationHistory()
            }
        }
    }

    private func startInspectTask() {
        Task { await inspectPrimaryModel() }
    }

    private func startDoctorTask() {
        Task { await runDoctor() }
    }

    private func startBenchmarkTask() {
        Task { await runBenchmark() }
    }

    private func startRefreshBenchmarkResultsTask() {
        Task { await refreshBenchmarkResults() }
    }

    private func startExportBenchmarkCSVTask() {
        Task { await exportBenchmarkCSV() }
    }

    private func startBenchmarkMatrixTask() {
        Task { await runBenchmarkMatrix() }
    }

    private func startRefreshBenchmarkMatrixResultsTask() {
        Task { await refreshBenchmarkMatrixResults() }
    }

    private func startExportBenchmarkMatrixSummaryCSVTask() {
        Task { await exportBenchmarkMatrixSummaryCSV() }
    }

    private func startExportBenchmarkMatrixRequestsCSVTask() {
        Task { await exportBenchmarkMatrixRequestsCSV() }
    }

    private func startEvaluationTask() {
        Task { await runEvaluation() }
    }

    private func startEvaluationCompareTask() {
        Task { await runEvaluationCompare() }
    }

    private func startRefreshEvaluationResultsTask() {
        Task { await refreshEvaluationResults() }
    }

    private func startExportEvaluationSummaryCSVTask() {
        Task { await exportEvaluationSummaryCSV() }
    }

    private func startExportEvaluationSamplesCSVTask() {
        Task { await exportEvaluationSamplesCSV() }
    }

    private func startExportEvaluationSamplesJSONLTask() {
        Task { await exportEvaluationSamplesJSONL() }
    }

    private func startRefreshToolingTask() {
        Task { await refreshTooling() }
    }

    private var benchmarkRunDisabled: Bool {
        viewModel.canRunDiagnosticsBenchmark == false
    }

    private var evaluationRunDisabled: Bool {
        viewModel.canRunDiagnosticsEvaluation == false
    }

    private func applyDiagnosticsStage(_ stage: DesktopDiagnosticsStage) {
        selectedStage = stage
        switch stage {
        case .benchmark:
            viewModel.preferredDiagnosticsStage = .benchmark
            viewModel.selectedBenchmarkPresentationMode = .standard
        case .matrix:
            viewModel.preferredDiagnosticsStage = .matrix
            viewModel.selectedBenchmarkPresentationMode = .matrix
        case .evaluation:
            viewModel.preferredDiagnosticsStage = .evaluation
            break
        }
    }

    private var benchmarkSnapshotEntry: RuntimeBenchmarkHistoryEntryState? {
        viewModel.selectedBenchmarkHistoryEntry ?? viewModel.benchmarkHistory.first
    }

    private var matrixSnapshotEntry: RuntimeBenchmarkMatrixHistoryEntryState? {
        viewModel.selectedBenchmarkMatrixHistoryEntry ?? viewModel.benchmarkMatrixHistory.first
    }

    private var evaluationSnapshotEntry: RuntimeEvaluationHistoryEntryState? {
        viewModel.selectedEvaluationHistoryEntry ?? viewModel.evaluationHistory.first
    }

    private var benchmarkSnapshotItems: [DesktopEditorialMetricItem] {
        Array(viewModel.benchmarkMetricCards.prefix(4)).map { metric in
            DesktopEditorialMetricItem(
                title: metric.metricLabel,
                value: metric.valueText,
                detail: metric.suiteTitle
            )
        }
    }

    private var matrixSnapshotItems: [DesktopEditorialMetricItem] {
        Array(viewModel.benchmarkMatrixSummaryCards.prefix(4)).map { card in
            DesktopEditorialMetricItem(
                title: card.title,
                value: card.valueText,
                detail: card.detail
            )
        }
    }

    private var evaluationSnapshotItems: [DesktopEditorialMetricItem] {
        Array(viewModel.evaluationMetricCards.prefix(4)).map { metric in
            DesktopEditorialMetricItem(
                title: metric.metricLabel,
                value: metric.valueText,
                detail: [metric.suiteTitle, metric.verdictText].filter { $0.isEmpty == false }.joined(separator: " • ")
            )
        }
    }

    private var diagnosticsSnapshotTitle: String {
        switch selectedStage {
        case .benchmark:
            return "Bench Report"
        case .matrix:
            return "Matrix Report"
        case .evaluation:
            return "Evaluation Report"
        }
    }

    @ViewBuilder
    private var diagnosticsSnapshotContent: some View {
        switch selectedStage {
        case .benchmark:
            benchmarkSnapshotContent
        case .matrix:
            matrixSnapshotContent
        case .evaluation:
            evaluationSnapshotContent
        }
    }

    @ViewBuilder
    private var benchmarkSnapshotContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let entry = benchmarkSnapshotEntry {
                DesktopPassiveHeadlineButton(
                    title: "Selected run \(entry.jobID) • \(entry.suiteTitle) • \(entry.createdAtText)"
                )
                Text(benchmarkSelectionSubtitle(for: entry))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                profileSummaryLabel(entry.profileSummaryText)
                memoryFitEvidenceLabel(entry.memoryFitSummaryText)
            }

            if benchmarkSnapshotItems.isEmpty {
                DesktopInlineEmptyStateView(
                    title: Self.emptyBenchmarkTitle,
                    detail: Self.emptyBenchmarkDetail,
                    symbolName: "gauge.with.dots.needle.67percent"
                )
            } else {
                snapshotMetricGrid(items: benchmarkSnapshotItems)
            }
        }
    }

    @ViewBuilder
    private var matrixSnapshotContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let entry = matrixSnapshotEntry {
                DesktopPassiveHeadlineButton(
                    title: "Selected matrix run \(entry.jobID) • \(entry.createdAtText)"
                )
                Text(matrixSelectionSubtitle(for: entry))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                profileSummaryLabel(entry.profileSummaryText)
            }

            if matrixSnapshotItems.isEmpty {
                DesktopInlineEmptyStateView(
                    title: Self.emptyBenchmarkTitle,
                    detail: Self.emptyBenchmarkDetail,
                    symbolName: "gauge.with.dots.needle.67percent"
                )
            } else {
                snapshotMetricGrid(items: matrixSnapshotItems)
            }
        }
    }

    @ViewBuilder
    private var evaluationSnapshotContent: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let entry = evaluationSnapshotEntry {
                DesktopPassiveHeadlineButton(
                    title: "Selected eval \(entry.jobID) • \(entry.suiteTitle) • \(entry.createdAtText)"
                )
                Text(evaluationSelectionSubtitle(for: entry))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                memoryFitEvidenceLabel(entry.memoryFitSummaryText)
            }

            if evaluationSnapshotItems.isEmpty {
                DesktopInlineEmptyStateView(
                    title: Self.emptyEvaluationTitle,
                    detail: Self.emptyEvaluationDetail,
                    symbolName: "checkmark.bubble"
                )
            } else {
                snapshotMetricGrid(items: evaluationSnapshotItems)
            }
        }
    }

    @ViewBuilder
    private func snapshotMetricGrid(items: [DesktopEditorialMetricItem]) -> some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 12)], spacing: 12) {
            ForEach(items) { item in
                DesktopEditorialMetricCardView(item: item)
            }
        }
    }

    private func benchmarkSelectionSubtitle(for entry: RuntimeBenchmarkHistoryEntryState) -> String {
        let selectedSource = entry.sourceRepo.isEmpty ? entry.modelID : entry.sourceRepo
        return [entry.taskTitle, selectedSource, entry.datasetLabel, entry.profileSummaryText]
            .filter { $0.isEmpty == false }
            .joined(separator: " • ")
    }

    private func matrixSelectionSubtitle(for entry: RuntimeBenchmarkMatrixHistoryEntryState) -> String {
        let selectedSource = entry.sourceRepo.isEmpty ? entry.modelID : entry.sourceRepo
        return [entry.taskTitle, selectedSource, entry.suiteSummary, entry.cellCountText, entry.profileSummaryText]
            .filter { $0.isEmpty == false }
            .joined(separator: " • ")
    }

    @ViewBuilder
    private func profileSummaryLabel(_ text: String) -> some View {
        if text.isEmpty == false {
            DesktopPassiveStaticTextLabel(
                title: text,
                font: .systemFont(ofSize: NSFont.smallSystemFontSize, weight: .semibold),
                textColor: .secondaryLabelColor
            )
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func evaluationSelectionSubtitle(for entry: RuntimeEvaluationHistoryEntryState) -> String {
        let selectedSource = entry.sourceRepo.isEmpty ? entry.modelID : entry.sourceRepo
        return [entry.taskTitle, selectedSource, entry.datasetID]
            .filter { $0.isEmpty == false }
            .joined(separator: " • ")
    }

    @ViewBuilder
    private func memoryFitEvidenceLabel(_ text: String) -> some View {
        if text.isEmpty == false {
            DesktopPassiveStaticTextLabel(
                title: "Memory fit: \(text)",
                font: .systemFont(ofSize: NSFont.smallSystemFontSize, weight: .semibold),
                textColor: .secondaryLabelColor
            )
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private var evidenceReportSections: some View {
        if let report = viewModel.evidenceReport {
            DesktopEditorialSectionCard("Run Evidence Report") {
                VStack(alignment: .leading, spacing: 12) {
                    evidenceReportControlRow(report: report)
                    evidenceReportStatusRows
                    DesktopPassiveHeadlineButton(
                        title: "\(report.reportKindText) • \(report.reportID)"
                    )
                    Text("\(report.generatedAtText) • \(report.identityText)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                    snapshotMetricGrid(
                        items: report.summaryItems.map {
                            DesktopEditorialMetricItem(
                                title: $0.title,
                                value: $0.value,
                                detail: $0.detail
                            )
                        }
                    )
                    evidenceReportFilterField
                    evidenceMetricRows(
                        report.metricRows(matching: evidenceReportFilter)
                            .prefix(EvidenceRowLimit.metrics)
                    )
                    evidenceGapRows(report)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            DesktopEditorialSectionCard("Run History") {
                VStack(alignment: .leading, spacing: 10) {
                    if report.runRows.isEmpty {
                        DesktopInlineEmptyStateView(
                            title: "No run evidence",
                            detail: "Structured report has no run rows.",
                            symbolName: "clock.badge.questionmark"
                        )
                    } else {
                        ForEach(report.runRows.prefix(EvidenceRowLimit.runs)) { row in
                            evidenceRunRow(row)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            DesktopEditorialSectionCard("Runtime Diagnostics") {
                VStack(alignment: .leading, spacing: 10) {
                    if report.probeRows.isEmpty {
                        DesktopInlineEmptyStateView(
                            title: "No probe timeline",
                            detail: "Structured report did not include probe phase summaries.",
                            symbolName: "waveform.path.ecg"
                        )
                    } else {
                        ForEach(report.probeRows.prefix(EvidenceRowLimit.probes)) { row in
                            evidenceProbeRow(row)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            DesktopEditorialSectionCard("Hardware Monitor") {
                VStack(alignment: .leading, spacing: 12) {
                    if report.telemetryRows.isEmpty {
                        DesktopInlineEmptyStateView(
                            title: "No Apple Silicon telemetry",
                            detail: "Structured report did not include hardware telemetry rows.",
                            symbolName: "cpu"
                        )
                    } else {
                        ForEach(report.telemetryRows.prefix(EvidenceRowLimit.telemetry)) { row in
                            evidenceTelemetryRow(row)
                        }
                    }

                    if report.processRows.isEmpty == false {
                        Divider()
                        Text("Process Attribution")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                        ForEach(report.processRows.prefix(EvidenceRowLimit.processes)) { row in
                            evidenceProcessRow(row)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            DesktopEditorialSectionCard("Evidence Artifacts") {
                VStack(alignment: .leading, spacing: 10) {
                    if report.artifactRows.isEmpty {
                        DesktopInlineEmptyStateView(
                            title: "No artifact paths",
                            detail: "Structured report did not include report, CSV, probe, or telemetry artifacts.",
                            symbolName: "doc.badge.questionmark"
                        )
                    } else {
                        ForEach(
                            report.artifactRows(matching: evidenceReportFilter)
                                .prefix(EvidenceRowLimit.artifacts)
                        ) { row in
                            evidenceArtifactRow(row)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        } else if viewModel.evidenceReportLoadError.isEmpty == false {
            DesktopEditorialSectionCard("Run Evidence Report") {
                VStack(alignment: .leading, spacing: 12) {
                    evidenceReportControlRow(report: nil)
                    evidenceReportStatusRows
                    DesktopInlineEmptyStateView(
                        title: "Evidence report failed to load",
                        detail: viewModel.evidenceReportLoadError,
                        symbolName: "exclamationmark.triangle"
                    )
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        } else {
            DesktopEditorialSectionCard("Run Evidence Report") {
                VStack(alignment: .leading, spacing: 12) {
                    evidenceReportControlRow(report: nil)
                    evidenceReportStatusRows
                    DesktopInlineEmptyStateView(
                        title: "No structured report loaded",
                        detail: "Load a report JSON artifact to inspect run evidence, probe phases, telemetry, and exports.",
                        symbolName: "doc.text.magnifyingglass"
                    )
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private var evidenceReportStatusRows: some View {
        VStack(alignment: .leading, spacing: 4) {
            if viewModel.evidenceReportSourcePath.isEmpty == false {
                Text(viewModel.evidenceReportSourcePath)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
            if viewModel.evidenceReportLoadError.isEmpty == false {
                Text(viewModel.evidenceReportLoadError)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
            if viewModel.evidenceReportOpenError.isEmpty == false {
                Text(viewModel.evidenceReportOpenError)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
        }
    }

    private var evidenceReportFilterField: some View {
        TextField("Filter report rows", text: $evidenceReportFilter)
            .textFieldStyle(.roundedBorder)
    }

    private func evidenceReportControlRow(report: RuntimeEvidenceReportState?) -> some View {
        HStack(spacing: 8) {
            Button(action: loadEvidenceReportFromPicker) {
                Label("Load Report JSON", systemImage: "doc.badge.plus")
            }
            Button(action: clearEvidenceReportSelection) {
                Label("Clear", systemImage: "xmark.circle")
            }
            .disabled(report == nil && viewModel.evidenceReportLoadError.isEmpty && viewModel.evidenceReportOpenError.isEmpty)

            if let markdownPath = report?.markdownReportPath {
                Button(action: { openEvidenceArtifact(path: markdownPath, opener: NSWorkspace.shared.open) }) {
                    Label("Open Markdown", systemImage: "doc.richtext")
                }
            }

            if let report, report.csvArtifactRows.isEmpty == false {
                Menu {
                    ForEach(report.csvArtifactRows) { row in
                        Button(row.kindText) {
                            openEvidenceArtifact(path: row.path, opener: NSWorkspace.shared.open)
                        }
                    }
                } label: {
                    Label("Open CSV", systemImage: "tablecells")
                }
            }
        }
    }

    private func loadEvidenceReportFromPicker() {
        guard let url = Self.selectEvidenceReportURL() else {
            return
        }
        Task {
            await loadEvidenceReport(from: url)
        }
    }

    @MainActor
    private static func selectEvidenceReportURL() -> URL? {
        let panel = NSOpenPanel()
        panel.title = "Load Evidence Report JSON"
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = false
        panel.allowedContentTypes = [.json]

        return panel.runModal() == .OK ? panel.url : nil
    }

    @MainActor
    private func loadEvidenceReport(from url: URL) async {
        do {
            try await viewModel.loadEvidenceReport(from: url)
            evidenceReportFilter = ""
        } catch {
            viewModel.recordEvidenceReportLoadError(error)
        }
    }

    private func clearEvidenceReportSelection() {
        evidenceReportFilter = ""
        viewModel.clearEvidenceReport()
    }

    func openEvidenceArtifact(path: String, opener: (URL) -> Bool) {
        let trimmedPath = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmedPath.isEmpty == false else {
            viewModel.recordEvidenceReportOpenError("Evidence artifact path is empty.")
            return
        }

        let opened = opener(URL(fileURLWithPath: trimmedPath))
        if opened {
            viewModel.clearEvidenceReportOpenError()
        } else {
            viewModel.recordEvidenceReportOpenError("Could not open evidence artifact at \(trimmedPath).")
        }
    }

    @ViewBuilder
    private func evidenceMetricRows(_ rows: ArraySlice<RuntimeEvidenceReportMetricRow>) -> some View {
        if rows.isEmpty == false {
            VStack(alignment: .leading, spacing: 8) {
                Text("Gate Metrics")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                ForEach(Array(rows)) { row in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text(row.metric)
                                .font(.headline)
                                .lineLimit(1)
                            Spacer()
                            Text(row.resultText)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
                        }
                        Text("\(row.statusText) • \(row.directionText) • \(row.deltaText)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(12)
                    .background(
                        Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                        in: RoundedRectangle(cornerRadius: 12)
                    )
                }
            }
        }
    }

    @ViewBuilder
    private func evidenceGapRows(_ report: RuntimeEvidenceReportState) -> some View {
        let gaps = Array((report.knownGapRows + report.instrumentationGapRows).prefix(EvidenceRowLimit.gaps))
        if gaps.isEmpty == false {
            VStack(alignment: .leading, spacing: 8) {
                Text("Instrumentation Gaps")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                ForEach(Array(gaps.enumerated()), id: \.offset) { _, gap in
                    Text(gap)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }
        }
    }

    private func evidenceRunRow(_ row: RuntimeEvidenceReportRunRow) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text("\(row.side) • \(row.runID)")
                    .font(.headline)
                Spacer()
                Text(row.statusText)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            Text("\(row.runKindText) • \(row.durationText) • \(row.targetText)")
                .font(.caption)
                .foregroundStyle(.secondary)
            if row.issueText.isEmpty == false {
                Text(row.issueText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if row.artifactRoot.isEmpty == false {
                Text(row.artifactRoot)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }

    private func evidenceProbeRow(_ row: RuntimeEvidenceReportProbeRow) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text("\(row.kind) • \(row.component) • \(row.phase)")
                    .font(.headline)
                Spacer()
                Text(row.durationText)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            Text("\(row.side) • \(row.runID) • \(row.statusText)")
                .font(.caption)
                .foregroundStyle(.secondary)
            if row.detailText.isEmpty == false {
                Text(row.detailText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }

    private func evidenceTelemetryRow(_ row: RuntimeEvidenceReportTelemetryRow) -> some View {
        VStack(alignment: .leading, spacing: 5) {
            HStack {
                Text("\(row.side) • \(row.runID)")
                    .font(.headline)
                Spacer()
                Text(row.collectorStatusText)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            Text(row.powerText)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text([row.utilizationText, row.memoryText].filter { $0.isEmpty == false }.joined(separator: " • "))
                .font(.caption)
                .foregroundStyle(.secondary)
            if row.failureText.isEmpty == false {
                Text(row.failureText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }

    private func evidenceProcessRow(_ row: RuntimeEvidenceReportProcessRow) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text("\(row.roleText) • \(row.nameText)")
                    .font(.headline)
                Spacer()
                Text(row.side)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            Text("\(row.runID) • \(row.pidText)")
                .font(.caption)
                .foregroundStyle(.secondary)
            if row.resourceText.isEmpty == false {
                Text(row.resourceText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }

    private func evidenceArtifactRow(_ row: RuntimeEvidenceReportArtifactRow) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(row.kindText)
                    .font(.headline)
                Spacer()
                Text(row.detailText)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }
            Text(row.path)
                .font(.caption)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            DesktopEditorialSectionCard("Diagnostics Actions") {
                VStack(alignment: .leading, spacing: 12) {
                    Picker(
                        "Diagnostics Stage",
                        selection: Binding(
                            get: { selectedStage },
                            set: { applyDiagnosticsStage($0) }
                        )
                    ) {
                        ForEach(DesktopDiagnosticsStage.allCases) { stage in
                            Text(stage.title).tag(stage)
                        }
                    }
                    .pickerStyle(.segmented)

                    HStack(spacing: 8) {
                        Button("Inspect", action: startInspectTask)
                        Button("Doctor", action: startDoctorTask)
                        switch selectedStage {
                        case .benchmark:
                            Button("Run Benchmark", action: startBenchmarkTask)
                                .disabled(benchmarkRunDisabled)
                        case .matrix:
                            Button("Run Matrix", action: startBenchmarkMatrixTask)
                                .disabled(benchmarkRunDisabled)
                        case .evaluation:
                            Button("Run Evaluation", action: startEvaluationTask)
                                .disabled(evaluationRunDisabled)
                            Button("Run Comparison", action: startEvaluationCompareTask)
                                .disabled(evaluationRunDisabled)
                        }

                        Menu {
                            switch selectedStage {
                            case .benchmark:
                                Button("Refresh Bench", action: startRefreshBenchmarkResultsTask)
                                Button("Export Bench CSV", action: startExportBenchmarkCSVTask)
                                    .disabled(viewModel.benchmarkHistory.isEmpty)
                            case .matrix:
                                Button("Refresh Matrix", action: startRefreshBenchmarkMatrixResultsTask)
                                Button("Export Matrix Summary", action: startExportBenchmarkMatrixSummaryCSVTask)
                                    .disabled(viewModel.benchmarkMatrixHistory.isEmpty)
                                Button("Export Matrix Requests", action: startExportBenchmarkMatrixRequestsCSVTask)
                                    .disabled(viewModel.benchmarkMatrixHistory.isEmpty)
                            case .evaluation:
                                Button("Refresh Eval", action: startRefreshEvaluationResultsTask)
                                Button("Export Eval Summary", action: startExportEvaluationSummaryCSVTask)
                                    .disabled(viewModel.evaluationHistory.isEmpty)
                                Button("Export Eval Samples", action: startExportEvaluationSamplesCSVTask)
                                    .disabled(viewModel.evaluationHistory.isEmpty)
                                Button("Export Eval JSONL", action: startExportEvaluationSamplesJSONLTask)
                                    .disabled(viewModel.evaluationHistory.isEmpty)
                            }
                            Button("Refresh Tooling", action: startRefreshToolingTask)
                        } label: {
                            Image(systemName: "ellipsis.circle")
                        }
                        .menuStyle(.borderlessButton)
                        .menuIndicator(.hidden)
                        .help("More Diagnostics Actions")
                        .accessibilityLabel("More Diagnostics Actions")
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            if let monitor = viewModel.diagnosticsRunMonitor {
                DesktopEditorialSectionCard("Run Monitor") {
                    DesktopDiagnosticsRunMonitorView(monitor: monitor)
                }
            }

            DesktopEditorialSectionCard(diagnosticsSnapshotTitle) {
                diagnosticsSnapshotContent
            }

            evidenceReportSections

            if selectedStage != .evaluation {
                DesktopEditorialSectionCard(selectedStage == .matrix ? "Matrix Configuration" : "Bench Configuration") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Running Server")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)

                        Picker(
                            "Running Server",
                            selection: Binding(
                                get: { viewModel.selectedDiagnosticsServerTargetID },
                                set: { viewModel.selectDiagnosticsServerTarget(id: $0) }
                            )
                        ) {
                            ForEach(viewModel.diagnosticsServerTargets) { target in
                                Text(target.title).tag(target.id)
                            }
                        }
                        .pickerStyle(.menu)

                        Text(viewModel.benchmarkTargetSummaryText)
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        if let disabledReason = viewModel.diagnosticsBenchmarkUnavailableText {
                            DesktopPassiveStaticTextLabel(
                                title: disabledReason,
                                font: .systemFont(ofSize: NSFont.smallSystemFontSize),
                                textColor: .secondaryLabelColor,
                                lineBreakMode: .byWordWrapping,
                                maximumNumberOfLines: 0
                            )
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .accessibilityLabel(disabledReason)
                        }

                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 12)], spacing: 12) {
                            ForEach(viewModel.benchmarkSuites) { suite in
                                Button {
                                    toggleBenchmarkSuiteSelection(suite.id)
                                } label: {
                                    VStack(alignment: .leading, spacing: 8) {
                                        HStack {
                                            Text(suite.title)
                                                .font(.headline)
                                            Spacer()
                                            Image(systemName: viewModel.selectedBenchmarkSuiteIDs.contains(suite.id) ? "checkmark.circle.fill" : "circle")
                                                .foregroundStyle(viewModel.selectedBenchmarkSuiteIDs.contains(suite.id) ? MelixDesignTokens.accent : .secondary)
                                        }
                                        Text("config \(suite.datasetName) • \(suite.defaultsText)")
                                            .font(.caption.weight(.semibold))
                                            .foregroundStyle(.secondary)
                                        Text(suite.datasetLabel)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(12)
                                    .background(
                                        viewModel.selectedBenchmarkSuiteIDs.contains(suite.id)
                                        ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                        : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                        in: RoundedRectangle(cornerRadius: 12)
                                    )
                                }
                                .buttonStyle(.plain)
                            }
                        }

                        Divider()

                        if viewModel.selectedBenchmarkPresentationMode == .standard {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Performance Controls")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Context Lengths")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], spacing: 8) {
                                    ForEach(RuntimeViewModel.benchmarkContextLengthOptions, id: \.self) { contextLength in
                                        Button {
                                            viewModel.toggleBenchContextLength(contextLength)
                                        } label: {
                                            Text("\(contextLength)")
                                                .font(.caption.weight(.semibold))
                                                .foregroundStyle(.primary)
                                                .frame(maxWidth: .infinity)
                                                .padding(.vertical, 6)
                                                .padding(.horizontal, 10)
                                                .background(
                                                    viewModel.selectedBenchContextLengths.contains(contextLength)
                                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                                    in: Capsule()
                                                )
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Batch Sizes")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], spacing: 8) {
                                    ForEach(RuntimeViewModel.benchmarkBatchSizeOptions, id: \.self) { batchSize in
                                        Button {
                                            viewModel.toggleBenchBatchSize(batchSize)
                                        } label: {
                                            Text("\(batchSize)")
                                                .font(.caption.weight(.semibold))
                                                .foregroundStyle(.primary)
                                                .frame(maxWidth: .infinity)
                                                .padding(.vertical, 6)
                                                .padding(.horizontal, 10)
                                                .background(
                                                    viewModel.selectedBenchBatchSizes.contains(batchSize)
                                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                                    in: Capsule()
                                                )
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }
                        }

                        HStack(spacing: 16) {
                            TextField(
                                "Sample Size",
                                text: Binding(
                                    get: { viewModel.benchmarkSampleSize },
                                    set: { viewModel.benchmarkSampleSize = $0 }
                                )
                            )
                            .textFieldStyle(.roundedBorder)
                            TextField(
                                "Batch Factor",
                                text: Binding(
                                    get: { viewModel.benchmarkBatchFactor },
                                    set: { viewModel.benchmarkBatchFactor = $0 }
                                )
                            )
                            .textFieldStyle(.roundedBorder)
                            TextField(
                                "Repeats",
                                text: Binding(
                                    get: { viewModel.benchRepeats },
                                    set: { viewModel.benchRepeats = $0 }
                                )
                            )
                            .textFieldStyle(.roundedBorder)
                        }

                        HStack(spacing: 16) {
                            Picker(
                                "Cache Profile",
                                selection: Binding(
                                    get: { viewModel.benchCacheProfile },
                                    set: { viewModel.benchCacheProfile = $0 }
                                )
                            ) {
                                ForEach(RuntimeViewModel.benchmarkCacheProfileOptions, id: \.self) { option in
                                    Text(option.replacingOccurrences(of: "_", with: " ").capitalized)
                                        .tag(option)
                                }
                            }
                            .pickerStyle(.menu)

                            Picker(
                                "Reasoning Mode",
                                selection: Binding(
                                    get: { viewModel.benchReasoningMode },
                                    set: { viewModel.benchReasoningMode = $0 }
                                )
                            ) {
                                ForEach(RuntimeViewModel.benchmarkReasoningModeOptions, id: \.self) { option in
                                    Text(option.replacingOccurrences(of: "_", with: " ").capitalized)
                                        .tag(option)
                                }
                            }
                            .pickerStyle(.menu)

                            Picker(
                                "Structured Output",
                                selection: Binding(
                                    get: { viewModel.benchStructuredOutputMode },
                                    set: { viewModel.benchStructuredOutputMode = $0 }
                                )
                            ) {
                                ForEach(RuntimeViewModel.benchmarkStructuredOutputModeOptions, id: \.self) { option in
                                    Text(option.replacingOccurrences(of: "_", with: " ").capitalized)
                                        .tag(option)
                                }
                            }
                            .pickerStyle(.menu)
                        }

                        if let export = viewModel.lastBenchmarkCSVExport {
                            Text("CSV exported: \(export.rowCount) rows • \(export.outputPath)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                        }
                    } else {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Matrix Controls")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Context Lengths")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], spacing: 8) {
                                    ForEach(RuntimeViewModel.benchmarkContextLengthOptions, id: \.self) { contextLength in
                                        Button {
                                            viewModel.toggleBenchContextLength(contextLength)
                                        } label: {
                                            Text("\(contextLength)")
                                                .font(.caption.weight(.semibold))
                                                .foregroundStyle(.primary)
                                                .frame(maxWidth: .infinity)
                                                .padding(.vertical, 6)
                                                .padding(.horizontal, 10)
                                                .background(
                                                    viewModel.selectedBenchContextLengths.contains(contextLength)
                                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                                    in: Capsule()
                                                )
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Generation Lengths")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], spacing: 8) {
                                    ForEach(RuntimeViewModel.benchmarkGenerationLengthOptions, id: \.self) { generationLength in
                                        Button {
                                            viewModel.toggleBenchGenerationLength(generationLength)
                                        } label: {
                                            Text("\(generationLength)")
                                                .font(.caption.weight(.semibold))
                                                .foregroundStyle(.primary)
                                                .frame(maxWidth: .infinity)
                                                .padding(.vertical, 6)
                                                .padding(.horizontal, 10)
                                                .background(
                                                    viewModel.selectedBenchGenerationLengths.contains(generationLength)
                                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                                    in: Capsule()
                                                )
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Batch Sizes")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], spacing: 8) {
                                    ForEach(RuntimeViewModel.benchmarkBatchSizeOptions, id: \.self) { batchSize in
                                        Button {
                                            viewModel.toggleBenchBatchSize(batchSize)
                                        } label: {
                                            Text("\(batchSize)")
                                                .font(.caption.weight(.semibold))
                                                .foregroundStyle(.primary)
                                                .frame(maxWidth: .infinity)
                                                .padding(.vertical, 6)
                                                .padding(.horizontal, 10)
                                                .background(
                                                    viewModel.selectedBenchBatchSizes.contains(batchSize)
                                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                                    in: Capsule()
                                                )
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Cache Profiles")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 110), spacing: 8)], spacing: 8) {
                                    ForEach(RuntimeViewModel.benchmarkCacheProfileOptions, id: \.self) { option in
                                        Button {
                                            viewModel.toggleBenchMatrixCacheProfile(option)
                                        } label: {
                                            Text(option.replacingOccurrences(of: "_", with: " ").capitalized)
                                                .font(.caption.weight(.semibold))
                                                .foregroundStyle(.primary)
                                                .frame(maxWidth: .infinity)
                                                .padding(.vertical, 6)
                                                .padding(.horizontal, 10)
                                                .background(
                                                    viewModel.selectedBenchMatrixCacheProfiles.contains(option)
                                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                                    in: Capsule()
                                                )
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Reasoning Modes")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), spacing: 8)], spacing: 8) {
                                    ForEach(RuntimeViewModel.benchmarkReasoningModeOptions, id: \.self) { option in
                                        Button {
                                            viewModel.toggleBenchMatrixReasoningMode(option)
                                        } label: {
                                            Text(option.replacingOccurrences(of: "_", with: " ").capitalized)
                                                .font(.caption.weight(.semibold))
                                                .foregroundStyle(.primary)
                                                .frame(maxWidth: .infinity)
                                                .padding(.vertical, 6)
                                                .padding(.horizontal, 10)
                                                .background(
                                                    viewModel.selectedBenchMatrixReasoningModes.contains(option)
                                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                                    in: Capsule()
                                                )
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Structured Output")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 120), spacing: 8)], spacing: 8) {
                                    ForEach(RuntimeViewModel.benchmarkStructuredOutputModeOptions, id: \.self) { option in
                                        Button {
                                            viewModel.toggleBenchMatrixStructuredOutputMode(option)
                                        } label: {
                                            Text(option.replacingOccurrences(of: "_", with: " ").capitalized)
                                                .font(.caption.weight(.semibold))
                                                .foregroundStyle(.primary)
                                                .frame(maxWidth: .infinity)
                                                .padding(.vertical, 6)
                                                .padding(.horizontal, 10)
                                                .background(
                                                    viewModel.selectedBenchMatrixStructuredOutputModes.contains(option)
                                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                                    in: Capsule()
                                                )
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Concurrency Levels")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                LazyVGrid(columns: [GridItem(.adaptive(minimum: 88), spacing: 8)], spacing: 8) {
                                    ForEach(RuntimeViewModel.benchmarkConcurrencyOptions, id: \.self) { option in
                                        Button {
                                            viewModel.toggleBenchMatrixConcurrencyLevel(option)
                                        } label: {
                                            Text("\(option)")
                                                .font(.caption.weight(.semibold))
                                                .foregroundStyle(.primary)
                                                .frame(maxWidth: .infinity)
                                                .padding(.vertical, 6)
                                                .padding(.horizontal, 10)
                                                .background(
                                                    viewModel.selectedBenchMatrixConcurrencyLevels.contains(option)
                                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                                    in: Capsule()
                                                )
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }
                        }

                        HStack(spacing: 16) {
                            TextField(
                                "Repeats",
                                text: Binding(
                                    get: { viewModel.benchMatrixRepeats },
                                    set: { viewModel.benchMatrixRepeats = $0 }
                                )
                            )
                            .textFieldStyle(.roundedBorder)

                            Picker(
                                "Load Budget",
                                selection: Binding(
                                    get: { viewModel.selectedBenchmarkMatrixLoadBudgetMode },
                                    set: { viewModel.selectedBenchmarkMatrixLoadBudgetMode = $0 }
                                )
                            ) {
                                ForEach(RuntimeBenchmarkMatrixLoadBudgetMode.allCases) { mode in
                                    Text(mode.title).tag(mode)
                                }
                            }
                            .pickerStyle(.segmented)

                            if viewModel.selectedBenchmarkMatrixLoadBudgetMode == .requests {
                                TextField(
                                    "Requests",
                                    text: Binding(
                                        get: { viewModel.benchMatrixRequests },
                                        set: { viewModel.benchMatrixRequests = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                            } else {
                                TextField(
                                    "Duration Seconds",
                                    text: Binding(
                                        get: { viewModel.benchMatrixDurationSeconds },
                                        set: { viewModel.benchMatrixDurationSeconds = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                            }
                        }

                        Toggle(
                            "Allow Large Matrix",
                            isOn: Binding(
                                get: { viewModel.benchMatrixAllowLargeMatrix },
                                set: { viewModel.benchMatrixAllowLargeMatrix = $0 }
                            )
                        )

                        Text("\(viewModel.benchmarkMatrixCellCountText) • \(viewModel.benchmarkMatrixLoadBudgetSummaryText)")
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        if let export = viewModel.lastBenchmarkMatrixExport {
                            Text("Matrix \(export.formatTitle) exported: \(export.rowCount) rows • \(export.outputPath)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            }

            if selectedStage != .evaluation {
                DesktopEditorialSectionCard(selectedStage == .matrix ? "Matrix Analysis" : "Bench Analysis") {
                VStack(alignment: .leading, spacing: 8) {
                    if viewModel.selectedBenchmarkPresentationMode == .standard {
                        if let selectedEntry = viewModel.selectedBenchmarkHistoryEntry {
                            Text("Selected run \(selectedEntry.jobID) • \(selectedEntry.suiteTitle) • \(selectedEntry.createdAtText)")
                                .font(.headline)
                            let selectedSource = selectedEntry.sourceRepo.isEmpty ? selectedEntry.modelID : selectedEntry.sourceRepo
                            Text("\(selectedEntry.taskTitle) • \(selectedSource) • \(selectedEntry.datasetLabel)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        if viewModel.benchmarkMetricOptions.isEmpty {
                            DesktopInlineEmptyStateView(
                                title: Self.emptyBenchmarkTitle,
                                detail: Self.emptyBenchmarkDetail,
                                symbolName: "gauge.with.dots.needle.67percent"
                            )
                        } else {
                            Picker(
                                "Metric",
                                selection: Binding(
                                    get: { viewModel.selectedBenchmarkMetricName },
                                    set: { viewModel.selectBenchmarkMetric($0) }
                                )
                            ) {
                                ForEach(viewModel.benchmarkMetricOptions, id: \.self) { metricName in
                                    Text(metricName).tag(metricName)
                                }
                            }
                            .pickerStyle(.menu)

                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 12)], spacing: 12) {
                                ForEach(viewModel.benchmarkMetricCards.prefix(6)) { metric in
                                    DesktopEditorialMetricCardView(
                                        item: DesktopEditorialMetricItem(
                                            title: metric.metricLabel,
                                            value: metric.valueText,
                                            detail: metric.suiteTitle
                                        )
                                    )
                                }
                            }

                            if viewModel.benchmarkChartPoints.isEmpty == false {
                                Chart(viewModel.benchmarkChartPoints) { point in
                                    AreaMark(
                                        x: .value("Run", point.createdAtLabel),
                                        y: .value("Value", point.value)
                                    )
                                    .interpolationMethod(.catmullRom)
                                    .foregroundStyle(
                                        MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.chartFillOpacity)
                                    )

                                    LineMark(
                                        x: .value("Run", point.createdAtLabel),
                                        y: .value("Value", point.value)
                                    )
                                    .interpolationMethod(.catmullRom)
                                    .lineStyle(StrokeStyle(lineWidth: 2))
                                    .foregroundStyle(MelixDesignTokens.accent)

                                    PointMark(
                                        x: .value("Run", point.createdAtLabel),
                                        y: .value("Value", point.value)
                                    )
                                    .symbolSize(28)
                                    .foregroundStyle(MelixDesignTokens.accent.opacity(0.9))
                                }
                                .frame(height: 240)
                                .chartLegend(.hidden)
                            }
                        }
                    } else {
                        if let selectedEntry = viewModel.selectedBenchmarkMatrixHistoryEntry {
                            Text("Selected matrix run \(selectedEntry.jobID) • \(selectedEntry.createdAtText)")
                                .font(.headline)
                            let selectedSource = selectedEntry.sourceRepo.isEmpty ? selectedEntry.modelID : selectedEntry.sourceRepo
                            Text("\(selectedEntry.taskTitle) • \(selectedSource) • \(selectedEntry.suiteSummary) • \(selectedEntry.cellCountText)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }

                        if viewModel.benchmarkMatrixSummaryRows.isEmpty {
                            DesktopInlineEmptyStateView(
                                title: Self.emptyBenchmarkTitle,
                                detail: Self.emptyBenchmarkDetail,
                                symbolName: "gauge.with.dots.needle.67percent"
                            )
                        } else {
                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 12)], spacing: 12) {
                                ForEach(viewModel.benchmarkMatrixSummaryCards) { card in
                                    DesktopEditorialMetricCardView(
                                        item: DesktopEditorialMetricItem(
                                            title: card.title,
                                            value: card.valueText,
                                            detail: card.detail
                                        )
                                    )
                                }
                            }

                            VStack(alignment: .leading, spacing: 8) {
                                Text("Summary Rows")
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(.secondary)
                                ForEach(viewModel.benchmarkMatrixSummaryRows.prefix(12)) { row in
                                    VStack(alignment: .leading, spacing: 4) {
                                        HStack {
                                            Text(row.suiteTitle)
                                                .font(.headline)
                                            Spacer()
                                            Text(row.createdAtText)
                                                .font(.caption)
                                                .foregroundStyle(.secondary)
                                        }
                                        Text(row.configurationSummary)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        Text("\(row.latencyText) • \(row.throughputText)")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        Text("\(row.successRateText) • \(row.peakMemoryText)")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(12)
                                    .background(
                                        Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                        in: RoundedRectangle(cornerRadius: 12)
                                    )
                                }
                            }

                            if viewModel.benchmarkMatrixContextChartPoints.isEmpty == false {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Context vs TTFT")
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(.secondary)
                                    Chart(viewModel.benchmarkMatrixContextChartPoints) { point in
                                        LineMark(
                                            x: .value("Context", point.xValue),
                                            y: .value("TTFT", point.yValue)
                                        )
                                        .interpolationMethod(.catmullRom)
                                        .lineStyle(StrokeStyle(lineWidth: 2))
                                        .foregroundStyle(MelixDesignTokens.accent)

                                        PointMark(
                                            x: .value("Context", point.xValue),
                                            y: .value("TTFT", point.yValue)
                                        )
                                        .symbolSize(24)
                                        .foregroundStyle(
                                            MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.chartFillOpacity + 0.5)
                                        )
                                    }
                                    .frame(height: 220)
                                    .chartLegend(.hidden)
                                }
                            }

                            if viewModel.benchmarkMatrixThroughputChartPoints.isEmpty == false {
                                VStack(alignment: .leading, spacing: 8) {
                                    Text("Batch / Concurrency Throughput")
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(.secondary)
                                    Chart(viewModel.benchmarkMatrixThroughputChartPoints) { point in
                                        BarMark(
                                            x: .value("Batch", point.xValue),
                                            y: .value("Throughput", point.yValue)
                                        )
                                        .foregroundStyle(
                                            MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.chartFillOpacity)
                                        )
                                    }
                                    .frame(height: 220)
                                    .chartLegend(.hidden)
                                }
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            }

            if selectedStage != .evaluation {
                DesktopEditorialSectionCard(selectedStage == .matrix ? "Matrix History" : "Bench History") {
                VStack(alignment: .leading, spacing: 10) {
                    if viewModel.selectedBenchmarkPresentationMode == .standard {
                        ForEach(viewModel.benchmarkHistory.prefix(12)) { entry in
                            Button {
                                selectBenchmarkHistory(jobID: entry.jobID)
                            } label: {
                                VStack(alignment: .leading, spacing: 6) {
                                    HStack {
                                        Text("\(entry.suiteTitle) • \(entry.jobID)")
                                            .font(.headline)
                                        Spacer()
                                        Text(entry.statusText)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    let sourceLabel = entry.sourceRepo.isEmpty ? entry.modelID : entry.sourceRepo
                                    Text("\(entry.taskTitle) • \(sourceLabel) • \(entry.datasetLabel)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text("sample \(entry.sampleSizeText) • batch \(entry.batchFactorText) • \(entry.metricCountText) • \(entry.createdAtText)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    if entry.reportPath.isEmpty == false {
                                        Text(entry.reportPath)
                                            .font(.caption2)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(12)
                                .background(
                                    viewModel.selectedBenchmarkHistoryJobID == entry.jobID
                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                    in: RoundedRectangle(cornerRadius: 12)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                        if viewModel.benchmarkHistory.isEmpty {
                            DesktopInlineEmptyStateView(
                                title: Self.emptyBenchmarkTitle,
                                detail: Self.emptyBenchmarkDetail,
                                symbolName: "gauge.with.dots.needle.67percent"
                            )
                        }
                    } else {
                        ForEach(viewModel.benchmarkMatrixHistory.prefix(12)) { entry in
                            Button {
                                selectBenchmarkMatrixHistory(jobID: entry.jobID)
                            } label: {
                                VStack(alignment: .leading, spacing: 6) {
                                    HStack {
                                        Text("\(entry.suiteSummary) • \(entry.jobID)")
                                            .font(.headline)
                                        Spacer()
                                        Text(entry.statusText)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    let sourceLabel = entry.sourceRepo.isEmpty ? entry.modelID : entry.sourceRepo
                                    Text("\(entry.taskTitle) • \(sourceLabel)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text("\(entry.cellCountText) • \(entry.loadBudgetText) • \(entry.createdAtText)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(12)
                                .background(
                                    viewModel.selectedBenchmarkMatrixHistoryJobID == entry.jobID
                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                    in: RoundedRectangle(cornerRadius: 12)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                        if viewModel.benchmarkMatrixHistory.isEmpty {
                            DesktopInlineEmptyStateView(
                                title: Self.emptyBenchmarkTitle,
                                detail: Self.emptyBenchmarkDetail,
                                symbolName: "gauge.with.dots.needle.67percent"
                            )
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            }

            if selectedStage == .evaluation {
                DesktopEditorialSectionCard("Evaluation Configuration") {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Running Server")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)

                        Picker(
                            "Running Server",
                            selection: Binding(
                                get: { viewModel.selectedDiagnosticsServerTargetID },
                                set: { viewModel.selectDiagnosticsServerTarget(id: $0) }
                            )
                        ) {
                            ForEach(viewModel.diagnosticsServerTargets) { target in
                                Text(target.title).tag(target.id)
                            }
                        }
                        .pickerStyle(.menu)

                        Text(viewModel.evaluationTargetSummaryText)
                            .font(.caption)
                            .foregroundStyle(.secondary)

                        if let disabledReason = viewModel.diagnosticsEvaluationUnavailableText {
                            DesktopPassiveStaticTextLabel(
                                title: disabledReason,
                                font: .systemFont(ofSize: NSFont.smallSystemFontSize),
                                textColor: .secondaryLabelColor,
                                lineBreakMode: .byWordWrapping,
                                maximumNumberOfLines: 0
                            )
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .accessibilityLabel(disabledReason)
                        }

                        Divider()

                        VStack(alignment: .leading, spacing: 10) {
                            Text("Evaluation Prompt")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)

                        Picker(
                            "Evaluation Prompt",
                            selection: Binding(
                                get: { viewModel.selectedEvaluationPromptID },
                                set: { viewModel.selectEvaluationPrompt(id: $0) }
                            )
                        ) {
                            ForEach(viewModel.evaluationPrompts, id: \.id) { prompt in
                                Text(prompt.title).tag(prompt.id)
                            }
                        }
                        .pickerStyle(.menu)

                        Text(viewModel.selectedEvaluationPromptSummaryText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)

                        HStack(spacing: 10) {
                            Button {
                                viewModel.prepareNewEvaluationPromptDraft()
                            } label: {
                                Label("New Prompt", systemImage: "plus")
                            }

                            Button {
                                viewModel.prepareEvaluationPromptDraftFromSelection()
                            } label: {
                                Label("Edit Draft", systemImage: "square.and.pencil")
                            }
                            .disabled(viewModel.selectedEvaluationPrompt?.readOnly ?? true)

                            Button {
                                viewModel.saveEvaluationPromptDraft()
                            } label: {
                                Label("Save Draft", systemImage: "tray.and.arrow.down")
                            }
                            .disabled(viewModel.isEvaluationPromptDraftEditable == false)

                            Button {
                                viewModel.freezeSelectedEvaluationPrompt()
                            } label: {
                                Label("Freeze Revision", systemImage: "snowflake")
                            }
                            .disabled(viewModel.canFreezeSelectedEvaluationPrompt == false)
                        }
                        .buttonStyle(.bordered)

                        HStack(spacing: 16) {
                            TextField(
                                "Prompt ID",
                                text: Binding(
                                    get: { viewModel.evaluationPromptIDDraft },
                                    set: { viewModel.evaluationPromptIDDraft = $0 }
                                )
                            )
                            .textFieldStyle(.roundedBorder)
                            .disabled(viewModel.isEvaluationPromptIDEditable == false)

                            TextField(
                                "Prompt Title",
                                text: Binding(
                                    get: { viewModel.evaluationPromptTitleDraft },
                                    set: { viewModel.evaluationPromptTitleDraft = $0 }
                                )
                            )
                            .textFieldStyle(.roundedBorder)
                            .disabled(
                                viewModel.isEvaluationPromptIDEditable == false
                                    || viewModel.isEvaluationPromptDraftEditable == false
                            )
                        }

                        TextEditor(
                            text: Binding(
                                get: { viewModel.evaluationPromptSystemPromptDraft },
                                set: { viewModel.evaluationPromptSystemPromptDraft = $0 }
                            )
                        )
                        .font(.system(.body, design: .monospaced))
                        .frame(minHeight: 140)
                        .padding(8)
                        .background(
                            Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                            in: RoundedRectangle(cornerRadius: 8)
                        )
                        .disabled(viewModel.isEvaluationPromptDraftEditable == false)
                    }

                    Divider()

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Semantic Judge")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)

                        Picker(
                            "Judge Remote Server",
                            selection: Binding(
                                get: { viewModel.selectedEvaluationSemanticJudgeRemoteServerID },
                                set: { viewModel.selectedEvaluationSemanticJudgeRemoteServerID = $0 }
                            )
                        ) {
                            Text("None").tag("")
                            ForEach(viewModel.remoteServers, id: \.id) { server in
                                Text(server.title.isEmpty ? server.id : "\(server.title) • \(server.id)")
                                    .tag(server.id)
                            }
                        }
                        .pickerStyle(.menu)

                        if viewModel.selectedEvaluationSemanticJudgeRemoteServerID.isEmpty == false {
                            TextField(
                                "Judge Model",
                                text: Binding(
                                    get: { viewModel.evaluationSemanticJudgeModelID },
                                    set: { viewModel.evaluationSemanticJudgeModelID = $0 }
                                )
                            )
                            .textFieldStyle(.roundedBorder)
                        }
                    }

                    Divider()

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Dataset Source")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)

                        Picker(
                            "Dataset Source",
                            selection: Binding(
                                get: { viewModel.evaluationDatasetSourceKind },
                                set: { viewModel.evaluationDatasetSourceKind = $0 }
                            )
                        ) {
                            ForEach(RuntimeEvaluationDatasetSourceKind.allCases) { sourceKind in
                                Text(sourceKind.title).tag(sourceKind)
                            }
                        }
                        .pickerStyle(.segmented)

                        switch viewModel.evaluationDatasetSourceKind {
                        case .builtinPackage:
                            Text("Use the checked-in evaluation package selected by each suite.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        case .localCSV, .localJSONL:
                            TextField(
                                "Local Source Path",
                                text: Binding(
                                    get: { viewModel.evaluationSourcePath },
                                    set: { viewModel.evaluationSourcePath = $0 }
                                )
                            )
                            .textFieldStyle(.roundedBorder)
                        case .huggingFaceDataset:
                            HStack(spacing: 16) {
                                TextField(
                                    "Dataset Path",
                                    text: Binding(
                                        get: { viewModel.evaluationHFDatasetPath },
                                        set: { viewModel.evaluationHFDatasetPath = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                                TextField(
                                    "Config",
                                    text: Binding(
                                        get: { viewModel.evaluationHFDatasetName },
                                        set: { viewModel.evaluationHFDatasetName = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                            }
                            HStack(spacing: 16) {
                                TextField(
                                    "Revision",
                                    text: Binding(
                                        get: { viewModel.evaluationHFDatasetRevision },
                                        set: { viewModel.evaluationHFDatasetRevision = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                                TextField(
                                    "Split",
                                    text: Binding(
                                        get: { viewModel.evaluationHFDatasetSplit },
                                        set: { viewModel.evaluationHFDatasetSplit = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                            }
                        }
                    }

                    if viewModel.evaluationDatasetSourceKind != .builtinPackage {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Field Mapping")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)

                            HStack(spacing: 16) {
                                TextField(
                                    "System Path",
                                    text: Binding(
                                        get: { viewModel.evaluationFieldSystemPath },
                                        set: { viewModel.evaluationFieldSystemPath = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                                TextField(
                                    "Input Text Path",
                                    text: Binding(
                                        get: { viewModel.evaluationFieldInputTextPath },
                                        set: { viewModel.evaluationFieldInputTextPath = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                            }

                            HStack(spacing: 16) {
                                TextField(
                                    "Target Path",
                                    text: Binding(
                                        get: { viewModel.evaluationFieldTargetPath },
                                        set: { viewModel.evaluationFieldTargetPath = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                                TextField(
                                    "Sample ID Path",
                                    text: Binding(
                                        get: { viewModel.evaluationFieldSampleIDPath },
                                        set: { viewModel.evaluationFieldSampleIDPath = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                            }

                            Text("Profile")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)

                            HStack(spacing: 16) {
                                TextField(
                                    "Result Kind",
                                    text: Binding(
                                        get: { viewModel.evaluationResultKind },
                                        set: { viewModel.evaluationResultKind = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                                TextField(
                                    "Extraction Mode",
                                    text: Binding(
                                        get: { viewModel.evaluationExtractionMode },
                                        set: { viewModel.evaluationExtractionMode = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                                TextField(
                                    "Threshold",
                                    text: Binding(
                                        get: { viewModel.evaluationThreshold },
                                        set: { viewModel.evaluationThreshold = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                            }

                            HStack(spacing: 16) {
                                TextField(
                                    "Output Schema JSON",
                                    text: Binding(
                                        get: { viewModel.evaluationOutputSchemaJSON },
                                        set: { viewModel.evaluationOutputSchemaJSON = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                                TextField(
                                    "Ignored Paths",
                                    text: Binding(
                                        get: { viewModel.evaluationIgnoredPaths },
                                        set: { viewModel.evaluationIgnoredPaths = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)
                            }
                        }
                    }

                    LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 12)], spacing: 12) {
                        ForEach(viewModel.evaluationSuites) { suite in
                            Button {
                                toggleEvaluationSuiteSelection(suite.id)
                            } label: {
                                VStack(alignment: .leading, spacing: 8) {
                                    HStack {
                                        Text(suite.title)
                                            .font(.headline)
                                        Spacer()
                                        Image(systemName: viewModel.selectedEvaluationSuiteIDs.contains(suite.id) ? "checkmark.circle.fill" : "circle")
                                            .foregroundStyle(viewModel.selectedEvaluationSuiteIDs.contains(suite.id) ? MelixDesignTokens.accent : .secondary)
                                    }
                                    Text("\(suite.scoreLabel) • \(suite.defaultsText)")
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(.secondary)
                                    Text(suite.datasetID)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(12)
                                .background(
                                    viewModel.selectedEvaluationSuiteIDs.contains(suite.id)
                                    ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                    : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                    in: RoundedRectangle(cornerRadius: 12)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    Divider()

                    VStack(alignment: .leading, spacing: 10) {
                        Text("Evaluation Mode")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)

                        Picker(
                            "Evaluation Mode",
                            selection: Binding(
                                get: { viewModel.selectedEvaluationMode },
                                set: { viewModel.selectedEvaluationMode = $0 }
                            )
                        ) {
                            ForEach(RuntimeEvaluationMode.allCases) { mode in
                                Text(mode.title).tag(mode)
                            }
                        }
                        .pickerStyle(.segmented)

                        Text("Compare Targets")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)

                        if viewModel.evaluationCompareTargetModels.isEmpty {
                            Text("No alternate catalog models are available for comparison.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        } else {
                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 8)], spacing: 8) {
                                ForEach(viewModel.evaluationCompareTargetModels, id: \.modelID) { model in
                                    let isSelected = viewModel.selectedEvaluationCompareTargetModelIDs.contains(model.modelID)
                                    Button {
                                        if isSelected {
                                            viewModel.selectedEvaluationCompareTargetModelIDs.remove(model.modelID)
                                        } else {
                                            viewModel.selectedEvaluationCompareTargetModelIDs.insert(model.modelID)
                                        }
                                    } label: {
                                        HStack {
                                            Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                                                .foregroundStyle(isSelected ? MelixDesignTokens.accent : .secondary)
                                            Text(model.displayNameWithID)
                                                .font(.caption)
                                                .foregroundStyle(.primary)
                                            Spacer()
                                        }
                                        .padding(.vertical, 6)
                                        .padding(.horizontal, 10)
                                        .background(
                                            isSelected
                                            ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                            : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                            in: RoundedRectangle(cornerRadius: 10)
                                        )
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }

                        Text("Evaluation Controls")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)

                    HStack(spacing: 16) {
                        TextField(
                            "Sample Size",
                            text: Binding(
                                get: { viewModel.evaluationSampleSize },
                                set: { viewModel.evaluationSampleSize = $0 }
                            )
                        )
                        .textFieldStyle(.roundedBorder)
                        TextField(
                            "Batch Factor",
                            text: Binding(
                                get: { viewModel.evaluationBatchFactor },
                                set: { viewModel.evaluationBatchFactor = $0 }
                            )
                        )
                        .textFieldStyle(.roundedBorder)
                        TextField(
                            "Few-shot",
                            text: Binding(
                                get: { viewModel.evaluationFewShot },
                                set: { viewModel.evaluationFewShot = $0 }
                            )
                        )
                        .textFieldStyle(.roundedBorder)
                        TextField(
                            "Seed",
                            text: Binding(
                                get: { viewModel.evaluationSeed },
                                set: { viewModel.evaluationSeed = $0 }
                            )
                        )
                        .textFieldStyle(.roundedBorder)
                    }

                        HStack(spacing: 16) {
                            TextField(
                                "Scoring Mode",
                                text: Binding(
                                    get: { viewModel.evaluationScoringMode },
                                    set: { viewModel.evaluationScoringMode = $0 }
                                )
                            )
                            .textFieldStyle(.roundedBorder)
                            TextField(
                                "Code Exec Policy",
                                text: Binding(
                                    get: { viewModel.evaluationCodeExecPolicy },
                                    set: { viewModel.evaluationCodeExecPolicy = $0 }
                                )
                            )
                            .textFieldStyle(.roundedBorder)
                        }
                    }

                    if let export = viewModel.lastEvaluationExport {
                        Text("Evaluation export (\(export.formatTitle)): \(export.rowCount) rows • \(export.outputPath)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            }

            if selectedStage == .evaluation {
                DesktopEditorialSectionCard("Evaluation Results") {
                VStack(alignment: .leading, spacing: 8) {
                    if let failure = viewModel.lastCLIWorkflowFailure,
                       failure.commandID.contains("eval") {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Evaluation Command Failed")
                                .font(.headline)
                                .foregroundStyle(MelixDesignTokens.StatusColor.error)
                                .textSelection(.enabled)
                            Text("\(failure.commandID) • \(failure.surface.rawValue) • \(failure.failureKind.rawValue)")
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                                .textSelection(.enabled)
                            Text(failure.detail)
                                .font(.caption)
                                .foregroundStyle(MelixDesignTokens.StatusColor.error)
                                .textSelection(.enabled)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(10)
                        .background(
                            MelixDesignTokens.StatusColor.error.opacity(0.08),
                            in: RoundedRectangle(cornerRadius: 8)
                        )
                    }

                    if let selectedEntry = viewModel.selectedEvaluationHistoryEntry {
                        Text("Selected eval \(selectedEntry.jobID) • \(selectedEntry.suiteTitle) • \(selectedEntry.createdAtText)")
                            .font(.headline)
                        let selectedSource = selectedEntry.sourceRepo.isEmpty ? selectedEntry.modelID : selectedEntry.sourceRepo
                        Text("\(selectedEntry.taskTitle) • \(selectedSource) • \(selectedEntry.datasetID)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    if viewModel.evaluationMetricCards.isEmpty {
                        DesktopInlineEmptyStateView(
                            title: Self.emptyEvaluationTitle,
                            detail: Self.emptyEvaluationDetail,
                            symbolName: "checkmark.bubble"
                        )
                    } else {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 12)], spacing: 12) {
                            ForEach(viewModel.evaluationMetricCards.prefix(8)) { metric in
                                DesktopEvaluationMetricCardView(metric: metric)
                            }
                        }

                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(viewModel.evaluationSamplePreview) { sample in
                                DesktopEvaluationSamplePreviewCardView(sample: sample)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            }

            if selectedStage == .evaluation {
                DesktopEditorialSectionCard("Evaluation History") {
                VStack(alignment: .leading, spacing: 10) {
                    ForEach(viewModel.evaluationHistory.prefix(12)) { entry in
                        Button {
                            selectEvaluationHistory(jobID: entry.jobID)
                        } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Text("\(entry.suiteTitle) • \(entry.jobID)")
                                        .font(.headline)
                                    Spacer()
                                    Text(entry.statusText)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                let sourceLabel = entry.sourceRepo.isEmpty ? entry.modelID : entry.sourceRepo
                                Text("\(entry.taskTitle) • \(sourceLabel) • \(entry.datasetID)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text("sample \(entry.sampleSizeText) • \(entry.scoringModeText) • \(entry.metricCountText) • \(entry.createdAtText)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                if entry.reportPath.isEmpty == false {
                                    Text(entry.reportPath)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(12)
                            .background(
                                viewModel.selectedEvaluationHistoryJobID == entry.jobID
                                ? MelixDesignTokens.accent.opacity(DesktopLoRAVisualPolish.selectedHistorySurfaceOpacity)
                                : Color.secondary.opacity(DesktopLoRAVisualPolish.sectionSurfaceOpacity),
                                in: RoundedRectangle(cornerRadius: 12)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                    if viewModel.evaluationHistory.isEmpty {
                        DesktopInlineEmptyStateView(
                            title: Self.emptyEvaluationTitle,
                            detail: Self.emptyEvaluationDetail,
                            symbolName: "checkmark.bubble"
                        )
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            }

            if let info = viewModel.selectedModelInfo {
                DesktopEditorialSectionCard("Model Info") {
                    DesktopModelInfoSummaryView(info: info)
                }
            }

            if let report = viewModel.lastDoctorReport {
                DesktopEditorialSectionCard("Doctor Report") {
                    DesktopDoctorReportSummaryView(report: report)
                }
            }

            DesktopEditorialSectionCard("Runtime Metrics Snapshot") {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(foundation.benchMetrics.prefix(10)) { metric in
                        HStack {
                            Text(metric.name)
                            Spacer()
                            Text(metric.value)
                                .monospacedDigit()
                                .foregroundStyle(.secondary)
                        }
                    }
                    if foundation.benchMetrics.isEmpty {
                        Text("No diagnostics yet.")
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .task(refreshDiagnosticsHistoryIfNeeded)
    }
}

struct DesktopAgentIntegrationExportsPanel: View {
    let exports: [AgentIntegrationExport]
    @Binding var selectedTarget: AgentIntegrationExportTarget

    var body: some View {
        MelixSectionCard("Agent Integrations") {
            VStack(alignment: .leading, spacing: 12) {
                if let export = selectedExport {
                    Picker(
                        "Target",
                        selection: $selectedTarget
                    ) {
                        ForEach(exports) { item in
                            Text(item.target.rawValue).tag(item.target)
                        }
                    }
                    .pickerStyle(.menu)

                    Text(export.instructions)
                        .foregroundStyle(.secondary)

                    HStack(spacing: 12) {
                        Label(export.baseURL, systemImage: "network")
                        Label(export.modelID, systemImage: "cube")
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)

                    DesktopCodeSnippetBlock(
                        title: export.target.configTitle,
                        body: export.configFragment,
                        copyAccessibilityLabel: "Copy Config",
                        accessibilityID: "agent.\(export.target.id).config"
                    )

                    DesktopCodeSnippetBlock(
                        title: "Shell Snippet",
                        body: export.shellSnippet,
                        copyAccessibilityLabel: "Copy Shell",
                        accessibilityID: "agent.\(export.target.id).shell"
                    )
                } else {
                    ContentUnavailableView(
                        "No Integration Export",
                        systemImage: "square.and.arrow.up.on.square",
                        description: Text("Start or select a server session to render reproducible agent integration exports.")
                    )
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private var selectedExport: AgentIntegrationExport? {
        exports.first(where: { $0.target == selectedTarget }) ?? exports.first
    }
}

private struct DesktopCodeSnippetBlock: View {
    let title: String
    let snippetText: String
    var copyAccessibilityLabel: String?
    var accessibilityID: String?

    init(
        title: String,
        body: String,
        copyAccessibilityLabel: String? = nil,
        accessibilityID: String? = nil
    ) {
        self.title = title
        self.snippetText = body
        self.copyAccessibilityLabel = copyAccessibilityLabel
        self.accessibilityID = accessibilityID
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 8) {
                Text(title).melixSectionLabel()
                Spacer()
                if let copyAccessibilityLabel {
                    Button(action: copyBody) {
                        Image(systemName: "doc.on.doc")
                    }
                    .buttonStyle(.borderless)
                    .help(copyAccessibilityLabel)
                    .accessibilityLabel(copyAccessibilityLabel)
                    .accessibilityIdentifier("desktop.code-snippet.copy.\(stableAccessibilityID)")
                }
            }
            Text(snippetText)
                .font(.caption.monospaced())
                .textSelection(.enabled)
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("desktop.code-snippet.\(stableAccessibilityID)")
    }

    private var stableAccessibilityID: String {
        let source = accessibilityID ?? title
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: ".-_"))
        return source.unicodeScalars.map { allowed.contains($0) ? String($0) : "-" }.joined()
    }

    private func copyBody() {
        copyToPasteboard(snippetText)
    }
}

struct DesktopBoundAgentIntegrationPanel: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        DesktopAgentIntegrationExportsPanel(
            exports: viewModel.agentIntegrationExports,
            selectedTarget: Binding(
                get: { viewModel.selectedAgentIntegrationTarget },
                set: { viewModel.selectAgentIntegrationTarget($0) }
            )
        )
    }
}

struct DesktopAgentIntegrationCopyButtons: View {
    let export: AgentIntegrationExport

    var body: some View {
        HStack {
            Button("Copy Config", action: copyConfig)
            Button("Copy Shell", action: copyShell)
        }
    }

    private func copyConfig() {
        copyToPasteboard(export.configFragment)
    }

    private func copyShell() {
        copyToPasteboard(export.shellSnippet)
    }
}

struct DesktopAPIAuthenticationReferenceView: View {
    let referenceText: String

    var body: some View {
        GroupBox("Auth") {
            Text(referenceText)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

struct DesktopAPIQuickStartSnippet: Identifiable {
    let id: String
    let language: String
    let title: String
    let body: String
}

struct DesktopAPIQuickStartGroup: Identifiable {
    let id: String
    let title: String
    let summary: String
    let statusText: String
    let note: String
    let snippets: [DesktopAPIQuickStartSnippet]
}

struct DesktopAPIQuickStartPanel: View {
    let foundation: DesktopFoundationState
    let selectedSession: DesktopServerSessionState?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Product Quick Starts").melixSectionLabel()
            if let selectedSession {
                let groups = desktopAPIQuickStartGroups(
                    foundation: foundation,
                    selectedSession: selectedSession
                )
                VStack(alignment: .leading, spacing: 16) {
                    Text("Examples use the effective listener URL \(selectedSession.effectiveBaseURL).")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    ForEach(groups) { group in
                        MelixSectionCard(group.title) {
                            VStack(alignment: .leading, spacing: 10) {
                                HStack {
                                    Text(group.summary)
                                        .foregroundStyle(.secondary)
                                    Spacer()
                                    Text(group.statusText)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                if group.note.isEmpty == false {
                                    Text(group.note)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                ForEach(group.snippets) { snippet in
                                    DesktopCodeSnippetBlock(
                                        title: snippet.title,
                                        body: snippet.body,
                                        copyAccessibilityLabel: "Copy \(snippet.title)",
                                        accessibilityID: "quick-start.\(group.id).\(snippet.id)"
                                    )
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    if groups.isEmpty {
                        Text("No product quick starts are published for the current API surfaces yet.")
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                ContentUnavailableView(
                    "No Server Session Selected",
                    systemImage: "network.slash",
                    description: Text("Start or select a server session to render session-aware quick-start snippets.")
                )
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
    }
}

func desktopAPIQuickStartGroups(
    foundation: DesktopFoundationState,
    selectedSession: DesktopServerSessionState
) -> [DesktopAPIQuickStartGroup] {
    let serviceBaseURL = selectedSession.effectiveBaseURL
    let serviceRootURL = serviceBaseURL.hasSuffix("/v1")
        ? String(serviceBaseURL.dropLast(3))
        : serviceBaseURL
    let authHeader = primaryGatewayHeader(for: selectedSession)
    let modelID = selectedSession.modelID
    let surfacesByID = Dictionary(uniqueKeysWithValues: foundation.apiSurfaces.map { ($0.id, $0) })

    func fetchHeaderBlock(extraHeaders: [(String, String)]) -> String {
        let headers = extraHeaders + (authHeader.map { [$0] } ?? [])
        return headers.map { "        \"\($0.0)\": \"\($0.1)\"," }.joined(separator: "\n") + "\n"
    }

    func pythonHeaderLiteral(extraHeaders: [(String, String)]) -> String {
        let headers = extraHeaders + (authHeader.map { [$0] } ?? [])
        guard headers.isEmpty == false else {
            return "{}"
        }

        return ([ "{"] + headers.map { "    \"\($0.0)\": \"\($0.1)\"," } + ["}"]).joined(separator: "\n")
    }

    func javascriptHeaderLiteral(extraHeaders: [(String, String)]) -> String {
        let headers = extraHeaders + (authHeader.map { [$0] } ?? [])
        guard headers.isEmpty == false else {
            return "{}"
        }

        return ([ "{"] + headers.map { "  \"\($0.0)\": \"\($0.1)\"," } + ["}"]).joined(separator: "\n")
    }

    let anthropicPythonHeaders = fetchHeaderBlock(
        extraHeaders: [
            ("anthropic-version", "2023-06-01"),
            ("content-type", "application/json"),
        ]
    )
    let anthropicJavaScriptHeaders = javascriptHeaderBlock(
        extraHeaders: [
            ("anthropic-version", "2023-06-01"),
            ("content-type", "application/json"),
        ],
        authHeader: authHeader
    )

    var groups: [DesktopAPIQuickStartGroup] = []

    if let surface = surfacesByID["openai_compatible"] {
        groups.append(
            DesktopAPIQuickStartGroup(
                id: surface.id,
                title: surface.title,
                summary: surface.summary,
                statusText: surface.statusText,
                note: "",
                snippets: [
                    DesktopAPIQuickStartSnippet(
                        id: "\(surface.id)-curl",
                        language: "curl",
                        title: "curl",
                        body: openAICurlQuickStart(
                            baseURL: serviceBaseURL,
                            modelID: modelID,
                            authHeader: authHeader
                        )
                    ),
                    DesktopAPIQuickStartSnippet(
                        id: "\(surface.id)-python",
                        language: "python",
                        title: "Python",
                        body: """
                        import requests

                        headers = \(pythonHeaderLiteral(extraHeaders: [("Content-Type", "application/json")]))
                        response = requests.post(
                            "\(serviceBaseURL)/responses",
                            headers=headers,
                            json={
                                "model": "\(modelID)",
                                "stream": True,
                                "input": "Hello from Melix"
                            },
                            timeout=30,
                            stream=True,
                        )
                        response.raise_for_status()
                        for line in response.iter_lines():
                            if line:
                                print(line.decode("utf-8"))
                        """
                    ),
                    DesktopAPIQuickStartSnippet(
                        id: "\(surface.id)-javascript",
                        language: "javascript",
                        title: "JavaScript",
                        body: """
                        const response = await fetch("\(serviceBaseURL)/responses", {
                          method: "POST",
                          headers: \(javascriptHeaderLiteral(extraHeaders: [("Content-Type", "application/json")])),
                          body: JSON.stringify({
                            model: "\(modelID)",
                            stream: true,
                            input: "Hello from Melix"
                          })
                        });

                        if (!response.ok || !response.body) {
                          throw new Error(`Melix request failed: ${response.status}`);
                        }

                        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
                        while (true) {
                          const { value, done } = await reader.read();
                          if (done) break;
                          process.stdout.write(value);
                        }
                        """
                    ),
                ]
            )
        )
    }

    if let surface = surfacesByID["anthropic_messages"] {
        groups.append(
            DesktopAPIQuickStartGroup(
                id: surface.id,
                title: surface.title,
                summary: surface.summary,
                statusText: surface.statusText,
                note: "",
                snippets: [
                    DesktopAPIQuickStartSnippet(
                        id: "\(surface.id)-curl",
                        language: "curl",
                        title: "curl",
                        body: anthropicCurlQuickStart(
                            baseURL: serviceBaseURL,
                            modelID: modelID,
                            authHeader: authHeader
                        )
                    ),
                    DesktopAPIQuickStartSnippet(
                        id: "\(surface.id)-python",
                        language: "python",
                        title: "Python",
                        body: [
                            "import requests",
                            "",
                            "headers = {",
                            anthropicPythonHeaders.trimmingCharacters(in: .newlines),
                            "}",
                            "",
                            "response = requests.post(",
                            "    \"\(serviceBaseURL)/messages\",",
                            "    headers=headers,",
                            "    json={",
                            "        \"model\": \"\(modelID)\",",
                            "        \"stream\": True,",
                            "        \"max_tokens\": 128,",
                            "        \"messages\": [{\"role\": \"user\", \"content\": \"Hello from Melix\"}]",
                            "    },",
                            "    timeout=30,",
                            "    stream=True,",
                            ")",
                            "",
                            "response.raise_for_status()",
                            "for line in response.iter_lines():",
                            "    if line:",
                            "        print(line.decode(\"utf-8\"))",
                        ].joined(separator: "\n")
                    ),
                    DesktopAPIQuickStartSnippet(
                        id: "\(surface.id)-javascript",
                        language: "javascript",
                        title: "JavaScript",
                        body: [
                            "const response = await fetch(\"\(serviceBaseURL)/messages\", {",
                            "  method: \"POST\",",
                            "  headers: {",
                            anthropicJavaScriptHeaders.trimmingCharacters(in: .newlines),
                            "  },",
                            "  body: JSON.stringify({",
                            "    model: \"\(modelID)\",",
                            "    stream: true,",
                            "    max_tokens: 128,",
                            "    messages: [{ role: \"user\", content: \"Hello from Melix\" }]",
                            "  })",
                            "});",
                            "",
                            "if (!response.ok || !response.body) {",
                            "  throw new Error(`Melix request failed: ${response.status}`);",
                            "}",
                            "",
                            "const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();",
                            "while (true) {",
                            "  const { value, done } = await reader.read();",
                            "  if (done) break;",
                            "  process.stdout.write(value);",
                            "}",
                        ].joined(separator: "\n")
                    ),
                ]
            )
        )
    }

    if let surface = surfacesByID["ollama_compatibility"] {
        let compatibilityLead = surface.compatibilityNote.isEmpty
            ? "Native Ollama /api/* routes are not shipped yet."
            : surface.compatibilityNote
        groups.append(
            DesktopAPIQuickStartGroup(
                id: surface.id,
                title: surface.title,
                summary: surface.summary,
                statusText: surface.statusText,
                note: compatibilityLead,
                snippets: [
                    DesktopAPIQuickStartSnippet(
                        id: "\(surface.id)-curl",
                        language: "curl",
                        title: "curl",
                        body: [
                            "# Use this bridge only with clients that can override their provider endpoint.",
                            healthCurlQuickStart(
                                baseURL: serviceRootURL,
                                authHeader: authHeader
                            ),
                            openAICurlQuickStart(
                                baseURL: serviceBaseURL,
                                modelID: modelID,
                                authHeader: authHeader
                            ),
                        ].joined(separator: "\n")
                    ),
                    DesktopAPIQuickStartSnippet(
                        id: "\(surface.id)-python",
                        language: "python",
                        title: "Python",
                        body: """
                        # Point your client at Melix through an OpenAI-compatible bridge.
                        import requests

                        health_headers = \(pythonHeaderLiteral(extraHeaders: []))
                        print(requests.get("\(serviceRootURL)/health", headers=health_headers, timeout=10).json())
                        print("Use \(serviceBaseURL) as the compatibility base URL for model \(modelID).")
                        """
                    ),
                    DesktopAPIQuickStartSnippet(
                        id: "\(surface.id)-javascript",
                        language: "javascript",
                        title: "JavaScript",
                        body: """
                        // Native Ollama /api/* routes are not available yet.
                        const health = await fetch("\(serviceRootURL)/health", {
                          headers: \(javascriptHeaderLiteral(extraHeaders: []))
                        });
                        console.log(await health.json());
                        console.log("Use \(serviceBaseURL) as the compatibility base URL for model \(modelID).");
                        """
                    ),
                ]
            )
        )
    }

    return groups
}

private func openAICurlQuickStart(
    baseURL: String,
    modelID: String,
    authHeader: (String, String)?
) -> String {
    var lines = ["curl -N -sS \(baseURL)/responses \\"]
    if let authHeader {
        lines.append("  -H \"\(authHeader.0): \(authHeader.1)\" \\")
    }
    lines.append("  -H \"Content-Type: application/json\" \\")
    lines.append("  -d '{\"model\":\"\(modelID)\",\"stream\":true,\"input\":\"Hello from Melix\"}'")
    return lines.joined(separator: "\n")
}

private func anthropicCurlQuickStart(
    baseURL: String,
    modelID: String,
    authHeader: (String, String)?
) -> String {
    var lines = ["curl -N -sS \(baseURL)/messages \\"]
    if let authHeader {
        lines.append("  -H \"\(authHeader.0): \(authHeader.1)\" \\")
    }
    lines.append("  -H \"anthropic-version: 2023-06-01\" \\")
    lines.append("  -H \"Content-Type: application/json\" \\")
    lines.append("  -d '{\"model\":\"\(modelID)\",\"stream\":true,\"max_tokens\":128,\"messages\":[{\"role\":\"user\",\"content\":\"Hello from Melix\"}]}'")
    return lines.joined(separator: "\n")
}

private func healthCurlQuickStart(
    baseURL: String,
    authHeader: (String, String)?
) -> String {
    var lines = ["curl -sS \(baseURL)/health \\"]
    if let authHeader {
        lines.append("  -H \"\(authHeader.0): \(authHeader.1)\"")
    } else {
        lines = ["curl -sS \(baseURL)/health"]
    }
    return lines.joined(separator: "\n")
}

private func javascriptHeaderBlock(
    extraHeaders: [(String, String)],
    authHeader: (String, String)?
) -> String {
    let headers = extraHeaders + (authHeader.map { [$0] } ?? [])
    return headers.map { "    \"\($0.0)\": \"\($0.1)\"," }.joined(separator: "\n") + "\n"
}

private func primaryGatewayHeader(
    for session: DesktopServerSessionState
) -> (String, String)? {
    switch session.sharedAccessState {
    case .localOnly:
        return session.authMode == .bearerToken
            ? ("Authorization", "Bearer \(session.integrationAuthValue)")
            : nil
    case .configuredDisabled:
        return nil
    case .enabled:
        switch session.authMode {
        case .none:
            return nil
        case .bearerToken:
            return ("Authorization", "Bearer \(session.integrationAuthValue)")
        case .apiKeys:
            return ("x-api-key", session.integrationAuthValue)
        }
    }
}

struct DesktopServerGatewayAccessSummaryView: View {
    let session: DesktopServerSessionState

    var body: some View {
        GroupBox("Gateway Access") {
            VStack(alignment: .leading, spacing: 8) {
                Text(session.sharedAccessSummaryText)
                    .font(.headline)
                Text("Effective auth: \(session.authMode.rawValue)")
                    .foregroundStyle(.secondary)
                Text(gatewayAccessHeaderText(session))
                    .foregroundStyle(.secondary)
                if session.accessKeyCount > 0 {
                    Text("Configured key hints (\(session.accessKeyCount)): \(session.accessKeyHintsText)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Text(session.persistentSessionSummaryText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                if session.lastAuthSessionSignOutLatencyMs > 0 {
                    Text("Last sign-out latency: \(String(format: "%.2f", session.lastAuthSessionSignOutLatencyMs)) ms")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

struct DesktopEvaluationMetricCardView: View {
    let metric: RuntimeEvaluationMetricCardState

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(metric.metricLabel)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(metric.valueText)
                .font(.headline)
                .monospacedDigit()
            Text(metric.suiteTitle)
                .font(.caption)
                .foregroundStyle(.secondary)
            ForEach(evidenceLines, id: \.self) { line in
                Text(line)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            Color.secondary.opacity(DesktopLoRAVisualPolish.metricSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }

    var evidenceLines: [String] {
        var lines: [String] = []
        if metric.verdictText.isEmpty == false {
            lines.append("Verdict: \(metric.verdictText)")
        }
        if metric.thresholdText.isEmpty == false {
            lines.append("Threshold: \(metric.thresholdText)")
        }
        if metric.bootstrapCIText.isEmpty == false {
            lines.append("Bootstrap CI: \(metric.bootstrapCIText)")
        }
        if metric.analyticalCIText.isEmpty == false {
            lines.append("Analytical CI: \(metric.analyticalCIText)")
        }
        return lines
    }
}

struct DesktopEvaluationSamplePreviewCardView: View {
    let sample: RuntimeEvaluationSamplePreviewState

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(sample.sampleID)
                    .font(.headline)
                Spacer()
                Text("Score \(sample.typedScoreText)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(sample.inputText)
                .font(.caption)
            Text("Target: \(sample.target)")
                .font(.caption)
                .foregroundStyle(.secondary)
            Text("Extracted: \(sample.extractedResult)")
                .font(.caption)
                .foregroundStyle(.secondary)
            if sample.rawResponse.isEmpty == false {
                Text("Raw: \(sample.rawResponse)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if let categoryAndSubjectText {
                Text(categoryAndSubjectText)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Text(statusLine)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(
            Color.secondary.opacity(DesktopLoRAVisualPolish.metricSurfaceOpacity),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }

    var categoryAndSubjectText: String? {
        let labels = [sample.categoryLabel, sample.subjectLabel].filter { $0.isEmpty == false }
        guard labels.isEmpty == false else {
            return nil
        }
        return labels.joined(separator: " • ")
    }

    var statusLine: String {
        sample.statusText.isEmpty ? sample.timeText : "\(sample.statusText) • \(sample.timeText)"
    }
}

struct DesktopAPISelectedExportCopyButton: View {
    let export: AgentIntegrationExport?

    var body: some View {
        Group {
            if let export {
                Button("Copy Selected Export", action: { copyToPasteboard(export.configFragment) })
            }
        }
    }
}

enum DesktopAPISection: String, CaseIterable, Identifiable {
    case overview = "Overview"
    case authentication = "Authentication"
    case quickStarts = "Quick Starts"
    case endpoints = "Endpoints"

    var id: String { rawValue }
}

struct DesktopAPIWorkspaceView: View {
    let viewModel: RuntimeViewModel
    let foundation: DesktopFoundationState
    @State private var selectedSection: DesktopAPISection
    @Binding var showsSidebar: Bool
    @Binding var showsInspector: Bool

    init(
        viewModel: RuntimeViewModel,
        foundation: DesktopFoundationState,
        initialSection: DesktopAPISection = .overview,
        showsSidebar: Binding<Bool>,
        showsInspector: Binding<Bool>
    ) {
        self.viewModel = viewModel
        self.foundation = foundation
        _selectedSection = State(initialValue: initialSection)
        _showsSidebar = showsSidebar
        _showsInspector = showsInspector
    }

    var body: some View {
        HStack(spacing: 0) {
            DesktopWorkspacePaneSlot(
                role: .sidebar,
                isVisible: showsSidebar,
                idealWidth: 240
            ) {
                VStack(alignment: .leading, spacing: 12) {
                    Text("API")
                        .font(.headline)
                    ForEach(DesktopAPISection.allCases) { section in
                        Button(section.rawValue) {
                            selectedSection = section
                        }
                        .buttonStyle(.plain)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 10)
                        .background(
                            selectedSection == section
                            ? MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.selected)
                            : Color.secondary.opacity(0.06),
                            in: RoundedRectangle(cornerRadius: 12)
                        )
                    }
                    Spacer()
                }
                .padding(20)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    DesktopWorkspaceHeader(title: "API") {}

                    switch selectedSection {
                    case .overview:
                        GroupBox("Base URL") {
                            Text(defaultBaseURL)
                                .font(.body.monospaced())
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    case .authentication:
                        DesktopAPIAuthenticationReferenceView(
                            referenceText: desktopAPIAuthenticationReferenceText(
                                selectedSession: viewModel.selectedServerSession,
                                selectedExport: viewModel.selectedAgentIntegrationExport
                            )
                        )
                    case .quickStarts:
                        VStack(alignment: .leading, spacing: 18) {
                            DesktopAPIQuickStartPanel(
                                foundation: foundation,
                                selectedSession: viewModel.selectedServerSession
                            )
                            DesktopBoundAgentIntegrationPanel(viewModel: viewModel)
                        }
                    case .endpoints:
                        DesktopAPIReferenceTabView(foundation: foundation)
                    }
                }
                .padding(20)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            DesktopWorkspacePaneSlot(
                role: .inspector,
                isVisible: showsInspector,
                idealWidth: 300
            ) {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Inspector")
                        .font(.headline)
                    GroupBox("Reference") {
                        VStack(alignment: .leading, spacing: 8) {
                            Text(defaultBaseURL)
                                .font(.caption.monospaced())
                            Button("Copy Base URL") {
                                copyToPasteboard(defaultBaseURL)
                            }
                            DesktopAPISelectedExportCopyButton(export: viewModel.selectedAgentIntegrationExport)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    GroupBox("Current Server") {
                        if let session = viewModel.selectedServerSession {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(session.title)
                                    .font(.headline)
                                Text(session.effectiveBaseURL)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(session.sharedAccessSummaryText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        } else {
                            Text("No server session selected.")
                                .foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                }
                .padding(20)
            }
        }
    }

    private var defaultBaseURL: String {
        viewModel.desktopRuntimeEndpointState.effectiveBaseURL
    }
}

func desktopAPIAuthenticationReferenceText(
    selectedSession: DesktopServerSessionState?,
    selectedExport: AgentIntegrationExport?
) -> String {
    guard let selectedSession else {
        return "Select a server session to render auth guidance."
    }

    let exportLead = if let selectedExport {
        "Selected target: \(selectedExport.target.rawValue). "
    } else {
        ""
    }

    switch selectedSession.sharedAccessState {
    case .localOnly:
        if selectedSession.authMode == .bearerToken {
            return "\(exportLead)Use Authorization: Bearer \(selectedSession.integrationAuthValue) for \(selectedSession.effectiveBaseURL)."
        }
        return "\(exportLead)Local trusted mode does not require authentication for \(selectedSession.effectiveBaseURL)."
    case .configuredDisabled:
        return "\(exportLead)Shared access is configured but disabled. Local trusted clients can call \(selectedSession.effectiveBaseURL) without auth. Prepared key hints: \(selectedSession.accessKeyHintsText)."
    case .enabled:
        return "\(exportLead)Shared access is enabled. Use x-api-key or Authorization: Bearer with \(selectedSession.integrationAuthValue) for \(selectedSession.effectiveBaseURL). Key hints: \(selectedSession.accessKeyHintsText)."
    }
}

private func gatewayAccessHeaderText(_ session: DesktopServerSessionState) -> String {
    switch session.sharedAccessState {
    case .localOnly:
        if session.authMode == .bearerToken {
            return "Header: Authorization: Bearer"
        }
        return "Header: not required"
    case .configuredDisabled:
        return "Header: not required until shared access is enabled"
    case .enabled:
        return "Headers: x-api-key or Authorization: Bearer"
    }
}

private func desktopAccelerationModeText(_ rawValue: String) -> String {
    switch rawValue {
    case "speculative_decode":
        return "Speculative Decode"
    case "accelerated_prefill":
        return "Accelerated Prefill"
    case "active_kv_quantized":
        return "Active KV Quantized"
    case "sparse_prefill":
        return "Sparse Prefill"
    case "baseline", "":
        return "None"
    default:
        return "None"
    }
}

private func servingAccelerationProfileLabel(_ rawValue: String) -> String {
    ServingAccelerationProfiles.profile(id: rawValue).label
}

func desktopAPIAuthenticationReferenceText(selectedExport: AgentIntegrationExport?) -> String {
    if let export = selectedExport {
        return "Selected target: \(export.target.rawValue). Use \(export.authPlaceholder) as the reproducible credential placeholder for \(export.baseURL)."
    }
    return "Select a server session to render auth guidance."
}

private func copyToPasteboard(_ value: String) {
    let pasteboard = NSPasteboard.general
    pasteboard.clearContents()
    pasteboard.setString(value, forType: .string)
}
