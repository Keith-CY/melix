# Evaluation Compare Target Lookup Normalization Fast Path

## Slice

Optimize `resolve_compare_target_models` in `services/mlx-worker-python/worker/productization/evaluation_compare.py` by avoiding `str(...).strip()` for already-clean string model IDs in the loaded-model scan. The function still preserves requested target order, short-circuits after all requested targets are found, trims whitespace-padded string IDs, and converts non-string IDs with the previous `str(...).strip()` fallback.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe `evaluation-compare-target-lookup-short-circuit` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused entries for:

- `test_command`: behavior tests for `test_evaluation_compare.py` plus registry/probe smoke tests.
- `coverage_command`: changed-scope coverage for `evaluation_compare.py`, `test_evaluation_compare.py`, `test_pr_scoped_performance.py`, and `scripts/evaluation_compare_target_lookup_probe.py`.
- `probe_command`: command-json probe using `scripts/evaluation_compare_target_lookup_probe.py`.

## Validation Plan

1. Run the registered focused tests locally on Linux.
2. Run the registered changed-scope coverage command locally on Linux.
3. Run `scripts/evaluation_compare_target_lookup_probe.py` locally on Linux before and after the change and compare `elapsed_ms_mean` / `get_loaded_model_calls_mean`.
4. Use the PR-scoped performance workflow as the CI validation source before merge.

## Expected Behavior

No behavior changes. The slice only avoids unnecessary string coercion/trimming for canonical string model IDs in the hot loaded-model scan loop while keeping the existing normalization fallback for non-canonical IDs.
