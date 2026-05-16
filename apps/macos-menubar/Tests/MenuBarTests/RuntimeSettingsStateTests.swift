import Foundation
import Testing

@testable import AppMain

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
}
