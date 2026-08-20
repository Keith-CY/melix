# Statistical Evidence Analytical Variance Loop

## Scope

This Python-only performance slice is limited to the analytical confidence
interval variance calculation in
`services/mlx-worker-python/worker/productization/statistical_evidence.py`.
It preserves bootstrap sampling, interval payload formatting, release verdict
classification, protocol artifacts, and Swift/macOS behavior.

## Registered probe

The affected path is already covered by the registered PR-scoped probe
`statistical-evidence-bootstrap-single-sort` in
`infra/perf/pr_scoped_probes.json`. The entry includes focused
`test_command`, `coverage_command`, and `probe_command` values and reports
`elapsed_ms_mean`, `peak_bytes_mean`, and `sorted_calls_mean`.

## Optimization

Compute the analytical interval variance with one explicit loop, bind the sample
size once, and calculate the standard error with a single square-root call over
`variance / sample_size`. This avoids generator-frame overhead, repeated length
lookups, and the second square-root call on the repeated statistical-evidence
hot path.

## Verification plan

- Run the registered focused pytest command locally on Linux.
- Run the registered changed-scope coverage command locally on Linux and require
  at least 95% for changed executable scope.
- Run the registered statistical-evidence probe locally on Linux before and after
  the change and compare `elapsed_ms_mean`, `peak_bytes_mean`, and
  `sorted_calls_mean`.
- Use GitHub Actions PR-scoped performance as the merge gate after push.

## Success criteria

- Focused tests pass.
- Changed-scope coverage remains at or above 95%.
- The registered local probe preserves interval bounds and `sorted_calls_mean ==
  0.0` while improving or staying within noise for `elapsed_ms_mean`.
