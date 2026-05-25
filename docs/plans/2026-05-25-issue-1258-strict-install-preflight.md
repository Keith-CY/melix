# Strict Managed Artifact Install Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make strict managed artifact installs fail closed before local activation when the request lacks immutable integrity metadata.

**Architecture:** `DownloadPipeline` remains the worker-owned receipt boundary for managed downloads and Hub imports. This slice adds a small strict-mode preflight to that boundary, emits a failed `artifact_integrity` receipt with a copyable refusal reason, and lets `MaintenanceCore` persist the failed receipt on the existing download job path. The change intentionally avoids release signing, async installers, desktop UI, and unrelated launch/profile cleanup.

**Tech Stack:** Python worker, protobuf request `ext` metadata, JSON receipts, pytest.

---

## Scope

In scope:

- `melix.strict_install_mode=true` and `melix.install_mode=strict` request parsing for managed artifact receipt paths.
- Strict-mode refusal when no digest is present in `melix.artifact_digest`, `artifact_digest`, or `sha256`.
- A failed `artifact_integrity` receipt with `verification_mode`, `policy_present=false`, empty `digest`, `checked_at`, `failure_reason=missing_artifact_digest`, and `status=failed`.
- A typed `ModelOperationError` code `artifact_integrity_required` with `state_json` so diagnostics and duplicate-suppression state see the same receipt.
- Runbook documentation for the strict preflight flag and its current digest-only boundary.

Out of scope:

- Signature verification and release-ref validation.
- Real install/upgrade job orchestration.
- Desktop status UI.
- Any #42, #350, #1384, or #1483 behavior.

## Tasks

### Task 1: Red Tests

**Files:**

- Modify: `services/mlx-worker-python/tests/test_download_pipeline_unit.py`
- Modify: `services/mlx-worker-python/tests/test_maintenance_service.py`

- [x] Add a `DownloadPipeline` unit test proving strict managed downloads without a digest raise `artifact_integrity_required`, write a failed receipt, and do not materialize the output artifact.
- [x] Add a service-level test proving `ConvertModel` persists and emits the failed receipt when `generate_manifest=True`.
- [x] Run the focused tests and confirm they fail because strict mode is not implemented yet.

### Task 2: Strict Preflight

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/download_pipeline.py`

- [x] Add helpers for strict-mode parsing and digest lookup.
- [x] Before copying bytes or materializing a managed Hub snapshot, build a failed receipt and raise `ModelOperationError(code="artifact_integrity_required")` when strict mode is enabled without a digest.
- [x] Keep non-strict managed downloads warning-compatible by preserving the existing pending/passed receipt behavior.

### Task 3: Documentation And Verification

**Files:**

- Modify: `docs/runbooks/phase-8-local-install.md`

- [x] Document `melix.strict_install_mode=true` / `melix.install_mode=strict`.
- [x] Run the red/green focused pytest command.
- [x] Run changed-scope coverage for the touched Python files.
- [x] Run PR-scoped performance for the changed scope and require `Status: ok`.
- [x] Run `git diff --check`.
- [ ] Commit one focused #1258 slice.
