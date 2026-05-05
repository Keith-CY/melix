# Event Extraction Alignment Detail Reuse

## Goal

Reduce redundant soft-alignment work in event-extraction evaluation by reusing the per-pair alignment details already computed while building the optimal event matching matrix.

## Linux-only constraint

This is a Python-only optimization under `services/mlx-worker-python`, so it can be validated on Linux with focused pytest, changed-scope coverage, and a synthetic local performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `infra/perf/pr_scoped_probes.json`
- `docs/plans/2026-05-05-event-extraction-alignment-reuse.md`

## Performance probe definition

Register PR-scoped probe ID `event-extraction-alignment-reuse`.

The probe runs `evaluate_event_extraction(...)` against a synthetic multi-dialogue dataset with reordered gold/predicted events, monkeypatches `_event_alignment(...)` to count calls, and records:

- `elapsed_ms_mean` — lower is better
- `alignment_calls_mean` — lower is better, expected to drop from pair count plus matched count to pair count only
- `dialogue_count` and `event_count` guard rails — unchanged

## Success metrics

- Focused event extraction tests pass.
- Changed-scope coverage is at least 95% for touched executable Python files and tests.
- Local probe shows identical matched-event behavior and fewer `_event_alignment(...)` calls than `origin/main` on the same synthetic workload.
- `git diff --check` is clean.
