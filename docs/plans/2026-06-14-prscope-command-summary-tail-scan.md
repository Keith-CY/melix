# PR-scoped performance command-summary partition fast path

## Scope

This Python-only performance slice is limited to `_summarize_command` in
`services/mlx-worker-python/worker/productization/pr_scoped_performance.py`.

The previous implementation found the first newline and then sliced the first
line manually. This slice keeps command-summary output unchanged while switching
to `str.partition("\n")`, which lets CPython split the first line and remainder
in one C-level operation for the long here-doc command payloads emitted by
PR-scoped performance command heartbeats.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `pr-scoped-performance-scope-matcher` in
`infra/perf/pr_scoped_probes.json`.

The registry entry includes focused:

- `test_command` for scope selection, glob matching, command-summary behavior,
  and probe dispatch.
- `coverage_command` for changed-scope coverage on `pr_scoped_performance.py`
  and its tests.
- `probe_command` that reports `build_scope_report_ms_*` and
  `command_summary_ms_mean`.

## Verification plan

Run on Linux before pushing:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_command_summary_keeps_ci_heartbeats_compact services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_pr_scoped_scope_matcher_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_command_summary_keeps_ci_heartbeats_compact services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_dispatch_probe_impl_supports_pr_scoped_scope_matcher_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/pr_scoped_performance.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 /tmp/run_prscope_scope_probe.py
```

GitHub Actions PR-scoped performance remains the final merge gate.

## Success criteria

- Focused tests pass.
- Changed-scope coverage is at or above the repository threshold for the touched
  scope.
- Local registered probe shows lower `command_summary_ms_mean` with unchanged
  scope-selection counts.
- PR-scoped performance CI completes successfully before merge.
