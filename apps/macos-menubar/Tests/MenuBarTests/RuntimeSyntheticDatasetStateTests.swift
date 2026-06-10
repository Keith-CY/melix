import AppKit
import SwiftUI
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Runtime Synthetic Dataset State", .serialized)
struct RuntimeSyntheticDatasetStateTests {
    @Test("synthetic dataset preview decoder maps manifest rows and artifact paths")
    func syntheticDatasetPreviewDecoderMapsManifestRowsAndArtifactPaths() throws {
        let preview = try RuntimeSyntheticDatasetPayloadDecoder.decodePreview(Self.syntheticPreviewJSON)

        #expect(preview.schemaVersion == "melix.synthetic_dataset_preview.v1")
        #expect(preview.datasetID == "synthetic.chat.v1")
        #expect(preview.datasetName == "Synthetic Chat")
        #expect(preview.outputKind == "training")
        #expect(preview.outputFormat == "prompt_completion")
        #expect(preview.sampleCount == 2)
        #expect(preview.previewCount == 3)
        #expect(preview.previewRows.count == 2)
        #expect(preview.previewRows.first?.fields.map(\.name) == ["completion", "prompt"])
        #expect(preview.previewRows.first?.fields.first?.id == "completion")
        #expect(preview.previewRows.first?.summaryText.contains("prompt=What is Melix?") == true)
        #expect(preview.artifactRows.map(\.name) == [
            "artifact_path",
            "config_path",
            "generated_jsonl_path",
            "manifest_path",
        ])
    }

    @Test("synthetic dataset create decoder maps package manifest and artifact paths")
    func syntheticDatasetCreateDecoderMapsPackageManifestAndArtifactPaths() throws {
        let result = try RuntimeSyntheticDatasetPayloadDecoder.decodeCreate(Self.syntheticCreateJSON)

        #expect(result.schemaVersion == "melix.training_dataset_package.v1")
        #expect(result.datasetID == "synthetic.chat.v1")
        #expect(result.datasetName == "Synthetic Chat")
        #expect(result.outputKind == "training")
        #expect(result.outputFormat == "prompt_completion")
        #expect(result.rowCount == 4)
        #expect(result.sampleCount == 4)
        #expect(result.previewOnly == false)
        #expect(result.summaryText == "synthetic.chat.v1 package contains 4 rows.")
        #expect(result.manifestRows.map(\.name) == [
            "build_ready",
            "dataset_id",
            "dataset_name",
            "operation",
            "output_format",
            "output_kind",
            "preview_only",
            "row_count",
            "sample_count",
            "schema_version",
            "validation_ratio",
        ])
        #expect(result.manifestRows.first { $0.name == "build_ready" }?.valueText == "true")
        #expect(result.manifestRows.first { $0.name == "validation_ratio" }?.valueText == "0.2")
        #expect(result.artifactRows.map(\.name) == [
            "artifact_path",
            "config_path",
            "generated_jsonl_path",
            "manifest_path",
            "output_path",
            "package.manifest_path",
            "package.samples_path",
            "validation_path",
        ])

        #expect(throws: DecodingError.self) {
            _ = try RuntimeSyntheticDatasetPayloadDecoder.decodeCreate("[]")
        }
    }

    @Test("synthetic dataset preview decoder maps fallback value shapes and rejects non objects")
    func syntheticDatasetPreviewDecoderMapsFallbackValueShapesAndRejectsNonObjects() throws {
        let preview = try RuntimeSyntheticDatasetPayloadDecoder.decodePreview(Self.syntheticPreviewVariantJSON)

        #expect(preview.datasetID == "123")
        #expect(preview.datasetName == "456")
        #expect(preview.outputKind == "true")
        #expect(preview.outputFormat == "1.5")
        #expect(preview.rowCount == 7)
        #expect(preview.sampleCount == 2)
        #expect(preview.previewOnly)
        #expect(preview.artifactRows.map(\.name) == ["output_path"])

        let row = try #require(preview.previewRows.first)
        #expect(row.fields.first { $0.name == "nullable" }?.valueText == "null")
        #expect(row.fields.first { $0.name == "flag" }?.valueText == "true")
        #expect(row.fields.first { $0.name == "count" }?.valueText == "2")
        #expect(row.fields.first { $0.name == "score" }?.valueText == "1.5")
        #expect(row.fields.first { $0.name == "nested" }?.valueText == #"{"a":1,"b":2}"#)
        #expect(row.fields.first { $0.name == "items" }?.valueText == #"["b","a"]"#)

        let emptyPreview = try RuntimeSyntheticDatasetPayloadDecoder.decodePreview(Self.syntheticEmptyPreviewJSON)
        #expect(emptyPreview.sampleCount == 0)
        #expect(emptyPreview.previewOnly == false)
        #expect(emptyPreview.previewRows.isEmpty)

        #expect(throws: DecodingError.self) {
            _ = try RuntimeSyntheticDatasetPayloadDecoder.decodePreview("[]")
        }
    }

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

    @Test("synthetic dataset generation controls validate seed ratio resume and telemetry")
    @MainActor
    func syntheticDatasetGenerationControlsValidateSeedRatioResumeAndTelemetry() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())

        #expect(viewModel.syntheticDatasetSeedSourceKindDraft.isEmpty)
        #expect(viewModel.syntheticDatasetSeedSourcePathDraft.isEmpty)
        #expect(viewModel.syntheticDatasetValidationRatioDraft.isEmpty)
        #expect(viewModel.syntheticDatasetResumeModeDraft == "never")
        #expect(viewModel.syntheticDatasetDataDesignerTelemetryEnabled == false)
        #expect(viewModel.syntheticDatasetGenerationControlValidationMessages.isEmpty)
        #expect(viewModel.syntheticDatasetGenerationControlCommandArguments == ["--resume", "never"])

        viewModel.updateSyntheticDatasetSeedSourceKindDraft(" local_jsonl ")
        #expect(viewModel.syntheticDatasetGenerationControlValidationMessages == [
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Seed Source Path",
                message: "Enter a seed source path."
            ),
        ])

        viewModel.updateSyntheticDatasetSeedSourcePathDraft(" /tmp/seeds.jsonl ")
        viewModel.updateSyntheticDatasetValidationRatioDraft(" 0.25 ")
        viewModel.updateSyntheticDatasetResumeModeDraft(" if_possible ")
        viewModel.updateSyntheticDatasetDataDesignerTelemetryEnabled(true)

        #expect(viewModel.normalizedSyntheticDatasetSeedSourceKind == "local_jsonl")
        #expect(viewModel.normalizedSyntheticDatasetSeedSourcePath == "/tmp/seeds.jsonl")
        #expect(viewModel.normalizedSyntheticDatasetValidationRatio == "0.25")
        #expect(viewModel.normalizedSyntheticDatasetResumeMode == "if_possible")
        #expect(viewModel.syntheticDatasetGenerationControlValidationMessages.isEmpty)
        #expect(viewModel.syntheticDatasetGenerationControlCommandArguments == [
            "--seed-source-kind",
            "local_jsonl",
            "--seed-source-path",
            "/tmp/seeds.jsonl",
            "--validation-ratio",
            "0.25",
            "--resume",
            "if_possible",
            "--enable-datadesigner-telemetry",
        ])

        viewModel.updateSyntheticDatasetSeedSourceKindDraft("")
        viewModel.updateSyntheticDatasetValidationRatioDraft("1.0")
        viewModel.updateSyntheticDatasetResumeModeDraft("sometimes")

        #expect(viewModel.syntheticDatasetGenerationControlValidationMessages == [
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Seed Source Kind",
                message: "Choose a seed source kind."
            ),
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Validation Ratio",
                message: "Enter a decimal from 0.0 up to but not including 1.0."
            ),
            RuntimeSyntheticDatasetValidationMessageState(
                field: "Resume",
                message: "Choose never, if_possible, or always."
            ),
        ])
    }

    @Test("runtime view model previews synthetic dataset through cli runner")
    @MainActor
    func runtimeViewModelPreviewsSyntheticDatasetThroughCLIRunner() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        let expectedCommand = Self.syntheticPreviewCommand()
        await runner.configureOutput(Self.syntheticPreviewJSON, for: expectedCommand)
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        configureValidSyntheticDatasetPreviewRequest(viewModel)

        #expect(viewModel.syntheticDatasetCanPreview)
        await viewModel.previewSyntheticDataset()

        #expect(viewModel.syntheticDatasetPreview?.datasetID == "synthetic.chat.v1")
        #expect(viewModel.syntheticDatasetPreview?.previewRows.count == 2)
        #expect(viewModel.syntheticDatasetPreviewMessage == "Previewed synthetic.chat.v1 with 2 rows.")
        #expect(viewModel.syntheticDatasetPreviewErrorMessage.isEmpty)
        #expect(viewModel.syntheticDatasetPreviewInProgress == false)
        #expect(await runner.snapshotRecordedCommands() == [expectedCommand])

        let invalidViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        await invalidViewModel.previewSyntheticDataset()
        #expect(invalidViewModel.syntheticDatasetPreviewErrorMessage == "Resolve synthetic dataset validation errors before preview.")

        let noRunnerViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        configureValidSyntheticDatasetPreviewRequest(noRunnerViewModel)
        await noRunnerViewModel.previewSyntheticDataset()
        #expect(noRunnerViewModel.syntheticDatasetPreviewErrorMessage == "Synthetic Dataset CLI runner is unavailable.")

        let malformedRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await malformedRunner.configureOutput("not-json\n", for: expectedCommand)
        let malformedViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: malformedRunner)
        configureValidSyntheticDatasetPreviewRequest(malformedViewModel)
        await malformedViewModel.previewSyntheticDataset()
        #expect(malformedViewModel.syntheticDatasetPreviewErrorMessage == "dataset.synthetic.preview returned malformed JSON.")
    }

    @Test("runtime view model creates synthetic dataset through cli runner")
    @MainActor
    func runtimeViewModelCreatesSyntheticDatasetThroughCLIRunner() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        let expectedCommand = Self.syntheticCreateCommand()
        await runner.configureOutput(Self.syntheticCreateJSON, for: expectedCommand)
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        configureValidSyntheticDatasetPreviewRequest(viewModel)

        #expect(viewModel.syntheticDatasetCanCreate)
        await viewModel.createSyntheticDataset()

        #expect(viewModel.syntheticDatasetCreateResult?.datasetID == "synthetic.chat.v1")
        #expect(viewModel.syntheticDatasetCreateResult?.manifestRows.count == 11)
        #expect(viewModel.syntheticDatasetCreateResult?.artifactRows.count == 8)
        #expect(viewModel.syntheticDatasetCreateMessage == "Created synthetic.chat.v1 package with 4 rows.")
        #expect(viewModel.syntheticDatasetCreateErrorMessage.isEmpty)
        #expect(viewModel.syntheticDatasetCreateInProgress == false)
        #expect(await runner.snapshotRecordedCommands() == [expectedCommand])

        let invalidViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        await invalidViewModel.createSyntheticDataset()
        #expect(invalidViewModel.syntheticDatasetCreateErrorMessage == "Resolve synthetic dataset validation errors before create.")

        let noRunnerViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        configureValidSyntheticDatasetPreviewRequest(noRunnerViewModel)
        await noRunnerViewModel.createSyntheticDataset()
        #expect(noRunnerViewModel.syntheticDatasetCreateErrorMessage == "Synthetic Dataset CLI runner is unavailable.")

        let malformedRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await malformedRunner.configureOutput("not-json\n", for: expectedCommand)
        let malformedViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: malformedRunner)
        configureValidSyntheticDatasetPreviewRequest(malformedViewModel)
        await malformedViewModel.createSyntheticDataset()
        #expect(malformedViewModel.syntheticDatasetCreateErrorMessage == "dataset.synthetic.create returned malformed JSON.")
    }

    @Test("synthetic dataset workflow runner rejects mismatched modes before dispatch")
    func syntheticDatasetWorkflowRunnerRejectsMismatchedModesBeforeDispatch() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        let createOptions: DatasetSyntheticOptions
        let previewOptions: DatasetSyntheticOptions
        if case .datasetSynthetic(let options) = Self.syntheticCreateCommand() {
            createOptions = options
        } else {
            Issue.record("Expected synthetic create command options.")
            return
        }
        if case .datasetSynthetic(let options) = Self.syntheticPreviewCommand() {
            previewOptions = options
        } else {
            Issue.record("Expected synthetic preview command options.")
            return
        }

        do {
            _ = try await runner.previewSyntheticDataset(options: createOptions)
            Issue.record("Expected preview to reject create-mode options.")
        } catch let error as MelixCLIWorkflowError {
            switch error {
            case .invalidOption(let commandID, let surface, let field, let expected, let actual):
                #expect(commandID == "dataset.synthetic.create")
                #expect(surface == .subprocess)
                #expect(field == "mode")
                #expect(expected == "preview")
                #expect(actual == "create")
            default:
                Issue.record("Expected invalidOption, got \(error)")
            }
        }

        do {
            _ = try await runner.createSyntheticDataset(options: previewOptions)
            Issue.record("Expected create to reject preview-mode options.")
        } catch let error as MelixCLIWorkflowError {
            switch error {
            case .invalidOption(let commandID, let surface, let field, let expected, let actual):
                #expect(commandID == "dataset.synthetic.preview")
                #expect(surface == .subprocess)
                #expect(field == "mode")
                #expect(expected == "create")
                #expect(actual == "preview")
            default:
                Issue.record("Expected invalidOption, got \(error)")
            }
        }

        #expect(await runner.snapshotRecordedCommands().isEmpty)
    }

    @Test("synthetic dataset error states classify dependency provider and invalid column failures")
    @MainActor
    func syntheticDatasetErrorStatesClassifyDependencyProviderAndInvalidColumnFailures() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureFailure(
            .processFailed(
                commandID: "dataset.synthetic.preview",
                surface: .subprocess,
                exitCode: 2,
                stderr: "DataDesigner extra is not installed. Install melix[datadesigner]."
            ),
            for: Self.syntheticPreviewCommand()
        )
        await runner.configureFailure(
            .processFailed(
                commandID: "dataset.synthetic.create",
                surface: .subprocess,
                exitCode: 503,
                stderr: "Provider request failed: HTTP 503 upstream unavailable."
            ),
            for: Self.syntheticCreateCommand()
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        configureValidSyntheticDatasetPreviewRequest(viewModel)

        await viewModel.previewSyntheticDataset()
        await viewModel.createSyntheticDataset()
        viewModel.updateSyntheticDatasetColumnNameDraft("broken")
        viewModel.updateSyntheticDatasetColumnPayloadDraft(#"{"prompt":"unterminated""#)

        let errorStates = viewModel.syntheticDatasetErrorStates
        let titles = errorStates.map(\.title)

        #expect(titles == [
            "Invalid Column Payload",
            "Missing DataDesigner Extra",
            "Provider Failure",
        ])

        let invalidColumn = try #require(errorStates.first { $0.title == "Invalid Column Payload" })
        #expect(invalidColumn.source == "Column Editor")
        #expect(invalidColumn.recoveryHint == "Use a JSON object such as {\"prompt\":\"...\"} or a readable source path.")

        let missingExtra = try #require(errorStates.first { $0.title == "Missing DataDesigner Extra" })
        #expect(missingExtra.source == "Preview")
        #expect(missingExtra.detail.contains("DataDesigner extra is not installed."))
        #expect(missingExtra.recoveryHint == "Install the DataDesigner extra, then retry preview or create.")

        let providerFailure = try #require(errorStates.first { $0.title == "Provider Failure" })
        #expect(providerFailure.source == "Create")
        #expect(providerFailure.detail.contains("HTTP 503"))
        #expect(providerFailure.recoveryHint == "Check provider endpoint, model, credentials, and availability before retrying.")

        let invalidPayloadRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await invalidPayloadRunner.configureFailure(
            .processFailed(
                commandID: "dataset.synthetic.create",
                surface: .subprocess,
                exitCode: 2,
                stderr: "Column payload must be a JSON object or file path."
            ),
            for: Self.syntheticCreateCommand()
        )
        let invalidPayloadViewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            cliWorkflowRunner: invalidPayloadRunner
        )
        configureValidSyntheticDatasetPreviewRequest(invalidPayloadViewModel)
        await invalidPayloadViewModel.createSyntheticDataset()

        let cliInvalidPayload = try #require(
            invalidPayloadViewModel.syntheticDatasetErrorStates.first { $0.title == "Invalid Column Payload" }
        )
        #expect(cliInvalidPayload.source == "Create")
        #expect(cliInvalidPayload.detail.contains("Column payload"))
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

    @Test("synthetic dataset tool section renders generation controls")
    @MainActor
    func syntheticDatasetToolSectionRendersGenerationControls() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.updateSyntheticDatasetSeedSourceKindDraft("training_package")
        viewModel.updateSyntheticDatasetSeedSourcePathDraft("/tmp/training-package")
        viewModel.updateSyntheticDatasetValidationRatioDraft("0.2")
        viewModel.updateSyntheticDatasetResumeModeDraft("always")
        viewModel.updateSyntheticDatasetDataDesignerTelemetryEnabled(true)

        let section = DesktopSyntheticDatasetToolSectionView(viewModel: viewModel)
        let hosted = hostSyntheticDatasetView(section)
        let summary = section.accessibilitySummary

        #expect(hosted.subviews.isEmpty == false)
        #expect(summary.contains("Generation Controls"))
        #expect(summary.contains("Seed Source Kind"))
        #expect(summary.contains("Seed Source Path"))
        #expect(summary.contains("Validation Ratio"))
        #expect(summary.contains("Resume"))
        #expect(summary.contains("DataDesigner Telemetry"))
        #expect(summary.contains("training_package"))
        #expect(summary.contains("/tmp/training-package"))
        #expect(summary.contains("0.2"))
        #expect(summary.contains("always"))
        #expect(summary.contains("--enable-datadesigner-telemetry"))

        let invalidViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        invalidViewModel.updateSyntheticDatasetSeedSourcePathDraft("/tmp/seeds.jsonl")
        invalidViewModel.updateSyntheticDatasetValidationRatioDraft("1.0")
        invalidViewModel.updateSyntheticDatasetResumeModeDraft("sometimes")
        let invalidSection = DesktopSyntheticDatasetToolSectionView(viewModel: invalidViewModel)
        _ = hostSyntheticDatasetView(invalidSection)
        let invalidSummary = invalidSection.accessibilitySummary

        #expect(invalidSummary.contains("Seed Source Kind Choose a seed source kind."))
        #expect(invalidSummary.contains("Validation Ratio Enter a decimal from 0.0 up to but not including 1.0."))
        #expect(invalidSummary.contains("Resume Choose never, if_possible, or always."))
    }

    @Test("synthetic dataset tool section renders and drives preview rows")
    @MainActor
    func syntheticDatasetToolSectionRendersAndDrivesPreviewRows() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(Self.syntheticPreviewJSON, for: Self.syntheticPreviewCommand())
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        configureValidSyntheticDatasetPreviewRequest(viewModel)

        let section = DesktopSyntheticDatasetToolSectionView(viewModel: viewModel)
        _ = hostSyntheticDatasetView(section)
        section.previewDatasetAction()

        try await waitForSyntheticDatasetCondition("synthetic preview action completes") {
            viewModel.syntheticDatasetPreview?.previewRows.count == 2
        }

        let renderedSection = DesktopSyntheticDatasetToolSectionView(viewModel: viewModel)
        let hosted = hostSyntheticDatasetView(renderedSection)
        let summary = renderedSection.accessibilitySummary

        #expect(hosted.subviews.isEmpty == false)
        #expect(summary.contains("Preview"))
        #expect(summary.contains("Preview Dataset"))
        #expect(summary.contains("Previewed synthetic.chat.v1 with 2 rows."))
        #expect(summary.contains("What is Melix?"))
        #expect(summary.contains("Local-first runtime."))
        #expect(summary.contains("/tmp/synthetic-chat/data_designer/generated.jsonl"))

        let emptyPreviewViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        emptyPreviewViewModel.applySyntheticDatasetPreview(
            try RuntimeSyntheticDatasetPayloadDecoder.decodePreview(Self.syntheticEmptyPreviewJSON)
        )
        let emptySummary = DesktopSyntheticDatasetToolSectionView(viewModel: emptyPreviewViewModel).accessibilitySummary
        #expect(emptySummary.contains("Preview returned no rows."))

        let errorViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        configureValidSyntheticDatasetPreviewRequest(errorViewModel)
        await errorViewModel.previewSyntheticDataset()
        let errorSection = DesktopSyntheticDatasetToolSectionView(viewModel: errorViewModel)
        _ = hostSyntheticDatasetView(errorSection)
        #expect(errorSection.accessibilitySummary.contains("Synthetic Dataset CLI runner is unavailable."))
    }

    @Test("synthetic dataset tool section renders and drives create package result")
    @MainActor
    func syntheticDatasetToolSectionRendersAndDrivesCreatePackageResult() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(Self.syntheticCreateJSON, for: Self.syntheticCreateCommand())
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        configureValidSyntheticDatasetPreviewRequest(viewModel)

        let section = DesktopSyntheticDatasetToolSectionView(viewModel: viewModel)
        _ = hostSyntheticDatasetView(section)
        section.createDatasetAction()

        try await waitForSyntheticDatasetCondition("synthetic create action completes") {
            viewModel.syntheticDatasetCreateResult?.artifactRows.count == 8
        }

        let renderedSection = DesktopSyntheticDatasetToolSectionView(viewModel: viewModel)
        let hosted = hostSyntheticDatasetView(renderedSection)
        let summary = renderedSection.accessibilitySummary

        #expect(hosted.subviews.isEmpty == false)
        #expect(summary.contains("Create Package"))
        #expect(summary.contains("Create Dataset"))
        #expect(summary.contains("Created synthetic.chat.v1 package with 4 rows."))
        #expect(summary.contains("Package Manifest"))
        #expect(summary.contains("generate_synthetic_dataset"))
        #expect(summary.contains("package.manifest_path"))
        #expect(summary.contains("/tmp/synthetic-chat/package/manifest.json"))
        #expect(summary.contains("validation_path"))
        #expect(summary.contains("/tmp/synthetic-chat/validation.jsonl"))

        let emptyResultViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        emptyResultViewModel.applySyntheticDatasetCreateResult(
            try RuntimeSyntheticDatasetPayloadDecoder.decodeCreate(Self.syntheticEmptyCreateJSON)
        )
        let emptySummary = DesktopSyntheticDatasetToolSectionView(viewModel: emptyResultViewModel).accessibilitySummary
        #expect(emptySummary.contains("Create result did not include manifest fields."))
        #expect(emptySummary.contains("Create result did not include artifact paths."))
    }

    @Test("synthetic dataset tool section renders classified error states")
    @MainActor
    func syntheticDatasetToolSectionRendersClassifiedErrorStates() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureFailure(
            .processFailed(
                commandID: "dataset.synthetic.preview",
                surface: .subprocess,
                exitCode: 2,
                stderr: "DataDesigner extra is not installed. Install melix[datadesigner]."
            ),
            for: Self.syntheticPreviewCommand()
        )
        await runner.configureFailure(
            .processFailed(
                commandID: "dataset.synthetic.create",
                surface: .subprocess,
                exitCode: 503,
                stderr: "Provider request failed: HTTP 503 upstream unavailable."
            ),
            for: Self.syntheticCreateCommand()
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        configureValidSyntheticDatasetPreviewRequest(viewModel)

        await viewModel.previewSyntheticDataset()
        await viewModel.createSyntheticDataset()
        viewModel.updateSyntheticDatasetColumnNameDraft("broken")
        viewModel.updateSyntheticDatasetColumnPayloadDraft(#"{"prompt":"unterminated""#)

        let section = DesktopSyntheticDatasetToolSectionView(viewModel: viewModel)
        let hosted = hostSyntheticDatasetView(section)
        let summary = section.accessibilitySummary

        #expect(hosted.subviews.isEmpty == false)
        #expect(summary.contains("Error States"))
        #expect(summary.contains("Invalid Column Payload"))
        #expect(summary.contains("Missing DataDesigner Extra"))
        #expect(summary.contains("Provider Failure"))
        #expect(summary.contains("Install the DataDesigner extra, then retry preview or create."))
        #expect(summary.contains("Check provider endpoint, model, credentials, and availability before retrying."))
    }

    @Test("synthetic dataset navigation has icon category and session persistence mapping")
    func syntheticDatasetNavigationHasIconCategoryAndSessionPersistenceMapping() throws {
        #expect(DesktopToolSection.syntheticDatasets.symbolName == "sparkles.rectangle.stack")
        #expect(DesktopToolCategory.workflows.sections.contains(.syntheticDatasets))
        #expect(DesktopToolCategory.workflows.sections.contains(.jobs) == false)
        #expect(DesktopToolCategory.jobs.sections == [.jobs])

        let state = OperatorSessionState(
            selectedSurface: .tools,
            selectedToolSection: .syntheticDatasets,
            selectedProviderID: "",
            providers: []
        )
        let encoded = try JSONEncoder().encode(state)
        let decoded = try JSONDecoder().decode(OperatorSessionState.self, from: encoded)
        let payload = try #require(JSONSerialization.jsonObject(with: encoded) as? [String: Any])

        #expect(decoded.selectedToolSection == .syntheticDatasets)
        #expect(payload["selected_tool_section"] as? String == "syntheticDatasets")
    }

    private static func syntheticPreviewCommand() -> MelixCLICommand {
        .datasetSynthetic(.init(
            mode: "preview",
            datasetID: "synthetic.chat.v1",
            datasetName: "Synthetic Chat",
            numRecords: 4,
            outputKind: "training",
            outputFormat: "prompt_completion",
            outputDir: "/tmp/synthetic-chat",
            providerEndpoint: "http://127.0.0.1:11434/v1",
            providerName: "melix",
            providerType: "openai",
            modelAlias: "generator",
            model: "melix-dev-text",
            columns: [
                #"prompt:llm_text:{"prompt":"Write a concise answer."}"#,
            ],
            seedSourceKind: "local_jsonl",
            seedSourcePath: "/tmp/seeds.jsonl",
            validationRatio: "0.2",
            resume: "if_possible",
            enableDataDesignerTelemetry: true,
            json: true
        ))
    }

    private static func syntheticCreateCommand() -> MelixCLICommand {
        .datasetSynthetic(.init(
            mode: "create",
            datasetID: "synthetic.chat.v1",
            datasetName: "Synthetic Chat",
            numRecords: 4,
            outputKind: "training",
            outputFormat: "prompt_completion",
            outputDir: "/tmp/synthetic-chat",
            providerEndpoint: "http://127.0.0.1:11434/v1",
            providerName: "melix",
            providerType: "openai",
            modelAlias: "generator",
            model: "melix-dev-text",
            columns: [
                #"prompt:llm_text:{"prompt":"Write a concise answer."}"#,
            ],
            seedSourceKind: "local_jsonl",
            seedSourcePath: "/tmp/seeds.jsonl",
            validationRatio: "0.2",
            resume: "if_possible",
            enableDataDesignerTelemetry: true,
            json: true
        ))
    }

    private static let syntheticPreviewJSON = #"""
    {
      "schema_version": "melix.synthetic_dataset_preview.v1",
      "dataset_id": "synthetic.chat.v1",
      "dataset_name": "Synthetic Chat",
      "output_kind": "training",
      "output_format": "prompt_completion",
      "row_count": 2,
      "sample_count": 2,
      "preview_count": 3,
      "preview_only": true,
      "manifest_path": "/tmp/synthetic-chat/synthetic_dataset.preview.json",
      "preview_samples": [
        {
          "prompt": "What is Melix?",
          "completion": "Local-first runtime."
        },
        {
          "prompt": "Summarize Apple Silicon serving",
          "completion": "Keep memory fit visible before dispatch."
        }
      ],
      "datadesigner": {
        "config_path": "/tmp/synthetic-chat/data_designer/config.json",
        "artifact_path": "/tmp/synthetic-chat/data_designer/artifacts",
        "generated_jsonl_path": "/tmp/synthetic-chat/data_designer/generated.jsonl"
      }
    }
    """#

    private static let syntheticPreviewVariantJSON = #"""
    {
      "schema_version": "melix.synthetic_dataset_preview.v1",
      "dataset_id": 123,
      "dataset_name": 456,
      "output_kind": true,
      "output_format": 1.5,
      "row_count": "7",
      "sample_count": "2",
      "preview_count": "1",
      "preview_only": "yes",
      "output_path": "/tmp/synthetic-chat/data_designer/generated.jsonl",
      "preview_samples": [
        {
          "nullable": null,
          "flag": true,
          "count": 2,
          "score": 1.5,
          "nested": {"b": 2, "a": 1},
          "items": ["b", "a"]
        }
      ]
    }
    """#

    private static let syntheticEmptyPreviewJSON = #"""
    {
      "schema_version": "melix.synthetic_dataset_preview.v1",
      "dataset_id": "synthetic.empty.v1",
      "dataset_name": "Synthetic Empty",
      "output_kind": "training",
      "output_format": "prompt_completion",
      "preview_only": 0,
      "preview_samples": []
    }
    """#

    private static let syntheticCreateJSON = #"""
    {
      "operation": "generate_synthetic_dataset",
      "schema_version": "melix.training_dataset_package.v1",
      "dataset_id": "synthetic.chat.v1",
      "dataset_name": "Synthetic Chat",
      "output_kind": "training",
      "output_format": "prompt_completion",
      "row_count": 4,
      "sample_count": 4,
      "preview_only": false,
      "build_ready": true,
      "validation_ratio": 0.2,
      "manifest_path": "/tmp/synthetic-chat/synthetic_dataset.manifest.json",
      "output_path": "/tmp/synthetic-chat/train.jsonl",
      "validation_path": "/tmp/synthetic-chat/validation.jsonl",
      "package": {
        "manifest_path": "/tmp/synthetic-chat/package/manifest.json",
        "samples_path": "/tmp/synthetic-chat/package/samples.jsonl"
      },
      "datadesigner": {
        "config_path": "/tmp/synthetic-chat/data_designer/config.json",
        "artifact_path": "/tmp/synthetic-chat/data_designer/artifacts",
        "generated_jsonl_path": "/tmp/synthetic-chat/data_designer/generated.jsonl"
      }
    }
    """#

    private static let syntheticEmptyCreateJSON = "{}"
}

@MainActor
private func hostSyntheticDatasetView<Content: View>(_ rootView: Content) -> NSView {
    let hostingView = NSHostingView(rootView: rootView)
    hostingView.frame = CGRect(origin: .zero, size: CGSize(width: 960, height: 720))
    hostingView.layoutSubtreeIfNeeded()
    return hostingView
}

@MainActor
private func configureValidSyntheticDatasetPreviewRequest(_ viewModel: RuntimeViewModel) {
    viewModel.updateSyntheticDatasetIDDraft(" synthetic.chat.v1 ")
    viewModel.updateSyntheticDatasetNameDraft(" Synthetic Chat ")
    viewModel.updateSyntheticDatasetNumRecordsDraft("4")
    viewModel.updateSyntheticDatasetOutputKindDraft("training")
    viewModel.updateSyntheticDatasetOutputFormatDraft("prompt_completion")
    viewModel.updateSyntheticDatasetOutputDirDraft(" /tmp/synthetic-chat ")
    viewModel.updateSyntheticDatasetProviderEndpointDraft(" http://127.0.0.1:11434/v1 ")
    viewModel.updateSyntheticDatasetProviderNameDraft("melix")
    viewModel.updateSyntheticDatasetProviderTypeDraft("openai")
    viewModel.updateSyntheticDatasetModelAliasDraft("generator")
    viewModel.updateSyntheticDatasetModelDraft(" melix-dev-text ")
    viewModel.updateSyntheticDatasetColumnNameDraft("prompt")
    viewModel.updateSyntheticDatasetColumnTypeDraft("llm_text")
    viewModel.updateSyntheticDatasetColumnPayloadDraft(#"{"prompt":"Write a concise answer."}"#)
    viewModel.addSyntheticDatasetColumnDraft()
    viewModel.updateSyntheticDatasetSeedSourceKindDraft("local_jsonl")
    viewModel.updateSyntheticDatasetSeedSourcePathDraft("/tmp/seeds.jsonl")
    viewModel.updateSyntheticDatasetValidationRatioDraft("0.2")
    viewModel.updateSyntheticDatasetResumeModeDraft("if_possible")
    viewModel.updateSyntheticDatasetDataDesignerTelemetryEnabled(true)
}

@MainActor
private func waitForSyntheticDatasetCondition(
    _ description: String,
    timeout: Duration = MenuBarTestEnvironment.bootstrapConditionTimeout,
    condition: @escaping @MainActor () -> Bool
) async throws {
    let start = ContinuousClock.now
    while condition() == false {
        if start.duration(to: .now) > timeout {
            Issue.record("Timed out waiting for \(description)")
            return
        }
        try await Task.sleep(nanoseconds: 10_000_000)
    }
}
