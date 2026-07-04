# Event Extraction Semantic Value-Group Cache

## Goal

Reduce repeated semantic action value-group combination construction in the event-extraction evaluator. The hot path scores action split/merge candidates and repeatedly requests the same index combinations for the same value counts within one semantic evaluation pass.

## Linux Constraint

This is a Python-only slice under `services/mlx-worker-python`, so it is locally verifiable on Linux with focused pytest, changed-scope coverage, and a synthetic performance probe.

## Touched Files

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/event_extraction_semantic_value_group_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Implementation Plan

1. Cache `_semantic_value_groups(value_count)` with a bounded LRU cache and return immutable tuples so callers can safely share cached groups.
2. Preserve existing group ordering and split/merge action semantics.
3. Add focused tests for cached identity, ordering, and the checked-in PR-scoped probe script.
4. Register a dedicated PR-scoped performance probe for the semantic value-group cache.

## Performance Probe

Probe ID: `event-extraction-semantic-value-group-cache`

The probe repeatedly requests semantic value groups for several action-value counts while wrapping the production `combinations` helper to count underlying combination construction. It reports:

- `elapsed_ms_mean` / `elapsed_ms_min` (lower is better)
- `peak_bytes_mean` (lower is better)
- `combination_build_calls_mean` (lower is better structural metric)
- checksum and workload-size metrics for output stability

## Success Metrics

- Focused pytest passes.
- Changed-scope coverage is at least 95%.
- Local base-vs-head probe shows materially fewer combination-build calls and improved elapsed time without changing output checksum.
- `git diff --check` passes.

## 2026-07-01 Follow-up Slice: Direct Precomputed Lookup

The first cache slice already precomputes the common `SEMANTIC_ACTION_GROUP_MAX_SIZE == 3`
value counts used by the registered probe. This follow-up keeps that behavior and
narrows one remaining Python overhead point: `_semantic_value_groups(...)` now uses
an index-addressable precomputed tuple before falling back to a bounded cached
builder for non-precomputed counts or patched group-size tests. The public helper
still exposes `cache_clear()` for tests and probe setup, but the common precomputed
path skips the `lru_cache` wrapper lookup.

Validation remains the registered `event-extraction-semantic-value-group-cache` probe,
focused event-extraction tests, changed-scope coverage, and GitHub PR-scoped
performance CI before merge.

## 2026-07-04 Follow-up Slice: Matching Entry Count Binding

The semantic value-group probe also exercises `_maximum_weight_semantic_value_group_matching(...)`,
where the recursive solver repeatedly checks whether the current candidate index reached
the ordered-entry boundary. This follow-up keeps the same dynamic-programming state,
tie-break ordering, and returned match payloads, but binds `len(ordered_entries)` once
before recursion so the terminal check uses a local integer instead of recomputing the
list length at every recursive visit.

The affected code path remains covered by the registered
`event-extraction-semantic-value-group-cache` probe, its focused pytest coverage, and the
PR-scoped performance workflow. This is Python-only and locally verifiable on Linux.
