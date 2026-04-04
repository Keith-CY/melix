# Task Plan

## Goal

Land the first executable `M9.5` slice by adding a shared rich-output sanitizer and applying it to gateway payloads plus operator-facing rendering or export boundaries.

## Scope

- add a shared deterministic sanitizer to `MelixControlPlaneCore`
- sanitize gateway JSON payload text before it reaches downstream rendering surfaces
- sanitize app-side doctor or benchmark reports, chat transcript and markdown export, evaluation sample previews, and local error or event text
- add a deterministic smoke script and runbook for blocked HTML fragments and unsafe URI schemes
- close the slice with targeted verification, changed-line coverage, and roadmap status records

## Phases

1. Shared sanitizer and gateway enforcement
   - status: completed
   - evidence:
     - active plan: `docs/plans/2026-04-04-m9-5-rich-output-sanitization-slice.md`
     - landed shared sanitizer rules in `services/control-plane-swift/Sources/HTTPGateway/OpenAI/OpenAIHandler.swift`
     - gateway JSON payload and typed JSON response tests now cover HTML stripping, unsafe URI rejection, fenced-code preservation, idempotency, and metrics counters
2. App-side rendering and export sanitization
   - status: completed
   - evidence:
     - target surfaces: chat transcript rows, chat markdown export, doctor and benchmark report state, evaluation sample previews, and local errors
     - menu-bar tests now cover sanitized exports, report state, preview state, and desktop log projection
3. Verification and milestone closure
   - status: completed
   - evidence:
     - runbook: `docs/runbooks/rich-output-sanitization.md`
     - success metrics: `sanitized_output.enforcement_count`, `sanitized_output.blocked_html_fragment_count`, and `sanitized_output.unsafe_uri_rejection_count`
     - focused Swift verification and changed-line coverage close the touched executable scope without adding a duplicate Python sanitizer implementation

## Acceptance

- unsafe HTML fragments never reach operator-facing report, transcript, or export surfaces
- unsafe URI schemes are removed while safe markdown-like content remains readable
- repeated sanitization is idempotent
- the touched executable scope closes with changed-line coverage of at least `95%`

## Risks

- over-sanitization can damage useful diagnostic markdown or code fences unless fenced-code preservation is handled explicitly
- sanitization must happen at boundary layers only; mutating worker truth or export bundle schemas would increase regression surface unnecessarily

## Outcome

- completed
