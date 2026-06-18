# Issue 1761 Agentic Judge Prompt Context Admission Plan

## Goal

Wire the agentic judge prompt snapshot boundary through the shared Python worker
prompt-context admission primitive without changing persisted prompt text,
receipt shape, or judge scoring behavior.

## Scope

This slice covers the Python worker agentic judge prompt snapshot entrypoint in
`worker.engine.evaluation_core`.

It will:

- build admitted prompt-context receipts through
  `worker.runtime.prompt_context.admit_prompt_context_segments`;
- build validator refusal receipts through
  `worker.runtime.prompt_context.refused_prompt_context_receipt`;
- keep `agentic-judge-prompt-snapshots.jsonl` message content unchanged;
- keep the `melix.untrusted_context_receipt.v1` receipt JSON shape unchanged;
- keep raw user payload values out of receipts.

This slice does not wire live chat, RAG stores, skill entrypoints, memory
entrypoints, background continuations, or additional owner-scope gates.

## Best End-State Architecture

All prompt assemblers should make one explicit admission decision per untrusted
segment before projecting it into a model-visible user-role payload. The shared
prompt-context primitive is the small Python worker abstraction for those
decisions: callers provide source metadata and segment values, and the primitive
returns both the user payload and matching data-only receipts or a typed refusal
receipt for rejected segments.

The agentic judge path is the current concrete prompt snapshot entrypoint with
stable fixture coverage. Wiring it through the primitive makes the existing
admission contract executable before broader RAG, skill, memory, and
background-continuation surfaces adopt the same boundary.

## Performance Probes And Metrics

The changed path is a deterministic Python loop over the existing agentic judge
user payload fields. Runtime cost remains linear in the number of prompt
segments and no additional model inference or tool execution is introduced.

Verification must include:

- focused pytest for prompt-context primitive and agentic judge prompt snapshot
  receipts;
- changed-line coverage for the touched Python scope with at least 95 percent
  changed-line coverage;
- the new helper-level prompt-context tests live in a focused test file so the
  registered evaluation PR-scoped probes keep measuring the production
  `evaluation_core.py` lines they exercise directly;
- full local pre-commit gate on this host;
- PR-scoped performance report with `Status: ok` and zero regressions.

## Implementation Steps

1. Add a focused failing test that monkeypatches the shared prompt-context
   admission function and proves agentic judge prompt receipts are generated
   through it.
2. Add a focused failing test that monkeypatches the shared refusal helper and
   proves agentic judge validation refusal receipts are generated through it.
3. Update `evaluation_core.py` imports to consume `PromptContextSegment`,
   `admit_prompt_context_segments`, and `refused_prompt_context_receipt`.
4. Replace the direct admitted receipt helper with segment construction plus
   `admit_prompt_context_segments`.
5. Replace the direct refusal receipt helper with
   `refused_prompt_context_receipt`.
6. Keep the helper-level admission and refusal tests in a focused prompt-context
   test file separate from the broad evaluation-core probe tests.
7. Run the focused red/green tests, changed-line coverage, full gate, and
   scoped performance report before committing.

## Success Criteria

- Agentic judge admitted receipts are produced through
  `admit_prompt_context_segments`.
- Agentic judge refusal receipts are produced through
  `refused_prompt_context_receipt`.
- Existing snapshot messages, receipt keys, refusal reasons, and no-leak
  validation behavior remain unchanged.
- Receipt evidence still omits raw prompt payload values.
