# Event Extraction Alignment Payload Reuse

## Goal

Reduce redundant event-alignment work in `evaluate_event_extraction()` by reusing the per-pair alignment payloads already computed during dialogue event matching.

## Linux-only constraint

This is a Python worker optimization and is locally verifiable on Linux with focused pytest, changed-scope coverage, and a synthetic performance probe.

## Touched files

- `services/mlx-worker-python/worker/productization/event_extraction.py`
- `services/mlx-worker-python/tests/test_event_extraction.py`
- `docs/plans/2026-05-08-event-extraction-alignment-payload-reuse.md`

## Implementation plan

1. Retain `_event_alignment(...)` payloads in `_align_dialogue_events()` keyed by `(gold_index, pred_index)` while building score/accepted matrices.
2. In `evaluate_event_extraction()`, look up matched-pair alignment details from that cached payload instead of recomputing `_event_alignment(...)` for every matched pair.
3. Add a focused regression test that monkeypatches `_event_alignment(...)` and proves evaluation calls it exactly once per gold/pred pair.

## Performance probe

Run a local synthetic evaluation probe that compares the current branch against a detached `origin/main` worktree on the same workload:

- 40 dialogues
- 8 gold events and 8 prediction events per dialogue
- reordered predictions so every dialogue has matched pairs

Metrics:

- `event_alignment_calls`: lower is better; expected reduction from `dialogues * (gold * pred + matched)` to `dialogues * gold * pred`.
- `elapsed_ms`: lower is better; timing is secondary to the deterministic call-count reduction.

## Success metrics

- Focused pytest passes.
- Changed-scope coverage is at least 95% for touched executable Python lines.
- Probe shows fewer `_event_alignment(...)` calls with identical matched-pair count.
- `git diff --check` passes.
