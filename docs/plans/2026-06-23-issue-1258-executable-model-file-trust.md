# Executable Model File Trust Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make model-provided executable loader files require the existing explicit model-load trust opt-in before Python text or VLM activation.

**Architecture:** Reuse the existing worker-side `ModelLoadTrustPolicy` gate instead of adding a parallel trust receipt. The policy resolver will inspect only lightweight top-level model artifact files, combine executable-file detection with the existing `config.json:auto_map` custom-loader detection, and keep route applicability, typed refusal details, metrics, and `trust_remote_code` forwarding unchanged.

**Tech Stack:** Python worker model-load trust helper, worker registry load boundary, protobuf `ModelLoadTrustPolicy`, pytest, Phase 8 local install runbook.

---

## Governing Context

- GitHub issue: `https://github.com/Keith-CY/melix/issues/1258`
- Existing model-load trust plan: `docs/plans/2026-05-14-model-load-trust-policy.md`
- Existing strict install and receipt plans:
  - `docs/plans/2026-05-25-issue-1258-strict-install-preflight.md`
  - `docs/plans/2026-06-21-issue-1258-digest-verification.md`
  - `docs/plans/2026-06-22-issue-1258-release-policy-receipts.md`
  - `docs/plans/2026-06-22-issue-1258-control-plane-integrity-receipt-schema.md`
- Runbook: `docs/runbooks/phase-8-local-install.md`

Issue #1258 calls out model-provided executable code and markerless runtime upgrades as managed artifact trust risks. The current worker policy blocks `config.json:auto_map` custom loaders by default, but a model directory can still carry executable Python loader files without `auto_map`. This slice closes that model-load activation gap without changing runtime execution semantics or adding real cryptographic signature verification.

## Scope

In scope:

- Detect top-level executable model-loader Python files under the selected model directory:
  - `modeling*.py`
  - `configuration*.py`
  - `tokenization*.py`
  - `processing*.py`
  - `image_processing*.py`
  - `feature_extraction*.py`
  - `generation*.py`
- Treat the detected files as a custom-loader requirement for trust-applicable Python text and VLM routes.
- Keep default-safe loads fail-closed with `unsafe_load_rejected` and `ModelLoadTrustPolicy.block_reason=custom_loader_requires_trust_remote_code`.
- Set `ModelLoadTrustPolicy.custom_loader_detection_source` to `model_files:<comma-separated file names>` when executable model files are the only reason for refusal.
- Preserve `config_json:auto_map` precedence when both `auto_map` and executable files are present.
- Allow activation when the request or model settings explicitly choose `trust_remote_code`, and pass the existing `trust_remote_code=True` kwarg through the runtime boundary.
- Document that executable-file trust uses the model-load trust receipt; it is complementary to managed artifact integrity receipts and does not replace digest/signature checks.

Out of scope:

- Real cryptographic verification of executable files.
- Remote release-ref fetching.
- Publish-token minimization.
- New desktop UI surfaces.
- Recursive scans of full model trees or weight directories.
- Changing non-trust-applicable deterministic, embedding, rerank, audio, image, speech, or transcription routes.

## Performance Probes And Metrics

- Detection must inspect only top-level directory entries and must not read model weights.
- Detection should not parse file contents; filename/stat checks are enough for this slice.
- Existing `model-load-config-json-bytes` and model-load trust probes remain the relevant changed-scope performance guard.
- The `model-load-config-json-bytes` focused coverage command must include any new tests that cover changed `model_load_trust.py` lines.
- Because `model-load-config-json-bytes` measures a low-millisecond 300-iteration workload, its elapsed mean gate uses a `0.5ms` absolute warning floor. This preserves the original regression catch (`+6.4ms`) while avoiding sub-millisecond sample noise once the `auto_map` fast path is restored.
- Changed-scope metrics:
  - focused pytest for `services/mlx-worker-python/tests/test_model_load_trust.py`
  - changed-scope coverage for `worker/model_load_trust.py` and touched tests, target `>=95%`
  - PR-scoped performance report; expected `Status: ok`
  - `git diff --check`

## Files

- Modify: `services/mlx-worker-python/tests/test_model_load_trust.py`
  - add red coverage for default-safe refusal when a model directory has an executable loader file but no `auto_map`
  - add red coverage for explicit `trust_remote_code` allowing the same model and forwarding the trust kwarg
  - add red coverage for `config_json:auto_map` precedence when both signals are present
  - add coverage that `config_json:auto_map` detection returns before scanning executable model files
- Modify: `services/mlx-worker-python/worker/model_load_trust.py`
  - add top-level executable model-file detection
  - merge the executable-file signal into `_detect_custom_loader_requirement`
  - preserve existing absent/config-only behavior
- Modify: `docs/runbooks/phase-8-local-install.md`
  - document executable model-file trust refusal and explicit opt-in behavior
- Modify: `infra/perf/pr_scoped_probes.json`
  - keep the `model-load-config-json-bytes` focused test and coverage commands aligned with the new hot-path regression test

## Task 1: Red Tests For Executable Model Files

