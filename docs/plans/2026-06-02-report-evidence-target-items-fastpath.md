# Report evidence target-field item scan fast path

## Scope

This Python performance slice is limited to the target-field branch of
`worker.productization.report_evidence_gate._rule_matches_report(...)`.
Run-kind, metric-prefix, and probe-phase matching semantics are unchanged.

## Registered probe

The affected path is already covered by the PR-scoped probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`.

The registered probe has:

- `test_command` with focused report-evidence gate tests and PR-scoped probe
  registry/script tests.
- `coverage_command` with changed-scope coverage for the gate module, focused
  tests, probe script, and registry.
- `probe_command` running `scripts/report_evidence_gate_run_kind_probe.py`,
  which emits `target_field_elapsed_ms_mean` alongside adjacent run-kind and
  metric-prefix timings.

## Optimization hypothesis

The existing target-field path first uses `frozenset.isdisjoint(target)` to skip
unrelated target rows, then iterates every configured target field and catches
`KeyError` until it finds the matching key. In the common sparse release-matrix
row shape, matching rows contain far fewer keys than the rule field set.

After the disjoint guard proves at least one candidate field exists, iterating
`target.items()` and checking each row key against the cached field set avoids
repeated missing-key lookups and exception handling while preserving the same
string-presence semantics for matched values.

## Validation plan

1. Run the registered focused `test_command` locally on Linux.
2. Run the registered changed-scope `coverage_command` locally on Linux.
3. Run the registered `probe_command` locally on Linux and accept only if
   `target_field_elapsed_ms_mean` improves without material total probe
   regression.
4. Use PR-scoped performance CI as the final registered probe gate before merge.

## Acceptance criteria

- Target-field matching still treats non-empty string values and stringified
  non-string values as present.
- Mutable list rule configuration still reflects mutation instead of incorrectly
  using a stale cached tuple/set.
- Changed-scope coverage remains at or above 95% for the touched files.
- Local and CI registered probes complete successfully with lower target-field
  elapsed mean for the changed path.
