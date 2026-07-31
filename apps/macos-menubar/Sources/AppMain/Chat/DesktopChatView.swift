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
    static let composerMinHeight: CGFloat = 40
    static let readableWorkspaceMaxWidth: CGFloat = 980
    static let transcriptTurnMaxWidth: CGFloat = 780
    static let assistantAvatarSize: CGFloat = 27
}

enum DesktopChatCapabilityGlyphMetrics {
    static let controlSize: CGFloat = 28
    static let statusMarkSize: CGFloat = 6
    static let maximumClusterHeight: CGFloat = 30
}

struct DesktopChatModelIdentityPresentation: Equatable {
    let canonicalID: String
    let displayName: String
    let quantizationLabel: String?

    init(modelID: String) {
        let canonicalID = modelID.trimmingCharacters(in: .whitespacesAndNewlines)
        self.canonicalID = canonicalID

        let leaf = canonicalID.split(separator: "/", omittingEmptySubsequences: true).last.map(String.init) ?? canonicalID
        var components = leaf
            .split(separator: "-", omittingEmptySubsequences: true)
            .map(String.init)

        if components.count >= 2,
           components.last?.lowercased() == "bit",
           components[components.count - 2].allSatisfy(\.isNumber) {
            quantizationLabel = "\(components[components.count - 2])-bit"
            components.removeLast(2)
        } else if let quantizationIndex = components.indices.reversed().first(where: {
            Self.quantizationLabel(for: components[$0]) != nil
        }) {
            quantizationLabel = Self.quantizationLabel(for: components[quantizationIndex])
            if components[quantizationIndex].lowercased().hasPrefix("q") {
                components.removeSubrange(quantizationIndex..<components.endIndex)
            } else {
                components.remove(at: quantizationIndex)
            }
        } else {
            quantizationLabel = nil
        }

        if components.last?.lowercased() == "mlx" {
            components.removeLast()
        }
        if let trailingQuantizationIndex = components.indices.reversed().first(where: {
            components[$0].lowercased().first == "q"
                && components[$0].lowercased().dropFirst().first?.isNumber == true
        }) {
            components.removeSubrange(trailingQuantizationIndex..<components.endIndex)
        }

        let humanReadableName = components
            .map(Self.humanizedComponent)
            .joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        displayName = humanReadableName.isEmpty ? (canonicalID.isEmpty ? "Unknown Model" : canonicalID) : humanReadableName
    }

    private static func quantizationLabel(for component: String) -> String? {
        let lowercased = component.lowercased()
        if lowercased.hasSuffix("bit") {
            let bits = lowercased.dropLast(3)
            if bits.isEmpty == false, bits.allSatisfy(\.isNumber) {
                return "\(bits)-bit"
            }
        }
        if lowercased.hasPrefix("int") || lowercased.hasPrefix("fp") || lowercased.hasPrefix("bf") {
            let suffix = lowercased.drop { $0.isLetter }
            if suffix.isEmpty == false, suffix.allSatisfy(\.isNumber) {
                return lowercased.uppercased()
            }
        }
        if lowercased.first == "q",
           lowercased.dropFirst().first?.isNumber == true {
            return component.uppercased()
        }
        return nil
    }

    private static func humanizedComponent(_ component: String) -> String {
        let lowercased = component.lowercased()
        let fixedNames = [
            "gemma": "Gemma",
            "llama": "Llama",
            "qwen": "Qwen",
            "it": "IT",
            "mlx": "MLX",
            "vlm": "VLM",
            "llm": "LLM",
            "ocr": "OCR",
            "optiq": "OptiQ",
        ]
        if let fixedName = fixedNames[lowercased] {
            return fixedName
        }
        if let suffix = lowercased.last,
           ["b", "m", "k"].contains(String(suffix)),
           lowercased.dropLast().allSatisfy({ $0.isNumber || $0 == "." }) {
            return "\(lowercased.dropLast())\(String(suffix).uppercased())"
        }
        if component.contains(where: \.isUppercase) {
            return component
        }
        return lowercased.prefix(1).uppercased() + String(lowercased.dropFirst())
    }
}

private enum DesktopChatStarterPrompt: String, CaseIterable, Identifiable {
    case providerStatus = "Explain current provider status"
    case benchmark = "Benchmark the active model"
    case syntheticDataset = "Draft a synthetic dataset recipe"
    case apiExample = "Show a local API request"

    var id: String { rawValue }

