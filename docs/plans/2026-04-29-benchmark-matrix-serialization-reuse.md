# Benchmark Matrix Serialization Reuse Plan

## Context

This Linux-only optimization slice targets `services/mlx-worker-python` and avoids Swift or macOS-only surfaces.

## Goal

Reduce redundant work in `worker/productization/benchmark_store.py` when persisting benchmark matrix artifacts by serializing each summary/request row exactly once per call and reusing the serialized payloads for both JSONL and CSV outputs.

## Touched Files

- `services/mlx-worker-python/worker/productization/benchmark_store.py`
- `services/mlx-worker-python/tests/test_benchmark_store.py`

## Constraints

- Preserve all artifact names, paths, output ordering, and output content.
- Keep the change locally verifiable on Linux with pytest and coverage.
- Keep scope limited to one coherent optimization slice.

## Probe

Create a small Python measurement script that persists synthetic benchmark matrix rows through the current code path and prints wall-clock timings for repeated runs. Success means the optimized path reduces repeated serialization work while preserving output bytes.

## Success Metrics

- Focused pytest for `test_benchmark_store.py` passes.
- Changed executable scope coverage is at least 95%.
- Performance probe shows a measurable improvement in the benchmark matrix persistence path.
- `git diff --check` passes.
