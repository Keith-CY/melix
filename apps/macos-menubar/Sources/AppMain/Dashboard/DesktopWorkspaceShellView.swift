import AppKit
import Charts
import SwiftUI

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
                    DesktopChatTabView(viewModel: viewModel)
                case .image:
                    DesktopImageTabView(viewModel: viewModel)
                case .server:
                    DesktopServerWorkspaceView(viewModel: viewModel)
                case .tools:
                    DesktopToolsWorkspaceView(viewModel: viewModel, foundation: foundation)
                case .api:
                    DesktopAPIWorkspaceView(viewModel: viewModel, foundation: foundation)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(Color(nsColor: .windowBackgroundColor))
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
            return Color.blue
        case .warning:
            return Color.orange
        case .critical:
            return Color.red
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
            return .blue
        case .warning:
            return .orange
        case .critical:
            return .red
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
            VStack(alignment: .leading, spacing: 20) {
                Text("Command Center")
                    .font(.largeTitle.weight(.semibold))

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 260), spacing: 12)], spacing: 12) {
                    GroupBox("Runtime Health") {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(foundation.serverStateText)
                                .font(.headline)
                            Text(foundation.connectionStateText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text(foundation.connectionDetailText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    GroupBox("Primary Model") {
                        VStack(alignment: .leading, spacing: 6) {
                            if let model = foundation.models.first {
                                Text(model.modelID)
                                    .font(.headline)
                                    .lineLimit(1)
                                Text("\(model.stateText) • \(model.memoryPolicyText)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(model.memoryText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                            } else {
                                Text("No model discovered.")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    if let viewModel, viewModel.recoverableDownloads.isEmpty == false {
                        GroupBox("Download Recovery") {
                            VStack(alignment: .leading, spacing: 8) {
                                ForEach(viewModel.recoverableDownloads.prefix(2)) { entry in
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(entry.sourceModel)
                                            .font(.headline)
                                            .lineLimit(1)
                                        Text(entry.progressText)
                                            .font(.caption.monospacedDigit())
                                            .foregroundStyle(.secondary)
                                        Button("Resume Download") {
                                            Task { await viewModel.resumeDownload(jobID: entry.jobID) }
                                        }
                                        .buttonStyle(.borderedProminent)
                                        .controlSize(.small)
                                    }
                                }
                                if let overflowText = Self.downloadRecoveryOverflowText(
                                    totalCount: viewModel.recoverableDownloads.count
                                ) {
                                    HStack {
                                        Text(overflowText)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        Spacer()
                                        Button(Self.downloadRecoveryOverflowActionTitle) {
                                            viewModel.selectSurface(.tools)
                                            viewModel.selectToolSection(.downloads)
                                        }
                                        .buttonStyle(.bordered)
                                        .controlSize(.small)
                                    }
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }

                    if let operation = viewModel?.lastModelOperation {
                        GroupBox("Last Operation") {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(operation.operation)
                                    .font(.headline)
                                Text(operation.modelID)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(operation.outputPath)
                                    .font(.caption2.monospaced())
                                    .foregroundStyle(.tertiary)
                                    .lineLimit(2)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }

                    if let lastError = viewModel?.lastError {
                        GroupBox("Latest Error") {
                            Text(lastError)
                                .foregroundStyle(.red)
                                .lineLimit(3)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }

                LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 12)], spacing: 12) {
                    ForEach(foundation.dashboardCards.filter { ["server", "connection", "backpressure", "memory"].contains($0.id) }) { card in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(card.title)
                                .font(.headline)
                            Text(card.value)
                                .font(.title3.weight(.semibold))
                            Text(card.detail)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 14))
                    }
                }

                HStack(alignment: .top, spacing: 16) {
                    GroupBox("Resource And Queue Pressure") {
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(foundation.queueLanes) { lane in
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack {
                                        Text(lane.id)
                                            .font(.headline)
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
                            if foundation.queueLanes.isEmpty {
                                Text("No active queue pressure.")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    GroupBox("Recovery Items") {
                        VStack(alignment: .leading, spacing: 10) {
                            ForEach(serverSessions.filter { $0.lifecycle == .error || $0.lifecycle == .stopped || $0.lifecycle == .unavailable }) { session in
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(session.title)
                                        .font(.headline)
                                    Text("\(session.lifecycle.rawValue) • \(session.baseURL)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    if !session.lastError.isEmpty {
                                        Text(session.lastError)
                                            .font(.caption)
                                            .foregroundStyle(.red)
                                    }
                                }
                            }
                            if serverSessions.contains(where: { $0.lifecycle == .error || $0.lifecycle == .stopped || $0.lifecycle == .unavailable }) == false {
                                Text("No recovery items.")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }

                GroupBox("Recent Activity") {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(foundation.logs.prefix(8)) { entry in
                            VStack(alignment: .leading, spacing: 2) {
                                HStack {
                                    Text(entry.kind)
                                        .font(.caption2)
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
                        }
                        if foundation.logs.isEmpty {
                            Text("No recent activity.")
                                .foregroundStyle(.secondary)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                GroupBox("Session Summary") {
                    HStack(alignment: .top, spacing: 24) {
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Chat Sessions")
                                .font(.headline)
                            Text("\(chatSessions.count)")
                                .font(.title3.weight(.semibold))
                            Text(chatSessions.first?.summaryText ?? "No chat sessions")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        VStack(alignment: .leading, spacing: 6) {
                            Text("Server Sessions")
                                .font(.headline)
                            Text("\(serverSessions.count)")
                                .font(.title3.weight(.semibold))
                            Text(serverSessions.first?.listenerLabel ?? "No listener configured")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(20)
        }
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

private struct DesktopServerWorkspaceView: View {
    let viewModel: RuntimeViewModel
    @State private var showsSidebar = true
    @State private var showsInspector = true
    @State private var showsAdvanced = DesktopServerWorkspaceDefaults.showsAdvancedServingDefaults

    var body: some View {
        HSplitView {
            if showsSidebar {
                DesktopServerSessionSidebar(viewModel: viewModel)
                    .frame(minWidth: 240, idealWidth: 260)
            }

            DesktopServerSessionEditor(
                viewModel: viewModel,
                showsSidebar: $showsSidebar,
                showsInspector: $showsInspector,
                showsAdvanced: $showsAdvanced
            )

            if showsInspector {
                DesktopServerSessionInspector(viewModel: viewModel)
                    .frame(minWidth: 280, idealWidth: 300)
            }
        }
    }
}

enum DesktopServerWorkspaceDefaults {
    static let showsAdvancedServingDefaults = false
    static let advancedServingDefaultsTitle = "Advanced Serving Defaults"
}

private struct DesktopServerSessionSidebar: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Server Sessions")
                    .font(.headline)
                Spacer()
                Button {
                    viewModel.createServerSession()
                } label: {
                    Image(systemName: "plus")
                }
                .buttonStyle(.plain)
                .help("New Server Session")
                .accessibilityLabel("New Server Session")
            }

            if viewModel.serverSessions.isEmpty {
                ContentUnavailableView(
                    "No Server Sessions",
                    systemImage: "network.slash",
                    description: Text("Create a server session to bind a model to a listener.")
                )
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(viewModel.serverSessions) { session in
                            Button {
                                viewModel.selectServerSession(id: session.id)
                            } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack {
                                        Text(session.title)
                                            .font(.headline)
                                        Spacer()
                                        Text(session.lifecycleSummaryText)
                                            .font(.caption)
                                            .foregroundStyle(session.isInteractiveReady ? .green : .secondary)
                                    }
                                    Text("\(session.modelID) • \(session.listenerLabel)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(12)
                                .background(
                                    viewModel.selectedServerSession?.id == session.id
                                    ? Color.accentColor.opacity(0.14)
                                    : Color.secondary.opacity(0.06),
                                    in: RoundedRectangle(cornerRadius: 12)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }

            Spacer()
        }
        .padding(20)
    }
}

private struct DesktopServerSessionEditor: View {
    let viewModel: RuntimeViewModel
    @Binding var showsSidebar: Bool
    @Binding var showsInspector: Bool
    @Binding var showsAdvanced: Bool

    private let servingAccelerationModeOptions = [
        ("Baseline", "baseline"),
        ("Speculative Decode", "speculative_decode"),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                DesktopWorkspaceHeader(
                    title: "Server",
                    subtitle: "Choose model, configure listener, then start the server session."
                ) {
                    DesktopPaneToggleButton(
                        role: .sidebar,
                        isVisible: showsSidebar,
                        shortcut: KeyboardShortcut("s", modifiers: [.command, .option])
                    ) {
                        showsSidebar.toggle()
                    }
                    DesktopPaneToggleButton(
                        role: .inspector,
                        isVisible: showsInspector,
                        shortcut: KeyboardShortcut("i", modifiers: [.command, .option])
                    ) {
                        showsInspector.toggle()
                    }
                }

                if let session = viewModel.selectedServerSession {
                    if let notice = session.lifecycleBannerState {
                        DesktopInlineNoticeCardView(notice: notice)
                    }

                    GroupBox("Basic Configuration") {
                        VStack(alignment: .leading, spacing: 12) {
                            Picker(
                                "Served Model",
                                selection: Binding(
                                    get: { session.modelID },
                                    set: { viewModel.updateSelectedServerSessionModelID($0) }
                                )
                            ) {
                                ForEach(viewModel.serveableModels, id: \.modelID) { model in
                                    Text(model.modelID).tag(model.modelID)
                                }
                            }

                            HStack {
                                TextField(
                                    "Host",
                                    text: Binding(
                                        get: { viewModel.selectedServerSession?.host ?? "127.0.0.1" },
                                        set: { viewModel.updateSelectedServerSessionHost($0) }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)

                                TextField(
                                    "Port",
                                    value: Binding(
                                        get: { viewModel.selectedServerSession?.port ?? 8080 },
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

                            HStack {
                                Button("Apply Gateway Config") {
                                    Task { await viewModel.applySelectedServerGatewayConfig() }
                                }
                                .buttonStyle(.bordered)

                                Text(
                                    session.gatewayConfigRequiresRestart
                                        ? "Requested listener differs from the active binding. Restart required."
                                        : "Listener config source: \(session.gatewayConfigSourceText)"
                                )
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    GroupBox {
                        VStack(alignment: .leading, spacing: 10) {
                            Text(servingDefaultsCompactSummary(for: session))
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            DisclosureGroup(DesktopServerWorkspaceDefaults.advancedServingDefaultsTitle, isExpanded: $showsAdvanced) {
                                advancedServingDefaultsForm(for: session)
                                    .padding(.top, 12)
                            }
                        }
                    }

                    GroupBox("Lifecycle Controls") {
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

                                Button("Pause") {
                                    Task { await viewModel.pauseSelectedServerSession() }
                                }
                                .buttonStyle(.bordered)
                                .disabled(session.canPause == false)

                                Button("Resume") {
                                    Task { await viewModel.resumeSelectedServerSession() }
                                }
                                .buttonStyle(.bordered)
                                .disabled(session.canResume == false)

                                Button("Wake") {
                                    Task { await viewModel.wakeSelectedServerSession() }
                                }
                                .buttonStyle(.bordered)
                                .disabled(session.canWake == false)

                                Button("Stop") {
                                    Task { await viewModel.stopSelectedServerSession() }
                                }
                                .buttonStyle(.bordered)
                                .disabled(session.canStop == false)
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

                                Button("Apply Idle Policy") {
                                    Task { await viewModel.applySelectedServerIdlePolicy() }
                                }
                                .buttonStyle(.bordered)
                            }

                            Text(session.idlePolicySummaryText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                } else {
                    ContentUnavailableView(
                        "No Server Session Selected",
                        systemImage: "server.rack",
                        description: Text("Choose a server session from the list or create a new one.")
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
                                    "Acceleration",
                                    selection: Binding(
                                        get: { viewModel.selectedServerSession?.servingDefaults.accelerationMode ?? "baseline" },
                                        set: { viewModel.updateSelectedServerSessionAccelerationMode($0) }
                                    )
                                ) {
                                    ForEach(servingAccelerationModeOptions, id: \.1) { option in
                                        Text(option.0).tag(option.1)
                                    }
                                }

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

                                HStack {
                                    Button("Apply Serving Defaults", action: viewModel.applySelectedServerServingDefaultsFromUI)
                                    .buttonStyle(.bordered)

                                    let servingDefaults = session.servingDefaults
                                    Text(
                                        "Source: \(servingDefaults.sourceText) • Effective temp \(servingDefaults.effectiveTemperature, format: .number.precision(.fractionLength(2))) • top_p \(servingDefaults.effectiveTopP, format: .number.precision(.fractionLength(2))) • max \(servingDefaults.effectiveMaxTokens) • stream \(servingDefaults.effectiveStreamIntervalTokens) • concurrent \(servingDefaults.effectiveConcurrentProcessingEnabled ? "on" : "off") • sequences \(servingDefaults.effectiveMaxConcurrentRequests) • prefill \(servingDefaults.effectivePrefillBatchSize) • completion \(servingDefaults.effectiveCompletionBatchSize) • accel \(servingDefaults.effectiveAccelerationMode)\(servingDefaults.effectiveDraftModelID.isEmpty ? "" : " • draft \(servingDefaults.effectiveDraftModelID)")\(servingDefaults.effectiveNumDraftTokens > 0 ? " • draft tokens \(servingDefaults.effectiveNumDraftTokens)" : "")\(servingDefaults.modelOverrideApplied ? " • model override applied" : "")"
                                    )
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                }
                            }
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
                            .foregroundStyle(.red)
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
    @State private var showsSidebar = true
    @State private var showsInspector = true

    var body: some View {
        HSplitView {
            if showsSidebar {
                DesktopToolsCategorySidebarView(
                    selectedToolSection: viewModel.selectedToolSection,
                    selectToolSection: viewModel.selectToolSection
                )
                .padding(20)
                .frame(minWidth: 240, idealWidth: 250)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    DesktopWorkspaceHeader(title: viewModel.selectedToolSection.rawValue) {
                        DesktopPaneToggleButton(
                            role: .sidebar,
                            isVisible: showsSidebar,
                            shortcut: KeyboardShortcut("s", modifiers: [.command, .option])
                        ) {
                            showsSidebar.toggle()
                        }
                        DesktopPaneToggleButton(
                            role: .inspector,
                            isVisible: showsInspector,
                            shortcut: KeyboardShortcut("i", modifiers: [.command, .option])
                        ) {
                            showsInspector.toggle()
                        }
                    }

                    switch viewModel.selectedToolSection {
                    case .modelsLibrary:
                        DesktopModelsTabView(foundation: foundation, viewModel: viewModel)
                    case .downloads:
                        DesktopDownloadsToolSectionView(viewModel: viewModel)
                    case .training:
                        DesktopTrainingToolSectionView(viewModel: viewModel)
                    case .diagnostics:
                        DesktopDiagnosticsToolSectionView(viewModel: viewModel, foundation: foundation)
                    case .logs:
                        DesktopLogsTabView(foundation: foundation)
                    case .settings:
                        DesktopSettingsTabView(foundation: foundation)
                    }
                }
                .padding(20)
            }

            if showsInspector {
                VStack(alignment: .leading, spacing: 16) {
                    Text("Inspector")
                        .font(.headline)

                    if let primaryModel = viewModel.primaryModel {
                        GroupBox("Primary Model") {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(primaryModel.modelID)
                                    .font(.headline)
                                Text(primaryModel.stateText)
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
                .frame(minWidth: 280, idealWidth: 300)
            }
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
                                    ? Color.accentColor.opacity(0.14)
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

            if viewModel.audioSetupActions.isEmpty == false {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(viewModel.audioSetupActions) { action in
                        DesktopAudioSetupNoticeRow(
                            action: action,
                            performAction: makeAudioSetupAction(for: action)
                        )
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            HStack {
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

            GroupBox("Download Queue") {
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
                                            .foregroundStyle(entry.resumeReady ? .orange : .secondary)
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
                GroupBox("Recent Transfer") {
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

    private func makeAudioSetupAction(for action: RuntimeAudioSetupActionState) -> () -> Void {
        { Task { await viewModel.performAudioSetupAction(action) } }
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

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Train adapters from a local package or a controlled Hugging Face dataset, then activate the saved adapter into a derived text model.")
                .foregroundStyle(.secondary)

            GroupBox("Training Configuration") {
                VStack(alignment: .leading, spacing: 12) {
                    Picker("Base Model", selection: stringBinding(\.selectedLoraModelID)) {
                        ForEach(viewModel.loraCapableModels, id: \.modelID) { model in
                            Text(model.modelID).tag(model.modelID)
                        }
                    }
                    .pickerStyle(.menu)

                    Picker("Dataset Source", selection: datasetSourceBinding()) {
                        ForEach(RuntimeLoraDatasetSourceKind.allCases) { source in
                            Text(source.title).tag(source)
                        }
                    }
                    .pickerStyle(.segmented)

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Training Mode")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                        Picker("Training Mode", selection: trainingModeBinding()) {
                            ForEach(RuntimeLoraTrainingMode.allCases) { mode in
                                Text(mode.title).tag(mode)
                            }
                        }
                        .pickerStyle(.segmented)
                    }

                    HStack(alignment: .top, spacing: 12) {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Preset")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
                            Picker("Preset", selection: trainingPresetBinding()) {
                                ForEach(RuntimeLoraTrainingPreset.allCases) { preset in
                                    Text(preset.title).tag(preset)
                                }
                            }
                            .pickerStyle(.menu)
                        }

                        VStack(alignment: .leading, spacing: 8) {
                            Text("Experiment Group")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
                            TextField("Optional group id", text: stringBinding(\.loraExperimentGroupID))
                                .textFieldStyle(.roundedBorder)
                            Text("Leave blank to derive from base model and adapter name.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }

                    if viewModel.loraDatasetSourceKind == .localPackage {
                        TextField("Dataset URI", text: stringBinding(\.loraDatasetURI))
                            .textFieldStyle(.roundedBorder)
                    } else {
                        VStack(alignment: .leading, spacing: 10) {
                            TextField("HF Dataset Path", text: stringBinding(\.loraHFDatasetPath))
                                .textFieldStyle(.roundedBorder)

                            HStack {
                                TextField("Config / Name", text: stringBinding(\.loraHFDatasetName))
                                    .textFieldStyle(.roundedBorder)
                                TextField("Revision", text: stringBinding(\.loraHFDatasetRevision))
                                    .textFieldStyle(.roundedBorder)
                            }

                            HStack {
                                TextField("Train Split", text: stringBinding(\.loraHFTrainSplit))
                                    .textFieldStyle(.roundedBorder)
                                TextField("Valid Split", text: stringBinding(\.loraHFValidSplit))
                                    .textFieldStyle(.roundedBorder)
                            }

                            HStack {
                                TextField("Text Feature", text: stringBinding(\.loraTextFeature))
                                    .textFieldStyle(.roundedBorder)
                                TextField("Prompt Feature", text: stringBinding(\.loraPromptFeature))
                                    .textFieldStyle(.roundedBorder)
                            }

                            HStack {
                                TextField("Completion Feature", text: stringBinding(\.loraCompletionFeature))
                                    .textFieldStyle(.roundedBorder)
                                TextField("Chat Feature", text: stringBinding(\.loraChatFeature))
                                    .textFieldStyle(.roundedBorder)
                            }
                        }
                    }

                    HStack {
                        TextField("Adapter Name", text: stringBinding(\.loraAdapterName))
                            .textFieldStyle(.roundedBorder)
                        TextField("Target Repo", text: stringBinding(\.loraTargetRepo))
                            .textFieldStyle(.roundedBorder)
                    }

                    VStack(alignment: .leading, spacing: 8) {
                        Text("Activation Mode")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                        Picker("Activation Mode", selection: activationModeBinding()) {
                            ForEach(RuntimeLoraActivationMode.allCases) { mode in
                                Text(mode.title).tag(mode)
                            }
                        }
                        .pickerStyle(.segmented)
                    }

                    DisclosureGroup(DesktopTrainingWorkspaceDefaults.advancedParametersTitle, isExpanded: $showsAdvanced) {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                TextField("Rank", text: stringBinding(\.loraRank))
                                    .textFieldStyle(.roundedBorder)
                                TextField("Alpha", text: stringBinding(\.loraAlpha))
                                    .textFieldStyle(.roundedBorder)
                                TextField("Dropout", text: stringBinding(\.loraDropout))
                                    .textFieldStyle(.roundedBorder)
                            }

                            HStack {
                                TextField("Batch Size", text: stringBinding(\.loraBatchSize))
                                    .textFieldStyle(.roundedBorder)
                                TextField("Epochs", text: stringBinding(\.loraEpochs))
                                    .textFieldStyle(.roundedBorder)
                                TextField("Learning Rate", text: stringBinding(\.loraLearningRate))
                                    .textFieldStyle(.roundedBorder)
                                TextField("Max Seq Length", text: stringBinding(\.loraMaxSeqLength))
                                    .textFieldStyle(.roundedBorder)
                            }

                            HStack {
                                TextField("Target Modules", text: stringBinding(\.loraTargetModules))
                                    .textFieldStyle(.roundedBorder)
                                TextField("Num Layers", text: stringBinding(\.loraNumLayers))
                                    .textFieldStyle(.roundedBorder)
                            }

                            TextField("Derived Model Alias", text: stringBinding(\.loraDerivedModelAlias))
                                .textFieldStyle(.roundedBorder)

                            HStack {
                                Toggle("Response Only", isOn: boolBinding(\.loraResponseOnly))
                                Toggle("Mask Prompt", isOn: boolBinding(\.loraMaskPrompt))
                                Toggle("Gradient Checkpointing", isOn: boolBinding(\.loraGradientCheckpointing))
                            }
                        }
                        .padding(.top, 8)
                    }

                    HStack {
                        Button("Train LoRA", action: startTrainLoRATask)
                        .buttonStyle(.borderedProminent)

                        Button("Activate Adapter", action: startActivateAdapterTask)
                        .buttonStyle(.bordered)
                        .disabled(viewModel.selectedAdapterPackage == nil)

                        Button("Remove Derived Model", action: startRemoveDerivedModelTask)
                            .buttonStyle(.bordered)
                            .disabled(
                                viewModel.selectedAdapterPackage?.derivedModelID.isEmpty ?? true
                            )

                        Button("Publish Adapter", action: startPublishAdapterTask)
                        .buttonStyle(.bordered)
                        .disabled(viewModel.selectedAdapterPackage == nil)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Adapter Activation") {
                VStack(alignment: .leading, spacing: 8) {
                    if viewModel.adapterPackages.isEmpty {
                        Text("No adapter packages yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        Picker("Selected Adapter", selection: stringBinding(\.selectedAdapterPackageID)) {
                            ForEach(viewModel.adapterPackages) { adapter in
                                Text("\(adapter.adapterName) • \(adapter.statusText)").tag(adapter.id)
                            }
                        }
                        .pickerStyle(.menu)

                        if let adapter = viewModel.selectedAdapterPackage {
                            Text("Saved artifact: \(adapter.outputPath)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Text("\(adapter.experimentSummaryText) • \(adapter.performanceSummaryText)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            if !adapter.derivedModelID.isEmpty {
                                Text("Derived model: \(adapter.derivedModelID)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            HStack {
                Text("Saved adapters and historical jobs come from the shared registry snapshot.")
                    .foregroundStyle(.secondary)
                Spacer()
            }

            GroupBox("Adapters") {
                VStack(alignment: .leading, spacing: 8) {
                    if viewModel.adapterPackages.isEmpty {
                        Text("No adapter packages yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(viewModel.adapterPackages) { adapter in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(adapter.adapterName)
                                    .font(.headline)
                                Text("\(adapter.statusText) • \(adapter.datasetURI)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(adapter.experimentSummaryText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(adapter.performanceSummaryText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Training Jobs") {
                VStack(alignment: .leading, spacing: 8) {
                    if viewModel.trainingHistory.isEmpty {
                        Text("No training history yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(viewModel.trainingHistory) { entry in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(entry.adapterName)
                                    .font(.headline)
                                Text("\(entry.statusText) • \(entry.datasetURI)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(entry.stageText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(entry.experimentSummaryText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                Text(entry.performanceSummaryText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Experiment Groups") {
                VStack(alignment: .leading, spacing: 10) {
                    if viewModel.loraExperimentGroups.isEmpty {
                        Text("No grouped LoRA runs yet.")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(viewModel.loraExperimentGroups) { group in
                            VStack(alignment: .leading, spacing: 4) {
                                HStack(alignment: .top) {
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
                                Text("Best loss \(String(format: "%.3f", group.bestLoss)) • \(group.recommendedManifestPath)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
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
                            .padding(.vertical, 4)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
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

struct DesktopDiagnosticsToolSectionView: View {
    let viewModel: RuntimeViewModel
    let foundation: DesktopFoundationState

    func inspectPrimaryModel() async {
        await viewModel.inspectPrimaryModel()
    }

    func runDoctor() async {
        await viewModel.runDoctor()
    }

    func runBenchmark() async {
        await viewModel.runBench()
    }

    func refreshBenchmarkResults() async {
        await viewModel.refreshBenchmarkHistory()
    }

    func exportBenchmarkCSV() async {
        await viewModel.exportSelectedBenchmarkCSV()
    }

    func runBenchmarkMatrix() async {
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
        await viewModel.runEvaluation()
    }

    func runEvaluationCompare() async {
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
            await viewModel.refreshBenchmarkHistory()
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

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            GroupBox("Diagnostics Actions") {
                VStack(alignment: .leading, spacing: 8) {
                    HStack {
                        Button("Inspect", action: startInspectTask)
                        Button("Doctor", action: startDoctorTask)
                        if viewModel.selectedBenchmarkPresentationMode == .standard {
                            Button("Run Benchmark", action: startBenchmarkTask)
                                .disabled(
                                    (
                                        viewModel.selectedBenchmarkTargetMode == .catalogModel
                                        && viewModel.benchmarkModels.isEmpty
                                    ) || viewModel.selectedBenchmarkSuiteIDs.isEmpty
                                )
                            Button("Refresh Bench", action: startRefreshBenchmarkResultsTask)
                            Button("Export Bench CSV", action: startExportBenchmarkCSVTask)
                                .disabled(viewModel.benchmarkHistory.isEmpty)
                        } else {
                            Button("Run Matrix", action: startBenchmarkMatrixTask)
                                .disabled(
                                    (
                                        viewModel.selectedBenchmarkTargetMode == .catalogModel
                                        && viewModel.benchmarkModels.isEmpty
                                    ) || viewModel.selectedBenchmarkSuiteIDs.isEmpty
                                )
                            Button("Refresh Matrix", action: startRefreshBenchmarkMatrixResultsTask)
                            Button("Export Matrix Summary", action: startExportBenchmarkMatrixSummaryCSVTask)
                                .disabled(viewModel.benchmarkMatrixHistory.isEmpty)
                            Button("Export Matrix Requests", action: startExportBenchmarkMatrixRequestsCSVTask)
                                .disabled(viewModel.benchmarkMatrixHistory.isEmpty)
                        }
                    }
                    HStack {
                        Button("Run Evaluation", action: startEvaluationTask)
                            .disabled(
                                (
                                    viewModel.selectedEvaluationTargetMode == .catalogModel
                                    && viewModel.evaluationModels.isEmpty
                                ) || viewModel.selectedEvaluationSuiteIDs.isEmpty
                            )
                        Button("Run Comparison", action: startEvaluationCompareTask)
                            .disabled(
                                (
                                    viewModel.selectedEvaluationTargetMode == .catalogModel
                                    && viewModel.evaluationModels.isEmpty
                                ) || viewModel.selectedEvaluationSuiteIDs.isEmpty
                            )
                        Button("Refresh Eval", action: startRefreshEvaluationResultsTask)
                        Button("Export Eval Summary", action: startExportEvaluationSummaryCSVTask)
                            .disabled(viewModel.evaluationHistory.isEmpty)
                        Button("Export Eval Samples", action: startExportEvaluationSamplesCSVTask)
                            .disabled(viewModel.evaluationHistory.isEmpty)
                        Button("Export Eval JSONL", action: startExportEvaluationSamplesJSONLTask)
                            .disabled(viewModel.evaluationHistory.isEmpty)
                        Button("Refresh Tooling", action: startRefreshToolingTask)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            if let info = viewModel.selectedModelInfo {
                GroupBox("Model Info") {
                    DesktopModelInfoSummaryView(info: info)
                }
            }

            GroupBox("Benchmark Configuration") {
                VStack(alignment: .leading, spacing: 12) {
                    Picker(
                        "Benchmark Mode",
                        selection: Binding(
                            get: { viewModel.selectedBenchmarkPresentationMode },
                            set: { viewModel.selectedBenchmarkPresentationMode = $0 }
                        )
                    ) {
                        ForEach(RuntimeBenchmarkPresentationMode.allCases) { mode in
                            Text(mode.title).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)

                    Picker(
                        "Benchmark Target",
                        selection: Binding(
                            get: { viewModel.selectedBenchmarkTargetMode },
                            set: { viewModel.selectedBenchmarkTargetMode = $0 }
                        )
                    ) {
                        ForEach(RuntimeBenchmarkTargetMode.allCases) { mode in
                            Text(mode.title).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)

                    if viewModel.selectedBenchmarkTargetMode == .catalogModel {
                        if viewModel.benchmarkModels.isEmpty {
                            Text("No benchmark-capable catalog models are available.")
                                .foregroundStyle(.secondary)
                        } else {
                            Picker(
                                "Benchmark Model",
                                selection: Binding(
                                    get: { viewModel.selectedBenchmarkModelID },
                                    set: { viewModel.selectedBenchmarkModelID = $0 }
                                )
                            ) {
                                ForEach(viewModel.benchmarkModels) { model in
                                    Text(model.alias.isEmpty ? model.modelID : "\(model.alias) • \(model.modelID)")
                                        .tag(model.modelID)
                                }
                            }
                            .pickerStyle(.menu)
                        }
                    } else {
                        TextField(
                            "Hugging Face Repo ID",
                            text: Binding(
                                get: { viewModel.benchmarkHFRepoID },
                                set: { viewModel.benchmarkHFRepoID = $0 }
                            )
                        )
                        .textFieldStyle(.roundedBorder)
                    }

                    Text(viewModel.benchmarkTargetSummaryText)
                        .font(.caption)
                        .foregroundStyle(.secondary)

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
                                            .foregroundStyle(viewModel.selectedBenchmarkSuiteIDs.contains(suite.id) ? Color.accentColor : .secondary)
                                    }
                                    Text(suite.datasetLabel)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text("config \(suite.datasetName) • \(suite.defaultsText)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(12)
                                .background(
                                    viewModel.selectedBenchmarkSuiteIDs.contains(suite.id)
                                    ? Color.accentColor.opacity(0.12)
                                    : Color.secondary.opacity(0.06),
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
                                                    ? Color.accentColor.opacity(0.16)
                                                    : Color.secondary.opacity(0.08),
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
                                                    ? Color.accentColor.opacity(0.16)
                                                    : Color.secondary.opacity(0.08),
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
                                                    ? Color.accentColor.opacity(0.16)
                                                    : Color.secondary.opacity(0.08),
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
                                                    ? Color.accentColor.opacity(0.16)
                                                    : Color.secondary.opacity(0.08),
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
                                                    ? Color.accentColor.opacity(0.16)
                                                    : Color.secondary.opacity(0.08),
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
                                                    ? Color.accentColor.opacity(0.16)
                                                    : Color.secondary.opacity(0.08),
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
                                                    ? Color.accentColor.opacity(0.16)
                                                    : Color.secondary.opacity(0.08),
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
                                                    ? Color.accentColor.opacity(0.16)
                                                    : Color.secondary.opacity(0.08),
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
                                                    ? Color.accentColor.opacity(0.16)
                                                    : Color.secondary.opacity(0.08),
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

            if let report = viewModel.lastDoctorReport {
                GroupBox("Doctor Report") {
                    DesktopDoctorReportSummaryView(report: report)
                }
            }

            GroupBox("Benchmark Results") {
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
                            Text("Run a benchmark or refresh persisted results to visualize history.")
                                .foregroundStyle(.secondary)
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
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(12)
                                    .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
                                }
                            }

                            if viewModel.benchmarkChartPoints.isEmpty == false {
                                Chart(viewModel.benchmarkChartPoints) { point in
                                    BarMark(
                                        x: .value("Run", point.createdAtLabel),
                                        y: .value("Value", point.value)
                                    )
                                    .foregroundStyle(by: .value("Suite", point.suiteTitle))
                                }
                                .frame(height: 240)
                                .chartLegend(position: .bottom)
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
                            Text("Run a matrix benchmark or refresh persisted results to inspect matrix summaries.")
                                .foregroundStyle(.secondary)
                        } else {
                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 180), spacing: 12)], spacing: 12) {
                                ForEach(viewModel.benchmarkMatrixSummaryCards) { card in
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text(card.title)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                        Text(card.valueText)
                                            .font(.headline)
                                            .monospacedDigit()
                                        Text(card.detail)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    .frame(maxWidth: .infinity, alignment: .leading)
                                    .padding(12)
                                    .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
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
                                    .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
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
                                        .foregroundStyle(by: .value("Series", point.seriesTitle))
                                    }
                                    .frame(height: 220)
                                    .chartLegend(position: .bottom)
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
                                        .foregroundStyle(by: .value("Series", point.seriesTitle))
                                    }
                                    .frame(height: 220)
                                    .chartLegend(position: .bottom)
                                }
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Benchmark History") {
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
                                    ? Color.accentColor.opacity(0.12)
                                    : Color.secondary.opacity(0.06),
                                    in: RoundedRectangle(cornerRadius: 12)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                        if viewModel.benchmarkHistory.isEmpty {
                            Text("No persisted benchmark history yet.")
                                .foregroundStyle(.secondary)
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
                                    ? Color.accentColor.opacity(0.12)
                                    : Color.secondary.opacity(0.06),
                                    in: RoundedRectangle(cornerRadius: 12)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                        if viewModel.benchmarkMatrixHistory.isEmpty {
                            Text("No persisted benchmark matrix history yet.")
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Evaluation Configuration") {
                VStack(alignment: .leading, spacing: 12) {
                    Picker(
                        "Evaluation Target",
                        selection: Binding(
                            get: { viewModel.selectedEvaluationTargetMode },
                            set: { viewModel.selectedEvaluationTargetMode = $0 }
                        )
                    ) {
                        ForEach(RuntimeBenchmarkTargetMode.allCases) { mode in
                            Text(mode.title).tag(mode)
                        }
                    }
                    .pickerStyle(.segmented)

                    if viewModel.selectedEvaluationTargetMode == .catalogModel {
                        if viewModel.evaluationModels.isEmpty {
                            Text("No text-generation catalog models are available.")
                                .foregroundStyle(.secondary)
                        } else {
                            Picker(
                                "Evaluation Model",
                                selection: Binding(
                                    get: { viewModel.selectedEvaluationModelID },
                                    set: { viewModel.selectedEvaluationModelID = $0 }
                                )
                            ) {
                                ForEach(viewModel.evaluationModels) { model in
                                    Text(model.alias.isEmpty ? model.modelID : "\(model.alias) • \(model.modelID)")
                                        .tag(model.modelID)
                                }
                            }
                            .pickerStyle(.menu)
                        }
                    } else {
                        TextField(
                            "Hugging Face Repo ID",
                            text: Binding(
                                get: { viewModel.evaluationHFRepoID },
                                set: { viewModel.evaluationHFRepoID = $0 }
                            )
                        )
                        .textFieldStyle(.roundedBorder)
                    }

                    Text(viewModel.evaluationTargetSummaryText)
                        .font(.caption)
                        .foregroundStyle(.secondary)

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
                                            .foregroundStyle(viewModel.selectedEvaluationSuiteIDs.contains(suite.id) ? Color.accentColor : .secondary)
                                    }
                                    Text(suite.datasetID)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                    Text("\(suite.scoreLabel) • \(suite.defaultsText)")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(12)
                                .background(
                                    viewModel.selectedEvaluationSuiteIDs.contains(suite.id)
                                    ? Color.accentColor.opacity(0.12)
                                    : Color.secondary.opacity(0.06),
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
                                                .foregroundStyle(isSelected ? Color.accentColor : .secondary)
                                            Text(model.alias.isEmpty ? model.modelID : "\(model.alias) • \(model.modelID)")
                                                .font(.caption)
                                                .foregroundStyle(.primary)
                                            Spacer()
                                        }
                                        .padding(.vertical, 6)
                                        .padding(.horizontal, 10)
                                        .background(
                                            isSelected
                                            ? Color.accentColor.opacity(0.12)
                                            : Color.secondary.opacity(0.06),
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

            GroupBox("Evaluation Results") {
                VStack(alignment: .leading, spacing: 8) {
                    if let selectedEntry = viewModel.selectedEvaluationHistoryEntry {
                        Text("Selected eval \(selectedEntry.jobID) • \(selectedEntry.suiteTitle) • \(selectedEntry.createdAtText)")
                            .font(.headline)
                        let selectedSource = selectedEntry.sourceRepo.isEmpty ? selectedEntry.modelID : selectedEntry.sourceRepo
                        Text("\(selectedEntry.taskTitle) • \(selectedSource) • \(selectedEntry.datasetID)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    if viewModel.evaluationMetricCards.isEmpty {
                        Text("Run an evaluation or refresh persisted results to inspect scores and samples.")
                            .foregroundStyle(.secondary)
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

            GroupBox("Evaluation History") {
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
                                ? Color.accentColor.opacity(0.12)
                                : Color.secondary.opacity(0.06),
                                in: RoundedRectangle(cornerRadius: 12)
                            )
                        }
                        .buttonStyle(.plain)
                    }
                    if viewModel.evaluationHistory.isEmpty {
                        Text("No persisted evaluation history yet.")
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Runtime Metrics Snapshot") {
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
        GroupBox("Agent Integrations") {
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

                    GroupBox(export.target.configTitle) {
                        Text(export.configFragment)
                            .font(.caption.monospaced())
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    GroupBox("Shell Snippet") {
                        Text(export.shellSnippet)
                            .font(.caption.monospaced())
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    DesktopAgentIntegrationCopyButtons(export: export)
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
        GroupBox("Product Quick Starts") {
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
                        GroupBox(group.title) {
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
                                    GroupBox(snippet.title) {
                                        Text(snippet.body)
                                            .font(.caption.monospaced())
                                            .textSelection(.enabled)
                                            .frame(maxWidth: .infinity, alignment: .leading)
                                    }
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
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
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
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12))
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
    @State private var showsSidebar = true
    @State private var showsInspector = true

    init(
        viewModel: RuntimeViewModel,
        foundation: DesktopFoundationState,
        initialSection: DesktopAPISection = .overview
    ) {
        self.viewModel = viewModel
        self.foundation = foundation
        _selectedSection = State(initialValue: initialSection)
    }

    var body: some View {
        HSplitView {
            if showsSidebar {
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
                            ? Color.accentColor.opacity(0.14)
                            : Color.secondary.opacity(0.06),
                            in: RoundedRectangle(cornerRadius: 12)
                        )
                    }
                    Spacer()
                }
                .padding(20)
                .frame(minWidth: 220, idealWidth: 240)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    DesktopWorkspaceHeader(title: "API") {
                        DesktopPaneToggleButton(
                            role: .sidebar,
                            isVisible: showsSidebar,
                            shortcut: KeyboardShortcut("s", modifiers: [.command, .option])
                        ) {
                            showsSidebar.toggle()
                        }
                        DesktopPaneToggleButton(
                            role: .inspector,
                            isVisible: showsInspector,
                            shortcut: KeyboardShortcut("i", modifiers: [.command, .option])
                        ) {
                            showsInspector.toggle()
                        }
                    }

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

            if showsInspector {
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
                                Text(session.baseURL)
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
                .frame(minWidth: 280, idealWidth: 300)
            }
        }
    }

    private var defaultBaseURL: String {
        viewModel.selectedServerSession?.effectiveBaseURL ?? "http://127.0.0.1:8080/v1"
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
