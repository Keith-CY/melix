# Issue 1761 Explicit Session Restore Receipt Plan

## Goal

Make caller-supplied session restore snapshot IDs visible as untrusted session
context boundaries without claiming owner-scope validation that has not run.

## Scope

This slice covers:

- control-plane `RequestCoordinator` handling for explicit
  `execution.cache_hints.restore_snapshot_id` values;
- session-context receipt evidence with `owner_scope_checked = false` for
  caller-supplied restore snapshot IDs;
- focused Swift tests for the explicit restore path; and
- contract documentation for the distinction between implicit session-graph
  restores and explicit caller-supplied restores.

This slice does not validate explicit snapshot ownership, change snapshot
lookup, alter cache restore routing, or add a durable RAG, skill, or memory
store.

## Best End-State Architecture

Every restore snapshot ID that can influence prompt continuation should have a
redacted untrusted-context receipt. Session-graph selected snapshots may record
`owner_scope_checked = true` because the request session and branch lookup has
already matched. Caller-supplied explicit restore IDs should record the same
session-context boundary but keep `owner_scope_checked = false` until a future
owner-aware snapshot lookup validates the ID.

## Performance Probes And Metrics

The changed path creates one small JSON receipt for requests that already carry
an explicit restore snapshot ID. It does not add store scans, model inference,
filesystem IO, or scheduler work.

Verification must include:

- a focused Swift test for explicit restore snapshot receipt evidence;
- changed-line coverage for the touched Swift request-coordinator scope at or
  above 95 percent;
- the local pre-commit gate before commit on this host; and
- a PR-scoped performance report with status `ok`, regressions `0`, context
  regressions `0`, and verification failures `0`.

## Implementation Steps

1. Add a failing request-coordinator test that expects explicit restore
   snapshot IDs to attach `melix.session_context.*` receipt ext fields with
   `owner_scope_checked = false`.
2. Extend `SessionContextBoundaryReceipts` to accept the owner-scope result
   used in the receipt while preserving the existing implicit restore default.
3. Attach an explicit restore receipt before implicit session-graph restore
   resolution, without overwriting existing receipt ext fields.
4. Update the unified runtime contract to document explicit restore receipt
   semantics.
5. Run focused Swift tests, coverage, local gate, and PR-scoped performance
   before opening the PR.

## Success Criteria

- Explicit restore snapshot IDs are no longer invisible to session-context
  receipt evidence.
- Explicit restore receipts do not claim owner-scope validation.
- Implicit session-graph restore receipts continue to record
  `owner_scope_checked = true`.
- No raw prompt text, hidden reasoning text, or private prompt content appears
  in the receipt JSON.
