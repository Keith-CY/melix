# Training Dataset Chunker Streaming Segments

## Goal

Avoid materializing every candidate user-content segment list during single-turn chunk search. The chunker can reject a candidate `k` as soon as the first rendered segment exceeds `chunk_size`, so it should generate candidate segments lazily and only retain accepted chunks.

## Linux-only constraint

This is a Python worker slice under `services/mlx-worker-python` and can be verified on Linux with focused pytest, changed-scope coverage, and a synthetic local performance probe.

## Touched files

- `services/mlx-worker-python/worker/model_ops/training_dataset_chunker.py`
- `services/mlx-worker-python/tests/test_training_dataset_chunker.py`

## Performance probe

Use a synthetic chunking workload that compares `origin/main` against the branch for repeated large single-turn samples. Measure:

- elapsed wall-clock time in milliseconds
- peak traced allocation in bytes
- emitted chunk count equivalence

The registered PR-scoped performance probe `training-dataset-chunker-top-level-base-copy` already watches the chunker implementation and focused tests, so touching this slice triggers hosted scoped validation without adding a new registry entry.

## Success metrics

- Focused tests pass.
- Changed executable line coverage is at least 95%.
- Local synthetic probe preserves emitted chunk counts and shows lower peak allocation or lower elapsed time versus `origin/main`.
- `git diff --check` passes.
