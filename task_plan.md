# Task Plan

## Goal

Land the first executable `M9.7` slice by adding a repository-owned security and stability closure audit that assembles typed findings from existing Melix release-gate assets, M9 probe coverage, and required operational runbooks.

## Scope

- add a typed closure-audit model under `worker.productization` for blocker, accepted-risk, evidence-gap, and deferred-work findings
- assemble deterministic audit evidence from the repository execution index, phase-8 release-gate assets, required M9 metric probes, and required M9 runbooks
- expose a repository-owned CLI wrapper that emits machine-readable audit JSON and exits non-zero only when blocker findings remain
- surface closure-audit counts through `build_phase8_metrics_report` so phase metrics can carry the audit state forward into later release gates
- add focused Python tests, runbook guidance, and a first decision record populated from the current repository evidence

## Phases

1. Typed audit schema and failing tests
   - status: completed
   - evidence:
     - active plan: `docs/plans/2026-03-30-m9-7-security-and-stability-closure-audit.md`
     - targets: `closure_audit.py`, `test_closure_audit.py`, and `test_acceptance_metrics.py`
     - TDD order: add failing tests for blocker classification, accepted-risk classification, evidence-gap detection, stable JSON emission, and phase-metrics integration before implementing the audit model
2. Repository-owned outputs and documentation
   - status: completed
   - evidence:
     - add `scripts/m9_closure_audit.py`
     - add `docs/runbooks/security-and-stability-closure.md`
     - add `docs/decisions/2026-04-02-m9-security-stability-closure-audit.md`
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - targeted pytest and CLI verification for the closure audit slice
     - changed-line coverage for the touched Python scope at or above `95%`
     - metrics and roadmap status recorded in `progress.md` and the execution index

## Acceptance

- the repository emits a deterministic closure-audit JSON document with typed findings and stable counts
- missing M9 runbooks or probe vocabulary produce explicit evidence-gap findings
- unresolved release-gate or milestone closure prerequisites can be classified as blockers or deferred work without relying on a hidden checklist
- phase metrics can surface `closure_audit.blocker_count`, `closure_audit.accepted_risk_count`, and `closure_audit.evidence_gap_count`

## Risks

- overfitting the audit to the current file layout can make it brittle when evidence moves across docs, scripts, or plans
- treating future milestone work as a present blocker could make the audit unusable as an intermediate closure artifact
- repository-wide text scanning can become noisy unless the audit constrains which probe names and artifact paths are authoritative

## Outcome

- completed
