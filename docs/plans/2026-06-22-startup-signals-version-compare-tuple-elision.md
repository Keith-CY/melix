# Startup Signals Version Compare Tuple Elision

## Scope

This slice keeps startup update-version comparison behavior unchanged while reducing
hot-path overhead in `worker.productization.startup_signals.compare_versions`.
The registered PR-scoped probe is
`startup-signals-version-compare-single-pass` in
`infra/perf/pr_scoped_probes.json`.

## Probe

The affected path is already covered by a focused registered probe with:

- `test_command` for startup-signals version and cache behavior tests plus probe
  registration checks.
- `coverage_command` for changed-scope coverage over `startup_signals.py`,
  `test_startup_signals.py`, `test_pr_scoped_performance.py`, and
  `scripts/startup_signals_version_probe.py`.
- `probe_command` executing `scripts/startup_signals_version_probe.py`.

## Optimization

Previous compare logic called `_next_normalized_version_part` for each side of
each parsed segment. That helper returns `(value, index, done)` tuples, so every
non-short-circuited comparison allocates temporary tuple objects.

This slice adds a paired comparator that scans both version strings in one loop
and returns the comparison directly, avoiding per-segment tuple allocation while
preserving existing raw-equality, stripped-equality, and `v`-prefix
short-circuits.

## Acceptance

- Focused startup-signals tests pass.
- Changed-scope coverage remains at least 95% for touched files.
- The registered startup-signals version probe shows a lower or acceptable
  `elapsed_ms_mean` without changing `comparison_total`.
