# Training dataset chunker segment count elision

## Scope

This Python-only performance slice is limited to the single-turn long-context
chunk search in `services/mlx-worker-python/worker/model_ops/training_dataset_chunker.py`.

## Registered Probe

The affected path is covered by the existing PR-scoped registered probe
`training-dataset-chunker-top-level-base-copy` in `infra/perf/pr_scoped_probes.json`.
The registry entry has focused `test_command`, `coverage_command`, and
`probe_command` entries and runs `scripts/training_dataset_chunker_top_level_copy_probe.py`.

## Optimization Slice

The previous streaming segment work guarantees that `_chunk_single_turn()` only
searches candidate `k` values after rejecting `k_floor > word_count`, so each
candidate `k` is `<= word_count`. For that domain `_iter_word_segments(words, k)`
yields exactly `k` non-empty segments. This slice removes the per-segment
`segment_count` bookkeeping and unreachable short-segment branch from the hot
candidate loop, preserving the same accepted chunk boundaries and early break on
over-budget segments.

## Success Metrics

- Focused chunker tests continue to pass.
- Changed-scope coverage for the touched chunker scope remains at least 95%.
- The registered local Linux probe reports lower or neutral `elapsed_ms_mean`
  without increasing `peak_bytes_mean` beyond the registered threshold.

## Linux Boundary

This is a Python-only path and is locally verifiable on Linux. Hosted PR-scoped
performance CI remains the merge gate for the registered probe report.
