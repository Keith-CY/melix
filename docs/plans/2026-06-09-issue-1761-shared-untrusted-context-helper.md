# Issue 1761 Shared Untrusted Context Helper Plan

## Scope

This slice introduces a shared Python worker helper for untrusted prompt-context
receipts and migrates the existing agentic judge prompt snapshot receipt
construction to that helper.

The slice covers:

- a reusable `worker.runtime.untrusted_context` helper for data-only untrusted
  prompt-context receipts
- admitted and refused receipt construction with the existing
  `melix.untrusted_context_receipt.v1` shape
- an optional source identifier for future retrieved-doc, skill, memory, and
  tool-output segments without changing existing agentic judge artifact JSON
- agentic judge prompt snapshot and refusal receipts that preserve their current
  persisted field values

This slice does not wire new retrieved-doc, skill, memory, background-job, or
live tool-output prompt surfaces. Those surfaces remain follow-up work under
#1761 and should reuse the helper introduced here when their concrete admission
points are added.

## Architecture

The Python worker already emits untrusted-context receipts from
`worker.engine.evaluation_core`, but the receipt builder is local to the
agentic judge surface. A shared runtime helper keeps the receipt schema, policy,
trust level, message role, owner-scope flag, and data-only corrective actions in
one place so future prompt-context entrypoints do not reimplement the boundary
shape.

The helper stays side-effect-free. It accepts source metadata and returns plain
JSON-serializable dictionaries. Existing judge snapshot code remains
responsible for building messages and validating no-leak payload keys; it
delegates only receipt construction.

## Performance Probes

This path allocates a small dictionary per prompt-context segment. The scoped
performance gate is expected to select the existing agentic judge prompt
snapshot tests or report no direct synthetic probe. Success means the PR-scoped
performance report is `Status: ok`, `Regressions: 0`, and
`Verification failures: 0`.

## Verification

Verification will include:

- focused red/green pytest for `worker.runtime.untrusted_context`
- focused agentic judge prompt snapshot tests proving persisted receipt JSON is
  unchanged after migration
- changed-scope coverage for the touched Python files
- `git diff --check`
- local PR-scoped performance report

## Implementation Steps

1. Add failing tests for admitted, refused, and optional-source-id receipt
   construction in `services/mlx-worker-python/tests/test_untrusted_context.py`.
2. Implement `services/mlx-worker-python/worker/runtime/untrusted_context.py`
   with shared receipt builders and schema constants.
3. Migrate `EvaluationCore._agentic_judge_untrusted_context_receipt` and
   `_agentic_judge_refusal_receipt` to call the shared helper while preserving
   the existing output shape.
4. Update `docs/unified-agentic-tool-runtime-contract.md` to name the helper as
   the reusable v1 prompt-context boundary primitive for follow-up #1761
   surfaces.
5. Run the focused tests, changed-scope coverage, whitespace check, and scoped
   performance report before opening the PR.
