# Startup product version stat cache

This Python performance slice is limited to repeated `read_product_version(...)`
lookups in `services/mlx-worker-python/worker/productization/startup_signals.py`.
The runtime already scans `pyproject.toml` line-by-line to avoid full-file reads;
this slice adds a process-local cache keyed by the resolved pyproject path plus
`st_mtime_ns` and `st_size` so repeated update checks avoid reopening and
rescanning an unchanged version file while still invalidating after file changes.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`startup-signals-version-compare-single-pass` in
`infra/perf/pr_scoped_probes.json`. The entry watches `startup_signals.py`, the
focused startup tests, the PR-scoped performance tests, and
`scripts/startup_signals_version_probe.py`, and it provides focused
`test_command`, `coverage_command`, and `probe_command` entries.

## Verification plan

Run locally on Linux before pushing:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_startup_signals.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_version_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_startup_signals.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_version_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/startup_signals.py services/mlx-worker-python/tests/test_startup_signals.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/startup_signals_version_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" MELIX_STARTUP_SIGNALS_VERSION_REPO_ROOT="$PWD" uv run --project services/mlx-worker-python python3 scripts/startup_signals_version_probe.py
```

GitHub Actions PR-scoped performance remains the merge gate.
