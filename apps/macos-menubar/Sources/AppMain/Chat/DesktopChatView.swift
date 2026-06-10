import AppKit
import SwiftUI
import MelixControlPlaneCore

enum DesktopChatLayoutMetrics {
    static let sidebarMinWidth: CGFloat = 190
    static let sidebarIdealWidth: CGFloat = 220
    static let sidebarMaxWidth: CGFloat = 250
    static let inspectorMinWidth: CGFloat = 210
    static let inspectorIdealWidth: CGFloat = 232
    static let inspectorMaxWidth: CGFloat = 280
    static let collapsedRailWidth: CGFloat = 0
    static let composerMinHeight: CGFloat = 76
    static let readableWorkspaceMaxWidth: CGFloat = 980
}

private enum DesktopChatStarterPrompt: String, CaseIterable, Identifiable {
    case runtimeState = "Explain current runtime state"
    case benchmark = "Benchmark the active model"
    case syntheticDataset = "Draft a synthetic dataset recipe"
    case apiExample = "Show a local API request"

    var id: String { rawValue }

    var detail: String {
        switch self {
        case .runtimeState:
            return "Summarize server, model, queue, and recent warnings."
        case .benchmark:
            return "Prepare a small latency and throughput run."
        case .syntheticDataset:
            return "Create a grounded workflow seed for data generation."
        case .apiExample:
            return "Copy a request shape for the selected endpoint."
        }
    }

    var prompt: String {
        switch self {
        case .runtimeState:
            return "Explain the current Melix runtime state and call out anything that needs attention."
        case .benchmark:
            return "Set up a quick benchmark for the active model and explain what metrics to watch."
        case .syntheticDataset:
            return "Draft a synthetic dataset recipe for event extraction and list the fields I should verify."
        case .apiExample:
            return "Show a local API request for the selected Melix server and explain the auth requirements."
        }
    }
}

enum DesktopChatTranscriptAutoScroll {
    enum Anchor: String, Hashable {
        case bottom = "desktop-chat-transcript-bottom"
    }

    struct Snapshot: Equatable {
        let entryCount: Int
        let lastEntryID: String
        let lastEntryBody: String
        let lastEntryDetail: String
        let isStreaming: Bool
        let statusText: String
    }

    static func snapshot(
        transcript: [DesktopChatTranscriptEntry],
        isStreaming: Bool,
        statusText: String
    ) -> Snapshot {
        let lastEntry = transcript.last
        return Snapshot(
            entryCount: transcript.count,
            lastEntryID: lastEntry?.id ?? "",
            lastEntryBody: lastEntry?.body ?? "",
            lastEntryDetail: lastEntry?.detail ?? "",
            isStreaming: isStreaming,
            statusText: isStreaming ? statusText : ""
        )
    }
}

enum DesktopChatComposerKeyPolicy {
    enum Action: Equatable {
        case submit
        case insertNewline
        case passThrough
    }

    static let returnKeyCode: UInt16 = 36
    static let keypadEnterKeyCode: UInt16 = 76

    static func action(keyCode: UInt16, modifiers: NSEvent.ModifierFlags) -> Action {
        guard keyCode == returnKeyCode || keyCode == keypadEnterKeyCode else {
            return .passThrough
        }
        if modifiers.contains(.command) {
            return .submit
        }
        if modifiers.contains(.control) {
            return .insertNewline
        }
        return .passThrough
    }
}

enum DesktopChatComposerReturnCommandPolicy {
    static func action(selector: Selector, modifiers: NSEvent.ModifierFlags) -> DesktopChatComposerKeyPolicy.Action {
        guard isReturnCommandSelector(selector) else {
            return .passThrough
        }
        if modifiers.contains(.command) {
            return .submit
        }
        if modifiers.contains(.control) {
            return .insertNewline
        }
        return .passThrough
    }

    private static func isReturnCommandSelector(_ selector: Selector) -> Bool {
        selector == #selector(NSTextView.insertNewline(_:))
        || selector == #selector(NSTextView.insertLineBreak(_:))
        || selector == #selector(NSTextView.insertNewlineIgnoringFieldEditor(_:))
    }
}

struct DesktopChatArtifactPreviewState: Equatable, Identifiable {
    let id: String
    let entryID: String
    let title: String
    let path: String
    let sourceKind: DesktopChatTranscriptEntry.Kind

    init(entry: DesktopChatTranscriptEntry, path: String) {
        self.id = "\(entry.id)-\(path)"
        self.entryID = entry.id
        self.title = entry.title.isEmpty ? "Chat Artifact" : entry.title
        self.path = path
        self.sourceKind = entry.kind
    }
}

enum DesktopChatArtifactPathDetector {
    static func firstPath(in text: String, isSanitized: Bool = false) -> String? {
        let sanitizedText = isSanitized ? text : RichOutputSanitizer.sanitized(text)
        let separators = CharacterSet.whitespacesAndNewlines
            .union(CharacterSet(charactersIn: "\"'`()[]{}<>,="))
        for tokenScalars in sanitizedText.unicodeScalars.lazy.split(whereSeparator: { scalar in
            separators.contains(scalar)
        }) {
            let token = String(String.UnicodeScalarView(tokenScalars))
            if let path = normalizedArtifactPath(token) {
                return path
            }
        }
        return nil
    }

    private static func normalizedArtifactPath(_ token: String) -> String? {
        let trimmed = token.trimmingCharacters(in: CharacterSet(charactersIn: ".:;"))
        guard trimmed.hasPrefix("/") || trimmed.hasPrefix("s3://") || trimmed.hasPrefix("lakefs://") else {
            return nil
        }
        let lowercased = trimmed.lowercased()
        guard lowercased.contains("/tmp/")
            || lowercased.contains(".artifact")
            || lowercased.hasSuffix(".md")
            || lowercased.hasSuffix(".json")
            || lowercased.hasSuffix(".jsonl")
            || lowercased.hasSuffix(".csv")
            || lowercased.hasSuffix(".html")
            || lowercased.hasSuffix(".png")
            || lowercased.hasSuffix(".jpg")
            || lowercased.hasSuffix(".jpeg")
            || lowercased.hasSuffix(".gif")
        else {
            return nil
        }
        return trimmed
    }
}

