# LoRA normalized manifest probe registration

## Scope

This performance-maintenance slice registers the existing Python probe for LoRA
normalized dataset manifest I/O before changing the training pipeline behavior.
The affected runtime path is `worker.model_ops.lora_training_pipeline.LoRATrainingPipeline.run`.

## Registered probe

Add `lora-normalized-manifest-io-count` to `infra/perf/pr_scoped_probes.json` with
focused `test_command`, `coverage_command`, and `probe_command` entries covering:

- `services/mlx-worker-python/worker/model_ops/lora_training_pipeline.py`
- `services/mlx-worker-python/tests/test_lora_model_ops.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/lora_normalized_manifest_probe.py`

The probe reports:

- `elapsed_ms_mean`
- `manifest_write_text_calls_mean`
- `manifest_read_text_calls_mean`

## Validation plan

1. Run the focused registry/test command locally on Linux.
2. Run changed-scope coverage for the registry slice.
3. Run `scripts/lora_normalized_manifest_probe.py` locally on Linux.
4. Use GitHub Actions PR-scoped performance as the registered CI validation gate.

## Deferred optimization

This slice intentionally does not change LoRA training pipeline behavior. A later
optimization slice may use this registered probe to reduce normalized manifest
read/write overhead, with before/after metrics captured by the PR-scoped
performance workflow.
