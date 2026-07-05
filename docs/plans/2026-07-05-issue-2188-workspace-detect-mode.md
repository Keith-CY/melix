# Issue 2188 Workspace Ingest Detect Mode

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit audit-only `detect` mode for workspace ingest privacy detection, aligned with local proxy detect mode.

**Architecture:** The Python privacy detector owns the shared receipt and audit-counter semantics. `detect` mode scans text and emits `action: detected` receipts with category and match counts, but does not mutate source records, does not write redacted spans, and does not block ingest. The dataset ingest CLI accepts `detect` only when the operator explicitly requests it through `--privacy-detector-mode detect` or `MELIX_WORKSPACE_PRIVACY_DETECTOR_MODE=detect`; default and unsupported values remain `off`.

**Tech Stack:** Python 3.12, `worker.productization.privacy_policy_receipts`, dataset preparation ingest CLI, pytest, PR-scoped performance probe registry.

---

## Scope

- Extend Python privacy detector receipts to allow `policy_mode: detect` and `action: detected`.
- Count `detected` as audit-only/pass behavior in `melix.privacy_audit_counter.v1`.
- Keep raw source text and raw sensitive spans out of receipts, counters, operator failures, diagnostics metadata, and CLI JSON.
- Keep workspace source records and `segments.jsonl` unmodified in `detect` mode.
- Allow `detect` through `DatasetIngestRequest.privacy_detector_mode`, `--privacy-detector-mode`, and `MELIX_WORKSPACE_PRIVACY_DETECTOR_MODE`.
- Keep unsupported or empty environment/programmatic values normalized to `off`.
- Update canonical docs and probe coverage mapping for the new focused tests.

## Non-Goals

- No default-on workspace privacy policy.
- No detector regex, protobuf schema, model-backed detector, or NER change.
- No local proxy behavior change.
- No diagnostics bundle content scanning.
- No change to `redact`, `block`, or `off` semantics.

## Files

- Modify `services/mlx-worker-python/worker/productization/privacy_policy_receipts.py`
  - Add `detected` action support to single-result, aggregate, audit-counter, and metadata-derivation paths.
- Modify `services/mlx-worker-python/worker/productization/dataset_preparation.py`
  - Normalize `detect` as a supported workspace ingest mode.
- Modify `scripts/dataset_preparation_ingest.py`
  - Allow `detect` in CLI choices and environment mode normalization.
- Modify `services/mlx-worker-python/tests/test_privacy_policy_receipts.py`
  - Add RED/GREEN tests for detect action, aggregate behavior, and metadata derivation.
- Modify `services/mlx-worker-python/tests/test_dataset_preparation_ingest.py`
  - Add RED/GREEN tests for programmatic, CLI, and environment `detect` behavior.
  - Keep unsupported environment coverage by using a truly unsupported value such as `audit-only`.
- Modify `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
  - Assert the dataset preparation probes replay the new detect-mode ingest tests.
- Modify `infra/perf/pr_scoped_probes.json`
  - Add new detect-mode ingest tests to the dataset preparation probe commands.
- Modify `docs/plans/2026-05-24-dataset-preparation-quality-and-versioning.md`
  - Document `off`, `detect`, `redact`, and `block` workspace ingest modes.
- Modify `docs/runbooks/serving-diagnostics-evidence.md`
  - Document `detected` as a valid detector receipt action for diagnostics metadata.
- Update this plan with verification evidence before PR handoff.

## Task 1: RED Tests For Python Detect Receipts

- [x] Add `test_pattern_privacy_detector_detect_mode_audits_matches_without_redaction` to `services/mlx-worker-python/tests/test_privacy_policy_receipts.py`.
  - Input contains an email and a token.
  - Call `detect_privacy_patterns(..., policy_mode="detect")`.
  - Assert `redacted_text` equals the original input.
  - Assert receipt has `policy_mode: detect`, `action: detected`, `match_count: 2`, `redacted_span_count: 0`, categories `["email", "secret"]`, no blocked reason, no raw text in receipt JSON.
  - Assert audit counter has `passed_count: 1`, `redacted_count: 0`, `blocked_count: 0`.
- [x] Add `test_privacy_detector_aggregate_detect_mode_reports_detected_without_redaction`.
  - Aggregate one detect result and assert aggregate receipt action is `detected`, redacted span count is `0`, match count is preserved, and audit counter treats the decision as passed.
- [x] Add `test_privacy_detector_receipt_metadata_derivation_accepts_detected_action`.
  - Build namespaced metadata with `melix.privacy.detector.action=detected`, `policy_mode=detect`, `raw_text_included=false`, and assert `privacy_detector_receipt_from_metadata(...)` returns the redacted receipt.
- [x] Run the three new tests and confirm RED failures are caused by missing `detect` support:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_privacy_policy_receipts.py::test_pattern_privacy_detector_detect_mode_audits_matches_without_redaction \
  services/mlx-worker-python/tests/test_privacy_policy_receipts.py::test_privacy_detector_aggregate_detect_mode_reports_detected_without_redaction \
  services/mlx-worker-python/tests/test_privacy_policy_receipts.py::test_privacy_detector_receipt_metadata_derivation_accepts_detected_action
```

