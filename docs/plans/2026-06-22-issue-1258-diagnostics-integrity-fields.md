# Managed Artifact Integrity Diagnostics Summary

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose normalized managed artifact integrity fields in model-ops download diagnostics rows.

**Architecture:** `ModelOpsJobRegistry.snapshot()` is the worker-side diagnostics boundary for model-ops jobs and registry snapshots. Download rows already preserve the full `artifact_integrity` receipt for compatibility. This slice adds a stable `artifact_integrity_summary` object with the fields required by the strict install policy so diagnostics consumers do not need to understand every historical receipt shape or malformed manifest.

**Tech Stack:** Python worker, JSON model-ops manifests, pytest.

---

## Scope

In scope:

- Download rows in `ModelOpsJobRegistry.snapshot()["downloads"]`.
- A stable `artifact_integrity_summary` object with `status`, `verification_mode`, `policy_present`, `digest`, `actual_digest`, `checked_at`, and `failure_reason`.
- Default values for missing or malformed receipt payloads: empty strings, `policy_present=false`, and no exception.
- Preservation of the existing full `artifact_integrity` payload and `artifact_integrity_status` field.
- Runbook documentation for the diagnostics field contract.

Out of scope:

- New protobuf fields.
- Desktop UI rendering changes.
- Release signatures or external trust policy validation.
- Changing the strict activation predicate.

## Tasks

### Task 1: Red Tests

**Files:**

- Modify: `services/mlx-worker-python/tests/test_model_ops_job_registry.py`

- [x] Add a failing unit test assertion proving completed download rows expose the normalized `artifact_integrity_summary`.
- [x] Add a failing malformed-receipt assertion proving the summary shape remains stable when `artifact_integrity` is not an object.
- [x] Run the focused tests and confirm they fail because the summary field is not implemented yet.

### Task 2: Diagnostics Summary Implementation

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`

- [x] Add a small helper that normalizes artifact integrity receipts into the stable summary shape.
- [x] Include `artifact_integrity_summary` on every download row.
- [x] Derive `artifact_integrity_status` from the normalized summary while preserving the existing full receipt payload.
- [x] Preserve existing snapshot behavior for non-download jobs.

### Task 3: Documentation And Verification

**Files:**

- Modify: `docs/runbooks/phase-8-local-install.md`

- [x] Document the download diagnostics summary fields.
- [x] Run focused red/green tests.
- [x] Run related registry snapshot tests.
- [x] Run changed-scope coverage for touched Python files.
- [x] Run PR-scoped performance for the changed scope and require `Status: ok`.
- [x] Run `git diff --check`.
- [ ] Commit one focused #1258 slice and update the PR.
