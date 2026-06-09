# Issue 1761 Tool Observation Boundary Receipt Plan

## Goal

Attach prompt-boundary receipts to normalized tool observations so generic tool
output persisted in an agentic trace is explicitly marked as untrusted,
data-only user-message context before downstream prompt assembly can reuse it.

## Scope

This slice covers the Python worker shared tool observation contract:

- `worker.runtime.tool_observation`
- `worker.runtime.untrusted_context`
- `melix.agentic_tool_observation.v1` trace observations emitted by
  deterministic tools and future tool executors using the shared normalizer
- the governing unified agentic tool runtime contract

This slice does not change judge prompt wording, generic chat prompt assembly,
skill entrypoints, memory entrypoints, RAG stores, or background-job
continuations. Those surfaces remain follow-up work under #1761, but they can
consume the new observation-level receipt instead of reconstructing the trust
boundary from tool metadata.

## Architecture

The best end state is that every segment crossing from retrieved or
tool-produced data into prompt-visible context carries a machine-readable
boundary receipt. Tool observations are the shared evidence object for current
agentic tools, SFT traces, rollouts, benchmark runs, and evaluations. Adding
the receipt at normalization time gives all consumers the same trust label
without requiring each adapter to duplicate receipt construction.

Each trace observation must include:

- `untrusted_context_receipt_count = 1`
- `untrusted_context_receipts[]` with one
  `melix.untrusted_context_receipt.v1` receipt
- `segment_id = <tool_call_id>:observation`
- `source_type = tool_observation`
- `source_field = payload`
- `message_role = user`
- `trust_level = untrusted`
- `policy = data_only`
- `boundary_checked = true`
- `included = true`
- `owner_scope_checked = false`
- a reason and corrective action that prohibit projecting tool output into
  system or developer instructions

The receipt is attached outside `payload` so existing payload hashes,
redaction, truncation, and replay fingerprints stay focused on sanitized tool
output. Replay metadata remains unchanged for identical payloads. The Python
worker must use `worker.runtime.untrusted_context.untrusted_context_receipt` so
the receipt schema is not redefined in `tool_observation.py`.

## Performance Probes And Metrics

The changed path adds a fixed one-receipt dictionary build per normalized tool
observation. The affected runtime file is covered by focused unit tests and the
PR-scoped performance selector.

Verification will include:

- focused pytest for the tool observation receipt shape
- full `test_tool_observation.py`
- changed-scope coverage for modified Python files with a target of at least
  95 percent
- local pre-commit performance report with `Status: ok`, regressions `0`, and
  verification failures `0`

## Implementation Steps

1. Add a failing test in
   `services/mlx-worker-python/tests/test_tool_observation.py` proving emitted
   trace observations include exactly one untrusted-context receipt with the
   stable shape above.
2. Attach the receipt count and receipt list in
   `ToolObservationRecord.as_agentic_trace_observation()` by delegating to the
   shared `untrusted_context_receipt` helper.
3. Keep the receipt outside the sanitized payload and replay metadata so payload
   redaction, truncation, metrics, and replay hashes remain deterministic and
   payload-focused.
4. Update `docs/unified-agentic-tool-runtime-contract.md` to define the generic
   tool-output prompt boundary receipt.
5. Run focused tests, changed-scope coverage, full local gates, scoped
   performance, and PR checks before merge.

## Success Criteria

- Every emitted shared tool observation carries one prompt-boundary receipt for
  the sanitized observation payload.
- Receipts mark tool output as untrusted, data-only, included user-role context
  and record that owner scope has not been checked by the generic normalizer.
- Existing payload redaction, truncation, metrics, and replay fingerprints
  remain deterministic and payload-focused.
- The unified runtime contract identifies this as the generic tool-output
  receipt slice, with skill, memory, RAG, chat prompt assembly, and
  background-job continuations left for later #1761 work.
