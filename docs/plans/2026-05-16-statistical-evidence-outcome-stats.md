# Statistical Evidence Outcome Stats Single Pass

## Goal

Reduce redundant scans while building paired statistical evidence by converting
incoming paired outcomes to floats, accumulating the mean numerator, and checking
constant-outcome status in one pass.

## Scope

This is a Python-only productization slice and is locally verifiable on Linux.
It does not change bootstrap sampling, interval math, category breakdown, or
release-verdict classification.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`statistical-evidence-bootstrap-single-sort` in `infra/perf/pr_scoped_probes.json`.
The probe includes focused `test_command`, `coverage_command`, and
`probe_command` entries for:

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/statistical_evidence_bootstrap_probe.py`

## Implementation Plan

1. Add a small helper that returns `(outcomes, mean_value, all_values_equal)` from
   one pass over the caller-provided paired outcomes.
2. Keep empty-input behavior identical: mean remains `0.0` and constant-outcome
   short-circuit remains disabled for empty input.
3. Reuse the computed mean/equality values for both bootstrap and analytical
   interval builders.
4. Run the registered focused tests, changed-scope coverage, and registered probe
   locally before pushing.

## Success Metrics

- Focused tests from the registered probe pass.
- Changed-scope coverage for touched executable Python remains at least 95%.
- The local registered probe reports stable/lower `elapsed_ms_mean` and no peak
  memory regression while preserving bootstrap interval bounds.
- GitHub Actions PR-scoped performance remains the final merge gate.
