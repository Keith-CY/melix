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
the no-truncation branch, keep the generic iterable loop unchanged and add a
list/tuple-specific fast path that seeds running totals from index 0, then scans
remaining entries by index. This preserves generator semantics while removing the
per-entry `sample_count == 0` bootstrap branch from the common materialized
sequence path used by the registered probe.

2026-07-24 implementation note: a generic `next(iterator, None)` variant was
measured locally and rejected because it regressed the no-limit probe path. The
accepted implementation is limited to list/tuple inputs and keeps the existing
iterator loop for one-pass generators.

## Verification

- Focused response-only boundary unit tests.
- Changed-scope coverage from the registered probe entry.
- Registered local probe `scripts/response_only_boundary_slots_probe.py` on
  Linux.

## Linux Boundary

This is a Python-only slice and is locally verifiable on Linux. No Swift runtime
behavior is changed.
