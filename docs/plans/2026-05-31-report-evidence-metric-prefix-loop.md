# Report Evidence Matrix Matching Loop Performance Slice

## Scope

This Python-only performance slice is limited to release-matrix matching in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

## Registered probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The probe defines focused `test_command`, `coverage_command`, and `probe_command` entries and emits:

- `run_kind_elapsed_ms_mean`
- `metric_prefix_elapsed_ms_mean`
- `target_field_elapsed_ms_mean`
- aggregate `elapsed_ms_mean`

## Linux verification boundary

This slice is Python-only and locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered command-json performance probe.

## Optimization hypothesis

`_rule_matches_report()` currently converts each observed run kind through `str()` before set membership and uses `any(...)` with a generator expression for metric-prefix matching. The normal report path uses string run kinds and can check direct set membership first while retaining a second-pass fallback for non-string values. The metric-prefix path can use an explicit short-circuit loop to avoid generator-frame overhead. Both changes preserve existing matching semantics while reducing hot-loop overhead in the registered release-matrix probe.

## Validation plan

1. Run the registered focused tests for `report-evidence-gate-run-kind-set-membership`.
2. Run the registered changed-scope coverage command for the same probe.
3. Run the registered probe locally on Linux before pushing.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Acceptance criteria

- Behavior remains unchanged for tuple/list run-kind rules, non-string run-kind values, and tuple/list metric prefix rules.
- Changed-scope coverage remains at or above 95% for `report_evidence_gate.py`.
- Local registered probe shows lower `run_kind_elapsed_ms_mean` and `metric_prefix_elapsed_ms_mean` versus the synced `origin/main` baseline sample.
- PR-scoped performance CI selects and completes `report-evidence-gate-run-kind-set-membership` successfully.
