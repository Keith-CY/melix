# Source Evidence Prompt Receipts

## Issue

Issue #1761 requires prompt-boundary evidence for retrieved documents, skills,
memories, tool output, and background continuations. Existing slices added the
generic Python prompt-context primitive and Swift chat message classification,
but Python source entrypoints still have to spell out source-specific reason
and corrective-action text by hand.

## Slice

Add a small Python worker helper layer for source-specific prompt evidence. The
helper covers retrieved document/image, skill, memory, and background
continuation evidence while reusing the existing
`worker.runtime.prompt_context` receipt shape.

This slice does not add a durable skill store, memory store, or live RAG store.
It gives those future entrypoints a single tested admission/refusal API so they
do not drift into ad hoc source-type strings or raw-payload receipts.

## Performance Probes

The changed path is constant-time metadata construction for prompt-context
receipts. No registered performance probe is expected to match this slice.

Success metrics:

- source-specific receipt construction remains payload-redacted
- invalid source types fail closed before receipt emission
- changed-line coverage for touched Python files is at least 95 percent
- PR-scoped performance report reports `Status: ok` with zero regressions

## Verification Plan

1. Add focused tests for source-specific skill, memory, and background
   continuation admission receipts.
2. Add a focused test for source-specific refusal receipts.
3. Add a focused test that unsupported source types fail closed.
4. Run focused pytest and changed-line coverage for `prompt_context.py` and
   `test_prompt_context.py`.
5. Run the repository gate required by the pre-commit hook before pushing.