struct DesktopChatTabView: View {
    let viewModel: RuntimeViewModel
    @Binding private var showsSidebar: Bool
    @Binding private var showsInspector: Bool
    @State private var artifactPreview: DesktopChatArtifactPreviewState? = nil

    init(
        viewModel: RuntimeViewModel,
        initiallyShowsSidebar: Bool = true,
        initiallyShowsInspector: Bool = true
    ) {
        self.viewModel = viewModel
        _showsSidebar = .constant(initiallyShowsSidebar)
        _showsInspector = .constant(initiallyShowsInspector)
    }

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
        DesktopChatTabContentView(
            viewModel: viewModel,
            showsSidebar: $showsSidebar,
            showsInspector: $showsInspector,
            artifactPreview: $artifactPreview
        )
    }
}

struct DesktopChatTabContentView: View {
    let viewModel: RuntimeViewModel
    @Binding var showsSidebar: Bool
    @Binding var showsInspector: Bool
    @Binding var artifactPreview: DesktopChatArtifactPreviewState?

    var body: some View {
        HStack(spacing: 0) {
            DesktopWorkspacePaneSlot(
                role: .sidebar,
                isVisible: showsSidebar,
                idealWidth: DesktopChatLayoutMetrics.sidebarIdealWidth
            ) {
                DesktopChatSessionSidebar(viewModel: viewModel)
            }

            DesktopChatSessionWorkspace(
                viewModel: viewModel,
                showsSidebar: $showsSidebar,
                showsInspector: $showsInspector,
                onPreviewArtifact: { preview in
                    selectArtifactPreview(preview)
                }
            )
            .frame(maxWidth: DesktopChatLayoutMetrics.readableWorkspaceMaxWidth, maxHeight: .infinity)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)

            DesktopWorkspacePaneSlot(
                role: .inspector,
                isVisible: showsInspector,
                idealWidth: DesktopChatLayoutMetrics.inspectorIdealWidth
            ) {
                if let artifactPreview {
                    DesktopChatArtifactPreviewRail(preview: artifactPreview) {
                        clearArtifactPreview()
                    }
                } else {
                    DesktopChatSessionInspector(viewModel: viewModel)
                }
            }
        }
    }

    func selectArtifactPreview(_ preview: DesktopChatArtifactPreviewState) {
        artifactPreview = preview
        showsInspector = true
    }

    func clearArtifactPreview() {
        artifactPreview = nil
    }
}

struct DesktopChatSessionSidebar: View {
    let viewModel: RuntimeViewModel

    func createChatSessionAction() {
        viewModel.createChatSession()
    }

    func openServerAction() {
        viewModel.selectSurface(.server)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Chat Sessions")
                    .melixSectionLabel()
                Spacer()
                Button(action: createChatSessionAction) {
                    Image(systemName: "plus")
                }
                .buttonStyle(.plain)
                .help("New Chat Session")
                .accessibilityLabel("New Chat Session")
                .focusable(false)
            }

