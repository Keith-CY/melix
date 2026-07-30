# Runtime utils indexed shard string cast fast path

## Scope

This Python-only performance slice is limited to `worker/runtime/runtime_utils.py`, specifically `_indexed_safetensors_shard_bytes(...)` while processing safetensors index `weight_map` shard names.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `runtime-utils-top-level-weight-streaming` in `infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/runtime_utils_top_level_weights_probe.py`

The probe reports both top-level directory scanning metrics and indexed safetensors metrics. This slice uses `indexed_elapsed_ms_mean` and `indexed_peak_bytes_mean` as the primary metrics.

## Optimization slice

Generated safetensors indexes already contain shard names as strings in the common path. `_indexed_safetensors_shard_bytes(...)` now skips the redundant `str(...)` cast for exact `str` shard values while preserving `.strip()` for legacy surrounding whitespace. Non-string values still use the original coercion path, and blank values, duplicate suppression, relative joins, and absolute POSIX paths remain unchanged.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.

## Rejected adjacent slice

A stricter whitespace-boundary fast path was tested first and rejected because the local registered probe regressed from `indexed_elapsed_ms_mean=336.836775` to `356.892904` ms on the same worktree. This accepted slice keeps the single narrower cast-elision change only.