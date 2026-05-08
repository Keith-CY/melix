# JSON Typed Score Running Aggregate Optimization

## Goal

Reduce transient list allocation in final-result JSON typed scoring by replacing recursive per-node `scores = [...]` materialization with running `total`/`count` aggregation.

## Scope

Touched files:

- `services/mlx-worker-python/worker/productization/evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_evaluation_final_result.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/evaluation_json_typed_score_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Linux-only constraint

This is a Python worker/productization slice and is fully verifiable on Linux with focused pytest, changed-scope coverage, and a local base-vs-head performance probe.

## Performance probe

Register a dedicated PR-scoped performance probe:

- Probe ID: `evaluation-final-result-json-typed-score-aggregate`
- Workload: repeatedly score a wide JSON payload through `score_final_result(...)` with ignored paths preserved.
- Metrics:
  - `elapsed_ms_mean` (lower is better)
  - `peak_bytes_mean` (lower is better)
  - `score_checksum` (structural equivalence)
  - `key_count` and `iteration_count` (workload shape)

## Success metrics

- Preserve JSON scoring semantics and ignored-path behavior.
- Focused pytest passes.
- Changed-scope coverage is at least 95%.
- Local probe shows lower peak allocation and/or lower elapsed time vs `origin/main` for the same workload.

## Verification commands

- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_evaluation_final_result.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_evaluation_final_result_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_evaluation_json_typed_score_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q ... && coverage json ... && python3 scripts/changed_scope_coverage.py ...`
- `PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python scripts/evaluation_json_typed_score_probe.py`
- `python scripts/pr_scoped_performance_run.py --probe-id evaluation-final-result-json-typed-score-aggregate --output /tmp/evaluation-json-typed-score-probe.json`
