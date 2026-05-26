# Report evidence target-field sentinel lookup

## Scope

This Python performance slice is limited to `worker.productization.report_evidence_gate._rule_matches_report(...)` target-field matching. The run-kind and metric-prefix behavior remain unchanged.

## Registered probe

Existing registered PR-scoped probe: `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

The probe already covers:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

The registry defines focused `test_command`, `coverage_command`, and `probe_command` entries for Linux CI, so no probe registry change is needed.

## Optimization

The target-field loop previously used `target.get(field, "")` followed by `field not in target` to distinguish absent fields from present falsey values. This slice replaces that with a module-level sentinel and a single `dict.get(field, sentinel)` lookup, preserving the existing behavior that present falsey non-string values such as `None` and `0` count as present after stringification.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe result in CI.

## Success criteria

- Focused report evidence gate tests pass.
- Changed-scope coverage remains at or above 95% for the touched Python paths.
- The registered probe shows lower `target_field_elapsed_ms_mean` / `elapsed_ms_mean` on the same synthetic workload.
- `git diff --check` passes.
