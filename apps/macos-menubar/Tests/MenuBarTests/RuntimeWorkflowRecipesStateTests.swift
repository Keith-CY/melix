import AppKit
import SwiftUI
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Runtime Workflow Recipes State", .serialized)
struct RuntimeWorkflowRecipesStateTests {
    @Test("workflow recipe decoder maps catalog filters and detail rows")
    func workflowRecipeDecoderMapsCatalogFiltersAndDetailRows() throws {
        let catalog = try RuntimeWorkflowRecipesPayloadDecoder.decodeCatalog(Self.catalogJSON)

        #expect(catalog.schemaVersion == "melix.workflow_recipe_catalog.v1")
        #expect(catalog.recipes.map(\.id) == ["import.hf-mlx-model", "dataset.hf-eval"])
        #expect(catalog.availableTaskFilters == ["dataset_import", "eval", "model_import"])
        #expect(catalog.recipes.first?.taskText == "model_import")
        #expect(catalog.recipes.first?.digest == "digest-import")

        let detail = try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(Self.detailJSON)

        #expect(detail.id == "import.hf-mlx-model")
        #expect(detail.description == "Inspect fit, download a Hugging Face model, and rescan managed roots.")
        #expect(detail.inputRows.map(\.name) == ["repo_id", "revision", "model_id"])
        #expect(detail.inputRows.first?.requirementText == "Required")
        #expect(detail.inputRows.first?.uriKind == "hf_model_repo")
        #expect(detail.pipelineSteps.map(\.command) == ["estimate.import", "model.hub.download", "model.roots.rescan"])
        #expect(detail.outputRows.first?.name == "managed_model_path")
        #expect(detail.preflightRows.contains { $0.name == "pipeline_dry_run" && $0.valueText == "true" })
    }

    @Test("workflow recipe decoder maps uri inspect candidates and ambiguity results")
    func workflowRecipeDecoderMapsURIInspectCandidatesAndAmbiguityResults() throws {
        let inspection = try RuntimeWorkflowRecipesPayloadDecoder.decodeURIInspection(Self.uriInspectionJSON)

        #expect(inspection.schemaVersion == "melix.uri_inspection.v1")
        #expect(inspection.originalURI == "org/repo")
        #expect(inspection.normalizedLocator == "org/repo")
        #expect(inspection.candidateCount == 2)
        #expect(inspection.ambiguityCount == 1)
        #expect(inspection.summaryText == "2 candidates, 1 ambiguous")
        #expect(inspection.candidates.map(\.kind) == ["hf_model_repo", "hf_dataset_repo"])
        #expect(inspection.candidates.first?.repoID == "org/repo")
        #expect(inspection.candidates.first?.revision == "main")
        #expect(inspection.candidates.first?.confidenceText == "62%")
        #expect(inspection.candidates.first?.reasonText == "bare org/repo locator; prefer hf://model or hf://dataset for disambiguation")
        #expect(inspection.candidates.first?.generatedCommandText == "model hub download --repo-id org/repo")
        #expect(inspection.candidates.last?.taskKind == "dataset_import")
        #expect(inspection.metrics.first?.name == "uri.ambiguity_count")

        let emptyInspection = try RuntimeWorkflowRecipesPayloadDecoder.decodeURIInspection(Self.emptyURIInspectionJSON)
        #expect(emptyInspection.candidates.isEmpty)
        #expect(emptyInspection.summaryText == "0 candidates, 0 ambiguous")

        let stringlyInspection = try RuntimeWorkflowRecipesPayloadDecoder.decodeURIInspection(Self.stringlyURIInspectionJSON)
        #expect(stringlyInspection.candidateCount == 1)
        #expect(stringlyInspection.ambiguityCount == 0)
        #expect(stringlyInspection.candidates.first?.confidenceText == "62.5%")

        let fallbackInspection = try RuntimeWorkflowRecipesPayloadDecoder.decodeURIInspection(Self.fallbackURIInspectionJSON)
        #expect(fallbackInspection.candidateCount == 1)
        #expect(fallbackInspection.ambiguityCount == 0)
        #expect(fallbackInspection.candidates.first?.confidenceText == "0%")
    }

    @Test("workflow recipe decoder maps init preview provenance from inspected uri")
    func workflowRecipeDecoderMapsInitPreviewProvenanceFromInspectedURI() throws {
        let preview = try RuntimeWorkflowRecipesPayloadDecoder.decodeInitPreview(Self.initPreviewJSON)

        #expect(preview.recipe.id == "import.hf-mlx-model")
        #expect(preview.recipe.title == "Import an MLX-compatible Hugging Face model")
        #expect(preview.source == "generated_from_uri")
        #expect(preview.sourceURIDigest == "sha256:source-uri-digest")
        #expect(preview.inspection?.summaryText == "1 candidate, 0 ambiguous")
        #expect(preview.inspection?.candidates.first?.normalizedLocator == "hf://model/org/repo@main")
        #expect(preview.provenanceRows.map(\.name) == ["source", "source_uri_digest"])
        #expect(preview.recipe.inputRows.map(\.name).contains("repo_id"))
        #expect(preview.recipe.pipelineSteps.map(\.command).contains("model.hub.download"))

        let previewWithoutInspection = try RuntimeWorkflowRecipesPayloadDecoder.decodeInitPreview(
            Self.initPreviewWithoutInspectionJSON
        )
        #expect(previewWithoutInspection.inspection == nil)
        #expect(previewWithoutInspection.provenanceRows.map(\.name) == ["source", "source_uri_digest"])
    }

    @Test("workflow recipe decoder maps planned pipeline json and dry-run receipts")
    func workflowRecipeDecoderMapsPlannedPipelineJSONAndDryRunReceipts() throws {
        let plan = try RuntimeWorkflowRecipesPayloadDecoder.decodePlan(Self.planJSON)

        #expect(plan.schemaVersion == "melix.workflow_recipe_plan.v1")
        #expect(plan.recipeID == "import.hf-mlx-model")
        #expect(plan.recipeVersion == "1")
        #expect(plan.recipeDigest == "digest-import")
        #expect(plan.pipelineSchemaVersion == "melix.pipeline.v1")
        #expect(plan.pipelineSteps.map(\.command) == ["estimate.import", "model.hub.download", "model.roots.rescan"])
        #expect(plan.pipelineJSONText.contains(#""schema_version" : "melix.pipeline.v1""#))
        #expect(plan.artifactRows.map(\.kind) == ["pipeline"])
        #expect(plan.artifactRows.first?.path == "/tmp/planned.pipeline.json")
        #expect(plan.metrics.map(\.name).contains("recipe.plan_ms"))
        #expect(plan.summaryText == "import.hf-mlx-model v1 planned 3 pipeline steps.")
    }

    @Test("workflow recipe decoder maps apply dry-run receipts")
    func workflowRecipeDecoderMapsApplyDryRunReceipts() throws {
        let result = try RuntimeWorkflowRecipesPayloadDecoder.decodeApplyResult(Self.applyJSON)

        #expect(result.schemaVersion == "melix.pipeline.run.v1")
        #expect(result.status == "planned")
        #expect(result.name == "import.hf-mlx-model")
        #expect(result.traceID == "trace-123")
        #expect(result.receiptDir == "/tmp/recipe-run/receipts")
        #expect(result.summaryPath == "/tmp/recipe-run/receipts/run.json")
        #expect(result.recipeRows.map(\.name).contains("run_root"))
        #expect(result.stepRows.map(\.status) == ["planned", "planned", "planned"])
        #expect(result.stepRows.first?.receiptPath == "/tmp/recipe-run/receipts/steps/001-estimate_import.json")
        #expect(result.stepRows.first?.artifactPaths == ["/tmp/import-fit.json"])
        #expect(result.metrics.map(\.name).contains("recipe.apply_start_ms"))
        #expect(result.summaryText == "planned 3 steps for import.hf-mlx-model.")
    }