    var detail: String {
        switch self {
        case .providerStatus:
            return "Summarize provider, model, queue, and recent warnings."
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
        case .providerStatus:
            return "Explain the current Melix provider status and call out anything that needs attention."
        case .benchmark:
            return "Set up a quick benchmark for the active model and explain what metrics to watch."
        case .syntheticDataset:
            return "Draft a synthetic dataset recipe for event extraction and list the fields I should verify."
        case .apiExample:
            return "Show a local API request for the selected Melix provider and explain the auth requirements."
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

enum DesktopChatReasoningPresentationPolicy {
    static let maximumStreamingHeight: CGFloat = 128
    static let streamingBodyOpacity = 0.72
    static let bottomTolerance: CGFloat = 8

    static func initiallyExpanded(isStreaming: Bool) -> Bool {
        isStreaming
    }

    static func summaryText(isStreaming: Bool, elapsedSeconds: Int?) -> String {
        if isStreaming {
            return "Thinking..."
        }
        if let elapsedSeconds {
            return "Thought for \(elapsedSeconds) seconds"
        }
        return "Thought recorded"
    }

    static func accessibilityAnnouncement(isStreaming: Bool) -> String {
        isStreaming
            ? "Public reasoning is streaming."
            : "Public reasoning completed."
    }

    static func compactStreamingAttributedText(
        from rawText: String,
        includesCaret: Bool,
        caretVisible: Bool
    ) -> AttributedString {
        var result = AttributedString()
        let lines = rawText.split(separator: "\n", omittingEmptySubsequences: false)

        for (index, line) in lines.enumerated() {
            if index > 0 {
                result.append(AttributedString("\n"))
            }

            let sourceLine = String(line)
            let formattedLine = DesktopChatMarkdownInlineFormatter.attributedString(from: sourceLine)
            if formattedLine.characters.isEmpty && sourceLine.isEmpty == false {
                result.append(AttributedString(sourceLine))
            } else {
                result.append(formattedLine)
            }
        }

        if includesCaret {
            var caret = AttributedString("▏")
            caret.foregroundColor = caretVisible ? MelixDesignTokens.accent : .clear
            result.append(caret)
        }

        return result
    }

    static func isAtBottom(
        contentOffsetY: CGFloat,
        contentHeight: CGFloat,
        viewportHeight: CGFloat
    ) -> Bool {
        let maximumOffset = max(0, contentHeight - viewportHeight)
        return contentOffsetY >= maximumOffset - bottomTolerance
    }
}

struct DesktopChatTranscriptPresentationRow: Identifiable {
    let index: Int
    let entry: DesktopChatTranscriptEntry

    var id: String { entry.id }
}

enum DesktopChatComposerKeyPolicy {
    enum Action: Equatable {
        case submit
        case insertNewline
        case passThrough
    }

    static let returnKeyCode: UInt16 = 36
    static let keypadEnterKeyCode: UInt16 = 76
    static let postCompositionGuardInterval: TimeInterval = 0.05

    static func action(keyCode: UInt16, modifiers: NSEvent.ModifierFlags) -> Action {
        guard keyCode == returnKeyCode || keyCode == keypadEnterKeyCode else {
            return .passThrough
        }
        let semanticModifiers = modifiers.intersection([.command, .shift, .option, .control])
        if semanticModifiers == [.command] {
            return .insertNewline
        }
        return semanticModifiers.isEmpty ? .submit : .passThrough
    }
}

enum DesktopChatComposerReturnCommandPolicy {
    static func action(selector: Selector, modifiers: NSEvent.ModifierFlags) -> DesktopChatComposerKeyPolicy.Action {
        guard isReturnCommandSelector(selector) else {
            return .passThrough
        }
        let semanticModifiers = modifiers.intersection([.command, .shift, .option, .control])
        if semanticModifiers == [.command] {
            return .insertNewline
        }
        return semanticModifiers.isEmpty ? .submit : .passThrough
    }

    static func isReturnCommandSelector(_ selector: Selector) -> Bool {
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
                    detail: "Start a chat after choosing a local or remote provider. Sessions keep transcript, model, and export context together."
                ) {
                    VStack(spacing: MelixDesignTokens.Spacing.sm) {
                        Button("New Chat", action: createChatSessionAction)
                        .buttonStyle(.borderedProminent)

                        Button("Open Providers", action: openServerAction)
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
                                onClear: {
                                    viewModel.selectChatSession(id: session.id)
                                    viewModel.clearChatTranscript()
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
    @Environment(\.accessibilityReduceMotion) private var accessibilityReduceMotion

    private var isSendDisabled: Bool {
        viewModel.chatComposerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        || viewModel.isChatStreaming
        || viewModel.isSelectedChatProviderReady == false
    }

    private var selectedChatModelNeedsAttachment: Bool {
        guard let serverSession = viewModel.selectedChatServerSession else {
            return false
        }
        let modelID = serverSession.modelID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard modelID.isEmpty == false else {
            return true
        }
        return viewModel.chatModelNeedsAttachment(modelID: modelID)
    }

    private func submitChatPrompt() {
        Task { await viewModel.submitChatPrompt() }
    }

    func openServerSurface() {
        viewModel.selectSurface(.server)
    }

    func startSelectedChatServerSession() {
        Task {
            guard let serverSessionID = viewModel.selectedChatServerSession?.id else {
                openServerSurface()
                return
            }
            await viewModel.startServerSession(id: serverSessionID)
        }
    }

    func resumeSelectedChatServerSession() {
        Task {
            guard let serverSessionID = viewModel.selectedChatServerSession?.id else {
                openServerSurface()
                return
            }
            await viewModel.resumeServerSession(id: serverSessionID)
        }
    }

    func wakeSelectedChatServerSession() {
        Task {
            guard let serverSessionID = viewModel.selectedChatServerSession?.id else {
                openServerSurface()
                return
            }
            await viewModel.wakeServerSession(id: serverSessionID)
        }
    }

    func openModelsSurface() {
        viewModel.selectSurface(.models)
    }

    func openDiagnosticsSurface() {
        viewModel.selectToolSection(.diagnostics)
    }

    private var chatTranscriptScrollSnapshot: DesktopChatTranscriptAutoScroll.Snapshot {
        DesktopChatTranscriptAutoScroll.snapshot(
            transcript: viewModel.chatTranscript,
            isStreaming: viewModel.isChatStreaming,
            statusText: viewModel.chatStatusText
        )
    }

    private var chatTranscriptPresentationRows: [DesktopChatTranscriptPresentationRow] {
        viewModel.chatTranscript.indices.compactMap { index in
            let entry = viewModel.chatTranscript[index]
            guard viewModel.shouldDisplayChatTranscriptEntry(entry) else {
                return nil
            }
            return DesktopChatTranscriptPresentationRow(index: index, entry: entry)
        }
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

    private func showsAssistantRole(at index: Int) -> Bool {
        guard viewModel.chatTranscript.indices.contains(index),
              viewModel.chatTranscript[index].kind != .user
        else {
            return false
        }
        guard index > viewModel.chatTranscript.startIndex else {
            return true
        }
        return viewModel.chatTranscript[index - 1].kind == .user
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                VStack(alignment: .leading, spacing: 5) {
                    Text(viewModel.selectedChatSession?.title ?? "Chat")
                        .font(.headline.weight(.semibold))
                    if let branch = viewModel.selectedChatSession?.displayBranchTitle {
                        DesktopChatSessionBranchBadgeView(branch: branch)
                    }
                }
                Spacer(minLength: 12)
                HStack(spacing: 8) {
                    DesktopChatServerPicker(viewModel: viewModel)
                    if let serverSession = viewModel.selectedChatServerSession {
                        DesktopChatModelIdentityButton(serverSession: serverSession)
                    } else if let providerTarget = viewModel.selectedChatProviderTarget {
                        DesktopChatModelIdentityButton(providerTarget: providerTarget)
                    }
                }
                .alignmentGuide(.firstTextBaseline) { dimensions in
                    dimensions[VerticalAlignment.center]
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        if viewModel.chatTranscript.isEmpty == false {
                            ForEach(chatTranscriptPresentationRows) { presentationRow in
                                let index = presentationRow.index
                                let entry = presentationRow.entry
                                DesktopChatTranscriptRowView(
                                    entry: entry,
                                    isPending: viewModel.isPendingAssistantTranscriptEntry(entry),
                                    isStreaming: viewModel.isStreamingChatTranscriptEntry(entry),
                                    showsAssistantRole: showsAssistantRole(at: index),
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
                    .frame(maxWidth: DesktopChatLayoutMetrics.transcriptTurnMaxWidth)
                    .frame(maxWidth: .infinity)
                }
                .onAppear {
                    scrollChatTranscriptToBottom(proxy, animated: false)
                }
                .onChange(of: chatTranscriptScrollSnapshot) { _, _ in
                    scrollChatTranscriptToBottom(
                        proxy,
                        animated: accessibilityReduceMotion == false
                    )
                }
            }

            DesktopChatComposerSurface(
                text: Binding(
                    get: { viewModel.chatComposerText },
                    set: { viewModel.chatComposerText = $0 }
                ),
                isThinkingEnabled: Binding(
                    get: { viewModel.chatThinkingEnabled },
                    set: { viewModel.chatThinkingEnabled = $0 }
                ),
                isSubmitAvailable: viewModel.isChatStreaming == false
                && viewModel.isSelectedChatProviderReady,
                isSendDisabled: isSendDisabled,
                isStreaming: viewModel.isChatStreaming,
                serverSession: viewModel.selectedChatServerSession,
                remoteProviderIsSelected: viewModel.selectedChatProviderTarget?.kind == .remoteServer,
                capabilities: viewModel.chatCapabilities,
                isModelMissing: selectedChatModelNeedsAttachment,
                onCommandSubmit: { draft in
                    viewModel.chatComposerText = draft
                    submitChatPrompt()
                },
                onSubmit: submitChatPrompt,
                onOpenServer: openServerSurface,
                onOpenModels: openModelsSurface,
                onRunCapabilitiesTest: openDiagnosticsSurface,
                onStartServer: startSelectedChatServerSession,
                onResumeServer: resumeSelectedChatServerSession,
                onWakeServer: wakeSelectedChatServerSession
            )
        }
        .padding(16)
        .onAppear {
            viewModel.setChatPresentationReduceMotion(accessibilityReduceMotion)
        }
        .onChange(of: accessibilityReduceMotion) { _, reduceMotion in
            viewModel.setChatPresentationReduceMotion(reduceMotion)
        }
    }
}

struct DesktopChatSessionInspector: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        DesktopChatPrecisionInspector(
            providerTarget: viewModel.selectedChatProviderTarget,
            serverSession: viewModel.selectedChatServerSession,
            capabilities: viewModel.chatCapabilities,
            isStreaming: viewModel.isChatStreaming,
            usageText: viewModel.lastChatUsageText,
            actions: inspectorActions,
            onStartProvider: startSelectedProvider,
            onResumeProvider: resumeSelectedProvider
        )
    }

    private var inspectorActions: [DesktopInspectorActionRow] {
        [
            DesktopInspectorActionRow(title: "Open Command Center", systemImage: "command.circle") {
                viewModel.selectSurface(.commandCenter)
            },
            DesktopInspectorActionRow(title: "Open Providers", systemImage: "server.rack") {
                viewModel.selectSurface(.server)
            },
            DesktopInspectorActionRow(title: "Open Diagnostics", systemImage: "stethoscope") {
                viewModel.selectToolSection(.diagnostics)
            },
        ]
    }

    func startSelectedProvider() {
        guard let serverSessionID = viewModel.selectedChatServerSession?.id else {
            viewModel.selectSurface(.server)
            return
        }
        Task { await viewModel.startServerSession(id: serverSessionID) }
    }

    func resumeSelectedProvider() {
        guard let serverSessionID = viewModel.selectedChatServerSession?.id else {
            viewModel.selectSurface(.server)
            return
        }
        Task { await viewModel.resumeServerSession(id: serverSessionID) }
    }
}

private struct DesktopChatPrecisionInspector: View {
    let providerTarget: RuntimeProviderTargetState?
    let serverSession: DesktopServerSessionState?
    let capabilities: [DesktopChatCapabilityRow]
    let isStreaming: Bool
    let usageText: String
    let actions: [DesktopInspectorActionRow]
    let onStartProvider: () -> Void
    let onResumeProvider: () -> Void

    private var modelIdentity: DesktopChatModelIdentityPresentation {
        DesktopChatModelIdentityPresentation(modelID: providerTarget?.modelID ?? "")
    }

    private var primaryCapabilities: [DesktopChatCapabilityRow] {
        let chatCapabilities = capabilities.filter { ["text", "vlm"].contains($0.id) }
        return Array((chatCapabilities.isEmpty ? capabilities : chatCapabilities).prefix(2))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            identityRow
                .padding(.bottom, 12)

            Divider()
                .opacity(0.55)
                .padding(.bottom, 7)

            if isStreaming {
                DesktopChatInspectorTransientRow(
                    systemImage: "waveform",
                    title: "Generating response",
                    tint: MelixDesignTokens.accent
                )
            } else if let serverSession {
                providerTransientRow(serverSession)
            }

            if let serverSession {
                DesktopChatInspectorLedgerRow(
                    systemImage: "waveform.path.ecg",
                    value: serverSession.lifecycle.rawValue,
                    tail: serverSession.powerState.rawValue,
                    helpText: serverSession.lifecycleSummaryText
                )
                DesktopChatInspectorLedgerRow(
                    systemImage: "network",
                    value: serverSession.effectiveListenerLabel,
                    tail: "/v1",
                    helpText: serverSession.effectiveBaseURL
                )
                DesktopChatInspectorLedgerRow(
                    systemImage: "number",
                    value: usageText.isEmpty ? "No usage" : usageText,
                    tail: "tokens",
                    helpText: usageText.isEmpty ? "No token usage recorded" : usageText
                )
                DesktopChatInspectorLedgerRow(
                    systemImage: "checkmark.shield",
                    value: trustLabel(serverSession),
                    tail: "trust",
                    helpText: serverSession.sharedAccessSummaryText
                )
                DesktopChatInspectorLedgerRow(
                    systemImage: "clock",
                    value: serverSession.idleTimerSeconds > 0 ? "\(serverSession.idleTimerSeconds)s" : "Idle",
                    tail: "timer",
                    helpText: serverSession.idlePolicySummaryText
                )
            } else if let providerTarget {
                DesktopChatInspectorLedgerRow(
                    systemImage: "waveform.path.ecg",
                    value: providerTarget.statusText,
                    tail: providerTarget.badgeText,
                    helpText: providerTarget.detailText
                )
                DesktopChatInspectorLedgerRow(
                    systemImage: "network",
                    value: providerTarget.endpointText,
                    tail: "remote",
                    helpText: providerTarget.endpointText
                )
                DesktopChatInspectorLedgerRow(
                    systemImage: "number",
                    value: usageText.isEmpty ? "No usage" : usageText,
                    tail: "tokens",
                    helpText: usageText.isEmpty ? "No token usage recorded" : usageText
                )
                DesktopChatInspectorLedgerRow(
                    systemImage: "checkmark.shield",
                    value: "Remote provider",
                    tail: "trust",
                    helpText: "Requests are sent directly to the configured remote Provider."
                )
            } else {
                DesktopChatInspectorLedgerRow(
                    systemImage: "server.rack",
                    value: "Choose a Provider",
                    tail: "route",
                    helpText: "Choose a local or remote Provider for this Chat."
                )
            }

            HStack(spacing: 5) {
                ForEach(actions.prefix(3)) { action in
                    Button(action: action.action) {
                        Image(systemName: action.systemImage)
                            .font(.system(size: 13, weight: .medium))
                            .frame(width: 30, height: 28)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(MelixDesignTokens.accent)
                    .background(Color.secondary.opacity(0.045), in: RoundedRectangle(cornerRadius: 6))
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline), lineWidth: 1)
                    )
                    .help(action.title)
                    .accessibilityLabel(action.title)
                }
            }
            .padding(.top, 9)
            .overlay(alignment: .top) {
                Divider().opacity(0.55)
            }

            Spacer(minLength: 0)
        }
        .padding(12)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Chat Inspector")
    }

    private var identityRow: some View {
        HStack(alignment: .top, spacing: 7) {
            Circle()
                .fill(providerStatusColor)
                .frame(width: 7, height: 7)
                .padding(.top, 5)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 3) {
                Text(providerTarget?.title ?? "No Provider")
                    .font(.caption.weight(.semibold))
                    .lineLimit(1)
                HStack(spacing: 5) {
                    Text(providerTarget == nil ? "Choose a provider" : modelIdentity.displayName)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.tail)
                    if let quantizationLabel = modelIdentity.quantizationLabel {
                        Text(quantizationLabel)
                            .font(.system(size: 8, weight: .medium, design: .monospaced))
                            .foregroundStyle(MelixDesignTokens.accent)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 2)
                            .background(MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.weak), in: RoundedRectangle(cornerRadius: 4))
                            .fixedSize()
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .help(modelIdentity.canonicalID)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(identityAccessibilityLabel)

            DesktopChatCapabilityGlyphCluster(capabilities: primaryCapabilities)
        }
    }

    @ViewBuilder
    private func providerTransientRow(_ serverSession: DesktopServerSessionState) -> some View {
        switch serverSession.lifecycle {
        case .draft, .stopped, .error, .unavailable:
            DesktopChatInspectorTransientRow(
                systemImage: "power",
                title: serverSession.lifecycle == .error ? "Provider needs recovery" : "Provider stopped",
                tint: serverSession.lifecycle == .error
                    ? MelixDesignTokens.StatusColor.error
                    : MelixDesignTokens.StatusColor.warning,
                actionTitle: "Start",
                action: onStartProvider
            )
        case .paused:
            DesktopChatInspectorTransientRow(
                systemImage: "pause.circle",
                title: "Provider paused",
                tint: MelixDesignTokens.StatusColor.warning,
                actionTitle: "Resume",
                action: onResumeProvider
            )
        case .starting, .stopping:
            DesktopChatInspectorTransientRow(
                systemImage: "arrow.triangle.2.circlepath",
                title: "Provider \(serverSession.lifecycle.rawValue.lowercased())",
                tint: MelixDesignTokens.accent
            )
        case .running, .sleeping:
            EmptyView()
        }
    }

    private var providerStatusColor: Color {
        if providerTarget?.kind == .remoteServer {
            return MelixDesignTokens.StatusColor.success
        }
        switch serverSession?.lifecycle {
        case .running, .sleeping:
            return MelixDesignTokens.StatusColor.success
        case .starting, .stopping:
            return MelixDesignTokens.StatusColor.info
        case .error:
            return MelixDesignTokens.StatusColor.error
        case .draft, .paused, .stopped, .unavailable:
            return MelixDesignTokens.StatusColor.warning
        case nil:
            return Color.secondary.opacity(0.45)
        }
    }

    private var identityAccessibilityLabel: String {
        guard let providerTarget else {
            return "No Provider selected"
        }
        let quantization = modelIdentity.quantizationLabel.map { ", quantization \($0)" } ?? ""
        return "\(providerTarget.title), model \(modelIdentity.displayName)\(quantization), canonical ID \(modelIdentity.canonicalID)"
    }

    private func trustLabel(_ serverSession: DesktopServerSessionState) -> String {
        switch serverSession.sharedAccessState {
        case .localOnly:
            return "Local only"
        case .configuredDisabled:
            return "Configured"
        case .enabled:
            return serverSession.accessKeyCount == 1 ? "1 shared key" : "\(serverSession.accessKeyCount) shared keys"
        }
    }
}

private struct DesktopChatInspectorLedgerRow: View {
    let systemImage: String
    let value: String
    let tail: String
    let helpText: String

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: systemImage)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(MelixDesignTokens.accent)
                .frame(width: 25)
                .accessibilityHidden(true)
            Text(value)
                .font(.caption2.weight(.medium))
                .lineLimit(1)
                .truncationMode(.middle)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
            Text(tail)
                .font(.system(size: 8))
                .foregroundStyle(.tertiary)
                .lineLimit(1)
        }
        .frame(minHeight: 31)
        .padding(.horizontal, 5)
        .help(helpText)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(tail), \(value). \(helpText)")
    }
}

