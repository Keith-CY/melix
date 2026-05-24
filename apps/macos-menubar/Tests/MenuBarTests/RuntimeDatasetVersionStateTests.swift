import Foundation
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Runtime Dataset Version State")
struct RuntimeDatasetVersionStateTests {
    @Test("dataset version receipt decodes quality summary paths and counts")
    func datasetVersionReceiptDecodesQualitySummaryPathsAndCounts() async throws {
        let runner = RecordingCLIWorkflowRunner()
        let options = Self.versionOptions()
        let command = MelixCLICommand.datasetPrepareVersion(options)
        await runner.configureOutput(Self.versionJSON, for: command)

        let version = try await runner.prepareDatasetVersion(options: options)

        #expect(version.schemaVersion == "melix.dataset_version.v1")
        #expect(version.datasetID == "support-chat")
        #expect(version.versionID == "support-chat-v1")
        #expect(version.trainCount == 2)
        #expect(version.validationCount == 1)
        #expect(version.failedCount == 1)
        #expect(version.qualitySummaryPath == "/tmp/datasets/support-chat/versions/support-chat-v1/quality-summary.json")
        #expect(version.metrics["generated_sample_count"] == 3)
        #expect(await runner.snapshotRecordedCommands() == [command])
    }

    @Test("dataset retry receipt proves successful samples were not rewritten")
    func datasetRetryReceiptProvesSuccessfulSamplesWereNotRewritten() async throws {
        let runner = RecordingCLIWorkflowRunner()
        let options = Self.retryOptions()
        let command = MelixCLICommand.datasetPrepareRetryFailed(options)
        await runner.configureOutput(Self.retryJSON, for: command)

        let retry = try await runner.retryFailedDatasetVersion(options: options)

        #expect(retry.schemaVersion == "melix.dataset_retry_receipt.v1")
        #expect(retry.baseVersionID == "support-chat-v1")
        #expect(retry.retryVersionID == "support-chat-v2")
        #expect(retry.inputFailedSegmentCount == 1)
        #expect(retry.retrySuccessCount == 1)
        #expect(retry.retryFailedCount == 0)
        #expect(retry.reusedSuccessfulSampleCount == 3)
        #expect(retry.rewrittenSuccessfulSampleCount == 0)
        #expect(retry.failedRetrySuccessRate == 1.0)
    }

    @Test("dataset version list decodes deterministic version rows")
    func datasetVersionListDecodesDeterministicVersionRows() async throws {
        let runner = RecordingCLIWorkflowRunner()
        let options = Self.listOptions()
        let command = MelixCLICommand.datasetPrepareListVersions(options)
        await runner.configureOutput(Self.listJSON, for: command)

        let listing = try await runner.listDatasetVersions(options: options)

        #expect(listing.schemaVersion == "melix.dataset_version_list.v1")
        #expect(listing.datasetID == "support-chat")
        #expect(listing.versions.map(\.versionID) == ["support-chat-v1", "support-chat-v2"])
        #expect(listing.metrics["dataset_version_listing_latency_ms"] == 0.25)
    }

    @Test("dataset quality summary decoder exposes reportable grade")
    func datasetQualitySummaryDecoderExposesReportableGrade() throws {
        let summary = try RuntimeDatasetQualitySummaryDecoder.decode(Self.qualityJSON)

        #expect(summary.schemaVersion == "melix.dataset_quality_summary.v1")
        #expect(summary.datasetID == "support-chat")
        #expect(summary.versionID == "support-chat-v1")
        #expect(summary.score == 0.75)
        #expect(summary.grade == "C")
        #expect(summary.failedCount == 1)
        #expect(summary.metrics["quality_scoring_latency_ms"] == 0.12)
    }

    @Test("dataset version maps malformed JSON to workflow errors")
    func datasetVersionMapsMalformedJSONToWorkflowErrors() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        let options = Self.versionOptions()
        let command = MelixCLICommand.datasetPrepareVersion(options)
        await runner.configureOutput("not-json", for: command)

        do {
            _ = try await runner.prepareDatasetVersion(options: options)
            Issue.record("Expected malformed dataset version output to fail.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error.failureKind == .invalidJSON)
            if case .invalidJSON(let commandID, let surface, let output) = error {
                #expect(commandID == "dataset.prepare.version")
                #expect(surface == .subprocess)
                #expect(output == "not-json")
            } else {
                Issue.record("Expected invalidJSON, got \(error).")
            }
        }
    }

    private static func versionOptions() -> DatasetPrepareVersionOptions {
        .init(
            workspaceManifestPath: "/tmp/workspace-manifest.json",
            ingestReceiptPath: "/tmp/prepared/dataset-ingest-receipt.json",
            outputRoot: "/tmp/datasets",
            datasetID: "support-chat",
            versionID: "support-chat-v1",
            json: true
        )
    }

