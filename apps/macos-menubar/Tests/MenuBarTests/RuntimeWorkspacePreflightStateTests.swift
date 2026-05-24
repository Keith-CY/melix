import Foundation
import Testing

@testable import AppMain
import MelixCLICore

@Suite("Runtime Workspace Preflight State")
struct RuntimeWorkspacePreflightStateTests {
    @Test("workspace preflight receipt decodes typed operator failures")
    func workspacePreflightReceiptDecodesTypedOperatorFailures() async throws {
        let runner = RecordingCLIWorkflowRunner()
        let command = MelixCLICommand.workspacePreflight(
            .init(
                manifestPath: "/tmp/melix-workspace/workspace-manifest.json",
                outputPath: "/tmp/melix-workspace/workspace-preflight-receipt.json",
                json: true
            )
        )
        await runner.configureOutput(Self.blockedReceiptJSON(), for: command)

        let receipt = try await runner.preflightWorkspace(
            manifestPath: "/tmp/melix-workspace/workspace-manifest.json",
            outputPath: "/tmp/melix-workspace/workspace-preflight-receipt.json"
        )

        #expect(receipt.schemaVersion == "melix.workspace_preflight_receipt.v1")
        #expect(receipt.status == "blocked")
        #expect(receipt.projectID == "demo")
        #expect(receipt.statusSummary == "blocked: 1 issue")
        #expect(receipt.blockingChecks.map(\.code) == ["WORKSPACE_ROOT_MISSING"])
        let check = try #require(receipt.blockingChecks.first)
        #expect(check.title == "Required workspace roots are missing.")
        #expect(check.detail.contains("Create the missing root directories"))
        #expect(check.recoveryHint.contains("Create the missing root paths"))
        #expect(check.items.first?["root_id"] == "runs")
        #expect(receipt.metrics["missing_root_count"] == 1)
        #expect(receipt.metrics["preflight_latency_ms"] == 2.5)
        #expect(await runner.snapshotRecordedCommands() == [command])
    }

    @Test("workspace preflight maps malformed receipts to workflow errors")
    func workspacePreflightMapsMalformedReceiptsToWorkflowErrors() async throws {
        let runner = RecordingCLIWorkflowRunner(surface: .subprocess)
        let command = MelixCLICommand.workspacePreflight(
            .init(manifestPath: "/tmp/melix-workspace/workspace-manifest.json", json: true)
        )
        await runner.configureOutput("not-json", for: command)

        do {
            _ = try await runner.preflightWorkspace(
                manifestPath: "/tmp/melix-workspace/workspace-manifest.json"
            )
            Issue.record("Expected malformed workspace preflight output to fail.")
        } catch let error as MelixCLIWorkflowError {
            #expect(error.failureKind == .invalidJSON)
            if case .invalidJSON(let commandID, let surface, let output) = error {
                #expect(commandID == "workspace.preflight")
                #expect(surface == .subprocess)
                #expect(output == "not-json")
            } else {
                Issue.record("Expected invalidJSON, got \(error).")
            }
        }
    }

    private static func blockedReceiptJSON() -> String {
        """
        {
          "schema_version": "melix.workspace_preflight_receipt.v1",
          "status": "blocked",
          "project_id": "demo",
          "manifest_path": "workspace-manifest.json",
          "workspace_manifest_schema_version": "melix.workspace_manifest.v1",
          "checks": [
            {
              "code": "WORKSPACE_ROOT_MISSING",
              "status": "error",
              "title": "Required workspace roots are missing.",
              "detail": "Create the missing root directories or restore the workspace artifact before running this workspace.",
              "recovery_hint": "Create the missing root paths, or regenerate the workspace manifest after moving the workspace.",
              "items": [
                {
                  "root_id": "runs",
                  "path": "/tmp/melix-workspace/runs"
                }
              ]
            }
          ],
          "metrics": {
            "missing_root_count": 1,
            "preflight_latency_ms": 2.5
          }
        }
        """
    }
}
