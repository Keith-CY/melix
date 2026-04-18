import SwiftUI
import MelixControlPlaneCore

enum DesktopChatLayoutMetrics {
    static let sidebarMinWidth: CGFloat = 190
    static let sidebarIdealWidth: CGFloat = 220
    static let inspectorMinWidth: CGFloat = 210
    static let inspectorIdealWidth: CGFloat = 232
    static let collapsedRailWidth: CGFloat = 28
    static let composerMinHeight: CGFloat = 76
}

enum DesktopChatPaneRailEdge {
    case leading
    case trailing

    var restoreSymbolName: String {
        switch self {
        case .leading:
            return "sidebar.left"
        case .trailing:
            return "sidebar.right"
        }
    }

    var accessibilityLabel: String {
        switch self {
        case .leading:
            return "Show Chat Sessions"
        case .trailing:
            return "Show Inspector"
        }
    }
}

struct DesktopChatPaneRail: View {
    let edge: DesktopChatPaneRailEdge
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: edge.restoreSymbolName)
                .font(.caption.weight(.semibold))
                .frame(width: DesktopChatLayoutMetrics.collapsedRailWidth)
                .frame(maxHeight: .infinity)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(edge.accessibilityLabel)
        .accessibilityLabel(edge.accessibilityLabel)
        .background(Color.secondary.opacity(0.04))
    }
}

struct DesktopChatTabView: View {
    let viewModel: RuntimeViewModel
    @State private var showsSidebar = true
    @State private var showsInspector = true

    init(
        viewModel: RuntimeViewModel,
        initiallyShowsSidebar: Bool = true,
        initiallyShowsInspector: Bool = true
    ) {
        self.viewModel = viewModel
        _showsSidebar = State(initialValue: initiallyShowsSidebar)
        _showsInspector = State(initialValue: initiallyShowsInspector)
    }

    var body: some View {
        HSplitView {
            if showsSidebar {
                DesktopChatSessionSidebar(viewModel: viewModel)
                    .frame(
                        minWidth: DesktopChatLayoutMetrics.sidebarMinWidth,
                        idealWidth: DesktopChatLayoutMetrics.sidebarIdealWidth
                    )
            } else {
                DesktopChatPaneRail(edge: .leading) {
                    showsSidebar = true
                }
                .frame(width: DesktopChatLayoutMetrics.collapsedRailWidth)
            }

            DesktopChatSessionWorkspace(
                viewModel: viewModel,
                showsSidebar: $showsSidebar,
                showsInspector: $showsInspector
            )

            if showsInspector {
                DesktopChatSessionInspector(viewModel: viewModel)
                    .frame(
                        minWidth: DesktopChatLayoutMetrics.inspectorMinWidth,
                        idealWidth: DesktopChatLayoutMetrics.inspectorIdealWidth
                    )
            } else {
                DesktopChatPaneRail(edge: .trailing) {
                    showsInspector = true
                }
                .frame(width: DesktopChatLayoutMetrics.collapsedRailWidth)
            }
        }
    }
}

struct DesktopChatSessionSidebar: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Chat Sessions")
                    .font(.headline)
                Spacer()
                Button {
                    viewModel.createChatSession()
                } label: {
                    Image(systemName: "plus")
                }
                .buttonStyle(.plain)
                .help("New Chat Session")
                .accessibilityLabel("New Chat Session")
            }

            if viewModel.chatSessions.isEmpty {
                ContentUnavailableView(
                    "No Chat Sessions",
                    systemImage: "message.badge",
                    description: Text("Create a new chat after starting a Server Session.")
                )
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 6) {
                        ForEach(viewModel.chatSessions) { session in
                            DesktopChatSessionRow(
                                session: session,
                                isSelected: viewModel.selectedChatSession?.id == session.id,
                                onSelect: {
                                    viewModel.selectChatSession(id: session.id)
                                },
                                onFork: {
                                    viewModel.selectChatSession(id: session.id)
                                    viewModel.forkSelectedChatSession()
                                },
                                onExport: {
                                    viewModel.selectChatSession(id: session.id)
                                    _ = viewModel.exportSelectedChatSession()
                                }
                            )
                        }
                    }
                }
            }

            Spacer()
        }
        .padding(14)
    }
}

