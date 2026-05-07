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