private struct DesktopChatInspectorTransientRow: View {
    let systemImage: String
    let title: String
    let tint: Color
    var actionTitle: String? = nil
    var action: () -> Void = {}

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: systemImage)
                .font(.system(size: 13, weight: .medium))
                .frame(width: 25)
            Text(title)
                .font(.caption2.weight(.semibold))
                .lineLimit(1)
                .frame(maxWidth: .infinity, alignment: .leading)
            if let actionTitle {
                Button(actionTitle, action: action)
                    .buttonStyle(.borderless)
                    .font(.system(size: 9, weight: .semibold))
                    .accessibilityLabel("\(actionTitle) Provider")
            }
        }
        .foregroundStyle(tint)
        .frame(minHeight: 31)
        .padding(.horizontal, 5)
        .background(tint.opacity(MelixDesignTokens.StateOpacity.background), in: RoundedRectangle(cornerRadius: 6))
        .accessibilityElement(children: .contain)
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
                Text("Start from a provider-aware prompt, or continue a recent local session.")
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

    private var selectedProviderBinding: Binding<String> {
        Binding(
            get: { viewModel.selectedChatSession?.providerTarget?.id ?? "" },
            set: { viewModel.bindSelectedChatSessionToProvider(targetID: $0) }
        )
    }

    var body: some View {
        if viewModel.chatProviderTargets.isEmpty {
            Button {
                viewModel.selectSurface(.server)
            } label: {
                Label("Choose Provider", systemImage: "server.rack")
                    .labelStyle(.titleAndIcon)
            }
            .font(.caption2)
            .buttonStyle(.borderless)
            .help("Open Providers to create a chat provider")
            .accessibilityLabel("Choose Chat Provider")
        } else {
            Picker("Provider", selection: selectedProviderBinding) {
                Text("Choose Provider").tag("")
                ForEach(viewModel.chatProviderTargets) { target in
                    Label(
                        target.title,
                        systemImage: target.kind == .localServer ? "desktopcomputer" : "network"
                    )
                    .tag(target.id)
                }
            }
            .labelsHidden()
            .pickerStyle(.menu)
            .controlSize(.small)
            .frame(maxWidth: 132)
            .disabled(viewModel.isChatStreaming)
            .help("Choose the provider for this chat session")
            .accessibilityLabel("Chat Provider")
        }
    }
}

struct DesktopChatModelIdentityButton: View {
    let providerTitle: String
    let providerStatusText: String
    let modelID: String
    let trustText: String
    @State private var showsModelDetails = false

    init(serverSession: DesktopServerSessionState) {
        providerTitle = serverSession.title
        providerStatusText = serverSession.lifecycle.rawValue
        modelID = serverSession.modelID
        trustText = serverSession.sharedAccessState == .localOnly ? "Local trust" : "Shared access"
    }

    init(providerTarget: RuntimeProviderTargetState) {
        providerTitle = providerTarget.title
        providerStatusText = providerTarget.statusText
        modelID = providerTarget.modelID
        trustText = providerTarget.kind == .localServer ? "Local trust" : "Remote provider"
    }

    private var identity: DesktopChatModelIdentityPresentation {
        DesktopChatModelIdentityPresentation(modelID: modelID)
    }

    var body: some View {
        Button {
            showsModelDetails.toggle()
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "cube")
                    .font(.system(size: 13, weight: .medium))
                    .foregroundStyle(MelixDesignTokens.accent)
                    .accessibilityHidden(true)
                Text(identity.displayName)
                    .font(.caption2.weight(.medium))
                    .lineLimit(1)
                    .truncationMode(.tail)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if let quantizationLabel = identity.quantizationLabel {
                    Text(quantizationLabel)
                        .font(.system(size: 8, weight: .medium, design: .monospaced))
                        .foregroundStyle(MelixDesignTokens.accent)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.weak), in: RoundedRectangle(cornerRadius: 4))
                        .fixedSize()
                        .layoutPriority(1)
                }
            }
            .padding(.horizontal, 8)
            .frame(height: 28)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .frame(maxWidth: 190)
        .background(Color.secondary.opacity(0.045), in: RoundedRectangle(cornerRadius: 7))
        .overlay(
            RoundedRectangle(cornerRadius: 7)
                .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline), lineWidth: 1)
        )
        .help(identity.canonicalID)
        .accessibilityLabel(modelAccessibilityLabel)
        .accessibilityHint("Shows the canonical model ID and copy action")
        .popover(isPresented: $showsModelDetails, arrowEdge: .top) {
            modelDetails
        }
    }

    var modelDetails: some View {
        VStack(alignment: .leading, spacing: 10) {
            VStack(alignment: .leading, spacing: 3) {
                Text(identity.displayName)
                    .font(.headline)
                Text("\(providerTitle) · \(providerStatusText)")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            HStack(alignment: .top, spacing: 7) {
                Text(identity.canonicalID)
                    .font(.caption2.monospaced())
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Button {
                    copyCanonicalID()
                } label: {
                    Image(systemName: "doc.on.doc")
                        .font(.system(size: 12, weight: .medium))
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.plain)
                .foregroundStyle(MelixDesignTokens.accent)
                .background(Color.primary.opacity(0.035), in: RoundedRectangle(cornerRadius: 5))
                .help("Copy Model ID")
                .accessibilityLabel("Copy Model ID")
            }
            .padding(8)
            .background(Color.secondary.opacity(0.055), in: RoundedRectangle(cornerRadius: 7))

            HStack(spacing: 10) {
                Text("Canonical ID")
                Text(trustText)
                if let quantizationLabel = identity.quantizationLabel {
                    Text("Quantization \(quantizationLabel)")
                }
            }
            .font(.system(size: 9))
            .foregroundStyle(.secondary)
        }
        .padding(12)
        .frame(width: 308)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Model identity details")
    }

    private var modelAccessibilityLabel: String {
        let quantization = identity.quantizationLabel.map { ", quantization \($0)" } ?? ""
        return "Model \(identity.displayName)\(quantization), canonical ID \(identity.canonicalID)"
    }

    func copyCanonicalID(
        to pasteboard: any RuntimePasteboardWriting = NSPasteboard.general
    ) {
        pasteboard.clearContents()
        _ = pasteboard.setString(identity.canonicalID, forType: .string)
    }
}

