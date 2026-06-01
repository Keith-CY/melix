# Statistical analytical variance summary reuse

## Scope

This Python-only performance slice keeps paired statistical evidence semantics unchanged while reusing the existing paired-outcome summary for analytical variance calculation.

## Registered probe

Existing registered probe: `statistical-evidence-bootstrap-single-sort` in `infra/perf/pr_scoped_probes.json`.

The probe covers:

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/statistical_evidence_bootstrap_probe.py`

The registry already defines focused `test_command`, `coverage_command`, and `probe_command` entries, so no probe registry change is needed for this narrow Python optimization.

## Optimization

`build_paired_statistical_evidence()` already computes paired-outcome summary data before building bootstrap and analytical intervals. This slice extends that summary with `sum_squares` and passes it into `_paired_analytical_interval()`, avoiding a second generator-backed `sum((value - mean) ** 2 ...)` scan when the analytical variance is computed.

The fallback path inside `_paired_analytical_interval()` still computes `sum_squares` if the helper is called directly without a precomputed summary.

## Verification plan

Run the registered focused tests, changed-scope coverage, and the registered `statistical-evidence-bootstrap-single-sort` probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the final registered-probe merge gate.

## Success criteria

- Focused statistical evidence tests pass.
- Changed-scope coverage for the affected source/test/probe files is at least 95%.
- Local registered probe shows non-regression or improvement for `elapsed_ms_mean` and `peak_bytes_mean`.
- PR-scoped performance CI selects and completes the registered probe successfully.
