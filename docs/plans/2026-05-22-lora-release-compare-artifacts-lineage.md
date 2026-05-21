# LoRA Release Compare Artifact Lineage

## Goal

Complete issue #730 by making `eval compare` artifacts carry the release-gate
evidence needed for base-vs-adapter LoRA review: adapter target lineage, dataset
lineage, and statistical verdicts in the persisted compare bundle.

Parent direction: issue #724, "OpenSearch-VL alignment: gate LoRA release with
paired compare evidence". Milestone direction: issue #728, "automate
base-vs-adapter compare execution".

## Current Shipped Surface

- Compare jobs already support registered targets and adapter manifest targets.
- `EvaluationCompareJob.target_lineage` records registered versus ephemeral
  adapter targets, including adapter manifest paths and adapter set hashes.
- The compare summary CSV carries adapter manifest and adapter set hash columns.
- Per-target summaries already include statistical evidence and
  `release_gate_summary`.

## Gap

The compare artifact bundle does not yet expose one stable machine-readable
view that joins dataset lineage, target lineage, and statistical verdicts. A
release reviewer currently has to read multiple artifacts and infer the dataset
materialization context from job parameters.

## Scope

This slice persists structured lineage and verdict fields without changing
compare execution:

- add a typed compare dataset-lineage record
- attach dataset lineage to compare jobs created by local and event-extraction
  compare paths
- expose dataset lineage, target lineage, and statistical verdicts in
  `evaluation-compare-summary.json`
- expose the same release-gate evidence in `run-record.json`
- update the benchmark/evaluation contract

Out of scope:

- enforcing the release gate as a blocking publish step
- changing statistical verdict rules
- changing CSV column order
- changing adapter materialization or unload behavior
- changing protobuf schemas

## Performance And Metrics

The implementation adds small JSON payloads to already-written compare
artifacts. It must not add model execution, dataset scanning, or additional
statistics passes.

Measurement points:

- focused store tests for compare artifact JSON and run-record payloads
- focused evaluation-core tests for dataset-lineage construction
- `git diff --check`
- changed-scope coverage for the touched Python files
- PR-scoped performance report; the artifact path touches evaluation/store
  watch globs, so selected direct probes are expected, but the changed code must
  not regress job-id allocation, sample aggregation, answer normalization,
  latency percentile aggregation, dialogue diagnostics, compare target lookup,
  or CSV streaming probes

Success metrics:

- every compare job produced by the worker has `dataset_lineage`
- `evaluation-compare-summary.json` includes `dataset_lineage`,
  `target_lineage`, and `statistical_verdicts`
- `run-record.json` includes the same lineage/verdict evidence for evidence
  collectors
- changed-scope coverage for modified executable Python files is at least 95
  percent before handoff

## Implementation Plan

- [x] Update the benchmark/evaluation contract with the compare artifact
  lineage bundle fields.
- [x] Add a compare dataset-lineage schema and include it in compare jobs.
- [x] Populate dataset lineage in the local and event-extraction compare paths.
- [x] Persist lineage and statistical verdicts in compare summary JSON and
  run-record artifacts.
- [x] Add focused tests and run verification.

## Verification

- `python3 -m py_compile services/mlx-worker-python/worker/productization/evaluation_schemas.py services/mlx-worker-python/worker/productization/evaluation_store.py services/mlx-worker-python/worker/productization/run_records.py services/mlx-worker-python/worker/engine/evaluation_core.py`
  - Result: passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_evaluation_core.py -k "compare"`
  - Result: 25 passed, 103 deselected.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run --data-file=/tmp/lora_compare_artifacts.coverage -m pytest -q services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_evaluation_core.py -k "compare or payload_helpers or lineage_helpers"`
  - Result: 27 passed, 103 deselected.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/changed_scope_coverage.py --coverage-json /tmp/lora_compare_artifacts_coverage.json services/mlx-worker-python/worker/productization/evaluation_schemas.py services/mlx-worker-python/worker/productization/evaluation_store.py services/mlx-worker-python/worker/productization/run_records.py services/mlx-worker-python/worker/engine/evaluation_core.py`
  - Result: `TOTAL 87 0 100%`.
- `git diff --check`
  - Result: passed.
- Local PR-scoped performance report via `scripts.pre_commit_gate.run_performance_report(...)`
  against `origin/main`
  - Result: selected 8 direct probes; 7 passed, and 1 initial
    `evaluation-job-id-high-water-mark` regression was not stable on isolated
    registered-probe rerun.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id evaluation-job-id-high-water-mark --base-repo /tmp/melix-jobid-rerun.i5kKO9/base --head-repo /tmp/melix-jobid-rerun.i5kKO9/head --output /tmp/evaluation-job-id-high-water-mark-rerun.json`
  - Result: passed; base `elapsed_ms_mean=8.858`, head
    `elapsed_ms_mean=8.899`, delta `+0.46%`, below the 5 percent threshold.
- `git commit -m "Persist LoRA compare release evidence"` with the local
  pre-commit hook
  - Result: blocked by local disk exhaustion during `make swift-test`,
    specifically `swift-test-text-worker`. The first attempt reached code
    signing and reported `internal error in Code Signing subsystem`; an
    immediate focused rerun then failed with `No space left on device` while
    writing Swift build/index artifacts. No Python compare tests failed.
- Review follow-up verification after deduplicating compare payload helpers:
  - `python3 -m py_compile services/mlx-worker-python/worker/productization/evaluation_schemas.py services/mlx-worker-python/worker/productization/evaluation_store.py services/mlx-worker-python/worker/productization/run_records.py services/mlx-worker-python/worker/engine/evaluation_core.py`
    - Result: passed.
  - `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_store.py services/mlx-worker-python/tests/test_evaluation_core.py -k "compare or payload_helpers or lineage_helpers"`
    - Result: 27 passed, 103 deselected.
  - `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/changed_scope_coverage.py --coverage-json /tmp/lora_compare_artifacts_review_coverage.json services/mlx-worker-python/worker/productization/evaluation_schemas.py services/mlx-worker-python/worker/productization/evaluation_store.py services/mlx-worker-python/worker/productization/run_records.py services/mlx-worker-python/worker/engine/evaluation_core.py`
    - Result: `TOTAL 4 0 100%`.