    private static func retryOptions() -> DatasetPrepareRetryFailedOptions {
        .init(
            workspaceManifestPath: "/tmp/workspace-manifest.json",
            datasetVersionPath: "/tmp/datasets/support-chat/versions/support-chat-v1/dataset-version.json",
            outputRoot: "/tmp/datasets",
            versionID: "support-chat-v2",
            json: true
        )
    }

    private static func listOptions() -> DatasetPrepareListVersionsOptions {
        .init(
            workspaceManifestPath: "/tmp/workspace-manifest.json",
            outputRoot: "/tmp/datasets",
            datasetID: "support-chat",
            json: true
        )
    }

    private static let versionJSON = """
    {
      "schema_version": "melix.dataset_version.v1",
      "status": "ready",
      "dataset_id": "support-chat",
      "version_id": "support-chat-v1",
      "created_at": "2026-05-24T01:00:00Z",
      "workspace_project_id": "m-courtyard-demo",
      "workspace_manifest_path": "/tmp/workspace-manifest.json",
      "source_receipt_path": "/tmp/prepared/dataset-ingest-receipt.json",
      "source_file_count": 1,
      "source_record_count": 1,
      "segment_count": 4,
      "mode": "chat",
      "generator_model": "melix.local.dataset-versioner.v1",
      "output_kind": "training",
      "output_format": "prompt_completion",
      "train_count": 2,
      "validation_count": 1,
      "failed_count": 1,
      "successful_segment_ids": ["segment-1", "segment-2", "segment-3"],
      "failed_segment_ids": ["segment-4"],
      "quality_summary_path": "/tmp/datasets/support-chat/versions/support-chat-v1/quality-summary.json",
      "package_manifest_path": "/tmp/datasets/support-chat/versions/support-chat-v1/manifest.json",
      "samples_path": "/tmp/datasets/support-chat/versions/support-chat-v1/samples.jsonl",
      "validation_samples_path": "/tmp/datasets/support-chat/versions/support-chat-v1/valid.jsonl",
      "failed_segments_path": "/tmp/datasets/support-chat/versions/support-chat-v1/failed-segments.jsonl",
      "metrics": {
        "generated_sample_count": 3,
        "failed_sample_count": 1
      }
    }
    """

    private static let retryJSON = """
    {
      "schema_version": "melix.dataset_retry_receipt.v1",
      "base_version_id": "support-chat-v1",
      "retry_version_id": "support-chat-v2",
      "input_failed_segment_count": 1,
      "retry_success_count": 1,
      "retry_failed_count": 0,
      "reused_successful_sample_count": 3,
      "rewritten_successful_sample_count": 0,
      "failed_retry_success_rate": 1.0,
      "dataset_version_path": "/tmp/datasets/support-chat/versions/support-chat-v2/dataset-version.json",
      "metrics": {
        "failed_retry_success_rate": 1.0
      }
    }
    """

    private static let listJSON = """
    {
      "schema_version": "melix.dataset_version_list.v1",
      "workspace_manifest_path": "/tmp/workspace-manifest.json",
      "dataset_id": "support-chat",
      "versions": [
        {
          "dataset_id": "support-chat",
          "version_id": "support-chat-v1",
          "created_at": "2026-05-24T01:00:00Z",
          "status": "ready",
          "train_count": 2,
          "validation_count": 1,
          "failed_count": 1,
          "quality_summary_path": "/tmp/datasets/support-chat/versions/support-chat-v1/quality-summary.json",
          "dataset_version_path": "/tmp/datasets/support-chat/versions/support-chat-v1/dataset-version.json"
        },
        {
          "dataset_id": "support-chat",
          "version_id": "support-chat-v2",
          "created_at": "2026-05-24T02:00:00Z",
          "status": "ready",
          "train_count": 4,
          "validation_count": 0,
          "failed_count": 0,
          "quality_summary_path": "/tmp/datasets/support-chat/versions/support-chat-v2/quality-summary.json",
          "dataset_version_path": "/tmp/datasets/support-chat/versions/support-chat-v2/dataset-version.json"
        }
      ],
      "metrics": {
        "dataset_version_listing_latency_ms": 0.25,
        "dataset_version_count": 2
      }
    }
    """

    private static let qualityJSON = """
    {
      "schema_version": "melix.dataset_quality_summary.v1",
      "dataset_id": "support-chat",
      "version_id": "support-chat-v1",
      "score": 0.75,
      "grade": "C",
      "success_rate": 0.75,
      "failed_count": 1,
      "train_count": 2,
      "validation_count": 1,
      "pii_mask_count": 1,
      "dedup_ratio": 0.0,
      "mean_output_length": 120,
      "p95_output_length": 160,
      "policy_id": "melix.dataset_quality.local.v1",
      "review_notes": [],
      "blocking_reasons": ["failed_generation"],
      "metrics": {
        "quality_scoring_latency_ms": 0.12
      }
    }
    """
}
