# Evaluation latency mean pre-sort sum

## Scope

This Python-only performance slice is limited to `EvaluationCore._latency_stats()` in `services/mlx-worker-python/worker/engine/evaluation_core.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `evaluation-latency-percentile-vector-reuse` in `infra/perf/pr_scoped_probes.json`. The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/engine/evaluation_core.py`
- `services/mlx-worker-python/tests/test_evaluation_core.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Change

`_latency_stats()` still sorts the latency vector once for percentile interpolation, but now computes the total from the original latency list before sorting and reuses that total for the mean. This keeps the percentile and rounding behavior unchanged while avoiding a second pass over the newly sorted list for mean calculation.

## Verification plan

Run the registered focused test command, the registered coverage command, and the registered performance probe locally on Linux. GitHub Actions PR-scoped performance remains the final merge gate for the registered probe report.

## Expected signal

The probe should preserve `sorted_calls_mean == 1.0` and show a lower or neutral `elapsed_ms_mean` for repeated `_latency_stats()` calls over the synthetic latency vector.
