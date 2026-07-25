# Maintenance capability split single-strip performance

## Scope

This slice targets capability metadata parsing in `services/mlx-worker-python/worker/engine/maintenance_core.py`, specifically `_split_capability_values()` used by model-info capability lists.

## Probe coverage

`infra/perf/pr_scoped_probes.json` registers `maintenance-capability-split-single-strip` for the touched maintenance-core path. The entry includes focused `test_command`, `coverage_command`, and `probe_command` values, with `scripts/maintenance_capability_split_probe.py` measuring baseline list-comprehension splitting against the current implementation.

## Implementation plan

- Preserve comma-separated capability parsing semantics: trim whitespace, drop empty segments, keep order.
- Replace the list comprehension that calls `strip()` in both the expression and filter with a small loop that strips each segment once.
- Validate locally on Linux with the registered focused tests, changed-scope coverage, and the registered Python probe.

## 2026-07-25 cached list copy follow-up

This follow-up keeps the same `maintenance-capability-split-single-strip` registered probe and remains limited to `_split_capability_values()`. Multi-segment capability strings still use an LRU-cached parsed representation and callers still receive isolated mutable lists, but the cached representation is now a list copied with `list.copy()` instead of a tuple expanded through a new list literal. The single-value cache-hit path also avoids a per-call local cache alias and reads the module cache directly. The intended effect is to reduce repeated cached split materialization cost without changing trimming, empty-segment filtering, ordering, cache bounds, or caller mutation semantics.

## Validation boundary

This is a Python-only Linux-verifiable slice. No Swift runtime effect is claimed.
