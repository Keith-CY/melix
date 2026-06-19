# Changed-scope Empty Output Write Slice

## Scope

This Python performance slice is limited to the empty-path fast path in
`scripts/changed_scope_coverage.py`. The path is exercised when the
`MELIX_CHANGED_SCOPE_COVERAGE_PATHS_JSON` allowlist filters every requested file
out of a changed-scope coverage run.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-empty-path-short-circuit` in
`infra/perf/pr_scoped_probes.json`. The registry entry already includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_probe.py`
- `tests/test_changed_scope_coverage.py`
- PR-scoped performance registry validation tests

## Implementation Plan

1. Preserve the current empty-path output contract exactly.
2. Replace the four separate `print()` calls in the empty-path branch with one
   `sys.stdout.write()` call containing the complete output block.
3. Run the registered focused test command, changed-scope coverage command, and
   registered probe locally on Linux.
4. Accept the slice only if behavior stays identical and the registered probe is
   neutral-to-improved for the empty-allowlist metric.

## Metrics

Primary metric: `main_empty_allowlist_elapsed_ms_mean` from the registered
`changed-scope-coverage-empty-path-short-circuit` probe.

Secondary guard metrics:

- `main_empty_allowlist_coverage_read_calls_mean` must remain zero.
- `source_read_calls_mean` must remain zero.
- `elapsed_ms_mean` should remain neutral for the measurable-lines helper.
