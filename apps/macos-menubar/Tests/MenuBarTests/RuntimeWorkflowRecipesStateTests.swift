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
    }

    @Test("workflow recipe cli bridge maps malformed json to workflow errors")
    func workflowRecipeCLIBridgeMapsMalformedJSONToWorkflowErrors() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        await runner.configureOutput("not-json\n", for: .recipesList(.init(task: "", json: true)))
        await runner.configureOutput("not-json\n", for: .recipesShow(.init(recipeID: "import.hf-mlx-model", json: true)))
        await runner.configureOutput("not-json\n", for: .uriInspect(.init(uri: "org/repo", json: true)))

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
