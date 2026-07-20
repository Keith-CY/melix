# Changed-scope dense range-skip performance slice

## Scope

This Python-only performance slice is limited to
`scripts/changed_scope_coverage.py` and the dense measured-line path in
`_measurable_changed_lines(...)`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`. The registry entry already includes focused
`test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_measured_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`

## Optimization

The dense changed-line path already intersects changed lines with measured
coverage lines. Before that intersection, it still ran `_line_ranges_may_overlap(...)`,
which computes changed-set bounds with `min(changed)` and `max(changed)`.
For dense `set`/`frozenset` inputs and sorted measured coverage lists, this slice
intersects the measured lists first and skips the separate range-bounds scan.
If the intersections are empty, the function returns without reading source; if
not, the existing measurable-line filtering and covered/missed partitioning stay
unchanged. The singleton changed-line path keeps its own direct measured-bounds
fast path so the dense guard does not add overhead to the registered singleton
range probe.

## Validation plan

1. Add regression coverage proving dense set inputs do not call the range-overlap
   helper before intersecting measured lines.
2. Run the registered focused test command for
   `changed-scope-coverage-measured-set-filter` locally on Linux.
3. Run the registered changed-scope coverage command locally on Linux.
4. Run the registered probe locally on Linux and compare against the pre-change
   baseline.
5. Use the GitHub Actions PR-scoped performance report as the merge gate.

## Boundary

No Swift/macOS runtime effect is claimed for this slice. Local Linux validation
covers the Python script behavior, changed-scope coverage, and registered probe.
