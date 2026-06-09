# Issue 1761 Prompt Context Segment Boundary Plan

## Goal

Add a small shared Python worker primitive for admitting or refusing untrusted
prompt-context segments before future retrieved-doc, skill, memory, chat, and
background-continuation surfaces project those segments into user-role prompt
payloads.

## Scope

- Add `worker.runtime.prompt_context` with a `PromptContextSegment` data model,
  an admission result, admitted receipt generation, and refusal receipt helper.
- Keep raw segment values out of receipts.
- Reject duplicate prompt payload fields so later callers cannot silently
  overwrite an admitted segment.
- Reject non-user message roles for untrusted prompt context.
- Migrate the existing agentic judge prompt snapshot receipt generation to use
  the new primitive without changing persisted prompt text or receipt shape.
- Update the unified agentic tool runtime contract with the shared primitive.

## Non-Goals

- Do not wire live chat, RAG, skill, memory, or background-job entrypoints in
  this slice.
- Do not add protocol schema fields.
- Do not copy private prompt bodies or segment values into receipts.
- Do not change agentic judge prompt wording or scorer behavior.

## Performance Probes

The changed path is deterministic Python prompt-context receipt assembly. The
expected cost is linear in the number of prompt segments and does not select a
registered performance probe today. The PR-scoped performance report must still
run and record selected probe count and regression status.

## Verification

- Focused prompt-context tests.
- Focused agentic judge prompt snapshot tests.
- Changed-line Python coverage for the new helper and migrated receipt path.
- Full pre-commit gate before commit on this host.
- Remote CI, PR evidence, and PR-scoped performance before merge.
