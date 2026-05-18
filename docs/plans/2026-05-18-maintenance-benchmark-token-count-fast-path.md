# Maintenance benchmark token-count fast path

## Scope

This Python-only performance slice is limited to benchmark helper token accounting in
`services/mlx-worker-python/worker/engine/maintenance_core.py`.

The slice preserves benchmark prompt shaping and context-length behavior while avoiding
`str.split()` list materialization for already-normalized single-space benchmark prompts.
Fallback behavior still delegates to `split()` when prompts contain leading/trailing
spaces, repeated spaces, or non-space whitespace.

## Registered performance probe

The affected path is covered by the existing registered PR-scoped probe
`maintenance-prompt-shape-vector-repeat` in `infra/perf/pr_scoped_probes.json`.
This slice extends the probe command to run `scripts/maintenance_prompt_shape_probe.py`
when present while retaining an inline fallback for base revisions that do not yet have
the script.

The focused commands remain:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_maintenance_service.py::test_benchmark_helper_parsers_cover_invalid_and_boundary_inputs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_maintenance_prompt_shape_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_maintenance_prompt_shape_probe_inline_fallback_is_base_compatible services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_maintenance_service.py::test_benchmark_helper_parsers_cover_invalid_and_boundary_inputs services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_maintenance_prompt_shape_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_maintenance_prompt_shape_probe_inline_fallback_is_base_compatible services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/engine/maintenance_core.py services/mlx-worker-python/tests/test_maintenance_service.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id maintenance-prompt-shape-vector-repeat --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/maintenance_prompt_shape_probe.json
```

## Verification boundary

This is a Python worker change and is locally verifiable on Linux with focused pytest,
changed-scope coverage, and the registered PR-scoped performance probe. GitHub Actions
PR-scoped performance remains the merge gate.
