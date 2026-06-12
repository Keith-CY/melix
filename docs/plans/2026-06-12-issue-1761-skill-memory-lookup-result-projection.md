# Issue 1761 Skill and Memory Lookup Result Projection Plan

## Goal

Add a side-effect-free Python worker projection helper for concrete skill-store
and memory-store lookup results that have already been redacted and owner-scope
checked by their caller.

## Architecture

The existing `worker.runtime.skill_memory_context` module owns the prompt
context boundary for skill and memory evidence. This slice keeps that ownership
and adds a higher-level lookup-result projection wrapper that accepts a mapping
with ordered `records`, delegates record validation to
`project_skill_memory_store_records`, and returns copied prompt payload,
untrusted-context receipts, refusal receipts, and an optional user-role message.

The helper does not implement a store, load skill files, read memory
persistence, rank results, infer owner scope, mutate sessions, or enqueue chat
messages. It only shapes already-redacted lookup results into prompt-ready
user-role data.

## Files

- Modify `services/mlx-worker-python/worker/runtime/skill_memory_context.py`
  - Add `SkillMemoryLookupResultProjection`.
  - Add `project_skill_memory_lookup_result`.
  - Reuse `project_skill_memory_store_records` for validation and receipt
    generation.
- Modify `services/mlx-worker-python/tests/test_skill_memory_context.py`
  - Add focused TDD coverage for admitted lookup results, malformed wrappers,
    refusal propagation, and copy isolation.
- Modify `docs/unified-agentic-tool-runtime-contract.md`
  - Document the lookup-result helper and its side-effect boundary.

## Implementation Steps

1. Add a failing test that imports `project_skill_memory_lookup_result` and
   verifies that a lookup result mapping with redacted skill and memory records
   returns prompt payload, copied receipts, and a user-role message with
   `untrusted_context_receipts`.
2. Add a failing test for malformed lookup-result wrappers. A non-mapping
   wrapper should produce no message, no user payload, no admitted receipts, and
   one refusal receipt with `source_field = lookup_result`.
3. Add a failing test proving record-level refusals are preserved while valid
   siblings still produce a message.
4. Implement the dataclass and helper with minimal copy isolation:
   - The top-level input must be a mapping.
   - The helper reads `lookup_result["records"]`.
   - It delegates to `project_skill_memory_store_records`.
   - It copies `user_payload`, admitted receipts, and refusal receipts.
   - It emits `lookup_message = None` when no admitted user payload exists.
5. Update the unified runtime contract with the helper name, wrapper semantics,
   refusal behavior, and non-goals.
6. Run focused pytest, changed-scope coverage, PR evidence validation, full
   local gate, and scoped performance before committing.

## Metrics

This Python worker slice is not a hot runtime path and performs no IO. The
changed-scope metrics are:

- focused pytest for `test_skill_memory_context.py`;
- changed-line coverage for touched Python files, target at least 95%;
- PR-scoped performance report status `ok` with zero regressions.
