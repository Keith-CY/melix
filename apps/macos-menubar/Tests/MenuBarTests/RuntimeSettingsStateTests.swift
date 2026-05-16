import Foundation
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Runtime Settings State")
struct RuntimeSettingsStateTests {
    @Test("settings show decoder creates sorted desktop setting rows")
    func settingsShowDecoderCreatesSortedDesktopSettingRows() throws {
        let snapshot = try RuntimeSettingsPayloadDecoder.decodeShow(Self.settingsShowJSON)

        #expect(snapshot.schemaVersion == "melix.runtime_settings.effective.v1")
        #expect(snapshot.rows.map(\.key) == [
            "artifact_path",
            "max_concurrent_jobs",
            "memory_pressure_threshold",
            "model_cache_path",
        ])

        let maxConcurrentJobs = try #require(snapshot.rows.first { $0.key == "max_concurrent_jobs" })
        #expect(maxConcurrentJobs.id == "max_concurrent_jobs")
        #expect(maxConcurrentJobs.currentValueText == "4")
        #expect(maxConcurrentJobs.source == "environment")
        #expect(maxConcurrentJobs.sourceDetail == "MELIX_MAX_CONCURRENT_JOBS")
        #expect(maxConcurrentJobs.validationState == .notValidated)
        #expect(maxConcurrentJobs.validationMessage.isEmpty)

        let memoryThreshold = try #require(snapshot.rows.first { $0.key == "memory_pressure_threshold" })
        #expect(memoryThreshold.currentValueText == "0.75")
        #expect(memoryThreshold.source == "project_settings")
        #expect(memoryThreshold.sourceDetail == "/repo/.melix/runtime_settings.json")

        #expect(snapshot.sources.map(\.key) == ["project_settings", "user_settings"])
        #expect(snapshot.sources.first { $0.key == "user_settings" }?.path == "/tmp/melix-home/runtime_settings.json")
        #expect(snapshot.metrics.first { $0.name == "settings_resolve_ms" }?.valueText == "3")
    }

    @Test("settings show decoder preserves object values as compact JSON")
    func settingsShowDecoderPreservesObjectValuesAsCompactJSON() throws {
        let snapshot = try RuntimeSettingsPayloadDecoder.decodeShow(
            """
            {
              "schema_version": "melix.runtime_settings.effective.v1",
              "settings": {
                "experimental_flags": {
                  "value": {
                    "beta": true,
                    "limit": 2
                  },
                  "source": "cli_flag",
                  "source_detail": "--override experimental_flags"
                },
                "null_override": {
                  "source": 7,
                  "source_detail": null
                }
              },
              "sources": {
                "user_settings": null
              },
              "metrics": {
                "cache_hit": true
              }
            }
            """
        )

        let objectRow = try #require(snapshot.rows.first { $0.key == "experimental_flags" })
        #expect(objectRow.currentValueText == "{\"beta\":true,\"limit\":2}")
        #expect(objectRow.source == "cli_flag")
        #expect(objectRow.sourceDetail == "--override experimental_flags")

        let nullRow = try #require(snapshot.rows.first { $0.key == "null_override" })
        #expect(nullRow.currentValueText == "null")
        #expect(nullRow.source == "7")
        #expect(nullRow.sourceDetail.isEmpty)
        #expect(snapshot.sources.first?.path == "")
        #expect(snapshot.metrics.first?.valueText == "true")
    }

    @Test("settings show decoder rejects invalid settings payloads")
    func settingsShowDecoderRejectsInvalidSettingsPayloads() {
        #expect(throws: DecodingError.self) {
            _ = try RuntimeSettingsPayloadDecoder.decodeShow("[]")
        }

        #expect(throws: DecodingError.self) {
            _ = try RuntimeSettingsPayloadDecoder.decodeShow(
                """
                {
                  "schema_version": "melix.runtime_settings.effective.v1",
                  "sources": {},
                  "metrics": {}
                }
                """
            )
        }
    }

    @Test("runtime settings validation decoder maps issues and metrics")
    func runtimeSettingsValidationDecoderMapsIssuesAndMetrics() throws {
        let result = try RuntimeSettingsPayloadDecoder.decodeValidation(
            """
            {
              "valid": false,
              "errors": [
                {
                  "key": "max_concurrent_jobs",
                  "message": "expected int",
                  "source": "user_settings"
                }
              ],
              "metrics": {
                "settings_validate_ms": 5
              }
            }
            """
        )

        #expect(result.valid == false)
        #expect(result.summaryText == "1 validation issue.")
        #expect(result.issues.first?.key == "max_concurrent_jobs")
        #expect(result.issues.first?.message == "expected int")
        #expect(result.issues.first?.source == "user_settings")
        #expect(result.metrics.first?.name == "settings_validate_ms")
        #expect(result.metrics.first?.valueText == "5")

        let multipleIssues = try RuntimeSettingsPayloadDecoder.decodeValidation(
            """
            {
              "errors": [
                {
                  "key": "max_concurrent_jobs",
                  "message": "expected int"
                },
                {
                  "key": "memory_pressure_threshold",
                  "message": "expected 0.0...1.0"
                }
              ]
            }
            """
        )
        #expect(multipleIssues.valid == false)
        #expect(multipleIssues.summaryText == "2 validation issues.")

        #expect(throws: DecodingError.self) {
            _ = try RuntimeSettingsPayloadDecoder.decodeValidation("[]")
        }
    }

    @Test("runtime view model wires settings set reset and validate through CLI runner")
    @MainActor
    func runtimeViewModelWiresSettingsSetResetAndValidateThroughCLIRunner() async throws {
        let runner = RecordingCLIWorkflowRunner()
        await runner.configureOutput(
            """
            {
              "key": "max_concurrent_jobs",
              "value": 6,
              "source": "user_settings"
            }
            """,
            for: .settingsSet(.init(key: "max_concurrent_jobs", value: "6", json: true))
        )
        await runner.configureOutput(Self.settingsAfterMutationJSON, for: .settingsShow(.init(json: true)))
        await runner.configureOutput(
            """
            {
              "valid": true,
              "errors": [],
              "metrics": {
                "settings_validate_ms": 4
              }
            }
            """,
            for: .settingsValidate(.init(json: true))
        )
        await runner.configureOutput(
            """
            {
              "key": "max_concurrent_jobs",
              "removed": true
            }
            """,
            for: .settingsReset(.init(key: "max_concurrent_jobs", json: true))
        )
        let viewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)

        viewModel.updateRuntimeSettingDraft(key: "max_concurrent_jobs", value: "6")
        await viewModel.setRuntimeSetting()
        #expect(viewModel.runtimeSettingsOperationInProgress == false)
        #expect(viewModel.runtimeSettingsOperationMessage == "Updated max_concurrent_jobs.")
        #expect(viewModel.runtimeSettingsOperationErrorMessage.isEmpty)
        #expect(viewModel.runtimeSettingRows.first { $0.key == "max_concurrent_jobs" }?.currentValueText == "6")

        await viewModel.validateRuntimeSettings()
        #expect(viewModel.runtimeSettingsValidationResult?.valid == true)
        #expect(viewModel.runtimeSettingsOperationMessage == "Runtime settings are valid.")

        await viewModel.resetRuntimeSetting()
        #expect(viewModel.runtimeSettingsOperationMessage == "Reset max_concurrent_jobs.")

        #expect(
            await runner.snapshotRecordedCommands() == [
                .settingsSet(.init(key: "max_concurrent_jobs", value: "6", json: true)),
                .settingsShow(.init(json: true)),
                .settingsValidate(.init(json: true)),
                .settingsReset(.init(key: "max_concurrent_jobs", json: true)),
                .settingsShow(.init(json: true)),
            ]
        )
    }

    @Test("runtime view model surfaces local settings operation errors")
    @MainActor
    func runtimeViewModelSurfacesLocalSettingsOperationErrors() async {
        let missingInputViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient())
        await missingInputViewModel.setRuntimeSetting()
        #expect(missingInputViewModel.runtimeSettingsOperationErrorMessage == "Enter a setting key and value before setting.")
        #expect(missingInputViewModel.lastError == "Enter a setting key and value before setting.")

        missingInputViewModel.updateRuntimeSettingDraft(key: "max_concurrent_jobs", value: "6")
        await missingInputViewModel.setRuntimeSetting()
        #expect(missingInputViewModel.runtimeSettingsOperationErrorMessage == "Settings CLI runner is unavailable.")

        missingInputViewModel.updateRuntimeSettingDraft(key: "", value: "6")
        await missingInputViewModel.resetRuntimeSetting()
        #expect(missingInputViewModel.runtimeSettingsOperationErrorMessage == "Enter a setting key before resetting.")

        missingInputViewModel.updateRuntimeSettingDraft(key: "max_concurrent_jobs", value: "6")
        await missingInputViewModel.resetRuntimeSetting()
        #expect(missingInputViewModel.runtimeSettingsOperationErrorMessage == "Settings CLI runner is unavailable.")

        await missingInputViewModel.validateRuntimeSettings()
        #expect(missingInputViewModel.runtimeSettingsOperationErrorMessage == "Settings CLI runner is unavailable.")

        let runner = RecordingCLIWorkflowRunner()
        await runner.configureFailure(
            .processFailed(commandID: "settings.set", surface: .subprocess, exitCode: 2, stderr: "invalid setting"),
            for: .settingsSet(.init(key: "max_concurrent_jobs", value: "many", json: true))
        )
        let failingViewModel = RuntimeViewModel(client: FakeControlPlaneXPCClient(), cliWorkflowRunner: runner)
        failingViewModel.updateRuntimeSettingDraft(key: "max_concurrent_jobs", value: "many")
        await failingViewModel.setRuntimeSetting()

        #expect(failingViewModel.runtimeSettingsOperationInProgress == false)
        #expect(failingViewModel.runtimeSettingsOperationErrorMessage.contains("invalid setting"))
        #expect(failingViewModel.lastCLIWorkflowFailure?.commandID == "settings.set")

        await runner.configureFailure(
            .processFailed(commandID: "settings.reset", surface: .subprocess, exitCode: 2, stderr: "reset failed"),
            for: .settingsReset(.init(key: "max_concurrent_jobs", json: true))
        )
        await failingViewModel.resetRuntimeSetting()
        #expect(failingViewModel.runtimeSettingsOperationErrorMessage.contains("reset failed"))
        #expect(failingViewModel.lastCLIWorkflowFailure?.commandID == "settings.reset")

        await runner.configureFailure(
            .processFailed(commandID: "settings.validate", surface: .subprocess, exitCode: 2, stderr: "validate failed"),
            for: .settingsValidate(.init(json: true))
        )
        await failingViewModel.validateRuntimeSettings()
        #expect(failingViewModel.runtimeSettingsOperationErrorMessage.contains("validate failed"))
        #expect(failingViewModel.lastCLIWorkflowFailure?.commandID == "settings.validate")
    }

    private static let settingsShowJSON = """
    {
      "schema_version": "melix.runtime_settings.effective.v1",
      "settings": {
        "model_cache_path": {
          "value": "/tmp/melix/models",
          "source": "default",
          "source_detail": "builtin"
        },
        "max_concurrent_jobs": {
          "value": 4,
          "source": "environment",
          "source_detail": "MELIX_MAX_CONCURRENT_JOBS"
        },
        "memory_pressure_threshold": {
          "value": 0.75,
          "source": "project_settings",
          "source_detail": "/repo/.melix/runtime_settings.json"
        },
        "artifact_path": {
          "value": "/tmp/melix/artifacts",
          "source": "user_settings",
          "source_detail": "/tmp/melix-home/runtime_settings.json"
        }
      },
      "sources": {
        "user_settings": "/tmp/melix-home/runtime_settings.json",
        "project_settings": "/repo/.melix/runtime_settings.json"
      },
      "metrics": {
        "settings_resolve_ms": 3
      }
    }
    """

    private static let settingsAfterMutationJSON = """
    {
      "schema_version": "melix.runtime_settings.effective.v1",
      "settings": {
        "max_concurrent_jobs": {
          "value": 6,
          "source": "user_settings",
          "source_detail": "/tmp/melix-home/runtime_settings.json"
        }
      },
      "sources": {
        "user_settings": "/tmp/melix-home/runtime_settings.json"
      },
      "metrics": {
        "settings_resolve_ms": 3
      }
    }
    """
}
