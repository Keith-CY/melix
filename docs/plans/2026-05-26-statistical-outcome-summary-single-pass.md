# Statistical outcome summary single pass

## Scope

This Python-only performance slice keeps paired statistical evidence semantics unchanged while computing the paired-outcome mean and constant-outcome flag in one pass.

## Registered probe

Existing registered probe: `statistical-evidence-bootstrap-single-sort` in `infra/perf/pr_scoped_probes.json`.

The probe covers:

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/statistical_evidence_bootstrap_probe.py`

The registry already defines focused `test_command`, `coverage_command`, and `probe_command` entries, so no probe registry change is needed for this narrow Python optimization.

## Optimization

`build_paired_statistical_evidence()` previously scanned the normalized outcome tuple once for the mean and once for the equality guard before passing both values downstream. This slice replaces those two top-level scans with `_outcome_summary()`, which accumulates the sum and detects non-constant outcomes in the same loop.

## Verification plan

Run the registered focused tests, changed-scope coverage, and the registered `statistical-evidence-bootstrap-single-sort` probe locally on Linux before pushing. GitHub Actions PR-scoped performance remains the final registered-probe merge gate.

## Success criteria

- Focused statistical evidence tests pass.
- Changed-scope coverage for the affected source/test/probe files is at least 95%.
- Local registered probe shows non-regression or improvement for `elapsed_ms_mean` and `peak_bytes_mean`.
- PR-scoped performance CI selects and completes the registered probe successfully.
