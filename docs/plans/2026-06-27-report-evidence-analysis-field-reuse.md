# Report evidence analysis payload field reuse

## Slice

Optimize exactly one Python hot path in report evidence analysis:
`_analyze_report()` in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.

The registered PR-scoped probe covering this path is `report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`. It already includes focused `test_command`, `coverage_command`, and
`probe_command` entries for `report_evidence_gate.py`, its focused tests, and
`scripts/report_evidence_gate_run_kind_probe.py`.

## Hypothesis

`_analyze_report()` previously looked up `source_evidence_ids` and `known_gaps` twice each while building
its result payload. Reusing the looked-up objects removes redundant dictionary lookups while preserving the
existing list-copy semantics for valid lists and the empty-list fallback for invalid values.

## Scope

- Keep report analysis behavior identical for list and non-list `source_evidence_ids` / `known_gaps`.
- Do not change report rendering, matrix matching, or probe registry semantics.
- Use the existing registered probe as the local and CI performance gate.

## Verification

Run the registered probe's focused tests, changed-scope coverage command, and probe command locally on
Linux. CI PR-scoped performance must also complete successfully before merge.