    @Test("runtime view model refreshes workflow recipe catalog and detail through CLI runner")
    @MainActor
    func runtimeViewModelRefreshesWorkflowRecipeCatalogAndDetailThroughCLIRunner() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(Self.catalogJSON, for: .recipesList(.init(task: "", json: true)))
        await runner.configureOutput(Self.filteredCatalogJSON, for: .recipesList(.init(task: "model_import", json: true)))
        await runner.configureOutput(Self.detailJSON, for: .recipesShow(.init(recipeID: "import.hf-mlx-model", json: true)))

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateWorkflowRecipeTaskFilter("model_import")

        await viewModel.refreshWorkflowRecipeCatalog()
        #expect(viewModel.workflowRecipeCatalog.recipes.map(\.id) == ["import.hf-mlx-model"])
        #expect(viewModel.workflowRecipeCatalogMessage == "Loaded 1 workflow recipe.")
        #expect(viewModel.workflowRecipeCatalogErrorMessage.isEmpty)

        await viewModel.selectWorkflowRecipe(recipeID: "import.hf-mlx-model")
        #expect(viewModel.selectedWorkflowRecipeID == "import.hf-mlx-model")
        #expect(viewModel.selectedWorkflowRecipeDetail?.pipelineSteps.map(\.command) == [
            "estimate.import",
            "model.hub.download",
            "model.roots.rescan",
        ])

        let recordedCommands = await runner.snapshotRecordedCommands()
        #expect(recordedCommands == [
            .recipesList(.init(task: "model_import", json: true)),
            .recipesShow(.init(recipeID: "import.hf-mlx-model", json: true)),
        ])
    }

    @Test("runtime view model inspects workflow recipe uri through cli runner")
    @MainActor
    func runtimeViewModelInspectsWorkflowRecipeURIThroughCLIRunner() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(Self.uriInspectionJSON, for: .uriInspect(.init(uri: "org/repo", json: true)))

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateWorkflowRecipeURIInspectDraft(" org/repo ")

        await viewModel.inspectWorkflowRecipeURI()

        #expect(viewModel.workflowRecipeURIInspection?.candidateCount == 2)
        #expect(viewModel.workflowRecipeURIInspection?.ambiguityCount == 1)
        #expect(viewModel.workflowRecipeURIInspection?.candidates.first?.kind == "hf_model_repo")
        #expect(viewModel.workflowRecipeURIInspectMessage == "Inspected org/repo: 2 candidates, 1 ambiguous.")
        #expect(viewModel.workflowRecipeURIInspectErrorMessage.isEmpty)
        #expect(await runner.snapshotRecordedCommands() == [.uriInspect(.init(uri: "org/repo", json: true))])

        let noRunnerViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        noRunnerViewModel.updateWorkflowRecipeURIInspectDraft("")
        await noRunnerViewModel.inspectWorkflowRecipeURI()
        #expect(noRunnerViewModel.workflowRecipeURIInspectErrorMessage == "Enter a URI before inspecting.")

        noRunnerViewModel.updateWorkflowRecipeURIInspectDraft("org/repo")
        await noRunnerViewModel.inspectWorkflowRecipeURI()
        #expect(noRunnerViewModel.workflowRecipeURIInspectErrorMessage == "Workflow recipe CLI runner is unavailable.")
    }

    @Test("runtime view model previews recipe init from inspected uri through cli runner")
    @MainActor
    func runtimeViewModelPreviewsRecipeInitFromInspectedURIThroughCLIRunner() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(
            Self.initPreviewJSON,
            for: .recipesInit(.init(sourceURI: "hf://model/org/repo", task: "model_import", json: true))
        )

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.applyWorkflowRecipeURIInspection(
            try RuntimeWorkflowRecipesPayloadDecoder.decodeURIInspection(Self.singleCandidateURIInspectionJSON)
        )

        #expect(viewModel.workflowRecipeInitTaskDraft == "model_import")

        await viewModel.previewWorkflowRecipeInitFromInspectedURI()

        #expect(viewModel.workflowRecipeInitPreview?.recipe.id == "import.hf-mlx-model")
        #expect(viewModel.workflowRecipeInitPreview?.sourceURIDigest == "sha256:source-uri-digest")
        #expect(viewModel.workflowRecipeInitPreviewMessage == "Previewed import.hf-mlx-model from hf://model/org/repo.")
        #expect(viewModel.workflowRecipeInitPreviewErrorMessage.isEmpty)
        #expect(await runner.snapshotRecordedCommands() == [
            .recipesInit(.init(sourceURI: "hf://model/org/repo", task: "model_import", json: true)),
        ])
    }

    @Test("runtime view model plans workflow recipe through cli runner")
    @MainActor
    func runtimeViewModelPlansWorkflowRecipeThroughCLIRunner() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(
            Self.planJSON,
            for: .recipesPlan(.init(
                recipeID: "import.hf-mlx-model",
                version: "1",
                values: ["repo_id": "org/repo"],
                outputPath: "/tmp/planned.pipeline.json",
                json: true
            ))
        )

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.applyWorkflowRecipeDetail(try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(Self.detailJSON))
        viewModel.updateWorkflowRecipeSetKeyDraft("repo_id")
        viewModel.updateWorkflowRecipeSetValueDraft("org/repo")
        viewModel.addWorkflowRecipeSetDraft()
        viewModel.updateWorkflowRecipePlanOutputPathDraft(" /tmp/planned.pipeline.json ")

        await viewModel.planWorkflowRecipe()

        #expect(viewModel.workflowRecipePlan?.recipeID == "import.hf-mlx-model")
        #expect(viewModel.workflowRecipePlan?.pipelineSteps.count == 3)
        #expect(viewModel.workflowRecipePlan?.artifactRows.first?.path == "/tmp/planned.pipeline.json")
        #expect(viewModel.workflowRecipePlanMessage == "Planned import.hf-mlx-model with 3 pipeline steps.")
        #expect(viewModel.workflowRecipePlanErrorMessage.isEmpty)
        #expect(await runner.snapshotRecordedCommands() == [
            .recipesPlan(.init(
                recipeID: "import.hf-mlx-model",
                version: "1",
                values: ["repo_id": "org/repo"],
                outputPath: "/tmp/planned.pipeline.json",
                json: true
            )),
        ])
    }

    @Test("runtime view model applies workflow recipe through existing cli runner")
    @MainActor
    func runtimeViewModelAppliesWorkflowRecipeThroughExistingCLIRunner() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(
            Self.applyJSON,
            for: .recipesApply(.init(
                recipeID: "import.hf-mlx-model",
                version: "1",
                values: ["repo_id": "org/repo"],
                dryRun: true,
                resume: true,
                fromStepID: "download_model",
                json: true
            ))
        )

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.applyWorkflowRecipeDetail(try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(Self.detailJSON))
        viewModel.updateWorkflowRecipeSetKeyDraft("repo_id")
        viewModel.updateWorkflowRecipeSetValueDraft("org/repo")
        viewModel.addWorkflowRecipeSetDraft()
        viewModel.updateWorkflowRecipeApplyDryRun(true)
        viewModel.updateWorkflowRecipeApplyResume(true)
        viewModel.updateWorkflowRecipeApplyFromStepDraft(" download_model ")

        await viewModel.applyWorkflowRecipe()

        #expect(viewModel.workflowRecipeApplyResult?.status == "planned")
        #expect(viewModel.workflowRecipeApplyResult?.stepRows.count == 3)
        #expect(viewModel.workflowRecipeApplyFromStepDraft == "download_model")
        #expect(viewModel.workflowRecipeApplyMessage == "Applied import.hf-mlx-model as dry run: planned 3 steps.")
        #expect(viewModel.workflowRecipeApplyErrorMessage.isEmpty)
        #expect(await runner.snapshotRecordedCommands() == [
            .recipesApply(.init(
                recipeID: "import.hf-mlx-model",
                version: "1",
                values: ["repo_id": "org/repo"],
                dryRun: true,
                resume: true,
                fromStepID: "download_model",
                json: true
            )),
        ])
    }

    @Test("runtime view model edits workflow recipe set variables")
    @MainActor
    func runtimeViewModelEditsWorkflowRecipeSetVariables() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())

        viewModel.updateWorkflowRecipeSetKeyDraft(" repo_id ")
        viewModel.updateWorkflowRecipeSetValueDraft(" org/repo ")
        viewModel.addWorkflowRecipeSetDraft()

        #expect(viewModel.workflowRecipeSetValues == ["repo_id": "org/repo"])
        #expect(viewModel.workflowRecipeSetRows.map(\.argumentText) == ["--set repo_id=org/repo"])
        #expect(viewModel.workflowRecipeSetArgumentSummaryText == "--set repo_id=org/repo")
        #expect(viewModel.workflowRecipeSetEditorMessage == "Added --set repo_id=org/repo.")
        #expect(viewModel.workflowRecipeSetEditorErrorMessage.isEmpty)
        #expect(viewModel.workflowRecipeSetKeyDraft.isEmpty)
        #expect(viewModel.workflowRecipeSetValueDraft.isEmpty)

        viewModel.updateWorkflowRecipeSetKeyDraft("repo_id")
        viewModel.updateWorkflowRecipeSetValueDraft("org/updated")
        viewModel.addWorkflowRecipeSetDraft()
        #expect(viewModel.workflowRecipeSetValues["repo_id"] == "org/updated")
        #expect(viewModel.workflowRecipeSetEditorMessage == "Updated --set repo_id=org/updated.")

        viewModel.updateWorkflowRecipeSetKeyDraft("invalid=key")
        viewModel.updateWorkflowRecipeSetValueDraft("value")
        viewModel.addWorkflowRecipeSetDraft()
        #expect(viewModel.workflowRecipeSetEditorErrorMessage == "Variable key cannot include '='.")

        viewModel.updateWorkflowRecipeSetKeyDraft("")
        viewModel.updateWorkflowRecipeSetValueDraft("value")
        viewModel.addWorkflowRecipeSetDraft()
        #expect(viewModel.workflowRecipeSetEditorErrorMessage == "Enter a variable key before adding a --set value.")

        viewModel.updateWorkflowRecipeSetKeyDraft("bad key")
        viewModel.updateWorkflowRecipeSetValueDraft("value")
        viewModel.addWorkflowRecipeSetDraft()
        #expect(viewModel.workflowRecipeSetEditorErrorMessage == "Variable key cannot contain whitespace.")

        viewModel.removeWorkflowRecipeSetValue(key: " ")
        #expect(viewModel.workflowRecipeSetEditorErrorMessage == "Select a variable before removing it.")

        viewModel.removeWorkflowRecipeSetValue(key: "repo_id")
        #expect(viewModel.workflowRecipeSetRows.isEmpty)
        #expect(viewModel.workflowRecipeSetEditorMessage == "Removed --set repo_id.")

        viewModel.updateWorkflowRecipeSetKeyDraft("revision")
        viewModel.updateWorkflowRecipeSetValueDraft("main")
        viewModel.addWorkflowRecipeSetDraft()
        viewModel.clearWorkflowRecipeSetValues()
        #expect(viewModel.workflowRecipeSetValues.isEmpty)
        #expect(viewModel.workflowRecipeSetEditorMessage == "Cleared recipe variables.")

        viewModel.clearWorkflowRecipeSetValues()
        #expect(viewModel.workflowRecipeSetEditorErrorMessage == "No recipe variables to clear.")
    }

    @Test("workflow recipes section renders catalog filters and selected recipe detail")
    @MainActor
    func workflowRecipesSectionRendersCatalogFiltersAndSelectedRecipeDetail() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.updateWorkflowRecipeTaskFilter("model_import")
        viewModel.applyWorkflowRecipeCatalog(try RuntimeWorkflowRecipesPayloadDecoder.decodeCatalog(Self.catalogJSON))
        viewModel.applyWorkflowRecipeDetail(try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(Self.detailJSON))

        let section = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel)
        let hosted = hostWorkflowRecipeView(section)
        let summary = section.accessibilitySummary

        #expect(hosted.subviews.isEmpty == false)
        #expect(summary.contains("Task filter"))
        #expect(summary.contains("Refresh Catalog"))
        #expect(summary.contains("Import an MLX-compatible Hugging Face model"))
        #expect(summary.contains("repo_id"))
        #expect(summary.contains("estimate.import"))
        #expect(summary.contains("managed_model_path"))
    }

    @Test("workflow recipes section renders uri inspect form and candidate ambiguity results")
    @MainActor
    func workflowRecipesSectionRendersURIInspectFormAndCandidateAmbiguityResults() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.updateWorkflowRecipeURIInspectDraft("org/repo")
        viewModel.applyWorkflowRecipeURIInspection(
            try RuntimeWorkflowRecipesPayloadDecoder.decodeURIInspection(Self.uriInspectionJSON)
        )

        let section = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel)
        let hosted = hostWorkflowRecipeView(section)
        let summary = section.accessibilitySummary

        #expect(hosted.subviews.isEmpty == false)
        #expect(summary.contains("URI to inspect"))
        #expect(summary.contains("Inspect URI"))
        #expect(summary.contains("org/repo"))
        #expect(summary.contains("2 candidates, 1 ambiguous"))
        #expect(summary.contains("hf_model_repo"))
        #expect(summary.contains("hf_dataset_repo"))
        #expect(summary.contains("model hub download --repo-id org/repo"))
        #expect(summary.contains("bare org/repo locator could also identify a Hugging Face dataset"))

        viewModel.applyWorkflowRecipeURIInspection(
            try RuntimeWorkflowRecipesPayloadDecoder.decodeURIInspection(Self.emptyURIInspectionJSON)
        )
        let emptySummary = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel).accessibilitySummary
        #expect(emptySummary.contains("No URI candidates found."))
    }

    @Test("workflow recipes section renders recipe init preview from inspected uri")
    @MainActor
    func workflowRecipesSectionRendersRecipeInitPreviewFromInspectedURI() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.applyWorkflowRecipeURIInspection(
            try RuntimeWorkflowRecipesPayloadDecoder.decodeURIInspection(Self.singleCandidateURIInspectionJSON)
        )
        viewModel.applyWorkflowRecipeInitPreview(
            try RuntimeWorkflowRecipesPayloadDecoder.decodeInitPreview(Self.initPreviewJSON)
        )

        let section = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel)
        let hosted = hostWorkflowRecipeView(section)
        let summary = section.accessibilitySummary

        #expect(hosted.subviews.isEmpty == false)
        #expect(summary.contains("Recipe init task"))
        #expect(summary.contains("Preview Recipe Init"))
        #expect(summary.contains("Recipe Init Preview"))
        #expect(summary.contains("generated_from_uri"))
        #expect(summary.contains("sha256:source-uri-digest"))
        #expect(summary.contains("Import an MLX-compatible Hugging Face model"))
        #expect(summary.contains("model.hub.download"))
    }

    @Test("workflow recipes section renders and drives set variable editor")
    @MainActor
    func workflowRecipesSectionRendersAndDrivesSetVariableEditor() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        let section = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel)
        let hosted = hostWorkflowRecipeView(section)
        let initialSummary = section.accessibilitySummary

        #expect(hosted.subviews.isEmpty == false)
        #expect(initialSummary.contains("Recipe Variables"))
        #expect(initialSummary.contains("Variable key"))
        #expect(initialSummary.contains("Variable value"))
        #expect(initialSummary.contains("Add --set"))
        #expect(initialSummary.contains("No recipe variables configured."))

        viewModel.updateWorkflowRecipeSetKeyDraft("repo_id")
        viewModel.updateWorkflowRecipeSetValueDraft("org/repo")
        section.addRecipeVariableAction()
        _ = hostWorkflowRecipeView(DesktopWorkflowRecipesToolSectionView(viewModel: viewModel))
        let addedSummary = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel).accessibilitySummary
        #expect(viewModel.workflowRecipeSetValues == ["repo_id": "org/repo"])
        #expect(addedSummary.contains("--set repo_id=org/repo"))
        #expect(addedSummary.contains("Added --set repo_id=org/repo."))

        section.applyRecipeVariableDraft(key: "invalid=key", value: "value")
        _ = hostWorkflowRecipeView(DesktopWorkflowRecipesToolSectionView(viewModel: viewModel))
        let errorSummary = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel).accessibilitySummary
        #expect(errorSummary.contains("Variable key cannot include '='."))

        section.applyRecipeVariableDraft(key: "repo_id", value: "org/repo")
        section.removeRecipeVariableAction("repo_id")
        _ = hostWorkflowRecipeView(DesktopWorkflowRecipesToolSectionView(viewModel: viewModel))
        let removedSummary = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel).accessibilitySummary
        #expect(viewModel.workflowRecipeSetValues.isEmpty)
        #expect(removedSummary.contains("Removed --set repo_id."))

        section.applyRecipeVariableDraft(key: "revision", value: "main")
        section.clearRecipeVariablesAction()
        #expect(viewModel.workflowRecipeSetValues.isEmpty)
        #expect(DesktopWorkflowRecipesToolSectionView(viewModel: viewModel).accessibilitySummary.contains(
            "Cleared recipe variables."
        ))
    }

    @Test("workflow recipes section renders and drives planned pipeline summary")
    @MainActor
    func workflowRecipesSectionRendersAndDrivesPlannedPipelineSummary() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(
            Self.planJSON,
            for: .recipesPlan(.init(
                recipeID: "import.hf-mlx-model",
                version: "1",
                values: ["repo_id": "org/repo"],
                outputPath: "/tmp/planned.pipeline.json",
                json: true
            ))
        )

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.applyWorkflowRecipeDetail(try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(Self.detailJSON))
        viewModel.updateWorkflowRecipeSetKeyDraft("repo_id")
        viewModel.updateWorkflowRecipeSetValueDraft("org/repo")
        viewModel.addWorkflowRecipeSetDraft()
        viewModel.updateWorkflowRecipePlanOutputPathDraft("/tmp/planned.pipeline.json")

        let section = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel)
        let hosted = hostWorkflowRecipeView(section)
        let initialSummary = section.accessibilitySummary

        #expect(hosted.subviews.isEmpty == false)
        #expect(initialSummary.contains("Planned Pipeline"))
        #expect(initialSummary.contains("Plan output path"))
        #expect(initialSummary.contains("Plan Recipe"))
        #expect(initialSummary.contains("Plan a selected recipe to inspect pipeline JSON and dry-run receipts."))

        section.planRecipeAction()
        try await waitForWorkflowRecipeCondition("workflow recipe plan action completes") {
            viewModel.workflowRecipePlan?.pipelineSteps.count == 3
        }

        _ = hostWorkflowRecipeView(DesktopWorkflowRecipesToolSectionView(viewModel: viewModel))
        let plannedSummary = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel).accessibilitySummary
        #expect(plannedSummary.contains("Planned import.hf-mlx-model with 3 pipeline steps."))
        #expect(plannedSummary.contains("Pipeline JSON"))
        #expect(plannedSummary.contains("Dry-run Receipts"))
        #expect(plannedSummary.contains("/tmp/planned.pipeline.json"))
        #expect(plannedSummary.contains("model.hub.download"))
        #expect(plannedSummary.contains("recipe.plan_ms"))
        #expect(await runner.snapshotRecordedCommands() == [
            .recipesPlan(.init(
                recipeID: "import.hf-mlx-model",
                version: "1",
                values: ["repo_id": "org/repo"],
                outputPath: "/tmp/planned.pipeline.json",
                json: true
            )),
        ])
    }

    @Test("workflow recipes section renders and drives apply dry-run controls")
    @MainActor
    func workflowRecipesSectionRendersAndDrivesApplyDryRunControls() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(
            Self.applyJSON,
            for: .recipesApply(.init(
                recipeID: "import.hf-mlx-model",
                version: "1",
                values: ["repo_id": "org/repo"],
                dryRun: true,
                resume: true,
                fromStepID: "download_model",
                json: true
            ))
        )

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.applyWorkflowRecipeDetail(try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(Self.detailJSON))
        viewModel.updateWorkflowRecipeSetKeyDraft("repo_id")
        viewModel.updateWorkflowRecipeSetValueDraft("org/repo")
        viewModel.addWorkflowRecipeSetDraft()
        viewModel.updateWorkflowRecipeApplyResume(true)
        viewModel.updateWorkflowRecipeApplyFromStepDraft("download_model")

        let section = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel)
        let hosted = hostWorkflowRecipeView(section)
        let initialSummary = section.accessibilitySummary

        #expect(hosted.subviews.isEmpty == false)
        #expect(initialSummary.contains("Recipe Apply"))
        #expect(initialSummary.contains("Dry Run"))
        #expect(initialSummary.contains("Resume"))
        #expect(initialSummary.contains("From step"))
        #expect(initialSummary.contains("Apply Recipe"))
        #expect(initialSummary.contains("Apply a selected recipe through the existing pipeline runner."))

        section.applyRecipeAction()
        try await waitForWorkflowRecipeCondition("workflow recipe apply action completes") {
            viewModel.workflowRecipeApplyResult?.stepRows.count == 3
        }

        _ = hostWorkflowRecipeView(DesktopWorkflowRecipesToolSectionView(viewModel: viewModel))
        let appliedSummary = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel).accessibilitySummary
        #expect(appliedSummary.contains("Applied import.hf-mlx-model as dry run: planned 3 steps."))
        #expect(appliedSummary.contains("Recipe Apply Result"))
        #expect(appliedSummary.contains("Receipt Directory"))
        #expect(appliedSummary.contains("download_model"))
        #expect(appliedSummary.contains("planned"))
        #expect(appliedSummary.contains("/tmp/recipe-run/receipts"))
        #expect(await runner.snapshotRecordedCommands() == [
            .recipesApply(.init(
                recipeID: "import.hf-mlx-model",
                version: "1",
                values: ["repo_id": "org/repo"],
                dryRun: true,
                resume: true,
                fromStepID: "download_model",
                json: true
            )),
        ])
    }

    @Test("workflow recipes section buttons drive filter refresh and clear actions")
    @MainActor
    func workflowRecipesSectionButtonsDriveFilterRefreshAndClearActions() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(Self.filteredCatalogJSON, for: .recipesList(.init(task: "model_import", json: true)))
        await runner.configureOutput(Self.detailJSON, for: .recipesShow(.init(recipeID: "import.hf-mlx-model", json: true)))

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.applyWorkflowRecipeCatalog(try RuntimeWorkflowRecipesPayloadDecoder.decodeCatalog(Self.catalogJSON))
        viewModel.updateWorkflowRecipeTaskFilter("model_import")

        let section = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel)
        let hosted = hostWorkflowRecipeView(section)
        let buttons = renderedWorkflowRecipeButtons(in: hosted)

        #expect(buttons.count >= 4)
        section.clearTaskFilter()
        #expect(viewModel.workflowRecipeTaskFilterDraft.isEmpty)

        section.applyTaskFilter("model_import")
        #expect(viewModel.workflowRecipeTaskFilterDraft == "model_import")

        section.refreshCatalogAction()
        try await waitForWorkflowRecipeCondition("workflow recipe catalog refresh action completes") {
            viewModel.workflowRecipeCatalogMessage == "Loaded 1 workflow recipe."
        }

        section.selectRecipeAction("import.hf-mlx-model")
        try await waitForWorkflowRecipeCondition("workflow recipe selection action completes") {
            viewModel.selectedWorkflowRecipeDetail?.id == "import.hf-mlx-model"
        }

        let recordedCommands = await runner.snapshotRecordedCommands()
        #expect(recordedCommands.contains(.recipesList(.init(task: "model_import", json: true))))
        #expect(recordedCommands.contains(.recipesShow(.init(recipeID: "import.hf-mlx-model", json: true))))
    }

    @Test("workflow recipes section drives uri inspect action")
    @MainActor
    func workflowRecipesSectionDrivesURIInspectAction() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(Self.uriInspectionJSON, for: .uriInspect(.init(uri: "org/repo", json: true)))

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.updateWorkflowRecipeURIInspectDraft("org/repo")

        let section = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel)
        let hosted = hostWorkflowRecipeView(section)

        #expect(hosted.subviews.isEmpty == false)
        #expect(section.accessibilitySummary.contains("Inspect URI"))

        section.inspectURIAction()
        try await waitForWorkflowRecipeCondition("workflow recipe uri inspect action completes") {
            viewModel.workflowRecipeURIInspection?.candidateCount == 2
        }

        #expect(viewModel.workflowRecipeURIInspectMessage == "Inspected org/repo: 2 candidates, 1 ambiguous.")
        #expect(await runner.snapshotRecordedCommands() == [.uriInspect(.init(uri: "org/repo", json: true))])
    }

    @Test("workflow recipes section drives recipe init preview action")
    @MainActor
    func workflowRecipesSectionDrivesRecipeInitPreviewAction() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput(
            Self.initPreviewJSON,
            for: .recipesInit(.init(sourceURI: "hf://model/org/repo", task: "model_import", json: true))
        )

        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.applyWorkflowRecipeURIInspection(
            try RuntimeWorkflowRecipesPayloadDecoder.decodeURIInspection(Self.singleCandidateURIInspectionJSON)
        )

        let section = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel)
        _ = hostWorkflowRecipeView(section)

        section.previewRecipeInitAction()
        try await waitForWorkflowRecipeCondition("workflow recipe init preview action completes") {
            viewModel.workflowRecipeInitPreview?.recipe.id == "import.hf-mlx-model"
        }

        #expect(viewModel.workflowRecipeInitPreviewMessage == "Previewed import.hf-mlx-model from hf://model/org/repo.")
        #expect(DesktopWorkflowRecipesToolSectionView(viewModel: viewModel).accessibilitySummary.contains(
            "Previewed import.hf-mlx-model from hf://model/org/repo."
        ))
        #expect(await runner.snapshotRecordedCommands() == [
            .recipesInit(.init(sourceURI: "hf://model/org/repo", task: "model_import", json: true)),
        ])
    }

    @Test("workflow recipes empty and error states are visible")
    @MainActor
    func workflowRecipesEmptyAndErrorStatesAreVisible() async throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.applyWorkflowRecipeCatalog(.empty)
        await viewModel.refreshWorkflowRecipeCatalog()

        let section = DesktopWorkflowRecipesToolSectionView(viewModel: viewModel)
        _ = hostWorkflowRecipeView(section)
        let summary = section.accessibilitySummary

        #expect(viewModel.workflowRecipeCatalogErrorMessage == "Workflow recipe CLI runner is unavailable.")
        #expect(summary.contains("No workflow recipes match this filter."))
        #expect(summary.contains("Select a recipe to inspect its inputs, preflight, pipeline, and outputs."))
        #expect(summary.contains("Workflow recipe CLI runner is unavailable."))
        #expect(summary.contains("Inspect a URI to see candidate workflow inputs."))
    }

    @Test("runtime view model handles workflow recipe errors and cached selection")
    @MainActor
    func runtimeViewModelHandlesWorkflowRecipeErrorsAndCachedSelection() async throws {
        let cachedViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        cachedViewModel.applyWorkflowRecipeCatalog(try RuntimeWorkflowRecipesPayloadDecoder.decodeCatalog(Self.catalogJSON))
        cachedViewModel.applyWorkflowRecipeDetail(try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(Self.detailJSON))
        await cachedViewModel.selectWorkflowRecipe(recipeID: "import.hf-mlx-model")
        #expect(cachedViewModel.selectedWorkflowRecipeDetail?.id == "import.hf-mlx-model")

        await cachedViewModel.selectWorkflowRecipe(recipeID: "   ")
        #expect(cachedViewModel.workflowRecipeCatalogErrorMessage == "Select a workflow recipe before loading detail.")

        let listFailureRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await listFailureRunner.configureFailure(
            .processFailed(commandID: "recipes.list", surface: .subprocess, exitCode: 2, stderr: "list failed"),
            for: .recipesList(.init(task: "", json: true))
        )
        let listFailureViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: listFailureRunner)
        await listFailureViewModel.refreshWorkflowRecipeCatalog()
        #expect(listFailureViewModel.workflowRecipeCatalogErrorMessage.contains("list failed"))

        let detailFailureRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await detailFailureRunner.configureFailure(
            .processFailed(commandID: "recipes.show", surface: .subprocess, exitCode: 3, stderr: "detail failed"),
            for: .recipesShow(.init(recipeID: "missing.recipe", json: true))
        )
        let detailFailureViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: detailFailureRunner)
        await detailFailureViewModel.selectWorkflowRecipe(recipeID: "missing.recipe")
        #expect(detailFailureViewModel.workflowRecipeCatalogErrorMessage.contains("detail failed"))

        let noRunnerViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await noRunnerViewModel.selectWorkflowRecipe(recipeID: "import.hf-mlx-model")
        #expect(noRunnerViewModel.workflowRecipeCatalogErrorMessage == "Workflow recipe CLI runner is unavailable.")

        let uriFailureRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await uriFailureRunner.configureFailure(
            .processFailed(commandID: "uri.inspect", surface: .subprocess, exitCode: 4, stderr: "inspect failed"),
            for: .uriInspect(.init(uri: "org/repo", json: true))
        )
        let uriFailureViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: uriFailureRunner)
        uriFailureViewModel.updateWorkflowRecipeURIInspectDraft("org/repo")
        await uriFailureViewModel.inspectWorkflowRecipeURI()
        #expect(uriFailureViewModel.workflowRecipeURIInspectErrorMessage.contains("inspect failed"))

        let failureSection = DesktopWorkflowRecipesToolSectionView(viewModel: uriFailureViewModel)
        _ = hostWorkflowRecipeView(failureSection)
        #expect(failureSection.accessibilitySummary.contains("inspect failed"))

        let initNoSourceViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await initNoSourceViewModel.previewWorkflowRecipeInitFromInspectedURI()
        #expect(
            initNoSourceViewModel.workflowRecipeInitPreviewErrorMessage
                == "Inspect or enter a URI before previewing recipe init."
        )

        let initMissingTaskRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        let initMissingTaskViewModel = RuntimeViewModel(
            client: FakeControlPlaneXPCClient(),
            cliWorkflowRunner: initMissingTaskRunner
        )
        initMissingTaskViewModel.updateWorkflowRecipeURIInspectDraft("hf://model/org/repo")
        initMissingTaskViewModel.updateWorkflowRecipeInitTaskDraft("  ")
        await initMissingTaskViewModel.previewWorkflowRecipeInitFromInspectedURI()
        #expect(initMissingTaskViewModel.workflowRecipeInitPreviewErrorMessage == "Enter a recipe init task before previewing.")

        let initNoRunnerViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        initNoRunnerViewModel.updateWorkflowRecipeURIInspectDraft("hf://model/org/repo")
        initNoRunnerViewModel.updateWorkflowRecipeInitTaskDraft("model_import")
        await initNoRunnerViewModel.previewWorkflowRecipeInitFromInspectedURI()
        #expect(initNoRunnerViewModel.workflowRecipeInitPreviewErrorMessage == "Workflow recipe CLI runner is unavailable.")

        let initFailureRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await initFailureRunner.configureFailure(
            .processFailed(commandID: "recipes.init", surface: .subprocess, exitCode: 5, stderr: "init failed"),
            for: .recipesInit(.init(sourceURI: "hf://model/org/repo", task: "model_import", json: true))
        )
        let initFailureViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: initFailureRunner)
        initFailureViewModel.applyWorkflowRecipeURIInspection(
            try RuntimeWorkflowRecipesPayloadDecoder.decodeURIInspection(Self.singleCandidateURIInspectionJSON)
        )
        await initFailureViewModel.previewWorkflowRecipeInitFromInspectedURI()
        #expect(initFailureViewModel.workflowRecipeInitPreviewErrorMessage.contains("init failed"))

        let initFailureSection = DesktopWorkflowRecipesToolSectionView(viewModel: initFailureViewModel)
        _ = hostWorkflowRecipeView(initFailureSection)
        #expect(initFailureSection.accessibilitySummary.contains("init failed"))

        let planNoSelectionViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await planNoSelectionViewModel.planWorkflowRecipe()
        #expect(planNoSelectionViewModel.workflowRecipePlanErrorMessage == "Select a workflow recipe before planning.")

        let planNoRunnerViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        planNoRunnerViewModel.applyWorkflowRecipeDetail(try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(Self.detailJSON))
        await planNoRunnerViewModel.planWorkflowRecipe()
        #expect(planNoRunnerViewModel.workflowRecipePlanErrorMessage == "Workflow recipe CLI runner is unavailable.")

        let planFailureRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await planFailureRunner.configureFailure(
            .processFailed(commandID: "recipes.plan", surface: .subprocess, exitCode: 6, stderr: "plan failed"),
            for: .recipesPlan(.init(recipeID: "import.hf-mlx-model", version: "1", json: true))
        )
        let planFailureViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: planFailureRunner)
        planFailureViewModel.applyWorkflowRecipeDetail(try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(Self.detailJSON))
        await planFailureViewModel.planWorkflowRecipe()
        #expect(planFailureViewModel.workflowRecipePlanErrorMessage.contains("plan failed"))

        let planFailureSection = DesktopWorkflowRecipesToolSectionView(viewModel: planFailureViewModel)
        _ = hostWorkflowRecipeView(planFailureSection)
        #expect(planFailureSection.accessibilitySummary.contains("plan failed"))

        let applyNoSelectionViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await applyNoSelectionViewModel.applyWorkflowRecipe()
        #expect(applyNoSelectionViewModel.workflowRecipeApplyErrorMessage == "Select a workflow recipe before applying.")

        let applyNoRunnerViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        applyNoRunnerViewModel.applyWorkflowRecipeDetail(try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(Self.detailJSON))
        await applyNoRunnerViewModel.applyWorkflowRecipe()
        #expect(applyNoRunnerViewModel.workflowRecipeApplyErrorMessage == "Workflow recipe CLI runner is unavailable.")

        let applyFailureRunner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await applyFailureRunner.configureFailure(
            .processFailed(commandID: "recipes.apply", surface: .subprocess, exitCode: 7, stderr: "apply failed"),
            for: .recipesApply(.init(recipeID: "import.hf-mlx-model", version: "1", dryRun: true, json: true))
        )
        let applyFailureViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: applyFailureRunner)
        applyFailureViewModel.applyWorkflowRecipeDetail(try RuntimeWorkflowRecipesPayloadDecoder.decodeDetail(Self.detailJSON))
        await applyFailureViewModel.applyWorkflowRecipe()
        #expect(applyFailureViewModel.workflowRecipeApplyErrorMessage.contains("apply failed"))

        let applyFailureSection = DesktopWorkflowRecipesToolSectionView(viewModel: applyFailureViewModel)
        _ = hostWorkflowRecipeView(applyFailureSection)
        #expect(applyFailureSection.accessibilitySummary.contains("apply failed"))
    }

    @Test("workflow recipe cli bridge maps malformed json to workflow errors")
    func workflowRecipeCLIBridgeMapsMalformedJSONToWorkflowErrors() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput("not-json\n", for: .recipesList(.init(task: "", json: true)))
        await runner.configureOutput("not-json\n", for: .recipesShow(.init(recipeID: "import.hf-mlx-model", json: true)))
        await runner.configureOutput("not-json\n", for: .uriInspect(.init(uri: "org/repo", json: true)))
        await runner.configureOutput(
            "not-json\n",
            for: .recipesInit(.init(sourceURI: "hf://model/org/repo", task: "model_import", json: true))
        )
        await runner.configureOutput(
            "not-json\n",
            for: .recipesPlan(.init(recipeID: "import.hf-mlx-model", version: "1", json: true))
        )
        await runner.configureOutput(
            "not-json\n",
            for: .recipesApply(.init(recipeID: "import.hf-mlx-model", version: "1", dryRun: true, json: true))
        )

        do {
            _ = try await runner.listWorkflowRecipes(task: "")
            Issue.record("Expected malformed catalog JSON to fail.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error.failureKind == .invalidJSON)
        }

        do {
            _ = try await runner.showWorkflowRecipe(recipeID: "import.hf-mlx-model")
            Issue.record("Expected malformed detail JSON to fail.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error.failureKind == .invalidJSON)
        }

        do {
            _ = try await runner.inspectWorkflowRecipeURI(uri: "org/repo")
            Issue.record("Expected malformed URI inspection JSON to fail.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error.failureKind == .invalidJSON)
        }

        do {
            _ = try await runner.initWorkflowRecipeFromURI(sourceURI: "hf://model/org/repo", task: "model_import")
            Issue.record("Expected malformed recipe init preview JSON to fail.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error.failureKind == .invalidJSON)
        }

        do {
            _ = try await runner.planWorkflowRecipe(recipeID: "import.hf-mlx-model", version: "1")
            Issue.record("Expected malformed recipe plan JSON to fail.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error.failureKind == .invalidJSON)
        }

        do {
            _ = try await runner.applyWorkflowRecipe(recipeID: "import.hf-mlx-model", version: "1", dryRun: true)
            Issue.record("Expected malformed recipe apply JSON to fail.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error.failureKind == .invalidJSON)
        }
    }

    @Test("workflow recipes workspace shell mounts through tools navigation")
    @MainActor
    func workflowRecipesWorkspaceShellMountsThroughToolsNavigation() throws {
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        viewModel.selectToolSection(.workflowRecipes)
        viewModel.applyWorkflowRecipeCatalog(try RuntimeWorkflowRecipesPayloadDecoder.decodeCatalog(Self.catalogJSON))

        let hosted = hostWorkflowRecipeView(DesktopWorkspaceShellView(viewModel: viewModel))

        #expect(hosted.subviews.isEmpty == false)
        #expect(viewModel.selectedSurface == .tools)
        #expect(viewModel.selectedToolSection == .workflowRecipes)
    }

    @Test("workflow recipes navigation has icon and session persistence mapping")
    func workflowRecipesNavigationHasIconAndSessionPersistenceMapping() throws {
        #expect(DesktopToolSection.workflowRecipes.symbolName == "list.bullet.clipboard")

        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let state = OperatorSessionState(
            selectedSurface: .tools,
            selectedToolSection: .workflowRecipes,
            selectedServerSessionID: "",
            serverSessions: []
        )
        let decodedState = try JSONDecoder().decode(OperatorSessionState.self, from: encoder.encode(state))
        #expect(decodedState.selectedToolSection == .workflowRecipes)

        let temporaryRoot = FileManager.default.temporaryDirectory
            .appendingPathComponent("melix-menubar-workflow-recipes-store-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: temporaryRoot, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: temporaryRoot) }

        let melixHome = MelixHome(environment: ["MELIX_HOME": temporaryRoot.path])
        let appStore = OperatorSessionStore(melixHome: melixHome)
        try appStore.save(state)

        let restoredState = try #require(try appStore.load())
        let uiPayload = try #require(
            JSONSerialization.jsonObject(with: Data(contentsOf: melixHome.operatorSessionFileURL)) as? [String: Any]
        )
        #expect(restoredState.selectedToolSection == .workflowRecipes)
        #expect(uiPayload["selected_tool_section"] as? String == "workflowRecipes")
    }

    static let catalogJSON = #"""
    {
      "schema_version": "melix.workflow_recipe_catalog.v1",
      "recipes": [
        {
          "id": "import.hf-mlx-model",
          "version": "1",
          "title": "Import an MLX-compatible Hugging Face model",
          "tasks": ["model_import"],
          "recipe_digest": "digest-import"
        },
        {
          "id": "dataset.hf-eval",
          "version": "1",
          "title": "Prepare a Hugging Face evaluation dataset",
          "tasks": ["dataset_import", "eval"],
          "recipe_digest": "digest-dataset"
        }
      ],
      "metrics": {
        "recipe.lookup_ms": 2.5
      }
    }
    """#

    static let filteredCatalogJSON = #"""
    {
      "schema_version": "melix.workflow_recipe_catalog.v1",
      "recipes": [
        {
          "id": "import.hf-mlx-model",
          "version": "1",
          "title": "Import an MLX-compatible Hugging Face model",
          "tasks": ["model_import"],
          "recipe_digest": "digest-import"
        }
      ],
      "metrics": {
        "recipe.lookup_ms": 1.5
      }
    }
    """#

    static let detailJSON = #"""
    {
      "schema_version": "melix.workflow_recipe.v1",
      "id": "import.hf-mlx-model",
      "version": "1",
      "title": "Import an MLX-compatible Hugging Face model",
      "description": "Inspect fit, download a Hugging Face model, and rescan managed roots.",
      "tasks": ["model_import"],
      "recipe_digest": "digest-import",
      "inputs": [
        {
          "name": "repo_id",
          "type": "string",
          "required": true,
          "uri_kind": "hf_model_repo"
        },
        {
          "name": "revision",
          "type": "string",
          "required": false,
          "default": "main"
        },
        {
          "name": "model_id",
          "type": "string",
          "required": false
        }
      ],
      "preflight": {
        "uri_inspection": true,
        "pipeline_dry_run": true,
        "memory_fit": "delegated_to_existing_commands"
      },
      "pipeline": {
        "schema_version": "melix.pipeline.v1",
        "steps": [
          {
            "id": "estimate_import",
            "command": "estimate.import",
            "args": {
              "repo_id": "",
              "target_kind": "import"
            }
          },
          {
            "id": "download_model",
            "command": "model.hub.download",
            "args": {
              "repo_id": "",
              "revision": "main"
            }
          },
          {
            "id": "rescan_roots",
            "command": "model.roots.rescan",
            "args": {}
          }
        ]
      },
      "outputs": {
        "managed_model_path": "from download_model step"
      }
    }
    """#

    static let uriInspectionJSON = #"""
    {
      "schema_version": "melix.uri_inspection.v1",
      "original_uri": "org/repo",
      "normalized_locator": "org/repo",
      "candidate_count": 2,
      "ambiguity_count": 1,
      "candidates": [
        {
          "kind": "hf_model_repo",
          "confidence": 0.62,
          "task_kind": "model_import",
          "source_kind": "huggingface",
          "revision": "main",
          "repo_id": "org/repo",
          "normalized_locator": "hf://model/org/repo",
          "reasons": [
            "bare org/repo locator; prefer hf://model or hf://dataset for disambiguation"
          ],
          "recommended_next_action": "model hub download --repo-id org/repo",
          "generated_command_arguments": ["model", "hub", "download", "--repo-id", "org/repo"],
          "warnings": []
        },
        {
          "kind": "hf_dataset_repo",
          "confidence": 0.38,
          "task_kind": "dataset_import",
          "source_kind": "huggingface",
          "revision": "main",
          "repo_id": "org/repo",
          "normalized_locator": "hf://dataset/org/repo",
          "reasons": [
            "bare org/repo locator could also identify a Hugging Face dataset"
          ],
          "recommended_next_action": "dataset hub download --repo-id org/repo",
          "generated_command_arguments": ["dataset", "hub", "download", "--repo-id", "org/repo"],
          "warnings": ["prefer an explicit hf://dataset URI"]
        }
      ],
      "metrics": {
        "uri.inspect_ms": 3.5,
        "uri.candidate_count": 2,
        "uri.ambiguity_count": 1
      }
    }
    """#

    static let emptyURIInspectionJSON = #"""
    {
      "schema_version": "melix.uri_inspection.v1",
      "original_uri": "",
      "normalized_locator": "",
      "candidate_count": 0,
      "ambiguity_count": 0,
      "candidates": [],
      "metrics": {}
    }
    """#

    static let stringlyURIInspectionJSON = #"""
    {
      "schema_version": "melix.uri_inspection.v1",
      "original_uri": "hf://model/org/repo",
      "normalized_locator": "hf://model/org/repo",
      "candidate_count": "1",
      "ambiguity_count": "0",
      "candidates": [
        {
          "kind": "hf_model_repo",
          "confidence": "0.625",
          "task_kind": "model_import",
          "source_kind": "huggingface",
          "normalized_locator": "hf://model/org/repo",
          "reasons": [],
          "generated_command_arguments": [],
          "recommended_next_action": "inspect_only",
          "warnings": []
        }
      ],
      "metrics": {}
    }
    """#

    static let singleCandidateURIInspectionJSON = #"""
    {
      "schema_version": "melix.uri_inspection.v1",
      "original_uri": "hf://model/org/repo",
      "normalized_locator": "hf://model/org/repo",
      "candidate_count": 1,
      "ambiguity_count": 0,
      "candidates": [
        {
          "kind": "hf_model_repo",
          "confidence": 0.96,
          "task_kind": "model_import",
          "source_kind": "huggingface",
          "revision": "main",
          "repo_id": "org/repo",
          "normalized_locator": "hf://model/org/repo@main",
          "reasons": ["explicit Hugging Face model locator"],
          "recommended_next_action": "model hub download --repo-id org/repo --revision main",
          "generated_command_arguments": ["model", "hub", "download", "--repo-id", "org/repo", "--revision", "main"],
          "warnings": []
        }
      ],
      "metrics": {
        "uri.candidate_count": 1
      }
    }
    """#

    static let initPreviewJSON = #"""
    {
      "schema_version": "melix.workflow_recipe.v1",
      "id": "import.hf-mlx-model",
      "version": "1",
      "title": "Import an MLX-compatible Hugging Face model",
      "description": "Inspect fit, download a Hugging Face model, and rescan managed roots.",
      "tasks": ["model_import"],
      "recipe_digest": "digest-import",
      "inputs": [
        {
          "name": "repo_id",
          "type": "string",
          "required": true,
          "uri_kind": "hf_model_repo"
        }
      ],
      "preflight": {
        "uri_inspection": true,
        "pipeline_dry_run": true
      },
      "pipeline": {
        "schema_version": "melix.pipeline.v1",
        "steps": [
          {
            "id": "download_model",
            "command": "model.hub.download",
            "args": {
              "repo_id": "org/repo",
              "revision": "main"
            }
          }
        ]
      },
      "outputs": {
        "managed_model_path": "from download_model step"
      },
      "provenance": {
        "source": "generated_from_uri",
        "source_uri_digest": "sha256:source-uri-digest",
        "inspection": {
          "schema_version": "melix.uri_inspection.v1",
          "original_uri": "hf://model/org/repo",
          "normalized_locator": "hf://model/org/repo",
          "candidate_count": 1,
          "ambiguity_count": 0,
          "candidates": [
            {
              "kind": "hf_model_repo",
              "confidence": 0.96,
              "task_kind": "model_import",
              "source_kind": "huggingface",
              "revision": "main",
              "repo_id": "org/repo",
              "normalized_locator": "hf://model/org/repo@main",
              "reasons": ["explicit Hugging Face model locator"],
              "recommended_next_action": "model hub download --repo-id org/repo --revision main",
              "generated_command_arguments": ["model", "hub", "download", "--repo-id", "org/repo", "--revision", "main"],
              "warnings": []
            }
          ],
          "metrics": {
            "uri.candidate_count": 1
          }
        }
      }
    }
    """#

    static let initPreviewWithoutInspectionJSON = #"""
    {
      "schema_version": "melix.workflow_recipe.v1",
      "id": "import.hf-mlx-model",
      "version": "1",
      "title": "Import an MLX-compatible Hugging Face model",
      "description": "Inspect fit, download a Hugging Face model, and rescan managed roots.",
      "tasks": ["model_import"],
      "recipe_digest": "digest-import",
      "inputs": [],
      "preflight": {},
      "pipeline": {
        "schema_version": "melix.pipeline.v1",
        "steps": []
      },
      "outputs": {},
      "provenance": {
        "source": "generated_from_uri",
        "source_uri_digest": "sha256:source-uri-digest"
      }
    }
    """#

    static let planJSON = #"""
    {
      "schema_version": "melix.workflow_recipe_plan.v1",
      "recipe_id": "import.hf-mlx-model",
      "recipe_version": "1",
      "recipe_digest": "digest-import",
      "pipeline": {
        "schema_version": "melix.pipeline.v1",
        "steps": [
          {
            "id": "estimate_import",
            "command": "estimate.import",
            "args": {
              "repo_id": "org/repo",
              "target_kind": "import"
            }
          },
          {
            "id": "download_model",
            "command": "model.hub.download",
            "args": {
              "repo_id": "org/repo",
              "revision": "main"
            }
          },
          {
            "id": "rescan_roots",
            "command": "model.roots.rescan",
            "args": {}
          }
        ]
      },
      "artifacts": [
        {
          "kind": "pipeline",
          "path": "/tmp/planned.pipeline.json"
        }
      ],
      "metrics": {
        "recipe.lookup_ms": 1.5,
        "recipe.schema_validate_ms": 0.5,
        "recipe.plan_ms": 2.25
      }
    }
    """#

    static let applyJSON = #"""
    {
      "schema_version": "melix.pipeline.run.v1",
      "name": "import.hf-mlx-model",
      "trace_id": "trace-123",
      "status": "planned",
      "receipt_dir": "/tmp/recipe-run/receipts",
      "summary_path": "/tmp/recipe-run/receipts/run.json",
      "pipeline_hash": "sha256:pipeline",
      "inputs_hash": "sha256:inputs",
      "recipe": {
        "id": "import.hf-mlx-model",
        "version": "1",
        "digest": "digest-import",
        "retention_limit": 20,
        "run_root": "/tmp/recipe-run"
      },
      "steps": [
        {
          "id": "estimate_import",
          "command": "estimate.import",
          "status": "planned",
          "receipt_path": "/tmp/recipe-run/receipts/steps/001-estimate_import.json",
          "artifact_paths": ["/tmp/import-fit.json"],
          "command_id": "estimate.import",
          "args_hash": "sha256:args-estimate"
        },
        {
          "id": "download_model",
          "command": "model.hub.download",
          "status": "planned",
          "receipt_path": "/tmp/recipe-run/receipts/steps/002-download_model.json",
          "artifact_paths": [],
          "command_id": "model.hub.download",
          "args_hash": "sha256:args-download"
        },
        {
          "id": "rescan_roots",
          "command": "model.roots.rescan",
          "status": "planned",
          "receipt_path": "/tmp/recipe-run/receipts/steps/003-rescan_roots.json",
          "artifact_paths": [],
          "command_id": "model.roots.rescan",
          "args_hash": "sha256:args-rescan"
        }
      ],
      "metrics": {
        "melix.pipeline.resume_skipped_count": 0,
        "melix.pipeline.failed_step_count": 0,
        "recipe.apply_start_ms": 1.75,
        "recipe.apply_retained_runs": 1
      }
    }
    """#

    static let fallbackURIInspectionJSON = #"""
    {
      "schema_version": "melix.uri_inspection.v1",
      "original_uri": "unknown",
      "normalized_locator": "unknown",
      "candidates": [
        {
          "kind": "unknown",
          "task_kind": "inspect",
          "source_kind": "local_path",
          "normalized_locator": "unknown",
          "reasons": [],
          "generated_command_arguments": [],
          "recommended_next_action": "inspect_only",
          "warnings": []
        }
      ],
      "metrics": {}
    }
    """#
}

@MainActor
private func hostWorkflowRecipeView<Content: View>(_ rootView: Content) -> NSView {
    let hostingView = NSHostingView(rootView: rootView)
    hostingView.frame = CGRect(origin: .zero, size: CGSize(width: 960, height: 720))
    hostingView.layoutSubtreeIfNeeded()
    return hostingView
}

@MainActor
private func renderedWorkflowRecipeButtons(in rootView: NSView) -> [NSButton] {
    var buttons: [NSButton] = []
    func visit(_ view: NSView) {
        if let button = view as? NSButton {
            buttons.append(button)
        }
        view.subviews.forEach(visit)
    }
    visit(rootView)
    return buttons
}

@MainActor
private func waitForWorkflowRecipeCondition(
    _ description: String,
    condition: @escaping @MainActor () -> Bool
) async throws {
    for _ in 0..<50 {
        if condition() {
            return
        }
        try await Task.sleep(nanoseconds: 20_000_000)
    }
    Issue.record("Timed out waiting for \(description).")
}
