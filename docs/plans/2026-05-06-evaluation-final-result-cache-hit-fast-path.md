# Evaluation Final-Result Cache-Hit Fast Path

## Goal

Avoid reparsing local evaluation source rows when `materialize_local_evaluation_dataset(...)` can prove that the requested package already exists in the materialization cache.

## Linux-only constraint

This slice is Python-only under `services/mlx-worker-python` and can be verified on Linux with focused pytest, changed-scope coverage, and the existing PR-scoped performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Probe definition

Update the registered `evaluation-final-result-materialization-streaming` PR-scoped probe so it measures repeated cache-hit materialization after a warm package has already been published.

Metrics:
- `elapsed_ms_mean`: lower is better for cache-hit materialization.
- `peak_bytes_mean`: lower is better for cache-hit materialization.
- `read_rows_calls_mean`: lower is better and should be `0.0` on cache hits.
- `sample_count`: structural guard that the warm package was built from the expected row count.
- `cache_hit_count`: structural guard that each measured iteration used the cache-hit path.

## Success metrics

- Focused pytest passes for evaluation final-result tests and related PR-scoped performance tests.
- Changed-scope coverage is at least 95% for touched executable Python scope.
- Local explicit probe shows cache-hit materialization avoids local row parsing (`read_rows_calls_mean=0.0`) and records concrete elapsed/peak numbers.
- `git diff --check` passes.
