# Managed Artifact Digest Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make strict managed artifact installs verify declared SHA-256 digests against staged bytes before activation.

**Architecture:** `DownloadPipeline` remains the worker-owned trust boundary for managed downloads. This slice adds a final SHA-256 check for direct worker-owned downloads after bytes are fully staged in the partial file and before `os.replace(...)` activates the artifact. The existing `artifact_integrity` receipt records the declared digest, computed digest, check timestamp, and refusal reason. This intentionally does not add release signatures, async installers, desktop UI, or Hub snapshot directory hashing.

**Tech Stack:** Python worker, protobuf request `ext` metadata, JSON download receipts, pytest.

---

## Scope

In scope:

- Strict managed direct downloads with `melix.strict_install_mode=true` or `melix.install_mode=strict`.
- Declared digest formats `sha256:<64 hex>` and bare `<64 hex>`.
- Fail-closed activation when the staged partial file digest differs from the declared digest.
- Strict-mode refusal for declared digest policies that are present but not verifiable as SHA-256 in this slice.
- Failed receipt fields: `artifact_integrity.status=failed`, `failure_reason=digest_mismatch`, declared `digest`, `actual_digest`, real `checked_at`, `last_error=digest_mismatch`, `activated=false`, and no final artifact materialized.
- Passed receipt fields: declared `digest`, matching `actual_digest`, real `checked_at`, `policy_present=true`, `status=passed`, and `activated=true`.
- Runbook documentation for the digest verification boundary.

Out of scope:

- Signature verification and release-reference validation.
- Directory snapshot digesting for managed Hub repo imports.
- Async installer orchestration.
- Desktop UI and control-plane schema changes.

## Tasks

### Task 1: Red Tests

**Files:**

- Modify: `services/mlx-worker-python/tests/test_download_pipeline_unit.py`

- [x] Add a failing strict managed download test where the declared SHA-256 matches staged bytes; the final receipt includes `actual_digest`, a non-placeholder `checked_at`, and `status=passed`.
- [x] Add a failing strict managed download test where the declared SHA-256 mismatches staged bytes; the pipeline raises `ModelOperationError(code="artifact_integrity_mismatch")`, keeps the final artifact inactive, leaves the partial for diagnosis/resume, writes a failed state receipt, and records `failure_reason=digest_mismatch`.
- [x] Add a failing helper-format test proving bare 64-hex SHA-256 values normalize to `sha256:<hex>` in receipts.
- [x] Add a failing strict managed download test where an unsupported declared digest policy refuses activation with `ModelOperationError(code="artifact_integrity_unsupported")`.
- [x] Run the focused tests and confirm they fail because digest verification is not implemented yet.

### Task 2: Digest Verification

**Files:**

- Modify: `services/mlx-worker-python/worker/model_ops/download_pipeline.py`

- [x] Add a file SHA-256 helper that streams the partial file without loading it all into memory.
- [x] Normalize declared digests from `melix.artifact_digest`, `artifact_digest`, or `sha256`; preserve unknown formats as declared policy strings but only verify SHA-256 formats in this slice.
- [x] Add `_verified_artifact_integrity_receipt(...)` for passed and failed direct-download terminal receipts.
- [x] Before `os.replace(...)`, compare the staged partial digest with the declared digest in strict mode and raise `artifact_integrity_mismatch` on mismatch.
- [x] In strict mode, reject declared digest policies that are not SHA-256-verifiable before activation.
- [x] Preserve existing missing-digest strict preflight behavior.

### Task 3: Documentation And Verification

**Files:**

- Modify: `docs/runbooks/phase-8-local-install.md`

- [x] Document that strict direct downloads now verify SHA-256 before activation.
- [x] Run focused red/green tests.
- [x] Run changed-scope coverage for touched Python files.
- [x] Run PR-scoped performance for the changed scope and require `Status: ok`.
- [x] Run `git diff --check`.
- [ ] Commit one focused #1258 slice and open a PR.
