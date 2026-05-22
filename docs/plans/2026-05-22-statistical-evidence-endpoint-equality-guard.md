# Statistical Evidence Endpoint Equality Guard

## Scope

This Python-only performance slice is limited to the paired-outcome equality
classification path in
`services/mlx-worker-python/worker/productization/statistical_evidence.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe
`statistical-evidence-bootstrap-single-sort` in
`infra/perf/pr_scoped_probes.json`. The registry entry includes focused
`test_command`, `coverage_command`, and `probe_command` entries for the
statistical evidence implementation, focused tests, PR-scoped performance tests,
and `scripts/statistical_evidence_bootstrap_probe.py`.

## Change

Before running the full constant-outcome scan, `build_paired_statistical_evidence`
now checks the first and last normalized outcomes. If those endpoints differ, the
sample cannot be constant, so the helper skips the full equality walk and passes
`all_values_equal=False` into both interval builders. Constant and singleton
samples keep the existing short-circuit behavior.

## Verification plan

1. Run the registered focused statistical-evidence tests locally on Linux.
2. Run changed-scope coverage for the touched source, focused tests, registry
   tests, and probe script.
3. Run the registered local Linux probe against `origin/main` and the branch.
4. Use GitHub Actions PR-scoped performance as the final registered probe gate
   before merge.

## Local evidence

Baseline `origin/main` registered probe, three runs:

- `elapsed_ms_mean`: 143.597, 147.072, 139.525 ms (mean 143.398 ms)
- `peak_bytes_mean`: 44553.6, 44635.2, 44635.2 bytes
- `sorted_calls_mean`: 0.0

Branch registered probe, three runs:

- `elapsed_ms_mean`: 135.225, 137.518, 137.300 ms (mean 136.681 ms)
- `peak_bytes_mean`: 44635.2, 44635.2, 44635.2 bytes
- `sorted_calls_mean`: 0.0

The local Linux registered probe shows a 6.717 ms mean reduction, roughly 4.7%
faster for the mixed-outcome probe workload, with unchanged sorted-call count and
stable peak allocation within the probe tolerance.
