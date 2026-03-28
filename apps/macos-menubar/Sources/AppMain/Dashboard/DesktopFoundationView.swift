import SwiftUI

@MainActor
public struct DesktopFoundationRootView: View {
    private let viewModel: RuntimeViewModel

    public init(viewModel: RuntimeViewModel) {
        self.viewModel = viewModel
    }

    public var body: some View {
        let foundation = viewModel.desktopFoundationState

        TabView {
            DesktopDashboardTabView(foundation: foundation)
                .tabItem {
                    Label("Dashboard", systemImage: "gauge.with.dots.needle.67percent")
                }

            DesktopModelsTabView(foundation: foundation, viewModel: viewModel)
                .tabItem {
                    Label("Models", systemImage: "cube.transparent")
                }

            DesktopSettingsTabView(foundation: foundation)
                .tabItem {
                    Label("Settings", systemImage: "slider.horizontal.3")
                }

            DesktopLogsTabView(foundation: foundation)
                .tabItem {
                    Label("Logs", systemImage: "doc.text.magnifyingglass")
                }

            DesktopBenchTabView(foundation: foundation)
                .tabItem {
                    Label("Bench", systemImage: "speedometer")
                }

            DesktopAPIReferenceTabView(foundation: foundation)
                .tabItem {
                    Label("API", systemImage: "chevron.left.forwardslash.chevron.right")
                }
        }
        .frame(minWidth: 980, minHeight: 680)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button("Refresh") {
                    Task { await viewModel.refreshDesktopFoundation() }
                }
            }
        }
    }
}

private struct DesktopDashboardTabView: View {
    let foundation: DesktopFoundationState

    var body: some View {
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
                        .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 12))
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
            }
            .padding(20)
        }
    }
}

private struct DesktopModelsTabView: View {
    let foundation: DesktopFoundationState
    let viewModel: RuntimeViewModel

    var body: some View {
        List(foundation.models, id: \.modelID) { model in
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(model.modelID)
                        .font(.headline)
                    Text("\(model.kind) • \(model.stateText) • \(model.maxContext) ctx")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button(model.actionTitle) {
                    Task {
                        if model.isLoaded {
                            await viewModel.unloadModel(modelID: model.modelID)
                        } else {
                            await viewModel.loadModel(modelID: model.modelID)
                        }
                    }
                }
                .buttonStyle(.borderedProminent)
            }
            .padding(.vertical, 4)
        }
    }
}

private struct DesktopSettingsTabView: View {
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

private struct DesktopLogsTabView: View {
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

private struct DesktopBenchTabView: View {
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

private struct DesktopAPIReferenceTabView: View {
    let foundation: DesktopFoundationState

    var body: some View {
        List(foundation.apiReference) { endpoint in
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
}
