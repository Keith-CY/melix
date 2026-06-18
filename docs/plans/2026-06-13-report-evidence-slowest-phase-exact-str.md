# Report evidence slowest-phase exact string duration fast path

## Scope

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._slowest_probe_phases`.

The report evidence gate consumes JSON-like report payloads. Slowest-phase duration values are expected as plain `float`, `int`, or `str` values from decoded report JSON. This slice keeps those accepted types and narrows the hot string branch to the exact `str` type used by decoded JSON payloads.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

The registry entry provides focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

## Implementation plan

1. Preserve existing tests for top-five slowest-phase ordering and typed duration conversion.
2. Replace the `isinstance(duration, str)` hot-path check with `type(duration) is str`, matching JSON-decoded payload types and avoiding subclass checks in the probe loop.
3. Run the registered focused tests, changed-scope coverage command, and local registered probe on Linux.
4. Use GitHub Actions PR-scoped performance as the merge gate before merging.

## Expected performance signal

The primary metric is `slowest_probe_phase_elapsed_ms_mean`; it should decrease because each slowest-phase row avoids the broader `isinstance(..., str)` check. The aggregate `elapsed_ms_mean` may also improve slightly, while unrelated sub-metrics may vary with local runtime noise.
