# 2026-04-29 Python benchmark export streaming JSONL plan

## Context

The Linux-verifiable optimization surface in `services/mlx-worker-python` includes several export collectors that currently load entire JSONL files into memory with `read_text(...).splitlines()` before parsing each row. This creates avoidable peak-memory growth when benchmark or evaluation artifacts become large.

The touched code path is:

- `worker/productization/benchmark_export.py`
- `tests/test_benchmark_export.py`

## Goal

Reduce peak memory and duplicate buffering in benchmark/evaluation export collection without changing the exported payload shape.

## Constraints

- The macOS app itself is not locally runnable in this Linux environment.
- Verification must rely on Python-only tests and probes.
- Public export shapes and ordering must remain unchanged.

## Planned Change

1. Add a shared helper that streams JSONL files line-by-line and yields only dictionary rows.
2. Reuse that helper across benchmark context rows, batch rows, matrix rows, evaluation samples, and compare samples.
3. Keep JSON file parsing behavior unchanged for single-payload files.
4. Add regression coverage proving blank lines and non-dictionary JSONL payloads are ignored consistently.

## Performance Probes

### Measurement points

- `collect_benchmark_artifacts(...)` on a synthetic large benchmark artifact tree
- `collect_evaluation_artifacts(...)` on JSONL-heavy evaluation sample inputs

### Success metrics

- No behavior regression in existing benchmark export tests
- Peak memory lower than the pre-change `read_text(...).splitlines()` approach on the synthetic benchmark probe
- Stable row counts and ordering in the resulting export bundle

## Verification Plan

```bash
PYTHONPATH=/tmp/melix-opt-benchmark-export:/tmp/melix-opt-benchmark-export/services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_export.py
PYTHONPATH=/tmp/melix-opt-benchmark-export:/tmp/melix-opt-benchmark-export/services/mlx-worker-python python3 - <<'PY'
# synthetic memory/time probe for benchmark export collection
PY
```

## Expected Evidence For PR

- targeted pytest pass result for `test_benchmark_export.py`
- synthetic probe output showing before/after memory and timing for the streaming path
- changed-scope coverage report for `worker/productization/benchmark_export.py`
