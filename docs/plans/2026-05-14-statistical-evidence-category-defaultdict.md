# Statistical Evidence Category Defaultdict Accumulator

## Scope

This performance slice is limited to `build_category_breakdown` in
`services/mlx-worker-python/worker/productization/statistical_evidence.py`.
It preserves the existing statistical-evidence category breakdown behavior while
reducing per-row accumulator work for repeated categories.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe
`statistical-evidence-category-breakdown-single-pass` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused
`test_command`, `coverage_command`, and `probe_command` entries and reports:

- `elapsed_ms_mean` (`lower_is_better`)
- `peak_bytes_mean` (`lower_is_better`)

## Implementation plan

Use a `defaultdict` accumulator for category totals so the hot loop can update
the category counter directly after label normalization instead of performing an
explicit `dict.get` branch for every row. The slice does not change ordering,
rounding, missing-label handling, or category-label normalization.

## Verification plan

Run the registered focused tests, changed-scope coverage command, and the
registered probe locally on Linux with `origin/main` as the baseline before
pushing. CI PR-scoped performance remains the merge validation source.

## Success criteria

- Focused statistical-evidence tests pass.
- Changed-scope coverage for touched files is at least 95%.
- The registered probe reports no regression and preferably lower
  `elapsed_ms_mean` and/or `peak_bytes_mean`.
