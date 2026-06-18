# Changed-scope diff split newline performance slice

## Scope

This Python-only performance slice is limited to the hot unified-diff parser in
`scripts/changed_scope_coverage.py`.

## Registered probe

The affected path is already covered by the registered PR-scoped performance
probe `changed-scope-coverage-diff-parser` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries, and selects the
synthetic parser workload in `scripts/changed_scope_coverage_parse_probe.py`.

## Plan

1. Preserve parser behavior for malformed headers, no-newline markers, blank
   context lines, and trailing newline inputs.
2. Parse the hot loop over UTF-8 bytes split on explicit newlines so the parser
   avoids universal line-boundary handling and string-character dispatch for the
   ASCII-only diff grammar markers emitted by `git diff`.
3. Run the registered focused tests, changed-scope coverage command, and
   registered parser probe locally on Linux.
4. Use GitHub Actions and the PR-scoped performance workflow as the merge gate.

## Validation commands

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/changed_scope_coverage.py tests/test_changed_scope_coverage.py scripts/changed_scope_coverage_parse_probe.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
python3 scripts/changed_scope_coverage_parse_probe.py
```
