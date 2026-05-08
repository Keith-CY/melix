# Quantization Indexed Shard Min Single-Pass Optimization

## Goal

Reduce redundant work in the MLX-LM quantization smoke-file helper when reading `model.safetensors.index.json` files. The helper only needs the deterministic first shard name for smoke evidence, so building a full unique set and sorting it is unnecessary.

## Linux Constraint

This is a Python-only slice under `services/mlx-worker-python` and is verifiable on Linux with focused pytest, changed-scope coverage, and a command-json PR-scoped performance probe.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_quantization_pipeline.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/quantization_index_shard_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance Probe

Registered scoped probe: `quantization-index-shard-min-single-pass`.

The probe creates a synthetic indexed MLX-LM bundle with many `weight_map` entries and repeatedly asks `_smoke_required_files_for_backend(...)` for the required smoke files. It reports:

- `elapsed_ms_mean` — lower is better.
- `sorted_calls_mean` — lower is better; the optimized helper should not call `sorted(...)` on this path.
- `peak_bytes_mean` — informational memory-pressure signal.

## Success Metrics

- Preserve smoke-file tuple semantics, including lexicographic first-shard selection, duplicate shard names, empty names, and non-string values.
- Focused Python tests pass.
- Changed-scope automated coverage is at least 95%.
- Local probe shows `sorted_calls_mean == 0.0` on the optimized branch and concrete timing/memory metrics.
