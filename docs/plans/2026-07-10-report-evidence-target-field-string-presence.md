# Report evidence target-field singleton fast path

## Scope

This Python-only performance slice is limited to `worker.productization.report_evidence_gate._rule_matches_report()` target-field presence checks. The registered probe's target-field workload and common release-evidence target rows use exact `dict` rows with one field. After the disjoint-key guard proves a singleton target has a matching key, the previous loop still iterated `target.items()` and repeated the field membership check before evaluating the value.

## Registered probe

The affected path is covered by the registered PR-scoped performance probe `report-evidence-gate-run-kind-set-membership` in `infra/perf/pr_scoped_probes.json`. That entry includes focused `test_command`, `coverage_command`, and `probe_command` entries and reports `target_field_elapsed_ms_mean` for this hot path.

## Optimization plan

1. Add an exact-`dict` singleton target fast path after the `target_field_set.isdisjoint(target)` guard.
2. Preserve subclass/custom-mapping behavior through the existing `.items()` path, and preserve string/non-string value presence semantics.
3. Run focused tests, changed-scope coverage, and the registered probe locally on Linux before opening the PR.
4. Use GitHub Actions PR-scoped performance as the registered probe merge gate.

## Verification

- Focused report-evidence gate tests pass.
- Changed-scope coverage for the touched Python file, test file, probe script, registry, and this plan remains at or above 95%.
- Local registered probe reports stable or improved `target_field_elapsed_ms_mean`; CI remains the source of truth for PR-scoped performance validation.
