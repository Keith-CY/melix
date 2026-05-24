# Report Evidence Run Kind Cache Slice

## Scope

This Python-only performance slice is limited to report evidence gate run-kind
rule matching in `services/mlx-worker-python/worker/productization/report_evidence_gate.py`.
It keeps release evidence matrix behavior unchanged while avoiding repeated
`frozenset` construction for immutable tuple-backed `run_kinds` rules.

## Registered Probe

The affected path is covered by the registered PR-scoped probe
`report-evidence-gate-run-kind-set-membership` in
`infra/perf/pr_scoped_probes.json`.

The probe includes:

- focused tests for tuple-backed rule cache reuse and mutable non-tuple rules;
- changed-scope coverage for the report evidence gate path;
- a command-json performance probe that repeatedly matches a tuple-backed
  `run_kinds` rule against synthetic report runs.

## Acceptance Criteria

- Focused report evidence gate tests pass locally on Linux.
- Changed-scope coverage for the touched Python path remains at or above 95%.
- The registered probe reports lower `elapsed_ms_mean` for repeated tuple-backed
  run-kind matching than the pre-change baseline.
- PR-scoped performance CI completes successfully before merge.

## Non-Goals

- No release evidence schema changes.
- No generated protocol or lockfile changes.
- No Swift runtime performance claims from local Linux validation.
