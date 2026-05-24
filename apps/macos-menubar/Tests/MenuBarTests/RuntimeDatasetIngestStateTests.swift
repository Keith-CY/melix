import Foundation
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Runtime Dataset Ingest State")
struct RuntimeDatasetIngestStateTests {
    @Test("dataset ingest receipt decodes quality control metrics")
    func datasetIngestReceiptDecodesQualityControlMetrics() async throws {
        let runner = RecordingCLIWorkflowRunner()
        let command = MelixCLICommand.datasetPrepareIngest(Self.options())
        await runner.configureOutput(Self.receiptJSON, for: command)

        let receipt = try await runner.prepareDatasetIngest(options: Self.options())

        #expect(receipt.schemaVersion == "melix.dataset_ingest_receipt.v1")
        #expect(receipt.status == "ready")
        #expect(receipt.workspaceProjectID == "m-courtyard-demo")
        #expect(receipt.datasetPreparationID == "prep-1")
        #expect(receipt.sourceInventory.map(\.sourceKind) == ["text"])
        #expect(receipt.sourceInventory.first?.recordCount == 1)
        #expect(receipt.qualityControlSummary["pii_mask_count"] == 1)
        #expect(receipt.metrics["segment_count"] == 1)
        #expect(await runner.snapshotRecordedCommands() == [command])
    }

    @Test("dataset ingest receipt decodes typed operator failures")
    func datasetIngestReceiptDecodesTypedOperatorFailures() throws {
        let receipt = try RuntimeDatasetIngestReceiptDecoder.decode(Self.blockedReceiptJSON)

        #expect(receipt.status == "blocked")
        #expect(receipt.operatorFailures.count == 1)
        #expect(receipt.operatorFailures.first?.code == "DATASET_INGEST_UNSUPPORTED_SOURCE")
        #expect(receipt.operatorFailures.first?.detail == "The source file extension is not supported for dataset ingest.")
        #expect(receipt.operatorFailures.first?.recoveryHint == "Convert the source to text, markdown, code, JSONL, JSON, CSV, TSV, PDF text, or DOCX text fixtures.")
    }

    @Test("dataset ingest maps malformed receipts to workflow errors")
    func datasetIngestMapsMalformedReceiptsToWorkflowErrors() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        let command = MelixCLICommand.datasetPrepareIngest(Self.options())
        await runner.configureOutput("not-json", for: command)

        do {
            _ = try await runner.prepareDatasetIngest(options: Self.options())
            Issue.record("Expected malformed dataset ingest output to fail.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error.failureKind == .invalidJSON)
            if case .invalidJSON(let commandID, let surface, let output) = error {
                #expect(commandID == "dataset.prepare.ingest")
                #expect(surface == .subprocess)
                #expect(output == "not-json")
            } else {
                Issue.record("Expected invalidJSON, got \(error).")
            }
        }
    }

    private static func options() -> DatasetPrepareIngestOptions {
        .init(
            workspaceProjectID: "m-courtyard-demo",
            workspaceManifestPath: "/tmp/melix-workspace/workspace-manifest.json",
            inputPath: "/tmp/melix-workspace/raw",
            outputDir: "/tmp/melix-workspace/prepared",
            datasetPreparationID: "prep-1",
            json: true
        )
    }

    private static let receiptJSON = """
    {
      "schema_version": "melix.dataset_ingest_receipt.v1",
      "status": "ready",
      "workspace_project_id": "m-courtyard-demo",
      "dataset_preparation_id": "prep-1",
      "source_inventory": [
        {
          "source_id": "source-notes",
          "source_kind": "text",
          "record_count": 1
        }
      ],
      "quality_control_summary": {
        "source_file_count": 1,
        "segment_count": 1,
        "pii_mask_count": 1,
        "exact_dedup_count": 0,
        "fuzzy_dedup_count": 0,
        "fuzzy_dedup_ratio": 0
      },
      "metrics": {
        "source_file_count": 1,
        "segment_count": 1,
        "pii_mask_count": 1
      }
    }
    """

    private static let blockedReceiptJSON = """
    {
      "schema_version": "melix.dataset_ingest_receipt.v1",
      "status": "blocked",
      "workspace_project_id": "m-courtyard-demo",
      "dataset_preparation_id": "prep-1",
      "source_inventory": [],
      "operator_failures": [
        {
          "id": "dataset-ingest-unsupported-source-archive-bin",
          "code": "DATASET_INGEST_UNSUPPORTED_SOURCE",
          "detail": "The source file extension is not supported for dataset ingest.",
          "recovery_hint": "Convert the source to text, markdown, code, JSONL, JSON, CSV, TSV, PDF text, or DOCX text fixtures."
        }
      ],
      "quality_control_summary": {
        "source_file_count": 1,
        "segment_count": 0,
        "pii_mask_count": 0,
        "exact_dedup_count": 0,
        "fuzzy_dedup_count": 0,
        "fuzzy_dedup_ratio": 0
      },
      "metrics": {
        "source_file_count": 1,
        "segment_count": 0,
        "pii_mask_count": 0
      }
    }
    """
}
