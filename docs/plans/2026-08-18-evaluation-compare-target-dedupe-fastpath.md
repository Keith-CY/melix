# Evaluation compare target dedupe fast path

This Python-only performance slice is limited to registered-model target lookup in
`services/mlx-worker-python/worker/productization/evaluation_compare.py`.

The affected path is covered by the registered PR-scoped performance probe
`evaluation-compare-target-lookup-short-circuit` in
`infra/perf/pr_scoped_probes.json`. That registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries and watches the
implementation, focused evaluation compare tests, PR-scoped performance tests,
and `scripts/evaluation_compare_target_lookup_probe.py`.

## Slice

`resolve_compare_target_models(...)` now uses a fast path for the common request
shape where compare target ids are already non-empty and unique. The function
still preserves the existing defensive slow path for empty or duplicate target
ids, keeps requested result ordering, and continues to short-circuit registry
handle scans once all targets are found.

## Verification plan

- Run the focused registered pytest command for evaluation compare target lookup.
- Run changed-scope coverage for the registered probe scope.
- Run `scripts/evaluation_compare_target_lookup_probe.py` locally on Linux before
  and after the change and compare `elapsed_ms_mean` plus lookup call counts.
- Use the PR-scoped performance workflow as the merge gate for registered CI
  probe validation.

## Expected metrics

The local Linux probe should preserve `get_loaded_model_calls_mean=3.0` and
reduce `elapsed_ms_mean` by avoiding the per-call append/deduplicate loop for the
common unique-target request tuple.
