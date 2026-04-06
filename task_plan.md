# Task Plan

## Goal

Close `M14.4` by adding live image-iteration integration coverage, repository-owned lineage and
timeout evidence, and operator runbook material that reproduces variation, iterate, and redo
workflows from stored artifact and job metadata alone.

## Scope

- add live integration coverage for baseline generate, variation, iterate, redo reconstruction,
  timeout, and cancel evidence across the shipped HTTP image surface
- extend the repository-owned image metrics smoke so it records variation, iterate, lineage, and
  timeout evidence instead of only baseline generate or edit latency
- update the image operator runbook and runbook indexes so contributors can reproduce iterative
  creative workflows and inspect lineage without unwritten desktop-local context

## Measurement Points

- one live smoke proves that a generated artifact can seed a variation request, an iterate request,
  and a redo reconstruction driven from persisted job recipe truth
- response payloads and recorded evidence keep `source_artifact_id`, `parent_artifact_id`,
  `prompt_delta`, `edit_mode`, and timeout policy visible enough to inspect lineage and recovery
  behavior after the run completes
- repository-owned metrics output distinguishes baseline generation, variation, iterate, queueing,
  cancelation, and timeout-triggered failure evidence
- changed-line coverage for the touched handwritten executable scope remains at or above `95%`

## Phases

1. Current-state review and evidence-gap mapping
   - status: completed
   - evidence:
     - reviewed `M14.4`, the `M14` umbrella plan, the existing Phase 7 smoke, and the image
       operator runbook and confirmed the repository still lacks one live path that proves
       variation, iterate, and redo reconstruction from persisted lineage
     - confirmed current metrics and runbook material still focus on baseline generate or edit,
       queueing, cancelation, and timeout evidence rather than iterative follow-up workflows
2. Live image-iteration integration evidence
   - status: completed
   - evidence:
     - added a live integration smoke that drives baseline generation into variation and iterate
       requests using `source_artifact_id` and reconstructs redo from the returned job recipe plus
       lineage fields
     - asserted persisted lineage and timeout fields directly from shipped HTTP payloads instead of
       internal test-only helpers, including `request_timeout_seconds`, `source_artifact_id`,
       `source_job_id`, `prompt_delta`, `edit_mode`, `recipe`, and `parent_artifact_id`
3. Metrics and evidence reporting
   - status: completed
   - evidence:
     - extended the repository-owned image metrics smoke to print variation, iterate, redo, and
       timeout evidence alongside the existing Phase 7 latency and queue metrics
     - kept the evidence reproducible from repository scripts and runtime artifacts alone through
       `make phase7-metrics`, including real local output for `image_variation`, `image_iterate`,
       `image_redo`, and `image_timeout`
4. Runbook and milestone bookkeeping
   - status: completed
   - evidence:
     - updated the image operator runbook and runbook index so contributors can reproduce the
       iterative workflow and inspect lineage or timeout recovery from documented commands
     - updated the roadmap execution index and progress log to close `M14.4` and complete `M14`
5. Verification and commit
   - status: completed
   - evidence:
     - reran focused Swift gateway tests, focused Python script tests, focused iteration
       integration coverage, real `make phase7-metrics`, and changed-line coverage for the touched
       Swift and Python scope
     - prepared a metrics report and milestone bookkeeping for a signed commit

## Acceptance

- iterative image workflows have live integration coverage and reproducible lineage evidence
- operators can reproduce variation, iterate, redo, timeout, and cancel flows from repository
  artifacts and documented commands alone
- `M14` can be treated as closed in the roadmap execution index once `M14.4` evidence lands

## Risks

- if the redo evidence depends on UI-only state, the runbook will not be reproducible from
  repository artifacts alone
- if the metrics smoke emits only latency numbers without lineage context, the milestone will still
  lack the operator-visible evidence required by `M14.4`
- if the new integration smoke reuses existing helpers too loosely, it may pass without actually
  proving variation or iterate lineage on the shipped HTTP contract

## Outcome

- m14_4_iteration_lineage_evidence_completed
