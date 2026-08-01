# Runtime utils indexed shard absolute check fast path

## Scope

This Python-only performance slice is limited to `worker/runtime/runtime_utils.py`, specifically `_indexed_safetensors_shard_bytes(...)` when processing repeated relative shard names from a safetensors index `weight_map`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `runtime-utils-top-level-weight-streaming` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/runtime/runtime_utils.py`
- `services/mlx-worker-python/tests/test_runtime_utils.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/runtime_utils_top_level_weights_probe.py`

The probe reports both top-level directory scanning metrics and indexed safetensors metrics. This follow-up slice uses `indexed_elapsed_ms_mean` and `indexed_peak_bytes_mean` as the primary metrics.

## Optimization slice

Safetensors index `weight_map` shard values are relative paths in the common generated-index case. `_indexed_safetensors_shard_bytes(...)` now checks the first character against `os.sep` before constructing an absolute `Path`, avoiding the per-shard `os.path.isabs(...)` call on the hot relative-shard loop. Existing string coercion, duplicate suppression, relative joins, and absolute POSIX path handling remain unchanged.

This follow-up keeps the same whitespace semantics but skips `str.strip()` for already-clean string shard names by checking the first and last character before the legacy strip fallback. Generated safetensors indexes use clean relative shard names, while existing tests continue to cover whitespace-padded legacy shard names and non-string coercion.

## Verification plan

Run the focused registered test command, changed-scope coverage command, and registered probe locally on Linux before opening the PR. GitHub Actions PR-scoped performance remains the merge gate for the registered probe report.

## Linux verification boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime effect is claimed.
