import AppKit
import SwiftUI

@MainActor
struct DesktopWorkspaceShellView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        let foundation = viewModel.desktopFoundationState

        VStack(spacing: 0) {
            if let banner = viewModel.desktopBannerState {
                DesktopShellBannerView(banner: banner)
            }

            DesktopShellHeaderView(viewModel: viewModel)
                .padding(.horizontal, 20)
                .padding(.top, 18)
                .padding(.bottom, 14)

            Divider()

            DesktopHeaderShelfView(viewModel: viewModel)
                .padding(.horizontal, 20)
                .padding(.vertical, 12)

            Divider()

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

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            Image(systemName: banner.severity == .critical ? "exclamationmark.triangle.fill" : "exclamationmark.circle.fill")
                .foregroundStyle(.white)
            VStack(alignment: .leading, spacing: 4) {
                Text(banner.title)
                    .font(.headline)
                    .foregroundStyle(.white)
                Text(banner.detail)
                    .font(.caption)
                    .foregroundStyle(.white.opacity(0.9))
            }
            Spacer()
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .background(banner.severity == .critical ? Color.red : Color.orange)
    }
}

private struct DesktopShellHeaderView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        ZStack {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Melix Workspace")
                        .font(.title2.weight(.semibold))
                    Text("\(viewModel.serverStateText) • \(viewModel.connectionStateText)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    Text(viewModel.daemonInstanceID.isEmpty ? "No daemon id" : viewModel.daemonInstanceID)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                    Text(viewModel.protocolVersion)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                }
            }

