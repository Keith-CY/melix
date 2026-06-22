# Managed Artifact Release Policy Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend strict managed artifact receipts with release reference and signature policy evidence before activation.

**Architecture:** `DownloadPipeline` remains the worker-owned managed artifact trust boundary. This slice adds fixture-shaped policy fields to the existing `artifact_integrity` receipt and makes strict mode reject release reference or signature policy mismatches before activation. The change intentionally does not add real cryptographic signing, publish-token changes, async installer orchestration, or desktop UI.

**Tech Stack:** Python worker model-ops download pipeline, JSON download state manifests, pytest, Phase 8 local install runbook.

---

## Governing Context

- GitHub issue: `https://github.com/Keith-CY/melix/issues/1258`
- Existing strict preflight plan: `docs/plans/2026-05-25-issue-1258-strict-install-preflight.md`
- Existing digest verification plans:
  - `docs/plans/2026-06-21-issue-1258-digest-verification.md`
  - `docs/plans/2026-06-22-issue-1258-hub-snapshot-digest.md`
- Existing diagnostics plans:
  - `docs/plans/2026-06-21-issue-1258-strict-install-diagnostics-bundle.md`
  - `docs/plans/2026-06-22-issue-1258-diagnostics-integrity-fields.md`
- Runbook: `docs/runbooks/phase-8-local-install.md`

Issue #1258 still calls out signed or policy-verified bundles, release reference validation, and `{artifact_id, source_ref, digest, signature_status, policy_mode, activation_decision}` evidence. Prior slices intentionally left signature verification and release-ref validation out of scope. This slice closes the first executable boundary by recording policy-shaped evidence and failing closed in strict mode when the declared policy cannot be satisfied.

## Scope

In scope:

- Optional request metadata:
  - `melix.artifact_id`
  - `melix.source_ref`
  - `melix.expected_source_ref`
  - `melix.signature_status`
  - `melix.policy_mode`
- `artifact_integrity` receipt fields:
  - `artifact_id`
  - `source_ref`
  - `expected_source_ref`
  - `signature_status`
  - `policy_mode`
  - `activation_decision`
- Strict-mode refusal before activation when:
  - `expected_source_ref` is present and differs from `source_ref`
  - `policy_mode=signed` and `signature_status` is not `verified`
- Typed `ModelOperationError` codes:
  - `artifact_release_ref_mismatch`
  - `artifact_signature_required`
- Registry diagnostics summary projection for the new policy fields.
- Runbook documentation for the current fixture-shaped policy boundary.

Out of scope:

- Real cryptographic signature verification.
- Fetching release refs from remote hosting APIs.
- Publish-token minimization.
- Desktop UI.
- Async install orchestration.

## Performance Probes And Metrics

- Download hot path: policy receipt fields must be derived from already-present `ext` metadata and must not add filesystem scans or network calls.
- Changed-scope metrics:
  - focused pytest for `test_download_pipeline_unit.py` and `test_model_ops_job_registry.py`
  - changed-scope coverage for `download_pipeline.py`, `job_registry.py`, and touched tests, target `>=95%`
  - PR-scoped performance report; expected `Status: ok`
  - `git diff --check`

## Files

- Modify: `services/mlx-worker-python/tests/test_download_pipeline_unit.py`
  - add red coverage for strict release-ref mismatch refusal, strict signature-required refusal, and verified signed-policy success
- Modify: `services/mlx-worker-python/tests/test_model_ops_job_registry.py`
  - add red coverage proving `artifact_integrity_summary` projects release policy fields
- Modify: `services/mlx-worker-python/worker/model_ops/download_pipeline.py`
  - enrich `artifact_integrity` receipt with release policy fields
  - add strict policy pre-activation checks for direct downloads and managed Hub imports
- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`
  - expose release policy fields in the normalized integrity summary
- Modify: `docs/runbooks/phase-8-local-install.md`
  - document the release policy receipt fields and strict refusal semantics

## Task 1: Add Failing Direct Download Policy Tests

- [x] Add `test_strict_managed_download_rejects_release_ref_mismatch_before_activation`.
- [x] Build a strict managed request with a correct SHA-256 digest, `melix.source_ref=refs/tags/v1.0.0`, and `melix.expected_source_ref=refs/tags/v1.0.1`.
- [x] Assert the pipeline raises `ModelOperationError(code="artifact_release_ref_mismatch")`.
- [x] Assert `download.state.json` has `artifact_integrity.failure_reason=release_ref_mismatch`, `activation_decision=blocked`, the source-ref fields, and no activated final artifact.
- [x] Add `test_strict_managed_download_rejects_unverified_signature_policy_before_activation`.
- [x] Build a strict managed request with a correct SHA-256 digest, `melix.policy_mode=signed`, and `melix.signature_status=unsigned`.
- [x] Assert the pipeline raises `ModelOperationError(code="artifact_signature_required")`.
- [x] Assert the failed state receipt records `failure_reason=signature_required`, `policy_mode=signed`, `signature_status=unsigned`, and `activation_decision=blocked`.
- [x] Run both tests and confirm they fail because the policy checks do not exist yet.

## Task 2: Add Failing Success And Registry Projection Tests

- [x] Add `test_strict_managed_download_records_verified_release_policy_receipt`.
- [x] Build a strict managed request with a correct SHA-256 digest, matching `source_ref` and `expected_source_ref`, `melix.policy_mode=signed`, `melix.signature_status=verified`, and `melix.artifact_id=artifact-demo`.
- [x] Assert the completed receipt has `activation_decision=allowed`, the release policy fields, and `status=passed`.
- [x] Extend `test_download_registry_snapshot_exposes_operation_receipt_fields` with the same `artifact_integrity` fields.
- [x] Assert `artifact_integrity_summary` exposes `artifact_id`, `source_ref`, `expected_source_ref`, `signature_status`, `policy_mode`, and `activation_decision`.
- [x] Run the tests and confirm they fail because summaries do not project the fields yet.

## Task 3: Implement Release Policy Receipt Fields

- [x] Add `_artifact_release_policy_receipt(ext, status)` that returns the six release policy fields.
- [x] Merge the policy fields into `_artifact_integrity_receipt(...)` for all receipt statuses.
- [x] Derive `activation_decision` as:
  - `blocked` when `status=failed`
  - `allowed` when `status=passed`
  - `pending` otherwise
- [x] Preserve empty-string defaults for absent optional metadata.
- [x] Re-run the success test and registry projection test; expect policy fields to appear, but strict refusal tests may still fail.

## Task 4: Implement Strict Policy Refusals

- [x] Add `_raise_if_strict_release_policy_failed(manifest_payload, partial_path, ext)`.
- [x] If strict mode is disabled, return without changes.
- [x] If `expected_source_ref` is present and does not equal `source_ref`, write a failed state payload with `failure_reason=release_ref_mismatch`, `activation_decision=blocked`, and raise `artifact_release_ref_mismatch`.
- [x] If `policy_mode=signed` and `signature_status != verified`, write a failed state payload with `failure_reason=signature_required`, `activation_decision=blocked`, and raise `artifact_signature_required`.
- [x] Call the helper after digest verification and before direct `os.replace(...)`.
- [x] Call the helper for managed Hub import manifests before returning a completed activated result.
- [x] Run focused tests until green.

## Task 5: Project Policy Fields Through Diagnostics Summary

- [x] Extend `_artifact_integrity_summary(...)` in `job_registry.py` with the six release policy fields.
- [x] Keep missing or malformed receipt payload defaults as empty strings.
- [x] Run the registry-focused tests until green.

## Task 6: Docs And Verification

- [x] Update `docs/runbooks/phase-8-local-install.md` with the release policy receipt fields.
- [x] State that the current boundary is metadata/fixture-shaped policy evidence, not real cryptographic signature verification.
- [x] Run focused pytest:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_download_pipeline_unit.py \
  services/mlx-worker-python/tests/test_model_ops_job_registry.py
```

- [x] Run changed-scope coverage and verify `>=95%`.
- [x] Run PR-scoped performance report and require `Status: ok`.
- [x] Run `git diff --check`.
- [ ] Commit one focused #1258 slice and open a PR.
