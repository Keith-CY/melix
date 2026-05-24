# Report Evidence Gate Run-Kind Set Membership

## Context

`worker.productization.report_evidence_gate._rule_matches_report` checks release-matrix `run_kinds` against report runs while building PR/release evidence summaries. Rules can contain multiple accepted run kinds, and reports can contain many runs.

## Slice

Convert the run-kind membership check from tuple membership to a one-time per-rule `frozenset` membership inside `_rule_matches_report`. This keeps behavior identical for non-tuple iterables while reducing repeated linear membership scans across report runs.

## Probe

Registered PR-scoped probe: `report-evidence-gate-run-kind-set-membership`.

The probe executes `scripts/report_evidence_gate_run_kind_probe.py` against a synthetic rule with 65 accepted run kinds and 80 report runs, asserting the expected match while reporting `elapsed_ms_mean`, `run_kind_count`, and `runs_per_call`.

## Verification

Use the registered probe commands from `infra/perf/pr_scoped_probes.json` for focused tests, changed-scope coverage, and command-json performance measurement.
