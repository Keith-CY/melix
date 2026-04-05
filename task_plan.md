# Task Plan

## Goal

Advance `M12.1` by making multi-root model registry management and rescans operator-facing,
control-plane-owned, and deterministic across worker scans, catalog sync, and Window UI actions.

## Scope

- replace environment-only registry-root discovery with control-plane-managed root configuration
- preserve stable registry-root identity across rescans while keeping root ordering explicit
- expose root add, remove, reorder, and rescan actions through the Window UI and model-ops path
- keep invalid roots observable without poisoning successful roots or discovered models

## Measurement Points

- registry snapshots must surface stable root IDs, ordered roots, accessibility, and discovered
  model IDs
- rescans must preserve first-root-wins discovery semantics while updating catalog entries
  deterministically
- Window UI actions must be able to add, remove, reorder, and rescan roots without losing the
  latest root snapshot or adapter-registry state

## Phases

1. Root identity, control-plane sync, and worker scan contract
   - status: in_progress
   - evidence:
     - define the root identity scheme, rescan contract, and first-root-wins precedence rules
     - route configured registry roots through the control plane into worker-backed
       `registry_snapshot` execution without requiring environment rewrites
2. Window UI root management and observability
   - status: pending
   - evidence:
     - add operator controls for root add, remove, reorder, and rescan
     - surface ordered root rows, accessibility, and discovered model counts in the tools surface
3. Verification and milestone bookkeeping
   - status: pending
   - evidence:
     - run the authoritative Swift and Python verification commands for the touched scope
     - record changed-line coverage at or above `95%`, update `progress.md`, and close `M12.1`
       only after root identity and rescan behavior are test-backed

## Acceptance

- operators can manage multiple model roots and trigger rescans deterministically
- registry-root identity remains stable across rescans and root reordering
- invalid roots remain visible without breaking successful discovery from valid roots

## Risks

- path-order-only root IDs would make reorders look like different roots and break observability
- UI-only root management would drift from control-plane truth and disappear on the next
  catalog-driven sync
- rescans that do not preserve first-root-wins precedence could make sidecar overrides
  non-deterministic

## Outcome

- m12_1_multi_root_registry_management_in_progress
