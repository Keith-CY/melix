# Artifact Transport Receipts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend issue #1258 managed download evidence with transport and byte-progress receipts before activation.

**Architecture:** Keep download state production in `DownloadPipeline`, attach a nested `artifact_transport_receipt` to the same `melix.download_job.v1` manifests that already carry `artifact_integrity`, and project the receipt through `ModelOpsJobRegistry` snapshots for operator/debug surfaces. This slice does not change real network defaults, release signing, async installers, or desktop UI; it makes the current deterministic local transfer boundary prove requested/effective transport, fallback, monotonic bytes, empty-body rejection, and integrity acceptance.

**Tech Stack:** Python worker model-ops download pipeline, JSON manifests, pytest, Phase 8 local install runbook.

---

## Governing Context

- GitHub issue: `https://github.com/Keith-CY/melix/issues/1258`
- Watch finding, 2026-06-18: fast artifact transport with explicit graceful fallback.
- Watch finding, 2026-06-19: artifact transports need byte-progress and empty-body integrity receipts.
- Existing strict preflight plan: `docs/plans/2026-05-25-issue-1258-strict-install-preflight.md`
- Existing operation receipt plan: `docs/plans/2026-05-24-issue-1258-managed-artifact-operation-receipts.md`
- Runbook: `docs/runbooks/phase-8-local-install.md`

## Performance Probes And Metrics

- Download hot path: the receipt must reuse already-computed byte counters and simple ext parsing. It must not introduce a filesystem scan, JSON parse loop, or network probe inside chunk processing.
- Changed-scope metrics:
  - focused pytest for `test_download_pipeline_unit.py`, `test_model_ops_job_registry.py`, and `test_managed_artifact_receipts.py`
  - changed-scope coverage for `download_pipeline.py`, `job_registry.py`, and touched tests, target `>=95%`
  - PR-scoped performance report; expected `Status: ok` or no selected probes
  - `git diff --check`

## Files

- Modify: `services/mlx-worker-python/tests/test_download_pipeline_unit.py`
  - add red coverage for transport resolver fields, monotonic byte progress, explicit fallback, and empty-body rejection
- Modify: `services/mlx-worker-python/tests/test_model_ops_job_registry.py`
  - add red coverage proving `artifact_transport_receipt` is exposed in download snapshots and malformed values collapse to `{}`
- Modify: `services/mlx-worker-python/worker/model_ops/download_pipeline.py`
  - add deterministic receipt builder and transport resolver
  - attach `artifact_transport_receipt` to managed operation manifests
  - reject unknown-size empty bodies before caching/activation
- Modify: `services/mlx-worker-python/worker/model_ops/job_registry.py`
  - expose the nested transport receipt and `artifact_transport_status`
- Modify: `docs/runbooks/phase-8-local-install.md`
  - document transport receipt fields and current fixture boundary

## Task 1: Add Failing Download Receipt Tests

- [x] Add a test named `test_managed_download_manifest_records_transport_receipt_progress` that downloads a 6-byte fixture with `chunk_bytes=2`, `melix.target_scope`, `melix.operation_kind`, `melix.requested_transport=parallel_chunked`, and `melix.transport_helper_available=false`.
- [x] Assert the first download snapshot records `artifact_transport_receipt.written_bytes == 2`, the final snapshot records `written_bytes == planned_bytes == 6`, and the written byte sequence across download snapshots is monotonic.
- [x] Assert the final receipt includes:
  - `requested_transport == "parallel_chunked"`
  - `effective_transport == "http_range_resume"`
  - `fallback_reason == "transport_helper_unavailable"`
  - `chunk_resume_mode == "range_resume"`
  - `planned_bytes == 6`
  - `written_bytes == 6`
  - `progress_pct == 1.0`
  - `integrity_decision == "accepted"`
  - `status == "completed"`
  - `selected_mirror == "https://huggingface.co"`
- [x] Run only that test and confirm it fails because no `artifact_transport_receipt` exists.

## Task 2: Add Failing Empty-Body Rejection Test

- [x] Add a test named `test_managed_download_rejects_unknown_size_empty_body_before_activation` using a zero-byte source file plus `melix.target_scope`, `melix.operation_kind`, and `melix.allow_unknown_size=true`.
- [x] Assert the pipeline raises `ModelOperationError(code="empty_artifact_body")`.
- [x] Assert `download.state.json` records `status=failed`, `terminal_state=failed`, `last_error=empty_artifact_body`, no completed output artifact, and an `artifact_transport_receipt` with `planned_bytes=0`, `written_bytes=0`, `integrity_decision=rejected_empty_body`, `status=failed`, and `fallback_reason=empty_body_unknown_size`.
- [x] Run only that test and confirm it fails because empty bodies currently complete.

## Task 3: Add Failing Registry Projection Test

- [x] Extend `test_download_registry_snapshot_exposes_operation_receipt_fields` with a manifest containing an object-valued `artifact_transport_receipt`.
- [x] Assert the snapshot exposes `artifact_transport_receipt` and `artifact_transport_status == "completed"`.
- [x] Reattach a manifest where `artifact_transport_receipt` is a string and assert the snapshot returns `{}` plus empty `artifact_transport_status`.
- [x] Run only that test and confirm it fails because the registry does not expose transport receipts.

## Task 4: Implement Minimal Receipt Support

- [x] Add `_transport_receipt_enabled(ext)` that returns true only when `uses_operation_receipt(ext)` is true.
- [x] Add `_transport_selection(ext)` returning `(requested_transport, effective_transport, fallback_reason, chunk_resume_mode)`.
- [x] Supported fixture behavior:
  - requested transport defaults to `http_range_resume`
  - `melix.requested_transport=parallel_chunked` with `melix.transport_helper_available=false` falls back to `http_range_resume`
  - `melix.force_transport_fallback=true` falls back to `http_range_resume` with `fallback_reason=user_forced_fallback`
  - all other requested values are used as the effective transport with empty fallback reason
- [x] Add `_artifact_transport_receipt(...)` that returns the exact fields from Tasks 1 and 2 plus `selected_mirror`.
- [x] Attach pending/running/completed/failed transport receipts in `_build_manifest_payload`, `_terminal_manifest_json`, strict-preflight failure payloads, and managed Hub import manifests when operation receipts are enabled.
- [x] Add `_raise_if_empty_unknown_size_body(...)` before writing the terminal completed snapshot for local deterministic downloads.

## Task 5: Project Receipt Through Registry

- [x] In `_download_registry`, normalize object-valued `artifact_transport_receipt` the same way `artifact_integrity` is normalized.
- [x] Add `artifact_transport_receipt` and `artifact_transport_status` to each download row.
- [x] Preserve existing snapshot fields and `resume_ready` behavior.

## Task 6: Docs And Verification

- [x] Update `docs/runbooks/phase-8-local-install.md` with `artifact_transport_receipt` fields:
  - `requested_transport`
  - `effective_transport`
  - `fallback_reason`
  - `chunk_resume_mode`
  - `planned_bytes`
  - `written_bytes`
  - `progress_pct`
  - `integrity_decision`
  - `status`
  - `selected_mirror`
- [x] State that this slice is deterministic local fixture evidence and does not change real network transfer defaults.
- [x] Run the focused red/green tests.
- [x] Run changed-scope coverage and verify `>=95%`.
- [x] Run PR-scoped performance reporting or record `N/A` if no probe selects this scope.
- [x] Run `git diff --check`.
- [x] Commit one focused #1258 slice.
