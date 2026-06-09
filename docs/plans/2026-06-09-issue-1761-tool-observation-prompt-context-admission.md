# Issue 1761 Tool Observation Prompt Context Admission Plan

## Goal

Wire the generic tool-observation prompt-boundary receipt path through the
shared Python worker prompt-context admission primitive without changing
persisted trace shape, sanitized payload content, replay hashes, or receipt JSON
schema.

## Scope

This slice covers:

- `worker.runtime.tool_observation.ToolObservationRecord`;
- the existing `melix.agentic_tool_observation.v1` top-level
  `untrusted_context_receipts` evidence;
- the governing unified agentic tool runtime contract.

This slice does not add source-specific RAG, skill, memory, chat, background
continuation, or owner-scope admission checks. Those later entrypoints must
still decide whether a generic tool observation may be projected into final
prompt context.

## Best End-State Architecture

Prompt-visible untrusted data should use one admission primitive before it is
recorded as user-role prompt context. The shared Python worker primitive,
`worker.runtime.prompt_context`, owns the admission metadata contract and the
stable `melix.untrusted_context_receipt.v1` receipt shape for admitted and
refused prompt context segments.

Tool observations are the current shared tool-output evidence object. Routing
their generic payload receipt through `admit_prompt_context_segments` aligns
this concrete tool-output path with the same primitive already used by the
agentic judge prompt snapshot path, while preserving the existing observation
payload and replay semantics.

## Performance Probes And Metrics

The changed path builds one `PromptContextSegment` and one receipt per emitted
tool observation. Runtime cost remains constant per observation and does not
add model inference, tool execution, parsing, or payload hashing work beyond the
existing trace observation path.

Verification must include:

- a focused failing test proving tool observation receipts are generated through
  `admit_prompt_context_segments`;
- full `test_tool_observation.py`;
- changed-line coverage for the touched Python scope with at least 95 percent
  changed-line coverage;
- local pre-commit gate on this host;
- PR-scoped performance report with `Status: ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add a focused monkeypatch regression test that replaces
   `worker.runtime.tool_observation.admit_prompt_context_segments` and proves
   `ToolObservationRecord.untrusted_context_receipts` constructs the expected
   `PromptContextSegment`.
2. Update `worker.runtime.tool_observation` to import `PromptContextSegment`
   and `admit_prompt_context_segments` from `worker.runtime.prompt_context`.
3. Replace the direct `untrusted_context_receipt` call with a one-segment
   admission and return `admission.untrusted_context_receipts`.
4. Update `docs/unified-agentic-tool-runtime-contract.md` so the tool
   observation prompt boundary names the shared prompt-context admission
   primitive.
5. Run focused tests, changed-line coverage, full local gate, and scoped
   performance before committing.

## Success Criteria

- Generic tool observation admitted receipts are produced through
  `admit_prompt_context_segments`.
- Existing trace observation JSON shape, receipt fields, payload redaction,
  replay hashes, timeout metadata, and byte metrics remain unchanged.
- Receipt evidence still omits raw tool payload values.
- The contract clearly states that generic tool-output evidence uses the shared
  prompt-context admission primitive, while source-specific projection checks
  remain later #1761 work.