private struct DesktopChatCapabilityGlyphCluster: View {
    let capabilities: [DesktopChatCapabilityRow]

    var body: some View {
        HStack(spacing: 4) {
            ForEach(capabilities) { capability in
                DesktopChatCapabilityGlyphButton(capability: capability)
            }
        }
        .frame(maxHeight: DesktopChatCapabilityGlyphMetrics.maximumClusterHeight)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Model Capabilities")
    }
}

struct DesktopChatCapabilityGlyphButton: View {
    let capability: DesktopChatCapabilityRow
    @State private var showsDetail = false

    init(capability: DesktopChatCapabilityRow) {
        self.capability = capability
    }

    var body: some View {
        Button {
            showsDetail.toggle()
        } label: {
            ZStack {
                RoundedRectangle(cornerRadius: 7)
                    .fill(
                        capability.isReady
                            ? MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.weak)
                            : Color.secondary.opacity(0.045)
                    )
                Image(systemName: capability.systemImageName)
                    .font(.system(size: 14, weight: .medium))
                    .foregroundStyle(capability.isReady ? MelixDesignTokens.accent : Color.secondary)
                if capability.isReady == false {
                    Capsule()
                        .fill(Color.secondary.opacity(0.7))
                        .frame(width: 16, height: 1)
                        .rotationEffect(.degrees(-42))
                        .accessibilityHidden(true)
                }
                Circle()
                    .fill(capability.isReady ? MelixDesignTokens.StatusColor.success : Color.secondary.opacity(0.45))
                    .frame(
                        width: DesktopChatCapabilityGlyphMetrics.statusMarkSize,
                        height: DesktopChatCapabilityGlyphMetrics.statusMarkSize
                    )
                    .offset(x: 9, y: -9)
                    .accessibilityHidden(true)
            }
            .frame(
                width: DesktopChatCapabilityGlyphMetrics.controlSize,
                height: DesktopChatCapabilityGlyphMetrics.controlSize
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .overlay(
            RoundedRectangle(cornerRadius: 7)
                .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline), lineWidth: 1)
        )
        .help("\(capability.title) · \(capability.isReady ? "Ready" : "Unavailable") · \(capability.detail)")
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(capability.title)
        .accessibilityValue(capability.isReady ? "Ready" : "Unavailable")
        .accessibilityHint("Shows capability detail")
        .popover(isPresented: $showsDetail, arrowEdge: .top) {
            detailView
        }
    }

    var detailView: some View {
        VStack(alignment: .leading, spacing: 5) {
            Text(capability.title)
                .font(.headline)
            Label(
                capability.isReady ? "Ready" : "Unavailable",
                systemImage: capability.isReady ? "checkmark.circle.fill" : "circle.slash"
            )
            .font(.caption.weight(.medium))
            .foregroundStyle(capability.isReady ? MelixDesignTokens.StatusColor.success : Color.secondary)
            Text(capability.detail)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
        .padding(10)
        .frame(width: 220, alignment: .leading)
    }
}

private struct DesktopChatSessionRow: View {
    let session: DesktopChatSessionState
    let isSelected: Bool
    let onSelect: () -> Void
    let onFork: () -> Void
    let onExport: () -> Void
    let onClear: () -> Void
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

            DesktopChatSessionRowActions(
                onFork: onFork,
                onExport: onExport,
                onClear: onClear,
                onDelete: onDelete
            )
        }
        .padding(10)
        .melixSelection(isSelected)
    }
}

private struct DesktopChatSessionRowActions: View {
    let onFork: () -> Void
    let onExport: () -> Void
    let onClear: () -> Void
    let onDelete: () -> Void

    var body: some View {
        Menu {
            Button("Fork", action: onFork)
            Button("Export", action: onExport)
            Divider()
            Button("Clear Conversation", role: .destructive, action: onClear)
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

enum DesktopChatComposerSubmissionPolicy {
    static func canSubmit(
        text: String,
        isSubmitAvailable: Bool,
        isSendDisabled: Bool,
        isStreaming: Bool,
        hasRepairState: Bool
    ) -> Bool {
        text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
        && isSubmitAvailable
        && isSendDisabled == false
        && isStreaming == false
        && hasRepairState == false
    }
}

struct DesktopChatComposerSurface: View {
    @Binding var text: String
    @Binding var isThinkingEnabled: Bool
    @State private var editorHeight = DesktopChatComposerHeightPolicy.minimumHeight
    @State private var editorContentHeight = DesktopChatComposerHeightPolicy.minimumHeight
    @State private var isEditorExpanded = false
    @State private var isEditorFocused = false
    @State private var editorFocusRequestID: UUID?
    @State private var restoresFocusAfterRepair = false
    let isSubmitAvailable: Bool
    let isSendDisabled: Bool
    let isStreaming: Bool
    let serverSession: DesktopServerSessionState?
    var remoteProviderIsSelected = false
    let capabilities: [DesktopChatCapabilityRow]
    let isModelMissing: Bool
    let onCommandSubmit: (String) -> Void
    let onSubmit: () -> Void
    let onOpenServer: () -> Void
    let onOpenModels: () -> Void
    let onRunCapabilitiesTest: () -> Void
    let onStartServer: () -> Void
    let onResumeServer: () -> Void
    let onWakeServer: () -> Void

    var composerGate: DesktopChatComposerGate {
        DesktopChatComposerGate(
            serverSession: serverSession,
            remoteProviderIsSelected: remoteProviderIsSelected,
            capabilities: capabilities,
            isModelMissing: isModelMissing
        )
    }

    var canSubmit: Bool {
        DesktopChatComposerSubmissionPolicy.canSubmit(
            text: text,
            isSubmitAvailable: isSubmitAvailable,
            isSendDisabled: isSendDisabled,
            isStreaming: isStreaming,
            hasRepairState: composerGate.repairState != nil
        )
    }

    var shouldShowExpandControl: Bool {
        DesktopChatComposerHeightPolicy.isAtCollapsedCap(contentHeight: editorContentHeight)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let repairState = composerGate.repairState {
                DesktopChatComposerRepairStrip(
                    state: repairState,
                    onPrimaryAction: { performRepairAction(repairState.primaryActionKind) },
                    onOpenServer: onOpenServer,
                    onOpenModels: onOpenModels,
                    onRunCapabilitiesTest: onRunCapabilitiesTest
                )
            }

            editorPlane
            actionPlane
        }
        .background(
            RoundedRectangle(
                cornerRadius: MelixDesignTokens.Radius.composer,
                style: .continuous
            )
                .fill(Color(nsColor: .textBackgroundColor).opacity(0.82))
        )
        .clipShape(
            RoundedRectangle(
                cornerRadius: MelixDesignTokens.Radius.composer,
                style: .continuous
            )
        )
        .overlay(
            RoundedRectangle(
                cornerRadius: MelixDesignTokens.Radius.composer,
                style: .continuous
            )
            .stroke(
                isEditorFocused
                    ? MelixDesignTokens.accent.opacity(MelixDesignTokens.StrokeOpacity.focusedInput)
                    : Color.primary.opacity(MelixDesignTokens.StrokeOpacity.interactive),
                lineWidth: isEditorFocused ? 1.5 : 1
            )
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Chat Composer")
        .onChange(of: composerGate.repairState == nil) { _, isReady in
            guard isReady, restoresFocusAfterRepair else {
                return
            }
            restoresFocusAfterRepair = false
            requestEditorFocus()
        }
        .onChange(of: shouldShowExpandControl) { _, isAtCap in
            if isAtCap == false {
                isEditorExpanded = false
            }
        }
        .onChange(of: text.isEmpty) { _, isEmpty in
            if isEmpty {
                isEditorExpanded = false
            }
        }
        .onChange(of: isStreaming) { wasStreaming, isStreaming in
            guard wasStreaming == false, isStreaming else {
                return
            }
            DesktopChatAccessibilityAnnouncer.post(
                "Response is generating. The next draft remains editable and is saved."
            )
        }
    }

    var editorPlane: some View {
        ZStack(alignment: .topTrailing) {
            ZStack(alignment: .topLeading) {
                DesktopChatComposerTextView(
                    text: $text,
                    height: $editorHeight,
                    contentHeight: $editorContentHeight,
                    isFocused: $isEditorFocused,
                    isExpanded: isEditorExpanded,
                    focusRequestID: editorFocusRequestID,
                    isSubmitAvailable: canSubmit,
                    onCommandSubmit: onCommandSubmit
                )
                .frame(height: editorHeight)
                .padding(.trailing, shouldShowExpandControl ? 28 : 0)

                if text.isEmpty {
                    Text("Message Melix…")
                        .font(.body)
                        .foregroundStyle(.tertiary)
                        .padding(.top, 1)
                        .padding(.leading, 1)
                        .allowsHitTesting(false)
                        .accessibilityHidden(true)
                }
            }

            if shouldShowExpandControl {
                expandEditorButton
            }
        }
        .padding(.horizontal, 12)
        .padding(.top, 11)
        .padding(.bottom, 3)
    }

    var actionPlane: some View {
        HStack(spacing: 8) {
            thinkingToggleButton

            Spacer(minLength: 8)

            contextualStatus

            primaryActionButton
                .fixedSize(horizontal: true, vertical: false)
        }
        .padding(.horizontal, 10)
        .padding(.top, 4)
        .padding(.bottom, 8)
    }

    var thinkingToggleButton: some View {
        Button {
            toggleThinking()
        } label: {
            Label {
                Text("Thinking")
                    .font(.caption.weight(.medium))
            } icon: {
                Image(systemName: isThinkingEnabled ? "lightbulb.fill" : "lightbulb")
            }
                .foregroundStyle(isThinkingEnabled ? MelixDesignTokens.accent : Color.secondary)
                .padding(.horizontal, 6)
                .frame(minHeight: 28)
                .contentShape(RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.md))
        }
        .buttonStyle(.plain)
        .disabled(isStreaming)
        .help(isThinkingEnabled ? "Thinking enabled" : "Thinking disabled")
        .accessibilityLabel("Thinking")
        .accessibilityValue(isThinkingEnabled ? "On" : "Off")
        .accessibilityHint(isStreaming ? "Unavailable while a response is generating." : "Toggles public reasoning display.")
    }

    @ViewBuilder
    var contextualStatus: some View {
        if isStreaming {
            HStack(spacing: 5) {
                ProgressView()
                    .controlSize(.mini)
                Text("Generating · draft saved")
                    .font(.caption2)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
            }
            .foregroundStyle(.secondary)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Generating. Draft saved.")
        } else if composerGate.isDegraded {
            Button(action: onOpenServer) {
                Label("Provider limited", systemImage: "exclamationmark.triangle.fill")
                    .font(.caption2)
                    .foregroundStyle(MelixDesignTokens.StatusColor.warning)
            }
            .buttonStyle(.plain)
            .help("Open Providers to inspect unavailable capabilities")
            .accessibilityLabel("Provider limited. Open Providers")
        } else if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  isEditorFocused,
                  composerGate.repairState == nil {
            Text("↵ Send · ⌘↵ New line")
                .font(.caption2)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .foregroundStyle(.secondary)
                .accessibilityHidden(true)
        }
    }

    var expandEditorButton: some View {
        Button {
            isEditorExpanded.toggle()
            requestEditorFocus()
        } label: {
            Image(
                systemName: isEditorExpanded
                    ? "arrow.down.right.and.arrow.up.left"
                    : "arrow.up.left.and.arrow.down.right"
            )
            .font(.caption.weight(.medium))
            .foregroundStyle(.secondary)
            .frame(width: 24, height: 24)
            .background(Color(nsColor: .textBackgroundColor).opacity(0.92), in: RoundedRectangle(cornerRadius: 7))
        }
        .buttonStyle(.plain)
        .help(isEditorExpanded ? "Collapse editor" : "Expand editor")
        .accessibilityLabel(isEditorExpanded ? "Collapse message editor" : "Expand message editor")
        .accessibilityValue(isEditorExpanded ? "Expanded" : "Collapsed")
    }

    func toggleThinking() {
        guard isStreaming == false else {
            return
        }
        isThinkingEnabled.toggle()
    }

    func primaryAction() {
        guard canSubmit else {
            return
        }
        onSubmit()
    }

    func performRepairAction(_ kind: DesktopChatComposerRepairActionKind) {
        switch kind {
        case .chooseProvider:
            onOpenServer()
        case .attachModel:
            onOpenModels()
        case .startProvider:
            restoresFocusAfterRepair = true
            onStartServer()
        case .resumeProvider:
            restoresFocusAfterRepair = true
            onResumeServer()
        case .wakeProvider:
            restoresFocusAfterRepair = true
            onWakeServer()
        case .openProviders:
            onOpenServer()
        case .runCapabilitiesTest:
            onRunCapabilitiesTest()
        }
    }

    func requestEditorFocus() {
        editorFocusRequestID = UUID()
    }

    var primaryActionHelpText: String {
        if isStreaming {
            return "Send unavailable while generating; draft saved"
        }
        if let repairState = composerGate.repairState {
            return "Send unavailable. \(repairState.title)"
        }
        if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "Send unavailable for an empty message"
        }
        return composerGate.isDegraded ? "Send Anyway" : "Send"
    }

    var primaryActionAccessibilityLabel: String {
        composerGate.isDegraded ? "Send Anyway" : "Send"
    }

    var primaryActionButton: some View {
        Button(action: primaryAction) {
            primaryActionLabel
        }
        .labelStyle(.iconOnly)
        .buttonStyle(.borderedProminent)
        .buttonBorderShape(.roundedRectangle(radius: 10))
        .controlSize(.regular)
        .disabled(canSubmit == false)
        .help(primaryActionHelpText)
        .accessibilityLabel(primaryActionAccessibilityLabel)
        .accessibilityHint(primaryActionHelpText)
    }

    var primaryActionLabel: some View {
        Label("Send", systemImage: "paperplane.fill")
    }
}

enum DesktopChatComposerRepairActionKind: Equatable {
    case chooseProvider
    case attachModel
    case startProvider
    case resumeProvider
    case wakeProvider
    case openProviders
    case runCapabilitiesTest
}

struct DesktopChatComposerRepairSecondaryAction: Equatable, Identifiable {
    let title: String
    let kind: DesktopChatComposerRepairActionKind

