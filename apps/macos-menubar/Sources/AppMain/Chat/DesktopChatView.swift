import SwiftUI

struct DesktopChatTabView: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Chat")
                        .font(.largeTitle)
                        .bold()

                    Spacer()

                    Picker(
                        "Model",
                        selection: Binding(
                            get: { viewModel.selectedChatModelID },
                            set: { viewModel.selectedChatModelID = $0 }
                        )
                    ) {
                        ForEach(viewModel.models.filter { $0.kind == "text" }, id: \.modelID) { model in
                            Text(model.modelID).tag(model.modelID)
                        }
                    }
                    .frame(width: 220)

                    Button("Clear") {
                        viewModel.clearChatTranscript()
                    }
                }

                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        if viewModel.chatTranscript.isEmpty {
                            GroupBox {
                                VStack(alignment: .leading, spacing: 6) {
                                    Text("No transcript yet")
                                        .font(.headline)
                                    Text("Submit a prompt to stream assistant, reasoning, and tool-call state through the control plane.")
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
                        Button("Send") {
                            Task { await viewModel.submitChatPrompt() }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(viewModel.chatComposerText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || viewModel.isChatStreaming)
                    }
                }
            }
            .padding(20)

            VStack(alignment: .leading, spacing: 12) {
                GroupBox("Runtime") {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(viewModel.chatStatusText)
                            .font(.headline)
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

                Spacer()
            }
            .frame(minWidth: 280, idealWidth: 320)
            .padding(20)
        }
    }
}

private struct DesktopChatTranscriptRowView: View {
    let entry: DesktopChatTranscriptEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(entry.title)
                    .font(.headline)
                Spacer()
                if !entry.detail.isEmpty {
                    Text(entry.detail)
                        .font(.caption.monospaced())
                        .foregroundStyle(.secondary)
                }
            }
            Text(entry.body.isEmpty ? "…" : entry.body)
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
