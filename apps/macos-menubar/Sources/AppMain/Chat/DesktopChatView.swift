import SwiftUI
import MelixControlPlaneCore

struct DesktopChatTabView: View {
    let viewModel: RuntimeViewModel
    @State private var showsSidebar = true
    @State private var showsInspector = true

    var body: some View {
        HSplitView {
            if showsSidebar {
                DesktopChatSessionSidebar(viewModel: viewModel)
                    .frame(minWidth: 250, idealWidth: 270)
            }

            DesktopChatSessionWorkspace(
                viewModel: viewModel,
                showsSidebar: $showsSidebar,
                showsInspector: $showsInspector
            )

            if showsInspector {
                DesktopChatSessionInspector(viewModel: viewModel)
                    .frame(minWidth: 280, idealWidth: 300)
            }
        }
    }
}

struct DesktopChatSessionSidebar: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
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
            }

            if viewModel.chatSessions.isEmpty {
                ContentUnavailableView(
                    "No Chat Sessions",
                    systemImage: "message.badge",
                    description: Text("Create a new chat after starting a Server Session.")
                )
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(viewModel.chatSessions) { session in
                            Button {
                                viewModel.selectChatSession(id: session.id)
                            } label: {
                                VStack(alignment: .leading, spacing: 4) {
                                    HStack {
                                        Text(session.title)
                                            .font(.headline)
                                        Spacer()
                                        Text(session.branchTitle)
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                    Text(session.summaryText)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .lineLimit(2)
                                }
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(12)
                                .background(
                                    viewModel.selectedChatSession?.id == session.id
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

struct DesktopChatSessionWorkspace: View {
    let viewModel: RuntimeViewModel
    @Binding var showsSidebar: Bool
    @Binding var showsInspector: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .center) {
                VStack(alignment: .leading, spacing: 6) {
                    Text(viewModel.selectedChatSession?.title ?? "Chat")
                        .font(.largeTitle.weight(.semibold))
                    HStack(spacing: 8) {
                        if let branch = viewModel.selectedChatSession?.branchTitle {
                            Text(branch)
                                .font(.caption)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(.quaternary, in: Capsule())
                        }
                        if let server = viewModel.selectedChatServerSession {
                            Text(server.title)
                                .font(.caption)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 4)
                                .background(.quaternary, in: Capsule())
                        }
                    }
                }
                Spacer()
                Button("Fork") {
                    viewModel.forkSelectedChatSession()
                }
                .buttonStyle(.bordered)
                Button("Export") {
                    _ = viewModel.exportSelectedChatSession()
                }
                .buttonStyle(.bordered)
                Button(showsSidebar ? "Hide List" : "Show List") {
                    showsSidebar.toggle()
                }
                Button(showsInspector ? "Hide Inspector" : "Show Inspector") {
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
                .frame(minHeight: 120)
                .padding(8)
                .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 12))

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
                    .disabled(
                        viewModel.chatComposerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        || viewModel.isChatStreaming
                        || viewModel.selectedChatServerSession?.isInteractiveReady != true
                    )
                }
            }
        }
        .padding(20)
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
        .padding(20)
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