            if viewModel.chatSessions.isEmpty {
                MelixActionableEmptyState(
                    title: "No Chat Sessions",
                    systemImage: "message.badge",
                    detail: "Start a chat after choosing a local or remote server. Sessions keep transcript, model, and export context together."
                ) {
                    VStack(spacing: MelixDesignTokens.Spacing.sm) {
                        Button("New Chat", action: createChatSessionAction)
                        .buttonStyle(.borderedProminent)

                        Button("Open Server", action: openServerAction)
                        .buttonStyle(.bordered)
                    }
                }
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
                                },
                                onDelete: {
                                    viewModel.deleteChatSession(id: session.id)
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
    var onPreviewArtifact: (DesktopChatArtifactPreviewState) -> Void = { _ in }

    private var isSendDisabled: Bool {
        viewModel.chatComposerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        || viewModel.isChatStreaming
        || viewModel.selectedChatServerSession?.isInteractiveReady != true
    }

    private func submitChatPrompt() {
        Task { await viewModel.submitChatPrompt() }
    }

    func openServerSurface() {
        viewModel.selectSurface(.server)
    }

    func startSelectedChatServerSession() {
        Task {
            guard let providerID = viewModel.selectedChatServerSession?.id else {
                openServerSurface()
                return
            }
            await viewModel.startServerSession(id: providerID)
        }
    }

    func resumeSelectedChatServerSession() {
        Task {
            guard let providerID = viewModel.selectedChatServerSession?.id else {
                openServerSurface()
                return
            }
            await viewModel.resumeServerSession(id: providerID)
        }
    }

    func wakeSelectedChatServerSession() {
        Task {
            guard let providerID = viewModel.selectedChatServerSession?.id else {
                openServerSurface()
                return
            }
            await viewModel.wakeServerSession(id: providerID)
        }
    }

    private var chatTranscriptScrollSnapshot: DesktopChatTranscriptAutoScroll.Snapshot {
        DesktopChatTranscriptAutoScroll.snapshot(
            transcript: viewModel.chatTranscript,
            isStreaming: viewModel.isChatStreaming,
            statusText: viewModel.chatStatusText
        )
    }

    private func scrollChatTranscriptToBottom(_ proxy: ScrollViewProxy, animated: Bool) {
        DispatchQueue.main.async {
            if animated {
                withAnimation(.easeOut(duration: 0.18)) {
                    proxy.scrollTo(DesktopChatTranscriptAutoScroll.Anchor.bottom, anchor: .bottom)
                }
            } else {
                proxy.scrollTo(DesktopChatTranscriptAutoScroll.Anchor.bottom, anchor: .bottom)
            }
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(viewModel.selectedChatSession?.title ?? "Chat")
                        .font(.title2.weight(.semibold))
                    if let branch = viewModel.selectedChatSession?.displayBranchTitle {
                        DesktopChatSessionBranchBadgeView(branch: branch)
                    }
                }
                Spacer(minLength: 12)
                DesktopChatServerPicker(viewModel: viewModel)
                    .alignmentGuide(.firstTextBaseline) { dimensions in
                        dimensions[VerticalAlignment.center]
                    }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            if let notice = viewModel.selectedChatServerSession?.chatWorkspaceNoticeState {
                DesktopInlineNoticeCardView(notice: notice)
            }

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        if viewModel.chatTranscript.isEmpty == false {
                            ForEach(viewModel.chatTranscript) { entry in
                                DesktopChatTranscriptRowView(
                                    entry: entry,
                                    isPending: viewModel.isPendingAssistantTranscriptEntry(entry),
                                    isStreaming: viewModel.isStreamingAssistantTranscriptEntry(entry),
                                    pendingStatusText: viewModel.chatStatusText,
                                    onPreviewArtifact: onPreviewArtifact
                                )
                                .id(entry.id)
                            }
                        } else {
                            DesktopChatEmptyStateView(viewModel: viewModel)
                        }
                        Color.clear
                            .frame(height: 1)
                            .id(DesktopChatTranscriptAutoScroll.Anchor.bottom)
                    }
                }
                .onAppear {
                    scrollChatTranscriptToBottom(proxy, animated: false)
                }
                .onChange(of: chatTranscriptScrollSnapshot) { _, _ in
                    scrollChatTranscriptToBottom(proxy, animated: true)
                }
            }

            DesktopChatComposerSurface(
                text: Binding(
                    get: { viewModel.chatComposerText },
                    set: { viewModel.chatComposerText = $0 }
                ),
                isSubmitAvailable: viewModel.isChatStreaming == false
                && viewModel.selectedChatServerSession?.isInteractiveReady == true,
                isSendDisabled: isSendDisabled,
                isStreaming: viewModel.isChatStreaming,
                statusText: viewModel.chatStatusText,
                usageText: viewModel.lastChatUsageText,
                serverSession: viewModel.selectedChatServerSession,
                capabilities: viewModel.chatCapabilities,
                onCommandSubmit: { draft in
                    viewModel.chatComposerText = draft
                    submitChatPrompt()
                },
                onSubmit: submitChatPrompt,
                onClear: viewModel.clearChatTranscript,
                onOpenServer: openServerSurface,
                onStartServer: startSelectedChatServerSession,
                onResumeServer: resumeSelectedChatServerSession,
                onWakeServer: wakeSelectedChatServerSession
            )
        }
        .padding(16)
    }
}

struct DesktopChatSessionInspector: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        DesktopInspectorContractView(
            title: "Chat Inspector",
            context: runtimeContextText,
            health: runtimeHealthText,
            metrics: runtimeMetricsText,
            actions: inspectorActions,
            evidence: inspectorEvidence
        ) {
            GroupBox("Model Capabilities") {
                DesktopChatCapabilityIconGrid(capabilities: viewModel.chatCapabilities)
            }
        }
    }

    private var runtimeContextText: String {
        if let server = viewModel.selectedChatServerSession {
            return "\(server.title) • \(server.modelID)"
        }
        return "No chat server selected"
    }

    private var runtimeHealthText: String {
        viewModel.selectedChatServerSession?.lifecycleSummaryText
            ?? viewModel.selectedChatSession?.statusText
            ?? "Choose a server to start chatting"
    }

    private var runtimeMetricsText: String {
        if let server = viewModel.selectedChatServerSession {
            return "\(server.effectiveBaseURL) • \(server.runtimeDetailText)"
        }
        return viewModel.lastChatUsageText.isEmpty ? "No usage recorded" : viewModel.lastChatUsageText
    }

    private var inspectorActions: [DesktopInspectorActionRow] {
        [
            DesktopInspectorActionRow(title: "Open Command Center", systemImage: "command.circle") {
                viewModel.selectSurface(.commandCenter)
            },
            DesktopInspectorActionRow(title: "Open Server", systemImage: "server.rack") {
                viewModel.selectSurface(.server)
            },
            DesktopInspectorActionRow(title: "Open Diagnostics", systemImage: "stethoscope") {
                viewModel.selectToolSection(.diagnostics)
            },
        ]
    }

    private var inspectorEvidence: [String] {
        [
            viewModel.selectedChatSession?.exportPath,
            viewModel.selectedChatServerSession?.sharedAccessSummaryText,
            viewModel.lastChatUsageText,
        ]
        .compactMap { $0 }
        .filter { $0.isEmpty == false }
    }
}

struct DesktopChatArtifactPreviewRail: View {
    let preview: DesktopChatArtifactPreviewState
    let onClose: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(alignment: .firstTextBaseline) {
                Text("Artifact Preview")
                    .font(.headline)
                    .textSelection(.enabled)
                Spacer()
                Button(action: onClose) {
                    Image(systemName: "xmark")
                }
                .buttonStyle(.borderless)
                .help("Close Preview")
                .accessibilityLabel("Close Preview")
            }