struct DesktopChatSessionWorkspace: View {
    let viewModel: RuntimeViewModel
    @Binding var showsSidebar: Bool
    @Binding var showsInspector: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(viewModel.selectedChatSession?.title ?? "Chat")
                        .font(.title2.weight(.semibold))
                    HStack(spacing: 8) {
                        if let branch = viewModel.selectedChatSession?.branchTitle {
                            Text(branch)
                                .font(.caption2)
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(.quaternary, in: Capsule())
                        }
                        if let server = viewModel.selectedChatServerSession {
                            Text(server.title)
                                .font(.caption2)
                                .padding(.horizontal, 7)
                                .padding(.vertical, 3)
                                .background(.quaternary, in: Capsule())
                        }
                    }
                }
                Spacer()
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

            if let notice = viewModel.selectedChatServerSession?.chatWorkspaceNoticeState {
                VStack(alignment: .leading, spacing: 10) {
                    DesktopInlineNoticeCardView(notice: notice)
                    HStack {
                        switch viewModel.selectedChatServerSession?.lifecycle {
                        case .paused:
                            Button("Resume Server") {
                                Task {
                                    if let serverSessionID = viewModel.selectedChatServerSession?.id {
                                        await viewModel.resumeServerSession(id: serverSessionID)
                                    }
                                }
                            }
                            .buttonStyle(.borderedProminent)
                        case .sleeping:
                            Button("Wake Now") {
                                Task {
                                    if let serverSessionID = viewModel.selectedChatServerSession?.id {
                                        await viewModel.wakeServerSession(id: serverSessionID)
                                    }
                                }
                            }
                            .buttonStyle(.bordered)
                        case .starting, .stopping:
                            EmptyView()
                        case .stopped, .draft, .unavailable:
                            Button("Start Server") {
                                Task {
                                    if let serverSessionID = viewModel.selectedChatServerSession?.id {
                                        await viewModel.startServerSession(id: serverSessionID)
                                    }
                                }
                            }
                            .buttonStyle(.borderedProminent)
                        case .error:
                            EmptyView()
                        case .running, .none:
                            EmptyView()
                        }

                        Button("Open Server") {
                            viewModel.selectSurface(.server)
                        }
                        .buttonStyle(.bordered)
                    }
                }
            }

            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    if viewModel.chatTranscript.isEmpty {
                        GroupBox {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("No transcript yet")
                                    .font(.headline)
                                Text("This chat session is bound to the selected Server Session. Submit a prompt to stream assistant, reasoning, and tool-call state.")
                                    .foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    } else {
                        ForEach(viewModel.chatTranscript) { entry in
                            DesktopChatTranscriptRowView(entry: entry)
                        }
                    }
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                TextEditor(
                    text: Binding(
                        get: { viewModel.chatComposerText },
                        set: { viewModel.chatComposerText = $0 }
                    )
                )
                .font(.body.monospaced())
                .scrollContentBackground(.hidden)
                .frame(height: DesktopChatLayoutMetrics.composerMinHeight)
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: 10)
                        .fill(Color(nsColor: .textBackgroundColor).opacity(0.75))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(Color.primary.opacity(0.08), lineWidth: 1)
                )

                HStack {
                    Text(viewModel.chatStatusText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    if !viewModel.lastChatUsageText.isEmpty {
                        Text(viewModel.lastChatUsageText)
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                    Button("Clear") {
                        viewModel.clearChatTranscript()
                    }
                    .buttonStyle(.bordered)
                    Button("Send") {
                        Task { await viewModel.submitChatPrompt() }
                    }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.return, modifiers: .command)
                    .disabled(
                        viewModel.chatComposerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        || viewModel.isChatStreaming
                        || viewModel.selectedChatServerSession?.isInteractiveReady != true
                    )
                }
            }
        }
        .padding(16)
    }
}

