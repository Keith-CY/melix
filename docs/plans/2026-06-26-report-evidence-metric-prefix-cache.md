# Report evidence metric-prefix rule cache

## Scope

This performance slice keeps report evidence gate matching behavior unchanged while
reducing repeated normalization overhead for tuple-backed `metric_prefixes` rules.
It is limited to `worker.productization.report_evidence_gate._rule_matches_report`
and its focused tests.

## Registered probe

The affected path is already covered by the PR-scoped registered probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. The probe includes focused `test_command`,
`coverage_command`, and `probe_command` entries and measures metric-prefix rule
matching alongside the existing run-kind, target-field, matrix, dict-list, and
probe-phase paths.

## Implementation plan

- Reuse the existing rule-local cache pattern used for tuple `run_kinds`.
- Cache the normalized tuple, first-character set, and empty-prefix flag for tuple
  `metric_prefixes` on the rule dictionary by object identity.
- Preserve the non-tuple iterable path through `_string_prefix_tuple`.
- Extend focused regression coverage to prove repeated tuple-prefix matching no
  longer re-enters the `lru_cache` helper after the rule-local cache is populated.

## Validation plan

- Focused report evidence gate tests.
- Changed-scope coverage command from the registered probe.
- Registered PR-scoped performance probe on Linux.
- GitHub Actions PR-scoped performance workflow after push.