            GroupBox("Source") {
                VStack(alignment: .leading, spacing: 6) {
                    Text(preview.title)
                        .font(.caption.weight(.semibold))
                    Text(preview.sourceKind.rawValue.capitalized)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(preview.entryID)
                        .font(.caption2.monospaced())
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                        .textSelection(.enabled)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Path") {
                Text(preview.path)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
                    .lineLimit(5)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }

            GroupBox("Preview") {
                VStack(alignment: .leading, spacing: 6) {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.title3)
                        .foregroundStyle(MelixDesignTokens.accent)
                    Text("Ready for artifact preview.")
                        .font(.caption.weight(.semibold))
                    Text("Open the referenced output from the owning workflow for full inspection.")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }

            Spacer(minLength: 0)
        }
        .padding(20)
    }
}

private struct DesktopChatEmptyStateView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text("Ask Melix")
                    .font(.title3.weight(.semibold))
                Text("Start from a runtime-aware prompt, or continue a recent local session.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 10)], spacing: 10) {
                ForEach(DesktopChatStarterPrompt.allCases) { prompt in
                    Button {
                        viewModel.chatComposerText = prompt.prompt
                    } label: {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(prompt.rawValue)
                                .font(.headline)
                            Text(prompt.detail)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .lineLimit(2)
                        }
                        .frame(maxWidth: .infinity, minHeight: 74, alignment: .leading)
                        .padding(12)
                        .background(Color.secondary.opacity(0.05), in: RoundedRectangle(cornerRadius: 10))
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline), lineWidth: 1)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }

            if viewModel.chatSessions.isEmpty == false {
                MelixSectionCard("Recent Chats") {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(viewModel.chatSessions.prefix(3)) { session in
                            HStack(alignment: .firstTextBaseline) {
                                Text(session.title)
                                    .font(.caption.weight(.semibold))
                                Spacer()
                                Text(session.summaryText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                            }
                        }
                    }
                }
            }

            if let notice = viewModel.selectedChatServerSession?.chatWorkspaceNoticeState {
                DesktopInlineNoticeCardView(notice: notice)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 12)
    }
}

struct DesktopChatSessionBranchBadgeView: View {
    let branch: String

    var body: some View {
        Text(branch)
            .font(.caption2)
            .padding(.horizontal, 7)
            .padding(.vertical, 3)
            .background(.quaternary, in: Capsule())
            .accessibilityLabel(branch)
    }
}

private struct DesktopChatServerPicker: View {
    let viewModel: RuntimeViewModel

    private var selectedServerBinding: Binding<String> {
        Binding(
            get: { viewModel.selectedChatSession?.providerID ?? "" },
            set: { viewModel.bindSelectedChatSessionToServer(providerID: $0) }
        )
    }

    var body: some View {
        if viewModel.providers.isEmpty {
            Button {
                viewModel.selectSurface(.server)
            } label: {
                Label("Choose Server", systemImage: "server.rack")
                    .labelStyle(.titleAndIcon)
            }
            .font(.caption2)
            .buttonStyle(.borderless)
            .help("Open Server to create a chat provider")
            .accessibilityLabel("Choose Chat Server")
        } else {
            Picker("Server", selection: selectedServerBinding) {
                Text("Choose Server").tag("")
                ForEach(viewModel.providers) { session in
                    Text(session.title).tag(session.id)
                }
            }
            .labelsHidden()
            .pickerStyle(.menu)
            .controlSize(.small)
            .frame(maxWidth: 180)
            .help("Choose the server or provider for this chat session")
            .accessibilityLabel("Chat Server")
        }
    }
}

private struct DesktopChatCapabilityIconGrid: View {
    let capabilities: [DesktopChatCapabilityRow]

    private let columns = [
        GridItem(.adaptive(minimum: 74), spacing: 8, alignment: .top),
    ]

    var body: some View {
        LazyVGrid(columns: columns, alignment: .leading, spacing: 8) {
            ForEach(capabilities) { capability in
                DesktopChatCapabilityIconTile(capability: capability)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Model Capabilities")
    }
}

private struct DesktopChatCapabilityIconTile: View {
    let capability: DesktopChatCapabilityRow

    var body: some View {
        VStack(spacing: 6) {
            ZStack(alignment: .topTrailing) {
                Image(systemName: capability.systemImageName)
                    .font(.system(size: 18, weight: .medium))
                    .frame(width: 34, height: 28)
                    .foregroundStyle(capability.isReady ? MelixDesignTokens.accent : Color.secondary)

                Circle()
                    .fill(capability.isReady ? MelixDesignTokens.StatusColor.success : Color.secondary.opacity(0.45))
                    .frame(width: 7, height: 7)
                    .offset(x: 2, y: -1)
            }

            Text(capability.shortTitle)
                .font(.caption2.weight(.medium))
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .frame(minWidth: 64, minHeight: 58)
        .padding(.horizontal, 6)
        .padding(.vertical, 7)
        .background(
            RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.sm)
                .fill(Color.primary.opacity(0.035))
        )
        .overlay(
            RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.sm)
                .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline), lineWidth: 1)
        )
        .help("\(capability.title): \(capability.detail)")
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(capability.title), \(capability.isReady ? "ready" : "unavailable")")
    }
}

private struct DesktopChatSessionRow: View {
    let session: DesktopChatSessionState
    let isSelected: Bool
    let onSelect: () -> Void
    let onFork: () -> Void
    let onExport: () -> Void
    let onDelete: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Button(action: onSelect) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(session.title)
                            .font(.headline)
                            .lineLimit(1)
                        Spacer(minLength: 4)
                        if let branch = session.displayBranchTitle {
                            Text(branch)
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                        }
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

            DesktopChatSessionRowActions(onFork: onFork, onExport: onExport, onDelete: onDelete)
        }
        .padding(10)
        .melixSelection(isSelected)
    }
}

private struct DesktopChatSessionRowActions: View {
    let onFork: () -> Void
    let onExport: () -> Void
    let onDelete: () -> Void

