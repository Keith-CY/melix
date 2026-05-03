# Evaluation Final Result Streaming Materialization Plan

## Goal

Reduce redundant memory use in `services/mlx-worker-python/worker/productization/evaluation_final_result.py` by removing the intermediate fully materialized `serialized_samples` list from final-result dataset package construction while preserving package bytes, row ordering, cache semantics, and manifest fields.

## Linux-only constraint

This cron run is on Linux, so the slice must stay inside the Python worker and be fully verifiable with focused pytest, changed-scope coverage, and a local synthetic performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Planned change

1. Refactor final-result package materialization so `samples.jsonl` is written from a single-pass iterable instead of first building a full `serialized_samples: list[dict]` in memory.
2. Keep the existing output schema and newline behavior unchanged.
3. Add focused regression coverage proving the materialization path passes a streaming iterable into the JSONL writer instead of a prebuilt list.
4. Register a PR-scoped performance probe for `evaluation_final_result.py` that measures the materialization path directly and reports elapsed time plus peak traced bytes.

## Performance probe

Probe ID: `evaluation-final-result-materialization-streaming`

Synthetic workload:
- Build a deterministic final-result source with many rows (target ~15,000 rows).
- Materialize the package into a temporary cache directory.
- Record `elapsed_ms_mean`, `peak_bytes_mean`, and `sample_count`.
- Compare `origin/main` vs head through Melix PR-scoped performance CI.

## Success metrics

- Focused tests pass for the touched path.
- Changed-scope automated coverage for touched executable files is at least 95%.
- Local probe shows reduced `peak_bytes_mean` versus the current baseline while preserving `sample_count` and output behavior.
- `git diff --check` passes.

## Verification commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_final_result.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_final_result_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_evaluation_final_result.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_final_result_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/evaluation_final_result.py services/mlx-worker-python/tests/test_evaluation_final_result.py services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- Local probe command from the registered PR-scoped performance entry
- `git diff --check`
