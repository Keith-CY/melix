# Benchmark Evaluation Report Streaming Aggregation Plan

## Context

This Linux-only optimization slice targets `services/mlx-worker-python` and avoids Swift or macOS-only surfaces.

## Goal

Reduce redundant memory use and per-row overhead in `worker/productization/benchmark_evaluation_report.py` by replacing per-metric `list[float]` accumulation with running sum/count aggregation, then fast-pathing numeric probe rows and label formatting before falling back to generic handling, while preserving all output keys and values.

## 2026-05-01 numeric coercion slice

A follow-up Linux-verifiable slice fast-paths exact `float`, `int`, and `bool` values inside `_float_or_none` before falling back to string parsing. The registered synthetic benchmark-evaluation report probe repeatedly normalizes already-numeric JSON rows, so this removes the tuple `isinstance` check from the hot path while preserving bool and string coercion semantics.

## 2026-05-01 exact numeric collector fast-path slice

A second follow-up Linux-verifiable slice extends the exact-type numeric fast path into metric-row comparison plus benchmark request-row and evaluation sample-row collectors. Already-decoded JSON probe metrics are commonly exact `float`, `int`, or `bool` values, so these hot paths now avoid a generic tuple `isinstance` check and skip `_float_or_none` unless the value needs string parsing, while preserving bool rate/count semantics.

## 2026-05-03 input JSON byte-decoding slice

This Linux-verifiable slice keeps the report loader behavior unchanged while decoding benchmark/evaluation export JSON directly from `Path.read_bytes()`. The registered benchmark-evaluation report probe now records `load_input_ms_mean` around `load_report_input()` before report construction, so this removes the intermediate UTF-8 string decode and lets `json.loads` consume bytes directly. The regression test forbids `Path.read_text()` on the loader path while preserving malformed, missing, non-object, and directory fallback behavior.

## 2026-05-03 benchmark probe key iteration slice

This Linux-verifiable slice keeps benchmark/evaluation report output unchanged while iterating the actual keys present in each benchmark probe row and filtering them through a module-level probe-key set. The previous hot path checked every known probe key against every sparse row before reading values. The registered benchmark-evaluation report probe exercises the benchmark context and matrix request row collectors, so the slice removes avoidable fixed-key membership scans while preserving label construction, aggregate suffixes, and metric names. The sparse-row regression test now fails on fixed-key membership scans as well as fixed-key `get()` calls.

## Touched Files

- `services/mlx-worker-python/worker/productization/benchmark_evaluation_report.py`
- `services/mlx-worker-python/tests/test_benchmark_evaluation_report.py`

## Constraints

- Preserve report schema, metric names, numeric values, ordering, and warning semantics.
- Keep the change locally verifiable on Linux with focused pytest and coverage.
- Keep the slice small and avoid unrelated refactors.

## Probe

Create a self-contained Python measurement script that builds a large synthetic benchmark/evaluation bundle and compares the current `origin/main` implementation against the branch implementation for identical report output, elapsed time, and peak traced allocation.

## Success Metrics

- Focused pytest for `test_benchmark_evaluation_report.py` passes.
- Changed executable scope coverage is at least 95%.
- Performance probe shows reduced elapsed time and/or peak traced allocation for `build_benchmark_evaluation_report(...)` while preserving identical rows/summary output.
- `git diff --check` passes.