    var body: some View {
        Menu {
            Button("Fork", action: onFork)
            Button("Export", action: onExport)
            Divider()
            Button("Delete", role: .destructive, action: onDelete)
        } label: {
            Image(systemName: "ellipsis.circle")
                .font(.body)
            .foregroundStyle(.secondary)
            .frame(width: 22, height: 22)
            .contentShape(Rectangle())
        }
        .menuStyle(.borderlessButton)
        .help("Chat Actions")
        .accessibilityLabel("Chat Actions")
        .fixedSize(horizontal: true, vertical: false)
    }
}

struct DesktopChatComposerSurface: View {
    @Binding var text: String
    let isSubmitAvailable: Bool
    let isSendDisabled: Bool
    let isStreaming: Bool
    let statusText: String
    let usageText: String
    let serverSession: DesktopProviderState?
    let capabilities: [DesktopChatCapabilityRow]
    let onCommandSubmit: (String) -> Void
    let onSubmit: () -> Void
    let onClear: () -> Void
    let onOpenServer: () -> Void
    let onStartServer: () -> Void
    let onResumeServer: () -> Void
    let onWakeServer: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            DesktopChatRuntimeControlStrip(
                serverSession: serverSession,
                capabilities: capabilities,
                onOpenServer: onOpenServer,
                onStartServer: onStartServer,
                onResumeServer: onResumeServer,
                onWakeServer: onWakeServer
            )

            HStack(alignment: .bottom, spacing: 10) {
                DesktopChatComposerTextView(
                    text: $text,
                    isSubmitAvailable: isSubmitAvailable,
                    onCommandSubmit: onCommandSubmit
                )
                .frame(height: DesktopChatLayoutMetrics.composerMinHeight)

                VStack(spacing: 6) {
                    Button(action: primaryAction) {
                        primaryActionLabel
                    }
                    .labelStyle(.iconOnly)
                    .buttonStyle(.borderedProminent)
                    .controlSize(.regular)
                    .disabled(isStreaming || isSendDisabled)
                    .help(isStreaming ? "Streaming cancellation is not available yet" : "Send")
                    .accessibilityLabel(isStreaming ? "Stop" : "Send")

                    Button(action: onClear) {
                        Image(systemName: "trash")
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                    .help("Clear Chat")
                    .accessibilityLabel("Clear Chat")
                }
                .fixedSize(horizontal: true, vertical: false)
            }

            HStack(spacing: 10) {
                Text(statusText)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Spacer(minLength: 8)
                if usageText.isEmpty == false {
                    Text(usageText)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
        .background(
            RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.lg)
                .fill(Color(nsColor: .textBackgroundColor).opacity(0.82))
        )
        .overlay(
            RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.lg)
                .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.interactive), lineWidth: 1)
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Chat Composer")
    }

    func primaryAction() {
        guard isStreaming == false else {
            return
        }
        onSubmit()
    }

    @ViewBuilder
    var primaryActionLabel: some View {
        if isStreaming {
            Label("Stop", systemImage: "stop.fill")
        } else {
            Label("Send", systemImage: "paperplane.fill")
        }
    }
}

struct DesktopChatRuntimeControlStrip: View {
    enum RecoveryActionKind {
        case openServer
        case startServer
        case resumeServer
        case wakeServer
    }

    struct RecoveryAction {
        let title: String
        let kind: RecoveryActionKind
        let isProminent: Bool
    }

    let serverSession: DesktopProviderState?
    let capabilities: [DesktopChatCapabilityRow]
    let onOpenServer: () -> Void
    let onStartServer: () -> Void
    let onResumeServer: () -> Void
    let onWakeServer: () -> Void

    var recoveryAction: RecoveryAction? {
        switch serverSession?.lifecycle {
        case .none:
            return RecoveryAction(title: "Choose Server", kind: .openServer, isProminent: false)
        case .paused:
            return RecoveryAction(title: "Resume Server", kind: .resumeServer, isProminent: true)
        case .sleeping:
            return RecoveryAction(title: "Wake", kind: .wakeServer, isProminent: false)
        case .draft, .stopped, .unavailable:
            return RecoveryAction(title: "Start Server", kind: .startServer, isProminent: true)
        case .error:
            return RecoveryAction(title: "Open Server", kind: .openServer, isProminent: true)
        case .starting, .stopping, .running:
            return nil
        }
    }

