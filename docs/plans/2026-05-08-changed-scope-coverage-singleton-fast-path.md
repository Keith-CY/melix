# Changed-scope coverage singleton measured-line short-circuit

## Scope

This Python-only performance slice narrows `scripts/changed_scope_coverage.py` in the empty-path hot path. The changed-line coverage helper now uses a singleton measured-line fast path for files with one executed and one missing line, avoiding per-file executed/missing set construction when the changed lines cannot be measured.

## Registered probe

The affected path is already covered by registered PR-scoped probe `changed-scope-coverage-empty-path-short-circuit` in `infra/perf/pr_scoped_probes.json`.

The probe includes:

- focused `test_command` for `tests/test_changed_scope_coverage.py` and PR-scoped registry tests;
- changed-scope `coverage_command` for the helper, probe script, and registry test coverage;
- `probe_command` that repeatedly calls `_measurable_changed_lines(...)` for changed lines outside measured coverage and reports elapsed time plus source-read calls.

## Validation plan

Run locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/changed_scope_coverage.py scripts/changed_scope_coverage_probe.py tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
python3 scripts/changed_scope_coverage_probe.py
```

CI remains the merge gate for the registered PR-scoped performance report.
