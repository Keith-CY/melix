# Statistical evidence interval payload local bounds

## Scope

This Python-only performance slice is limited to `worker.productization.statistical_evidence._interval_payload()`.

The bootstrap evidence path creates interval payloads for each paired statistical evidence build. The current implementation rounds bounds into a dictionary and then reads those dictionary entries back to compute `crosses_zero`. This slice keeps the emitted payload schema unchanged while computing the rounded local bounds once and storing `crosses_zero` during dictionary construction.

## Registered probe

The affected path is covered by the registered PR-scoped probe `statistical-evidence-bootstrap-single-sort` in `infra/perf/pr_scoped_probes.json`.

The registry entry includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/statistical_evidence.py`
- `services/mlx-worker-python/tests/test_statistical_evidence.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/statistical_evidence_bootstrap_probe.py`

## Plan

1. Preserve interval payload fields and rounded bound semantics.
2. Compute rounded lower/upper bounds once as locals inside `_interval_payload()`.
3. Build the payload with `crosses_zero` directly from those locals, avoiding dictionary lookups on the hot path.
4. Verify with the registered focused pytest command, changed-scope coverage, and the registered bootstrap probe locally on Linux.
5. Use GitHub Actions PR-scoped performance as the merge gate.

## Metrics

Primary metric: `elapsed_ms_mean` from `scripts/statistical_evidence_bootstrap_probe.py`.
Secondary metrics: `peak_bytes_mean`, `lower_bound_mean`, and `upper_bound_mean` to confirm allocation and numerical parity.

Initial local Linux measurements on this worktree:

- Baseline `statistical_evidence_bootstrap_probe.py`: `elapsed_ms_mean=143.049859`, `peak_bytes_mean=44544.0`, `lower_bound_mean=0.31374`, `upper_bound_mean=0.4419`.
- Candidate after this slice: `elapsed_ms_mean=131.745462`, `peak_bytes_mean=44544.0`, `lower_bound_mean=0.31374`, `upper_bound_mean=0.4419`.

The local probe shows an `11.304397 ms` mean reduction (`7.90%` lower) while preserving rounded interval bounds.
