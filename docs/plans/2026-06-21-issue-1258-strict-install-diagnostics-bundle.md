# Strict Managed Artifact Diagnostics Bundle Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the next executable slice of issue #1258 by making export diagnostics bundles include managed artifact integrity receipts for strict install refusals and verified managed installs.

**Architecture:** Keep receipt production in the Python worker download pipeline and add an export-bundle projection over persisted `melix.download_job.v1` state files. The projection is read-only and flattens the existing `artifact_integrity` receipt into operator-visible diagnostics fields. This slice does not change artifact verification semantics, signing policy, or activation orchestration.

**Tech Stack:** Python worker model-ops state files, benchmark/export bundle utilities, gRPC maintenance service, pytest.

---

## Governing Context

- GitHub issue: `https://github.com/Keith-CY/melix/issues/1258`
- Existing strict preflight plan: `docs/plans/2026-05-25-issue-1258-strict-install-preflight.md`
- Existing partial lifecycle plan: `docs/plans/2026-06-21-managed-artifact-partial-lifecycle.md`
- Runbook: `docs/runbooks/phase-8-local-install.md`

Issue #1258 remains a broad tracking issue. This PR intentionally implements the diagnostics-bundle visibility slice and leaves release signing, publish-token minimization, async installer UX, and desktop surfaces for later slices.

## Performance Probes And Metrics

- Export probe: `build_export_bundle(jobs_root)` should scan model-ops state files only at export time and avoid changing download hot-path behavior.
- Runtime probe: no download pipeline hot-path probe is expected to select this read-only export projection.
- Metrics to record in PR evidence:
  - focused pytest result for benchmark export diagnostics tests
  - changed-scope coverage for touched Python files, target `>=95%`
  - PR-scoped performance report, expected `Status: ok` or no selected probes for this slice
  - `git diff --check`

## Files

- Modify: `services/mlx-worker-python/worker/productization/benchmark_export.py`
  - collect persisted model-ops download state files
  - flatten `artifact_integrity` into `managed_artifact_integrity_receipts[]`
  - preserve deterministic ordering and tolerate unreadable or unrelated state files
- Modify: `services/mlx-worker-python/tests/test_benchmark_export.py`
  - add bundle-level failing coverage for strict refusal diagnostics fields
- Modify: `docs/runbooks/phase-8-local-install.md`
  - document the export-bundle receipt fields and current boundaries

## Task 1: Add Failing Export Coverage

- [x] Add a benchmark export test that writes a strict failed `download.state.json` under `model-ops` and expects `managed_artifact_integrity_receipts[]`.
- [x] Assert each exported receipt includes `verification_mode`, `policy_present`, `digest`, `checked_at`, and `failure_reason`.
- [x] Add bundle write coverage proving `write_export_bundle(...)` persists managed artifact diagnostics.
- [x] Run the focused tests and confirm they fail because export bundles do not yet collect managed artifact integrity receipts.

## Task 2: Implement Read-Only Receipt Projection

- [x] Add a model-ops artifact collector to `benchmark_export.py`.
- [x] Scan `download.state.json` and `*.state.json` files under the model-ops job root.
- [x] Include only JSON objects with `operation=download` and an object-valued `artifact_integrity` receipt.
- [x] Flatten receipt data into deterministic rows with job identity, operation identity, activation decision, status, output path, and state path.
- [x] Keep unreadable, malformed, or unrelated state files non-fatal.

## Task 3: Docs And Verification

- [x] Update the Phase 8 local install runbook with the export-bundle diagnostics fields.
- [x] Run focused pytest until green.
- [x] Run changed-scope coverage for the touched Python files and verify `>=95%`.
- [x] Run PR-scoped performance reporting or record `N/A` if no probe selects this scope.
- [x] Run `git diff --check`.
- [x] Validate the PR body with `scripts/validate_pr_evidence.py --body-file`.
- [ ] Commit the focused slice and open a PR against `main`.
