# Quantization index direct binary open performance slice

## Scope

This Python-only performance slice is limited to the MLX-LM indexed shard smoke-file helper in `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`.

The helper already caches parsed `model.safetensors.index.json` results by path, mtime, and size, and already finds the lexicographically first valid shard in a single pass. This follow-up keeps behavior identical while avoiding the `Path.read_bytes()` wrapper in the cache miss path by reading the index with direct binary `open(..., "rb")`.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe `quantization-index-shard-min-single-pass` in `infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries, and reports:

- `elapsed_ms_mean`
- `sorted_calls_mean`
- `peak_bytes_mean`

## Verification plan

1. Keep the existing shard selection, malformed index fallback, and cache invalidation semantics unchanged.
2. Extend the regression test to prove the index loading path avoids both `Path.read_text()` and `Path.read_bytes()` wrapper calls.
3. Run the registered focused tests, changed-scope coverage command, and `quantization-index-shard-min-single-pass` probe locally on Linux before pushing.
4. Use the GitHub PR-scoped performance workflow as the final merge gate after opening the PR.

## Metrics expectation

The direct-open slice should be neutral-to-improved for `elapsed_ms_mean`, keep `sorted_calls_mean` at zero, and preserve peak memory within probe noise.
