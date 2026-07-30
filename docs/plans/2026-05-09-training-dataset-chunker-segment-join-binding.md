# Training Dataset Chunker Segment Join Binding

## Scope

This Python-only performance slice narrows the long-context dataset chunker hot path in `services/mlx-worker-python/worker/model_ops/training_dataset_chunker.py`.

## Probe Coverage

The affected path is already covered by the PR-scoped `training-dataset-chunker-top-level-base-copy` command-json probe in `infra/perf/pr_scoped_probes.json`. The registered probe includes focused `test_command`, `coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/model_ops/training_dataset_chunker.py`
- `services/mlx-worker-python/tests/test_training_dataset_chunker.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/training_dataset_chunker_top_level_copy_probe.py`

## Optimization

Bind the whitespace join callable once per `_iter_word_segments` invocation before the candidate segment loop. The behavior and segment boundaries stay unchanged, but the loop avoids repeated method lookup while evaluating many candidate chunks for long samples.

## Verification Plan

- Run the focused chunker regression tests from the registered probe.
- Run changed-scope coverage for the touched source, test, and probe files.
- Run the registered local probe on Linux and compare against an `origin/main` base worktree.
- Let GitHub Actions run the PR-scoped performance workflow before merge.

## 2026-07-20 output chunk loop local bindings

This follow-up Python-only slice keeps the same registered probe and narrows to
`_chunk_sample(...)` after chunk message groups have already been selected. Bind
`_copy_messages`, `chunks.append`, and the optional chunk-id prefix once before
the output materialization loop so every emitted chunk preserves the same shallow
source fields and independent message containers while avoiding repeated global
lookups and repeated prefix formatting setup.
