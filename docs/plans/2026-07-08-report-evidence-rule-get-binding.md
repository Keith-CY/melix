# Report Evidence Rule Getter Binding

## Scope

This Python performance slice is limited to the report evidence gate rule matching hot path in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.
It does not change report validation semantics, release matrix behavior, generated protocol artifacts, or CLI surfaces.

## Optimization Hypothesis

`_rule_matches_report()` repeatedly reads rule fields and cached normalized rule state while the registered report evidence gate probe exercises run-kind, metric-prefix, target-field, and probe-phase rules. Binding `rule.get` once per call should reduce repeated method lookup overhead without changing the mutable rule-cache behavior or list-rule mutation semantics. The release-matrix row renderer also binds `rows.append` while keeping per-row rule lookups unchanged, preserving output shape while avoiding repeated append-method lookup in the row emission loop.

## Registered Probe

The affected path is covered by the registered PR-scoped probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. The entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports the relevant `run_kind_elapsed_ms_mean`, `metric_prefix_elapsed_ms_mean`, `target_field_elapsed_ms_mean`, and `elapsed_ms_mean` metrics.

## Verification Plan

- Run the focused report evidence gate tests from the registered probe.
- Run changed-scope coverage through the registered probe coverage command.
- Run the registered probe locally on Linux and compare baseline versus candidate metrics.
- Let the PR-scoped performance CI workflow provide the merge-blocking registered probe report.

## Expected Effect

- Lower or neutral rule-matching elapsed time in the registered report evidence gate probe.
- Preserve cached tuple-rule behavior, list-rule mutation behavior, and probe-phase fallback behavior.
