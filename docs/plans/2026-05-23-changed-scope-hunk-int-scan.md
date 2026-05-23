# Changed-Scope Coverage Hunk Integer Scan Slice

## Scope

Optimize one small Python hot path in `scripts/changed_scope_coverage.py`: parsing the new-file start line number from unified-diff hunk headers.

The behavior stays unchanged for supported hunk forms:

- `@@ -a,b +c,d @@`
- `@@ -a +c @@`

Malformed hunk headers still return `None` and are ignored by the changed-line parser.

## Registered Probe

The affected path is covered by registered PR-scoped probe `changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`.

The probe already declares:

- `test_command` for `tests/test_changed_scope_coverage.py` and PR-scoped registry tests.
- `coverage_command` that runs changed-scope coverage over the parser/probe/test files.
- `probe_command` through `scripts/changed_scope_coverage_parse_probe.py`.

## Implementation Plan

Replace the current substring extraction plus `int(...)` conversion in `_parse_hunk_new_start_from_digit` with a single-pass digit scan that accumulates the integer until the existing comma/space delimiters. This avoids temporary substring allocation and exception setup for normal hunk headers while preserving the same malformed-header behavior.

## Verification Plan

Run, from this worktree:

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json && PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/changed_scope_coverage.py tests/test_changed_scope_coverage.py scripts/changed_scope_coverage_parse_probe.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/pr_scoped_performance_run.py --registry infra/perf/pr_scoped_probes.json --probe-id changed-scope-coverage-diff-parser --base-repo <base-worktree> --head-repo "$PWD" --output <json-output>
```

## Success Criteria

- Focused tests pass.
- Changed-scope coverage is at least 95%.
- The registered probe reports a non-regressing parser metric with a clear local Linux comparison.
