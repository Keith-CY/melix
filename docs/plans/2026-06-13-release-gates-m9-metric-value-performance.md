# Release Gates M9 Metric Lookup Performance Slice

## Context

The M9 release gate evaluator repeatedly resolves policy metric keys through
`_metric_value()` while computing missing and threshold-failure counts. The path
is covered by the registered PR-scoped probe
`release-gates-m9-failure-count-single-pass` in
`infra/perf/pr_scoped_probes.json`.

## Slice

Avoid allocating a `dotted_key.split(".")` list for every nested metric lookup.
Keep the flat-key fast path and first-segment missing guard, then walk the dotted
key with indexed `str.find()` slices.

## Verification

Use the registered probe commands for this path:

- focused release-gate tests and PR-scoped probe registry tests;
- changed-scope coverage for `release_gates.py`, `test_release_gates.py`,
  `test_pr_scoped_performance.py`, and `release_gates_m9_failure_count_probe.py`;
- `scripts/release_gates_m9_failure_count_probe.py` for local Linux metrics and
  CI PR-scoped performance validation.

## Expected Metrics

The target metric is `elapsed_ms_mean` from
`release_gates_m9_failure_count_probe.py`; `failure_count_mean` must remain
stable and `endswith_checks_mean` must stay at zero.