    var id: DesktopChatComposerRepairActionKind {
        kind
    }
}

struct DesktopChatComposerRepairState: Equatable {
    let title: String
    let detail: String
    let primaryActionTitle: String
    let primaryActionKind: DesktopChatComposerRepairActionKind
    let secondaryActions: [DesktopChatComposerRepairSecondaryAction]
    let systemImageName: String
}

struct DesktopChatComposerGate: Equatable {
    let serverSession: DesktopServerSessionState?
    var remoteProviderIsSelected = false
    let capabilities: [DesktopChatCapabilityRow]
    let isModelMissing: Bool

    var repairState: DesktopChatComposerRepairState? {
        if remoteProviderIsSelected {
            return hasInvalidCapabilityReceipt
                ? DesktopChatComposerRepairState(
                    title: "Capability receipt is invalid.",
                    detail: "Run a capability test before sending with this model.",
                    primaryActionTitle: "Run Capabilities Test",
                    primaryActionKind: .runCapabilitiesTest,
                    secondaryActions: [.openProviders],
                    systemImageName: "checklist"
                )
                : nil
        }
        guard let serverSession else {
            return DesktopChatComposerRepairState(
                title: "Select a provider before sending.",
                detail: "Bind this chat to a local or remote provider.",
                primaryActionTitle: "Choose Provider",
                primaryActionKind: .chooseProvider,
                secondaryActions: [],
                systemImageName: "server.rack"
            )
        }

        if isModelMissing {
            return DesktopChatComposerRepairState(
                title: "Provider is missing a model.",
                detail: "Attach a model before this chat can send requests.",
                primaryActionTitle: "Attach Model",
                primaryActionKind: .attachModel,
                secondaryActions: [.openProviders],
                systemImageName: "cube.box"
            )
        }

        switch serverSession.lifecycle {
        case .draft, .stopped, .unavailable:
            return DesktopChatComposerRepairState(
                title: "Provider is offline.",
                detail: "Start the bound provider before sending.",
                primaryActionTitle: "Start Provider",
                primaryActionKind: .startProvider,
                secondaryActions: [.openProviders],
                systemImageName: "power"
            )
        case .paused:
            return DesktopChatComposerRepairState(
                title: "Provider is paused.",
                detail: "Resume this provider before sending.",
                primaryActionTitle: "Resume Provider",
                primaryActionKind: .resumeProvider,
                secondaryActions: [.openProviders],
                systemImageName: "pause.circle"
            )
        case .starting:
            return DesktopChatComposerRepairState(
                title: "Provider is starting.",
                detail: "Sending is blocked until startup completes.",
                primaryActionTitle: "Open Providers",
                primaryActionKind: .openProviders,
                secondaryActions: [],
                systemImageName: "arrow.clockwise.circle"
            )
        case .stopping:
            return DesktopChatComposerRepairState(
                title: "Provider is stopping.",
                detail: "Wait for shutdown to finish, then start it again.",
                primaryActionTitle: "Open Providers",
                primaryActionKind: .openProviders,
                secondaryActions: [],
                systemImageName: "pause.circle"
            )
        case .error:
            return DesktopChatComposerRepairState(
                title: "Provider failed.",
                detail: serverSession.lastError.isEmpty ? "Recover the failed provider before sending." : serverSession.lastError,
                primaryActionTitle: "Open Providers",
                primaryActionKind: .openProviders,
                secondaryActions: [.openDiagnostics],
                systemImageName: "exclamationmark.triangle"
            )
        case .sleeping, .running:
            break
        }

        if hasInvalidCapabilityReceipt {
            return DesktopChatComposerRepairState(
                title: "Capability receipt is invalid.",
                detail: "Run a capability test before sending with this model.",
                primaryActionTitle: "Run Capabilities Test",
                primaryActionKind: .runCapabilitiesTest,
                secondaryActions: [.openProviders],
                systemImageName: "checklist"
            )
        }

        return nil
    }

    var isDegraded: Bool {
        guard repairState == nil, serverSession != nil || remoteProviderIsSelected else {
            return false
        }
        return capabilities.contains { $0.isReady == false }
    }

    private var hasInvalidCapabilityReceipt: Bool {
        // Chat send is gated by text readiness; non-text failures are surfaced as degraded provider signals.
        capabilities.contains { capability in
            capability.id == "text" && capability.isReady == false
        }
    }
}

struct DesktopChatComposerRepairStrip: View {
    let state: DesktopChatComposerRepairState
    let onPrimaryAction: () -> Void
    let onOpenServer: () -> Void
    let onOpenModels: () -> Void
    let onRunCapabilitiesTest: () -> Void

    var body: some View {
        HStack(alignment: .center, spacing: 8) {
            Image(systemName: state.systemImageName)
                .font(.caption.weight(.semibold))
                .foregroundStyle(MelixDesignTokens.StatusColor.warning)
                .frame(width: 18, height: 18)
                .accessibilityHidden(true)

            Text(state.title)
                .font(.caption.weight(.semibold))
                .lineLimit(1)
                .truncationMode(.tail)
                .accessibilityLabel("\(state.title) \(state.detail)")

            Spacer(minLength: 8)

            ForEach(state.secondaryActions) { action in
                Button(action.title) {
                    performSecondaryAction(action.kind)
                }
                .buttonStyle(.borderless)
                .controlSize(.small)
                .fixedSize(horizontal: true, vertical: false)
                .help(action.title)
                .accessibilityLabel(action.title)
            }

            Button(state.primaryActionTitle, action: onPrimaryAction)
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .fixedSize(horizontal: true, vertical: false)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 5)
        .frame(minHeight: 34)
        .background(
            MelixDesignTokens.StatusColor.warning.opacity(MelixDesignTokens.StateOpacity.background)
        )
        .help(state.detail)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Provider repair")
    }

