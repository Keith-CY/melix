# Task Plan

## Goal

Complete `M14.2` by making image defaults persistent across restart and exposing role-aware image
model selection for generation versus editing through the control-plane and Window UI truth.

## Scope

- persist creative defaults such as steps, guidance, strength, and negative prompt through a
  control-plane-owned store
- project requested-versus-effective image defaults through reconnect-stable snapshots
- expose role-aware generate and edit model selection in the Window UI based on capability metadata
- keep the slice bounded to protocol, control-plane, Window UI, and focused Swift verification

## Measurement Points

- explicit image defaults survive service restart and remain inspectable through `ServerSnapshot`
- generate and edit requests keep explicit per-request values authoritative over persisted defaults
- Window UI image model pickers only surface models that support the requested creative role
- changed-line coverage for the touched handwritten executable scope remains at or above `95%`

## Phases

1. Contract and persistence design
   - status: completed
   - evidence:
     - reviewed the existing creative request flow and confirmed generation or edit parameters still
       lived in request-local UI draft state rather than a control-plane-owned persisted summary
     - inspected the image-model catalog metadata and confirmed the picker still lacked
       capability-driven generate-versus-edit role filtering
2. Persisted image defaults and snapshot projection
   - status: completed
   - evidence:
     - extended the control-plane protocol with typed `ApplyImageDefaults`, `ImageDefaultsSummary`,
       and optional creative parameter fields on generate or edit requests, then regenerated the
       versioned Swift, Python, and descriptor artifacts
     - added `ImageDefaultsStore` so the Swift control plane persists creative defaults, validates
       requested values, and projects requested-versus-effective summaries through reconnect-stable
       snapshots and XPC replies
     - updated the catalog seed and snapshot builders so image models declare generate/edit role
       support explicitly for downstream picker filtering
3. Window UI role-aware picker and defaults flow
   - status: completed
   - evidence:
     - updated `RuntimeViewModel`, `DesktopImageView`, and the shared XPC client so the Window UI
       hydrates image defaults from control-plane truth, applies persisted defaults explicitly, and
       routes typed creative parameters back through generate or edit requests
     - added role-aware picker filtering so generation and edit surfaces only expose compatible
       image families while keeping effective defaults inspectable after merge
4. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - reran `make proto`, focused control-plane and menu-bar Swift suites, coverage-enabled
       changed-line reports, `git diff --check`, and repository integration coverage for the
       touched slice
     - updated the active `M14.2` plan plus the roadmap execution index to reflect the completed
       persisted-image-defaults and role-aware-picker slice

## Acceptance

- persisted image defaults survive restart and remain inspectable through control-plane truth
- generate and edit requests merge persisted defaults without silently overriding explicit inputs
- role-aware picking for generation and editing is capability-driven and test-covered

## Risks

- persisted creative defaults could drift from runtime truth if snapshots stop projecting the
  requested-versus-effective merge result
- picker filtering could hide usable models if image-role metadata is not kept aligned with family
  capabilities
- negative-prompt or strength defaults could become misleading if the control plane persists values
  the runtime path later ignores

## Outcome

- m14_2_image_defaults_role_picker_completed
