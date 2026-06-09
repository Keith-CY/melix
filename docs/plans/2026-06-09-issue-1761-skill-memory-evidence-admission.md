# Skill And Memory Evidence Admission

## Issue

Issue #1761 requires untrusted-context prompt boundaries for retrieved docs,
skills, memories, tool output, and background continuations. The previous source
evidence helper standardized receipt construction, but concrete skill and
memory prompt entrypoints still needed an admission primitive that validates the
wrapper shape before prompt assembly.

## Slice

Add a small Python worker `worker.runtime.source_evidence_context` helper for
skill and memory evidence. The helper validates the source identifier, payload
container, and owner-scope flag before admitting the payload through
`PromptContextSourceEvidence`.

Malformed skill or memory evidence raises a typed admission error with
`included = false` untrusted-context refusal receipts. This slice does not add a
durable skill store, memory store, live RAG store, or owner-lookup mechanism; it
gives those future entrypoints a concrete prompt-boundary admission API.

## Performance Probes

The changed path is constant-time metadata validation and receipt construction.
No registered performance probe is expected to match this slice.

Success metrics:

- skill and memory payload receipts remain payload-redacted
- invalid source identifiers, non-object payloads, and malformed
  `owner_scope_checked` values fail closed before prompt admission
- changed-line coverage for touched Python files is at least 95 percent
- PR-scoped performance report reports `Status: ok` with zero regressions

## Verification Plan

1. Add focused tests for admitted skill and memory evidence receipts.
2. Add focused tests for malformed skill and memory evidence refusal receipts.
3. Run focused pytest for the new source evidence context helper.
4. Run changed-line coverage for the touched helper and tests.
5. Run the repository gate required by the pre-commit hook before pushing.