## Task 2: RED Tests For Workspace Ingest Detect

- [x] Add `test_dataset_ingest_privacy_detector_detect_mode_audits_without_mutating_segments`.
  - Use `prepare_dataset_ingest(...)` with `privacy_detector_mode="detect"` and disabled PII masking.
  - Assert ingest is ready, receipt action is `detected`, match count is nonzero, redacted span count is `0`, audit passed count is `1`, and `segments.jsonl` still contains the raw synthetic secret.
  - Assert the serialized receipt does not contain the raw synthetic secret.
- [x] Add `test_dataset_ingest_cli_accepts_detect_privacy_detector_mode`.
  - Pass `--privacy-detector-mode detect`.
  - Assert action is `detected`, match count is nonzero, and `segments.jsonl` remains unmodified.
- [x] Add `test_dataset_ingest_cli_accepts_detect_privacy_detector_mode_from_environment`.
  - Set `MELIX_WORKSPACE_PRIVACY_DETECTOR_MODE=detect` and omit the CLI flag.
  - Assert action is `detected` and the segment text remains unmodified.
- [x] Change `test_dataset_ingest_cli_ignores_unsupported_privacy_detector_environment` to use `audit-only` so unsupported-value coverage remains meaningful after `detect` becomes supported.
- [x] Run the new and changed tests and confirm RED failures are caused by missing `detect` support:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_privacy_detector_detect_mode_audits_without_mutating_segments \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_detect_privacy_detector_mode \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_detect_privacy_detector_mode_from_environment \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_ignores_unsupported_privacy_detector_environment
```

## Task 3: Implement Minimal Detect Support

- [x] In `privacy_policy_receipts.py`, update `privacy_audit_counter(...)` so `detected` increments `passed_count`.
- [x] In `detect_privacy_patterns(...)`, allow normalized mode `detect`; for matches, set `action="detected"`, preserve `redacted_text`, set `redacted_span_count=0`, and keep `blocked_reason=""`.
- [x] In `aggregate_privacy_detection_results(...)`, allow normalized mode `detect`; if any result action is `detected` and none are blocked or redacted, set aggregate action to `detected`.
- [x] In `privacy_detector_receipt_from_metadata(...)`, accept `detected` as a valid action while preserving raw-text rejection.
- [x] In `dataset_preparation.py`, allow `_privacy_detector_mode(...)` to return `detect`.
- [x] In `scripts/dataset_preparation_ingest.py`, add `detect` to parser choices and environment normalization.
- [x] Re-run the RED commands and confirm they are GREEN.

## Task 4: Docs, Probe Mapping, And Verification

- [x] Update `docs/plans/2026-05-24-dataset-preparation-quality-and-versioning.md` to list `detect` as an audit-only mode and describe CLI/env/default precedence.
- [x] Update `docs/runbooks/serving-diagnostics-evidence.md` so detector actions include `detected`.
- [x] Add new dataset ingest detect-mode tests to the three dataset preparation probe commands in `infra/perf/pr_scoped_probes.json`.
- [x] Update `test_dataset_preparation_probes_cover_privacy_detector_ingest_tests` with the new node IDs.
- [x] Run focused tests:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_privacy_policy_receipts.py::test_pattern_privacy_detector_detect_mode_audits_matches_without_redaction \
  services/mlx-worker-python/tests/test_privacy_policy_receipts.py::test_privacy_detector_aggregate_detect_mode_reports_detected_without_redaction \
  services/mlx-worker-python/tests/test_privacy_policy_receipts.py::test_privacy_detector_receipt_metadata_derivation_accepts_detected_action \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_privacy_detector_detect_mode_audits_without_mutating_segments \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_detect_privacy_detector_mode \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_detect_privacy_detector_mode_from_environment \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_ignores_unsupported_privacy_detector_environment
```

- [x] Run adjacent suites:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_privacy_policy_receipts.py \
  services/mlx-worker-python/tests/test_dataset_preparation_ingest.py
```

- [x] Validate probe registry and coverage guard:

```bash
python3 -m json.tool infra/perf/pr_scoped_probes.json >/dev/null
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q \
  services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_preparation_probes_cover_privacy_detector_ingest_tests
