# Managed Artifact Operation Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add narrow managed artifact operation receipts for download/install jobs so operators can distinguish scoped duplicates, in-progress deadlines, failures, and activation eligibility.

**Architecture:** Download manifests remain the worker-owned receipt source of truth. `DownloadPipeline` emits stable operation metadata, timeout/retry fields, and a minimal `artifact_integrity` receipt; `ModelOpsJobRegistry` exposes those fields in download snapshots and provides a strict activation fixture helper; `MaintenanceCore` suppresses duplicate managed artifact operations by scoped operation identity before creating a new job. This slice intentionally avoids real asynchronous installation, release signing, publish tokens, and desktop UI.

**Tech Stack:** Python worker, protobuf request `ext` metadata, JSON manifests, pytest.

---

## Scope

In scope:

- Stable manifest fields: `operation_id`, `target_scope`, `operation_kind`, `attempts`, `timeout_ms`, `retry_after_ms`, `last_error`, and `artifact_integrity`.
- Deterministic test knobs for local deadlines: `test_request_deadline_ms` and `test_slow_in_progress_ms`.
- Duplicate suppression for managed download/install requests with the same scoped operation identity.
- Strict activation fixture helper that requires a completed receipt with `artifact_integrity.status == "passed"`.
- Runbook documentation for the receipt contract.
- Reviewer follow-up: in-progress managed artifact jobs must publish their scoped operation receipt before the
  long-running pipeline starts, duplicate suppression must use the same eligibility boundary as receipt emission,
  local fallback scopes must canonicalize source paths, and strict activation receipts must require complete
  operation and integrity evidence.

Out of scope:

- Full signature verification.
- Real async installer orchestration.
- Release publish tokens.
- Desktop UI.

## Tasks

### Task 1: Red Tests

**Files:**

- Modify: `services/mlx-worker-python/tests/test_download_pipeline_unit.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`
- Modify: `services/mlx-worker-python/tests/test_model_ops_job_registry.py`

- [x] Add failing tests for stable receipt fields and in-progress timeout receipts.
- [x] Add failing tests for duplicate suppression by `operation_id` and `target_scope`.
- [x] Add failing tests for strict activation receipt eligibility and registry snapshot fields.
- [x] Run the focused red tests and confirm they fail for missing behavior, not syntax errors.

### Task 2: Receipt Emission

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/download_pipeline.py`

- [x] Add deterministic operation identity and target scope helpers.
- [x] Include receipt fields in standard and managed Hub download manifests.
- [x] Emit an `in_progress` receipt when the test deadline knob expires while progress is still being made.
- [x] Keep terminal failure handling separate from `in_progress` receipts.

### Task 3: Registry And Duplicate Suppression

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`
- Modify: `services/mlx-worker-python/worker/engine/maintenance_core.py`

- [x] Expose receipt fields in the `downloads` registry snapshot.
- [x] Add a registry lookup for scoped managed artifact operations.
- [x] Suppress duplicate managed installs before a new job is created.
- [x] Add the strict activation fixture helper that only passes completed receipts with passed artifact integrity.

### Task 4: Documentation And Verification

**Files:**

- Modify: `docs/runbooks/phase-8-local-install.md`

- [x] Document operation receipt fields, duplicate suppression, in-progress deadline semantics, and strict activation fixture behavior.
- [x] Run focused red/green tests.
- [x] Run the required combined pytest command.
- [x] Run a coverage command for the changed Python scope if feasible.
- [x] Run `git diff --check`.
- [x] Commit one focused change.
