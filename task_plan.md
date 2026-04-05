# Task Plan

## Goal

Advance `M11.4` by adding truthful large-model streaming evidence, unsupported-path smoke
coverage, and operator runbook guidance for the current Melix disk-streaming surface.

## Scope

- measure the RAM-resident baseline with the current benchmark pipeline
- capture typed unsupported-path evidence for `prefer_disk` and `require_disk`
- preserve requested-versus-effective disk-streaming and cache-policy visibility in a smoke report
- document current operator setup and diagnostic workflows without fabricating SSD-backed metrics

## Measurement Points

- the smoke runner must emit numeric RAM-baseline benchmark metrics for the selected model
- `prefer_disk` and `require_disk` attempts must capture typed unsupported evidence plus
  requested-versus-effective disk-streaming state
- the report must expose runtime support flags and cache-compatibility detail without inventing
  unavailable SSD-backed metrics

## Phases

1. Streaming evidence design and command contract
   - status: completed
   - evidence:
     - define the smoke report structure, baseline benchmark inputs, and unsupported-path evidence
       fields for the current disk-streaming surface
     - record the current runtime constraint that true SSD-backed execution is still unsupported
2. Smoke runner, integration coverage, and runbook
   - status: completed
   - evidence:
     - implement a repository-owned smoke command that benchmarks the RAM baseline, exercises
       `prefer_disk` and `require_disk`, restores settings, and emits a machine-readable report
     - add live integration coverage plus an operator runbook for setup and diagnosis
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - run the authoritative verification commands for the touched scope, including the new
       disk-streaming smoke integration path
     - record changed-line coverage at or above `95%`, update `progress.md`, and only close
       `M11.4` if the resulting evidence stays truthful to current runtime capabilities

## Acceptance

- Melix owns reproducible smoke evidence for the current disk-streaming surface
- operators can inspect requested-versus-effective disk-streaming state and unsupported-path
  diagnostics in one report
- runbook guidance explains current capability boundaries and diagnostic interpretation

## Risks

- emitting deterministic SSD metrics would make the milestone look complete while the runtime still
  rejects disk-backed execution
- treating unsupported-path smoke as a hard test failure would remove the operator evidence Melix
  currently can and should surface
- failing to restore model settings after the smoke path would leave operator state mutated between
  verification runs

## Outcome

- m11_4_truthful_streaming_evidence_completed_m11_closed
