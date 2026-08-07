# Report evidence run-kind set comprehension

## Scope

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._report_run_kind_values`, the helper used by `_report_matrix_roles(...)` when a release evidence matrix contains run-kind-only rules.

## Optimization

`_report_run_kind_values(...)` currently builds the run-kind set with an explicit Python loop and a locally bound `set.add`. This slice keeps the same normalization behavior while using a set comprehension so CPython can perform the simple collection build with less Python bytecode overhead.

Behavior remains unchanged:

- string `run_kind` values are included as-is;
- non-string values are converted with `str(...)`;
- missing run kinds still contribute the existing empty-string fallback.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

## Verification plan

1. Run focused report evidence tests around run-kind role matching.
2. Run the registered focused test command for `report-evidence-gate-run-kind-set-membership`.
3. Run the registered changed-scope coverage command and require at least 95 percent coverage.
4. Run the registered probe locally on Linux before and after the change and compare `matrix_roles_elapsed_ms_mean` plus the broader report-evidence guardrail metrics.
5. Use GitHub Actions PR-scoped performance output as the final merge gate.

## Baseline

Initial local Linux baseline on `origin/main` with the registered probe command:

```json
{"dict_list_checksum": 10240000.0, "dict_list_elapsed_ms_mean": 38.20913536474109, "dict_list_identity_hits": 5000.0, "dict_list_rows_per_call": 2048.0, "elapsed_ms_mean": 1005.0677983555943, "iterations": 50000.0, "load_report_payload_bytes": 6247.0, "load_report_payload_checksum": 48000.0, "load_report_payload_elapsed_ms_mean": 7.150595122948289, "match_count": 250000.0, "matrix_roles_elapsed_ms_mean": 3.1098753679543734, "matrix_roles_emitted_roles": 40000.0, "matrix_roles_probe_phase_rows": 2048.0, "matrix_roles_report_count": 1.0, "matrix_roles_role_count": 32.0, "metric_prefix_count": 65.0, "metric_prefix_elapsed_ms_mean": 405.36599582992494, "metric_prefix_match_count": 250000.0, "metrics_per_call": 80.0, "probe_phases_checksum": 320000.0, "probe_phases_elapsed_ms_mean": 46.749754482880235, "probe_phases_rows_per_call": 2048.0, "release_matrix_elapsed_ms_mean": 28.913624864071608, "release_matrix_emitted_rows": 80000.0, "release_matrix_report_count": 96.0, "release_matrix_role_count": 32.0, "run_kind_count": 65.0, "run_kind_elapsed_ms_mean": 213.39659257791936, "runs_per_call": 80.0, "sample_count": 5.0, "slowest_probe_phase_checksum": 2488000.0, "slowest_probe_phase_elapsed_ms_mean": 25.466515589505434, "slowest_probe_phase_rows_per_call": 2000.0, "target_field_count": 65.0, "target_field_elapsed_ms_mean": 265.61933401972055, "target_field_match_count": 250000.0, "targets_per_call": 80.0}
```