    var body: some View {
        HStack(spacing: 8) {
            DesktopChatRuntimeServerCapsule(serverSession: serverSession)

            if capabilities.isEmpty == false {
                DesktopChatInlineCapabilityCluster(capabilities: Array(capabilities.prefix(5)))
            }

            Spacer(minLength: 8)

            recoveryActionButton

            Button(action: onOpenServer) {
                Image(systemName: "server.rack")
                    .frame(width: 18, height: 18)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Open Server")
            .accessibilityLabel("Open Server")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    var recoveryActionButton: some View {
        if let recoveryAction {
            if recoveryAction.isProminent {
                Button(recoveryAction.title) {
                    perform(recoveryAction)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
            } else {
                Button(recoveryAction.title) {
                    perform(recoveryAction)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        } else {
            EmptyView()
        }
    }

    func perform(_ action: RecoveryAction) {
        switch action.kind {
        case .openServer:
            onOpenServer()
        case .startServer:
            onStartServer()
        case .resumeServer:
            onResumeServer()
        case .wakeServer:
            onWakeServer()
        }
    }
}

struct DesktopChatRuntimeServerCapsule: View {
    let serverSession: DesktopProviderState?

    var body: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(statusColor)
                .frame(width: 7, height: 7)
            VStack(alignment: .leading, spacing: 1) {
                Text(serverTitle)
                    .font(.caption.weight(.semibold))
                    .lineLimit(1)
                Text(serverDetail)
                    .font(.caption2.monospaced())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 5)
        .background(Color.secondary.opacity(0.06), in: Capsule())
        .overlay(
            Capsule()
                .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline), lineWidth: 1)
        )
        .help(serverSession?.runtimeDetailText ?? "Choose a server for this chat")
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(serverTitle), \(serverDetail)")
    }

    var serverTitle: String {
        serverSession?.title ?? "No Server"
    }

    var serverDetail: String {
        guard let serverSession else {
            return "Choose Server"
        }
        return "\(serverSession.lifecycle.rawValue) • \(serverSession.modelID)"
    }

    var statusColor: Color {
        switch serverSession?.lifecycle {
        case .running, .sleeping:
            return MelixDesignTokens.StatusColor.success
        case .paused, .starting, .stopping, .stopped, .draft, .unavailable:
            return MelixDesignTokens.StatusColor.warning
        case .error:
            return MelixDesignTokens.StatusColor.error
        case .none:
            return Color.secondary.opacity(0.55)
        }
    }
}

struct DesktopChatInlineCapabilityCluster: View {
    let capabilities: [DesktopChatCapabilityRow]

    var body: some View {
        HStack(spacing: 4) {
            ForEach(capabilities) { capability in
                Image(systemName: capability.systemImageName)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(capability.isReady ? MelixDesignTokens.accent : Color.secondary)
                    .frame(width: 22, height: 22)
                    .background(Color.primary.opacity(0.035), in: Circle())
                    .help("\(capability.title): \(capability.detail)")
                    .accessibilityLabel("\(capability.title), \(capability.isReady ? "ready" : "unavailable")")
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Model Capabilities")
    }
}

private struct DesktopChatComposerTextView: NSViewRepresentable {
    @Binding var text: String
    let isSubmitAvailable: Bool
    let onCommandSubmit: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text)
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = DesktopChatComposerCommandSubmitScrollView()
        scrollView.drawsBackground = false
        scrollView.hasVerticalScroller = true
        scrollView.borderType = .noBorder

        let textView = DesktopChatComposerCommandSubmitTextView()
        textView.delegate = context.coordinator
        textView.isRichText = false
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.font = NSFont.monospacedSystemFont(ofSize: NSFont.systemFontSize, weight: .regular)
        textView.drawsBackground = false
        textView.textContainerInset = NSSize(width: 0, height: 0)
        textView.minSize = NSSize(width: 0, height: DesktopChatLayoutMetrics.composerMinHeight)
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainer?.widthTracksTextView = true
        scrollView.commandSubmitTextView = textView
        scrollView.documentView = textView
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? DesktopChatComposerCommandSubmitTextView else {
            return
        }
        if textView.string != text {
            textView.string = text
        }
        textView.onCommandSubmit = { currentText in
            context.coordinator.text.wrappedValue = currentText
            guard isSubmitAvailable,
                  currentText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            else {
                return false
            }
            onCommandSubmit(currentText)
            return true
        }
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var text: Binding<String>

        init(text: Binding<String>) {
            self.text = text
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else {
                return
            }
            text.wrappedValue = textView.string
        }
    }

}

@MainActor
final class DesktopChatComposerCommandSubmitScrollView: NSScrollView {
    weak var commandSubmitTextView: DesktopChatComposerCommandSubmitTextView?
    private var localKeyDownMonitor: Any?

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()

        if window == nil {
            if let localKeyDownMonitor {
                NSEvent.removeMonitor(localKeyDownMonitor)
                self.localKeyDownMonitor = nil
            }
            return
        }

        guard localKeyDownMonitor == nil else {
            return
        }
        localKeyDownMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self,
                  let window = self.window,
                  window.isKeyWindow,
                  event.window == nil || event.window === window,
                  self.isComposerInteractionActive
            else {
                return event
            }
            return self.handleComposerKeyEvent(event) ? nil : event
        }
    }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        if handleComposerKeyEvent(event) {
            return true
        }
        return super.performKeyEquivalent(with: event)
    }

    override func keyDown(with event: NSEvent) {
        if handleComposerKeyEvent(event) == false {
            super.keyDown(with: event)
        }
    }

    @discardableResult
    func handleComposerKeyEvent(_ event: NSEvent) -> Bool {
        guard let commandSubmitTextView,
              isComposerInteractionActive
        else {
            return false
        }
        return commandSubmitTextView.handleLocalKeyDown(event)
    }

    private var isComposerInteractionActive: Bool {
        guard let window else {
            return true
        }
        guard let firstResponder = window.firstResponder else {
            return false
        }
        if firstResponder === self || firstResponder === commandSubmitTextView {
            return true
        }
        guard let firstResponderView = firstResponder as? NSView else {
            return false
        }
        return firstResponderView.isDescendant(of: self)
    }
}

@MainActor
final class DesktopChatComposerCommandSubmitTextView: NSTextView {
    var onCommandSubmit: ((String) -> Bool)?
    private var localKeyDownMonitor: Any?

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()

        if window == nil {
            if let localKeyDownMonitor {
                NSEvent.removeMonitor(localKeyDownMonitor)
                self.localKeyDownMonitor = nil
            }
            return
        }

