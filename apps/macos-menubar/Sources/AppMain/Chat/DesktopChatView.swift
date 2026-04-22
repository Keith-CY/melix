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
}

enum DesktopChatEmptyTranscriptCopy {
    static let title = "Start a conversation"
    static let detail = "Type a prompt below. Messages will appear here after you send."
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

struct DesktopChatTabView: View {
    let viewModel: RuntimeViewModel
    @Binding private var showsSidebar: Bool
    @Binding private var showsInspector: Bool

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
                showsInspector: $showsInspector
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            DesktopWorkspacePaneSlot(
                role: .inspector,
                isVisible: showsInspector,
                idealWidth: DesktopChatLayoutMetrics.inspectorIdealWidth
            ) {
                DesktopChatSessionInspector(viewModel: viewModel)
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
                    .melixSectionLabel()
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

    private var isSendDisabled: Bool {
        viewModel.chatComposerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        || viewModel.isChatStreaming
        || viewModel.selectedChatServerSession?.isInteractiveReady != true
    }

    private func submitChatPrompt() {
        Task { await viewModel.submitChatPrompt() }
    }

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
                        MelixSectionCard(DesktopChatEmptyTranscriptCopy.title) {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(DesktopChatEmptyTranscriptCopy.detail)
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
                DesktopChatComposerTextView(
                    text: Binding(
                        get: { viewModel.chatComposerText },
                        set: { viewModel.chatComposerText = $0 }
                    ),
                    isSubmitAvailable: viewModel.isChatStreaming == false
                    && viewModel.selectedChatServerSession?.isInteractiveReady == true,
                    onCommandSubmit: { draft in
                        viewModel.chatComposerText = draft
                        submitChatPrompt()
                    }
                )
                .frame(height: DesktopChatLayoutMetrics.composerMinHeight)
                .padding(.horizontal, 10)
                .padding(.vertical, 8)
                .background(
                    RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.lg)
                        .fill(Color(nsColor: .textBackgroundColor).opacity(0.75))
                )
                .overlay(
                    RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.lg)
                        .stroke(Color.primary.opacity(MelixDesignTokens.StrokeOpacity.interactive), lineWidth: 1)
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
                    Button("Send \u{2318}\u{21A9}") {
                        submitChatPrompt()
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(isSendDisabled)
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
            MelixSectionCard("Session") {
                VStack(alignment: .leading, spacing: 6) {
                    Text(viewModel.selectedChatSession?.statusText ?? "Idle")
                        .font(.headline)
                    if let server = viewModel.selectedChatServerSession {
                        Text(server.effectiveBaseURL)
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                    }
                    if let exportPath = viewModel.selectedChatSession?.exportPath, !exportPath.isEmpty {
                        Text(exportPath)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }

            MelixSectionCard("Analysis Routes") {
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
            }

            if !viewModel.lastChatRequestID.isEmpty || !viewModel.lastChatUsageText.isEmpty {
                MelixSectionCard("Runtime") {
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
        .background(backgroundStyle, in: RoundedRectangle(cornerRadius: MelixDesignTokens.Radius.xl))
    }

    private var backgroundStyle: some ShapeStyle {
        switch entry.kind {
        case .user:
            return MelixDesignTokens.BubbleTint.user.opacity(MelixDesignTokens.BubbleOpacity.user)
        case .assistant:
            return MelixDesignTokens.BubbleTint.assistant.opacity(MelixDesignTokens.BubbleOpacity.assistant)
        case .reasoning:
            return MelixDesignTokens.BubbleTint.reasoning.opacity(MelixDesignTokens.BubbleOpacity.reasoning)
        case .tool:
            return MelixDesignTokens.BubbleTint.tool.opacity(MelixDesignTokens.BubbleOpacity.tool)
        case .error:
            return MelixDesignTokens.BubbleTint.error.opacity(MelixDesignTokens.BubbleOpacity.error)
        }
    }
}