    func performSecondaryAction(_ kind: DesktopChatComposerRepairActionKind) {
        switch kind {
        case .openProviders:
            onOpenServer()
        case .attachModel:
            onOpenModels()
        case .runCapabilitiesTest:
            onRunCapabilitiesTest()
        case .chooseProvider, .startProvider, .resumeProvider, .wakeProvider:
            break
        }
    }
}

extension DesktopChatComposerRepairSecondaryAction {
    static let openProviders = Self(title: "Open Providers", kind: .openProviders)
    static let openModels = Self(title: "Open Models", kind: .attachModel)
    static let openDiagnostics = Self(title: "Open Diagnostics", kind: .runCapabilitiesTest)
}

struct DesktopChatProviderControlStrip: View {
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

    let serverSession: DesktopServerSessionState?
    let capabilities: [DesktopChatCapabilityRow]
    let onOpenServer: () -> Void
    let onStartServer: () -> Void
    let onResumeServer: () -> Void
    let onWakeServer: () -> Void

    var recoveryAction: RecoveryAction? {
        switch serverSession?.lifecycle {
        case .none:
            return RecoveryAction(title: "Choose Provider", kind: .openServer, isProminent: false)
        case .paused:
            return RecoveryAction(title: "Resume Provider", kind: .resumeServer, isProminent: true)
        case .sleeping:
            return RecoveryAction(title: "Wake", kind: .wakeServer, isProminent: false)
        case .draft, .stopped, .unavailable:
            return RecoveryAction(title: "Start Provider", kind: .startServer, isProminent: true)
        case .error:
            return RecoveryAction(title: "Open Providers", kind: .openServer, isProminent: true)
        case .starting, .stopping, .running:
            return nil
        }
    }

    var body: some View {
        HStack(spacing: 8) {
            DesktopChatProviderStatusSignal(serverSession: serverSession)

            if capabilities.isEmpty == false {
                DesktopChatCapabilityStatusSignal(capabilities: Array(capabilities.prefix(5)))
            }

            recoveryActionButton

            Button(action: onOpenServer) {
                Image(systemName: "server.rack")
                    .frame(width: 18, height: 18)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .help("Open Providers")
            .accessibilityLabel("Open Providers")
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

struct DesktopChatProviderStatusSignal: View {
    let serverSession: DesktopServerSessionState?

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: statusSymbolName)
                .font(.caption.weight(.semibold))
                .foregroundStyle(statusColor)
                .frame(width: DesktopChatProviderSignalMetrics.iconSize, height: DesktopChatProviderSignalMetrics.iconSize)
            Text(statusShortText)
                .font(.caption2.monospacedDigit().weight(.semibold))
                .foregroundStyle(statusColor)
                .lineLimit(1)
                .frame(width: DesktopChatProviderSignalMetrics.shortTextWidth, alignment: .leading)
        }
        .padding(.horizontal, 7)
        .padding(.vertical, 4)
        .frame(width: DesktopChatProviderSignalMetrics.providerSignalWidth, alignment: .leading)
        .background(Color.secondary.opacity(0.06), in: Capsule())
        .overlay(
            Capsule()
                .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline), lineWidth: 1)
        )
        .help(helpText)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityLabel)
    }

    var serverTitle: String {
        serverSession?.title ?? "No Provider"
    }

    var serverDetail: String {
        guard let serverSession else {
            return "Choose Provider"
        }
        return "\(serverSession.lifecycle.rawValue) • \(serverSession.modelID)"
    }

    var statusShortText: String {
        switch serverSession?.lifecycle {
        case .running:
            return "OK"
        case .sleeping:
            return "SLP"
        case .starting:
            return "ON"
        case .stopping:
            return "OFF"
        case .paused:
            return "PAU"
        case .draft:
            return "NEW"
        case .stopped:
            return "OFF"
        case .unavailable:
            return "MISS"
        case .error:
            return "ERR"
        case .none:
            return "SET"
        }
    }

    var statusSymbolName: String {
        switch serverSession?.lifecycle {
        case .running:
            return "checkmark.circle.fill"
        case .sleeping:
            return "moon.fill"
        case .starting:
            return "arrow.clockwise.circle.fill"
        case .stopping:
            return "pause.circle.fill"
        case .paused:
            return "pause.circle.fill"
        case .draft:
            return "plus.circle.fill"
        case .stopped:
            return "power.circle.fill"
        case .unavailable:
            return "questionmark.circle.fill"
        case .error:
            return "exclamationmark.triangle.fill"
        case .none:
            return "circle.dashed"
        }
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

    var helpText: String {
        guard let serverSession else {
            return "Choose a provider for this chat"
        }
        return "\(serverSession.title) • \(serverSession.modelID) • \(serverSession.runtimeDetailText)"
    }

    var accessibilityLabel: String {
        "\(serverTitle), \(serverDetail)"
    }
}

struct DesktopChatCapabilityStatusSignal: View {
    let capabilities: [DesktopChatCapabilityRow]

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: "square.grid.2x2.fill")
                .font(.caption.weight(.semibold))
                .foregroundStyle(statusColor)
                .frame(width: DesktopChatProviderSignalMetrics.iconSize, height: DesktopChatProviderSignalMetrics.iconSize)
            Text("\(readyCount)/\(capabilities.count)")
                .font(.caption2.monospacedDigit().weight(.semibold))
                .foregroundStyle(statusColor)
                .lineLimit(1)
        }
        .padding(.horizontal, 7)
        .padding(.vertical, 4)
        .frame(width: DesktopChatProviderSignalMetrics.capabilitySignalWidth, alignment: .leading)
        .background(Color.secondary.opacity(0.06), in: Capsule())
        .overlay(
            Capsule()
                .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.hairline), lineWidth: 1)
        )
        .help(helpText)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Model capabilities, \(readyCount) of \(capabilities.count) ready")
    }

    var readyCount: Int {
        capabilities.filter(\.isReady).count
    }

    var statusColor: Color {
        if capabilities.isEmpty {
            return Color.secondary
        }
        if readyCount == capabilities.count {
            return MelixDesignTokens.StatusColor.success
        }
        if readyCount > 0 {
            return MelixDesignTokens.StatusColor.warning
        }
        return MelixDesignTokens.StatusColor.error
    }

    var helpText: String {
        let details = capabilities
            .map { "\($0.shortTitle): \($0.isReady ? "ready" : "unavailable") • \($0.detail)" }
            .joined(separator: "\n")
        return details.isEmpty ? "No model capabilities detected" : details
    }
}

enum DesktopChatProviderSignalMetrics {
    static let iconSize: CGFloat = 16
    static let shortTextWidth: CGFloat = 28
    static let providerSignalWidth: CGFloat = 68
    static let capabilitySignalWidth: CGFloat = 66
}

enum DesktopChatComposerHeightPolicy {
    static let minimumHeight: CGFloat = 40
    static let collapsedMaximumHeight: CGFloat = 99
    static let expandedMaximumHeight: CGFloat = 220

    static func resolvedHeight(contentHeight: CGFloat, isExpanded: Bool = false) -> CGFloat {
        let maximumHeight = isExpanded ? expandedMaximumHeight : collapsedMaximumHeight
        return min(maximumHeight, max(minimumHeight, ceil(contentHeight)))
    }

    static func isAtCollapsedCap(contentHeight: CGFloat) -> Bool {
        ceil(contentHeight) >= collapsedMaximumHeight
    }
}

struct DesktopChatComposerTextView: NSViewRepresentable {
    @Binding var text: String
    @Binding var height: CGFloat
    @Binding var contentHeight: CGFloat
    @Binding var isFocused: Bool
    let isExpanded: Bool
    let focusRequestID: UUID?
    let isSubmitAvailable: Bool
    let onCommandSubmit: (String) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(
            text: $text,
            height: $height,
            contentHeight: $contentHeight,
            isFocused: $isFocused,
            isExpanded: isExpanded
        )
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = DesktopChatComposerCommandSubmitScrollView()
        scrollView.drawsBackground = false
        scrollView.hasVerticalScroller = true
        scrollView.autohidesScrollers = true
        scrollView.borderType = .noBorder

        let textView = DesktopChatComposerCommandSubmitTextView()
        textView.delegate = context.coordinator
        textView.isRichText = false
        textView.isAutomaticQuoteSubstitutionEnabled = false
        textView.isAutomaticDashSubstitutionEnabled = false
        textView.font = NSFont.systemFont(ofSize: NSFont.systemFontSize, weight: .regular)
        textView.drawsBackground = false
        textView.textContainerInset = NSSize(width: 0, height: 0)
        textView.minSize = NSSize(width: 0, height: DesktopChatComposerHeightPolicy.minimumHeight)
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
        textView.textContainer?.widthTracksTextView = true
        textView.setAccessibilityLabel("Message")
        textView.setAccessibilityHelp("Return to send. Command Return for a new line.")
        scrollView.commandSubmitTextView = textView
        scrollView.documentView = textView
        scrollView.onLayout = { [weak textView, weak coordinator = context.coordinator] in
            guard let textView else {
                return
            }
            coordinator?.updateHeight(for: textView)
        }
        context.coordinator.updateHeight(for: textView)
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = scrollView.documentView as? DesktopChatComposerCommandSubmitTextView else {
            return
        }
        if textView.string != text {
            textView.string = text
        }
        context.coordinator.text = $text
        context.coordinator.height = $height
        context.coordinator.contentHeight = $contentHeight
        context.coordinator.isFocused = $isFocused
        context.coordinator.isExpanded = isExpanded
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
        context.coordinator.updateHeight(for: textView)