        guard localKeyDownMonitor == nil else {
            return
        }
        localKeyDownMonitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard let self,
                  let window = self.window,
                  window.isKeyWindow,
                  event.window == nil || event.window === window,
                  window.firstResponder === self || window.firstResponder is NSTextView
            else {
                return event
            }
            return self.handleLocalKeyDown(event) ? nil : event
        }
    }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        guard DesktopChatComposerKeyPolicy.action(
            keyCode: event.keyCode,
            modifiers: event.modifierFlags
        ) == .submit else {
            return super.performKeyEquivalent(with: event)
        }
        return submitCurrentText()
    }

    override func doCommand(by selector: Selector) {
        switch currentReturnCommandAction(for: selector) {
        case .submit:
            _ = submitCurrentText()
        case .insertNewline:
            super.insertNewlineIgnoringFieldEditor(nil)
        case .passThrough:
            super.doCommand(by: selector)
        }
    }

    override func insertNewline(_ sender: Any?) {
        guard currentReturnCommandAction(for: #selector(NSTextView.insertNewline(_:))) == .submit else {
            super.insertNewline(sender)
            return
        }
        _ = submitCurrentText()
    }

    override func insertLineBreak(_ sender: Any?) {
        guard currentReturnCommandAction(for: #selector(NSTextView.insertLineBreak(_:))) == .submit else {
            super.insertLineBreak(sender)
            return
        }
        _ = submitCurrentText()
    }

    override func insertNewlineIgnoringFieldEditor(_ sender: Any?) {
        guard currentReturnCommandAction(
            for: #selector(NSTextView.insertNewlineIgnoringFieldEditor(_:))
        ) == .submit else {
            super.insertNewlineIgnoringFieldEditor(sender)
            return
        }
        _ = submitCurrentText()
    }

    @discardableResult
    func handleLocalKeyDown(_ event: NSEvent) -> Bool {
        switch DesktopChatComposerKeyPolicy.action(keyCode: event.keyCode, modifiers: event.modifierFlags) {
        case .submit:
            return submitCurrentText()
        case .insertNewline:
            insertNewlineIgnoringFieldEditor(nil)
            return true
        case .passThrough:
            return false
        }
    }

    override func keyDown(with event: NSEvent) {
        if handleLocalKeyDown(event) == false {
            super.keyDown(with: event)
        }
    }

    private func currentReturnCommandAction(for selector: Selector) -> DesktopChatComposerKeyPolicy.Action {
        guard let event = NSApp.currentEvent else {
            return .passThrough
        }
        return DesktopChatComposerReturnCommandPolicy.action(selector: selector, modifiers: event.modifierFlags)
    }

    private func submitCurrentText() -> Bool {
        if onCommandSubmit?(string) == true {
            return true
        }
        NSSound.beep()
        return true
    }
}

struct DesktopChatTranscriptRowView: View {
    let entry: DesktopChatTranscriptEntry
    let isPending: Bool
    let isStreaming: Bool
    let pendingStatusText: String
    let onPreviewArtifact: (DesktopChatArtifactPreviewState) -> Void

    init(
        entry: DesktopChatTranscriptEntry,
        isPending: Bool = false,
        isStreaming: Bool = false,
        pendingStatusText: String = "",
        onPreviewArtifact: @escaping (DesktopChatArtifactPreviewState) -> Void = { _ in }
    ) {
        self.entry = entry
        self.isPending = isPending
        self.isStreaming = isStreaming
        self.pendingStatusText = pendingStatusText
        self.onPreviewArtifact = onPreviewArtifact
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            rowContent
            if let artifactPreview {
                DesktopChatArtifactPreviewTrigger(preview: artifactPreview) {
                    onPreviewArtifact(artifactPreview)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private var rowContent: some View {
        switch entry.kind {
        case .user:
            DesktopChatUserBubbleView(messageBody: sanitizedBody)
        case .assistant:
            DesktopChatAssistantDocumentView(
                messageBody: sanitizedBody,
                isPending: isPending,
                isStreaming: isStreaming,
                pendingStatusText: sanitizedPendingStatusText
            )
        case .reasoning:
            DesktopChatActivityBlockView(
                kind: .reasoning,
                title: sanitizedTitle,
                messageBody: sanitizedBody,
                detail: sanitizedDetail,
                isStreaming: isStreaming
            )
        case .tool:
            DesktopChatActivityBlockView(
                kind: .tool,
                title: sanitizedTitle,
                messageBody: sanitizedBody,
                detail: sanitizedDetail,
                isStreaming: isStreaming
            )
        case .error:
            DesktopChatErrorBlockView(
                title: sanitizedTitle,
                messageBody: sanitizedBody,
                detail: sanitizedDetail
            )
        }
    }

    private var artifactPreview: DesktopChatArtifactPreviewState? {
        if let path = DesktopChatArtifactPathDetector.firstPath(in: sanitizedBody, isSanitized: true) {
            return DesktopChatArtifactPreviewState(entry: entry, path: path)
        }
        if let path = DesktopChatArtifactPathDetector.firstPath(in: sanitizedDetail, isSanitized: true) {
            return DesktopChatArtifactPreviewState(entry: entry, path: path)
        }
        return nil
    }

    private var sanitizedTitle: String {
        RichOutputSanitizer.sanitized(entry.title)
    }

    private var sanitizedDetail: String {
        RichOutputSanitizer.sanitized(entry.detail)
    }

    private var sanitizedBody: String {
        RichOutputSanitizer.sanitized(entry.body)
    }

    private var sanitizedPendingStatusText: String {
        RichOutputSanitizer.sanitized(pendingStatusText)
    }
}

struct DesktopChatArtifactPreviewTrigger: View {
    let preview: DesktopChatArtifactPreviewState
    let onPreview: () -> Void

    var body: some View {
        HStack(spacing: 6) {
            DesktopChatArtifactPreviewButton(
                title: "Preview Artifact",
                systemImageName: "doc.text.magnifyingglass",
                action: onPreview
            )
            .fixedSize(horizontal: true, vertical: true)
            Text(preview.path)
                .font(.caption2.monospaced())
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .textSelection(.enabled)
        }
        .padding(.leading, 11)
    }
}

struct DesktopChatArtifactPreviewButton: NSViewRepresentable {
    let title: String
    let systemImageName: String
    let action: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(action: action)
    }

    func makeNSView(context: Context) -> NSButton {
        let button = NSButton(title: title, target: context.coordinator, action: #selector(Coordinator.performAction))
        button.bezelStyle = .rounded
        button.controlSize = .small
        button.image = NSImage(systemSymbolName: systemImageName, accessibilityDescription: nil)
        button.imagePosition = .imageLeading
        button.setContentHuggingPriority(.required, for: .horizontal)
        button.setContentCompressionResistancePriority(.required, for: .horizontal)
        button.setAccessibilityLabel(title)
        return button
    }

    func updateNSView(_ button: NSButton, context: Context) {
        context.coordinator.action = action
        button.title = title
        button.image = NSImage(systemSymbolName: systemImageName, accessibilityDescription: nil)
        button.setAccessibilityLabel(title)
    }

    final class Coordinator: NSObject {
        var action: () -> Void

        init(action: @escaping () -> Void) {
            self.action = action
        }

        @objc
        func performAction() {
            action()
        }
    }
}

struct DesktopChatUserBubbleView: View {
    let messageBody: String

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            Spacer(minLength: 72)
            Text(messageBody.isEmpty ? "…" : messageBody)
                .font(.body)
                .textSelection(.enabled)
                .padding(.horizontal, 12)
                .padding(.vertical, 9)
                .background(
                    RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.lg)
                        .fill(Color.secondary.opacity(0.10))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.lg)
                        .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline), lineWidth: 1)
                )
                .frame(maxWidth: 560, alignment: .leading)
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("User message: \(accessibilityMessageBody)")
    }

    private var accessibilityMessageBody: String {
        messageBody.isEmpty ? "Empty" : messageBody
    }
}

