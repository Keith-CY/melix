# Training Dataset Chunker Top-Level Copy Optimization

## Goal

Reduce redundant top-level sample key filtering in `worker/model_ops/training_dataset_chunker.py` when a long sample emits many chunks.

## Linux Constraint

This is a Python-only worker slice and is verifiable on Linux with focused pytest, changed-scope coverage, and a local PR-scoped performance probe.

## Touched Files

- `services/mlx-worker-python/worker/model_ops/training_dataset_chunker.py`
- `services/mlx-worker-python/tests/test_training_dataset_chunker.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/training_dataset_chunker_top_level_copy_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance Probe

Register `training-dataset-chunker-top-level-base-copy` in `infra/perf/pr_scoped_probes.json`.

The probe builds one synthetic sample with many top-level metadata fields and long user content that splits into many chunks. It records:

- `elapsed_ms_mean`
- `peak_bytes_mean`
- `chunk_count`
- `top_level_key_count`
- `sample_count`

## Success Metrics

- Behavior preserved: chunk IDs, shallow shared top-level metadata/tools, copied message containers.
- Focused tests pass.
- Changed-scope coverage is at least 95% for touched executable Python/test/probe files.
- Local base-vs-head probe shows reduced or neutral latency/peak memory on the synthetic many-chunk workload.
