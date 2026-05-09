# LoRA Normalized Dataset Manifest Single Write

## Goal

Avoid redundant disk I/O in the LoRA training preparation path by writing validation metadata into the normalized dataset manifest during the first snapshot write instead of reading, parsing, mutating, and rewriting the just-created manifest.

## Linux-only constraint

This is a Python worker slice. It is validated locally on Linux with focused pytest, changed-scope coverage, and an explicit synthetic probe.

## Touched files

- `services/mlx-worker-python/worker/model_ops/training_dataset.py`
- `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- `services/mlx-worker-python/tests/test_training_dataset_builder.py`
- `services/mlx-worker-python/tests/test_lora_model_ops.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/lora_normalized_manifest_probe.py`
- `infra/perf/pr_scoped_probes.json`

## Performance probe

Register `lora-normalized-manifest-single-write` in PR-scoped performance CI. The probe runs a synthetic LoRA training setup repeatedly and reports:

- `manifest_read_text_calls_mean` — lower is better, expected to drop from one reread per run to zero.
- `manifest_write_text_calls_mean` — lower is better, expected to drop from two manifest writes per run to one.
- `elapsed_ms_mean` — informational wall-clock timing.

## Success metrics

- Focused tests pass for the LoRA path and normalized snapshot helper.
- Changed-scope coverage is at least 95% for touched executable Python lines.
- Local probe shows the optimized path avoids the normalized manifest reread/rewrite while preserving manifest payload fields.
- PR-scoped performance CI selects and validates the registered probe.
