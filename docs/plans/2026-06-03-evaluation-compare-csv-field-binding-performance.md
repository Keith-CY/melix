# Evaluation compare CSV field binding performance

## Scope

This slice targets the registered `evaluation-store-compare-summary-csv-streaming` PR-scoped performance probe. The affected path is `services/mlx-worker-python/worker/productization/evaluation_store.py`, specifically compare-summary CSV row rendering.

## Probe coverage

The existing registry entry in `infra/perf/pr_scoped_probes.json` already covers this path and includes focused `test_command`, `coverage_command`, and `probe_command` entries. The probe measures compare-summary CSV streaming across 10,000 summaries.

## Implementation plan

- Keep compare-summary CSV behavior unchanged.
- Bind `EvaluationStore._csv_field` once per `_compare_summary_csv_row` invocation and reuse the local binding for each field.
- Run the focused registered tests, changed-scope coverage, and the registered probe locally on Linux.

## Validation boundary

This is a Python-only Linux-verifiable slice. No Swift runtime effect is claimed.
