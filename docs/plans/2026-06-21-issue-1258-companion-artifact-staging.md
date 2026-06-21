# Managed Companion Artifact Staging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the managed artifact trust boundary so a primary model artifact can require companion files or directories before activation.

**Architecture:** `DownloadPipeline` remains the worker-owned receipt boundary for managed downloads and Hub imports. This slice adds a small manifest-driven companion resolver that searches the configured managed artifact root and the primary artifact directory, expands directory companions file-by-file for receipt evidence, and blocks strict managed installs before activation when required companions are missing. The change intentionally avoids release signing, real network transport changes, desktop UI, and broad model registry rewrites.

**Tech Stack:** Python worker, protobuf request `ext` metadata, JSON state manifests, pytest.

---

## Scope

In scope:

- A test-only but production-shaped companion declaration carried through `melix.companion_manifest`.
- Companion declarations with `path`, `kind=file|directory`, and `required=true|false`.
- Search order for relative companion paths:
  1. the primary artifact directory
  2. `melix.managed_root`
- Receipt fields: `primary_artifact`, `companion_artifacts`, `missing_required`, `staged_file_count`, and `verification_result`.
- Strict-mode refusal with `ModelOperationError(code="artifact_companion_required")` before the final artifact is activated.
- Registry projection for the companion receipt.
- Runbook documentation for the current companion staging boundary.

Out of scope:

- Signature verification or release-ref validation.
- Archive extraction orchestration.
- Desktop UI.
- Changing ordinary non-managed download behavior.

## Tasks

### Task 1: Red Tests

**Files:**

- Modify: `services/mlx-worker-python/tests/test_download_pipeline_unit.py`
- Modify: `services/mlx-worker-python/tests/test_model_ops_job_registry.py`

- [x] Add a failing strict managed download test where a primary artifact declares a required file companion and a required directory companion; the final receipt lists the primary, both companions, expanded directory file count, no missing required companions, and `verification_result=passed`.
- [x] Add a failing strict managed download test where a required companion is missing; the pipeline raises `artifact_companion_required`, keeps the final artifact inactive, writes `download.state.json`, and records `verification_result=failed`.
- [x] Add a failing registry snapshot test that projects `artifact_companions_status`, `artifact_companions`, and `missing_required_companions`.
- [x] Run the focused tests and confirm they fail because the companion receipt does not exist yet.

### Task 2: Companion Resolver

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/download_pipeline.py`

- [x] Add `_companion_manifest(ext)` parsing for JSON arrays from `melix.companion_manifest`.
- [x] Add `_resolve_companion_artifacts(primary_artifact, ext)` that resolves relative paths against the primary artifact directory first, then `melix.managed_root`.
- [x] Expand directory companions into stable file lists and byte counts.
- [x] Add `_artifact_companions_receipt(...)` and include it in managed operation manifests.
- [x] Raise `artifact_companion_required` in strict mode when `missing_required` is non-empty before `os.replace(...)` activates the final artifact.

### Task 3: Registry Projection

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`

- [x] Normalize non-dict companion receipts to `{}`.
- [x] Project `artifact_companions`, `artifact_companions_status`, and `missing_required_companions` in the download registry snapshot.

### Task 4: Documentation And Verification

**Files:**

- Modify: `docs/runbooks/phase-8-local-install.md`

- [x] Document the companion declaration and receipt fields.
- [x] Run focused red/green tests.
- [x] Run changed-scope coverage for the touched Python files.
- [x] Run PR-scoped performance for the changed scope and require `Status: ok`.
- [x] Run `git diff --check`.
- [ ] Commit one focused #1258 slice.
