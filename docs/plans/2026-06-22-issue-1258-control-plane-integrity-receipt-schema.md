# Control Plane Artifact Integrity Receipt Schema Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make managed artifact integrity evidence part of the typed control-plane model operation artifact schema.

**Architecture:** Keep the Python worker download pipeline as the receipt producer and add a typed `ArtifactIntegrityReceipt` message to both worker and control-plane protocol schemas. `MaintenanceCore` attaches the latest worker-owned `artifact_integrity` receipt to download/import completion events, and `ControlPlaneService` projects it through `ModelOperationArtifact` so CLI, desktop, and API consumers do not need to parse raw manifest JSON for the trust decision.

**Tech Stack:** Protobuf schemas and generated Python/Swift artifacts, Python worker maintenance core, Swift control-plane model operation mapping, pytest, Swift Testing.

---

## Governing Context

- GitHub issue: `https://github.com/Keith-CY/melix/issues/1258`
- Existing worker receipt slices:
  - `docs/plans/2026-05-25-issue-1258-strict-install-preflight.md`
  - `docs/plans/2026-06-21-issue-1258-digest-verification.md`
  - `docs/plans/2026-06-22-issue-1258-hub-snapshot-digest.md`
  - `docs/plans/2026-06-22-issue-1258-release-policy-receipts.md`
- Runbook: `docs/runbooks/phase-8-local-install.md`

Issue #1258 calls for a shared artifact integrity receipt in the control-plane schema and operator-visible diagnostics. Current slices persist JSON receipts in worker-owned manifests and registry summaries, but model operation results only expose generic artifact path/byte fields through typed protocol messages. This slice closes that typed-schema gap without changing the actual signature or digest verification semantics.

## Scope

In scope:

- Add `ArtifactIntegrityReceipt` messages to worker and control-plane protocol schemas.
- Add `artifact_integrity` to `QuantizedArtifact` and `ModelOperationArtifact`.
- Regenerate protocol artifacts and descriptors.
- Attach the latest managed download/import `artifact_integrity` receipt to worker `ConvertCompleted.artifact`.
- Project the typed receipt through `ControlPlaneService`.
- Document that typed control-plane operation results now carry the same receipt fields as the persisted worker manifest.

Out of scope:

- Real cryptographic signature verification.
- Remote release-ref fetching.
- Publish-token minimization.
- New desktop visual layouts.
- Changing strict install admission semantics already implemented by worker slices.

## Performance Probes And Metrics

- The new projection reads receipt fields from the already-built manifest payload and does not add file-system scans or network calls.
- Changed-scope metrics:
  - focused Swift control-plane test for model operation projection
  - focused Python maintenance test for worker completed artifact receipt attachment
  - `make proto` / generated artifact drift check
  - changed-scope coverage for touched Python files, target `>=95%`
  - PR-scoped performance report if probes select this scope
  - `git diff --check`

## Files

- Modify: `packages/protocol/schema/worker/v1/maintenance.proto`
  - add `ArtifactIntegrityReceipt` and `QuantizedArtifact.artifact_integrity`
- Modify: `packages/protocol/schema/controlplane/v1/control_plane.proto`
  - add `ArtifactIntegrityReceipt` and `ModelOperationArtifact.artifact_integrity`
- Regenerate:
  - `packages/protocol/python/**`
  - `packages/protocol/swift/**`
  - `packages/protocol/descriptors/melix.pb`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`
  - build typed worker artifacts for managed download/import completion with the current `artifact_integrity` receipt
- Modify: `services/mlx-worker-python/tests/test_managed_artifact_receipts.py`
  - cover the completed worker artifact typed receipt
- Modify: `services/control-plane-swift/Sources/XPCService/ControlPlaneService.swift`
  - project the worker typed receipt into the control-plane typed receipt
- Modify: `services/control-plane-swift/Tests/ControlPlaneTests/ControlPlaneServiceTests.swift`
  - cover control-plane model operation artifact projection
- Modify: `docs/runbooks/phase-8-local-install.md`
  - document the typed protocol projection

## Task 1: Add Failing Typed Projection Tests

- [x] Add a Swift test that returns a worker `ConvertCompleted.artifact.artifact_integrity` from the scripted model-ops client and asserts `response.model.operation.artifact.artifactIntegrity` contains digest, actual digest, checked time, policy fields, and `activation_decision=allowed`.
- [x] Add a Python test that runs a strict managed download with a matching digest and asserts the final `ConvertCompleted.artifact.artifact_integrity` has the same receipt fields as the terminal manifest.
- [x] Run the focused tests and confirm they fail because the typed protocol fields do not exist or are not populated.

## Task 2: Add Protocol Receipt Messages

- [x] Add `ArtifactIntegrityReceipt` to `worker/v1/maintenance.proto` with fields:
  - `status`
  - `verification_mode`
  - `policy_present`
  - `digest`
  - `actual_digest`
  - `checked_at`
  - `failure_reason`
  - `artifact_id`
  - `source_ref`
  - `expected_source_ref`
  - `signature_status`
  - `policy_mode`
  - `activation_decision`
- [x] Add the same message shape to `controlplane/v1/control_plane.proto`.
- [x] Add `artifact_integrity` to `QuantizedArtifact` and `ModelOperationArtifact`.
- [x] Run `make proto`.

## Task 3: Populate Worker Typed Artifacts

- [x] Add a maintenance-core helper that converts a manifest `artifact_integrity` object into `maintenance_pb2.ArtifactIntegrityReceipt`.
- [x] Add a helper that builds a `QuantizedArtifact` for managed download/import completions using the final output path and latest manifest payload.
- [x] Emit that artifact on managed download/import completed events.
- [x] Run the Python focused test until green.

## Task 4: Project Through Control Plane

- [x] Extend `controlPlaneArtifact(from:)` to copy the receipt fields when the worker artifact has `artifactIntegrity`.
- [x] Run the Swift focused test until green.

## Task 5: Docs And Verification

- [x] Update the Phase 8 local install runbook with the typed protocol projection.
- [x] Run focused Python and Swift tests.
- [x] Run `make proto-check`.
- [x] Run changed-scope coverage and PR-scoped performance if selected.
- [x] Run `git diff --check`.
- [x] Commit the focused #1258 schema slice and update PR #2271.
