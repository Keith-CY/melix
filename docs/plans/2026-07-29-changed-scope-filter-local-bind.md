# Changed-scope measured filter local binding slice

This Python-only performance slice is limited to the final measured-line covered/missed partition in `scripts/changed_scope_coverage.py`.

## Registered probe

The affected path is covered by the existing registered PR-scoped probe `changed-scope-coverage-measured-set-filter` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `scripts/changed_scope_coverage.py`
- `scripts/changed_scope_coverage_measured_probe.py`
- `tests/test_changed_scope_coverage.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`

## Slice

Bind `_sorted_line_list_contains` once before the final list-comprehension partition that classifies measurable changed lines as covered or missed. This preserves behavior and avoids repeated global name resolution in the hot path measured by the registered probe.

The same `_measurable_changed_lines(...)` hot path keeps singleton changed-set extraction direct with `next(iter(changed))` instead of a one-iteration loop. This is included to keep the sibling singleton PR-scoped probe neutral while preserving the same behavior and avoiding any extra source reads.

## Validation

Run the focused changed-scope coverage tests, changed-scope coverage command, and the registered probe locally on Linux before opening the PR. The PR-scoped performance workflow remains the hosted merge gate.

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95% for the touched paths.
- The registered probe reports a directionally lower `elapsed_ms_mean` or no material regression for the measured filter path.
