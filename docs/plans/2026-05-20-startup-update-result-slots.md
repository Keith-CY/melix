# Startup update-check result slots performance slice

## Scope

This Python-only performance slice is limited to `UpdateCheckResult` allocations
in `services/mlx-worker-python/worker/productization/startup_signals.py`.
Startup update checks construct this immutable result for every channel check,
so the slice removes per-instance dictionaries by making the dataclass slotted.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `startup-signals-version-compare-single-pass` in
`infra/perf/pr_scoped_probes.json`. This slice extends that probe's focused
commands to include `test_check_for_updates_reports_newer_available_version`
and extends `scripts/startup_signals_version_probe.py` with an
`UpdateCheckResult` allocation metric:

- `update_result_elapsed_ms_mean`
- `update_result_peak_bytes_mean`
- `update_result_iterations`
- `update_result_available_count`

The existing version-compare metrics remain unchanged so the shared startup
signals path still guards the previously optimized parser path.

## Implementation plan

1. Add `slots=True` to `UpdateCheckResult` while preserving frozen dataclass
   semantics and field names.
2. Add a regression assertion that update-check results no longer expose a
   per-instance `__dict__`.
3. Extend the registered probe command coverage and probe-output tests for the
   allocation metric.
4. Run focused pytest, changed-scope coverage, and the registered probe locally
   on Linux before opening the PR.

## Verification commands

```text
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_startup_signals.py::test_check_for_updates_reports_newer_available_version services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_ignores_build_metadata_suffix services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_handles_suffixes_without_padding_lists services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_does_not_allocate_streaming_part_generators services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_identical_raw_values_skip_normalization services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_identical_clean_values_skip_part_parsing services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_v_prefix_equivalent_values_skip_part_parsing services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_version_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_startup_signals.py::test_check_for_updates_reports_newer_available_version services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_ignores_build_metadata_suffix services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_handles_suffixes_without_padding_lists services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_does_not_allocate_streaming_part_generators services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_identical_raw_values_skip_normalization services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_identical_clean_values_skip_part_parsing services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_v_prefix_equivalent_values_skip_part_parsing services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_version_probe_script_emits_metrics && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/startup_signals.py services/mlx-worker-python/tests/test_startup_signals.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/startup_signals_version_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/startup_signals_version_probe.py
```
