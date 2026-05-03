# Download snapshot manifest base-reuse slice

## Scope

This slice is limited to the Python worker download pipeline manifest hot path for file-based download jobs.

Touched paths:

- `services/mlx-worker-python/worker/model_ops/download_pipeline.py`
- `services/mlx-worker-python/tests/test_download_pipeline_unit.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Goal

Reduce repeated work in `DownloadPipeline.run()` by reusing the static portion of per-snapshot manifest payloads and avoiding terminal-state JSON reparsing on retry/stall failures.

## Linux-only constraint

This host is Linux, so validation must stay inside Python worker code paths and the PR-scoped performance harness. No macOS-only runtime verification is required for this slice.

## Probe definition

Update the existing PR-scoped probe `download-pipeline-directory-size-single-stat` so it measures the download snapshot manifest hot path instead of the older directory-size helper. The probe must:

- create a synthetic source file,
- force many snapshot updates with a tiny `chunk_bytes` value,
- record `snapshot_count`, `elapsed_ms_mean`, and `elapsed_ms_min`,
- remain base-compatible for `origin/main` by keeping the probe command self-contained.

## Success metrics

- Focused tests pass.
- Changed-scope coverage for the touched executable files is at least 95%.
- The updated scoped probe reports non-regressive or improved elapsed metrics versus `origin/main` on the same synthetic workload.

## Verification commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_download_pipeline_unit.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_download_pipeline_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_download_pipeline_unit.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_download_pipeline_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json`
- `python scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/model_ops/download_pipeline.py services/mlx-worker-python/tests/test_download_pipeline_unit.py services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/pr_scoped_performance_run.py --probe-id download-pipeline-directory-size-single-stat --base-ref origin/main --samples 5 --output /tmp/download-pipeline-snapshot-probe.json`
- `git diff --check`