        if let focusRequestID,
           context.coordinator.lastHandledFocusRequestID != focusRequestID {
            context.coordinator.lastHandledFocusRequestID = focusRequestID
            DispatchQueue.main.async { [weak scrollView, weak textView] in
                guard let scrollView, let textView else {
                    return
                }
                scrollView.window?.makeFirstResponder(textView)
            }
        }
    }

    @MainActor
    final class Coordinator: NSObject, NSTextViewDelegate {
        var text: Binding<String>
        var height: Binding<CGFloat>
        var contentHeight: Binding<CGFloat>
        var isFocused: Binding<Bool>
        var isExpanded: Bool
        var lastHandledFocusRequestID: UUID?

        init(
            text: Binding<String>,
            height: Binding<CGFloat>,
            contentHeight: Binding<CGFloat>,
            isFocused: Binding<Bool>,
            isExpanded: Bool
        ) {
            self.text = text
            self.height = height
            self.contentHeight = contentHeight
            self.isFocused = isFocused
            self.isExpanded = isExpanded
        }

        func textDidChange(_ notification: Notification) {
            guard let textView = notification.object as? NSTextView else {
                return
            }
            text.wrappedValue = textView.string
            updateHeight(for: textView)
        }

        func textDidBeginEditing(_ notification: Notification) {
            guard isFocused.wrappedValue == false else {
                return
            }
            isFocused.wrappedValue = true
        }

        func textDidEndEditing(_ notification: Notification) {
            guard isFocused.wrappedValue else {
                return
            }
            isFocused.wrappedValue = false
        }

        func updateHeight(for textView: NSTextView) {
            guard let textContainer = textView.textContainer,
                  let layoutManager = textView.layoutManager
            else {
                return
            }
            layoutManager.ensureLayout(for: textContainer)
            let contentHeight = layoutManager.usedRect(for: textContainer).height
                + (textView.textContainerInset.height * 2)
            let measuredContentHeight = ceil(contentHeight)
            let documentHeight = max(DesktopChatComposerHeightPolicy.minimumHeight, measuredContentHeight)
            if abs(textView.frame.height - documentHeight) > 0.5 {
                var frame = textView.frame
                frame.size.height = documentHeight
                textView.frame = frame
            }
            let resolvedHeight = DesktopChatComposerHeightPolicy.resolvedHeight(
                contentHeight: measuredContentHeight,
                isExpanded: isExpanded
            )
            if abs(self.contentHeight.wrappedValue - measuredContentHeight) > 0.5 {
                let contentHeightBinding = self.contentHeight
                DispatchQueue.main.async {
                    contentHeightBinding.wrappedValue = measuredContentHeight
                }
            }
            if abs(height.wrappedValue - resolvedHeight) > 0.5 {
                let heightBinding = height
                DispatchQueue.main.async {
                    heightBinding.wrappedValue = resolvedHeight
                }
            }
        }
    }

}

@MainActor
final class DesktopChatComposerCommandSubmitScrollView: NSScrollView {
    weak var commandSubmitTextView: DesktopChatComposerCommandSubmitTextView?
    var onLayout: (() -> Void)?

    override func layout() {
        super.layout()
        onLayout?()
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
    var monotonicNow: () -> TimeInterval = { ProcessInfo.processInfo.systemUptime }
    private var compositionGuardUntil: TimeInterval = -.infinity

    override func unmarkText() {
        let wasComposing = hasMarkedText()
        super.unmarkText()
        if wasComposing {
            armPostCompositionGuard()
        }
    }

    override func insertText(_ insertString: Any, replacementRange: NSRange) {
        let wasComposing = hasMarkedText()
        super.insertText(insertString, replacementRange: replacementRange)
        if wasComposing {
            armPostCompositionGuard()
        }
    }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        guard hasMarkedText() == false else {
            return super.performKeyEquivalent(with: event)
        }
        if shouldConsumePostCompositionReturn(event) {
            return true
        }
        switch DesktopChatComposerKeyPolicy.action(keyCode: event.keyCode, modifiers: event.modifierFlags) {
        case .submit:
            guard event.isARepeat == false else { return true }
            return submitCurrentText()
        case .insertNewline:
            super.insertNewlineIgnoringFieldEditor(nil)
            return true
        case .passThrough:
            return super.performKeyEquivalent(with: event)
        }
    }

    override func doCommand(by selector: Selector) {
        guard hasMarkedText() == false else {
            super.doCommand(by: selector)
            return
        }
        if shouldConsumePostCompositionReturn(selector) {
            return
        }
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
        guard hasMarkedText() == false else {
            super.insertNewline(sender)
            return
        }
        if shouldConsumePostCompositionReturn(#selector(NSTextView.insertNewline(_:))) {
            return
        }
        switch currentReturnCommandAction(for: #selector(NSTextView.insertNewline(_:))) {
        case .submit:
            _ = submitCurrentText()
        case .insertNewline:
            super.insertNewlineIgnoringFieldEditor(sender)
        case .passThrough:
            super.insertNewline(sender)
        }
    }

    override func insertLineBreak(_ sender: Any?) {
        guard hasMarkedText() == false else {
            super.insertLineBreak(sender)
            return
        }
        if shouldConsumePostCompositionReturn(#selector(NSTextView.insertLineBreak(_:))) {
            return
        }
        switch currentReturnCommandAction(for: #selector(NSTextView.insertLineBreak(_:))) {
        case .submit:
            _ = submitCurrentText()
        case .insertNewline:
            super.insertNewlineIgnoringFieldEditor(sender)
        case .passThrough:
            super.insertLineBreak(sender)
        }
    }

    override func insertNewlineIgnoringFieldEditor(_ sender: Any?) {
        guard hasMarkedText() == false else {
            super.insertNewlineIgnoringFieldEditor(sender)
            return
        }
        if shouldConsumePostCompositionReturn(#selector(NSTextView.insertNewlineIgnoringFieldEditor(_:))) {
            return
        }
        switch currentReturnCommandAction(for: #selector(NSTextView.insertNewlineIgnoringFieldEditor(_:))) {
        case .submit:
            _ = submitCurrentText()
        case .insertNewline:
            super.insertNewlineIgnoringFieldEditor(sender)
        case .passThrough:
            super.insertNewlineIgnoringFieldEditor(sender)
        }
    }

