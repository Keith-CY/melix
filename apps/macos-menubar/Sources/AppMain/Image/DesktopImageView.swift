import AppKit
import MelixControlPlaneProtocol
import SwiftUI

struct DesktopImageTabView: View {
    let viewModel: RuntimeViewModel
    @State private var showsSidebar = true
    @State private var showsInspector = true
    @State private var selectedMode: DesktopImageWorkspaceMode = .generate

    @MainActor
    func cancelSelectedJob() {
        Task {
            await viewModel.cancelSelectedImageJob()
        }
    }

    var body: some View {
        HSplitView {
            if showsSidebar {
                DesktopImageJobsSidebar(viewModel: viewModel)
                    .frame(minWidth: 250, idealWidth: 270)
            }

            DesktopImageWorkspace(
                viewModel: viewModel,
                selectedMode: $selectedMode,
                showsSidebar: $showsSidebar,
                showsInspector: $showsInspector
            )

            if showsInspector {
                DesktopImageInspector(viewModel: viewModel, cancelSelectedJob: cancelSelectedJob)
                    .frame(minWidth: 300, idealWidth: 320)
            }
        }
    }
}

enum DesktopImageWorkspaceMode: String, CaseIterable, Identifiable {
    case generate = "Generate"
    case edit = "Edit"

    var id: String { rawValue }
}

struct DesktopImageJobsSidebar: View {
    let viewModel: RuntimeViewModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Image Jobs")
                .font(.headline)

            if viewModel.imageJobs.isEmpty {
                ContentUnavailableView(
                    "No image jobs yet",
                    systemImage: "photo.on.rectangle.angled",
                    description: Text("Submit a generation or edit request to track image artifacts and progress.")
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

            Spacer()
        }
        .padding(20)
    }
}

struct DesktopImageWorkspace: View {
    let viewModel: RuntimeViewModel
    @Binding var selectedMode: DesktopImageWorkspaceMode
    @Binding var showsSidebar: Bool
    @Binding var showsInspector: Bool

    private var workflowRole: RuntimeImageWorkflowRole {
        selectedMode == .generate ? .generate : .edit
    }

    private var availableImageModels: [RuntimeModelRow] {
        viewModel.imageModels(for: workflowRole)
    }

    private var selectedImageModelSummary: RuntimeModelRow? {
        availableImageModels.first(where: { $0.modelID == viewModel.selectedImageModelID(for: workflowRole) })
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                HStack {
                    Text("Image")
                        .font(.largeTitle.weight(.semibold))
                    Spacer()
                    Button(showsSidebar ? "Hide List" : "Show List") {
                        showsSidebar.toggle()
                    }
                    Button(showsInspector ? "Hide Inspector" : "Show Inspector") {
                        showsInspector.toggle()
                    }
                }

                Picker("Workflow", selection: $selectedMode) {
                    ForEach(DesktopImageWorkspaceMode.allCases) { mode in
                        Text(mode.rawValue).tag(mode)
                    }
                }
                .pickerStyle(.segmented)

                Picker(
                    "Model",
                    selection: Binding(
                        get: { viewModel.selectedImageModelID(for: workflowRole) },
                        set: { viewModel.setSelectedImageModelID($0, for: workflowRole) }
                    )
                ) {
                    ForEach(availableImageModels, id: \.modelID) { model in
                        Text(model.modelID).tag(model.modelID)
                    }
                }
                .frame(maxWidth: 320)

                if let selectedImageModelSummary {
                    Text(imageRoleSummary(for: selectedImageModelSummary))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                GroupBox(selectedMode.rawValue) {
                    VStack(alignment: .leading, spacing: 10) {
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

                        if selectedMode == .edit {
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

                        HStack {
                            Text(viewModel.imageStatusText)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Button("Run") {
                                Task {
                                    if selectedMode == .generate {
                                        await viewModel.submitImageGeneration()
                                    } else {
                                        await viewModel.submitImageEdit()
                                    }
                                }
                            }
                            .buttonStyle(.borderedProminent)
                            .disabled(isActionDisabled)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                GroupBox("Results") {
                    if let job = viewModel.selectedImageJob, job.artifacts.isEmpty == false {
                        LazyVGrid(columns: [GridItem(.adaptive(minimum: 220), spacing: 12)], spacing: 12) {
                            ForEach(job.artifacts, id: \.artifactID) { artifact in
                                DesktopImageArtifactCardView(artifact: artifact)
                            }
                        }
                    } else {
                        Text("Select a job to review generated artifacts.")
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .padding(20)
        }
    }

    private var isActionDisabled: Bool {
        switch selectedMode {
        case .generate:
            return viewModel.imagePromptText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || availableImageModels.isEmpty
        case .edit:
            return viewModel.imageEditSourceURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                || availableImageModels.isEmpty
        }
    }

    private func imageRoleSummary(for model: RuntimeModelRow) -> String {
        let familyText = model.imageFamilyID.isEmpty ? "generic-image" : model.imageFamilyID
        let roleText: String
        switch workflowRole {
        case .generate:
            roleText = model.imageSupportsEdit ? "Supports generate + edit" : "Supports generate"
        case .edit:
            roleText = model.imageSupportsGeneration ? "Supports edit + generate" : "Supports edit"
        }
        return "Family \(familyText) • \(roleText)"
    }
}

struct DesktopImageInspector: View {
    let viewModel: RuntimeViewModel
    let cancelSelectedJob: @MainActor () -> Void

    var body: some View {
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
                    Text("Select an image job to inspect metadata.")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            GroupBox("Artifacts") {
                if let job = viewModel.selectedImageJob, job.artifacts.isEmpty == false {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(job.artifacts, id: \.artifactID) { artifact in
                            Text(artifact.storageUri)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Text("No artifacts available yet.")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            }

            Spacer()
        }
        .padding(20)
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
