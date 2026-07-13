# Changed Scope Coverage Measurable Line Direct List Slice

## Goal

Reduce per-file overhead in `scripts/changed_scope_coverage.py` when converting
measured changed lines into non-comment measurable line numbers.

## Registered Probe

The affected path is already covered by the registered PR-scoped probe
`changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for
`scripts/changed_scope_coverage.py`, its probe script, and focused tests.

## Scope

This slice only changes the source-line filtering helper used by
`_measurable_changed_lines`:

- return the measurable non-comment line-number list directly;
- avoid building an intermediate `line_no -> stripped_source` dictionary;
- preserve sparse streaming reads and dense full-file reads.

No coverage threshold, diff parsing, allowlist parsing, or PR-scoped probe
selection behavior changes are included.

## Validation Plan

Run the registered focused test set, changed-scope coverage command, and local
registered probe on Linux:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/changed_scope_coverage.py scripts/changed_scope_coverage_measured_probe.py tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
python3 scripts/changed_scope_coverage_measured_probe.py
```

## Metrics

Primary probe metric: lower `dense_elapsed_ms_mean` and `sparse_elapsed_ms_mean`
from `changed-scope-coverage-measured-set-filter`, with unchanged source read
call counts and measured line counts.
