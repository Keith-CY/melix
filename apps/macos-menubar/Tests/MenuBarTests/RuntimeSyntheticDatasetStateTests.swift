import AppKit
import SwiftUI
import Testing

@testable import AppMain

@Suite("Runtime Synthetic Dataset State", .serialized)
struct RuntimeSyntheticDatasetStateTests {
    @Test("synthetic dataset identity output provider model form validates required inputs")
    @MainActor
    func syntheticDatasetIdentityOutputProviderModelFormValidatesRequiredInputs() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())

        #expect(viewModel.syntheticDatasetNumRecordsDraft == "100")
        #expect(viewModel.syntheticDatasetOutputKindDraft == "training")
        #expect(viewModel.syntheticDatasetOutputFormatDraft == "prompt_completion")
        #expect(viewModel.syntheticDatasetProviderNameDraft == "melix")
        #expect(viewModel.syntheticDatasetProviderTypeDraft == "openai")
        #expect(viewModel.syntheticDatasetModelAliasDraft == "generator")
        #expect(viewModel.syntheticDatasetBaseFormCanContinue == false)
        #expect(viewModel.syntheticDatasetBaseFormValidationMessages.map(\.field) == [
            "Dataset ID",
            "Dataset Name",
            "Output Directory",
            "Provider Endpoint",
            "Model",
        ])

        viewModel.updateSyntheticDatasetIDDraft(" synthetic.chat.v1 ")
        viewModel.updateSyntheticDatasetNameDraft(" Synthetic Chat ")
        viewModel.updateSyntheticDatasetNumRecordsDraft("0")
        viewModel.updateSyntheticDatasetOutputKindDraft(" training ")
        viewModel.updateSyntheticDatasetOutputFormatDraft(" prompt_completion ")
        viewModel.updateSyntheticDatasetOutputDirDraft(" /tmp/synthetic-chat ")
        viewModel.updateSyntheticDatasetProviderEndpointDraft(" http://127.0.0.1:11434/v1 ")
        viewModel.updateSyntheticDatasetProviderNameDraft(" melix ")
        viewModel.updateSyntheticDatasetProviderTypeDraft(" openai ")
        viewModel.updateSyntheticDatasetModelAliasDraft(" generator ")
        viewModel.updateSyntheticDatasetModelDraft(" melix-dev-text ")

        #expect(viewModel.normalizedSyntheticDatasetID == "synthetic.chat.v1")
        #expect(viewModel.normalizedSyntheticDatasetName == "Synthetic Chat")
        #expect(viewModel.normalizedSyntheticDatasetOutputDir == "/tmp/synthetic-chat")
        #expect(viewModel.normalizedSyntheticDatasetProviderEndpoint == "http://127.0.0.1:11434/v1")
        #expect(viewModel.normalizedSyntheticDatasetProviderName == "melix")
        #expect(viewModel.normalizedSyntheticDatasetProviderType == "openai")
        #expect(viewModel.normalizedSyntheticDatasetModelAlias == "generator")
        #expect(viewModel.normalizedSyntheticDatasetModel == "melix-dev-text")
        #expect(viewModel.syntheticDatasetBaseFormCanContinue == false)
        #expect(viewModel.syntheticDatasetBaseFormValidationMessages == [
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Records",
                message: "Enter a positive record count."
            ),
        ])

        viewModel.updateSyntheticDatasetNumRecordsDraft("12")

        #expect(viewModel.syntheticDatasetBaseFormCanContinue)
        #expect(viewModel.syntheticDatasetBaseFormValidationMessages.isEmpty)

        viewModel.updateSyntheticDatasetOutputKindDraft(" ")
        viewModel.updateSyntheticDatasetOutputFormatDraft(" ")
        viewModel.updateSyntheticDatasetProviderNameDraft(" ")
        viewModel.updateSyntheticDatasetProviderTypeDraft(" ")
        viewModel.updateSyntheticDatasetModelAliasDraft(" ")

        #expect(viewModel.syntheticDatasetBaseFormValidationMessages == [
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Output Kind",
                message: "Enter an output kind."
            ),
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Output Format",
                message: "Enter an output format."
            ),
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Provider Name",
                message: "Enter a provider name."
            ),
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Provider Type",
                message: "Enter a provider type."
            ),
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Model Alias",
                message: "Enter a model alias."
            ),
        ])
    }

    @Test("synthetic dataset column editor builds NAME TYPE payload arguments")
    @MainActor
    func syntheticDatasetColumnEditorBuildsNameTypePayloadArguments() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())

        #expect(viewModel.syntheticDatasetColumnTypeDraft == "llm_text")
        #expect(viewModel.syntheticDatasetColumnDraftCanAdd == false)
        #expect(viewModel.syntheticDatasetColumnDraftValidationMessages.map(\.field) == [
            "Column Name",
            "Column Payload",
        ])

        viewModel.updateSyntheticDatasetColumnNameDraft(" prompt ")
        viewModel.updateSyntheticDatasetColumnTypeDraft(" llm_text ")
        viewModel.updateSyntheticDatasetColumnPayloadDraft(#"{"prompt":"write a concise answer"}"#)
        viewModel.addSyntheticDatasetColumnDraft()

        #expect(viewModel.syntheticDatasetColumns == [
            RuntimeSyntheticDatasetColumnState(
                name: "prompt",
                type: "llm_text",
                payload: #"{"prompt":"write a concise answer"}"#
            ),
        ])
        #expect(viewModel.syntheticDatasetColumnCommandArguments == [
            #"prompt:llm_text:{"prompt":"write a concise answer"}"#,
        ])
        #expect(viewModel.syntheticDatasetColumnNameDraft.isEmpty)
        #expect(viewModel.syntheticDatasetColumnPayloadDraft.isEmpty)
        #expect(viewModel.syntheticDatasetColumnTypeDraft == "llm_text")
        #expect(viewModel.syntheticDatasetColumnEditorErrorMessage.isEmpty)

        viewModel.updateSyntheticDatasetColumnNameDraft("broken")
        viewModel.updateSyntheticDatasetColumnPayloadDraft(#"{"prompt":"unterminated""#)

        #expect(viewModel.syntheticDatasetColumnDraftCanAdd == false)
        #expect(viewModel.syntheticDatasetColumnDraftValidationMessages == [
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Column Payload",
                message: "Column payload must be a JSON object or file path."
            ),
        ])

        viewModel.updateSyntheticDatasetColumnTypeDraft(" ")
        #expect(viewModel.syntheticDatasetColumnDraftValidationMessages == [
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Column Type",
                message: "Enter a column type."
            ),
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Column Payload",
                message: "Column payload must be a JSON object or file path."
            ),
        ])

        viewModel.addSyntheticDatasetColumnDraft()
        #expect(viewModel.syntheticDatasetColumnEditorErrorMessage.contains("Column Type: Enter a column type."))
        #expect(viewModel.syntheticDatasetColumnCommandArguments == [
            #"prompt:llm_text:{"prompt":"write a concise answer"}"#,
        ])

        viewModel.updateSyntheticDatasetColumnTypeDraft("llm_text")
        viewModel.updateSyntheticDatasetColumnPayloadDraft("/tmp/source-seeds.jsonl")
        viewModel.addSyntheticDatasetColumnDraft()

        #expect(viewModel.syntheticDatasetColumnCommandArguments == [
            #"prompt:llm_text:{"prompt":"write a concise answer"}"#,
            "broken:llm_text:/tmp/source-seeds.jsonl",
        ])

        viewModel.removeSyntheticDatasetColumn(id: "prompt:llm_text:{\"prompt\":\"write a concise answer\"}")

        #expect(viewModel.syntheticDatasetColumnCommandArguments == [
            "broken:llm_text:/tmp/source-seeds.jsonl",
        ])
    }

    @Test("synthetic dataset tool section renders identity output provider model form")
    @MainActor
    func syntheticDatasetToolSectionRendersIdentityOutputProviderModelForm() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectToolSection(.syntheticDatasets)
        viewModel.updateSyntheticDatasetIDDraft("synthetic.chat.v1")
        viewModel.updateSyntheticDatasetNameDraft("Synthetic Chat")
        viewModel.updateSyntheticDatasetOutputDirDraft("/tmp/synthetic-chat")
        viewModel.updateSyntheticDatasetProviderEndpointDraft("http://127.0.0.1:11434/v1")
        viewModel.updateSyntheticDatasetModelDraft("melix-dev-text")

        let section = DesktopSyntheticDatasetToolSectionView(viewModel: viewModel)
        let hosted = hostSyntheticDatasetView(section)
        let summary = section.accessibilitySummary

        #expect(hosted.subviews.isEmpty == false)
        #expect(summary.contains("Synthetic Dataset Studio"))
        #expect(summary.contains("Dataset Identity"))
        #expect(summary.contains("Dataset ID"))
        #expect(summary.contains("Output Directory"))
        #expect(summary.contains("Provider Endpoint"))
        #expect(summary.contains("Model Alias"))
        #expect(summary.contains("melix-dev-text"))
        #expect(summary.contains("Ready to configure columns before preview or create."))

        let workspace = hostSyntheticDatasetView(DesktopWorkspaceShellView(viewModel: viewModel))
        #expect(workspace.subviews.isEmpty == false)
        #expect(viewModel.selectedToolSection == .syntheticDatasets)

        let emptySection = DesktopSyntheticDatasetToolSectionView(
            viewModel: RuntimeViewModel(client: FakeControlPlaneXPCClient())
        )
        let emptyHosted = hostSyntheticDatasetView(emptySection)
        let emptySummary = emptySection.accessibilitySummary

        #expect(emptyHosted.subviews.isEmpty == false)
        #expect(emptySummary.contains("Dataset ID"))
        #expect(emptySummary.contains("Enter a dataset ID."))
        #expect(emptySummary.contains("Provider Endpoint"))
        #expect(emptySummary.contains("Enter a model."))
    }

    @Test("synthetic dataset tool section renders and drives column editor")
    @MainActor
    func syntheticDatasetToolSectionRendersAndDrivesColumnEditor() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.updateSyntheticDatasetColumnNameDraft("response")
        viewModel.updateSyntheticDatasetColumnTypeDraft("llm_text")
        viewModel.updateSyntheticDatasetColumnPayloadDraft(#"{"prompt":"answer"}"#)

        let section = DesktopSyntheticDatasetToolSectionView(viewModel: viewModel)
        _ = hostSyntheticDatasetView(section)
        let initialSummary = section.accessibilitySummary

        #expect(initialSummary.contains("Columns"))
        #expect(initialSummary.contains("Column Name"))
        #expect(initialSummary.contains("Column Type"))
        #expect(initialSummary.contains("JSON or Path"))
        #expect(initialSummary.contains("Add Column"))

        section.addColumnAction()

        let addedSection = DesktopSyntheticDatasetToolSectionView(viewModel: viewModel)
        _ = hostSyntheticDatasetView(addedSection)
        let addedSummary = addedSection.accessibilitySummary

        #expect(addedSummary.contains(#"response:llm_text:{"prompt":"answer"}"#))
        #expect(addedSummary.contains("Remove Column"))

        addedSection.removeColumn(id: #"response:llm_text:{"prompt":"answer"}"#)

        let removedSummary = DesktopSyntheticDatasetToolSectionView(viewModel: viewModel).accessibilitySummary
        #expect(removedSummary.contains("No synthetic columns configured."))

        let invalidViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        let invalidSection = DesktopSyntheticDatasetToolSectionView(viewModel: invalidViewModel)
        invalidSection.addColumnAction()
        let invalidRenderedSection = DesktopSyntheticDatasetToolSectionView(viewModel: invalidViewModel)
        _ = hostSyntheticDatasetView(invalidRenderedSection)
        let invalidSummary = invalidRenderedSection.accessibilitySummary

        #expect(invalidSummary.contains("Column Name: Enter a column name."))
        #expect(invalidSummary.contains("Column Payload: Enter JSON or a source path."))
    }

    @Test("synthetic dataset navigation has icon category and session persistence mapping")
    func syntheticDatasetNavigationHasIconCategoryAndSessionPersistenceMapping() throws {
        #expect(DesktopToolSection.syntheticDatasets.symbolName == "sparkles.rectangle.stack")
        #expect(DesktopToolCategory.build.sections.contains(.syntheticDatasets))

        let state = OperatorSessionState(
            selectedSurface: .tools,
            selectedToolSection: .syntheticDatasets,
            selectedServerSessionID: "",
            serverSessions: []
        )
        let encoded = try JSONEncoder().encode(state)
        let decoded = try JSONDecoder().decode(OperatorSessionState.self, from: encoded)
        let payload = try #require(JSONSerialization.jsonObject(with: encoded) as? [String: Any])

        #expect(decoded.selectedToolSection == .syntheticDatasets)
        #expect(payload["selected_tool_section"] as? String == "syntheticDatasets")
    }
}

@MainActor
private func hostSyntheticDatasetView<Content: View>(_ rootView: Content) -> NSView {
    let hostingView = NSHostingView(rootView: rootView)
    hostingView.frame = CGRect(origin: .zero, size: CGSize(width: 960, height: 720))
    hostingView.layoutSubtreeIfNeeded()
    return hostingView
}
