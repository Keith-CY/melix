# Issue 17 Qwen3-MoE LoRA Family Support

## Goal

Productize the experimental `qwen3moe` LoRA family slice without reopening the
already shipped dense-family baseline. This slice makes Qwen3-MoE trainable
through the existing Melix LoRA and QLoRA pipeline, keeps the default preset on
attention targets, and exposes expert projection presets as experimental
operator-tuned paths.

## Scope

- Add a `qwen3moe` family profile to the Python training config mapper.
- Expand Qwen3-MoE expert templates from the source model expert count, using
  `melix.text.moe.expert_count`; expert presets fail closed when that count is
  not confirmed by the live local model config.
- Mark `qwen3moe` catalog LoRA metadata as `experimental`; publish
  `training_ready=true` only when the live local model config confirms the MoE
  expert count.
- Reject unsafe quantized LoRA/QLoRA requests for embedding, LM head, and
  output-projection targets with `unsupported_lora_target_module`.
- Keep `deepseek-mla`, `mistral4`, `nemotron-h`, embedding families, and other
  advanced families blocked or not productized.
- Update the LoRA runbook, current status, and Module 6 planning note.

## Non-Goals

- No live 30B MoE fine-tune is required for this deterministic acceptance slice.
- No family-specific shortcut should bypass dataset validation, normalization,
  masking, adapter training, activation, or registry registration.
- No protocol or dependency changes are expected.

## Public Interface

- `qwen3moe` default LoRA preset: `attention`.
- `qwen3moe` supported presets:
  - `attention`: `q_proj`, `k_proj`, `v_proj`, `o_proj`
  - `qkv`: `q_proj`, `k_proj`, `v_proj`
  - `experts`: `gate_proj`, `up_proj`, `down_proj`
  - `attention_experts`: attention plus experts
  - `full`: attention plus experts; operator-facing alias for `attention_experts`
- Catalog metadata for discovered Qwen3-MoE text models:
  - `melix.lora.family_kind = moe`
  - `melix.lora.support_tier = experimental`
  - `melix.lora.training_ready = true` only when the registry confirms MoE
    expert count metadata from live model config
  - `melix.lora.default_target_preset = attention`

## Performance Probes And Metrics

- Training configuration normalization remains deterministic and bounded by
  `selected_layer_count * target_count * expert_count` for expert presets.
- Manifest evidence records `training.tokens_per_second`,
  `training.peak_memory_gb`, `training.job_duration_ms`, selected target
  modules, and quantized source metadata for the deterministic training path.
- Success metric for this slice: touched Python changed-line coverage is at
  least 95 percent, target tests pass, and `make py-test` passes.

## Verification

Run:

```bash
PYTHONPATH="$(pwd):$(pwd)/services/mlx-worker-python" uv run --locked --project services/mlx-worker-python --extra mlx pytest services/mlx-worker-python/tests/test_lora_model_ops.py services/mlx-worker-python/tests/test_model_registry_catalog.py services/mlx-worker-python/tests/test_training_dataset_builder.py -q
make py-test
coverage run + scripts/python_changed_line_coverage.py over touched Python files
git diff --check
```