            HStack(spacing: 10) {
                ForEach(DesktopSurface.allCases) { surface in
                    Button {
                        viewModel.selectSurface(surface)
                    } label: {
                        Label(surface.rawValue, systemImage: surface.symbolName)
                            .font(.subheadline.weight(.medium))
                            .padding(.horizontal, 14)
                            .padding(.vertical, 8)
                            .background(
                                viewModel.selectedSurface == surface
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
}

private struct DesktopHeaderShelfView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        HStack(spacing: 10) {
            Button("New Chat") {
                viewModel.createChatSession()
            }
            .buttonStyle(.borderedProminent)

            Button("New Image Job") {
                viewModel.selectSurface(.image)
            }
            .buttonStyle(.bordered)

            Button("New Server Session") {
                viewModel.createServerSession()
            }
            .buttonStyle(.bordered)

            Button("Open Command Center") {
                viewModel.openCommandCenter()
            }
            .buttonStyle(.bordered)

            Spacer()
        }
    }
}

struct DesktopCommandCenterView: View {
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
    @State private var showsAdvanced = true

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
                                        Text(session.lifecycle.rawValue)
                                            .font(.caption)
                                            .foregroundStyle(session.isRunning ? .green : .secondary)
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

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                HStack {
                    Text("Server")
                        .font(.largeTitle.weight(.semibold))
                    Spacer()
                    Button(showsSidebar ? "Hide List" : "Show List") {
                        showsSidebar.toggle()
                    }
                    Button(showsInspector ? "Hide Inspector" : "Show Inspector") {
                        showsInspector.toggle()
                    }
                }

                if let session = viewModel.selectedServerSession {
                    Text("Choose model, configure listener, then start the server session.")
                        .foregroundStyle(.secondary)

                    GroupBox("Basic Configuration") {
                        VStack(alignment: .leading, spacing: 12) {
                            Picker(
                                "Served Model",
                                selection: Binding(
                                    get: { session.modelID },
                                    set: { viewModel.updateSelectedServerSessionModelID($0) }
                                )
                            ) {
                                ForEach(viewModel.models.filter { $0.kind == "text" }, id: \.modelID) { model in
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
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }

                    GroupBox {
                        DisclosureGroup("Advanced Defaults", isExpanded: $showsAdvanced) {
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
                                            get: { viewModel.selectedServerSession?.servingDefaults.maxTokens ?? 1024 },
                                            set: { viewModel.updateSelectedServerSessionMaxTokens($0) }
                                        ),
                                        format: .number
                                    )
                                    .textFieldStyle(.roundedBorder)

                                    TextField(
                                        "Max concurrent",
                                        value: Binding(
                                            get: { viewModel.selectedServerSession?.servingDefaults.maxConcurrentRequests ?? 4 },
                                            set: { viewModel.updateSelectedServerSessionMaxConcurrentRequests($0) }
                                        ),
                                        format: .number
                                    )
                                    .textFieldStyle(.roundedBorder)
                                }
                            }
                            .padding(.top, 12)
                        }
                    }

                    HStack {
                        Button("Start") {
                            Task { await viewModel.startSelectedServerSession() }
                        }
                        .buttonStyle(.borderedProminent)

                        Button("Stop") {
                            Task { await viewModel.stopSelectedServerSession() }
                        }
                        .buttonStyle(.bordered)
                        .disabled(viewModel.selectedServerSession?.isRunning != true)
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
                        Text(session.lifecycle.rawValue)
                            .font(.headline)
                        Text(session.lastKnownModelStateText.isEmpty ? session.modelID : "\(session.modelID) • \(session.lastKnownModelStateText)")
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                GroupBox("Listener") {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(session.baseURL)
                            .font(.body.monospaced())
                        HStack {
                            Button("Copy URL") {
                                copyToPasteboard(session.baseURL)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                DesktopServerGatewayAccessSummaryView(session: session)

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
                VStack(alignment: .leading, spacing: 12) {
                    Text("Tools")
                        .font(.headline)
                    ForEach(DesktopToolSection.allCases) { section in
                        Button {
                            viewModel.selectToolSection(section)
                        } label: {
                            Label(section.rawValue, systemImage: section.symbolName)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 10)
                                .background(
                                    viewModel.selectedToolSection == section
                                    ? Color.accentColor.opacity(0.14)
                                    : Color.secondary.opacity(0.06),
                                    in: RoundedRectangle(cornerRadius: 12)
                                )
                        }
                        .buttonStyle(.plain)
                    }
                    Spacer()
                }
                .padding(20)
                .frame(minWidth: 240, idealWidth: 250)
            }

            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    HStack {
                        Text(viewModel.selectedToolSection.rawValue)
                            .font(.largeTitle.weight(.semibold))
                        Spacer()
                        Button(showsSidebar ? "Hide List" : "Show List") {
                            showsSidebar.toggle()
                        }
                        Button(showsInspector ? "Hide Inspector" : "Show Inspector") {
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

private struct DesktopDownloadsToolSectionView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Model ingress and artifact publishing stay under Tools, not Server.")
                .foregroundStyle(.secondary)

            if viewModel.audioSetupActions.isEmpty == false {
                GroupBox("Audio Setup") {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(viewModel.audioSetupActions) { action in
                            HStack(alignment: .top) {
                                VStack(alignment: .leading, spacing: 4) {
                                    Text(action.alias)
                                        .font(.headline)
                                    Text(action.detail)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                                Spacer()
                                Button(action.actionTitle) {
                                    Task {
                                        switch action.kind {
                                        case .installRuntime:
                                            await viewModel.installAudioRuntime(modelID: action.modelID)
                                        case .downloadModel:
                                            await viewModel.downloadAudioModel(modelID: action.modelID)
                                        }
                                    }
                                }
                                .buttonStyle(.borderedProminent)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            HStack {
                Button("Download Model") {
                    Task { await viewModel.downloadPrimaryModel() }
                }
                .buttonStyle(.borderedProminent)

                Button("Upload Artifact") {
                    Task { await viewModel.uploadPrimaryModel() }
                }
                .buttonStyle(.bordered)
            }

            if let operation = viewModel.lastModelOperation {
                GroupBox("Recent Transfer") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("\(operation.operation) • \(operation.modelID)")
                            .font(.headline)
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

private struct DesktopTrainingToolSectionView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Button("Train LoRA") {
                    Task { await viewModel.trainPrimaryModel() }
                }
                .buttonStyle(.borderedProminent)

                Button("Publish Adapter") {
                    Task { await viewModel.publishLatestAdapter() }
                }
                .buttonStyle(.bordered)
                .disabled(viewModel.latestAdapterPackage == nil)
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
                                Text(entry.stageText)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }
}

private struct DesktopDiagnosticsToolSectionView: View {
    let viewModel: RuntimeViewModel
    let foundation: DesktopFoundationState

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Button("Inspect") {
                    Task { await viewModel.inspectPrimaryModel() }
                }
                Button("Doctor") {
                    Task { await viewModel.runDoctor() }
                }
                Button("Bench") {
                    Task { await viewModel.runBench() }
                }
                Button("Refresh Tooling") {
                    Task { await viewModel.refreshModelOpsProductState() }
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
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            if let report = viewModel.lastDoctorReport {
                GroupBox("Doctor Report") {
                    Text(report.markdown)
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            GroupBox("Bench Metrics") {
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
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
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
                    HStack {
                        Text("API")
                            .font(.largeTitle.weight(.semibold))
                        Spacer()
                        Button(showsSidebar ? "Hide List" : "Show List") {
                            showsSidebar.toggle()
                        }
                        Button(showsInspector ? "Hide Inspector" : "Show Inspector") {
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
                        DesktopBoundAgentIntegrationPanel(viewModel: viewModel)
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
        viewModel.selectedServerSession?.baseURL ?? "http://127.0.0.1:8080/v1"
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
            return "\(exportLead)Use Authorization: Bearer \(selectedSession.integrationAuthValue) for \(selectedSession.baseURL)."
        }
        return "\(exportLead)Local trusted mode does not require authentication for \(selectedSession.baseURL)."
    case .configuredDisabled:
        return "\(exportLead)Shared access is configured but disabled. Local trusted clients can call \(selectedSession.baseURL) without auth. Prepared key hints: \(selectedSession.accessKeyHintsText)."
    case .enabled:
        return "\(exportLead)Shared access is enabled. Use x-api-key or Authorization: Bearer with \(selectedSession.integrationAuthValue) for \(selectedSession.baseURL). Key hints: \(selectedSession.accessKeyHintsText)."
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
