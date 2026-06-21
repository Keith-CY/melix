# Managed Artifact Partial Lifecycle Receipt Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the next executable slice of issue #1258 by making managed download receipts prove whether partial artifact bytes were kept for resume, removed as stale, or rejected before activation.

**Architecture:** Keep the trust boundary in the Python worker download pipeline because it owns artifact materialization and partial files. Extend the existing `melix.download_job.v1` state payload with a small partial-file lifecycle section and surface those fields through the existing model-ops download registry. Do not introduce signing infrastructure, desktop UI, or new protocol messages in this slice.

**Tech Stack:** Python worker model-ops code, pytest, deterministic local download fixtures, Phase 8 local install runbook, PR-scoped performance tooling.

---

## Governing Context

- GitHub issue: `https://github.com/Keith-CY/melix/issues/1258`
- Existing runbook: `docs/runbooks/phase-8-local-install.md`
- Existing completed download plan: `docs/plans/2026-03-30-m8-4-resumable-downloads-retries-and-mirrors.md`

Issue #1258 is a broad tracking issue. This PR intentionally implements the current narrow slice for partial lifecycle receipts and leaves signature policy, publish-token minimization, desktop UI, and transport acceleration for later PRs.

## Performance Probes And Metrics

- Runtime hot-path probe: `download-pipeline-directory-size-single-stat` covers the per-snapshot manifest path. Lifecycle fields must not add per-snapshot filesystem probes and should stay on managed/operation receipt payloads so plain-download progress remains non-regressive.
- Evidence probe: `scripts/m8_download_smoke.py --json` must include stale-partial lifecycle checks.
- Metrics to record in PR evidence:
  - focused pytest result for `test_download_pipeline_unit.py` and `test_managed_artifact_receipts.py`
  - deterministic smoke result for `scripts/m8_download_smoke.py --json`
  - changed-scope coverage for touched Python files, target `>=95%`
  - PR-scoped performance report, expected no selected probes or no regressions unless a matching probe exists

## Files

- Modify: `services/mlx-worker-python/worker/model_ops/download_pipeline.py`
  - add stale partial sweep before resume calculation
  - add lifecycle fields to all download state payloads
  - distinguish cancel-kept resumable partials from stall-kept partials
- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`
  - project lifecycle fields into `snapshot()["downloads"]`
  - base `resume_ready` on explicit receipt data when present
- Modify: `services/mlx-worker-python/tests/test_download_pipeline_unit.py`
  - add failing tests for stale partial removal and terminal cancel/stall lifecycle fields
- Modify: `services/mlx-worker-python/tests/test_managed_artifact_receipts.py` or `services/mlx-worker-python/tests/test_maintenance_service.py`
  - add registry-level assertion that stale partial lifecycle is operator-visible
- Modify: `scripts/m8_download_smoke.py`
  - add deterministic stale partial fixture
- Modify: `docs/runbooks/phase-8-local-install.md`
  - document lifecycle fields and stale partial behavior

## Task 1: Add Failing Unit Coverage

- [ ] Add a test proving an old `download.artifact.partial` is removed before a managed download resumes.
- [ ] Assert the state payload records `partial_bytes`, `partial_age_ms`, `resume_eligible`, `stale_partial_removed`, `partial_lifecycle`, and `activated`.
- [ ] Add terminal receipt assertions for cancelled and stalled downloads so cancel and stall no longer look the same in receipt data.
- [ ] Run focused pytest and confirm the new tests fail for missing fields or stale partial behavior.

## Task 2: Implement Pipeline Receipt Fields

- [ ] Add partial lifecycle derivation in `DownloadPipeline.run` before `_resume_from_bytes`.
- [ ] Preserve recent partial files for resume, remove empty or oversized invalid partial files, and remove aged partial files older than configured `melix.stale_partial_after_ms` / `stale_partial_after_ms`.
- [ ] Include lifecycle fields in managed/operation-receipt prepare, progress, terminal, strict-preflight, and managed hub import payloads.
- [ ] Keep existing plain downloads working without adding managed artifact lifecycle fields or per-snapshot filesystem probes.
- [ ] Run focused pytest until green.

## Task 3: Surface Operator Registry State

- [ ] Project the lifecycle fields from job manifests into `ModelOpsJobRegistry._download_registry`.
- [ ] Update `resume_ready` to use explicit `resume_eligible` when present.
- [ ] Add or update service-level tests so diagnostics/download snapshots expose the stale-removal result.
- [ ] Run focused registry tests until green.

## Task 4: Update Smoke And Docs

- [ ] Extend `scripts/m8_download_smoke.py` with a stale partial fixture.
- [ ] Update `docs/runbooks/phase-8-local-install.md` with the lifecycle receipt fields and behavior.
- [ ] Run the smoke command and focused tests.

## Task 5: Verification And PR Evidence

- [ ] Run `git diff --check`.
- [ ] Run focused pytest for the touched Python tests.
- [ ] Run changed-scope coverage for the touched Python scope and verify `>=95%`.
- [ ] Run the deterministic download smoke.
- [ ] Run PR-scoped performance reporting or record `N/A` if no probe selects this scope.
- [ ] Validate the PR body with `scripts/validate_pr_evidence.py --body-file`.
- [ ] Commit the focused slice and open a PR against `main`.
