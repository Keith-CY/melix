# Task Plan

## Goal

Land the first executable `M9.8` slice by wiring repository-owned M9 ecosystem and security evidence into the existing Phase 8 release gate and phase metrics pipeline.

## Scope

- add deterministic M9 evidence collectors for MCP tooling, agent export, shared access, persistent sessions, rich-output sanitization, connection lifecycle, and closure audit
- extend release-gate evaluation and policy handling so missing or regressed M9 evidence becomes machine-readable failure state
- surface `release_gate.m9_required_probe_count`, `release_gate.m9_missing_probe_count`, and `release_gate.m9_failed_threshold_count` through the phase metrics report
- add a repository-owned `m9_release_gate_smoke.py` command plus tests for passing and failing gate states
- update the release-gate and product-acceptance runbooks to describe the new M9 signals

## Phases

1. Failing tests and deterministic evidence collectors
   - status: completed
   - evidence:
     - active plan: `docs/plans/2026-03-30-m9-8-ecosystem-and-security-release-gates.md`
     - targets: `release_gates.py`, `test_release_gates.py`, `test_phase8_release_gate.py`, `test_phase8_runtime_probes.py`, and `test_acceptance_metrics.py`
     - TDD order: add failing tests for missing M9 evidence, failed thresholds, and phase-metrics exposure before wiring the collectors
2. M9 gate smoke and runbook closure
   - status: completed
   - evidence:
     - add `scripts/m9_release_gate_smoke.py`
     - add `services/mlx-worker-python/tests/test_m9_release_gate_smoke.py`
     - update `docs/runbooks/phase-8-release-gates.md`
     - update `docs/runbooks/phase-8-product-acceptance.md`
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - targeted pytest and smoke verification for the M9.8 slice
     - changed-line coverage for the touched Python scope at or above `95%`
     - metrics and roadmap status recorded in `progress.md` and the execution index

## Acceptance

- the release gate emits a machine-readable `m9` evidence section with stable collector payloads and summary counts
- missing required M9 probes or failed M9 thresholds fail the release gate closed
- phase metrics surface the three `release_gate.m9_*` counts without creating a second unrelated gate system
- a repository-owned smoke command can demonstrate both passing and failing M9 gate states deterministically

## Risks

- overloading the existing phase-8 gate with M9-only semantics can make the gate harder to reason about if the new summary fields are not clearly separated
- adding a second layer of synthetic evidence instead of reusing existing smoke contracts could duplicate source-of-truth definitions
- wiring closure audit into the gate too aggressively can turn deferred work into a false blocker

## Outcome

- m9_release_gate_slice_completed
