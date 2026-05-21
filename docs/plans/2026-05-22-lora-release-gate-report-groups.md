# LoRA Release Gate Report Groups

## Goal

Complete issue #733 by making human-readable LoRA compare reports separate
quality improvements, regressions, and inconclusive results.

Parent direction: issue #724, "OpenSearch-VL alignment: gate LoRA release with
paired compare evidence". Milestone direction: issue #731, "enforce
release-gate verdicts".

## Current Shipped Surface

- `evaluation-compare-report.md` includes verdict, delta accuracy, bootstrap CI,
  analytical CI, effect threshold, and per-target details.
- Compare summary JSON and run records persist statistical verdict payloads for
  release-gate automation.
- The release gate enforces selected-suite verdict policy, including exact
  improvement and non-regression modes.

## Gap

The Markdown compare report still renders targets in input order only.
Operators reviewing a release candidate must visually scan the whole table to
separate targets that improved, regressed, or remained inconclusive.

## Scope

This slice changes only the human-readable compare report:

- add a verdict-grouped release summary before per-target details
- group targets into quality improvements, regressions, and inconclusive
  results
- preserve the existing top-level target table and per-target detail sections
- update the benchmark/evaluation contract and operator runbook

Out of scope:

- changing statistical verdict derivation
- changing release-gate pass/fail policy
- changing persisted JSON/CSV schemas
- changing Swift or protobuf surfaces

## Performance And Metrics

The implementation groups already-materialized summary objects. It must not add
model execution, dataset materialization, artifact scans, or additional
statistical passes.

Measurement points:

- focused report-builder tests for all three verdict groups and empty-group
  behavior
- focused store test coverage for persisted report Markdown integration
- `git diff --check`
- changed-scope coverage for modified Python executable files
- PR-scoped performance report; report-generation changes are expected to
  select evaluation/report or store-adjacent probes and must remain
  non-regressing

Success metrics:

- report Markdown has explicit sections for quality improvements, regressions,
  and inconclusive results
- each section summarizes target model, verdict, delta accuracy, effect
  threshold, regression count, and interval detail
- empty sections render an explicit `None` row so reviewers can distinguish no
  results from a rendering failure
- changed-scope coverage for modified executable Python files is at least 95
  percent before handoff

## Implementation Plan

- [x] Update this plan and the governing contracts before broad code changes.
- [x] Add grouped release-summary rendering to `evaluation_reports.py`.
- [x] Add focused tests for grouped report output.
- [x] Run focused verification and changed-scope coverage.

## Verification

- `python3 -m py_compile services/mlx-worker-python/worker/productization/evaluation_reports.py services/mlx-worker-python/tests/test_evaluation_reports.py`
  - Result: passed.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_reports.py services/mlx-worker-python/tests/test_evaluation_store.py -k "compare_report or persist_compare_result_writes_expected_artifact_names_and_payloads"`
  - Result: 2 passed, 21 deselected.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python coverage run --data-file=/tmp/lora_release_report_groups.coverage -m pytest -q services/mlx-worker-python/tests/test_evaluation_reports.py services/mlx-worker-python/tests/test_evaluation_store.py -k "compare_report or persist_compare_result_writes_expected_artifact_names_and_payloads"`
  - Result: 2 passed, 21 deselected.
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --frozen --project services/mlx-worker-python python scripts/changed_scope_coverage.py --coverage-json /tmp/lora_release_report_groups_coverage.json services/mlx-worker-python/worker/productization/evaluation_reports.py`
  - Result: `TOTAL 26 1 96%`.
- `git diff --check`
  - Result: passed.
- Current local disk state during verification:
  - `df -h .`: about 3.1 GiB available, so full local Swift rebuild gates are high risk on this host.
