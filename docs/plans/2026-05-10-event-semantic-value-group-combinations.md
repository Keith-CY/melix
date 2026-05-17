# Event Semantic Value Group Combination Reuse

## Goal

Reduce overhead in event-extraction semantic action split/merge scoring by reusing precomputed two- and three-value semantic action groups for the common bounded action sizes instead of rebuilding those combinations after every cache clear.

## Scope

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/event_extraction_semantic_value_group_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Registered probe

The affected path is covered by the registered PR-scoped probe `event-extraction-semantic-value-group-cache`. The probe has focused `test_command`, `coverage_command`, and `probe_command` entries and reports:

- `elapsed_ms_mean` (lower is better)
- `peak_bytes_mean` (lower is better)
- `combination_build_calls_mean` (lower is better)
- `group_count_per_sample` (structural parity metric)

## Linux verification

This is a Python-only slice and is locally verifiable on Linux with focused pytest, changed-scope coverage, and the registered command-json performance probe.

## Success metrics

- Focused event extraction tests pass.
- Changed executable scope coverage is at least 95%.
- The registered local probe preserves `group_count_per_sample`, `combination_build_calls_mean`, and checksum while improving or staying within noise on `elapsed_ms_mean`.
