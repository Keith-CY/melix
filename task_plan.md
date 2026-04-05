# Task Plan

## Goal

Advance `M12.3` by adding metadata-driven image family dispatch and role-aware picker coverage for
the supported creative model families.

## Scope

- add image-family adapter metadata for the supported generation and edit families
- detect image family identity from explicit overrides, imported model metadata, and path-based
  fallback
- surface role support for generation and editing through worker registry snapshots, control-plane
  catalog summaries, and Window UI picker state
- keep the family support matrix operator-visible and aligned with the repository-owned image
  family set
- add focused unit and integration coverage for image-family metadata, role gating, and picker
  routing

## Measurement Points

- discovered image models must carry stable adapter metadata including family ID, backend ID, image
  task kind, default workflow role, and explicit generate or edit support declarations
- control-plane summaries must preserve image-family metadata and expose role-capable picker state
  without collapsing generate-only and edit-only families into one generic image entry
- image generation and image edit requests must reject models whose declared family role does not
  support the requested workflow
- the family support matrix must distinguish contract-only from live-verified image-family rows

## Phases

1. Image-family adapter contract and detection
   - status: completed
   - evidence:
     - add adapter descriptors for the targeted creative families
     - resolve image family identity from explicit overrides, imported metadata, and path-based
       fallback
     - project capability metadata and role-support declarations into worker model specs
2. Control-plane propagation and Window picker routing
   - status: completed
   - evidence:
     - preserve discovered image-family metadata through registry snapshot sync and worker
       preparation
     - update the Window UI image workflow picker so generate and edit modes resolve against
       role-capable image models instead of a single shared fallback
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - add focused Python, Swift, and menu-bar regression coverage for image-family metadata and
       role gating
     - record changed-line coverage at or above `95%`, update `progress.md`, and close `M12.3`
       only after the family matrix and picker behavior are test-backed

## Acceptance

- supported image families are scanned with stable family metadata instead of a generic
  deterministic image fallback
- generation and edit workflows select from role-capable image families and reject unsupported
  families with typed validation failures
- the support matrix, tests, and runbook evidence cover both contract and live-path status for the
  targeted image family set

## Risks

- over-broad path heuristics could misclassify image-edit families as text-to-image families and
  hide workflow constraints from operators
- UI fallback logic could silently switch workflows onto incompatible models if role metadata is
  missing or inconsistent across worker and control plane
- support-matrix rows without live verification would overstate image-family coverage for new
  creative families

## Outcome

- m12_3_image_family_dispatch_and_picker_completed
