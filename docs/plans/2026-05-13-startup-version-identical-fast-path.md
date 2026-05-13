# Startup version identical fast path

## Scope

This Python-only performance slice keeps the startup signal version comparator behavior unchanged while avoiding normalized part parsing when two cleaned version strings are identical.

Touched path:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `infra/perf/pr_scoped_probes.json`

## Probe coverage

The affected path is already covered by the registered PR-scoped performance probe `startup-signals-version-compare-single-pass` in `infra/perf/pr_scoped_probes.json`. The probe declares focused `test_command`, `coverage_command`, and `probe_command` entries and reports `elapsed_ms_mean`, `peak_bytes_mean`, and `comparison_total`.

This slice extends the focused test command and coverage command to include the identical-clean-value regression test.

## Verification plan

Run locally on Linux before opening the PR:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_ignores_build_metadata_suffix services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_handles_suffixes_without_padding_lists services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_does_not_allocate_streaming_part_generators services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_identical_clean_values_skip_part_parsing services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_version_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_ignores_build_metadata_suffix services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_handles_suffixes_without_padding_lists services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_does_not_allocate_streaming_part_generators services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_identical_clean_values_skip_part_parsing services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_version_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/startup_signals.py services/mlx-worker-python/tests/test_startup_signals.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/startup_signals_version_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/startup_signals_version_probe.py
```

The PR-scoped performance GitHub Actions workflow remains the merge gate for the registered probe result in CI.

## Acceptance

- Focused startup-signal tests pass.
- Changed-scope coverage remains at or above 95% for the touched scope.
- Local registered probe shows no regression and preferably improves `elapsed_ms_mean`.
- PR-scoped performance CI completes `startup-signals-version-compare-single-pass` successfully.