struct DesktopChatSessionInspector: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            GroupBox("Session") {
                VStack(alignment: .leading, spacing: 6) {
                    Text(viewModel.selectedChatSession?.statusText ?? "Idle")
                        .font(.headline)
                    if let server = viewModel.selectedChatServerSession {
                        Text(server.baseURL)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                    if let exportPath = viewModel.selectedChatSession?.exportPath, !exportPath.isEmpty {
                        Text(exportPath)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Analysis Routes") {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(viewModel.chatCapabilities) { capability in
                        HStack(alignment: .top) {
                            Image(systemName: capability.isReady ? "checkmark.circle.fill" : "circle.dotted")
                                .foregroundStyle(capability.isReady ? .green : .secondary)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(capability.title)
                                    .font(.headline)
                                Text(capability.detail)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            if !viewModel.lastChatRequestID.isEmpty || !viewModel.lastChatUsageText.isEmpty {
                GroupBox("Runtime") {
                    VStack(alignment: .leading, spacing: 6) {
                        if !viewModel.lastChatRequestID.isEmpty {
                            Text("request \(viewModel.lastChatRequestID)")
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                        }
                        if !viewModel.lastChatUsageText.isEmpty {
                            Text(viewModel.lastChatUsageText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            Spacer()
        }
        .padding(14)
    }
}

private struct DesktopChatSessionRow: View {
    let session: DesktopChatSessionState
    let isSelected: Bool
    let onSelect: () -> Void
    let onFork: () -> Void
    let onExport: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Button(action: onSelect) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(session.title)
                            .font(.headline)
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        Text(session.branchTitle)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                    Text(session.summaryText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)

            DesktopChatSessionRowActions(onFork: onFork, onExport: onExport)
        }
        .padding(10)
        .background(
            isSelected
            ? Color.accentColor.opacity(0.14)
            : Color.secondary.opacity(0.06),
            in: RoundedRectangle(cornerRadius: 10)
        )
    }
}

private struct DesktopChatSessionRowActions: View {
    let onFork: () -> Void
    let onExport: () -> Void

    var body: some View {
        Menu {
            Button("Fork", action: onFork)
            Button("Export", action: onExport)
        } label: {
            HStack(spacing: 2) {
                Image(systemName: "ellipsis.circle")
                Image(systemName: "chevron.down")
                    .font(.system(size: 8, weight: .semibold))
            }
            .foregroundStyle(.secondary)
            .frame(height: 18)
            .contentShape(Rectangle())
        }
        .menuStyle(.borderlessButton)
        .fixedSize(horizontal: true, vertical: false)
    }
}

private struct DesktopChatPaneToggleButton: View {
    let systemName: String
    let helpText: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: systemName)
                .font(.caption.weight(.semibold))
                .frame(width: 26, height: 24)
                .contentShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        }
        .buttonStyle(.plain)
        .help(helpText)
        .accessibilityLabel(helpText)
    }
}

private struct DesktopChatTranscriptRowView: View {
    let entry: DesktopChatTranscriptEntry

    var body: some View {
        let sanitizedTitle = RichOutputSanitizer.sanitized(entry.title)
        let sanitizedDetail = RichOutputSanitizer.sanitized(entry.detail)
        let sanitizedBody = RichOutputSanitizer.sanitized(entry.body)
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(sanitizedTitle)
                    .font(.headline)
                Spacer()
                if !sanitizedDetail.isEmpty {
                    Text(sanitizedDetail)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                }
            }
            Text(sanitizedBody.isEmpty ? "…" : sanitizedBody)
                .font(entry.kind == .tool ? .caption.monospaced() : .body)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(backgroundStyle, in: RoundedRectangle(cornerRadius: 12))
    }

    private var backgroundStyle: some ShapeStyle {
        switch entry.kind {
        case .user:
            return .blue.opacity(0.14)
        case .assistant:
            return .green.opacity(0.12)
        case .reasoning:
            return .orange.opacity(0.12)
        case .tool:
            return .purple.opacity(0.12)
        case .error:
            return .red.opacity(0.12)
        }
    }
}
