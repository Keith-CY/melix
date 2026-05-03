# MLX-LM structured result tail parsing optimization

## Goal

Reduce redundant stdout parsing work in `MLXLMRunner._run_subprocess()` when extracting the final structured MLX result from large subprocess output, without changing error handling or parsed payload semantics.

## Scope

This slice is limited to:

- `services/mlx-worker-python/worker/model_ops/mlx_lm_runner.py`
- `services/mlx-worker-python/tests/test_lora_model_ops_unit.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/mlx_lm_result_tail_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux constraint

This is a Python-only optimization slice. Verification must stay Linux-local via focused pytest, changed-scope coverage, and a PR-scoped performance probe that compares `origin/main` to the branch implementation.

## Performance probe

Register a dedicated PR-scoped performance probe for the hot path that:

- synthesizes a large `stdout` payload with many noise lines and one terminal `__MELIX_MLX_RESULT__=` JSON line
- measures `elapsed_ms_mean` for repeated structured-result extraction
- measures `peak_bytes_mean` with `tracemalloc`
- preserves an explicit correctness signal such as `payload_id`, `line_count`, and `sample_count`

## Implementation plan

1. Add a small helper that extracts the last structured result line from `stdout` by searching backward for the last line-start-prefixed result marker instead of materializing `stdout.splitlines()`.
2. Preserve current semantics for:
   - subprocess error propagation
   - accepting a terminal structured result with or without a trailing newline
   - rejecting outputs that never expose a line starting with `__MELIX_MLX_RESULT__=`
3. Add focused regression tests covering the optimized helper through `_run_subprocess()`.
4. Register the dedicated `command_json` PR-scoped probe and add focused probe-registry tests.
5. Validate with focused pytest, changed-scope coverage >=95%, `git diff --check`, and a local `origin/main` vs head probe run.

## Success criteria

- `_run_subprocess()` still returns the same parsed JSON payload for valid structured-result output.
- Missing structured-result output still raises the same `ModelOperationError` code/message class.
- Changed-scope coverage for the touched executable Python files remains at least 95%.
- The dedicated probe shows lower `elapsed_ms_mean` and lower `peak_bytes_mean` than `origin/main` for the same synthetic workload.
