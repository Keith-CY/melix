# Changed-scope coverage sorted membership

## Goal

Reduce allocation in `scripts/changed_scope_coverage.py` when filtering a small set of changed lines against the sorted `executed_lines` and `missing_lines` arrays emitted by coverage.py.

## Linux-only constraint

This slice is Python-only and locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered changed-scope coverage measured-set probe.

## Touched files

- `scripts/changed_scope_coverage.py`
- `tests/test_changed_scope_coverage.py`

## Performance probe

Use the existing registered `changed-scope-coverage-measured-set-filter` PR-scoped probe. The probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for the changed path and validates that no source reads occur when changed-line ranges cannot overlap measured coverage lines.

This slice additionally records a local before/after micro-probe for the overlap case where coverage line lists are sorted and the changed set is small.

## Success metrics

- Focused tests pass.
- Changed-scope coverage for touched executable lines is at least 95%.
- Registered probe command completes successfully.
- Local overlap micro-probe shows lower mean elapsed time for sorted coverage line membership.

## Verification commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/changed_scope_coverage.py scripts/changed_scope_coverage_measured_probe.py tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
python3 scripts/changed_scope_coverage_measured_probe.py
```
