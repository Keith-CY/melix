# Issue 1761 Skill And Memory Batch Projection Plan

## Goal

Add a side-effect-free Python worker projection helper that lets future skill
and memory entrypoints admit several already-redacted skill or memory evidence
items at once while isolating malformed items into refusal receipts.

## Scope

This slice covers:

- a reusable `project_skill_memory_contexts` helper in
  `worker.runtime.skill_memory_context`;
- ordered admission of multiple skill and memory entries into one user-role
  prompt payload;
- per-entry refusal receipts for malformed source IDs, payloads, owner-scope
  metadata, or entrypoint receipt metadata;
- focused tests for mixed accepted/refused skill and memory entries;
- contract documentation for future concrete skill-store and memory-store
  callers.

This slice does not implement a skill store, memory store, skill lookup, memory
persistence, retrieval ranking, chat/session wiring, or owner-scope inference.
Callers must still pass already-redacted payload dictionaries and explicit
owner-scope evidence.

## Best End-State Architecture

Concrete skill and memory entrypoints should not manually stitch prompt payloads
or receipt arrays. They should convert store-specific records into redacted
entry descriptors, hand those descriptors to a shared projection helper, then
attach the returned prompt payload and receipts to the user-role message.

The helper should reuse the existing single-entry admission helpers so receipt
shape, source ID normalization, policy text, and fail-closed behavior stay
centralized. A malformed entry must not discard other admitted entries, because
future stores may return a mixed set of selected skills and memories where one
bad record should be visible as a refused segment instead of aborting the whole
prompt projection.

## Performance Probes And Metrics

The changed path performs one constant-time validation/admission pass per entry
and allocates small dictionaries/lists. It adds no filesystem scans, store
lookups, network calls, scheduler work, model inference, or tool execution.

Verification must include:

- focused red/green tests for `test_skill_memory_context.py`;
- adjacent prompt-context tests;
- changed-line coverage for touched Python files with at least 95 percent
  coverage;
- full local pre-commit gate before commit on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add failing tests for `project_skill_memory_contexts` that prove accepted
   skill and memory entries are projected into one ordered prompt payload with
   copied receipt dictionaries and no raw evidence text inside receipt JSON.
2. Add failing tests proving malformed entries append refusal receipts without
   preventing valid sibling entries from being admitted.
3. Implement entry dataclasses and the projection helper by delegating every
   item to `admit_skill_context` or `admit_memory_context`.
4. Update the unified runtime contract to document the batch projection helper
   and its side-effect-free boundary.
5. Run focused tests, adjacent tests, changed-line coverage, the full local
   gate, and the PR-scoped performance report before opening the PR.

## Success Criteria

- Multiple redacted skill and memory entries can be projected through one shared
  helper without bypassing the existing single-entry admission logic.
- Malformed entries produce `included = false` refusal receipts and no prompt
  payload while valid sibling entries remain admitted.
- Receipt JSON remains redacted from raw skill and memory payload text.
- The implementation does not add storage, lookup, ranking, or session mutation
  behavior.
