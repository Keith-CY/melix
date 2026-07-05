# Runtime export diagnostic known-code countdown

## Scope

This Python-only performance slice is limited to
`worker.productization.export_target_diagnostics._diagnoses_from_excerpt`.

## Registered performance probe

The affected path is covered by the registered PR-scoped probe
`runtime-export-diagnostic-parser` in `infra/perf/pr_scoped_probes.json`. The
registry entry includes focused `test_command`, `coverage_command`, and
`probe_command` entries for the diagnostic parser, diagnostics tests, and probe
script.

## Optimization

The diagnosis scan already stops once every known diagnosis code has matched.
This slice replaces the per-line `len(seen_codes)` check with a small remaining
known-code countdown that is decremented only when a new code is admitted. The
behavior stays equivalent because `seen_codes` still guards duplicates and the
counter only reaches zero after every known code has been inserted.

## Verification plan

Run the registered focused tests, changed-scope coverage, and the registered
probe locally on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q services/mlx-worker-python/tests/test_export_target_diagnostics.py services/mlx-worker-python/tests/test_export_target_smoke_policy.py::test_export_target_smoke_blocks_report_when_required_file_is_missing services/mlx-worker-python/tests/test_export_target_smoke_policy.py::test_export_target_smoke_failure_boundaries services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_export_diagnostic_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_export_diagnostic_parser_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q services/mlx-worker-python/tests/test_export_target_diagnostics.py services/mlx-worker-python/tests/test_export_target_smoke_policy.py::test_export_target_smoke_blocks_report_when_required_file_is_missing services/mlx-worker-python/tests/test_export_target_smoke_policy.py::test_export_target_smoke_failure_boundaries services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_runtime_export_diagnostic_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_runtime_export_diagnostic_parser_probe_script_emits_metrics services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && python3 scripts/changed_scope_coverage.py --coverage-json coverage.json services/mlx-worker-python/worker/productization/export_target_diagnostics.py services/mlx-worker-python/worker/productization/export_target_smoke.py services/mlx-worker-python/tests/test_export_target_diagnostics.py services/mlx-worker-python/tests/test_export_target_smoke_policy.py services/mlx-worker-python/tests/test_pr_scoped_performance.py scripts/runtime_export_diagnostic_parser_probe.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id runtime-export-diagnostic-parser --base-repo <baseline-worktree> --head-repo "$PWD" --output /tmp/runtime_export_diagnostic_parser_probe.json
```

GitHub Actions PR-scoped performance remains the final merge gate for the
registered probe.
