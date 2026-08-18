# Changed-scope coverage single-pass line classification

## Scope

Optimize one Python hot path in `scripts/changed_scope_coverage.py`: after the
changed line set is reduced to measurable source lines, classify each measurable
line as covered or missed in a single pass instead of building covered and missed
lists with two separate scans.

## Registered probe

The affected path is covered by the existing PR-scoped performance probe
`changed-scope-coverage-measured-set-filter` in
`infra/perf/pr_scoped_probes.json`. The probe entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries and reports the
changed-scope elapsed metrics (`elapsed_ms_mean`, `sparse_elapsed_ms_mean`,
`dense_elapsed_ms_mean`, and `allowlist_parse_elapsed_ms_mean`).

## Behavior parity

The change preserves the existing precedence for line classification: a line
present in both executed and missing data is classified as covered first, matching
the previous covered-list comprehension plus missed-list comprehension behavior
for normal coverage.py line partitions.

## Verification plan

1. Run the focused changed-scope tests and probe-selection tests from the
   registered probe.
2. Run changed-scope coverage for the touched files.
3. Run `python3 scripts/changed_scope_coverage_measured_probe.py` locally and
   compare the primary elapsed metrics against the `origin/main` baseline.
4. Use the registered PR-scoped performance CI probe as the final merge gate.
