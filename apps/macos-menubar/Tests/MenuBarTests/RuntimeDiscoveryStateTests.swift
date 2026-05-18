import Foundation
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Runtime Discovery State")
struct RuntimeDiscoveryStateTests {
    @Test("runtime discovery decoder maps metadata payloads")
    func runtimeDiscoveryDecoderMapsMetadataPayloads() throws {
        let snapshot = try RuntimeDiscoveryPayloadDecoder.decodeSnapshot([
            (.info, Self.infoJSON),
            (.capabilities, Self.capabilitiesJSON),
            (.instructions, Self.instructionsJSON),
            (.schema, Self.schemaJSON),
            (.configMetadata, Self.configMetadataJSON),
        ])

        #expect(snapshot.payloads.map(\.endpoint) == RuntimeDiscoveryEndpoint.allCases)

        let info = try #require(snapshot.payload(for: .info))
        #expect(info.schemaVersion == "melix.discovery.info.v1")
        #expect(info.valueRows.contains { $0.key == "version" && $0.value == "0.2.0" })
        #expect(info.valueRows.contains { $0.key == "features" && $0.value.contains("runtime_settings") })
        #expect(info.valueRows.contains { $0.key == "supported_tasks" && $0.value.contains("evaluation") })
        #expect(info.valueRows.contains { $0.key == "local_paths.melix_home" && $0.value == "/tmp/melix-home" })
        #expect(info.valueRows.contains { $0.key == "update.status" && $0.value == "ok" })
        #expect(info.links.first { $0.key == "config_metadata" }?.url == "/api/config-metadata")
        #expect(info.schemaPaths.first { $0.key == "protocol" }?.path == "/repo/packages/protocol/schema")

        let capabilities = try #require(snapshot.payload(for: .capabilities))
        #expect(capabilities.models.first?.modelID == "mlx-community/Qwen3.5-9B-MLX-4bit")
        #expect(capabilities.models.first?.supportedTasksText == "text-generation, tools")
        #expect(capabilities.aliasDiscovery?.status == "suggested")
        #expect(capabilities.aliasDiscovery?.suggestionsText.contains("Qwen3.5-9B-MLX-4bit") == true)

        let instructions = try #require(snapshot.payload(for: .instructions))
        #expect(instructions.instructionAreas.first?.title == "Runtime settings")
        #expect(instructions.instructionAreas.first?.commandsText.contains("melix settings show --json") == true)

        let schema = try #require(snapshot.payload(for: .schema))
        #expect(schema.schemaPaths.map(\.key) == ["plans", "protocol"])
        #expect(schema.schemaPaths.first { $0.key == "plans" }?.path == "/repo/docs/plans")

        let configMetadata = try #require(snapshot.payload(for: .configMetadata))
        #expect(configMetadata.configSettings.first?.key == "max_concurrent_jobs")
        #expect(configMetadata.configSettings.first?.valueType == "int")
        #expect(configMetadata.configSettings.first?.defaultValueText == "2")
        #expect(configMetadata.configSettings.first?.environmentVariable == "MELIX_MAX_CONCURRENT_JOBS")
    }

    @Test("runtime discovery decoder maps model alias suggestions and no match states")
    func runtimeDiscoveryDecoderMapsModelAliasSuggestionsAndNoMatchStates() throws {
        let suggested = try RuntimeDiscoveryPayloadDecoder.decodePayload(endpoint: .capabilities, Self.capabilitiesJSON)
        let alias = try #require(suggested.aliasDiscovery)
        #expect(alias.statusDisplayTitle == "Suggestions available")
        #expect(alias.suggestions.map(\.modelID) == ["mlx-community/Qwen3.5-9B-MLX-4bit"])
        #expect(alias.suggestions.first?.aliasesText == "qwen35_9b_mlx_4bit")
        #expect(alias.suggestions.first?.displayText.contains("qwen3.5") == true)
        #expect(alias.emptyStateMessage.isEmpty)

        let noMatch = try RuntimeDiscoveryPayloadDecoder.decodePayload(endpoint: .capabilities, Self.noMatchCapabilitiesJSON)
        let noMatchAlias = try #require(noMatch.aliasDiscovery)
        #expect(noMatchAlias.status == "no_match")
        #expect(noMatchAlias.statusDisplayTitle == "No match")
        #expect(noMatchAlias.suggestions.isEmpty)
        #expect(noMatchAlias.emptyStateMessage == "No model alias matches not a/model id.")

        let fullModel = RuntimeDiscoveryAliasState(query: "org/model", status: "valid_full_model_id")
        #expect(fullModel.statusDisplayTitle == "Full model ID")
        #expect(fullModel.emptyStateMessage == "Query is already a full model ID.")
        let localPath = RuntimeDiscoveryAliasState(query: "/tmp/model", status: "local_path_passthrough")
        #expect(localPath.statusDisplayTitle == "Local path")
        #expect(localPath.emptyStateMessage == "Query is treated as a local model path.")
        let notRequested = RuntimeDiscoveryAliasState(query: "", status: "not_requested")
        #expect(notRequested.statusDisplayTitle == "Not requested")
        #expect(notRequested.emptyStateMessage == "Enter a model alias query to see suggestions.")
        let unknown = RuntimeDiscoveryAliasState(query: "custom", status: "custom_status")
        #expect(unknown.statusDisplayTitle == "custom_status")
        #expect(unknown.emptyStateMessage.isEmpty)
    }

