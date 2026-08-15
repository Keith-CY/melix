# Report evidence single run-kind direct membership

## Slice

Optimize the report evidence release-matrix role matcher by using direct set
membership for matching `run_kinds=("single_kind",)` matrix rules before falling
back to the generic rule matcher.

## Scope

- Change only `worker.productization.report_evidence_gate._report_matrix_roles`.
- Preserve existing behavior for misses, mutable run-kind rules, multi-kind
  tuples, metric-prefix rules, target-field rules, probe-phase rules, and
  non-string tuple values by keeping the generic normalization path where needed.
- Keep the existing PR-scoped registered probe
  `report-evidence-gate-run-kind-set-membership` as the performance gate for this
  path.

## Validation

- Focused regression: verify matching single-item tuple run-kind matrix rules
  skip `_string_frozenset` while preserving non-string stringification semantics
  and leaving generic fallback behavior intact.
- Existing mixed-rule regressions continue to cover metric-prefix, target-field,
  and probe-phase clauses.
- Registered probe: `scripts/report_evidence_gate_run_kind_probe.py`, which
  reports `run_kind_elapsed_ms_mean`, `matrix_roles_elapsed_ms_mean`, and
  companion metrics.

## Known Gaps

Linux local verification covers the Python implementation and registered probe.
No Swift runtime behavior is changed in this slice.
