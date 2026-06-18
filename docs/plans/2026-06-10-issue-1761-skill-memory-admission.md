# Issue 1761 Skill And Memory Admission Plan

## Goal

Add a small Python worker primitive that validates already-redacted skill and
memory evidence before future entrypoints can project it into user-role prompt
payloads, and records admitted or refused `skill` and `memory`
untrusted-context receipts through the shared prompt-context admission helper.

## Scope

This slice covers:

- `worker.runtime.skill_memory_context` as a reusable admission/refusal
  boundary for future skill and memory prompt-context entrypoints.
- Focused Python tests for admitted skill and memory payloads, malformed-field
  refusal receipts, and reuse of `admit_prompt_context_segments`.
- `docs/unified-agentic-tool-runtime-contract.md` documentation for the
  skill/memory primitive.

This slice does not implement a skill store, memory store, live RAG retrieval,
skill execution, memory persistence, or chat/session wiring. Future callers
must pass already-redacted payload dictionaries and perform their own
owner-scope checks before admission.

## Best End-State Architecture

Skill manifests, skill search results, memory snippets, and pinned memories are
untrusted local context. Future retrieval and prompt assembly surfaces should
call a narrow admission helper with already-redacted evidence, receive a
user-role prompt payload, and attach receipt evidence that records the data-only
boundary without raw source content.

The helper belongs in the Python worker runtime beside `prompt_context`,
`tool_observation`, and `background_continuation`. It is a prompt-boundary
primitive, not a storage or retrieval layer. It delegates receipt creation to
`admit_prompt_context_segments` and `refused_prompt_context_receipt` so skill
and memory evidence uses the same schema as retrieved documents, tool
observations, chat projections, and background continuations.

## Performance Probes And Metrics

The changed path validates one small metadata dictionary and emits one receipt
per admitted skill or memory payload. Runtime cost is constant per admitted
source payload and does not add filesystem scanning, store lookups, model
inference, or scheduler work.

Verification must include:

- focused red/green tests for `test_skill_memory_context.py`;
- adjacent prompt-context regression tests;
- changed-line coverage for the touched Python files with at least 95 percent
  coverage;
- full local pre-commit gate before commit on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add failing tests for `admit_skill_context` and `admit_memory_context`:
   - accepted payloads return `PromptContextAdmission.user_payload` with
     `skill` or `memory` fields;
   - receipts use `source_type = skill|memory` and omit raw evidence text;
   - monkeypatching `admit_prompt_context_segments` proves the helper uses the
     shared prompt-context primitive.
2. Add failing tests for malformed payload fields:
   - non-string source IDs, non-dict payloads, and non-boolean
     `owner_scope_checked` are refused before admission;
   - each refusal carries an `included=false` receipt with reason
     `invalid_skill_context_field` or `invalid_memory_context_field`.
3. Implement `worker.runtime.skill_memory_context` with:
   - `SkillMemoryContextAdmissionError`;
   - `admit_skill_context(skill_id, skill_payload, owner_scope_checked)`;
   - `admit_memory_context(memory_id, memory_payload, owner_scope_checked)`;
   - deterministic `segment_id = <source_id>:skill-context` or
     `<source_id>:memory-context`;
   - source ID equal to the redacted skill or memory identifier.
4. Update the unified agentic tool runtime contract to specify this primitive
   as the required future admission boundary for skill and memory prompt
   evidence.
5. Run focused tests, adjacent tests, changed-line coverage, full local gate,
   and PR-scoped performance before opening the PR.

## Success Criteria

- Skill and memory evidence can be admitted through reusable primitives before
  prompt projection.
- Refused malformed skill and memory fields produce machine-readable refusal
  receipts and no user payload.
- Receipt evidence uses `melix.untrusted_context_receipt.v1`, records
  `source_type = skill|memory`, and omits raw source content.
- The implementation does not create a skill or memory store or change existing
  chat/session behavior.