    @Test("runtime view model refreshes discovery through CLI runner")
    @MainActor
    func runtimeViewModelRefreshesDiscoveryThroughCLIRunner() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureOutput(Self.infoJSON, for: .info(.init(json: true)))
        await runner.configureOutput(Self.capabilitiesJSON, for: .capabilities(.init(json: true)))
        await runner.configureOutput(Self.instructionsJSON, for: .instructions(.init(json: true)))
        await runner.configureOutput(Self.schemaJSON, for: .schema(.init(json: true)))
        await runner.configureOutput(Self.configMetadataJSON, for: .configMetadata(.init(json: true)))
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)

        await viewModel.refreshRuntimeDiscovery()

        #expect(viewModel.runtimeDiscoveryRefreshInProgress == false)
        #expect(viewModel.runtimeDiscoveryOperationMessage == "Runtime discovery refreshed.")
        #expect(viewModel.runtimeDiscoveryOperationErrorMessage.isEmpty)
        #expect(viewModel.runtimeDiscoveryPayloads.map(\.endpoint) == RuntimeDiscoveryEndpoint.allCases)
        #expect(viewModel.runtimeDiscoveryPayloads.first { $0.endpoint == .configMetadata }?.configSettings.first?.key == "max_concurrent_jobs")
        #expect(
            await runner.snapshotRecordedCommands() == [
                .info(.init(json: true)),
                .capabilities(.init(json: true)),
                .instructions(.init(json: true)),
                .schema(.init(json: true)),
                .configMetadata(.init(json: true)),
            ]
        )
    }

    @Test("runtime view model surfaces discovery refresh errors")
    @MainActor
    func runtimeViewModelSurfacesDiscoveryRefreshErrors() async {
        let missingRunnerViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await missingRunnerViewModel.refreshRuntimeDiscovery()
        #expect(missingRunnerViewModel.runtimeDiscoveryOperationErrorMessage == "Discovery CLI runner is unavailable.")
        #expect(missingRunnerViewModel.lastError == "Discovery CLI runner is unavailable.")

        let runner = RecordingCLIWorkflowRunner()
        await runner.configureFailure(
            .processFailed(commandID: "capabilities", surface: .subprocess, exitCode: 2, stderr: "discovery failed"),
            for: .capabilities(.init(json: true))
        )
        let failingViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        await failingViewModel.refreshRuntimeDiscovery()
        #expect(failingViewModel.runtimeDiscoveryOperationInProgress == false)
        #expect(failingViewModel.runtimeDiscoveryOperationErrorMessage.contains("discovery failed"))
        #expect(failingViewModel.lastCLIWorkflowFailure?.commandID == "capabilities")
    }

    @Test("runtime view model looks up model aliases through capabilities query")
    @MainActor
    func runtimeViewModelLooksUpModelAliasesThroughCapabilitiesQuery() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureOutput(
            Self.noMatchCapabilitiesJSON,
            for: .capabilities(.init(json: true, modelQuery: "not a/model id"))
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        viewModel.applyRuntimeDiscovery(
            RuntimeDiscoverySnapshotState(
                payloads: [
                    try RuntimeDiscoveryPayloadDecoder.decodePayload(endpoint: .info, Self.infoJSON),
                ]
            )
        )
        viewModel.updateRuntimeDiscoveryAliasQuery(" not a/model id ")

        await viewModel.lookupRuntimeDiscoveryModelAlias()

        let alias = try #require(viewModel.runtimeDiscoverySnapshot.payload(for: .capabilities)?.aliasDiscovery)
        #expect(alias.status == "no_match")
        #expect(alias.emptyStateMessage == "No model alias matches not a/model id.")
        #expect(viewModel.runtimeDiscoveryAliasLookupCanRun)
        #expect(viewModel.runtimeDiscoveryOperationMessage == "Model alias lookup refreshed.")
        #expect(
            await runner.snapshotRecordedCommands() == [
                .capabilities(.init(json: true, modelQuery: "not a/model id")),
            ]
        )

        let missingQueryViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        await missingQueryViewModel.lookupRuntimeDiscoveryModelAlias()
        #expect(missingQueryViewModel.runtimeDiscoveryOperationErrorMessage == "Model alias query is required.")

        let missingRunnerViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        missingRunnerViewModel.updateRuntimeDiscoveryAliasQuery("qwen")
        await missingRunnerViewModel.lookupRuntimeDiscoveryModelAlias()
        #expect(missingRunnerViewModel.runtimeDiscoveryOperationErrorMessage == "Discovery CLI runner is unavailable.")

        let failingRunner = RecordingCLIWorkflowRunner()
        await failingRunner.configureFailure(
            .processFailed(commandID: "capabilities", surface: .subprocess, exitCode: 2, stderr: "alias failed"),
            for: .capabilities(.init(json: true, modelQuery: "qwen"))
        )
        let failingViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: failingRunner)
        failingViewModel.updateRuntimeDiscoveryAliasQuery("qwen")
        await failingViewModel.lookupRuntimeDiscoveryModelAlias()
        #expect(failingViewModel.runtimeDiscoveryOperationErrorMessage.contains("alias failed"))
        #expect(failingViewModel.lastCLIWorkflowFailure?.commandID == "capabilities")
    }

    static let infoJSON = #"""
    {
      "schema_version": "melix.discovery.info.v1",
      "version": "0.2.0",
      "features": ["runtime_settings", "model_alias_discovery"],
      "supported_tasks": ["evaluation", "benchmark"],
      "links": {
        "capabilities": "/api/capabilities",
        "config_metadata": "/api/config-metadata"
      },
      "schema": {
        "schema_version": "melix.discovery.schema.v1",
        "schemas": [
          {
            "id": "protocol",
            "path": "/repo/packages/protocol/schema"
          }
        ]
      },
      "local_paths": {
        "melix_home": "/tmp/melix-home",
        "runtime_settings": "/tmp/melix-home/runtime_settings.json"
      },
      "update": {
        "status": "ok",
        "update_channel": "stable"
      },
      "metrics": {
        "discovery_build_ms": 4
      }
    }
    """#

    static let capabilitiesJSON = #"""
    {
      "schema_version": "melix.discovery.capabilities.v1",
      "features": ["runtime_settings"],
      "supported_tasks": ["text-generation", "tools"],
      "models": [
        {
          "model_id": "mlx-community/Qwen3.5-9B-MLX-4bit",
          "kind": "text",
          "supported_modalities": ["text"],
          "supported_tasks": ["text-generation", "tools"],
          "capability_receipt": {
            "tasks": {
              "text-generation": {
                "state": "supported"
              }
            }
          }
        }
      ],
      "model_alias_discovery": {
        "query": "qwen35_9b_mlx_4bit",
        "status": "suggested",
        "suggestions": [
          {
            "model_id": "mlx-community/Qwen3.5-9B-MLX-4bit",
            "family": "qwen3.5",
            "aliases": ["qwen35_9b_mlx_4bit"],
            "quantization": "4bit"
          }
        ],
        "families": []
      }
    }
    """#

    static let noMatchCapabilitiesJSON = #"""
    {
      "schema_version": "melix.discovery.capabilities.v1",
      "features": ["runtime_settings"],
      "supported_tasks": ["text-generation", "tools"],
      "models": [],
      "model_alias_discovery": {
        "query": "not a/model id",
        "status": "no_match",
        "suggestions": [],
        "families": []
      }
    }
    """#

    static let instructionsJSON = #"""
    {
      "schema_version": "melix.discovery.instructions.v1",
      "areas": [
        {
          "id": "settings",
          "title": "Runtime settings",
          "commands": [
            "melix settings show --json",
            "melix settings validate"
          ]
        }
      ]
    }
    """#

    static let schemaJSON = #"""
    {
      "schema_version": "melix.discovery.schema.v1",
      "schemas": [
        {
          "id": "plans",
          "path": "/repo/docs/plans"
        },
        {
          "id": "protocol",
          "path": "/repo/packages/protocol/schema"
        }
      ]
    }
    """#

    static let configMetadataJSON = #"""
    {
      "schema_version": "melix.discovery.config_metadata.v1",
      "settings": [
        {
          "key": "max_concurrent_jobs",
          "type": "int",
          "default": 2,
          "environment_variable": "MELIX_MAX_CONCURRENT_JOBS",
          "summary": "Maximum number of local runtime jobs Melix should schedule concurrently."
        }
      ]
    }
    """#
}
