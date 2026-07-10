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
cache-hit path. Earlier slices moved canonical cache values to lists and kept the
fresh-list return contract with `copy()`. This slice narrows the warmed cache-hit
lookup itself from `dict.get()` plus a nullable sentinel check to direct
subscription guarded by `KeyError`, so common cache hits avoid the extra
`None`-handling branch while preserving cache-miss behavior and defensive support
for older tuple-style cache entries.

## Verification Plan

Run the registered focused tests, changed-scope coverage command, and local
registered probe on Linux before opening the PR. The PR-scoped performance
workflow remains the merge gate for the registered probe result in CI.