```

- [x] Run changed-scope hygiene and performance:

```bash
git diff --check
git diff --cached --check
MELIX_PRE_COMMIT_ALLOW_PERF_REGRESSION=1 \
MELIX_PRE_COMMIT_PERF_REGRESSION_REASON="dataset-source-records-scandir p95 regression was not reproduced by targeted base/head rerun; detect-mode change does not modify source record scanning path; context regressions are outside this PR scope" \
  .githooks/pre-commit
```

- [x] Run the full local gate before PR:

```bash
.githooks/pre-commit
```

## Verification Evidence

RED checks:

- `test_privacy_policy_receipts.py` detect-mode receipt nodes failed before
  implementation because direct detection redacted text, aggregate `detect`
  normalized to `off`, and metadata derivation rejected `detected`.
- `test_dataset_preparation_ingest.py` detect-mode nodes failed before
  implementation because programmatic `detect` normalized to `off`, CLI
  `detect` was rejected by argparse, and environment `detect` normalized to
  `off`; the unsupported `audit-only` environment fallback passed.

GREEN focused and adjacent checks:

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_privacy_policy_receipts.py::test_pattern_privacy_detector_detect_mode_audits_matches_without_redaction services/mlx-worker-python/tests/test_privacy_policy_receipts.py::test_privacy_detector_aggregate_detect_mode_reports_detected_without_redaction services/mlx-worker-python/tests/test_privacy_policy_receipts.py::test_privacy_detector_receipt_metadata_derivation_accepts_detected_action` -> `3 passed in 0.02s`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_privacy_detector_detect_mode_audits_without_mutating_segments services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_detect_privacy_detector_mode services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_accepts_detect_privacy_detector_mode_from_environment services/mlx-worker-python/tests/test_dataset_preparation_ingest.py::test_dataset_ingest_cli_ignores_unsupported_privacy_detector_environment` -> `4 passed in 0.06s`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_privacy_policy_receipts.py` -> `17 passed in 0.02s`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_dataset_preparation_ingest.py` -> `29 passed in 0.16s`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_serving_diagnostics.py::test_serving_diagnostics_effective_config_derives_privacy_detector_receipts_from_metadata services/mlx-worker-python/tests/test_serving_diagnostics.py::test_serving_diagnostics_effective_config_skips_incomplete_privacy_policy_metadata` -> `2 passed in 0.02s`.
- `python3 -m json.tool infra/perf/pr_scoped_probes.json >/dev/null` -> pass.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dataset_preparation_probes_cover_privacy_detector_ingest_tests` -> `1 passed in 0.36s`.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" UV_PYTHON=3.12 uv run --project services/mlx-worker-python --extra mlx python -m py_compile scripts/dataset_preparation_ingest.py services/mlx-worker-python/worker/productization/dataset_preparation.py services/mlx-worker-python/worker/productization/privacy_policy_receipts.py services/mlx-worker-python/tests/test_dataset_preparation_ingest.py services/mlx-worker-python/tests/test_privacy_policy_receipts.py services/mlx-worker-python/tests/test_pr_scoped_performance.py` -> pass.
- `git diff --check` -> pass.

Invalid pre-stage performance pre-run:

- `run_performance_report(..., changed_files=git diff + untracked, base_ref="origin/main")` selected 141 probes and exited `verification_failed`; report at `.runtime/pre-commit-performance/20260705-143803-acf03da8/report/report.md`.
- The failure is not valid PR evidence because the manual helper did not stage
  the changes and therefore its temporary head comparison snapshot did not
  include the new detect-mode test nodes referenced by the modified registry.
  The three direct dataset probes failed with pytest `not found` for those new
  node IDs. The official `.githooks/pre-commit` path uses the staged index
  snapshot and must be run after staging all files.

Staged pre-commit performance analysis:

- `.githooks/pre-commit` with all files staged ran the full host gate:
  `make swift-test` -> pass (`rc=0`, `500.1s`), `make py-test` -> pass
  (`4691 passed, 14 skipped, 2 warnings in 173.24s`), and
  `make integration-test` -> pass (`123 passed, 1 skipped in 693.79s`).
- The same staged pre-commit run produced
  `.runtime/pre-commit-performance/20260705-152724-acf03da8/report/report.md`
  with `status=regression`, `verification_failures=0`, `regression_count=1`,
  and `context_regression_count=9`.
- The only direct regression was `dataset-source-records-scandir`
  `elapsed_ms_p95`: base `8.555ms`, head `8.987ms`, delta `+5.04%`.
  The same probe's `elapsed_ms_mean` improved from `8.625ms` to `8.562ms`,
  `elapsed_ms_min` improved from `8.444ms` to `8.378ms`, and source-kind and
  record construction metrics stayed neutral.
