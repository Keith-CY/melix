# Startup Version Parse Single-Pass Optimization

## Scope

This slice is Python-only under `services/mlx-worker-python` and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered PR-scoped performance probe.

Affected files:

- `services/mlx-worker-python/worker/productization/startup_signals.py`
- `services/mlx-worker-python/tests/test_startup_signals.py`
- `infra/perf/pr_scoped_probes.json` (existing registered probe)

## Optimization hypothesis

`normalized_version_parts()` previously trimmed version suffixes, split the cleaned version string, and applied a compiled regex to every segment. Startup update checks call this helper through `compare_versions()`. A single pass over the stripped version string can preserve the same behavior while avoiding the intermediate split list and per-segment regex match.

The intended behavior stays unchanged:

- optional leading `v` is ignored;
- `+` build metadata and `-` prerelease suffixes stop parsing;
- empty dotted segments are skipped;
- leading decimal digits in each segment are parsed, non-numeric segments become `0`;
- an empty result normalizes to `[0]`.

## Registered probe

Use the existing `startup-signals-version-compare-single-pass` registered probe in `infra/perf/pr_scoped_probes.json`. It includes focused `test_command`, `coverage_command`, and `probe_command` entries for `startup_signals.py` and validates repeated `compare_versions()` calls.

## Verification plan

Run locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_ignores_build_metadata_suffix services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_handles_suffixes_without_padding_lists services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_version_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_ignores_build_metadata_suffix services/mlx-worker-python/tests/test_startup_signals.py::test_compare_versions_handles_suffixes_without_padding_lists services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_startup_signals_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_startup_signals_version_probe_script_emits_metrics
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage report --include='services/mlx-worker-python/worker/productization/startup_signals.py'
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id startup-signals-version-compare-single-pass --base-repo <origin-main-worktree> --head-repo "$PWD" --output /tmp/startup-version-parse-probe.json
```

Success criteria: focused tests pass, changed-scope coverage is at least 95%, and the registered probe reports lower `elapsed_ms_mean` for head versus base without behavior regressions.
