# Issue 1385 Effective Policy Receipts

## Goal

Productize model and operator generation policy selection by making the final
sampling, template, and reasoning decisions visible as stable effective-policy
receipts before a request reaches the worker.

## End-State Architecture

- Model policy lookup owns a pure catalog of recommended sampling and template
  policies. It returns status (`known`, `unknown`, or `operator_override`),
  normalized aliases, source metadata, and the recommended defaults without
  mutating a request.
- Policy application is a separate strict/non-strict step. Strict mode rejects
  unknown model policies with a typed operator-facing error; non-strict mode
  continues with gateway defaults while recording the unknown status.
- Request, preset, model, OCR, and gateway defaults merge field by field. A
  request override only replaces the field it explicitly sets; all remaining
  fields retain their highest-priority recommendation.
- Dispatch receipts record the final effective policy for sampling, chat
  template kwargs, reasoning mode, seed, stop strings, and output cap source.
  The receipt is copied into benchmark/eval rows and diagnostics bundles rather
  than reconstructed from ad hoc ext fields later.
- Template and reasoning defaults are explicit and overridable. Receipts record
  `reasoning_mode`, source, effort, template kwargs source, forced-template
  keys, and whether an operator/request override was applied.

## Current Slice

This slice adds the control-plane receipt surface without introducing the model
recommendation catalog yet:

- add request-local sampling source fields for effective temperature and
  `top_p`;
- preserve the existing output-cap source while making model/gateway policy
  fallback distinguishable in the effective receipt;
- add a `melix.text_effective_policy_receipt.v1` JSON receipt under
  `execution.ext` before dispatch;
- include individual ext mirrors for receipt schema, hash, sampling sources,
  chat-template source, reasoning source, and override booleans;
- keep existing worker behavior and legacy `melix.generation.*`,
  `melix.chat_template_kwargs.*`, and `melix.compat.*` receipts intact.

Out of scope for this slice:

- the alias-backed model recommendation catalog;
- strict unknown-model policy rejection;
- benchmark/eval row schema changes;
- diagnostics bundle propagation outside the already persisted worker request
  metadata.

## Metrics And Success Targets

- Changed-line coverage for the touched Swift request-shaping and receipt scope
  must be at least 95 percent.
- Existing `melix.generation.*` receipt fields must remain byte-for-byte
  compatible for covered tests.
- The new effective-policy receipt must serialize deterministically so its hash
  is stable for the same shaped request.
- Request overrides must be visible as overrides in the receipt without
  changing the final sampling values already covered by existing tests.

## Verification

- Focused red/green Swift tests for effective policy receipts.
- `swift test --package-path services/control-plane-swift --filter
  ControlPlaneTests.TextEndpointContractTests`
- Swift changed-line coverage for the touched request files and tests.
- Full repository gate before PR merge per `AGENTS.md`.

## Acceptance

- A translated text request with model sampling defaults and template kwargs
  emits an effective-policy receipt with model/request/forced sources.
- A request override records the override source for the overridden field while
  retaining model policy for untouched fields.
- Gateway defaults are recorded as gateway-sourced when no model policy is
  available.
- Existing generation, template, reasoning, compatibility, and gateway receipt
  tests continue to pass.