- Root-cause check: this change does not modify `_iter_source_file_paths`,
  `_source_kind`, or `_record`; it only adds `detect` normalization, CLI/env
  acceptance, receipt semantics, and focused test/probe coverage mapping.
- Targeted base/head rerun of only `dataset-source-records-scandir` using the
  same pre-commit snapshot/export path passed with `status=ok`; `elapsed_ms_p95`
  was base `9.918ms`, head `9.692ms`, delta `-2.27%`. The rerun artifact is
  `.runtime/pre-commit-performance/20260705-152724-acf03da8/analysis/dataset-source-records-scandir-rerun.json`.
  This did not reproduce the direct p95 regression and supports treating the
  original p95-only failure as measurement noise outside the detect-mode code
  path.

Final staged pre-commit gate:

- `MELIX_PRE_COMMIT_ALLOW_PERF_REGRESSION=1 MELIX_PRE_COMMIT_PERF_REGRESSION_REASON="dataset-source-records-scandir p95 regression was not reproduced by targeted base/head rerun; detect-mode change does not modify source record scanning path; context regressions are outside this PR scope" .githooks/pre-commit`
  exited `0`.
- The hook ran the full host gate again: `make swift-test` -> pass
  (`rc=0`, `209.0s`), `make py-test` -> pass
  (`4691 passed, 14 skipped, 2 warnings in 161.48s`), and
  `make integration-test` -> pass (`123 passed, 1 skipped in 455.93s`).
- The final performance report is
  `.runtime/pre-commit-performance/20260705-161637-acf03da8/report/report.md`
  with `status=regression`, `verification_failures=0`, `selected_probes=141`,
  `direct_or_gated_probes=4`, `regression_count=2`, and
  `context_regression_count=14`.
- Direct/gated detail:
  - `dataset-version-listing-scandir` stayed `ok` with targeted tests and
    coverage passing at `100.0%`.
  - `dataset-quality-lengths-chain` reported a direct regression only on
    `failed_partition_elapsed_ms_p95`: base `0.635ms`, head `0.697ms`,
    delta `+9.69%`. The primary elapsed p95 improved from `1.483ms` to
    `1.407ms`, mean elapsed improved from `1.421ms` to `1.396ms`, and row,
    output-length, segment, and failed-count metrics were unchanged.
  - `dataset-source-records-scandir` reported direct regressions across
    scanning/source-kind/record timing metrics while `file_count_mean` and
    `source_kind_variant_count` stayed unchanged.
- Current-snapshot targeted rerun of `dataset-source-records-scandir` using the
  same staged base/head export path passed verification (`38 passed`, changed
  line coverage `100.00%`) and did not reproduce the regression:
  `elapsed_ms_mean` delta `-0.623%`, `elapsed_ms_p95` delta `-0.462%`,
  `record_elapsed_ms_mean` delta `-0.621%`,
  `source_kind_elapsed_ms_mean` delta `+0.134%`, file count delta `0`, and
  source-kind variant count delta `0`. Artifact:
  `.runtime/pre-commit-performance/20260705-161637-acf03da8/analysis/dataset-source-records-scandir-rerun.json`.
- Current-snapshot targeted reruns of `dataset-quality-lengths-chain` passed
  verification (`24 passed`, changed line coverage `100.00%`) and did not
  reproduce the failed-partition p95 regression:
  - Rerun 1 artifact
    `.runtime/pre-commit-performance/20260705-161637-acf03da8/analysis/dataset-quality-lengths-chain-rerun.json`:
    `failed_partition_elapsed_ms_p95` base `0.673ms`, head `0.614ms`; row and
    failed-count deltas `0`.
  - Rerun 2 artifact
    `.runtime/pre-commit-performance/20260705-161637-acf03da8/analysis/dataset-quality-lengths-chain-rerun-2.json`:
    `elapsed_ms_p95` delta `-1.033%`,
    `failed_partition_elapsed_ms_p95` delta `-0.775%`, row and failed-count
    deltas `0`.
  - Rerun 3 artifact
    `.runtime/pre-commit-performance/20260705-161637-acf03da8/analysis/dataset-quality-lengths-chain-rerun-3.json`:
    `elapsed_ms_p95` delta `-2.460%`,
    `failed_partition_elapsed_ms_p95` delta `-0.091%`, row and failed-count
    deltas `0`.
- Expanded performance rationale: this change adds audit-only `detect` mode,
  CLI/env normalization, receipt derivation, tests, docs, and probe replay
  coverage. It does not modify dataset quality partitioning, output-length
  calculation, source file scanning, source-kind classification, or record
  construction. The final hook's direct regressions were accepted only after
  same-snapshot targeted reruns failed to reproduce a stable regression and the
  hook was rerun with an explicit non-empty performance-regression reason.
