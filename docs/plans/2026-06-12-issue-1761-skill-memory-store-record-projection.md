# Issue 1761 Skill And Memory Store Record Projection Plan

## Goal

Add a side-effect-free Python worker projection bridge for future skill-store
and memory-store entrypoints so already-redacted store records are validated and
converted into prompt-context entries before prompt assembly.

## Scope

This slice covers:

- `worker.runtime.skill_memory_context.project_skill_memory_store_records`;
- validation of ordered skill and memory store record mappings before they are
  converted into `SkillMemoryContextEntry` descriptors;
- fail-closed refusal receipts for malformed record containers, non-mapping
  records, invalid `context_kind` values, and malformed source/payload/owner or
  receipt metadata fields;
- focused tests and contract documentation for future concrete skill, agent
  skill, pinned-memory, and retrieved-memory store callers.

This slice does not implement a skill store, memory store, retrieval ranking,
owner lookup, chat/session mutation, or filesystem access. Future concrete
entrypoints must still perform lookup, redaction, and owner-scope checks before
passing records to this helper.

## Best End-State Architecture

Concrete skill and memory stores should have one narrow prompt-boundary path:
store-specific code returns already-redacted record dictionaries, this bridge
validates record shape and converts each record into a typed
`SkillMemoryContextEntry`, and the existing batch projection helper owns prompt
payload assembly and receipt copying.

That keeps storage, retrieval, and ranking out of the boundary primitive while
preventing future callers from manually stitching prompt payloads or skipping
the established `skill` and `memory` untrusted-context receipts.

## Performance Probes And Metrics

The changed path performs one linear pass over an already-materialized list or
tuple of small record dictionaries, then delegates to the existing
`project_skill_memory_contexts` helper. It adds no filesystem scanning, store
lookups, model inference, scheduler work, tool execution, or network calls.

Verification must include:

- focused red/green tests for `test_skill_memory_context.py`;
- adjacent prompt-context tests;
- changed-line coverage for touched Python files with at least 95 percent
  coverage;
- full local pre-commit gate before commit on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add failing tests proving valid skill and memory store record dictionaries
   are projected through the existing skill/memory projection helper.
2. Add failing tests proving malformed record containers and non-mapping records
   produce refusal receipts with no admitted prompt payload.
3. Add failing tests proving invalid `context_kind` values and malformed
   required fields produce per-record refusal receipts without dropping valid
   sibling records.
4. Implement `project_skill_memory_store_records` by validating records into
   `SkillMemoryContextEntry` values, appending refusal receipts for invalid
   records, and delegating typed entries to `project_skill_memory_contexts`.
5. Update `docs/unified-agentic-tool-runtime-contract.md` to require future
   concrete skill and memory stores to use the store-record projection bridge.
6. Run focused tests, adjacent tests, changed-line coverage, the full local
   gate, and the PR-scoped performance report before opening the PR.

## Success Criteria

- Future skill and memory stores have a concrete side-effect-free entrypoint for
  already-redacted record dictionaries.
- Malformed store records fail closed before prompt assembly and emit
  `included = false` receipts.
- Valid sibling records remain admitted when another record is malformed.
- Receipt JSON stays redacted from raw skill and memory payload text.
- The implementation does not add storage, lookup, ranking, owner inference, or
  session mutation behavior.