struct DesktopChatAssistantDocumentView: View {
    let messageBody: String
    let isPending: Bool
    let isStreaming: Bool
    let pendingStatusText: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if isPending {
                pendingAssistantView
            } else {
                DesktopChatMarkdownBodyView(
                    rawText: messageBody.isEmpty ? "…" : messageBody,
                    isStreaming: isStreaming
                )
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 4)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Assistant message")
    }

    private var pendingAssistantView: some View {
        HStack(alignment: .center, spacing: 8) {
            ProgressView()
                .controlSize(.small)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text("Thinking...")
                    .font(.body)
                if pendingStatusText.isEmpty == false {
                    Text(pendingStatusText)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Assistant is thinking")
    }
}

struct DesktopChatActivityBlockView: View {
    enum ActivityKind {
        case reasoning
        case tool
    }

    let kind: ActivityKind
    let title: String
    let messageBody: String
    let detail: String
    let isStreaming: Bool
    @State private var isExpanded: Bool

    init(
        kind: ActivityKind,
        title: String,
        messageBody: String,
        detail: String,
        isStreaming: Bool
    ) {
        self.kind = kind
        self.title = title
        self.messageBody = messageBody
        self.detail = detail
        self.isStreaming = isStreaming
        _isExpanded = State(initialValue: isStreaming)
    }

    var body: some View {
        HStack(alignment: .top, spacing: 9) {
            Rectangle()
                .fill(tint.opacity(0.55))
                .frame(width: 2)
                .padding(.vertical, 5)

            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Button {
                        isExpanded.toggle()
                    } label: {
                        Image(systemName: isExpanded ? "chevron.down" : "chevron.right")
                            .font(.caption2.weight(.semibold))
                            .frame(width: 14, height: 14)
                    }
                    .buttonStyle(.plain)
                    .help(isExpanded ? "Hide activity details" : "Show activity details")
                    .accessibilityLabel(isExpanded ? "Hide Activity Details" : "Show Activity Details")

                    Image(systemName: systemImageName)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(tint)
                        .frame(width: 16)
                    Text(summaryText)
                        .font(.caption.weight(.semibold))
                        .textSelection(.enabled)
                    if detail.isEmpty == false {
                        Text(detail)
                            .font(.caption2.monospaced())
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    } else if title.isEmpty == false {
                        Text(title)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                    }
                }

                if isExpanded {
                    activityBody
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 4)
        .padding(.vertical, 2)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(summaryText)
        .onChange(of: isStreaming) { _, newValue in
            isExpanded = newValue
        }
    }

    @ViewBuilder
    var activityBody: some View {
        if messageBody.isEmpty {
            Text(isStreaming ? "Waiting for details..." : "No details recorded.")
                .font(.caption)
                .foregroundStyle(.secondary)
        } else if kind == .reasoning && DesktopChatMarkdownRenderer.usesMarkdown(for: .reasoning) {
            DesktopChatMarkdownBodyView(rawText: messageBody, isStreaming: isStreaming)
        } else {
            Text(messageBody)
                .font(kind == .tool ? .caption.monospaced() : .caption)
                .textSelection(.enabled)
        }
    }

    var summaryText: String {
        switch kind {
        case .reasoning:
            return isStreaming ? "Thinking..." : "Thought recorded"
        case .tool:
            return isStreaming ? "Calling tool" : "Tool completed"
        }
    }

    var systemImageName: String {
        switch kind {
        case .reasoning:
            return "brain.head.profile"
        case .tool:
            return "hammer"
        }
    }

    var tint: Color {
        switch kind {
        case .reasoning:
            return MelixDesignTokens.BubbleTint.reasoning
        case .tool:
            return MelixDesignTokens.BubbleTint.tool
        }
    }
}

private struct DesktopChatErrorBlockView: View {
    let title: String
    let messageBody: String
    let detail: String

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(MelixDesignTokens.StatusColor.error)
                Text(title.isEmpty ? "Error" : title)
                    .font(.headline)
                if detail.isEmpty == false {
                    Text(detail)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                }
            }
            Text(messageBody.isEmpty ? "Request failed." : messageBody)
                .font(.body)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(
            RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.lg)
                .fill(MelixDesignTokens.BubbleTint.error.opacity(MelixDesignTokens.BubbleOpacity.error))
        )
        .overlay(
            RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.lg)
                .stroke(MelixDesignTokens.StatusColor.error.opacity(0.22), lineWidth: 1)
        )
    }
}
