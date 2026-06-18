# Closure Audit Text-File Path Elision

## Scope

This Python performance slice is limited to the closure-audit fallback text-file
walker used when curated probe evidence files do not saturate the required probe
source map. The change keeps deterministic sorted traversal and symlink-avoidance
semantics intact while avoiding a `Path(...)` object construction for every
recursive directory descent.

## Registered Probe

The affected path is covered by the registered PR-scoped performance probe
`closure-audit-probe-source-short-circuit` in `infra/perf/pr_scoped_probes.json`.
The probe already declares focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/closure_audit.py`
- `services/mlx-worker-python/tests/test_closure_audit.py`
- `services/mlx-worker-python/worker/productization/pr_scoped_performance.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Plan

1. Confirm the registered probe covers the closure-audit fallback scan path.
2. Preserve existing test coverage for deterministic sorted traversal, early
   probe-source saturation, and focused PR-scoped probe selection.
3. Reuse `DirEntry.path` directly for recursive `os.scandir` calls and construct
   `Path` objects only for yielded text files.
4. Run focused tests, changed-scope coverage, and the registered closure-audit
   probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Validation

Local Linux validation must include:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_closure_audit.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_only_matching_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_job_id_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_closure_audit.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_only_matching_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_probe_smokes_return_metrics_against_current_repo services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_evaluation_job_id_probe
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/closure_audit.py services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_closure_audit.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 -c "import json; from pathlib import Path; from worker.productization.pr_scoped_performance import _probe_closure_audit as probe; print(json.dumps(probe(Path.cwd()), sort_keys=True))"
```

CI validation comes from the registered PR-scoped performance report.
