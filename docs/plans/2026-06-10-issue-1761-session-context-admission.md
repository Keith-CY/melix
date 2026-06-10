# Issue 1761 Session Context Admission Receipts

## Goal

Make session-backed snapshot restoration visible as an untrusted-context
boundary when the control plane projects prior session state into a follow-up
worker request.

## Scope

This slice covers the Swift `RequestCoordinator` path that resolves an implicit
follow-up restore snapshot from `SessionGraphStore`. When the coordinator finds
a branch resume snapshot for the same session and branch, it attaches a
redacted `melix.untrusted_context_receipt.v1` receipt to the worker request
metadata before dispatch.

In scope:

- emit one session-context receipt when `SessionGraphStore` supplies an
  implicit follow-up restore snapshot;
- classify the receipt as `source_type = background_continuation`;
- set `owner_scope_checked = true` only for the session graph lookup that
  matched the request session and selected branch;
- store receipt metadata under `ExecutionMetadata.ext` keys namespaced as
  `melix.session_context.*`;
- keep receipt JSON limited to IDs, source fields, policy, and corrective
  guidance.

Out of scope:

- adding protobuf fields to `SessionState`, `SnapshotRef`, or worker requests;
- changing snapshot restore behavior, scheduler lanes, cache hints, prompt
  messages, or worker execution;
- validating caller-supplied explicit `restore_snapshot_id` values;
- implementing durable background-job, RAG, skill, or memory entrypoint stores.

## Best End-State Architecture

Session, RAG, skill, memory, and background-job continuation stores should each
perform owner-scope checks at their source-specific admission point and attach
redacted receipt evidence before untrusted data is projected into prompt or
model context.

For session follow-ups, the control plane already has the authoritative
`SessionGraphStore` lookup that decides which branch resume snapshot is reused.
That lookup is the narrow owner-scope check for this slice: the requested
session and selected branch must lead to the resume snapshot before the receipt
can claim `owner_scope_checked = true`.

## Performance Probes And Metrics

The changed path adds one small dictionary-to-JSON receipt after an in-memory
session graph lookup that already happens for follow-up restore. It does not
add filesystem IO, worker RPCs, hashing, protobuf regeneration, or model
inference.

Verification must include:

- focused red/green Swift test for session follow-up prefill request metadata;
- changed-scope coverage for touched Swift source and test files with at least
  95 percent coverage;
- full local pre-commit gate before commit on this host;
- PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

Metrics:

- No new runtime metric is required for this metadata-only receipt. The
  existing `session_graph.restore_snapshot_count` metric remains the restore
  behavior signal.

## Implementation Steps

1. Add a failing `RequestCoordinatorTests` case proving a session follow-up
   prefill request carries `melix.session_context.*` receipt metadata and does
   not leak raw prompt text.
2. Add a small Swift receipt helper for session-context admission evidence.
3. Attach the receipt from `resolvedRecoveryRequest` only when
   `SessionGraphStore` supplies the implicit restore snapshot.
4. Keep explicit request `restore_snapshot_id` unchanged and without a verified
   session-context receipt.
5. Update the unified agentic tool runtime contract with the session-context
   receipt namespace and owner-scope rule.
6. Run focused tests, changed-scope coverage, full local gate, and PR-scoped
   performance before merge.

## Success Criteria

- Implicit session follow-up restore requests include
  `melix.session_context.receipt_schema =
  melix.untrusted_context_receipt.v1`.
- The receipt uses `source_type = background_continuation`,
  `source_field = execution.cache_hints.restore_snapshot_id`, and
  `owner_scope_checked = true`.
- The receipt JSON records the selected snapshot ID as source metadata but does
  not include raw user message text, hidden reasoning text, or prompt bodies.
- Caller-supplied explicit restore snapshot IDs are not marked as
  owner-scope-checked by this session graph slice.
- Existing scheduler route selection, phase-aware prefill, and restore behavior
  remain unchanged.
