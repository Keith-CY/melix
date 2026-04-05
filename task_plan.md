# Task Plan

## Goal

Start `M14.1` by making image variation and iterate flows explicit, typed, and lineage-aware across
the control-plane and worker contracts instead of treating every derived image request as a generic
image edit.

## Scope

- add typed image edit modes for `edit`, `variation`, and `iterate`
- allow control-plane image edits to reference a prior artifact by stable artifact ID
- preserve source-artifact and prompt-delta lineage through the worker artifact metadata returned to
  control-plane consumers
- keep the first slice bounded to protocol, control-plane, worker, and focused tests

## Measurement Points

- image edit requests can carry an explicit mode and optional `source_artifact_id` plus
  `prompt_delta`
- variation and iterate requests resolve a prior artifact ID into the worker-facing source image
  input without bypassing the existing image-job history
- returned generated artifacts preserve lineage metadata that identifies the parent artifact and
  requested edit mode
- changed-line coverage for the touched handwritten executable scope remains at or above `95%`

## Phases

1. Contract and slice design
   - status: completed
   - evidence:
     - reviewed the current `GenerateImage` / `EditImage` protocol messages and confirmed they only
       support raw image bytes or URIs, not artifact-derived variation or iterate semantics
     - inspected the current image runtime and read-model behavior and confirmed the worker already
       persists source and generated artifacts, so the missing piece is typed request and lineage
       propagation rather than a brand-new image pipeline
2. Typed variation and iterate contract
   - status: completed
   - evidence:
     - added typed `ImageEditMode` enums to the control-plane and worker protobuf contracts and
       regenerated the versioned Swift, Python, and descriptor outputs
     - taught the Swift control plane and OpenAI handler to resolve `source_artifact_id` into the
       stored artifact URI, enforce iterate-only `prompt_delta`, and preserve source-artifact plus
       source-job lineage in queued image jobs and worker requests
     - taught the worker image-edit runtime and terminal job descriptors to preserve
       `parent_artifact_id`, `source_job_id`, `prompt_delta`, and `edit_mode` lineage through
       deterministic image artifacts and job metadata
3. Verification and milestone bookkeeping
   - status: completed
   - evidence:
     - reran `make proto`, focused Swift image-job suites, focused Python image-runtime tests,
       repository Python tests, changed-line coverage, and `git diff --check`
     - updated the active `M14.1` plan plus the roadmap execution index to reflect the completed
       typed variation and iterate contract slice

## Acceptance

- variation and iterate requests are typed rather than implicit string conventions
- control-plane image jobs preserve lineage to their parent artifacts
- worker artifact metadata keeps enough lineage detail for later desktop consumers to render
  variation and iterate relationships without re-deriving them from file paths

## Risks

- artifact-ID resolution could silently break if control-plane image jobs do not reject unknown
  lineage references early
- prompt-delta semantics could become misleading if the runtime ignores them while the protocol
  claims to support iterate flows
- broadening the image request contract could destabilize existing generate and edit behavior if the
  new fields are not kept strictly optional

## Outcome

- m14_1_variation_iterate_contract_completed