- [x] Extend `test_worker_rejects_custom_loader_metadata_without_explicit_trust`.
- [x] Build a text model directory with `config.json` containing only `{"model_type": "llama"}` and a top-level `modeling_melix_demo.py`.
- [x] Load it through `WorkerRuntimeService` with a trust-applicable `RecordingTextBackend`.
- [x] Assert `response.ok is False`, `response.error.code == "unsafe_load_rejected"`, `response.error.details["block_reason"] == "custom_loader_requires_trust_remote_code"`, `response.load_trust.custom_loader_detection_source == "model_files:modeling_melix_demo.py"`, and `backend.load_calls == []`.
- [x] Extend `test_worker_trusted_custom_loader_receipt_passes_trust_remote_code`.
- [x] Reuse the same model fixture with a `LoadModelRequest.load_trust.requested_mode=MODEL_LOAD_TRUST_TRUST_REMOTE_CODE`.
- [x] Assert `response.ok is True`, `response.load_trust.custom_loader_required is True`, `response.load_trust.custom_loader_detection_source == "model_files:modeling_melix_demo.py"`, and `backend.load_calls == [True]` for the executable-file-only load.
- [x] Cover `config_json:auto_map` precedence when executable model files are also present.
- [x] Build a model directory with both `config.json:auto_map` and `modeling_melix_demo.py`.
- [x] Assert default-safe resolution rejects with `custom_loader_detection_source == "config_json:auto_map"`.
- [x] Add a regression guard that `config_json:auto_map` detection does not scan model files before returning.
- [x] Run the executable model-file focused selection and confirm it fails because executable model-file detection does not exist yet.

## Task 2: Implement File Detection

- [x] Add an `EXECUTABLE_MODEL_FILE_PREFIXES` tuple in `worker/model_load_trust.py`.
- [x] Add `_detect_executable_model_files(model_spec)` that returns sorted top-level file names matching the supported prefixes and `.py` suffix.
- [x] Keep path handling consistent with `_model_config_path`: blank paths return empty, `~` paths expand, plain paths avoid unnecessary `Path.expanduser()`.
- [x] Ignore directories, symlinks, non-`.py` files, and nested files.
- [x] Return a detection source string `model_files:<comma-separated file names>` when files are present.

## Task 3: Merge Detection Into Trust Policy

- [x] In `_detect_custom_loader_requirement`, keep the existing `config.json:auto_map` result as the first custom-loader signal.
- [x] If `auto_map` is absent and executable model files are present, return `(True, "model_files:<names>")`.
- [x] Preserve existing outputs:
  - missing or unreadable `config.json` with no executable files returns `(False, "config_json:absent")`
  - readable config without `auto_map` and no executable files returns `(False, "config_json")`
- [x] Re-run the focused tests until green.
- [x] Fix the first pre-commit performance regression by preserving the `auto_map` fast path: executable model-file scanning is deferred until `config.json` is missing, unreadable, non-regular, or readable without `auto_map`.

## Task 4: Documentation And Verification

- [x] Update `docs/runbooks/phase-8-local-install.md` under the strict install/trust discussion.
- [x] State that executable model-file refusal is a model-load trust receipt, not an artifact digest/signature receipt.
- [x] Update `infra/perf/pr_scoped_probes.json` so the focused `model-load-config-json-bytes` test and coverage commands include the `auto_map` no-scan regression guard.
- [x] Add a `0.5ms` absolute warning floor to `model-load-config-json-bytes.elapsed_ms_mean`; local re-runs showed the fixed `auto_map` path within sub-millisecond variance while preserving identical peak bytes and rejection counts. The `0.5ms` floor is below the original blocked regression delta (`+6.4ms`) and is covered by a registry policy assertion.
- [x] Run focused pytest:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_model_load_trust.py
```

- [x] Run changed-scope coverage and verify `>=95%` for the touched Python scope.
- [x] Run PR-scoped performance report and require `Status: ok`.
- [x] Run `git diff --check`.
- [x] Run the repository gates relevant to this slice: `make py-test`, `make swift-test`, and `make integration-test`.
- [x] Re-run the full pre-commit hook after the performance fix and registry update.

Final verification notes:

- Full pre-commit hook passed after the executable-file trust fix:
  - `make swift-test`: pass.
  - `make py-test`: pass, `4246 passed, 14 skipped, 2 warnings`.
  - `make integration-test`: pass, `122 passed, 1 skipped`.
  - PR-scoped performance report: `Status: ok`, direct probe `model-load-config-json-bytes` passed with changed-scope coverage `98%`.
- After merging current `origin/main` (`38695982abd9ff51d540040bb3a1e6d81ed0779b`), the focused model-load trust selection passed again: `30 passed`.
- After merging current `origin/main`, the direct `model-load-config-json-bytes` probe passed against a fresh `origin/main` baseline: elapsed mean `3.392571ms -> 3.789506ms`, delta `+0.396934ms`, peak bytes unchanged, rejection count unchanged.

## Self-Review

- Spec coverage: the tasks cover default fail-closed behavior, explicit trust allow behavior, detection-source precedence, implementation, documentation, coverage, performance, and PR evidence.
- Placeholder scan: no placeholder steps remain.
- Type consistency: all tests and implementation use the existing `ModelLoadTrustPolicy` fields and existing `unsafe_load_rejected` error path.
