# Report Evidence Slowest Probe Phase Top-K Slice

## Scope

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._slowest_probe_phases`.

The current implementation materializes every baseline and candidate slowest-probe row, sorts the full list by `duration_ms`, and then keeps only the first five rows. PR-scoped evidence reports can contain many phase rows, while the report evidence gate only needs the top five for downstream summaries.

## Registered probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

This slice extends that existing focused probe so its `test_command`, `coverage_command`, `probe_command`, and metrics include `_slowest_probe_phases` timing. The registry continues to watch:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

## Plan

1. Add a focused regression test that proves `_slowest_probe_phases` preserves the top-five descending order and side annotation.
2. Replace the full-row dict materialization and full-list dict sort with `heapq.nlargest(5, ...)` over compact duration/side tuples, so only the winning rows are expanded back to dictionaries.
3. Extend `scripts/report_evidence_gate_run_kind_probe.py` with a synthetic 2,000-row slowest-phase workload and expose `slowest_probe_phase_elapsed_ms_mean` plus row-count metrics.
4. Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux.
5. Use GitHub Actions PR-scoped performance output as the merge gate.

## Metrics

Success is measured by lower `slowest_probe_phase_elapsed_ms_mean` in the registered probe while preserving behavior parity through the focused report-evidence gate tests and changed-scope coverage for the touched module, tests, registry, and probe script.

This slice is Python-only and locally verifiable on Linux. No Swift runtime effect is claimed.
