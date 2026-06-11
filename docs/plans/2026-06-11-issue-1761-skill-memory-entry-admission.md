# Issue 1761 Skill And Memory Entry Admission Hardening Plan

## Goal

Harden the Python worker skill and memory batch projection boundary so malformed
untyped batch items become refusal receipts instead of aborting prompt
assembly.

## Scope

This slice covers:

- defensive admission of non-`SkillMemoryContextEntry` objects passed to
  `worker.runtime.skill_memory_context.project_skill_memory_contexts`;
- refusal receipts with `source_field = entry` for malformed untyped batch
  items;
- preservation of valid sibling skill and memory entries after malformed items;
- contract documentation for future skill-store and memory-store callers.

This slice does not add skill lookup, memory persistence, retrieval ranking,
chat/session wiring, owner-scope inference, or any new prompt payload shape.

## Best End-State Architecture

Concrete skill and memory stores should treat batch projection as the single
prompt-context boundary for already-redacted skill and memory evidence. The
projector should reject malformed records locally, record a stable refusal
receipt, and continue admitting later valid entries so one bad store record does
not erase unrelated user-role context.

The defensive branch should reuse the existing refusal receipt helper and keep
the public receipt shape aligned with the retrieval batch projector. The default
fallback is a skill-context refusal because the malformed object has no trusted
kind metadata to distinguish a skill record from a memory record.

## Performance Probes And Metrics

The changed path adds one constant-time `isinstance` check per projected item.
It adds no filesystem scans, store lookups, network calls, scheduler work, model
inference, or tool execution.

Verification must include:

- a red/green test for malformed untyped batch items in
  `test_skill_memory_context.py`;
- the full focused `test_skill_memory_context.py` file;
- adjacent prompt-context and retrieval-context tests;
- changed-line coverage for `worker.runtime.skill_memory_context` at or above
  95 percent;
- a local scoped performance report with status `ok` and zero regressions;
- the repository pre-commit gate before commit.

## Implementation Steps

1. Add a failing test proving `project_skill_memory_contexts` refuses `None` and
   plain dictionaries as malformed entries while preserving a later valid memory
   entry.
2. Run the new test and verify it fails because `_admit_entry` tries to read
   `context_kind` from a non-entry object.
3. Add a defensive `isinstance(entry, SkillMemoryContextEntry)` guard at the
   start of `_admit_entry`.
4. Update the unified agentic tool runtime contract to state that non-entry
   objects produce `source_field = entry` refusal receipts.
5. Run focused tests, adjacent tests, coverage, scoped performance reporting,
   and the pre-commit gate before opening a pull request.

## Success Criteria

- Non-`SkillMemoryContextEntry` batch items produce `included = false` refusal
  receipts instead of raising `AttributeError`.
- Valid sibling skill or memory entries remain admitted after malformed untyped
  items.
- The new behavior is documented for future concrete skill and memory stores.
- The PR performance report shows no regressions.
