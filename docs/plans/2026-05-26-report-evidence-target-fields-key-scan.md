# Report evidence target-fields key scan

## Scope

This Python performance slice is limited to `worker.productization.report_evidence_gate._rule_matches_report(...)` target-field matching. The run-kind, metric-prefix, and probe-phase paths remain unchanged.

## Registered probe

Existing registered PR-scoped probe: `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`.

The probe already covers:

- `services/mlx-worker-python/worker/productization/report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_report_evidence_gate.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/report_evidence_gate_run_kind_probe.py`

The registry defines focused `test_command`, `coverage_command`, and `probe_command` entries for Linux CI, so no probe registry change is needed.

## Optimization

The target-field path previously iterated over every configured target field for every target row and performed a dictionary lookup for each candidate field. This slice normalizes the configured fields once to a cached `frozenset` and scans each target row's actual keys, checking set membership before evaluating the value. The behavior remains the same for present string values, whitespace-only strings, present falsey non-string values such as `None` and `0`, and absent fields.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and local registered probe on Linux before opening the PR. The PR-scoped performance workflow remains the merge gate for the registered probe result in CI.

## Success criteria

- Focused report evidence gate tests pass.
- Changed-scope coverage remains at or above 95% for the touched Python paths.
- The registered probe shows lower `target_field_elapsed_ms_mean` / `elapsed_ms_mean` on the same synthetic workload.
- `git diff --check` passes.
