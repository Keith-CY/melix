# Changed-scope coverage single-string allowlist fast path

## Scope

This slice optimizes `scripts/changed_scope_coverage.py` when the probe-specific
`MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON` environment value is a simple JSON
string such as `"scripts/changed_scope_coverage.py"`.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`.
The probe watches `scripts/changed_scope_coverage.py`,
`scripts/changed_scope_coverage_measured_probe.py`,
`tests/test_changed_scope_coverage.py`,
`services/mlx-worker-python/tests/test_pr_scoped_performance.py`, and the probe
registry. It includes focused `test_command`, `coverage_command`, and
`probe_command` entries. Its metrics include `allowlist_parse_elapsed_ms_mean`,
which repeatedly parses the single-string allowlist case used by PR-scoped
changed-line coverage.

## Plan

1. Add regression coverage proving a plain JSON-string allowlist can bypass the
   full JSON decoder while escaped JSON strings still use the decoder and keep
   current semantics.
2. Add a minimal fast path for unescaped JSON-string allowlists before falling
   back to `json.loads` for lists, escaped strings, invalid JSON, and other
   payloads.
3. Run the focused tests, registered changed-scope coverage command, and local
   registered probe on Linux.
4. Use the PR-scoped performance workflow as the merge gate and compare the
   registered probe metrics against `origin/main`.

## Verification targets

```bash
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage run -m pytest -q tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_scope_report_selects_changed_scope_coverage_parser_probe services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probes_expose_focused_commands services/mlx-worker-python/tests/test_pr_scoped_performance.py::test_registered_probe_registry_entries_validate_commands_and_watch_globs
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python coverage json -o coverage.json
PYTHONPATH="$PWD:$PWD/services/mlx-worker-python" uv run --project services/mlx-worker-python python3 scripts/changed_scope_coverage.py --coverage-json coverage.json scripts/changed_scope_coverage.py scripts/changed_scope_coverage_measured_probe.py tests/test_changed_scope_coverage.py services/mlx-worker-python/tests/test_pr_scoped_performance.py
python3 scripts/changed_scope_coverage_measured_probe.py
```
