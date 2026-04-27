import AppKit
import MelixControlPlaneProtocol
import SwiftUI

struct DesktopImageTabView: View {
    let viewModel: RuntimeViewModel
    @Binding private var showsSidebar: Bool
    @Binding private var showsInspector: Bool
    @State private var selectedMode: DesktopImageWorkspaceMode = .generate

    init(viewModel: RuntimeViewModel) {
        self.viewModel = viewModel
        _showsSidebar = .constant(true)
        _showsInspector = .constant(false)
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

    @MainActor
    func cancelSelectedJob() {
        Task {
            await viewModel.cancelSelectedImageJob()
        }
    }

    @MainActor
    func redoSelectedJob() {
        Task {
            await viewModel.redoSelectedImageJob()
        }
    }

    @MainActor
    func prepareReiterateFromSelectedJob() {
        selectedMode = .edit
        viewModel.prepareReiterateFromSelectedImageJob()
    }

    var body: some View {
        HStack(spacing: 0) {
            DesktopWorkspacePaneSlot(
                role: .sidebar,
                isVisible: showsSidebar,
                idealWidth: 270
            ) {
                DesktopImageJobsSidebar(viewModel: viewModel)
            }

            DesktopImageWorkspace(
                viewModel: viewModel,
                selectedMode: $selectedMode,
                showsSidebar: $showsSidebar,
                showsInspector: $showsInspector
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            DesktopWorkspacePaneSlot(
                role: .inspector,
                isVisible: showsInspector,
                idealWidth: 320
            ) {
                DesktopImageInspector(
                    viewModel: viewModel,
                    cancelSelectedJob: cancelSelectedJob,
                    redoSelectedJob: redoSelectedJob,
                    prepareReiterateFromSelectedJob: prepareReiterateFromSelectedJob
                )
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
    @State private var showsAdvancedDefaults = DesktopImageWorkspaceDefaults.showsAdvancedDefaults

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
                DesktopWorkspaceHeader(title: "Image") {}

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

                MelixSectionCard("Defaults") {
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text("Source")
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(viewModel.imageDefaultsSourceText)
                        }
                        HStack {
                            Text("Effective models")
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(effectiveModelSummary)
                                .multilineTextAlignment(.trailing)
                        }
                        HStack {
                            Text("Effective parameters")
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(effectiveDefaultsSummary)
                                .multilineTextAlignment(.trailing)
                        }
                        HStack {
                            Text("Timeout policy")
                                .foregroundStyle(.secondary)
                            Spacer()
                            Text(viewModel.imageTimeoutPolicyText)
                                .multilineTextAlignment(.trailing)
                        }
                    }
                    .font(.caption)
                }

                MelixSectionCard(selectedMode.rawValue) {
                    VStack(alignment: .leading, spacing: 10) {
                        ZStack(alignment: .topLeading) {
                            TextEditor(
                                text: Binding(
                                    get: { viewModel.imagePromptText },
                                    set: { viewModel.imagePromptText = $0 }
                                )
                            )
                            .font(.body.monospaced())
                            .frame(minHeight: 120)

                            if viewModel.imagePromptText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                                Text(selectedMode == .generate ? "Describe the image to generate..." : "Describe the edit to apply...")
                                    .font(.body.monospaced())
                                    .foregroundStyle(.tertiary)
                                    .padding(.top, 8)
                                    .padding(.leading, 5)
                                    .allowsHitTesting(false)
                            }
                        }

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

                        DisclosureGroup(DesktopImageWorkspaceDefaults.advancedDefaultsTitle, isExpanded: $showsAdvancedDefaults) {
                            VStack(alignment: .leading, spacing: 10) {
                                HStack {
                                    TextField(
                                        "Steps",
                                        text: Binding(
                                            get: { viewModel.imageSteps },
                                            set: { viewModel.imageSteps = $0 }
                                        )
                                    )
                                    .textFieldStyle(.roundedBorder)

                                    TextField(
                                        "Guidance",
                                        text: Binding(
                                            get: { viewModel.imageGuidance },
                                            set: { viewModel.imageGuidance = $0 }
                                        )
                                    )
                                    .textFieldStyle(.roundedBorder)

                                    if selectedMode == .edit {
                                        TextField(
                                            "Strength",
                                            text: Binding(
                                                get: { viewModel.imageStrength },
                                                set: { viewModel.imageStrength = $0 }
                                            )
                                        )
                                        .textFieldStyle(.roundedBorder)
                                    }
                                }

                                TextField(
                                    "Negative prompt",
                                    text: Binding(
                                        get: { viewModel.imageNegativePrompt },
                                        set: { viewModel.imageNegativePrompt = $0 }
                                    )
                                )
                                .textFieldStyle(.roundedBorder)

                                HStack {
                                    Button("Save Defaults", action: viewModel.applyImageDefaultsFromUI)
                                        .buttonStyle(.bordered)
                                    Text(effectiveDefaultsSummary)
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .padding(.top, 8)
                        }

                        if selectedMode == .edit {
                            Picker(
                                "Edit mode",
                                selection: Binding(
                                    get: { viewModel.imageEditMode },
                                    set: { viewModel.imageEditMode = $0 }
                                )
                            ) {
                                Text("Edit").tag(RuntimeImageEditMode.edit)
                                Text("Variation").tag(RuntimeImageEditMode.variation)
                                Text("Iterate").tag(RuntimeImageEditMode.iterate)
                            }
                            .pickerStyle(.segmented)

                            if let sourceArtifactSummary = viewModel.imageEditSourceArtifactSummaryText {
                                Text("Source artifact • \(sourceArtifactSummary)")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

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
                            Text(imageActionStatusText)
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
                            .keyboardShortcut(.return, modifiers: .command)
                            .disabled(isActionDisabled)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }

                MelixSectionCard("Results") {
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
            if availableImageModels.isEmpty {
                return true
            }
            switch viewModel.imageEditMode {
            case .edit:
                return viewModel.imageEditSourceURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            case .variation:
                return viewModel.imageEditSourceArtifactID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            case .iterate:
                return viewModel.imageEditSourceArtifactID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    || viewModel.imagePromptText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            }
        }
    }

    private var imageActionStatusText: String {
        if isActionDisabled {
            if availableImageModels.isEmpty {
                return "Select an image-capable model before running."
            }
            switch selectedMode {
            case .generate:
                return "Enter a prompt before running."
            case .edit:
                switch viewModel.imageEditMode {
                case .edit:
                    return "Add a source image URI before editing."
                case .variation:
                    return "Select a source artifact before creating a variation."
                case .iterate:
                    return "Select a source artifact and enter a prompt before iterating."
                }
            }
        }
        return viewModel.imageStatusText
    }

    private func imageRoleSummary(for model: RuntimeModelRow) -> String {
        let familyText = model.imageFamilyID.isEmpty ? "generic-image" : model.imageFamilyID
        let defaultRoleText: String
        switch model.imageDefaultWorkflowRole {
        case RuntimeImageWorkflowRole.generate.rawValue:
            defaultRoleText = "Primary role generate"
        case RuntimeImageWorkflowRole.edit.rawValue:
            defaultRoleText = "Primary role edit"
        default:
            defaultRoleText = "Primary role mixed"
        }
        let roleText: String
        switch workflowRole {
        case .generate:
            roleText = model.imageSupportsEdit ? "Supports generate + edit" : "Supports generate"
        case .edit:
            roleText = model.imageSupportsGeneration ? "Supports edit + generate" : "Supports edit"
        }
        return "Family \(familyText) • \(roleText) • \(defaultRoleText)"
    }

    private var effectiveModelSummary: String {
        let generateModelID = viewModel.effectiveImageGenerateModelID.isEmpty
            ? viewModel.selectedImageModelID(for: .generate)
            : viewModel.effectiveImageGenerateModelID
        let editModelID = viewModel.effectiveImageEditModelID.isEmpty
            ? viewModel.selectedImageModelID(for: .edit)
            : viewModel.effectiveImageEditModelID
        return "Generate \(generateModelID)\nEdit \(editModelID)"
    }

    private var effectiveDefaultsSummary: String {
        let negativePrompt = viewModel.effectiveImageNegativePrompt.isEmpty
            ? "None"
            : viewModel.effectiveImageNegativePrompt
        return """
        size \(viewModel.effectiveImageSize) • steps \(viewModel.effectiveImageSteps)
        guidance \(viewModel.effectiveImageGuidance) • strength \(viewModel.effectiveImageStrength)
        negative \(negativePrompt)
        """
    }
}

enum DesktopImageWorkspaceDefaults {
    static let showsAdvancedDefaults = false
    static let advancedDefaultsTitle = "Advanced Image Defaults"
}

struct DesktopImageInspector: View {
    let viewModel: RuntimeViewModel
    let cancelSelectedJob: @MainActor () -> Void
    let redoSelectedJob: @MainActor () -> Void
    let prepareReiterateFromSelectedJob: @MainActor () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            MelixSectionCard("Selected Job") {
                if let job = viewModel.selectedImageJob {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(job.jobID)
                            .font(.headline)
                        Text("\(job.operation) • \(job.modelID)")
                            .foregroundStyle(.secondary)
                        Text("\(job.progress.stage) • \(String(format: "%.0f%%", job.progress.pct * 100))")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(.secondary)
                        Text(viewModel.selectedImageJobTimeoutText)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        HStack {
                            Button("Redo", action: redoSelectedJob)
                                .disabled(viewModel.canRedoSelectedImageJob == false)
                            Button("Reiterate", action: prepareReiterateFromSelectedJob)
                                .disabled(viewModel.canPrepareReiterateFromSelectedImageJob == false)
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

            MelixSectionCard("Artifacts") {
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
            return job.error.code == "deadline_exceeded" ? "timed_out" : "failed"
        default:
            return "unknown"
        }
    }

    private var backgroundStyle: Color {
        if isSelected {
            return MelixDesignTokens.accent.opacity(MelixDesignTokens.AccentOpacity.selected)
        }
        switch job.state {
        case .imageJobCompleted:
            return MelixDesignTokens.StatusColor.success.opacity(MelixDesignTokens.StateOpacity.background)
        case .imageJobFailed:
            return MelixDesignTokens.StatusColor.error.opacity(MelixDesignTokens.StateOpacity.background)
        case .imageJobRunning:
            return MelixDesignTokens.StatusColor.warning.opacity(MelixDesignTokens.StateOpacity.background)
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
