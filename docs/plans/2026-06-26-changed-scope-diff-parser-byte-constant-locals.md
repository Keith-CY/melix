# Changed-scope diff parser byte constant locals

## Scope

This Python-only performance slice is limited to the hot unified-diff parser in
`scripts/changed_scope_coverage.py`. It keeps parser behavior unchanged while
binding the byte-dispatch constants used inside `_parse_changed_lines(...)` to
function-local names before the per-line loop.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-diff-parser` in `infra/perf/pr_scoped_probes.json`. The
entry already includes focused `test_command`, `coverage_command`, and
`probe_command` values for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_parse_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Plan

1. Keep the change to `_parse_changed_lines(...)` only: localize the hot hunk
   new-range byte marker used by the per-hunk `bytes.find(...)` branch.
2. Run the registered focused tests, registered coverage command, and registered
   parser probe locally on Linux.
3. Run the registered PR-scoped performance comparison against `origin/main` and
   require a neutral-to-improved parser timing before opening/merging the PR.
4. Use GitHub Actions PR-scoped performance as the merge gate after the PR opens.

## Metrics

The registered probe reports `elapsed_ms_mean`, `elapsed_ms_min`, `line_count`,
`file_count`, and `changed_line_count` for a deterministic synthetic multi-file
diff. Lower elapsed values are better; output counts must stay unchanged.
