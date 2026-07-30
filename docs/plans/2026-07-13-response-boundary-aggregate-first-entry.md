# Response-only boundary aggregate first-entry fast path

## Goal

Reduce the no-truncation response-only boundary aggregation overhead by avoiding
the one-iteration bootstrap loop used only to seed running min/max totals.

## Scope

- Python-only worker slice.
- Touch only `worker.model_ops.response_only_boundary` and its focused tests.
- Keep the existing registered PR-scoped probe
  `response-only-boundary-slotted-records` as the performance gate.

## Approach

The aggregate helper already accepts any iterable and performs a single pass. For
the no-truncation branch, seed the first entry with `next(iterator, None)` and
then continue the remaining stream in the existing loop. This preserves generator
semantics while removing the synthetic `for ... break` bootstrap path from the
hot aggregation loop.

## Verification

- Focused response-only boundary unit tests.
- Changed-scope coverage from the registered probe entry.
- Registered local probe `scripts/response_only_boundary_slots_probe.py` on
  Linux.

## Linux Boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior is changed.
