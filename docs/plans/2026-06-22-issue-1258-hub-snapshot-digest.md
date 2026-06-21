# Managed Hub Snapshot Digest Verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make strict managed Hub repository imports verify a deterministic directory snapshot digest before activation.

**Architecture:** `DownloadPipeline` remains the worker-owned managed artifact trust boundary. Direct file downloads already verify staged bytes before `os.replace(...)`; this slice adds the matching strict-mode boundary for managed Hub directory snapshots by hashing the resolved snapshot tree before the snapshot is reported as activated. The digest is a deterministic SHA-256 over each regular file's repo-relative path, file size, and bytes, with symlinks and directories excluded from the hash surface for this slice.

**Tech Stack:** Python worker, protobuf request `ext` metadata, JSON download receipts, pytest.

---

## Scope

In scope:

- Strict managed Hub repo imports with `melix.strict_install_mode=true` or `melix.install_mode=strict`.
- Declared digest formats `sha256:<64 hex>` and bare `<64 hex>`.
- A deterministic directory snapshot digest computed before the import is marked completed/activated.
- Failed receipt fields: `artifact_integrity.status=failed`, `failure_reason=digest_mismatch`, declared `digest`, computed `actual_digest`, real `checked_at`, `last_error=digest_mismatch`, `activated=false`, and no completed output event.
- Passed receipt fields: declared `digest`, matching `actual_digest`, real `checked_at`, `policy_present=true`, `status=passed`, and `activated=true`.
- Runbook documentation for the managed Hub snapshot digest boundary and the digest algorithm.

Out of scope:

- Signature verification and release-reference validation.
- Signed manifest policy.
- Async installer orchestration.
- Desktop UI and control-plane schema changes.
- Hashing symlink targets or non-regular file metadata.

## Tasks

### Task 1: Red Tests

**Files:**

- Modify: `services/mlx-worker-python/tests/test_download_pipeline_unit.py`
- Modify: `services/mlx-worker-python/tests/test_managed_artifact_receipts.py`

- [x] Add a failing unit test proving a strict managed Hub import with a matching declared directory digest completes, records `actual_digest`, and sets `activated=true`.
- [x] Add a failing unit test proving a strict managed Hub import with a mismatched declared directory digest raises `ModelOperationError(code="artifact_integrity_mismatch")`, records a failed receipt, and sets `activated=false`.
- [x] Add a service-level test proving `ConvertModel` persists and emits the failed receipt for a mismatched managed Hub snapshot digest.
- [x] Run the focused tests and confirm they fail because directory snapshot digesting is not implemented yet.

### Task 2: Directory Snapshot Digest Verification

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/download_pipeline.py`

- [x] Add a deterministic directory SHA-256 helper that streams files in sorted repo-relative path order and binds path names plus file sizes before bytes.
- [x] Thread verified `artifact_integrity` receipts into `_build_managed_import_manifest_json(...)`.
- [x] For strict mode, reject unsupported declared digest policies and mismatches before returning a completed managed Hub import result.
- [x] Preserve existing strict missing-digest preflight and non-strict managed import behavior.

### Task 3: Documentation And Verification

**Files:**

- Modify: `docs/runbooks/phase-8-local-install.md`

- [x] Document that strict managed Hub imports verify deterministic directory snapshot SHA-256 before activation.
- [x] Run focused red/green tests.
- [x] Run related Python tests for download receipts and maintenance service managed import paths.
- [x] Run changed-scope coverage for touched Python files.
- [x] Run PR-scoped performance for the changed scope and require `Status: ok`.
- [x] Run `git diff --check`.
- [ ] Commit one focused #1258 slice and update/open the PR.