    @discardableResult
    func handleLocalKeyDown(_ event: NSEvent) -> Bool {
        guard hasMarkedText() == false else {
            return false
        }
        if shouldConsumePostCompositionReturn(event) {
            return true
        }
        switch DesktopChatComposerKeyPolicy.action(keyCode: event.keyCode, modifiers: event.modifierFlags) {
        case .submit:
            guard event.isARepeat == false else { return true }
            return submitCurrentText()
        case .insertNewline:
            super.insertNewlineIgnoringFieldEditor(nil)
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

    private func shouldConsumePostCompositionReturn(_ event: NSEvent) -> Bool {
        guard event.keyCode == DesktopChatComposerKeyPolicy.returnKeyCode
                || event.keyCode == DesktopChatComposerKeyPolicy.keypadEnterKeyCode
        else {
            return false
        }
        return monotonicNow() < compositionGuardUntil
    }

    private func shouldConsumePostCompositionReturn(_ selector: Selector) -> Bool {
        DesktopChatComposerReturnCommandPolicy.isReturnCommandSelector(selector)
        && monotonicNow() < compositionGuardUntil
    }

    private func armPostCompositionGuard() {
        compositionGuardUntil = monotonicNow()
            + DesktopChatComposerKeyPolicy.postCompositionGuardInterval
    }

    private func submitCurrentText() -> Bool {
        _ = onCommandSubmit?(string)
        return true
    }
}

struct DesktopChatTranscriptRowView: View {
    let entry: DesktopChatTranscriptEntry
    let isPending: Bool
    let isStreaming: Bool
    let showsAssistantRole: Bool
    let pendingStatusText: String
    let onPreviewArtifact: (DesktopChatArtifactPreviewState) -> Void

    init(
        entry: DesktopChatTranscriptEntry,
        isPending: Bool = false,
        isStreaming: Bool = false,
        showsAssistantRole: Bool = true,
        pendingStatusText: String = "",
        onPreviewArtifact: @escaping (DesktopChatArtifactPreviewState) -> Void = { _ in }
    ) {
        self.entry = entry
        self.isPending = isPending
        self.isStreaming = isStreaming
        self.showsAssistantRole = showsAssistantRole
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
            DesktopChatAssistantTurnEnvelope(showsRole: showsAssistantRole) {
                DesktopChatAssistantDocumentView(
                    messageBody: sanitizedBody,
                    isPending: isPending,
                    isStreaming: isStreaming,
                    pendingStatusText: sanitizedPendingStatusText,
                    metadataText: sanitizedDetail
                )
            }
        case .reasoning:
            DesktopChatAssistantTurnEnvelope(showsRole: showsAssistantRole) {
                DesktopChatReasoningBlockView(
                    publicMessageBody: sanitizedBody,
                    isStreaming: isStreaming,
                    reasoningElapsedSeconds: entry.reasoningElapsedSeconds
                )
            }
        case .tool:
            DesktopChatAssistantTurnEnvelope(showsRole: showsAssistantRole) {
                DesktopChatActivityBlockView(
                    kind: .tool,
                    title: sanitizedTitle,
                    messageBody: sanitizedBody,
                    detail: sanitizedDetail,
                    isStreaming: isStreaming
                )
            }
        case .error:
            DesktopChatAssistantTurnEnvelope(showsRole: showsAssistantRole) {
                DesktopChatErrorBlockView(
                    title: sanitizedTitle,
                    messageBody: sanitizedBody,
                    detail: sanitizedDetail
                )
            }
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

struct DesktopChatAssistantTurnEnvelope<Content: View>: View {
    let showsRole: Bool
    @ViewBuilder let content: Content

    init(showsRole: Bool, @ViewBuilder content: () -> Content) {
        self.showsRole = showsRole
        self.content = content()
    }

    var body: some View {
        HStack(alignment: .top, spacing: 11) {
            Group {
                if showsRole {
                    Text("M")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(MelixDesignTokens.accent)
                        .frame(
                            width: DesktopChatLayoutMetrics.assistantAvatarSize,
                            height: DesktopChatLayoutMetrics.assistantAvatarSize
                        )
                        .background(
                            MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.weak),
                            in: RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.sm)
                        )
                        .accessibilityHidden(true)
                } else {
                    Color.clear
                        .frame(
                            width: DesktopChatLayoutMetrics.assistantAvatarSize,
                            height: 1
                        )
                        .accessibilityHidden(true)
                }
            }

            VStack(alignment: .leading, spacing: showsRole ? 10 : 0) {
                if showsRole {
                    Text("MELIX ASSISTANT")
                        .font(.caption2.weight(.semibold))
                        .tracking(0.35)
                        .foregroundStyle(.secondary)
                        .accessibilityAddTraits(.isHeader)
                }
                content
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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
                .frame(minWidth: 64, alignment: .leading)
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
    let metadataText: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if isPending {
                pendingAssistantView
            } else {
                DesktopChatMarkdownBodyView(
                    rawText: messageBody.isEmpty ? "…" : messageBody,
                    isStreaming: isStreaming
                )
                if isStreaming == false, metadataText.isEmpty == false {
                    Text(metadataText)
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .accessibilityLabel("Usage \(metadataText)")
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, 4)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Assistant message")
    }

    private var pendingAssistantView: some View {
        DesktopChatReasoningBlockView(
            publicMessageBody: "",
            isStreaming: true,
            reasoningElapsedSeconds: nil,
            announcesStreamingStart: true
        )
    }
}

struct DesktopChatReasoningBlockView: View {
    private enum ScrollAnchor: Hashable {
        case latest
    }

    let publicMessageBody: String
    let isStreaming: Bool
    let reasoningElapsedSeconds: Int?
    let announcesStreamingStart: Bool
    @Environment(\.accessibilityReduceMotion) private var accessibilityReduceMotion
    @State private var isExpanded: Bool
    @State private var isFollowingLatest = true
    @State private var isUserScrolling = false

    init(
        publicMessageBody: String,
        isStreaming: Bool,
        reasoningElapsedSeconds: Int? = nil,
        announcesStreamingStart: Bool = false
    ) {
        self.publicMessageBody = publicMessageBody
        self.isStreaming = isStreaming
        self.reasoningElapsedSeconds = reasoningElapsedSeconds
        self.announcesStreamingStart = announcesStreamingStart
        _isExpanded = State(
            initialValue: DesktopChatReasoningPresentationPolicy.initiallyExpanded(
                isStreaming: isStreaming
            )
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button {
                isExpanded.toggle()
            } label: {
                HStack(spacing: 7) {
                    Image(systemName: "brain.head.profile")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(MelixDesignTokens.accent)
                        .frame(width: 16, height: 16)
                    DesktopChatThinkingLabel(
                        text: summaryText,
                        isStreaming: isStreaming
                    )
                    Image(systemName: "chevron.down")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.tertiary)
                        .rotationEffect(.degrees(isExpanded ? 180 : 0))
                    Spacer(minLength: 0)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help(isExpanded ? "Hide public reasoning" : "Show public reasoning")
            .accessibilityLabel(summaryText)
            .accessibilityValue(isExpanded ? "Expanded" : "Collapsed")

            if isExpanded {
                HStack(alignment: .top, spacing: 14) {
                    DesktopChatReasoningDottedRule()

                    if isStreaming {
                        streamingReasoningBody
                    } else {
                        completedReasoningBody
                    }
                }
                .padding(.top, 11)
                .padding(.leading, 8)
                .transition(.opacity)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .animation(
            accessibilityReduceMotion ? nil : .easeOut(duration: 0.16),
            value: isExpanded
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Public reasoning")
        .accessibilityValue(isStreaming ? "Busy" : "Completed")
        .onAppear {
            guard announcesStreamingStart, isStreaming else {
                return
            }
            DesktopChatAccessibilityAnnouncer.post(
                DesktopChatReasoningPresentationPolicy.accessibilityAnnouncement(isStreaming: true)
            )
        }
        .onChange(of: isStreaming) { _, newValue in
            isExpanded = newValue
            if newValue {
                isFollowingLatest = true
            }
            DesktopChatAccessibilityAnnouncer.post(
                DesktopChatReasoningPresentationPolicy.accessibilityAnnouncement(isStreaming: newValue)
            )
        }
    }

    private var summaryText: String {
        DesktopChatReasoningPresentationPolicy.summaryText(
            isStreaming: isStreaming,
            elapsedSeconds: reasoningElapsedSeconds
        )
    }

    private var streamingReasoningBody: some View {
        ScrollViewReader { proxy in
            ScrollView(.vertical) {
                VStack(alignment: .leading, spacing: 0) {
                    publicReasoningText(showsCaret: accessibilityReduceMotion == false)
                    Color.clear
                        .frame(height: 1)
                        .id(ScrollAnchor.latest)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: DesktopChatReasoningPresentationPolicy.maximumStreamingHeight, alignment: .top)
            .scrollIndicators(.hidden)
            .opacity(DesktopChatReasoningPresentationPolicy.streamingBodyOpacity)
            .overlay(alignment: .top) {
                DesktopChatReasoningTopFade()
            }
            .onAppear {
                scrollToLatest(proxy)
            }
            .onChange(of: publicMessageBody) { _, _ in
                scrollToLatest(proxy)
            }
            .onScrollPhaseChange { _, newPhase, context in
                switch newPhase {
                case .tracking, .interacting:
                    isUserScrolling = true
                    isFollowingLatest = false
                case .idle:
                    guard isUserScrolling else {
                        return
                    }
                    isFollowingLatest = DesktopChatReasoningPresentationPolicy.isAtBottom(
                        contentOffsetY: context.geometry.contentOffset.y,
                        contentHeight: context.geometry.contentSize.height,
                        viewportHeight: context.geometry.containerSize.height
                    )
                    isUserScrolling = false
                case .decelerating, .animating:
                    break
                }
            }
        }
    }

    private var completedReasoningBody: some View {
        publicReasoningText(showsCaret: false)
    }

    @ViewBuilder
    private func publicReasoningText(showsCaret: Bool) -> some View {
        if publicMessageBody.isEmpty {
            Text(isStreaming ? "Waiting for reasoning..." : "No public reasoning recorded.")
                .font(.caption)
                .foregroundStyle(.secondary)
        } else if isStreaming {
            DesktopChatCompactStreamingReasoningText(
                rawText: publicMessageBody,
                showsCaret: showsCaret
            )
        } else {
            DesktopChatMarkdownBodyView(
                rawText: publicMessageBody,
                isStreaming: false
            )
            .foregroundStyle(.secondary)
            .textSelection(.enabled)
        }
    }

    private func scrollToLatest(_ proxy: ScrollViewProxy) {
        guard isFollowingLatest else {
            return
        }
        DispatchQueue.main.async {
            var transaction = Transaction()
            transaction.animation = nil
            withTransaction(transaction) {
                proxy.scrollTo(ScrollAnchor.latest, anchor: .bottom)
            }
        }
    }
}

struct DesktopChatCompactStreamingReasoningText: View {
    let rawText: String
    let showsCaret: Bool

    var body: some View {
        Group {
            if showsCaret {
                TimelineView(.animation(minimumInterval: 0.36, paused: false)) { context in
                    compactText(caretVisible: isCaretVisible(at: context.date))
                }
            } else {
                compactText(caretVisible: false)
            }
        }
        .font(.caption)
        .lineSpacing(3)
        .foregroundStyle(.secondary)
        .textSelection(.enabled)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(rawText)
    }

    private func compactText(caretVisible: Bool) -> some View {
        Text(
            DesktopChatReasoningPresentationPolicy.compactStreamingAttributedText(
                from: rawText,
                includesCaret: showsCaret,
                caretVisible: caretVisible
            )
        )
    }

    private func isCaretVisible(at date: Date) -> Bool {
        let phase = Int(date.timeIntervalSinceReferenceDate / 0.36)
        return phase.isMultiple(of: 2)
    }
}

private struct DesktopChatReasoningTopFade: View {
    var body: some View {
        LinearGradient(
            colors: [
                Color(nsColor: .windowBackgroundColor),
                Color(nsColor: .windowBackgroundColor).opacity(0),
            ],
            startPoint: .top,
            endPoint: .bottom
        )
        .frame(height: 28)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

private enum DesktopChatAccessibilityAnnouncer {
    @MainActor
    static func post(_ announcement: String) {
        NSAccessibility.post(
            element: NSApplication.shared,
            notification: .announcementRequested,
            userInfo: [
                .announcement: announcement,
                .priority: NSAccessibilityPriorityLevel.medium.rawValue,
            ]
        )
    }
}

private struct DesktopChatThinkingLabel: View {
    let text: String
    let isStreaming: Bool
    @Environment(\.accessibilityReduceMotion) private var accessibilityReduceMotion

    var body: some View {
        Group {
            if isStreaming && accessibilityReduceMotion == false {
                TimelineView(.animation(minimumInterval: 1.0 / 30.0, paused: false)) { context in
                    let progress = context.date.timeIntervalSinceReferenceDate
                        .truncatingRemainder(dividingBy: 1.35) / 1.35
                    Text(text)
                        .foregroundStyle(
                            LinearGradient(
                                colors: [
                                    Color.secondary,
                                    MelixDesignTokens.accent,
                                    Color.secondary,
                                ],
                                startPoint: UnitPoint(x: progress * 2.0 - 1.0, y: 0.5),
                                endPoint: UnitPoint(x: progress * 2.0, y: 0.5)
                            )
                        )
                }
            } else {
                Text(text)
                    .foregroundStyle(.secondary)
            }
        }
        .font(.caption.weight(.medium))
    }
}

private struct DesktopChatReasoningDottedRule: View {
    var body: some View {
        GeometryReader { geometry in
            Path { path in
                path.move(to: CGPoint(x: 1, y: 0))
                path.addLine(to: CGPoint(x: 1, y: geometry.size.height))
            }
            .stroke(
                MelixDesignTokens.accent.opacity(0.5),
                style: StrokeStyle(lineWidth: 2, lineCap: .round, dash: [1, 4])
            )
        }
        .frame(width: 2)
        .accessibilityHidden(true)
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
