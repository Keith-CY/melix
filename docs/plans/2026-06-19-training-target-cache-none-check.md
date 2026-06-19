# Training target-module cache hit check slice

## Scope

This Python-only performance slice is limited to the cached target-module
resolution path in `worker.model_ops.training_config._resolve_target_modules`.
The behavior remains unchanged: cached target-module tuples are still copied to a
fresh list for callers, preserving mutation isolation.

## Registered Probe

The affected path is covered by the existing registered PR-scoped probe
`training-config-target-module-cache` in `infra/perf/pr_scoped_probes.json`.
That registry entry already includes focused `test_command`, `coverage_command`,
and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/training_config.py`
- `services/mlx-worker-python/tests/test_lora_model_ops.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/training_config_target_modules_probe.py`

## Optimization

The hot probe prewarms the target-module cache, then repeatedly exercises the
cache-hit path. Cache values are always immutable tuples; missing entries are
represented by `None` from `dict.get()`. This slice replaces the generic
`isinstance(cached_targets, tuple)` guard with a direct `cached_targets is not
None` check on the cache-hit path, avoiding a repeated runtime type check while
keeping the cache-miss behavior unchanged.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and local
registered probe on Linux before opening the PR. The PR-scoped performance
workflow remains the merge gate for the registered probe result in CI.
