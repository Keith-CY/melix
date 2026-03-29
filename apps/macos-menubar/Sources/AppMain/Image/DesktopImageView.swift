import AppKit
import MelixControlPlaneProtocol
import SwiftUI

struct DesktopImageTabView: View {
    let viewModel: RuntimeViewModel

    @MainActor
    func cancelSelectedJob() {
        Task {
            await viewModel.cancelSelectedImageJob()
        }
    }

    var body: some View {
        HSplitView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Image")
                        .font(.largeTitle)
                        .bold()

                    Spacer()

                    Picker(
                        "Model",
                        selection: Binding(
                            get: { viewModel.selectedImageModelID },
                            set: { viewModel.selectedImageModelID = $0 }
                        )
                    ) {
                        ForEach(viewModel.imageModels, id: \.modelID) { model in
                            Text(model.modelID).tag(model.modelID)
                        }
                    }
                    .frame(width: 220)
                }

                GroupBox("Prompt") {
                    VStack(alignment: .leading, spacing: 8) {
                        TextEditor(
                            text: Binding(
                                get: { viewModel.imagePromptText },
                                set: { viewModel.imagePromptText = $0 }
                            )
                        )
                        .font(.body.monospaced())
                        .frame(minHeight: 120)

                        HStack {
                            TextField(
                                "Size",
                                text: Binding(
                                    get: { viewModel.imageSize },
                                    set: { viewModel.imageSize = $0 }
                                )
                            )
                            .textFieldStyle(.roundedBorder)
                            Stepper(
                                "Variants \(viewModel.imageVariantCount)",
                                value: Binding(
                                    get: { Int(viewModel.imageVariantCount) },
                                    set: { viewModel.imageVariantCount = UInt32(max(1, $0)) }
                                ),
                                in: 1...4
                            )
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                GroupBox("Edit Sources") {
                    VStack(alignment: .leading, spacing: 8) {
                        TextField(
                            "Source image URI",
                            text: Binding(
                                get: { viewModel.imageEditSourceURL },
                                set: { viewModel.imageEditSourceURL = $0 }
                            )
                        )
                        .textFieldStyle(.roundedBorder)

                        TextField(
                            "Mask URI (optional)",
                            text: Binding(
                                get: { viewModel.imageEditMaskURL },
                                set: { viewModel.imageEditMaskURL = $0 }
                            )
                        )
                        .textFieldStyle(.roundedBorder)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                HStack {
                    Text(viewModel.imageStatusText)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button("Generate") {
                        Task { await viewModel.submitImageGeneration() }
                    }
                    .buttonStyle(.borderedProminent)
                    .disabled(viewModel.imagePromptText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                    Button("Edit") {
                        Task { await viewModel.submitImageEdit() }
                    }
                    .buttonStyle(.bordered)
                    .disabled(viewModel.imageEditSourceURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }

                GroupBox("Jobs") {
                    if viewModel.imageJobs.isEmpty {
                        ContentUnavailableView(
                            "No image jobs yet",
                            systemImage: "photo.on.rectangle.angled",
                            description: Text("Submit a generation or edit request to track image artifacts and progress through the control plane.")
                        )
                    } else {
                        ScrollView {
                            LazyVStack(alignment: .leading, spacing: 10) {
                                ForEach(viewModel.imageJobs, id: \.jobID) { job in
                                    Button {
                                        viewModel.selectImageJob(jobID: job.jobID)
                                    } label: {
                                        DesktopImageJobRowView(
                                            job: job,
                                            isSelected: viewModel.selectedImageJobID == job.jobID
                                        )
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }
                }

                Spacer()
            }
            .padding(20)

            VStack(alignment: .leading, spacing: 16) {
                GroupBox("Selected Job") {
                    if let job = viewModel.selectedImageJob {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(job.jobID)
                                .font(.headline)
                            Text("\(job.operation) • \(job.modelID)")
                                .foregroundStyle(.secondary)
                            Text("\(job.progress.stage) • \(String(format: "%.0f%%", job.progress.pct * 100))")
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(.secondary)
                            HStack {
                                Spacer()
                                Button("Cancel", action: cancelSelectedJob)
                                .disabled(job.cancelable == false)
                            }
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    } else {
                        Text("Select an image job to inspect artifacts.")
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }

                GroupBox("Artifacts") {
                    if let job = viewModel.selectedImageJob, job.artifacts.isEmpty == false {
                        ScrollView {
                            LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 12)], spacing: 12) {
                                ForEach(job.artifacts, id: \.artifactID) { artifact in
                                    DesktopImageArtifactCardView(artifact: artifact)
                                }
                            }
                        }
                    } else {
                        Text("No artifacts available yet.")
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }

                Spacer()
            }
            .frame(minWidth: 320, idealWidth: 420)
            .padding(20)
        }
    }
}

private struct DesktopImageJobRowView: View {
    let job: Melix_Controlplane_V1_ImageJobSummary
    let isSelected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(job.operation)
                    .font(.headline)
                Spacer()
                Text(stateText)
                    .font(.caption.monospaced())
                    .foregroundStyle(.secondary)
            }
            Text(job.jobID)
                .font(.caption.monospaced())
                .foregroundStyle(.secondary)
            Text("\(job.progress.stage) • \(String(format: "%.0f%%", job.progress.pct * 100))")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(backgroundStyle, in: RoundedRectangle(cornerRadius: 12))
    }

    private var stateText: String {
        switch job.state {
        case .imageJobQueued:
            return "queued"
        case .imageJobRunning:
            return "running"
        case .imageJobCompleted:
            return "completed"
        case .imageJobCanceled:
            return "canceled"
        case .imageJobFailed:
            return "failed"
        default:
            return "unknown"
        }
    }

    private var backgroundStyle: Color {
        if isSelected {
            return .blue.opacity(0.16)
        }
        switch job.state {
        case .imageJobCompleted:
            return .green.opacity(0.10)
        case .imageJobFailed:
            return .red.opacity(0.10)
        case .imageJobRunning:
            return .orange.opacity(0.10)
        default:
            return .secondary.opacity(0.08)
        }
    }
}

private struct DesktopImageArtifactCardView: View {
    let artifact: Melix_Controlplane_V1_ImageArtifactRef

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            preview
                .frame(maxWidth: .infinity)
            Text(roleText)
                .font(.headline)
            Text(artifact.storageUri)
                .font(.caption.monospaced())
                .foregroundStyle(.secondary)
                .lineLimit(2)
            Text("\(artifact.width)x\(artifact.height) • \(artifact.format)")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding()
        .background(.quaternary.opacity(0.6), in: RoundedRectangle(cornerRadius: 12))
    }

    @ViewBuilder
    private var preview: some View {
        if let fileURL = resolvedFileURL, let image = NSImage(contentsOf: fileURL) {
            Image(nsImage: image)
                .resizable()
                .scaledToFit()
                .frame(height: 160)
                .clipShape(RoundedRectangle(cornerRadius: 10))
        } else {
            RoundedRectangle(cornerRadius: 10)
                .fill(.tertiary.opacity(0.3))
                .frame(height: 160)
                .overlay {
                    VStack(spacing: 6) {
                        Image(systemName: "photo")
                            .font(.title2)
                        Text(roleText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
        }
    }

    private var resolvedFileURL: URL? {
        if artifact.storageUri.hasPrefix("file://") {
            return URL(string: artifact.storageUri)
        }
        guard artifact.storageUri.hasPrefix("/") else {
            return nil
        }
        return URL(fileURLWithPath: artifact.storageUri)
    }

    private var roleText: String {
        switch artifact.role {
        case .imageArtifactInput:
            return "Input"
        case .imageArtifactMask:
            return "Mask"
        case .imageArtifactGenerated:
            return "Generated"
        case .imageArtifactEditSource:
            return "Edit Source"
        case .imageArtifactPreview:
            return "Preview"
        default:
            return "Artifact"
        }
    }
}
