# Changed-scope coverage singleton membership direct slice

## Scope

This slice keeps the registered `changed-scope-coverage-singleton-range-fastpath`
probe focused on `scripts/changed_scope_coverage.py` and narrows one hot branch
inside `_measurable_changed_lines`.

## Optimization

When a singleton changed line is already present in `executed_lines`, coverage
data cannot also require a missing-line classification for the same line. The
branch now skips the second sorted-list membership probe in that covered case
and returns the existing covered singleton result directly.

## Validation

- Focused regression tests cover the covered-singleton short-circuit and the
  registered singleton probe contract.
- Local Linux probe: `python3 scripts/changed_scope_coverage_singleton_probe.py`.
- Registered PR-scoped probe: `changed-scope-coverage-singleton-range-fastpath`.

## Expected metric movement

The covered singleton half of the probe should avoid one `bisect_left` lookup per
path, so `singleton_measured_elapsed_ms_mean` is expected to decrease while
`source_read_calls_mean` remains zero.