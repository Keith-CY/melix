# Benchmark Export Evaluation JSONL Streaming Plan

## Goal
Reduce redundant memory pressure in `services/mlx-worker-python/worker/productization/benchmark_export.py` by keeping evaluation sample ingestion on the existing streaming JSONL path instead of materializing full file contents before normalization.

## Linux-only constraint
This cron run executes on Linux and cannot validate Melix macOS/Swift surfaces locally. The slice must stay inside the Python worker export path with Linux-verifiable tests, changed-scope coverage, and a local performance probe.

## Touched files
- `services/mlx-worker-python/worker/productization/benchmark_export.py`
- `services/mlx-worker-python/tests/test_benchmark_export.py`
- optional if needed for evidence only: no planned PR-scoped performance registry changes because `benchmark-export-run-scan-single-pass` already watches `benchmark_export.py`

## Hot path and waste
`collect_evaluation_artifacts()` reads evaluation sample JSONL artifacts. This slice targets the evaluation sample rows path so it continues to stream rows without any `Path.read_text(...).splitlines()` materialization step on large `evaluation-samples.jsonl` or `evaluation-compare-samples.jsonl` inputs.

## Probe definition
Local probe script:
- synthesize one large evaluation export tree with many `evaluation-samples.jsonl` rows and compare rows
- call `collect_evaluation_artifacts()`
- record elapsed milliseconds and peak traced bytes
- print concrete metrics as JSON

Scoped CI probe:
- reuse existing `benchmark-export-run-scan-single-pass` registration for `benchmark_export.py`
- no registry update unless implementation scope expands into uncovered harness code

## Success metrics
- Focused pytest for touched scope passes.
- Changed executable scope coverage for touched Python files is >=95%.
- `git diff --check` passes.
- Local probe preserves row counts and shows concrete performance evidence; the expected primary win is lower peak traced allocation on large evaluation JSONL exports.

## Verification commands
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_benchmark_export.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_benchmark_export.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json`
- `python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/benchmark_export.py services/mlx-worker-python/tests/test_benchmark_export.py`
- local benchmark-export evaluation JSONL probe
- `git diff --check`
