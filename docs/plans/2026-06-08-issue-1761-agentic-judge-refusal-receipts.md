# Issue 1761 Agentic Judge Refusal Receipt Plan

## Goal

Record machine-readable refusal receipts when agentic judge prompt context is
rejected before prompt snapshot persistence.

## Scope

This slice covers the existing Python worker validator for
`agentic-judge-prompt-snapshots.jsonl` user payloads. It adds receipt evidence
for the two current rejection paths:

- unsupported user-payload fields
- forbidden nested no-leak keys such as hidden gold, credentials, tokens, and
  remote base URLs

This slice does not change judge scoring, prompt wording, accepted prompt
snapshot rows, generic chat prompt assembly, skill entrypoints, memory
entrypoints, background-job continuations, or broader RAG stores.

## Architecture

Accepted prompt segments already emit `melix.untrusted_context_receipt.v1`
receipts with `included = true`. Rejected segments should use the same schema
with `included = false`, `boundary_checked = true`, and a stable refusal reason
so operators can distinguish hidden instructions or unsupported wrapper shapes
from generic Python exceptions.

The implementation keeps `ValueError` compatibility by introducing a small
subclass that carries `refusal_receipts`. Existing callers that catch
`ValueError` keep working, while tests and future evidence publishers can read
the structured receipts.

## Performance Probes And Metrics

The new path only builds receipts when validation fails. Accepted snapshot rows
still use the fixed receipt loop from the previous slice. The changed
`evaluation_core.py` path selects the evaluation scoped performance probes.

Verification will include:

- focused pytest for validator refusal receipts
- changed-line coverage for modified Python and test lines with a target of at
  least 95 percent
- local PR-scoped performance report with `Status: ok`

## Implementation Steps

1. Add failing tests that assert unsupported-field and forbidden-key validation
   errors carry `refusal_receipts`.
2. Add a `ValueError` subclass for agentic judge context validation failures.
3. Add a helper that builds deterministic rejected untrusted-context receipts.
4. Update the validator to raise the subclass with refusal receipts for both
   existing rejection paths.
5. Update benchmark/evaluation and unified runtime contracts with the rejected
   receipt behavior.
6. Run focused tests, changed-line coverage, scoped performance, full gates,
   and PR checks.

## Success Criteria

- Unsupported user-payload fields fail before prompt snapshot persistence and
  expose receipts with `reason = unsupported_user_payload_field`.
- Forbidden nested keys fail before prompt snapshot persistence and expose
  receipts with `reason = forbidden_user_payload_key`.
- Refusal receipts use the same schema as admitted prompt-context receipts,
  mark `included = false`, and keep the segment in the user role/data-only
  policy.
- Accepted prompt snapshot rows remain unchanged.
